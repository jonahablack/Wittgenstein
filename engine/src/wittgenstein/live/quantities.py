"""Quantities (number + unit) in text, for checking that an answer's doses, thresholds,
durations and frequencies appear in the passages it cites.

Deliberately conservative: a bare small integer ("two", "3 of the criteria") is not
checked, because in prose most such numbers are counts or list positions; a number is
checked when it carries a unit, has a decimal point, or is large (>= 100), which is
where a wrong value changes a clinical meaning (500 mg vs 1000 mg, eGFR 30 vs 45).

Equal amounts in other units count as the same value (2 g = 2,000 mg; one-half hour =
30 minutes), so a correct conversion is never flagged. Ranges are compared as ranges:
"2.5 to 3.0" is not "2.0 to 3.0" even though both numbers appear in the source. Dosing
frequency ("once daily" vs "twice daily") is compared too. Red-team cases that drove
these rules: scripts/redteam/scenarios.py (C1-C3, C7, M4, M7).
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

_NUMBER_WORDS = {
    "one-half": 0.5, "one half": 0.5, "half an": 0.5, "half a": 0.5, "one-quarter": 0.25, "a quarter": 0.25,
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
    "eleven": 11, "twelve": 12, "fourteen": 14, "fifteen": 15, "eighteen": 18, "twenty": 20, "twenty-four": 24,
    "thirty": 30, "forty-eight": 48, "seventy-two": 72,
}  # fmt: skip
_WORD_NUM = "|".join(sorted((re.escape(w) for w in _NUMBER_WORDS), key=len, reverse=True))

_UNITS = [
    *sorted((re.escape(w) for w in _SPELLED), key=len, reverse=True),
    r"mg/kg/day", r"mg/kg/dose", r"mcg/kg/day", r"mg/kg", r"mcg/kg", r"mg/m\s?2", r"ml/min(?:ute)?/1\.73\s?m\s?2",
    r"ml/min(?:ute)?", r"mmol/l", r"mg/dl", r"meq/l", r"g/dl", r"mg", r"mcg", r"µg", r"ug", r"kg", r"ml", r"g",
    r"l", r"units?", r"iu", r"%", r"percent", r"hours?", r"hrs?", r"h", r"days?", r"weeks?", r"months?",
    r"years?", r"minutes?", r"min", r"times daily", r"times a day", r"cm", r"mm",
]  # fmt: skip
_UNIT_RE = "|".join(_UNITS)
_NUM = r"\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?"
_QTY = re.compile(
    rf"(?<![\w.])(?P<num>{_NUM})"
    rf"(?:\s*(?:-|–|to|and)\s*(?P<num2>{_NUM}))?"
    rf"(?:\s*(?P<unit>{_UNIT_RE}))?(?![\w/])",
    re.IGNORECASE,
)
#: Spelled-out amounts are read only with a unit ("one-half to one hour", "two weeks"):
#: without one, a number word is almost always a count.
_WORD_QTY = re.compile(
    rf"(?<![\w-])(?P<num>{_WORD_NUM})(?:\s+(?:to|or)\s+(?P<num2>{_WORD_NUM}))?\s+"
    rf"(?P<unit>hours?|days?|weeks?|months?|minutes?|years?)\b",
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
    "ml/minute": "ml/min",
    "ml/minute/1.73m2": "ml/min/1.73m2",
}
#: unit -> (dimension, factor to the dimension's base unit). Units not listed compare
#: only to themselves.
_SCALE = {
    "mcg": ("mass", 0.001), "mg": ("mass", 1.0), "g": ("mass", 1000.0),
    "ml": ("volume", 1.0), "l": ("volume", 1000.0),
    "min": ("time", 1.0), "hour": ("time", 60.0), "day": ("time", 1440.0), "week": ("time", 10080.0),
    "mcg/kg": ("dose_per_kg", 0.001), "mg/kg": ("dose_per_kg", 1.0),
    "mcg/kg/day": ("daily_dose_per_kg", 0.001), "mg/kg/day": ("daily_dose_per_kg", 1.0),
}  # fmt: skip


@dataclass(frozen=True)
class Quantity:
    value: str
    unit: str | None
    text: str
    start: int
    end: int
    range_with: str | None = None
    """For one end of a range ("2.0 to 3.0"), the other end's value."""


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


