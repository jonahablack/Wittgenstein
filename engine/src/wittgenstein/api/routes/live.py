"""Live self-aware pipeline API (docs/live-pipeline-plan.md §7).

- GET  /live/config                         presets, providers available here, embedders
- GET  /live/corpora                        loaded corpora and their warm-up status
- POST /live/corpora                        upload .txt / .md / .pdf files as a new corpus
- GET  /live/corpora/{id}                   one corpus
- GET  /live/corpora/{id}/documents/{doc}   full document text, for "Show me"
- POST /live/runs                           run a question; streams Server-Sent Events
- GET  /live/runs/{run_id}                  a stored run (events + outcomes), for replay
"""

from __future__ import annotations

import asyncio
import json
import threading
from collections.abc import AsyncIterator
from typing import Any

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, Field
from sse_starlette.sse import EventSourceResponse

from wittgenstein.core.enums import LiveEventType
from wittgenstein.live.embedding import DEFAULT_EMBEDDER, EMBEDDER_CHOICES
from wittgenstein.live.events import LiveEvent
from wittgenstein.live.generate import PROVIDER_CHOICES, available_providers
from wittgenstein.live.pipelines import DEFAULT_PIPELINE, PRESETS
from wittgenstein.live.runner import run_query
from wittgenstein.live.store import corpora, extract_text, runs, slug

router = APIRouter(prefix="/live", tags=["live"])

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


@router.get("/runs/{run_id}")
def get_run(run_id: str) -> dict[str, Any]:
    run = runs.get(run_id)
    if run is None:
        raise HTTPException(404, f"No run {run_id!r}.")
    return run


__all__ = ["router", "LiveEventType"]
