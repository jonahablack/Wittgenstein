"""The local audit feed: checks of a user's own RAG pipeline, kept for the local UI.

When Wittgenstein runs on a laptop (`wittgenstein serve`) and the user's pipeline is
instrumented (wittgenstein.monitor), every answer the pipeline produces is checked and
recorded here, so the "Your pipeline" view can show it as it happens.

Kept in memory (the most recent MAX_AUDITS) and, if a directory is configured
(WITTGENSTEIN_AUDIT_DIR, set by `wittgenstein serve` to ~/.wittgenstein), appended to
audits.jsonl there, so the feed survives a restart. Nothing leaves the machine.
"""

from __future__ import annotations

import json
import os
import threading
import uuid
from collections import deque
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

MAX_AUDITS = 500


class AuditLog:
    def __init__(self, directory: Path | None = None) -> None:
        self._lock = threading.Lock()
        self._items: deque[dict[str, Any]] = deque(maxlen=MAX_AUDITS)
        self._file: Path | None = None
        if directory is not None:
            directory.mkdir(parents=True, exist_ok=True)
            self._file = directory / "audits.jsonl"
            self._load()

    def _load(self) -> None:
        assert self._file is not None
        if not self._file.exists():
            return
        for line in self._file.read_text().splitlines()[-MAX_AUDITS:]:
            try:
                self._items.append(json.loads(line))
            except json.JSONDecodeError:
                continue

    def add(self, request: dict[str, Any], report: dict[str, Any], source: str | None) -> dict[str, Any]:
        item = {
            "audit_id": uuid.uuid4().hex[:12],
            "created": datetime.now(UTC).isoformat(timespec="seconds"),
            "source": source,
            "request": request,
            "report": report,
        }
        with self._lock:
            self._items.append(item)
            if self._file is not None:
                with self._file.open("a") as fh:
                    fh.write(json.dumps(item) + "\n")
        return item

    def list(self) -> list[dict[str, Any]]:
        with self._lock:
            items = list(self._items)
        return [_brief(i) for i in reversed(items)]

    def get(self, audit_id: str) -> dict[str, Any] | None:
        with self._lock:
            return next((i for i in self._items if i["audit_id"] == audit_id), None)

    def clear(self) -> None:
        with self._lock:
            self._items.clear()
            if self._file is not None and self._file.exists():
                self._file.unlink()


def _brief(item: dict[str, Any]) -> dict[str, Any]:
    summary = item["report"].get("summary", {})
    req = item["request"]
    return {
        "audit_id": item["audit_id"],
        "created": item["created"],
        "source": item["source"],
        "query": req.get("query"),
        "answer": (req.get("answer") or "")[:300],
        "needs_review": summary.get("needs_review"),
        "retrieval_needs_review": summary.get("retrieval_needs_review"),
        "worst_severity": summary.get("worst_severity"),
        "answer_flags": summary.get("answer_flags", 0),
        "context_flags": summary.get("context_flags", 0),
        "retrieval_flags": summary.get("retrieval_flags", 0),
        "candidates": len(req.get("candidates", [])),
        "in_prompt": len(req.get("context_ids") or req.get("candidates", [])),
    }


_LOG: AuditLog | None = None


def audit_log() -> AuditLog:
    global _LOG
    if _LOG is None:
        d = os.environ.get("WITTGENSTEIN_AUDIT_DIR")
        _LOG = AuditLog(Path(d).expanduser() if d else None)
    return _LOG


__all__ = ["AuditLog", "audit_log", "MAX_AUDITS"]