def _word_value(w: str) -> str:
    return _norm_value(f"{_NUMBER_WORDS[' '.join(w.lower().split())]:g}")


def quantities(text: str) -> list[Quantity]:
    out: list[Quantity] = []
    for m in _QTY.finditer(text):
        unit = _norm_unit(m.group("unit"))
        # "30 and 45" is a range only after "between"; otherwise two separate values.
        if (
            m.group("num2")
            and re.search(r"\band\b", m.group(0), re.IGNORECASE)
            and not re.search(r"\bbetween\s*$", text[: m.start()], re.IGNORECASE)
        ):
            for key in ("num", "num2"):
                out.append(Quantity(_norm_value(m.group(key)), unit, m.group(0).strip(), m.start(), m.end()))
            continue
        a, b = m.group("num"), m.group("num2")
        va, vb = _norm_value(a), _norm_value(b) if b else None
        out.append(Quantity(va, unit, m.group(0).strip(), m.start(), m.end(), vb))
        if b and vb is not None:
            out.append(Quantity(vb, unit, m.group(0).strip(), m.start(), m.end(), va))
    for m in _WORD_QTY.finditer(text):
        unit = _norm_unit(m.group("unit"))
        va = _word_value(m.group("num"))
        vb = _word_value(m.group("num2")) if m.group("num2") else None
        out.append(Quantity(va, unit, m.group(0).strip(), m.start(), m.end(), vb))
        if vb is not None:
            out.append(Quantity(vb, unit, m.group(0).strip(), m.start(), m.end(), va))
    return out


def checkable(q: Quantity) -> bool:
    return q.unit is not None or "." in q.value or float(q.value) >= 100


def canonical(value: str, unit: str | None) -> tuple[str, float] | None:
    """(dimension, amount in the base unit), or None for a unit with no conversions."""
    if unit not in _SCALE:
        return None
    dim, f = _SCALE[unit]
    return dim, float(value) * f


def _same_amount(a: tuple[str, float] | None, b: tuple[str, float] | None) -> bool:
    return a is not None and b is not None and a[0] == b[0] and abs(a[1] - b[1]) <= 1e-9 + 1e-6 * abs(b[1])


def present(q: Quantity, src: list[Quantity]) -> bool:
    """The source states this amount: same value and unit, or an equal amount in another unit."""
    cq = canonical(q.value, q.unit)
    for s in src:
        if s.value == q.value and s.unit == q.unit:
            return True
        if cq is not None and _same_amount(cq, canonical(s.value, s.unit)):
            return True
    return False


# --------------------------------------------------------------------------- frequency
_FREQ = re.compile(
    r"\b(?:(?P<word>once|twice|thrice)|(?P<n>\d+|two|three|four)\s+times)\s+(?:a\s+|per\s+)?"
    r"(?P<per>daily|day|weekly|week)\b"
    r"|\bevery\s+(?P<hours>\d+)\s+hours?\b"
    r"|\b(?P<single>single daily)\b",
    re.IGNORECASE,
)
_FREQ_WORDS = {"once": 1, "twice": 2, "thrice": 3, "two": 2, "three": 3, "four": 4}


@dataclass(frozen=True)
class Frequency:
    per_day: float
    text: str


def frequencies(text: str) -> list[Frequency]:
    out = []
    for m in _FREQ.finditer(text):
        if m.group("hours"):
            h = float(m.group("hours"))
            if h > 0:
                out.append(Frequency(24.0 / h, m.group(0)))
            continue
        if m.group("single"):
            out.append(Frequency(1.0, m.group(0)))
            continue
        w = (m.group("word") or m.group("n") or "").lower()
        n = float(_FREQ_WORDS.get(w, w if w.isdigit() else 1))
        per = m.group("per").lower()
        out.append(Frequency(n / 7.0 if per.startswith("week") else n, m.group(0)))
    return out


def compare_frequency(answer: str, focus: str, source: str) -> list[tuple[Frequency, list[Frequency]]]:
    """Answer frequencies the source never states, each with what the restated sentence
    (`focus`) says instead -- reported only when that sentence states a frequency, so a
    paraphrase of a sentence without one is never flagged."""
    have = {round(f.per_day, 4) for f in frequencies(source)}
    if re.search(r"\b(?:once\s+)?daily\b", source, re.IGNORECASE):
        have.add(1.0)
    focus_f = frequencies(focus)
    out = []
    for f in frequencies(answer):
        if round(f.per_day, 4) not in have and focus_f:
            out.append((f, focus_f))
    return out


