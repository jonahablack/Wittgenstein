"""Live self-aware pipeline API (docs/live-pipeline-plan.md §7).

- GET  /live/config                         presets, providers available here, embedders
- GET  /live/corpora                        loaded corpora and their warm-up status
- POST /live/corpora                        upload .txt / .md / .pdf files as a new corpus
- GET  /live/corpora/{id}                   one corpus
- GET  /live/corpora/{id}/documents/{doc}   full document text, for "Show me"
- POST /live/runs                           run a question; streams Server-Sent Events
- GET  /live/runs/{run_id}                  a stored run (events + outcomes), for replay
- POST /live/check                          check an EXTERNAL pipeline's run (docs/integration.md)
- POST /live/check/batch                    up to MAX_BATCH such checks (e.g. replaying logs)
- POST /v1/check, /v1/check/batch           the same, under a stable versioned path

Integration endpoints require an API key when the server sets WITTGENSTEIN_API_KEYS
(comma-separated): send it as `Authorization: Bearer <key>` or `X-API-Key: <key>`.
"""

from __future__ import annotations

import asyncio
import hmac
import json
import os
import threading
from collections.abc import AsyncIterator
from typing import Any

from fastapi import APIRouter, Depends, File, Form, Header, HTTPException, UploadFile
from pydantic import BaseModel, Field
from sse_starlette.sse import EventSourceResponse

from wittgenstein.core.enums import LiveEventType
from wittgenstein.live.embedding import (
    DEFAULT_EMBEDDER,
    EMBEDDER_CHOICES,
    CachingEmbedder,
    EmbedCallbackError,
    HttpEmbedder,
)
from wittgenstein.live.events import LiveEvent
from wittgenstein.live.external import ExternalCheckRequest, GeneratorCallbackError, check_external
from wittgenstein.live.generate import PROVIDER_CHOICES, available_providers
from wittgenstein.live.pipelines import DEFAULT_PIPELINE, PRESETS
from wittgenstein.live.runner import run_query
from wittgenstein.live.store import corpora, extract_text, runs, slug

router = APIRouter(prefix="/live", tags=["live"])
v1 = APIRouter(prefix="/v1", tags=["v1"])
MAX_BATCH = 50
API_VERSION = "1.1"


def require_api_key(
    authorization: str | None = Header(default=None),
    x_api_key: str | None = Header(default=None),
) -> None:
    """No-op unless WITTGENSTEIN_API_KEYS is set; then one of its keys is required."""
    keys = [k.strip() for k in os.environ.get("WITTGENSTEIN_API_KEYS", "").split(",") if k.strip()]
    if not keys:
        return
    given = x_api_key or (
        authorization[7:].strip() if authorization and authorization.lower().startswith("bearer ") else None
    )
    if not given or not any(hmac.compare_digest(given, k) for k in keys):
        raise HTTPException(401, "A valid API key is required (Authorization: Bearer <key> or X-API-Key).")


MAX_UPLOAD_BYTES = 40 * 1024 * 1024
MAX_QUERY_CHARS = 2000


@router.get("/config")
def config() -> dict[str, Any]:
    return {
        "pipelines": [
            {
                "pipeline_id": p.pipeline_id,
                "label": p.label,
                "description": p.description,
                "chunker": p.chunker,
                "channels": [c.value for c in p.channels],
                "embedder": p.embedder,
                "k_policy": p.k_policy.value,
                "k": p.k,
                "token_budget": p.token_budget,
            }
            for p in PRESETS.values()
        ],
        "default_pipeline": DEFAULT_PIPELINE,
        "providers": {name: available_providers().get(name, False) for name in PROVIDER_CHOICES},
        "embedders": sorted(EMBEDDER_CHOICES),
        "default_embedder": DEFAULT_EMBEDDER,
    }


@router.get("/corpora")
def list_corpora() -> list[dict[str, Any]]:
    return [r.summary() for r in corpora.list()]


@router.post("/corpora")
async def upload_corpus(title: str = Form(...), files: list[UploadFile] = File(...)) -> dict[str, Any]:
    docs: dict[str, str] = {}
    titles: dict[str, str] = {}
    total = 0
    for f in files:
        data = await f.read()
        total += len(data)
        if total > MAX_UPLOAD_BYTES:
            raise HTTPException(413, f"Upload exceeds {MAX_UPLOAD_BYTES // (1024 * 1024)} MB.")
        name = f.filename or "document"
        if not name.lower().endswith((".txt", ".md", ".markdown", ".pdf")):
            raise HTTPException(415, f"{name}: only .txt, .md and .pdf files are supported.")
        try:
            text = extract_text(name, data)
        except Exception as e:  # noqa: BLE001 -- a malformed file is a client error, reported as such
            raise HTTPException(422, f"{name}: couldn't read text ({type(e).__name__}).") from e
        doc_id = slug(name.rsplit(".", 1)[0])
        while doc_id in docs:
            doc_id += "-2"
        docs[doc_id] = text
        titles[doc_id] = name
    try:
        rec = corpora.add(title.strip() or "Untitled", docs, "upload", titles=titles)
    except ValueError as e:
        raise HTTPException(422, str(e)) from e
    return rec.summary()


def _record(corpus_id: str):  # noqa: ANN202
    rec = corpora.get(corpus_id)
    if rec is None:
        raise HTTPException(404, f"No corpus {corpus_id!r}.")
    return rec


@router.get("/corpora/{corpus_id}")
def get_corpus(corpus_id: str) -> dict[str, Any]:
    return _record(corpus_id).summary()


