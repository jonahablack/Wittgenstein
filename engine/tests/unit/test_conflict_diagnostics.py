"""Artifact-versus-genuine-conflict explanation instrumentation --
docs/evidence-set-real-corpus-diagnostics-plan.md §7. Fixtures 5-8 from
"FIXTURES AND TESTS": genuine conflict with high-confidence extraction; apparent
conflict caused by low-confidence extraction; parser/regex disagreement; a long
sentence with multiple field extractions.
"""

from __future__ import annotations

from wittgenstein.core.enums import ComparisonFieldName, ComparisonOutcome, ExtractionStatus
from wittgenstein.review.conflict_diagnostics import DIAGNOSTIC_LOW_CONFIDENCE_THRESHOLD, explain_conflicts
from wittgenstein.review.field_comparison import compare_field
from wittgenstein.review.field_extraction import extract_fields
from wittgenstein.schemas.claim_comparison import ExtractedField
from wittgenstein.schemas.evidence_set import EvidenceSet, EvidenceSetConflict
from wittgenstein.schemas.trace import ContextItem

_ITEMS = {
    "a": ContextItem(item_id="a", excerpt="Widgets must be inspected annually, per Program Year 2019.", rank=1),
    "b": ContextItem(item_id="b", excerpt="Widgets must be inspected annually, per Program Year 2023.", rank=2),
    "c": ContextItem(
        item_id="c",
        excerpt="Widgets must be inspected annually, subject to standard scheduling requirements.",
        rank=3,
    ),
}


def _evidence_set(conflicts: list[EvidenceSetConflict]) -> EvidenceSet:
    return EvidenceSet(
        evidence_set_id="EVSET-test",
        trace_id="t1",
        answer_claim_id="c1",
        member_context_item_ids=["a", "b"],
        conflicts=conflicts,
        relationship_status="composite_conflict_candidate",
        construction_rationale="test fixture",
        explanation="test fixture",
    )


# Fixture 5: genuine conflict with high-confidence extraction (VERSION, dedicated
# comparator, moderate-to-high confidence).
def test_05_genuine_conflict_high_confidence() -> None:
    evidence_set = _evidence_set(
        [
            EvidenceSetConflict(
                member_a_context_item_id="a",
                member_b_context_item_id="b",
                field_name=ComparisonFieldName.VERSION,
                explanation="Program Year 2019 vs. Program Year 2023.",
            )
        ]
    )
    explanations = explain_conflicts(evidence_set, _ITEMS)
    assert len(explanations) == 1
    explanation = explanations[0]
    assert explanation.field_comparison.outcome == ComparisonOutcome.MISMATCH
    assert explanation.field_comparison.confidence is not None
    assert explanation.field_comparison.confidence >= DIAGNOSTIC_LOW_CONFIDENCE_THRESHOLD
    assert explanation.rests_on_low_confidence_field is False


# Fixture 6: apparent conflict caused by low-confidence extraction (OBJECT_VALUE's
# "rest of the sentence" heuristic, deliberately low confidence).
def test_06_apparent_conflict_low_confidence_extraction() -> None:
    evidence_set = _evidence_set(
        [
            EvidenceSetConflict(
                member_a_context_item_id="a",
                member_b_context_item_id="c",
                field_name=ComparisonFieldName.OBJECT_VALUE,
                explanation="Trailing text differs.",
            )
        ]
    )
    explanations = explain_conflicts(evidence_set, {"a": _ITEMS["a"], "c": _ITEMS["c"]})
    assert len(explanations) == 1
    explanation = explanations[0]
    assert explanation.rests_on_low_confidence_field is True
    # Only conflict in the set + low confidence -> flagged as plausibly reversible,
    # never auto-reversed.
    assert explanation.alternative_non_conflict_classification_plausible is True


# The system never lowers a conflict on its own -- explain_conflicts never mutates
# evidence_set.conflicts or evidence_set.relationship_status.
def test_conflict_diagnostics_never_mutates_the_evidence_set() -> None:
    evidence_set = _evidence_set(
        [
            EvidenceSetConflict(
                member_a_context_item_id="a",
                member_b_context_item_id="c",
                field_name=ComparisonFieldName.OBJECT_VALUE,
                explanation="Trailing text differs.",
            )
        ]
    )
    before_status = evidence_set.relationship_status
    before_conflict_count = len(evidence_set.conflicts)
    explain_conflicts(evidence_set, {"a": _ITEMS["a"], "c": _ITEMS["c"]})
    assert evidence_set.relationship_status == before_status
    assert len(evidence_set.conflicts) == before_conflict_count


# Fixture 7: parser/regex disagreement -- an EXTRACTION_CONFLICT status on either side
# must compare as UNKNOWN, never silently resolved to a MATCH or MISMATCH.
def test_07_parser_disagreement_preserved_as_unknown() -> None:
    conflicted_field = ExtractedField(
        field_name=ComparisonFieldName.FREQUENCY_DURATION,
        value=None,
        extraction_method="regex",
        extraction_status=ExtractionStatus.EXTRACTION_CONFLICT,
    )
    other_field = ExtractedField(
        field_name=ComparisonFieldName.FREQUENCY_DURATION,
        value={"value": 12.0, "unit": "months", "kind": "recurrence", "calendar": "standard"},
        raw_surface_form="every 12 months",
        extraction_method="regex",
        extraction_status=ExtractionStatus.EXTRACTED,
        confidence=0.7,
    )
    comparison = compare_field(conflicted_field, other_field)
    assert comparison.outcome == ComparisonOutcome.UNKNOWN


# Fixture 8: a long, syntactically complex sentence still extracts multiple fields
# with valid, non-overlapping-nonsense spans.
def test_08_long_sentence_multiple_field_extractions() -> None:
    text = (
        "Class III widgets operating in Zone A must be inspected once every 6 months "
        "under Program Year 2024, unless the widget qualifies for Exemption D, except "
        "for widgets manufactured before January 2020, per Section 4 of the Handbook."
    )
    fields = extract_fields(text)
    extracted = {name: f for name, f in fields.items() if f.extraction_status == ExtractionStatus.EXTRACTED}
    assert len(extracted) >= 6
    for field_name, extracted_field in extracted.items():
        if extracted_field.source_span is not None:
            start, end = extracted_field.source_span
            assert 0 <= start < end <= len(text), field_name
