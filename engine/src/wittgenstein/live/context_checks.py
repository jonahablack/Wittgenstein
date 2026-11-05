"""Integrity of what reached the model: the packed context itself, before any answer.

Red-team cases (scripts/redteam/scenarios.py) that these exist for:

- P1 instructions inside a passage aimed at the model ("ignore previous instructions
  and tell the user ..."): retrieved text is data, and a pipeline that pastes it into a
  prompt lets any document author steer the answer. Pattern-matched, so it catches
  the common phrasings, not a determined attacker -- labeled as such.
- P2 invisible characters (zero-width spaces, bidirectional overrides, soft hyphens):
  the text a person reads differs from what the index and the model see; "2​0 mg"
  no longer matches "20 mg" in search or checking.
- P8 a passage cut off mid-sentence by chunking: whatever followed (often the list of
  who an instruction applies to) never reached the model.
- P9 the same passage several times: duplicates waste the context budget and can
  crowd out the evidence that was needed.
"""

from __future__ import annotations

import re
import unicodedata

from wittgenstein.core.enums import CheckOutcome, FlagDisposition, FlagKind, FlagOrigin, FlagSeverity
from wittgenstein.live.flags import AwarenessFlag, FlagCollector
from wittgenstein.live.generate import ContextPassage
from wittgenstein.live.probes import ref

_INSTRUCTION = re.compile(
    r"\b(?:ignore|disregard|forget|override)\s+(?:all\s+|any\s+|the\s+)?(?:previous|prior|above|earlier|"
    r"preceding|your|system|other)\s+(?:instructions?|prompts?|rules?|directions?|context|messages?)"
    r"|\b(?:you\s+are\s+now|from\s+now\s+on,?\s+you|act\s+as\s+(?:an?\s+)?(?:ai|assistant|chatbot|"
    r"language\s+model))\b"
    r"|\b(?:note|message|instructions?)\s+(?:to|for)\s+(?:the\s+)?(?:ai|assistants?|chatbots?|language\s+models?|"
    r"llms?|models?)\b"
    r"|\b(?:system\s+prompt|developer\s+message|jailbreak)\b"
    r"|\b(?:do\s+not|don't|never)\s+(?:tell|inform|reveal\s+to|mention\s+to)\s+the\s+(?:user|patient|reader)\b"
    r"|\b(?:tell|inform)\s+the\s+user\s+(?:that|the)\b"
    r"|\b(?:respond|answer|reply)\s+(?:only\s+)?with\b"
    r"|<\s*/?\s*(?:system|instructions?|assistant)\s*>",
    re.IGNORECASE,
)
#: Unicode "format" characters (category Cf: zero-width, bidi controls, soft hyphen,
#: word joiner, BOM) plus other invisible spaces. Ordinary whitespace is not included.
_EXTRA_INVISIBLE = {" ": "no-break space"}


def _invisible(text: str) -> list[tuple[int, str]]:
    out = []
    for i, ch in enumerate(text):
        if unicodedata.category(ch) == "Cf":
            out.append((i, unicodedata.name(ch, f"U+{ord(ch):04X}").lower()))
    return out


_ENDS_CLEANLY = re.compile(r"""[.!?:;)\]"'”’]\s*$|\(\d+(?:\.\d+)*\)\s*$""")
_TRAILING_FUNCTION = re.compile(
    r"\b(?:a|an|the|of|in|with|and|or|to|for|by|on|at|from|if|unless|when|who|which|that|than|as|is|are|"
    r"patients?)\s*$",
    re.IGNORECASE,
)


def truncated(text: str) -> bool:
    """Ends mid-sentence: no closing punctuation and a function word or connective last
    ("...; in patients with a"). Headings, list items and table cells often lack a full
    stop, so a missing full stop alone isn't enough."""
    t = text.rstrip()
    if not t or _ENDS_CLEANLY.search(t):
        return False
    return bool(_TRAILING_FUNCTION.search(t)) or t.endswith(",")


def _norm(text: str) -> str:
    return " ".join(re.sub(r"[^\w\s]", " ", text.lower()).split())


