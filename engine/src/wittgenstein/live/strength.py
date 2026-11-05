"""Recommendation strength and certainty labels in clinical guideline text.

Guidelines grade their recommendations, and an answer that turns a weak or conditional
recommendation into a rule -- or misses that a recommendation is *against* something --
says more than its source. Recognized systems (pattern matching only; a label is
reported with the exact text it came from):

- ACC/AHA class of recommendation and level of evidence: "Class I", "Class IIa",
  "Class IIb", "Class III" (no benefit or harm: a recommendation *against*); "LOE B-NR".
- GRADE: "strong / weak / conditional recommendation"; "high / moderate / low /
  very low -quality (or certainty) evidence"; "Grade 1A" ... "Grade 2C".
- USPSTF grades A, B, C, D, I ("Grade D recommendation", "(B recommendation)").
- Expert opinion / consensus / good practice statements.

"Class" followed by a letter is deliberately *not* matched (device classes, "Class R").
"""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class StrengthLabel:
    system: str
    text: str
    level: str
    """strong | moderate | weak | against | insufficient | expert_opinion | evidence_only"""
    start: int
    end: int

    @property
    def plain(self) -> str:
        return {
            "strong": "strong recommendation",
            "moderate": "moderate recommendation",
            "weak": "weak or conditional recommendation",
            "against": "recommendation against",
            "insufficient": "insufficient evidence to recommend",
            "expert_opinion": "expert opinion",
            "evidence_only": "evidence quality only",
        }[self.level]


_ACC = re.compile(
    r"\b(?:COR|Class(?: of Recommendation)?)\s*:?\s*(?P<cls>III|IIa|IIb|I)\b"
    r"(?:\s*[:(]\s*(?:No Benefit|Harm)\)?)?"
    r"(?:\s*[;,(]?\s*(?:LOE|Level of Evidence)\s*:?\s*(?P<loe>[ABC](?:-(?:R|NR|LD|EO))?))?"
)
_GRADE_WORDS = re.compile(r"\b(?P<s>strong|weak|conditional)\s+recommendation\b", re.I)
_GRADE_NUM = re.compile(r"\bGrade\s+(?P<g>[12][A-C])\b")
_USPSTF = re.compile(r"(?:\bGrade\s+(?P<a>[ABCDI])\b(?:\s+recommendation)?|\((?P<b>[ABCDI])\s+recommendation\))")
_QUALITY = re.compile(r"\b(?P<q>high|moderate|low|very low)[- ](?:quality|certainty)(?: of)?\s+evidence\b", re.I)
_EXPERT = re.compile(
    r"\b(?:expert opinion|consensus statement|good practice statement|best practice statement)\b", re.I
)
#: Context words that make a Roman-numeral "Class" a guideline class, not a device class.
_ACC_CONTEXT = re.compile(r"\b(?:recommend\w*|LOE|level of evidence|COR|benefit|harm)\b", re.I)


def find_strength(text: str) -> list[StrengthLabel]:
    out: list[StrengthLabel] = []
    acc_ok = bool(_ACC_CONTEXT.search(text))
    for m in _ACC.finditer(text):
        if not acc_ok and not m.group("loe"):
            continue
        cls = m.group("cls")
        level = {"I": "strong", "IIa": "moderate", "IIb": "weak", "III": "against"}[cls]
        out.append(StrengthLabel("ACC/AHA", m.group(0).strip(), level, m.start(), m.end()))
    for m in _GRADE_WORDS.finditer(text):
        out.append(
            StrengthLabel(
                "GRADE", m.group(0), "strong" if m.group("s").lower() == "strong" else "weak", m.start(), m.end()
            )
        )
    for m in _GRADE_NUM.finditer(text):
        out.append(
            StrengthLabel("GRADE", m.group(0), "strong" if m.group("g")[0] == "1" else "weak", m.start(), m.end())
        )
    for m in _USPSTF.finditer(text):
        g = m.group("a") or m.group("b")
        if m.group("a") and _GRADE_NUM.match(text, m.start()):
            continue
        level = {"A": "strong", "B": "moderate", "C": "weak", "D": "against", "I": "insufficient"}[g]
        out.append(StrengthLabel("USPSTF", m.group(0), level, m.start(), m.end()))
    for m in _QUALITY.finditer(text):
        out.append(StrengthLabel("GRADE", m.group(0), "evidence_only", m.start(), m.end()))
    for m in _EXPERT.finditer(text):
        out.append(StrengthLabel("expert", m.group(0), "expert_opinion", m.start(), m.end()))
    return sorted(out, key=lambda s: s.start)


def summarize(labels: list[StrengthLabel]) -> str | None:
    """One short chip text, e.g. "Class IIb, LOE B-NR (weak or conditional recommendation)"."""
    if not labels:
        return None
    rec = next((x for x in labels if x.level != "evidence_only"), None)
    quality = next((x for x in labels if x.level == "evidence_only"), None)
    parts = [x.text for x in (rec, quality) if x is not None]
    return f"{'; '.join(parts)} ({rec.plain})" if rec else "; ".join(parts)
