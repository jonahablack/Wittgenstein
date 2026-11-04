"""Tier 2: lightweight, regex/word-list-based annotation. Produces candidate risk cues
and dependency links -- never guaranteed semantic interpretations
(docs/efficiency-and-processing-architecture.md §1, "TIER 2"). Every annotation this
module produces is labeled `research_hypothesis` or `experimental_review_cue`
(`CueEpistemicLabel`) and must never be presented as proof of model error ("RISK
ANALYSIS" in the architecture doc) -- see `matching/explanation.py` for the same
discipline already enforced for registry mechanisms.

All patterns use `\\b` word boundaries specifically to avoid the substring-collision
class of bug documented in this project's own history (`CLAUDE.md`, "Risk-triage
engineering conventions" -- e.g. a bare `in` check matching inside "nonprofit"); this
is the same lesson, applied here rather than merely cited.
"""

from __future__ import annotations

import re

from wittgenstein.core.enums import AnnotationCueType, CueEpistemicLabel
from wittgenstein.schemas.proposition import PropositionAnnotation, PropositionCandidate

_DETECTOR_VERSION = "tier2-regex-1"

_NEGATION_RE = re.compile(r"\b(not|never|none|cannot|no longer|without)\b", re.IGNORECASE)
_MODALITY_HEDGE_RE = re.compile(
    r"\b(may|might|could|should|must|shall|can|possibly|likely|unlikely|presumably)\b", re.IGNORECASE
)
_CONDITION_RE = re.compile(r"\b(if|unless|provided that|in the event that|contingent on|only if)\b", re.IGNORECASE)
_EXCEPTION_RE = re.compile(
    r"\b(except|excluding|other than|aside from|unless otherwise|with the exception of)\b", re.IGNORECASE
)
_ATTRIBUTION_RE = re.compile(
    r"\b(according to|states that|reports that|claims that|per the|as stated in)\b", re.IGNORECASE
)
_TEMPORAL_RE = re.compile(
    r"\b(before|after|since|until|effective|as of|program year \d+|"
    r"january|february|march|april|may|june|july|august|september|october|november|december)\b",
    re.IGNORECASE,
)
_NUMERIC_UNIT_RE = re.compile(
    r"\b\d+(?:\.\d+)?\s*(?:kg|km|%|percent|days?|years?|business days?|tokens?|kb|mb|hours?|minutes?)\b",
    re.IGNORECASE,
)
_CROSS_REFERENCE_RE = re.compile(
    r"\b(Section|Table|Figure|Exemption|Appendix|Clause)\s+[A-Za-z0-9.]+(?:\([a-z]\))?", re.IGNORECASE
)

_PATTERNS: list[tuple[AnnotationCueType, re.Pattern[str]]] = [
    (AnnotationCueType.NEGATION, _NEGATION_RE),
    (AnnotationCueType.MODALITY_HEDGE, _MODALITY_HEDGE_RE),
    (AnnotationCueType.CONDITION, _CONDITION_RE),
    (AnnotationCueType.EXCEPTION, _EXCEPTION_RE),
    (AnnotationCueType.ATTRIBUTION, _ATTRIBUTION_RE),
    (AnnotationCueType.TEMPORAL, _TEMPORAL_RE),
    (AnnotationCueType.NUMERIC_UNIT, _NUMERIC_UNIT_RE),
    (AnnotationCueType.CROSS_REFERENCE, _CROSS_REFERENCE_RE),
]


def annotate_candidate(
    candidate: PropositionCandidate,
    epistemic_label: CueEpistemicLabel = CueEpistemicLabel.EXPERIMENTAL_REVIEW_CUE,
) -> list[PropositionAnnotation]:
    """Scan one PropositionCandidate's text for Tier-2 cues. Never mutates the
    candidate; offsets are relative to the candidate's own text.
    """

    annotations: list[PropositionAnnotation] = []
    counter = 0
    for cue_type, pattern in _PATTERNS:
        for match in pattern.finditer(candidate.text):
            counter += 1
            annotations.append(
                PropositionAnnotation(
                    annotation_id=f"{candidate.candidate_id}-ann{counter}",
                    candidate_id=candidate.candidate_id,
                    cue_type=cue_type,
                    matched_text=match.group(0),
                    char_start=match.start(),
                    char_end=match.end(),
                    epistemic_label=epistemic_label,
                    detector_version=_DETECTOR_VERSION,
                )
            )
    return annotations


def contains_negation(text: str) -> bool:
    """Whether `text` matches the same negation-cue pattern `annotate_candidate` uses.
    Exposed for `review/claim_linking.py`'s conflict-candidate heuristic, so that module
    reuses this pattern rather than defining a second one (CLAUDE.md, "avoid two lists/
    tables describing the same category").
    """

    return bool(_NEGATION_RE.search(text))
