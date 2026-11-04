"""Tier 1: programmatic candidate-proposition splitting. Rule-based only -- sentence
boundaries are already Tier 0; this module further splits a Tier-0 segment (typically
a sentence) on semicolons, coordinating conjunctions, relative clauses, and condition
markers. The original segment is never rewritten; every candidate retains its
`source_segment_id` and its own char offsets *within that segment's text*
(docs/efficiency-and-processing-architecture.md §5, "TIER 1").

This is an approximate, auditable rule set, not a claim of correct syntactic parsing --
a candidate produced by an ambiguous split (`is_ambiguous=True`) is exactly the
"deterministic splitting produces ambiguous fragments" Tier-3 escalation trigger.
"""

from __future__ import annotations

import re
from itertools import pairwise

from wittgenstein.schemas.proposition import PropositionCandidate, SourceSegment

_SEMICOLON_RE = re.compile(r";\s*")
_COORDINATING_CONJUNCTION_RE = re.compile(r",\s+(and|but|or)\s+", re.IGNORECASE)
_RELATIVE_CLAUSE_RE = re.compile(r",\s+(which|who|that)\s+", re.IGNORECASE)
_CONDITION_MARKER_RE = re.compile(
    r"\b(if|unless|provided that|except (?:for|when|that)|when|where)\b\s+", re.IGNORECASE
)

#: Minimum span length (chars) for a split to be accepted -- avoids pathological
#: over-splitting of short coordinated phrases like "black and white".
_MIN_SPAN_LENGTH = 12


def _split_points(text: str, pattern: re.Pattern[str]) -> list[int]:
    return [m.end() for m in pattern.finditer(text)]


def split_candidates(segment: SourceSegment, id_prefix: str | None = None) -> list[PropositionCandidate]:
    """Split one SourceSegment's text into Tier-1 PropositionCandidates. Always returns
    at least one candidate (the whole segment, if no rule fires).
    """

    text = segment.text
    prefix = id_prefix or segment.segment_id

    split_points: set[int] = set()
    methods_by_point: dict[int, str] = {}
    for pattern, method in (
        (_SEMICOLON_RE, "semicolon"),
        (_COORDINATING_CONJUNCTION_RE, "conjunction"),
        (_RELATIVE_CLAUSE_RE, "relative_clause"),
        (_CONDITION_MARKER_RE, "condition_marker"),
    ):
        for point in _split_points(text, pattern):
            split_points.add(point)
            methods_by_point.setdefault(point, method)

    boundaries = sorted({0, *split_points, len(text)})
    spans: list[tuple[int, int, str]] = []
    for start, end in pairwise(boundaries):
        raw = text[start:end]
        stripped = raw.strip()
        if not stripped:
            continue
        local_start = start + raw.index(stripped)
        local_end = local_start + len(stripped)
        method = methods_by_point.get(start, "sentence_boundary" if start == 0 else "unspecified")
        spans.append((local_start, local_end, method))

    # Merge spans shorter than _MIN_SPAN_LENGTH into the following span, to avoid
    # pathological over-splitting -- never drop text, only avoid a spurious boundary.
    merged: list[tuple[int, int, str]] = []
    pending_start: int | None = None
    pending_method = "sentence_boundary"
    for local_start, local_end, method in spans:
        if pending_start is None:
            pending_start, pending_method = local_start, method
        if local_end - pending_start < _MIN_SPAN_LENGTH and (local_start, local_end, method) != spans[-1]:
            continue
        merged.append((pending_start, local_end, pending_method))
        pending_start = None
    if pending_start is not None:
        merged.append((pending_start, len(text), pending_method))

    if not merged:
        merged = [(0, len(text), "sentence_boundary")]

    candidates: list[PropositionCandidate] = []
    for i, (local_start, local_end, method) in enumerate(merged, start=1):
        candidate_text = text[local_start:local_end]
        candidates.append(
            PropositionCandidate(
                candidate_id=f"{prefix}-cand{i}",
                source_segment_id=segment.segment_id,
                text=candidate_text,
                char_start=local_start,
                char_end=local_end,
                split_method=method,
                is_ambiguous=len(merged) > 1 and method in ("conjunction", "relative_clause"),
            )
        )
    return candidates
