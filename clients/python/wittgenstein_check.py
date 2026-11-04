"""Minimal client for Wittgenstein's external-pipeline check (POST /live/check).

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
    )
    for flag in report["flags"]:
        if flag["disposition"] == "needs_review":
            print(flag["title"], "-", flag["observation"])

See engine/docs/integration.md for the request/response format and access levels.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any


class WittgensteinError(RuntimeError):
    pass


def check(
    base_url: str,
    *,
    query: str,
    candidates: list[dict[str, Any]],
    context_ids: list[str] | None = None,
    answer: str | None = None,
    pipeline: dict[str, Any] | None = None,
    corpus_id: str | None = None,
    embed_url: str | None = None,
    embed_headers: dict[str, str] | None = None,
    timeout: float = 120.0,
) -> dict[str, Any]:
    body: dict[str, Any] = {"query": query, "candidates": candidates, "pipeline": pipeline or {}}
    for key, value in (
        ("context_ids", context_ids),
        ("answer", answer),
        ("corpus_id", corpus_id),
        ("embed_url", embed_url),
        ("embed_headers", embed_headers),
    ):
        if value is not None:
            body[key] = value
    req = urllib.request.Request(
        base_url.rstrip("/") + "/live/check",
        data=json.dumps(body).encode(),
        headers={"content-type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        detail = e.read().decode(errors="replace")
        raise WittgensteinError(f"{e.code}: {detail}") from e


def needs_review(report: dict[str, Any]) -> list[dict[str, Any]]:
    """The flags a person should look at, most severe first."""
    order = {"warning": 0, "caution": 1, "info": 2}
    flags = [f for f in report.get("flags", []) if f.get("disposition") == "needs_review"]
    return sorted(flags, key=lambda f: order.get(f.get("severity"), 3))
