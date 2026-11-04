"""Answer providers (docs/live-pipeline-plan.md §§3, 11).

`AnswerProvider` is the single interface every generator implements: given the
question and the packed evidence, stream answer text that cites evidence as [n].
Providers:

- `extractive` (default, offline, deterministic): no language model. It quotes the
  evidence sentences that best cover each part of the question. Labeled as such in the
  UI; it can never state anything the document doesn't.
- `claude` and `openai` (optional extras): live LLM answers, in their own modules
  (live/providers/), imported lazily so the base install never needs either SDK.

Reserved for later (plan §11): an optional attribution channel from an open-weights
model, mapping answer spans to context spans with weights.
"""

from __future__ import annotations

import os
import re
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Protocol

import numpy as np

from wittgenstein.live import phrases as P
from wittgenstein.live.corpus import Unit
from wittgenstein.live.coverage import Instruments


@dataclass(frozen=True)
class ProviderInfo:
    provider_id: str
    label: str
    model_identifier: str | None
    uses_llm: bool


@dataclass(frozen=True)
class ContextPassage:
    n: int
    unit: Unit


class ProviderError(RuntimeError):
    """A provider failure, with a message safe to show the user."""


class AnswerProvider(Protocol):
    info: ProviderInfo

    def stream(self, question: str, passages: list[ContextPassage]) -> Iterator[str]: ...


SYSTEM_PROMPT = (
    "You answer questions using only the numbered passages provided. After every sentence, cite the passage "
    "numbers it relies on in square brackets, like [2] or [1, 3]. Keep conditions, exceptions and hedges from "
    "the passages (for example 'provided that', 'unless', 'may') in your sentences rather than simplifying them "
    "away. If the passages do not contain the answer, or only part of it, say so plainly instead of filling "
    "the gap. Be concise."
)


def format_passages(passages: list[ContextPassage]) -> str:
    blocks = []
    for p in passages:
        head = f" ({p.unit.heading_context.splitlines()[-1]})" if p.unit.heading_context else ""
        blocks.append(f"[{p.n}]{head}\n{p.unit.text}")
    return "\n\n".join(blocks)


def user_prompt(question: str, passages: list[ContextPassage]) -> str:
    return f"Passages:\n\n{format_passages(passages)}\n\nQuestion: {question}"


class ExtractiveProvider:
    """Quotes, per question part, the evidence sentence that best covers it (whole-word
    term coverage first, then similarity), then fills up to MAX_SENTENCES with the most
    similar remaining sentences. Deterministic."""

    MAX_SENTENCES = 4
    info = ProviderInfo("extractive", "Quoted from the document (no language model)", None, False)

    def __init__(self, inst: Instruments) -> None:
        self._inst = inst

    def stream(self, question: str, passages: list[ContextPassage]) -> Iterator[str]:
        inst = self._inst
        if not passages:
            yield "The document doesn't appear to contain passages relevant to this question."
            return
        seen: set[str] = set()
        sents: list[tuple[int, str]] = []
        for p in passages:
            for s, _, _ in p.unit.sentences:
                s = _DANGLING_ENUM.sub("", s).strip()
                key = " ".join(s.lower().split())
                if len(s) > 20 and key not in seen:
                    seen.add(key)
                    sents.append((p.n, s))
        if not sents:
            sents = [(p.n, p.unit.text) for p in passages]
        sims = np.zeros(len(sents))
        if inst.embedder is not None and inst.query_vector is not None:
            sims = inst.embedder.embed([s for _, s in sents]) @ inst.query_vector
        chosen: list[int] = []
        for f in inst.analysis.facets:
            terms = list(dict.fromkeys(f.terms))
            scored = [
                (sum(P.contains_phrase(P.lower(s), t) for t in terms) / max(1, len(terms)), float(sims[i]), i)
                for i, (_, s) in enumerate(sents)
                if i not in chosen
            ]
            if scored:
                share, _, i = max(scored)
                if share >= 0.5:
                    chosen.append(i)
        for i in np.argsort(-sims, kind="stable"):
            if len(chosen) >= self.MAX_SENTENCES:
                break
            if int(i) not in chosen:
                chosen.append(int(i))
        chosen = chosen[: self.MAX_SENTENCES]
        # Present in document order so quotations read naturally.
        order = {p.n: k for k, p in enumerate(passages)}
        chosen.sort(key=lambda i: (order[sents[i][0]], i))
        for k, i in enumerate(chosen):
            n, s = sents[i]
            text = s.rstrip()
            yield ("" if k == 0 else " ") + f"{text} [{n}]"


_DANGLING_ENUM = re.compile(r"\s+(?:\d{1,3}|[a-z]|[ivx]{1,4})[.)]$")

PROVIDER_CHOICES = ["extractive", "claude", "openai"]


def available_providers() -> dict[str, bool]:
    """Which providers can run here. LLM providers need their SDK and a credential;
    nothing is assumed configured."""
    out = {"extractive": True}
    try:
        import anthropic  # noqa: F401

        out["claude"] = bool(os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN"))
    except ImportError:
        out["claude"] = False
    try:
        import openai  # noqa: F401

        out["openai"] = bool(os.environ.get("OPENAI_API_KEY"))
    except ImportError:
        out["openai"] = False
    return out


def get_provider(name: str, inst: Instruments) -> AnswerProvider:
    if name == "extractive":
        return ExtractiveProvider(inst)
    if name == "claude":
        from wittgenstein.live.providers.anthropic_provider import ClaudeProvider

        return ClaudeProvider()
    if name == "openai":
        from wittgenstein.live.providers.openai_provider import OpenAIProvider

        return OpenAIProvider()
    raise ValueError(f"Unknown provider {name!r}; choose one of {PROVIDER_CHOICES}")
