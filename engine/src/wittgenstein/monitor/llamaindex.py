"""LlamaIndex hook: an event handler on the root instrumentation dispatcher. Every query
engine reports its retrievals and its final response; the response's source nodes are
what went into the prompt."""

from __future__ import annotations

import threading
import time
from typing import Any

from llama_index.core.instrumentation import get_dispatcher
from llama_index.core.instrumentation.event_handlers import BaseEventHandler
from llama_index.core.instrumentation.events.query import QueryEndEvent
from llama_index.core.instrumentation.events.retrieval import RetrievalEndEvent

from ._client import record

_RECENT_SECONDS = 300


class WittgensteinEventHandler(BaseEventHandler):
    @classmethod
    def class_name(cls) -> str:
        return "WittgensteinEventHandler"

    def handle(self, event: Any, **kwargs: Any) -> None:
        if isinstance(event, RetrievalEndEvent):
            with _lock:
                _recent.append((time.time(), list(event.nodes or [])))
                del _recent[:-20]
        elif isinstance(event, QueryEndEvent):
            _on_query_end(event)


_lock = threading.Lock()
_recent: list[tuple[float, list[Any]]] = []


def _on_query_end(event: QueryEndEvent) -> None:
    resp = event.response
    sources = list(getattr(resp, "source_nodes", None) or [])
    if not sources:
        return
    q = event.query
    question = q if isinstance(q, str) else getattr(q, "query_str", str(q))
    ids = {getattr(n.node, "node_id", None) for n in sources}
    retrieved = sources
    now = time.time()
    with _lock:
        for t, nodes in reversed(_recent):
            # The retrieval this response drew from: it contains the response's sources.
            if now - t < _RECENT_SECONDS and ids & {getattr(n.node, "node_id", None) for n in nodes}:
                retrieved = nodes
                break
    record(question, retrieved, str(resp), context=sources, pipeline={"name": "llamaindex"})


_INSTALLED = False


def install() -> None:
    global _INSTALLED
    if not _INSTALLED:
        get_dispatcher().add_event_handler(WittgensteinEventHandler())
        _INSTALLED = True


__all__ = ["WittgensteinEventHandler", "install"]
