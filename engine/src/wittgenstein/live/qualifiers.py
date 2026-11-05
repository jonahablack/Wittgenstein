"""How far a patient group extends: the degree words and thresholds that narrow it.

The patient-group check asks whether the answer still names the group the source is
about. That is not enough: "contraindicated in severe renal impairment" restated as
"contraindicated in renal impairment" keeps the group and silently widens it to every
patient with any kidney impairment (found in testing; the planted-error evaluation
only dropped whole groups). Likewise "eGFR below 30" restated as "renal impairment".

So for each group the source sentence names, this module reads its *extent*:
- degree words in front of it ("severe", "moderate to severe", "end-stage"), and the
  adverb forms that precede a participle ("severely impaired renal function");
- a numeric threshold next to it ("eGFR below 30 mL/min", "CrCl < 30").

and compares it with the answer's mention of the same group (POPULATION_GROUPS
equivalence: kidney disease = renal impairment = eGFR):
- source narrowed, answer names the group with no degree and no threshold: dropped;
- answer gives a different degree ("moderate" for "severe"): changed;
- answer gives a threshold or any overlapping degree: kept. A threshold restating a
  degree ("eGFR below 30" for "severe") is accepted without judging the equivalence.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from wittgenstein.live import phrases as P

#: Degree word stem -> canonical degree.
_DEGREES = {
    "mild": "mild",
    "moderat": "moderate",
    "sever": "severe",
    "advanced": "advanced",
    "end-stage": "end-stage",
    "end stage": "end-stage",
    "endstage": "end-stage",
    "decompensated": "decompensated",
}
_DEGREE_RE = re.compile(r"\b(mild(?:ly)?|moderat(?:e|ely)|sever(?:e|ely)|advanced|end[- ]?stage|decompensated)\b")
#: Words allowed between a degree word and the group it qualifies: "moderate to
#: severe", "severe or end-stage", "severely impaired", "severe chronic".
_FILLER = {
    "to", "or", "and", "-", "/", "impaired", "reduced", "decreased", "chronic", "acute", "renal", "hepatic",
    "kidney", "liver", "the", "of",
}  # fmt: skip
_WINDOW = 5
_NUMBER = re.compile(r"\d")
#: The rest of a threshold after the group: " below 30 mL/min/1.73 m2", " < 30 mL/min".
_THRESHOLD_SPAN = re.compile(
    r"(?:\s*\(?\s*(?:egfr|crcl|gfr)?\s*(?:is\s+)?"
    r"(?:below|above|less than|greater than|under|over|at least|between|of|<|>|≤|≥|<=|>=)?"
    r"\s*\d[\d.,]*(?:\s*(?:and|to|-)\s*\d[\d.,]*)?\s*"
    r"(?:ml/min(?:ute)?(?:/1\.73\s*m\s*2|/1\.73\s*m²)?|mg/dl|%|years?|kg)?)"
)
_THRESHOLD_WORDS = re.compile(r"\b(below|above|less than|greater than|under|over|at least|<|>|≤|≥|<=|>=)")


@dataclass(frozen=True)
class Extent:
    group: str
    cue: str
    degrees: frozenset[str]
    threshold: bool
    phrase: str  # the source wording, for the flag ("severe renal impairment")


def _tokens(text: str) -> list[tuple[str, int, int]]:
    return [(m.group(0), m.start(), m.end()) for m in re.finditer(r"[a-z0-9]+(?:-[a-z0-9]+)*|[<>≤≥/-]", text)]


def extents(text: str) -> dict[str, Extent]:
    """For each patient group `text` names, its degree words and whether a threshold is
    attached. Keyed by group (POPULATION_GROUPS), the first mention with the most detail."""
    low = P.lower(text)
    toks = _tokens(low)
    out: dict[str, Extent] = {}
    for cue in P.POPULATION_CUES:
        if cue in P.GENERIC_POPULATION_CUES:
            continue
        for m in re.finditer(rf"\b{re.escape(cue)}", low):
            group = P.POPULATION_GROUPS.get(cue, cue)
            start_tok = next((i for i, t in enumerate(toks) if t[1] >= m.start()), len(toks))
            degrees: set[str] = set()
            first = start_tok
            j = start_tok - 1
            steps = 0
            while j >= 0 and steps < _WINDOW:
                word = toks[j][0]
                d = _degree(word)
                if d:
                    degrees.add(d)
                    first = j
                elif word not in _FILLER:
                    break
                j -= 1
                steps += 1
            # A threshold right after the group ("eGFR below 30", "CrCl < 30 mL/min",
            # "renal impairment (eGFR below 30 ...)") or right before it ("30 mL/min").
            after = low[m.end() : m.end() + 60]
            before = low[max(0, m.start() - 25) : m.start()]
            threshold = bool(
                (_NUMBER.search(after[:40]) and _THRESHOLD_WORDS.search(after[:40]))
                or (_NUMBER.search(after[:12]))
                or (_THRESHOLD_WORDS.search(before) and _NUMBER.search(before))
            )
            end = m.end()
            if threshold:
                t = _THRESHOLD_SPAN.match(low, m.end())
                if t:
                    end = t.end()
            phrase = text[toks[first][1] : end] if first < len(toks) else cue
            if phrase.count("(") > phrase.count(")"):
                phrase += ")"
            prev = out.get(group)
            if prev is None or (len(degrees) + threshold) > (len(prev.degrees) + prev.threshold):
                out[group] = Extent(group, cue, frozenset(degrees), threshold, phrase.strip())
    return out


def _degree(word: str) -> str | None:
    m = _DEGREE_RE.fullmatch(word) or _DEGREE_RE.match(word)
    if not m:
        return None
    w = m.group(1)
    for stem, canon in _DEGREES.items():
        if w.startswith(stem):
            return canon
    return None


@dataclass(frozen=True)
class Widening:
    group: str
    source_phrase: str
    kind: str  # "dropped" | "changed"
    answer_degrees: frozenset[str]


def widened(source: str, answer: str, given: str = "") -> list[Widening]:
    """Groups the source narrows by degree or threshold that the answer names without
    that narrowing. `given`: the question; a degree the question states counts as kept
    (a bare "Yes." to "...in severe renal impairment?" is reconstructed with it)."""
    src = extents(source)
    ans = extents(answer)
    asked = extents(given) if given else {}
    out: list[Widening] = []
    for group, s in src.items():
        if not (s.degrees or s.threshold):
            continue
        a = ans.get(group)
        if a is None:
            continue  # the group itself is gone: the patient-group check reports that
        if a.threshold:
            continue
        if s.degrees and a.degrees:
            # Same or narrower ("severe" for "moderate to severe") is faithful; any
            # degree the source doesn't give ("moderate to severe" for "severe") widens it.
            if not (a.degrees - s.degrees):
                continue
            out.append(Widening(group, s.phrase, "changed", a.degrees))
            continue
        q = asked.get(group)
        if not a.degrees and q is not None and (q.threshold or (s.degrees & q.degrees)):
            continue
        if a.degrees:
            continue  # source gave only a threshold, answer a degree: not judged
        out.append(Widening(group, s.phrase, "dropped", frozenset()))
    return out


__all__ = ["Extent", "Widening", "extents", "widened"]
