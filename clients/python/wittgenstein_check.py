"""Minimal client for Wittgenstein's external-pipeline check (POST /v1/check).

Standard library only, so it drops into any RAG codebase. Call `check(...)` after your
pipeline has retrieved, chosen the context, and answered:

    from wittgenstein_check import check

    report = check(
        "http://127.0.0.1:8100",
        query=question,
        candidates=[{"id": d.id, "text": d.text, "score": d.score} for d in retrieved],
        context_ids=[d.id for d in in_prompt],          # answer citations [n] refer to this order
        answer=answer_text,                              # optional
        pipeline={"retriever": "dense", "embedding_model": "your-model"},
        corpus_id="your-uploaded-document",              # optional: enables document-wide checks
        embed_url="http://localhost:9000/embed",         # optional: probes your own model
        generator_url="http://localhost:9000/generate",  # optional: tests if your LLM reads its context
        api_key="...",                                   # if the server requires one
    )
    if report["summary"]["needs_review"]:
        for s in report["summary"]["sentences"]:
            if s["status"] == "review":
                print(s["text"], [f["title"] for f in s["flags"]])

Many runs at once (e.g. replaying logs): `check_batch(base_url, [request(...), ...])`.
See engine/docs/integration.md for the request/response format and access levels.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any


class WittgensteinError(RuntimeError):
    pass


def _post(base_url: str, path: str, body: dict[str, Any], api_key: str | None, timeout: float) -> dict[str, Any]:
    headers = {"content-type": "application/json"}
    if api_key:
        headers["authorization"] = f"Bearer {api_key}"
    req = urllib.request.Request(
        base_url.rstrip("/") + path, data=json.dumps(body).encode(), headers=headers, method="POST"
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        detail = e.read().decode(errors="replace")
        raise WittgensteinError(f"{e.code}: {detail}") from e


def request(
    *,
    query: str,
    candidates: list[dict[str, Any]],
    context_ids: list[str] | None = None,
    answer: str | None = None,
    pipeline: dict[str, Any] | None = None,
    corpus_id: str | None = None,
    embed_url: str | None = None,
    embed_headers: dict[str, str] | None = None,
    generator_url: str | None = None,
    generator_headers: dict[str, str] | None = None,
) -> dict[str, Any]:
    """One check request body (also what `check_batch` takes a list of)."""
    body: dict[str, Any] = {"query": query, "candidates": candidates, "pipeline": pipeline or {}}
    for key, value in (
        ("context_ids", context_ids),
        ("answer", answer),
        ("corpus_id", corpus_id),
        ("embed_url", embed_url),
        ("embed_headers", embed_headers),
        ("generator_url", generator_url),
        ("generator_headers", generator_headers),
    ):
        if value is not None:
            body[key] = value
    return body


def check(base_url: str, *, api_key: str | None = None, timeout: float = 120.0, **fields: Any) -> dict[str, Any]:
    """Check one run. Keyword fields are those of `request` (query, candidates, ...)."""
    return _post(base_url, "/v1/check", request(**fields), api_key, timeout)


def check_batch(
    base_url: str, items: list[dict[str, Any]], *, api_key: str | None = None, timeout: float = 600.0
) -> dict[str, Any]:
    """Up to 50 requests in one call. A failed item comes back as
    {"error": {"status", "detail"}} in its place; the others are unaffected."""
    return _post(base_url, "/v1/check/batch", {"items": items}, api_key, timeout)


def needs_review(report: dict[str, Any]) -> list[dict[str, Any]]:
    """The flags a person should look at, most severe first."""
    order = {"warning": 0, "caution": 1, "info": 2}
    flags = [f for f in report.get("flags", []) if f.get("disposition") == "needs_review"]
    return sorted(flags, key=lambda f: order.get(f.get("severity"), 3))