# --------------------------------------------------------------------------- comparison
def _derived(q: Quantity, given: list[Quantity], src: list[Quantity]) -> str | None:
    """The answer's value worked out from the question and the source -- a per-kilogram
    dose times the patient's weight (1.6 mcg/kg/day x 70 kg = 112 mcg/day). Returns the
    calculation, so it can be shown for checking; it's arithmetic, not a quotation."""
    try:
        target = float(q.value)
    except ValueError:
        return None
    for g in given:
        for s in src:
            try:
                gv, sv = float(g.value), float(s.value)
            except ValueError:
                continue
            per_kg = s.unit is not None and "/kg" in s.unit and g.unit == "kg"
            if not per_kg:
                continue
            product = gv * sv
            if target and abs(product - target) / target <= 0.03:
                base = s.unit.split("/kg")[0] if s.unit else ""
                per_day = "/day" if "day" in (s.unit or "") else ""
                return f"{s.value} {s.unit} × {g.value} kg = {product:g} {base}{per_day}"
    return None


def compare(answer: str, source: str, given: str = "") -> list[tuple[Quantity, str, str | None]]:
    """(answer quantity, problem, what the source has) for each checkable quantity in
    `answer` that `source` doesn't state. problem:

    - "value_not_in_source": the source never states this amount (in any unit);
    - "different_unit": the number is there, but with a different unit;
    - "range_differs": one end of a range doesn't match the range the source gives;
    - "derived": not stated, but worked out from the question and the source (the third
      element is the calculation) -- reported for transparency, not as an error.

    Values from `given` (the question: the patient's weight, eGFR, age) are the
    question's facts, not claims about the source, and aren't checked here."""
    src = quantities(source)
    giv = quantities(given) if given else []
    by_value: dict[str, set[str | None]] = {}
    for s in src:
        by_value.setdefault(s.value, set()).add(s.unit)
    problems: list[tuple[Quantity, str, str | None]] = []
    seen_ranges: set[tuple[str, str, str | None]] = set()
    for q in quantities(answer):
        if not checkable(q):
            continue
        if any(g.value == q.value and (g.unit == q.unit or g.unit is None or q.unit is None) for g in giv):
            continue
        if q.range_with is not None and present(q, src):
            # Both ends must match one of the source's ranges (in any equal units).
            lo, hi = sorted((q.value, q.range_with), key=float)
            key = (lo, hi, q.unit)
            if key in seen_ranges:
                continue
            seen_ranges.add(key)
            ranges = [s for s in src if s.range_with is not None]
            if ranges and not any(
                present(
                    Quantity(q.range_with, q.unit, "", 0, 0), [Quantity(s.range_with or "", s.unit, "", 0, 0)]
                )
                and present(q, [s])
                for s in ranges
            ):
                near = next((s for s in ranges if present(q, [s])), ranges[0])
                problems.append((q, "range_differs", near.text))
            continue
        if present(q, src):
            continue
        units = by_value.get(q.value)
        if units is None:
            how = _derived(q, giv, src)
            problems.append((q, "derived", how) if how else (q, "value_not_in_source", None))
        elif q.unit is not None and q.unit not in units and any(u for u in units):
            # The source states this value with another unit; a unit-less mention of the
            # same number elsewhere (an imprint, a list number) doesn't excuse it.
            other = sorted(u for u in units if u)
            problems.append((q, "different_unit", f"{q.value} {other[0]}" if other else None))
    return problems


def compare_focused(
    answer: str, focus: str, source: str, given: str = ""
) -> list[tuple[Quantity, str, str | None]]:
    """Like `compare`, but a unit mismatch against `focus` -- the source sentence the
    answer restates -- is reported even when the same number appears unit-less elsewhere
    in the passage (a tablet imprint "10" must not excuse "10 mcg" for "10 mg")."""
    problems = compare(answer, source, given)
    flagged = {(q.value, q.unit) for q, _, _ in problems}
    for q, problem, found in compare(answer, focus, given):
        if problem == "different_unit" and (q.value, q.unit) not in flagged:
            problems.append((q, problem, found))
    return problems
