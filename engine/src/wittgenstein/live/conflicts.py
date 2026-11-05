"""Conflicting evidence among the passages an answer was built from.

Two passages used together can state different values or opposite polarity for the same
thing (an older and a newer dose, "contraindicated" vs "not contraindicated"). A model
given both may follow either one, silently. This module finds such pairs and reports
them side by side; it never decides which one is right.

It reuses the engine's conservative field comparison (`review/claim_linking.py`:
entity, predicate, values, polarity, patient group, ...) rather than defining a second
notion of contradiction. Pairs that differ only by patient group or condition are
"unresolved" there, not contradictions, and are not reported as conflicts.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from wittgenstein.core.enums import ClaimSupportCandidateStatus, ComparisonOutcome
from wittgenstein.live import nli
from wittgenstein.live.corpus import UnitSet
from wittgenstein.review.claim_linking import compare_claim_to_candidate
from wittgenstein.schemas.trace import AnswerClaim, ContextItem

#: Sentences are compared only when they share at least this share of content words --
#: they must be about the same thing before a difference can be a conflict.
MIN_TOPIC_OVERLAP = 0.35
MAX_SENTENCES_PER_PASSAGE = 25
MAX_CONFLICTS = 3
#: Language-inference bar for a passage-pair conflict, and a per-run call budget.
NLI_CONFLICT = 0.95
MAX_NLI_CALLS = 80
_STOP = frozenset(
    [
        "the",
        "a",
        "an",
        "and",
        "or",
        "of",
        "to",
        "in",
        "on",
        "for",
        "by",
        "with",
        "as",
        "at",
        "from",
        "that",
        "this",
        "these",
        "those",
        "is",
        "are",
        "was",
        "were",
        "be",
        "been",
        "it",
        "its",
        "may",
        "can",
        "should",
        "must",
        "not",
        "no",
    ]
)
_DIMENSIONS = {
    "numeric_value": "value",
    "object_value": "value",
    "unit": "value",
    "frequency_duration": "value",
    "polarity": "polarity",
    "comparator": "value",
    "temporal_scope": "time_version",
}


@dataclass(frozen=True)
class Conflict:
    unit_a: str
    unit_b: str
    sentence_a: tuple[str, int, int]
    sentence_b: tuple[str, int, int]
    fields: tuple[str, ...]
    dimension: str
    model_contradiction: float | None = None
    """Set when found by the language-inference model rather than field comparison."""


def _content(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-z0-9]+", text.lower()) if w not in _STOP and len(w) > 1}


#: A named item of a kind: "Class S", "Article 5", "Tier 2", "Schedule II".
_NAMED = re.compile(
    r"\b(class|type|tier|grade|category|stage|schedule|group|level|phase|article|section|part|annex|table|"
    r"definition|model|version)\s+([A-Z0-9][\w.()-]*)",
    re.IGNORECASE,
)


def different_referents(a: str, b: str) -> bool:
    """The two sentences are about different things of the same kind: different named
    items ("Class R" / "Class S") or opposite members of a contrast set
    (immediate-release / extended-release). Different limits for different things are
    not a conflict (seen: Class R's 12 cm against Class S's 8 cm)."""
    from wittgenstein.live.claims import contrast_terms

    def named(t: str) -> dict[str, set[str]]:
        out: dict[str, set[str]] = {}
        for m in _NAMED.finditer(t):
            out.setdefault(m.group(1).lower(), set()).add(m.group(2).lower().rstrip(".,;:"))
        return out

    na, nb = named(a), named(b)
    if any(k in nb and na[k].isdisjoint(nb[k]) for k in na):
        return True
    ca = {(group, member) for _, member, group in contrast_terms(a)}
    cb = {(group, member) for _, member, group in contrast_terms(b)}
    groups = {g for g, _ in ca} & {g for g, _ in cb}
    return any({m for g, m in ca if g == grp}.isdisjoint({m for g, m in cb if g == grp}) for grp in groups)


def find_conflicts(units: UnitSet, used: list[str]) -> list[Conflict]:
    sents = {
        uid: [s for s in units.by_id[uid].sentences if len(s[0]) > 20][:MAX_SENTENCES_PER_PASSAGE] for uid in used
    }
    found: list[Conflict] = []
    nli_calls = 0
    pairs_seen: set[tuple[str, str]] = set()
    for i, ua in enumerate(used):
        for ub in used[i + 1 :]:
            if (ua, ub) in pairs_seen:
                continue
            for sa in sents[ua]:
                ca = _content(sa[0])
                if not ca:
                    continue
                for sb in sents[ub]:
                    cb = _content(sb[0])
                    if not cb or " ".join(sa[0].lower().split()) == " ".join(sb[0].lower().split()):
                        continue
                    if len(ca & cb) / len(ca | cb) < MIN_TOPIC_OVERLAP:
                        continue
                    if different_referents(sa[0], sb[0]):
                        continue
                    cmp = compare_claim_to_candidate(
                        AnswerClaim(claim_id="a", text=sa[0]), ContextItem(item_id="b", excerpt=sb[0])
                    )
                    if cmp.relationship_status != ClaimSupportCandidateStatus.CONTRADICTION_CANDIDATE:
                        # Same topic, no field-level contradiction: ask the language-inference
                        # model, with a strict bar (a passage pair gets more scrutiny than an
                        # answer sentence).
                        if nli_calls < MAX_NLI_CALLS and (v := nli.pair(sa[0], sb[0])) is not None:
                            nli_calls += 1
                            if v.contradiction >= NLI_CONFLICT:
                                found.append(Conflict(ua, ub, sa, sb, ("meaning",), "meaning", v.contradiction))
                                pairs_seen.add((ua, ub))
                                break
                        continue
                    fields = tuple(
                        fc.field_name.value
                        for fc in cmp.field_comparisons
                        if fc.outcome == ComparisonOutcome.MISMATCH
                    )
                    dims = {_DIMENSIONS[f] for f in fields if f in _DIMENSIONS}
                    dimension = "polarity" if "polarity" in dims else (sorted(dims)[0] if dims else "value")
                    found.append(Conflict(ua, ub, sa, sb, fields, dimension, None))
                    pairs_seen.add((ua, ub))
                    break
                if (ua, ub) in pairs_seen:
                    break
            if len(found) >= MAX_CONFLICTS:
                return found
    return found
