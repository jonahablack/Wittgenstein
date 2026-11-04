"""Text-artifact detectors, ported from the original app's `risk_triage.py`.

There they compared a source claim with its formal representation. Here the same
machinery compares an *evidence* sentence with the *answer* sentence that cites it:
did the answer keep the condition ("provided that ..."), the acknowledged exception
("although ..."), the hedge ("may")? Detection on evidence alone produces
`TextArtifact` records (a property of the source text); only the comparison against an
answer sentence can produce a needs-review flag (live/verify.py).

Kept from the original, with its documented rationale: word-boundary-safe matching
only (live/phrases.py); the spaCy subject-plus-finite-verb gate before a connective
counts as introducing a clause; "however"/"yet" need a clause before them; the
three-way present / severed / dropped classification. Literature references in the
original docstrings (RST definitions via Carlson & Marcu 2001; negation-scope and
context-mismatch studies) are not restated here and have not been re-verified as part
of this port.

One deliberate change: an answer that drops a *strong* modal ("must" -> plain
statement) is not flagged, since plain restatement of a requirement is ordinary
paraphrase; dropping a weak or medium hedge ("may", "should") is, because the answer
then claims more certainty than its source.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from wittgenstein.core.enums import FlagKind
from wittgenstein.live import phrases as P
from wittgenstein.live.corpus import Unit
from wittgenstein.live.nlp import has_subject_and_finite_verb

_CLAUSE_BOUNDARY = re.compile(r"[,;:.]")
_CLAUSE_STOPWORDS = {
    "the", "a", "an", "and", "or", "but", "that", "this", "these", "those", "is", "are", "was", "were", "be",
    "been", "being", "to", "of", "in", "on", "at", "for", "with", "as", "by", "it", "its", "not", "no", "may",
    "might", "could", "can", "will", "would", "shall", "should", "must", "do", "does", "did",
}  # fmt: skip


@dataclass(frozen=True)
class TextArtifact:
    kind: FlagKind
    unit_id: str
    sentence_start: int
    sentence_end: int
    """Offsets within the unit's text."""
    cue: str
    clause: str | None = None


def modal_strength(text: str) -> str | None:
    low = P.lower(text)
    if P.find_phrases(low, P.STRONG_MODALS):
        return "strong"
    if P.find_phrases(low, P.MEDIUM_MODALS):
        return "medium"
    if P.find_phrases(low, P.WEAK_MODALS):
        return "weak"
    return None


def modal_mismatch(source: str, answer: str) -> tuple[str, str | None] | None:
    """(source tier, answer tier) when the answer changes the source's modal force in a
    way that claims more (or different) certainty; None otherwise."""
    s = modal_strength(source)
    if s is None:
        return None
    a = modal_strength(answer)
    if a is None:
        return (s, None) if s in {"weak", "medium"} else None
    return None if a == s else (s, a)


def _clause_after(text: str, end: int) -> str:
    rest = text[end:]
    b = _CLAUSE_BOUNDARY.search(rest)
    return (rest[: b.start()] if b else rest).strip()


def find_satellite(
    low: str, connectives: list[str], needs_preceding: frozenset[str] = frozenset()
) -> tuple[str, str, int] | None:
    """Earliest, most specific connective introducing a well-formed clause, as
    (connective, clause, start offset). `low` must come from `phrases.lower()`."""
    cands = []
    for phrase in connectives:
        m = P.boundary_pattern(phrase).search(low)
        if m:
            cands.append((m.start(), -len(phrase), phrase, m.end()))
    cands.sort()
    for start, _, phrase, end in cands:
        if phrase in needs_preceding and not has_subject_and_finite_verb(low[:start].strip(" \t.,;:")):
            continue
        clause = _clause_after(low, end)
        if clause and has_subject_and_finite_verb(clause):
            return phrase, clause, start
    return None


def classify_severance(clause: str, connective: str, target: str) -> str | None:
    """None if both the connective and the clause's content survive in `target`;
    "dropped" if neither does; "severed" if only one does."""
    t = P.lower(target)
    conn = bool(t) and P.contains_phrase(t, connective)
    cwords = set(re.findall(r"[a-z']+", connective))
    content = [w for w in re.findall(r"[a-z']+", clause) if w not in _CLAUSE_STOPWORDS and w not in cwords]
    cont = bool(t) and any(P.contains_phrase(t, w) for w in content)
    if conn and cont:
        return None
    if not conn and not cont:
        return "dropped"
    return "severed"


def passage_artifacts(unit: Unit) -> list[TextArtifact]:
    out: list[TextArtifact] = []
    for sent, s0, s1 in unit.sentences:
        low = P.lower(sent)
        cond = find_satellite(low, P.CONDITION_CONNECTIVES)
        if cond:
            out.append(TextArtifact(FlagKind.CONDITION_SATELLITE, unit.unit_id, s0, s1, cond[0], cond[1]))
        conc = find_satellite(low, P.CONCESSION_CONNECTIVES, P.CONCESSION_NEEDS_PRECEDING_CLAUSE)
        if conc and not (cond and conc[0] == cond[0]):
            out.append(TextArtifact(FlagKind.CONCESSION_SATELLITE, unit.unit_id, s0, s1, conc[0], conc[1]))
        neg = P.find_phrases(low, P.NEGATION_WORDS)
        if neg and sum(P.count_phrase(low, c) for c in P.CLAUSE_CONNECTORS):
            out.append(TextArtifact(FlagKind.NEGATION_SCOPE, unit.unit_id, s0, s1, neg[0]))
        back = P.find_phrases(low, P.CROSS_REFERENCE_PHRASES)
        if back:
            out.append(TextArtifact(FlagKind.BACKWARD_REFERENCE, unit.unit_id, s0, s1, back[0]))
        unres = P.find_phrases(low, P.UNRESOLVED_REFERENCE_MARKERS)
        if unres:
            out.append(TextArtifact(FlagKind.UNRESOLVED_REFERENCE, unit.unit_id, s0, s1, unres[0]))
    return out
