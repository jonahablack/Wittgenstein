"""LangChain hook: a callback handler registered with LangChain's configure hook, so
every chain, retriever and model call in the process reports to it.

Pairing: a model call is audited when its prompt contains text of passages retrieved
in the same trace (same root run), or, for pipelines that call the retriever and the
model separately, by the most recent retrieval whose passages appear in the prompt.
Model calls with no retrieved passage in their prompt (e.g. question rewriting) are
skipped.
"""

from __future__ import annotations

import threading
import time
from collections import OrderedDict
from contextvars import ContextVar
from typing import Any
from uuid import UUID

from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.tracers.context import register_configure_hook

from ._client import context_order, record

_MAX_TRACES = 256
_RECENT_SECONDS = 300


class WittgensteinHandler(BaseCallbackHandler):
    raise_error = False

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._parent: OrderedDict[UUID, UUID | None] = OrderedDict()
        self._traces: OrderedDict[UUID, dict[str, Any]] = OrderedDict()
        self._prompts: dict[UUID, str] = {}
        self._recent: list[tuple[float, str, list[Any]]] = []  # (time, query, docs)

    # -- bookkeeping ---------------------------------------------------------
    def _link(self, run_id: UUID, parent_run_id: UUID | None) -> None:
        with self._lock:
            self._parent[run_id] = parent_run_id
            while len(self._parent) > _MAX_TRACES * 16:
                self._parent.popitem(last=False)

    def _root(self, run_id: UUID) -> UUID:
        seen = 0
        while seen < 64:
            p = self._parent.get(run_id)
            if p is None:
                return run_id
            run_id, seen = p, seen + 1
        return run_id

    def _trace(self, run_id: UUID) -> dict[str, Any]:
        root = self._root(run_id)
        t = self._traces.get(root)
        if t is None:
            t = self._traces[root] = {"question": None, "query": None, "docs": []}
            while len(self._traces) > _MAX_TRACES:
                self._traces.popitem(last=False)
        return t

    # -- events --------------------------------------------------------------
    def on_chain_start(
        self, serialized: Any, inputs: Any, *, run_id: UUID, parent_run_id: UUID | None = None, **kw: Any
    ) -> None:  # noqa: E501
        self._link(run_id, parent_run_id)
        if parent_run_id is None:
            with self._lock:
                self._trace(run_id)["question"] = _question(inputs)

    def on_retriever_start(
        self, serialized: Any, query: str, *, run_id: UUID, parent_run_id: UUID | None = None, **kw: Any
    ) -> None:  # noqa: E501
        self._link(run_id, parent_run_id)
        with self._lock:
            t = self._trace(run_id)
            t["query"] = t["query"] or query
            t.setdefault("pending", {})[run_id] = query

    def on_retriever_end(
        self, documents: Any, *, run_id: UUID, parent_run_id: UUID | None = None, **kw: Any
    ) -> None:  # noqa: E501
        with self._lock:
            t = self._trace(run_id)
            docs = list(documents)
            t["docs"].extend(docs)
            query = t.get("pending", {}).pop(run_id, t["query"] or "")
            now = time.time()
            self._recent = [r for r in self._recent if now - r[0] < _RECENT_SECONDS][-20:]
            self._recent.append((now, query, docs))

    def on_llm_start(
        self, serialized: Any, prompts: list[str], *, run_id: UUID, parent_run_id: UUID | None = None, **kw: Any
    ) -> None:  # noqa: E501
        self._link(run_id, parent_run_id)
        self._prompts[run_id] = "\n".join(prompts)

    def on_chat_model_start(
        self,
        serialized: Any,
        messages: list[list[Any]],
        *,
        run_id: UUID,
        parent_run_id: UUID | None = None,
        **kw: Any,
    ) -> None:  # noqa: E501
        self._link(run_id, parent_run_id)
        parts = []
        for batch in messages:
            for m in batch:
                c = getattr(m, "content", m)
                parts.append(c if isinstance(c, str) else " ".join(_text_blocks(c)))
        self._prompts[run_id] = "\n".join(parts)

    def on_llm_end(self, response: Any, *, run_id: UUID, parent_run_id: UUID | None = None, **kw: Any) -> None:
        prompt = self._prompts.pop(run_id, "")
        answer = _answer(response)
        if not prompt or answer is None:
            return
        with self._lock:
            t = self._trace(run_id)
            docs = list(t["docs"])
            question = t["question"] or t["query"]
            texts = [getattr(d, "page_content", "") for d in docs]
            if not docs or not context_order(texts, prompt):
                # Retriever and model called separately: the latest retrieval in the prompt.
                for _, q, ds in reversed(self._recent):
                    if context_order([getattr(d, "page_content", "") for d in ds], prompt):
                        docs, question = ds, question or q
                        break
                else:
                    return
        if not question:
            return
        record(question, docs, answer, prompt=prompt, source=None, pipeline={"name": "langchain"})


def _question(inputs: Any) -> str | None:
    if isinstance(inputs, str):
        return inputs
    if isinstance(inputs, dict):
        for k in ("question", "input", "query", "q"):
            v = inputs.get(k)
            if isinstance(v, str):
                return v
        strs = [v for v in inputs.values() if isinstance(v, str)]
        if len(strs) == 1:
            return strs[0]
    return None


def _text_blocks(content: Any) -> list[str]:
    if isinstance(content, list):
        return [b.get("text", "") if isinstance(b, dict) else str(b) for b in content]
    return [str(content)]


def _answer(response: Any) -> str | None:
    try:
        g = response.generations[0][0]
    except (AttributeError, IndexError):
        return None
    msg = getattr(g, "message", None)
    if msg is not None:
        c = msg.content
        return c if isinstance(c, str) else " ".join(_text_blocks(c))
    return getattr(g, "text", None)


_HANDLER: WittgensteinHandler | None = None
#: Default set to the handler, so every thread and task sees it without setup.
_VAR: ContextVar[WittgensteinHandler | None] | None = None


def install() -> WittgensteinHandler:
    global _HANDLER, _VAR
    if _HANDLER is None:
        _HANDLER = WittgensteinHandler()
        _VAR = ContextVar("wittgenstein_monitor", default=_HANDLER)
        register_configure_hook(_VAR, inheritable=True)
    return _HANDLER


__all__ = ["WittgensteinHandler", "install"]
