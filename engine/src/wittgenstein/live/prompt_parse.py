"""Read a RAG request off the wire: the question and the retrieved passages inside an
ordinary chat request, for the model proxy (live/proxy.py).

A RAG app sends its passages to the model inside the prompt. Common shapes, all
handled:
- numbered: "[1] ...", "1. ...", "Source 1: ...", "Document 2: ...", "Passage 3 ...";
- tagged: <document>...</document>, <doc>...</doc>, <source>...</source>;
- a "Context:" section followed by the question, split into paragraphs.

The question is the last user message, or, when the context is in that message too,
the text after "Question:" (or the last sentence ending in "?"). Requests where no
passages can be found are passed through without an audit: guessing would produce
audits of things that aren't RAG answers.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

_NUMBERED = re.compile(
    r"(?im)^[ \t]*(?:\[(\d{1,3})\]|(?:source|document|doc|passage|chunk|context)\s*#?\s*(\d{1,3})\s*[:.)\]-]|"
    r"(\d{1,3})[.)])[ \t]+"
)
_TAGGED = re.compile(r"(?is)<(document|doc|source|passage|chunk)\b[^>]*>(.*?)</\1>")
_CONTEXT_HEAD = re.compile(
    r"(?im)^[ \t]*(?:context|sources|documents|passages|retrieved (?:context|passages))\s*:?\s*$"
    r"|^[ \t]*(?:context|sources)\s*:\s*"
)
_QUESTION = re.compile(
    r"(?is)(?:^|\n)[ \t]*(?:question|query|q|user question)\s*:\s*(.+?)\s*(?:\n\s*(?:answer|a)\s*:.*)?$"
)
_MIN_WORDS = 5


@dataclass
class ParsedRequest:
    question: str
    passages: list[str]
    prompt: str


def text_of(content: Any) -> str:
    """Message content as text: a string, or a list of content blocks."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for b in content:
            if isinstance(b, dict) and b.get("type") in {"text", "input_text"}:
                parts.append(str(b.get("text", "")))
            elif isinstance(b, str):
                parts.append(b)
        return "\n".join(parts)
    return ""


def parse(messages: list[dict[str, Any]], system: Any = None) -> ParsedRequest | None:
    sys_text = text_of(system) if system is not None else ""
    texts = [(m.get("role"), text_of(m.get("content"))) for m in messages if isinstance(m, dict)]
    sys_text = "\n\n".join([sys_text] + [t for r, t in texts if r in {"system", "developer"}]).strip()
    users = [t for r, t in texts if r == "user" and t.strip()]
    if not users:
        return None
    last = users[-1]
    prompt = "\n\n".join([sys_text] + [t for r, t in texts if r not in {"system", "developer"}])
    passages = _passages(last) or _passages(sys_text)
    if not passages:
        return None
    question = _question(last, passages)
    if not question or len(question) < 2:
        return None
    return ParsedRequest(question=question[:2000], passages=passages, prompt=prompt)


def _passages(text: str) -> list[str]:
    if not text:
        return []
    tagged = [re.sub(r"\s+", " ", m.group(2)).strip() for m in _TAGGED.finditer(text)]
    tagged = [t for t in tagged if len(t.split()) >= _MIN_WORDS]
    if tagged:
        return tagged
    marks = list(_NUMBERED.finditer(text))
    if len(marks) >= 1:
        out = []
        for i, m in enumerate(marks):
            end = marks[i + 1].start() if i + 1 < len(marks) else len(text)
            body = text[m.end() : end]
            body = _cut_tail(body) if i + 1 == len(marks) else body
            body = re.sub(r"\s+", " ", body).strip()
            if len(body.split()) >= _MIN_WORDS:
                out.append(body)
        # A numbered list of one short item is more likely an instruction than a passage.
        if out and (len(out) >= 2 or len(out[0].split()) >= 12):
            return out
    head = _CONTEXT_HEAD.search(text)
    if head:
        body = _cut_tail(text[head.end() :])
        paras = [re.sub(r"\s+", " ", p).strip() for p in re.split(r"\n\s*\n", body)]
        paras = [p for p in paras if len(p.split()) >= _MIN_WORDS]
        while paras and paras[-1].rstrip().endswith("?"):
            paras.pop()  # the question after the context, not a passage
        if paras:
            return paras
    return []


def _cut_tail(body: str) -> str:
    """End the last passage where the question or instructions begin."""
    m = re.search(r"(?im)^[ \t]*(?:question|query|q|user question|answer|instructions?)\s*:", body)
    return body[: m.start()] if m else body


def _question(last: str, passages: list[str]) -> str:
    m = _QUESTION.search(last)
    if m:
        return re.sub(r"\s+", " ", m.group(1)).strip()
    stripped = last
    for p in passages:  # what's left after the passages
        stripped = stripped.replace(p, " ")
    norm = re.sub(r"\s+", " ", last)
    if all(p not in norm for p in passages):
        return norm.strip()  # the passages were in the system prompt: the message is the question
    qs = re.findall(r"[^.?!\n]{3,300}\?", stripped)
    if qs:
        return qs[-1].strip()
    lines = [ln.strip() for ln in stripped.splitlines() if ln.strip()]
    return lines[-1] if lines else ""


__all__ = ["ParsedRequest", "parse", "text_of"]
