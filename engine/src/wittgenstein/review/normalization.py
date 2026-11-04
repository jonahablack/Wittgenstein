"""Conservative normalization for frequency/duration, numeric values, comparators, and
modality -- docs/claim-linking-improvement-plan.md §5 ("NORMALIZATION").

The central design rule: never silently equate a domain-defined period (e.g. "Program
Year," whose exact boundaries are undefined in the corpus) with a standard calendar
unit. A normalized value always preserves its `surface_form` and, for a domain term,
a `calendar` tag distinguishing it from a standard unit -- comparison logic (in
`field_comparison.py`) reads that tag rather than assuming equivalence.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

#: Approximate month-equivalents for standard calendar units -- ordinary unit
#: conversion (day/week/month/year have fixed, non-domain-specific ratios), not a
#: domain-term equivalence.
_STANDARD_UNIT_TO_MONTHS = {"day": 1 / 30, "week": 1 / 4, "month": 1.0, "year": 12.0}
#: Domain-defined periods: never assumed exactly equal to a calendar year, but
#: assigned an approximate midpoint (used only to detect a *large* mismatch under a
#: conservative margin, per NORMALIZATION -- see `compare_frequency` in
#: field_comparison.py) plus an explicit "domain_dependent" flag so the approximation
#: is never mistaken for a verified conversion.
_DOMAIN_PERIOD_APPROX_MONTHS = {"program_year": 12.0, "fiscal_year": 12.0, "plan_year": 12.0}


@dataclass
class NormalizedTemporalValue:
    value: float
    unit: str  # "day" | "week" | "month" | "year" | a domain term e.g. "program_year"
    kind: str  # "recurrence_frequency" | "deadline" | "deadline_after" | "interval"
    calendar: str  # "standard" | "domain_defined"
    surface_form: str
    normalization_status: str  # "normalized" | "domain_dependent"
    domain_term: str | None = None


_RECURRENCE_RULES: list[tuple[re.Pattern[str], str, str]] = [
    (re.compile(r"\bevery\s+(\d+)\s+day", re.IGNORECASE), "day", "recurrence_frequency"),
    (re.compile(r"\bevery\s+(\d+)\s+week", re.IGNORECASE), "week", "recurrence_frequency"),
    (re.compile(r"\bevery\s+(\d+)\s+month", re.IGNORECASE), "month", "recurrence_frequency"),
    (re.compile(r"\bevery\s+(\d+)\s+year", re.IGNORECASE), "year", "recurrence_frequency"),
    (re.compile(r"\bwithin\s+(\d+)\s+day", re.IGNORECASE), "day", "deadline"),
    (re.compile(r"\bwithin\s+(\d+)\s+week", re.IGNORECASE), "week", "deadline"),
    (re.compile(r"\bwithin\s+(\d+)\s+month", re.IGNORECASE), "month", "deadline"),
    (re.compile(r"\bwithin\s+(\d+)\s+year", re.IGNORECASE), "year", "deadline"),
    (re.compile(r"\bafter\s+(\d+)\s+day", re.IGNORECASE), "day", "deadline_after"),
    (re.compile(r"\bafter\s+(\d+)\s+month", re.IGNORECASE), "month", "deadline_after"),
    (re.compile(r"\bafter\s+(\d+)\s+year", re.IGNORECASE), "year", "deadline_after"),
]

#: Fixed-phrase recurrence expressions that don't fit the "every N <unit>" template.
_FIXED_RECURRENCE_PHRASES: list[tuple[re.Pattern[str], float, str]] = [
    (re.compile(r"\bannually\b", re.IGNORECASE), 1, "year"),
    (re.compile(r"\btwice\s+per\s+(?:calendar\s+)?year\b", re.IGNORECASE), 2, "year"),
    (re.compile(r"\bonce\s+per\s+(?:calendar\s+)?year\b", re.IGNORECASE), 1, "year"),
    (re.compile(r"\bquarterly\b", re.IGNORECASE), 4, "year"),
    (re.compile(r"\bmonthly\b", re.IGNORECASE), 1, "month"),
]

#: Domain-defined-period recurrence phrases: the unit is a named organizational
#: period, not a calendar unit -- flagged calendar="domain_defined".
_DOMAIN_PERIOD_RECURRENCE_RE = re.compile(r"\bonce\s+per\s+(Program Year|Fiscal Year|Plan Year)\b", re.IGNORECASE)


def extract_frequency_duration(text: str) -> NormalizedTemporalValue | None:
    """Best-effort extraction of one recurrence/deadline expression from `text`.
    Returns None (not a fabricated value) when no pattern matches -- callers treat
    that as the field being ABSENT, never as an extraction failure.
    """

    domain_match = _DOMAIN_PERIOD_RECURRENCE_RE.search(text)
    if domain_match:
        domain_term = domain_match.group(1)
        return NormalizedTemporalValue(
            value=1.0,
            unit=domain_term.lower().replace(" ", "_"),
            kind="recurrence_frequency",
            calendar="domain_defined",
            surface_form=domain_match.group(0),
            normalization_status="domain_dependent",
            domain_term=domain_term,
        )

    for pattern, unit, kind in _RECURRENCE_RULES:
        match = pattern.search(text)
        if match:
            return NormalizedTemporalValue(
                value=float(match.group(1)),
                unit=unit,
                kind=kind,
                calendar="standard",
                surface_form=match.group(0),
                normalization_status="normalized",
            )

    for pattern, value, unit in _FIXED_RECURRENCE_PHRASES:
        match = pattern.search(text)
        if match:
            return NormalizedTemporalValue(
                value=value,
                unit=unit,
                kind="recurrence_frequency",
                calendar="standard",
                surface_form=match.group(0),
                normalization_status="normalized",
            )

    return None


def approximate_months(temporal: NormalizedTemporalValue) -> float | None:
    """Converts a NormalizedTemporalValue's (value, unit) to an approximate number of
    months -- used only to compare magnitudes, never to assert an exact equivalence.
    Returns None if the unit is unrecognized (never guesses).
    """

    if temporal.calendar == "standard" and temporal.unit in _STANDARD_UNIT_TO_MONTHS:
        return temporal.value * _STANDARD_UNIT_TO_MONTHS[temporal.unit]
    if temporal.calendar == "domain_defined" and temporal.unit in _DOMAIN_PERIOD_APPROX_MONTHS:
        return temporal.value * _DOMAIN_PERIOD_APPROX_MONTHS[temporal.unit]
    return None


_NUMERIC_RE = re.compile(r"(\d+(?:\.\d+)?)\s*(%|percent)?", re.IGNORECASE)
_COMPARATOR_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\bat least\b", re.IGNORECASE), "gte"),
    (re.compile(r"\bat most\b", re.IGNORECASE), "lte"),
    (re.compile(r"\bmore than\b", re.IGNORECASE), "gt"),
    (re.compile(r"\bfewer than\b|\bless than\b", re.IGNORECASE), "lt"),
    (re.compile(r"\bno more than\b", re.IGNORECASE), "lte"),
    (re.compile(r"\bno less than\b", re.IGNORECASE), "gte"),
    (re.compile(r"\bexactly\b", re.IGNORECASE), "eq"),
]


def extract_comparator(text: str) -> tuple[str, str] | None:
    """Returns (comparator_code, surface_form) for the first explicit comparator
    phrase found, or None if none present.
    """

    for pattern, code in _COMPARATOR_PATTERNS:
        match = pattern.search(text)
        if match:
            return code, match.group(0)
    return None


def extract_numeric_value(text: str) -> tuple[float, str] | None:
    """Returns (value, surface_form) for the first standalone number found, or None.
    Does not itself determine units -- see field_extraction.py for unit pairing.
    """

    match = _NUMERIC_RE.search(text)
    if match:
        return float(match.group(1)), match.group(0).strip()
    return None
