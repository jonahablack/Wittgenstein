"""Attach Wittgenstein to an existing RAG pipeline, as a third layer beside retrieval and
generation.

    import wittgenstein.monitor as wm
    wm.instrument()          # detects LangChain / LlamaIndex and hooks them

Every answer the pipeline produces is then sent, with what was retrieved and what went
into the prompt, to a Wittgenstein server (by default the local one started with
`wittgenstein serve`) and appears in its "Your pipeline" view with the same checks the
site runs.

How it adapts to the pipeline without configuration:
- **LangChain**: a callback handler is registered globally (LangChain's own configure
  hook), so every chain, retriever and model call reports to it without code changes.
- **LlamaIndex**: an event handler on the root instrumentation dispatcher sees every
  retrieval and query.
- **What went into the prompt** is read from the prompt itself: the retrieved passages
  whose text appears in it, in the order they appear. So a custom prompt template,
  reranker or context filter is handled as it is.
- **Anything else**: call `record(question, retrieved, answer)` after each answer.

It never slows or breaks the pipeline: reports are sent from a background thread, and a
failure to reach the server is logged once, never raised.

Settings (environment or `configure`): WITTGENSTEIN_URL (default
http://127.0.0.1:8100), WITTGENSTEIN_API_KEY, WITTGENSTEIN_SOURCE (a name for this
pipeline in the feed).
"""

from __future__ import annotations

from wittgenstein.monitor._client import configure, flush, record

__all__ = ["instrument", "record", "configure", "flush"]


def instrument(*, langchain: bool = True, llamaindex: bool = True) -> list[str]:
    """Hook every supported framework that is installed. Returns the names hooked."""
    hooked: list[str] = []
    if langchain:
        try:
            from wittgenstein.monitor import langchain as lc

            lc.install()
            hooked.append("langchain")
        except ImportError:
            pass
    if llamaindex:
        try:
            from wittgenstein.monitor import llamaindex as li

            li.install()
            hooked.append("llamaindex")
        except ImportError:
            pass
    return hooked