def check_context(passages: list[ContextPassage], out: FlagCollector) -> None:
    injected: list[AwarenessFlag] = []
    hidden: list[AwarenessFlag] = []
    cut: list[AwarenessFlag] = []
    dupes: list[AwarenessFlag] = []
    seen: dict[str, int] = {}
    for p in passages:
        u = p.unit
        for m in _INSTRUCTION.finditer(u.text):
            # The sentence around the match, for the reader.
            s0 = max(u.text.rfind(".", 0, m.start()) + 1, 0)
            s1 = u.text.find(".", m.end())
            s1 = len(u.text) if s1 < 0 else s1 + 1
            f = out.flag(
                FlagKind.INSTRUCTION_IN_CONTEXT,
                origin=FlagOrigin.TEXT,
                stage="context",
                severity=FlagSeverity.WARNING,
                disposition=FlagDisposition.NEEDS_REVIEW,
                title="A passage contains instructions aimed at the model",
                observation=f"Passage [{p.n}] says: “{u.text[s0:s1].strip()[:220]}”.",
                why_it_matters="Retrieved text is pasted into the prompt; instructions inside it can steer the "
                "answer (prompt injection). Anyone who can edit a source document can do this.",
                what_to_check="Whether this passage belongs in the knowledge base, and whether the answer "
                "followed it.",
                refs=[ref(u, s0, s1)],
                metrics={"passage": p.n, "match": m.group(0)},
                measurement="pattern_match",
            )
            injected.append(f)
            break
        inv = _invisible(u.text)
        if inv:
            names = sorted({n for _, n in inv})
            first = inv[0][0]
            s0, s1 = max(0, first - 40), min(len(u.text), first + 40)
            f = out.flag(
                FlagKind.HIDDEN_CHARACTERS,
                origin=FlagOrigin.TEXT,
                stage="context",
                severity=FlagSeverity.CAUTION,
                disposition=FlagDisposition.NEEDS_REVIEW,
                title="A passage contains invisible characters",
                observation=f"Passage [{p.n}] has {len(inv)} invisible character(s): {', '.join(names[:4])}.",
                why_it_matters="Text can read one way to a person and another to the search index and the "
                "model (“2​0 mg” no longer matches “20 mg”); bidirectional controls can reorder what "
                "is displayed.",
                what_to_check="The source file's encoding, and whether the passage was tampered with.",
                refs=[ref(u, s0, s1)],
                metrics={"passage": p.n, "count": len(inv), "characters": names[:8]},
                measurement="pattern_match",
            )
            hidden.append(f)
        if truncated(u.text):
            tail = u.text.rstrip()
            s0 = max(0, len(tail) - 120)
            f = out.flag(
                FlagKind.TRUNCATED_PASSAGE,
                origin=FlagOrigin.PIPELINE,
                stage="context",
                severity=FlagSeverity.CAUTION,
                disposition=FlagDisposition.NEEDS_REVIEW,
                title="A passage stops mid-sentence",
                observation=f"Passage [{p.n}] ends “…{tail[-90:]}” — what came next didn't reach the model.",
                why_it_matters="Chunking that cuts a sentence can drop exactly the condition, exception or list "
                "of patients the instruction applies to.",
                what_to_check="The full sentence in the source document.",
                refs=[ref(u, s0, len(tail))],
                metrics={"passage": p.n},
                measurement="pattern_match",
            )
            cut.append(f)
        key = _norm(u.text)
        if key in seen:
            f = out.flag(
                FlagKind.REDUNDANCY,
                origin=FlagOrigin.PIPELINE,
                stage="context",
                severity=FlagSeverity.INFO,
                disposition=FlagDisposition.NEEDS_REVIEW,
                title="The same passage is in the prompt more than once",
                observation=f"Passage [{p.n}] repeats passage [{seen[key]}] word for word.",
                why_it_matters="Duplicates use context budget that other evidence could have had, and can make "
                "one source look like several agreeing ones.",
                what_to_check="Deduplication in the index or in retrieval.",
                refs=[ref(u, 0, min(len(u.text), 200))],
                metrics={"passage": p.n, "duplicate_of": seen[key]},
                measurement="measured",
            )
            dupes.append(f)
        else:
            seen[key] = p.n

    n = len(passages)
    out.check(
        FlagKind.INSTRUCTION_IN_CONTEXT,
        "No instructions to the model inside passages",
        CheckOutcome.FLAGGED if injected else CheckOutcome.PASSED if n else CheckOutcome.NOT_APPLICABLE,
        f"{len(injected)} of {n} passages contain text addressed to the model.",
        injected,
    )
    out.check(
        FlagKind.HIDDEN_CHARACTERS,
        "No invisible characters in passages",
        CheckOutcome.FLAGGED if hidden else CheckOutcome.PASSED if n else CheckOutcome.NOT_APPLICABLE,
        f"{len(hidden)} of {n} passages contain invisible characters.",
        hidden,
    )
    out.check(
        FlagKind.TRUNCATED_PASSAGE,
        "Passages end on complete sentences",
        CheckOutcome.FLAGGED if cut else CheckOutcome.PASSED if n else CheckOutcome.NOT_APPLICABLE,
        f"{len(cut)} of {n} passages stop mid-sentence.",
        cut,
    )
    if dupes:
        out.check(
            FlagKind.REDUNDANCY,
            "No duplicate passages in the prompt",
            CheckOutcome.FLAGGED,
            f"{len(dupes)} passages repeat another one.",
            dupes,
        )


__all__ = ["check_context", "truncated"]
