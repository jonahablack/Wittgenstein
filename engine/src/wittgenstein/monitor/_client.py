"""Background reporting to a Wittgenstein server (standard library only)."""

from __future__ import annotations

import json
import logging
import os
import queue
import re
import threading
import urllib.error
import urllib.request
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

log = logging.getLogger("wittgenstein.monitor")

MAX_CANDIDATES = 500
MAX_TEXT = 20_000
MAX_QUERY = 2000


@dataclass
class _Settings:
    url: str = field(default_factory=lambda: os.environ.get("WITTGENSTEIN_URL", "http://127.0.0.1:8100"))
    api_key: str | None = field(default_factory=lambda: os.environ.get("WITTGENSTEIN_API_KEY"))
    source: str | None = field(default_factory=lambda: os.environ.get("WITTGENSTEIN_SOURCE"))
    timeout: float = 120.0


_settings = _Settings()
_queue: queue.Queue[dict[str, Any] | None] = queue.Queue(maxsize=1000)
_worker: threading.Thread | None = None
_worker_lock = threading.Lock()
_warned = False
#: The last report the server returned (for scripts and tests).
last_report: dict[str, Any] | None = None


def configure(url: str | None = None, api_key: str | None = None, source: str | None = None) -> None:
    if url is not None:
        _settings.url = url
    if api_key is not None:
        _settings.api_key = api_key
    if source is not None:
        _settings.source = source


def _post(body: dict[str, Any]) -> dict[str, Any]:
    headers = {"content-type": "application/json"}
    if _settings.api_key:
        headers["authorization"] = f"Bearer {_settings.api_key}"
    req = urllib.request.Request(
        _settings.url.rstrip("/") + "/v1/audits", data=json.dumps(body).encode(), headers=headers, method="POST"
    )
    with urllib.request.urlopen(req, timeout=_settings.timeout) as r:
        return json.loads(r.read())


def _run() -> None:
    global _warned, last_report
    while True:
        body = _queue.get()
        try:
            if body is None:
                return
            last_report = _post(body)
            _warned = False
        except Exception as e:  # noqa: BLE001 -- reporting must never break the caller's pipeline
            detail = e.read().decode(errors="replace")[:300] if isinstance(e, urllib.error.HTTPError) else str(e)
            if not _warned:
                log.warning("Wittgenstein: couldn't send an audit to %s (%s)", _settings.url, detail)
                _warned = True
        finally:
            _queue.task_done()


def _ensure_worker() -> None:
    global _worker
    with _worker_lock:
        if _worker is None or not _worker.is_alive():
            _worker = threading.Thread(target=_run, name="wittgenstein-monitor", daemon=True)
            _worker.start()


def flush(timeout: float | None = None) -> bool:
    """Wait until queued audits are sent. True if the queue drained."""
    done = threading.Event()

    def wait() -> None:
        _queue.join()
        done.set()

    threading.Thread(target=wait, daemon=True).start()
    return done.wait(timeout)


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().lower()


def context_order(texts: Sequence[str], prompt: str) -> list[int]:
    """Indices of the passages that appear in the prompt, in prompt order. A passage
    counts if its text (whitespace-normalized) is in the prompt, or, for long passages a
    template may trim, its first 200 characters are."""
    p = _norm(prompt)
    found: list[tuple[int, int]] = []
    for i, t in enumerate(texts):
        n = _norm(t)
        if not n:
            continue
        pos = p.find(n)
        if pos < 0 and len(n) > 200:
            pos = p.find(n[:200])
        if pos >= 0:
            found.append((pos, i))
    return [i for _, i in sorted(found)]


def record(
    question: str,
    retrieved: Sequence[Any],
    answer: str | None = None,
    *,
    context: Sequence[Any] | None = None,
    prompt: str | None = None,
    pipeline: dict[str, Any] | None = None,
    source: str | None = None,
) -> None:
    """Report one run of the pipeline. Returns at once; the check runs on the server.

    retrieved: what the retriever returned, best first. Each item may be a string, a
      dict with "text" (and optionally "id", "score"), a LangChain Document, or a
      LlamaIndex node / NodeWithScore.
    context: the items that went into the prompt, in prompt order (default: inferred
      from `prompt` if given, else all of `retrieved`).
    """
    cands = _candidates(retrieved)
    if not cands or not question or len(question.strip()) < 2:
        return
    ctx_ids: list[str] | None = None
    if context is not None:
        by_text = {c["text"]: c["id"] for c in cands}
        ctx_ids = []
        for c in _candidates(context):
            cid = by_text.get(c["text"])
            if cid is None:  # in the prompt but not among the retrieved: add it
                c["id"] = f"ctx-{len(cands)}"
                cands.append(c)
                cid = c["id"]
            ctx_ids.append(cid)
    elif prompt:
        order = context_order([c["text"] for c in cands], prompt)
        ctx_ids = [cands[i]["id"] for i in order] or None
    body: dict[str, Any] = {
        "query": question.strip()[:MAX_QUERY],
        "candidates": cands[:MAX_CANDIDATES],
        "pipeline": pipeline or {},
        "source": source or _settings.source,
    }
    if ctx_ids:
        body["context_ids"] = [i for i in ctx_ids if any(c["id"] == i for c in body["candidates"])]
    if answer:
        body["answer"] = answer[:20_000]
    try:
        _queue.put_nowait(body)
    except queue.Full:
        log.warning("Wittgenstein: audit queue full; dropping one audit")
        return
    _ensure_worker()


def _candidates(items: Sequence[Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for i, item in enumerate(items):
        text, cid, score = _unpack(item)
        if not text or not text.strip():
            continue
        cid = (cid or f"p{i + 1}")[:200]
        if cid in seen:
            cid = f"{cid}#{i + 1}"
        seen.add(cid)
        c: dict[str, Any] = {"id": cid, "text": text[:MAX_TEXT]}
        if isinstance(score, int | float):
            c["score"] = float(score)
        out.append(c)
    return out


def _unpack(item: Any) -> tuple[str, str | None, Any]:
    if isinstance(item, str):
        return item, None, None
    if isinstance(item, dict):
        return str(item.get("text") or item.get("page_content") or ""), _str(item.get("id")), item.get("score")
    # LlamaIndex NodeWithScore -> node
    node = getattr(item, "node", None)
    if node is not None and hasattr(node, "get_content"):
        return node.get_content(), _str(getattr(node, "node_id", None)), getattr(item, "score", None)
    if hasattr(item, "get_content"):  # LlamaIndex node
        return item.get_content(), _str(getattr(item, "node_id", None)), None
    if hasattr(item, "page_content"):  # LangChain Document
        meta = getattr(item, "metadata", {}) or {}
        cid = getattr(item, "id", None) or meta.get("id")
        if cid is None and meta.get("source") is not None:
            cid = f"{meta['source']}:{meta.get('page', meta.get('start_index', ''))}".rstrip(":")
        return item.page_content, _str(cid), meta.get("score")
    return str(item), None, None


def _str(x: Any) -> str | None:
    return None if x is None else str(x)
