"""Artifact-versus-genuine-conflict explanation instrumentation --
docs/evidence-set-real-corpus-diagnostics-plan.md §7. Read-only: re-derives the exact
`extract_fields`/`compare_field` calls `review/evidence_set.py::_check_member_compatibility`
already made to recover full field comparisons (spans, extraction method, confidence)
for each recorded `EvidenceSetConflict` -- never a second extraction method, and never
writes back onto `EvidenceSet`/`review/evidence_set.py`'s production output.

This module never lowers, resolves, or reclassifies a conflict. It only exposes why
the system reached the conflict classification it did, for a human to label
(`core/enums.py::ConflictQualityDiagnosticLabel`).
"""

from __future__ import annotations

from dataclasses import dataclass

from wittgenstein.review.field_comparison import compare_field
from wittgenstein.review.field_extraction import extract_fields
from wittgenstein.schemas.claim_comparison import FieldComparison
from wittgenstein.schemas.evidence_set import EvidenceSet, EvidenceSetConflict
from wittgenstein.schemas.trace import ContextItem

#: Exposure-only threshold for flagging a conflict as resting on a low-confidence
#: field in the diagnostic report -- distinct from, and never substituted for,
#: `review/relationship_classification.py`'s `_NOISE_FLOOR_CONFIDENCE`/
#: `_CONTRADICTION_CONFIDENCE_THRESHOLD`, which are the only thresholds that affect
#: actual classification. Changing this constant changes what gets flagged for human
#: attention in a diagnostic report; it never changes any `ClaimSupportCandidateStatus`.
DIAGNOSTIC_LOW_CONFIDENCE_THRESHOLD = 0.5


@dataclass
class ConflictFieldExplanation:
    conflict: EvidenceSetConflict
    #: The re-derived member-a-vs-member-b `FieldComparison` for `conflict.field_name`
    #: -- `claim_value`/`claim_span` hold member_a's extraction, `source_value`/
    #: `source_span` hold member_b's (the same "claim"/"source" role convention
    #: `compare_field` always uses, here applied to two set members rather than a
    #: claim and a candidate).
    field_comparison: FieldComparison
    rests_on_low_confidence_field: bool
    #: True only when this is the *sole* conflicting field in the set and its
    #: comparison confidence sits below `DIAGNOSTIC_LOW_CONFIDENCE_THRESHOLD` -- a
    #: heuristic flag, not a re-classification, for "removing just this field would
    #: plausibly have changed the outcome away from a conflict." A human still makes
    #: the actual call (`ConflictQualityDiagnosticLabel`); this field never causes the
    #: system to act on its own judgment.
    alternative_non_conflict_classification_plausible: bool


def explain_conflicts(
    evidence_set: EvidenceSet, packed_items_by_id: dict[str, ContextItem]
) -> list[ConflictFieldExplanation]:
    """One `ConflictFieldExplanation` per `EvidenceSetConflict` already recorded on
    `evidence_set.conflicts`. Requires the same packed items the set was built from
    (`packed_items_by_id`, keyed by `ContextItem.item_id`) to re-extract each side's
    fields for the conflicting field name.
    """

    explanations = []
    only_conflict = len(evidence_set.conflicts) == 1
    for conflict in evidence_set.conflicts:
        item_a = packed_items_by_id.get(conflict.member_a_context_item_id)
        item_b = packed_items_by_id.get(conflict.member_b_context_item_id)
        if item_a is None or item_b is None:
            continue  # a member outside the supplied pool -- nothing to re-derive against

        fields_a = extract_fields(item_a.excerpt or "")
        fields_b = extract_fields(item_b.excerpt or "")
        comparison = compare_field(fields_a[conflict.field_name], fields_b[conflict.field_name])

        low_confidence = (comparison.confidence or 0.0) < DIAGNOSTIC_LOW_CONFIDENCE_THRESHOLD
        explanations.append(
            ConflictFieldExplanation(
                conflict=conflict,
                field_comparison=comparison,
                rests_on_low_confidence_field=low_confidence,
                alternative_non_conflict_classification_plausible=only_conflict and low_confidence,
            )
        )
    return explanations
