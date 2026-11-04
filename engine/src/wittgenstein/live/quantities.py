"""Quantities (number + unit) in text, for checking that an answer's doses, thresholds,
durations and frequencies appear in the passages it cites.

Deliberately conservative: a bare small integer ("two", "3 of the criteria") is not
checked, because in prose most such numbers are counts or list positions; a number is
checked when it carries a unit, has a decimal point, or is large (>= 100), which is
where a wrong value changes a clinical meaning (500 mg vs 1000 mg, eGFR 30 vs 45).
"""

from __future__ import annotations

import re
from dataclasses import dataclass

_SPELLED = {
    "milligrams": "mg", "milligram": "mg", "micrograms": "mcg", "microgram": "mcg", "grams": "g", "gram": "g",
    "kilograms": "kg", "kilogram": "kg", "milliliters": "ml", "millilitres": "ml", "milliliter": "ml",
    "millilitre": "ml", "liters": "l", "litres": "l", "liter": "l", "litre": "l", "centimeters": "cm",
    "centimetres": "cm", "centimeter": "cm", "centimetre": "cm", "millimeters": "mm", "millimetres": "mm",
    "millimeter": "mm", "millimetre": "mm", "international units": "iu",
}  # fmt: skip

_UNITS = [
    *sorted((re.escape(w) for w in _SPELLED), key=len, reverse=True),
    r"mg/kg/day", r"mg/kg/dose", r"mg/kg", r"mcg/kg", r"mg/m\s?2", r"ml/min/1\.73\s?m\s?2", r"ml/min",
    r"mmol/l", r"mg/dl", r"meq/l", r"g/dl", r"mg", r"mcg", r"µg", r"ug", r"kg", r"ml", r"g", r"l", r"units?",
    r"iu", r"%", r"percent", r"hours?", r"hrs?", r"h", r"days?", r"weeks?", r"months?", r"years?", r"minutes?",
    r"min", r"times daily", r"times a day", r"cm", r"mm",
]  # fmt: skip
_UNIT_RE = "|".join(_UNITS)
_QTY = re.compile(
    rf"(?<![\w.])(?P<num>\d{{1,3}}(?:,\d{{3}})+|\d+(?:\.\d+)?)"
    rf"(?:\s*(?:-|–|to)\s*(?P<num2>\d+(?:\.\d+)?))?"
    rf"(?:\s*(?P<unit>{_UNIT_RE}))?(?![\w/])",
    re.IGNORECASE,
)
_SYNONYMS = {
    **_SPELLED,
    "µg": "mcg",
    "ug": "mcg",
    "percent": "%",
    "hrs": "hour",
    "hr": "hour",
    "hours": "hour",
    "h": "hour",
    "days": "day",
    "weeks": "week",
    "months": "month",
    "years": "year",
    "minutes": "min",
    "minute": "min",
    "unit": "units",
    "times a day": "times daily",
}


@dataclass(frozen=True)
class Quantity:
    value: str
    unit: str | None
    text: str
    start: int
    end: int


def _norm_value(raw: str) -> str:
    v = raw.replace(",", "")
    if "." in v:
        v = v.rstrip("0").rstrip(".")
    return v


def _norm_unit(raw: str | None) -> str | None:
    if not raw:
        return None
    spaced = " ".join(raw.lower().split())
    if spaced in _SYNONYMS:
        return _SYNONYMS[spaced]
    u = spaced.replace(" ", "")
    return _SYNONYMS.get(u, u)


def quantities(text: str) -> list[Quantity]:
    out: list[Quantity] = []
    for m in _QTY.finditer(text):
        unit = _norm_unit(m.group("unit"))
        for key in ("num", "num2"):
            raw = m.group(key)
            if raw is None:
                continue
            out.append(Quantity(_norm_value(raw), unit, m.group(0).strip(), m.start(), m.end()))
    return out


def checkable(q: Quantity) -> bool:
    return q.unit is not None or "." in q.value or float(q.value) >= 100


def compare(answer: str, source: str) -> list[tuple[Quantity, str, str | None]]:
    """(answer quantity, problem, what the source has) for each checkable quantity in
    `answer` that `source` doesn't state. problem: "value_not_in_source" or
    "different_unit" (the value is there, but with another unit)."""
    src = quantities(source)
    pairs = {(q.value, q.unit) for q in src}
    by_value: dict[str, set[str | None]] = {}
    for q in src:
        by_value.setdefault(q.value, set()).add(q.unit)
    problems: list[tuple[Quantity, str, str | None]] = []
    for q in quantities(answer):
        if not checkable(q) or (q.value, q.unit) in pairs:
            continue
        units = by_value.get(q.value)
        if units is None:
            problems.append((q, "value_not_in_source", None))
        elif q.unit is not None and q.unit not in units and None not in units:
            other = sorted(u for u in units if u)
            problems.append((q, "different_unit", f"{q.value} {other[0]}" if other else None))
    return problems
