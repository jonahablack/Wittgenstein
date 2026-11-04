"""Conservative candidate-relationship classification from a field-comparison vector
-- docs/claim-linking-improvement-plan.md §5, implementing rules A-G exactly.

`classify_relationship` never itself asserts factual truth: its output
(`ClaimSupportCandidateStatus`) is always a pre-review candidate classification. Rule
E (conflict_candidate, multiple incompatible sources) is a multi-candidate aggregation
and is applied separately in `review/claim_linking.py`, not here -- this function
classifies exactly one (claim, candidate) pair.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from wittgenstein.core.enums import (
    ClaimSupportCandidateStatus,
    ComparisonFieldName,
    ComparisonOutcome,
    MismatchType,
)
from wittgenstein.schemas.claim_comparison import FieldComparison

#: Mismatch types that indicate the source supports a narrower/weaker/more
#: conditional version of the claim -- routed to QUALIFICATION_REQUIRED, never treated
#: as a contradiction (docs/claim-linking-improvement-plan.md, rule C).
_QUALIFICATION_MISMATCH_TYPES = {
    MismatchType.MODALITY_ESCALATION,
    MismatchType.MODALITY_WEAKENING,
    MismatchType.SCOPE_BROADENING,
    MismatchType.SCOPE_NARROWING,
    MismatchType.CONDITION_OMISSION,
    MismatchType.EXCEPTION_OMISSION,
}
#: Fields whose alignment is always required for any support relationship at all --
#: distinct from "critical fields," which also includes whatever else the claim
#: itself asserts (rule A/B/D's "entity/predicate alignment is established").
_STRUCTURAL_FIELDS = {ComparisonFieldName.ENTITY, ComparisonFieldName.PREDICATE}
#: Minimum comparison confidence required to promote a mismatch to
#: contradiction_candidate rather than leaving it unresolved (rule D, "comparison
#: confidence is sufficient").
_CONTRADICTION_CONFIDENCE_THRESHOLD = 0.5
#: Below this, a MISMATCH or UNKNOWN outcome is treated as noise, not a signal --
#: excluded even from pushing the result to `unresolved` (rule G). Without this floor,
#: a single very-low-confidence field (e.g. `object_value`'s crude "rest of the
#: sentence" heuristic, deliberately extracted at ~0.3 confidence) would drag an
#: otherwise fully-matching comparison down to `unresolved` even when seven other
#: fields cleanly matched -- exactly the "unjustified caution" this threshold exists
#: to avoid, mirroring "prefer unresolved over unjustified partial support" but applied
#: to noise floor rather than the support/unresolved boundary itself.
_NOISE_FLOOR_CONFIDENCE = 0.35


@dataclass
class RelationshipResult:
    status: ClaimSupportCandidateStatus
    mismatch_types: list[MismatchType] = field(default_factory=list)
    uncertainty_reason: str | None = None
    explanation: str = ""


def _outcome_for(comparisons: list[FieldComparison], field_name: ComparisonFieldName) -> FieldComparison | None:
    return next((c for c in comparisons if c.field_name == field_name), None)


def _bounded_explanation(status: ClaimSupportCandidateStatus, detail: str | None = None) -> str:
    templates = {
        ClaimSupportCandidateStatus.DIRECT_SUPPORT_CANDIDATE: "Candidate support identified.",
        ClaimSupportCandidateStatus.PARTIAL_SUPPORT_CANDIDATE: "This passage is topically related but may not "
        "fully support the claim.",
        ClaimSupportCandidateStatus.QUALIFICATION_REQUIRED: "A possible qualification mismatch was detected.",
        ClaimSupportCandidateStatus.CONTRADICTION_CANDIDATE: "A possible conflict in polarity, value, scope, or "
        "version was detected.",
        ClaimSupportCandidateStatus.NO_SUPPORT_EDGE_FOUND: "Support could not be established automatically.",
        ClaimSupportCandidateStatus.UNRESOLVED: "Support could not be established automatically. Human review is "
        "recommended.",
    }
    base = templates.get(status, "Human review is recommended.")
    return f"{base} {detail}".strip() if detail else base


def classify_relationship(comparisons: list[FieldComparison]) -> RelationshipResult:
    """Rules A-D, F, G from docs/claim-linking-improvement-plan.md. Rule E (conflict
    across multiple sources) is applied by the caller, over multiple RelationshipResults.
    """

    entity = _outcome_for(comparisons, ComparisonFieldName.ENTITY)
    predicate = _outcome_for(comparisons, ComparisonFieldName.PREDICATE)

    entity_established = entity is not None and entity.outcome == ComparisonOutcome.MATCH
    predicate_established = predicate is not None and predicate.outcome == ComparisonOutcome.MATCH

    # Rule F: no_support_found -- neither structural anchor established, and nothing
    # else in the vector suggests a plausible relationship either. POLARITY is
    # excluded from this check: `_extract_polarity` defaults to "positive" whenever no
    # negation cue fires, so two unrelated sentences trivially "match" on polarity --
    # that is not evidence of a plausible relationship, just the absence of negation
    # on both sides.
    if not entity_established and not predicate_established:
        any_match = any(
            c.outcome == ComparisonOutcome.MATCH and c.field_name != ComparisonFieldName.POLARITY
            for c in comparisons
        )
        if not any_match:
            return RelationshipResult(
                status=ClaimSupportCandidateStatus.NO_SUPPORT_EDGE_FOUND,
                explanation=_bounded_explanation(ClaimSupportCandidateStatus.NO_SUPPORT_EDGE_FOUND),
            )
        return RelationshipResult(
            status=ClaimSupportCandidateStatus.UNRESOLVED,
            uncertainty_reason="Entity/predicate alignment is uncertain despite some field-level overlap.",
            explanation=_bounded_explanation(
                ClaimSupportCandidateStatus.UNRESOLVED, "Entity or predicate alignment could not be established."
            ),
        )

    # Structural fields established on only one side -- not enough for support, but
    # not "no plausible relationship" either.
    if not entity_established or not predicate_established:
        return RelationshipResult(
            status=ClaimSupportCandidateStatus.UNRESOLVED,
            uncertainty_reason="Only one of entity/predicate alignment was established.",
            explanation=_bounded_explanation(
                ClaimSupportCandidateStatus.UNRESOLVED, "Entity or predicate alignment could not be established."
            ),
        )

    non_structural = [c for c in comparisons if c.field_name not in _STRUCTURAL_FIELDS]
    # A MISMATCH below the noise floor is dropped entirely (neither a mismatch nor an
    # absence) -- see _NOISE_FLOOR_CONFIDENCE. UNKNOWN is not floored the same way:
    # UNKNOWN's own definition already means "not confident enough to call MATCH or
    # MISMATCH," and most UNKNOWN comparisons carry no secondary confidence number at
    # all (None) -- an UNKNOWN is itself the signal Rule G abstains on, not a graded one.
    mismatches = [
        c
        for c in non_structural
        if c.outcome == ComparisonOutcome.MISMATCH and (c.confidence or 0.0) >= _NOISE_FLOOR_CONFIDENCE
    ]
    unknowns = [c for c in non_structural if c.outcome == ComparisonOutcome.UNKNOWN]
    matches = [c for c in non_structural if c.outcome == ComparisonOutcome.MATCH]
    # A field the claim never asserted at all (claim_value is None) is genuinely
    # non-applicable to this claim -- it must not block DIRECT_SUPPORT_CANDIDATE just
    # because most claims don't mention most of the 17 possible fields. Only an ABSENT
    # outcome where the claim *did* assert the field (but the source doesn't address
    # it) is the "non-critical absence" rule A/B actually care about.
    absences = [c for c in non_structural if c.outcome == ComparisonOutcome.ABSENT and c.claim_value is not None]

    qualification_mismatches = [c for c in mismatches if c.mismatch_type in _QUALIFICATION_MISMATCH_TYPES]
    hard_mismatches = [
        c
        for c in mismatches
        if c.mismatch_type not in _QUALIFICATION_MISMATCH_TYPES
        and (c.confidence or 0.0) >= _CONTRADICTION_CONFIDENCE_THRESHOLD
    ]
    low_confidence_mismatches = [
        c
        for c in mismatches
        if c.mismatch_type not in _QUALIFICATION_MISMATCH_TYPES
        and (c.confidence or 0.0) < _CONTRADICTION_CONFIDENCE_THRESHOLD
    ]

    # Rule D: contradiction_candidate -- entity/predicate established, an explicit,
    # sufficiently-confident incompatible value exists.
    if hard_mismatches:
        mismatch_types = [c.mismatch_type for c in hard_mismatches if c.mismatch_type is not None]
        detail = "; ".join(c.explanation for c in hard_mismatches)
        return RelationshipResult(
            status=ClaimSupportCandidateStatus.CONTRADICTION_CANDIDATE,
            mismatch_types=mismatch_types,
            explanation=_bounded_explanation(ClaimSupportCandidateStatus.CONTRADICTION_CANDIDATE, detail),
        )

    # Rule C: qualification_required -- source supports a narrower/weaker/more
    # conditional claim than asserted.
    if qualification_mismatches:
        mismatch_types = [c.mismatch_type for c in qualification_mismatches if c.mismatch_type is not None]
        detail = "; ".join(c.explanation for c in qualification_mismatches)
        return RelationshipResult(
            status=ClaimSupportCandidateStatus.QUALIFICATION_REQUIRED,
            mismatch_types=mismatch_types,
            explanation=_bounded_explanation(ClaimSupportCandidateStatus.QUALIFICATION_REQUIRED, detail),
        )

    # Rule G: unresolved -- a critical (non-structural, claim-asserted) field is
    # UNKNOWN, or a mismatch existed but confidence was too low to call it a
    # contradiction candidate.
    if unknowns or low_confidence_mismatches:
        return RelationshipResult(
            status=ClaimSupportCandidateStatus.UNRESOLVED,
            uncertainty_reason="A field comparison was UNKNOWN or too low-confidence to classify with confidence.",
            explanation=_bounded_explanation(ClaimSupportCandidateStatus.UNRESOLVED),
        )

    # Rule A: direct_support_candidate -- no mismatch, no unknown, and either every
    # non-structural field matched or there were simply no further fields to check.
    if not absences:
        return RelationshipResult(
            status=ClaimSupportCandidateStatus.DIRECT_SUPPORT_CANDIDATE,
            explanation=_bounded_explanation(ClaimSupportCandidateStatus.DIRECT_SUPPORT_CANDIDATE),
        )

    # Rule B: partial_support_candidate -- meaningful components matched, remaining
    # limitation is non-critical absence, not an explicit contradiction.
    if matches:
        return RelationshipResult(
            status=ClaimSupportCandidateStatus.PARTIAL_SUPPORT_CANDIDATE,
            explanation=_bounded_explanation(ClaimSupportCandidateStatus.PARTIAL_SUPPORT_CANDIDATE),
        )

    # Entity/predicate matched but nothing else could be compared either way --
    # genuinely nothing beyond topical/structural alignment to judge support on.
    return RelationshipResult(
        status=ClaimSupportCandidateStatus.UNRESOLVED,
        uncertainty_reason="Entity/predicate aligned, but no further field could be compared.",
        explanation=_bounded_explanation(ClaimSupportCandidateStatus.UNRESOLVED),
    )