@router.get("/corpora/{corpus_id}/documents/{document_id}")
def get_document(corpus_id: str, document_id: str) -> dict[str, Any]:
    rec = _record(corpus_id)
    if document_id not in rec.documents:
        raise HTTPException(404, f"No document {document_id!r} in {corpus_id!r}.")
    return {
        "document_id": document_id,
        "title": rec.titles.get(document_id, document_id),
        "text": rec.documents[document_id],
    }


class RunRequest(BaseModel):
    corpus_id: str
    query: str = Field(..., min_length=2, max_length=MAX_QUERY_CHARS)
    pipelines: list[str] = Field(default_factory=lambda: [DEFAULT_PIPELINE], min_length=1, max_length=6)
    provider: str = "extractive"
    counterfactual: bool = Field(
        default=False,
        description="Also test whether the model answers from the passages (LLM providers only; up to 2 extra "
        "generations).",
    )


@router.post("/runs")
async def start_run(req: RunRequest) -> EventSourceResponse:
    rec = _record(req.corpus_id)
    if rec.status != "ready" or rec.corpus is None:
        raise HTTPException(
            409, f"Corpus {req.corpus_id!r} is {rec.status}" + (f": {rec.error}" if rec.error else ".")
        )
    unknown = [p for p in req.pipelines if p not in PRESETS]
    if unknown:
        raise HTTPException(422, f"Unknown pipeline(s): {unknown}")
    if req.provider not in PROVIDER_CHOICES:
        raise HTTPException(422, f"Unknown provider {req.provider!r}")
    if not available_providers().get(req.provider):
        raise HTTPException(422, f"Provider {req.provider!r} isn't configured on this server.")

    loop = asyncio.get_running_loop()
    queue: asyncio.Queue[LiveEvent | None] = asyncio.Queue()
    corpus = rec.corpus

    def forward(ev: LiveEvent) -> None:
        loop.call_soon_threadsafe(queue.put_nowait, ev)

    def work() -> None:
        try:
            result = run_query(
                corpus,
                req.query,
                req.pipelines,
                req.provider,
                sink=forward,
                counterfactual=req.counterfactual,
            )
            runs.put(result)
        except Exception:  # noqa: BLE001 -- the runner already emitted an ERROR event on the stream
            pass
        finally:
            loop.call_soon_threadsafe(queue.put_nowait, None)

    threading.Thread(target=work, daemon=True, name="live-run").start()

    async def events() -> AsyncIterator[dict[str, str]]:
        while True:
            ev = await queue.get()
            if ev is None:
                return
            yield {"event": ev.type.value, "id": str(ev.seq), "data": json.dumps(ev.model_dump(mode="json"))}

    return EventSourceResponse(events(), ping=10)


_EMBEDDERS: dict[tuple[str, str | None], CachingEmbedder] = {}
_EMBEDDERS_LOCK = threading.Lock()


def _callback_embedder(url: str, model: str | None, headers: dict[str, str] | None) -> CachingEmbedder:
    """One measured embedder per callback URL, so a caller's model is characterized once
    per document rather than on every request."""
    key = (url, model)
    with _EMBEDDERS_LOCK:
        if key not in _EMBEDDERS:
            _EMBEDDERS[key] = CachingEmbedder(HttpEmbedder(url, model, headers))
        return _EMBEDDERS[key]


def _check_one(req: ExternalCheckRequest) -> dict[str, Any]:
    corpus = None
    if req.corpus_id is not None:
        rec = _record(req.corpus_id)
        if rec.status != "ready" or rec.corpus is None:
            raise HTTPException(409, f"Corpus {req.corpus_id!r} is {rec.status}.")
        corpus = rec.corpus
    embedder = None
    if req.embed_url:
        try:
            embedder = _callback_embedder(req.embed_url, req.pipeline.embedding_model, req.embed_headers)
        except EmbedCallbackError as e:
            raise HTTPException(422 if "localhost" in str(e) else 502, str(e)) from e
    try:
        return {"api_version": API_VERSION, **check_external(req, corpus, embedder)}
    except EmbedCallbackError as e:
        raise HTTPException(502, str(e)) from e
    except GeneratorCallbackError as e:
        raise HTTPException(422, str(e)) from e


@router.post("/check", dependencies=[Depends(require_api_key)])
@v1.post("/check", dependencies=[Depends(require_api_key)])
def check(req: ExternalCheckRequest) -> dict[str, Any]:
    """Check an external RAG pipeline's run: send the question, the ranked candidates,
    which went into the prompt, and the answer. See live/external.py and
    docs/integration.md. `summary.needs_review` is the one field most callers need."""
    return _check_one(req)


class BatchRequest(BaseModel):
    items: list[ExternalCheckRequest] = Field(..., min_length=1, max_length=MAX_BATCH)


@router.post("/check/batch", dependencies=[Depends(require_api_key)])
@v1.post("/check/batch", dependencies=[Depends(require_api_key)])
def check_batch(req: BatchRequest) -> dict[str, Any]:
    """Several checks in one call, in order. One item's failure doesn't fail the batch:
    it comes back as {"error": {"status", "detail"}} in its place."""
    results: list[dict[str, Any]] = []
    for item in req.items:
        try:
            results.append(_check_one(item))
        except HTTPException as e:
            results.append({"error": {"status": e.status_code, "detail": e.detail}})
    return {
        "api_version": API_VERSION,
        "results": results,
        "needs_review": sum(1 for r in results if r.get("summary", {}).get("needs_review")),
        "retrieval_needs_review": sum(1 for r in results if r.get("summary", {}).get("retrieval_needs_review")),
        "errors": sum(1 for r in results if "error" in r),
    }


@router.get("/runs/{run_id}")
def get_run(run_id: str) -> dict[str, Any]:
    run = runs.get(run_id)
    if run is None:
        raise HTTPException(404, f"No run {run_id!r}.")
    return run


__all__ = ["router", "v1", "LiveEventType"]
