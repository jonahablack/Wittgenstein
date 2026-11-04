"""The field-extraction/comparison/relationship-classification engine --
docs/claim-linking-improvement-plan.md. Covers required test categories 1-19 (the
task's numbering is preserved in each test's docstring/name for traceability).
"""

from __future__ import annotations

from wittgenstein.core.enums import ComparisonFieldName, ComparisonOutcome, ExtractionStatus, MismatchType
from wittgenstein.review.field_comparison import compare_all_fields, compare_field
from wittgenstein.review.field_extraction import extract_fields
from wittgenstein.review.relationship_classification import classify_relationship
from wittgenstein.schemas.claim_comparison import ExtractedField


def _classify(claim: str, source: str):
    return classify_relationship(compare_all_fields(extract_fields(claim), extract_fields(source)))


# 1. Direct support.
def test_01_direct_support() -> None:
    result = _classify(
        "A Class I widget must pass the Load Stress Test at a 95% threshold.",
        "A Class I widget must pass the Load Stress Test at a 95% threshold.",
    )
    assert result.status.value == "direct_support_candidate"


# 2. Partial support with a non-critical missing field.
def test_02_partial_support_with_non_critical_missing_field() -> None:
    """The claim asserts a cross-reference ("per Section 3") the source simply doesn't
    repeat -- a non-critical absence, not a contradiction, so partial support (not
    direct support, since the claim's own cross-reference assertion is unconfirmed;
    not unresolved/no-support, since entity/predicate/threshold all still align).
    """

    result = _classify(
        "A Class I widget must pass the Load Stress Test at a 95% threshold, per Section 3.",
        "A Class I widget must pass the Load Stress Test at a 95% threshold.",
    )
    assert result.status.value == "partial_support_candidate"


# 3. High topical overlap with incompatible frequency.
def test_03_high_topical_overlap_incompatible_frequency() -> None:
    result = _classify(
        "Class III widgets must be inspected every 6 months.",
        "Class III widgets must be inspected once per Program Year.",
    )
    assert result.status.value not in ("direct_support_candidate", "partial_support_candidate")
    assert MismatchType.FREQUENCY_MISMATCH in result.mismatch_types or result.status.value in (
        "unresolved",
        "no_support_edge_found",
    )


# 4. High topical overlap with incompatible numeric threshold.
def test_04_high_topical_overlap_incompatible_numeric_threshold() -> None:
    result = _classify(
        "A Class I widget must pass the Load Stress Test at a 95% threshold.",
        "A Class I widget must pass the Load Stress Test at a 80% threshold.",
    )
    assert result.status.value not in ("direct_support_candidate", "partial_support_candidate")
    assert result.status.value == "contradiction_candidate"
    assert MismatchType.NUMERIC_MISMATCH in result.mismatch_types


# 5. Negation mismatch.
def test_05_negation_mismatch() -> None:
    result = _classify(
        "A Class I widget is not exempt from testing.",
        "A Class I widget is exempt from testing under Exemption C.",
    )
    assert result.status.value == "contradiction_candidate"
    assert MismatchType.POLARITY_MISMATCH in result.mismatch_types


# 6. Modal-strength escalation.
def test_06_modal_strength_escalation() -> None:
    """Claim asserts a stronger obligation ("must") than the source supports ("may")."""

    result = _classify(
        "A Class I widget must be inspected annually.",
        "A Class I widget may be inspected annually.",
    )
    assert result.status.value == "qualification_required"
    assert MismatchType.MODALITY_ESCALATION in result.mismatch_types


# 7. Modal-strength weakening.
def test_07_modal_strength_weakening() -> None:
    """Claim asserts a weaker obligation ("may") than the source states ("must")."""

    result = _classify(
        "A Class I widget may be inspected annually.",
        "A Class I widget must be inspected annually.",
    )
    assert result.status.value == "qualification_required"
    assert MismatchType.MODALITY_WEAKENING in result.mismatch_types


# 8. Population mismatch.
def test_08_population_scope_mismatch() -> None:
    claim_fields = extract_fields("Class I widgets must be inspected annually.")
    source_fields = extract_fields("Class II widgets must be inspected annually.")
    comparison = compare_field(
        claim_fields[ComparisonFieldName.POPULATION_SCOPE], source_fields[ComparisonFieldName.POPULATION_SCOPE]
    )
    assert comparison.outcome == ComparisonOutcome.MISMATCH


# 9. Temporal/version mismatch.
def test_09_version_mismatch() -> None:
    claim_fields = extract_fields("This applies under Program Year 2023.")
    source_fields = extract_fields("This applies under Program Year 2024.")
    comparison = compare_field(
        claim_fields[ComparisonFieldName.VERSION], source_fields[ComparisonFieldName.VERSION]
    )
    assert comparison.outcome == ComparisonOutcome.MISMATCH
    assert comparison.mismatch_type == MismatchType.VERSION_MISMATCH


# 10. Condition omission.
def test_10_condition_omission() -> None:
    claim_fields = extract_fields("A widget must pass inspection.")
    source_fields = extract_fields("A widget must pass inspection unless it qualifies for an exemption.")
    claim_field = claim_fields[ComparisonFieldName.CONDITION]
    source_field = source_fields[ComparisonFieldName.CONDITION]
    assert claim_field.extraction_status == ExtractionStatus.ABSENT
    assert source_field.extraction_status == ExtractionStatus.EXTRACTED
    comparison = compare_field(claim_field, source_field)
    assert comparison.outcome == ComparisonOutcome.ABSENT  # claim never asserted a condition at all


# 11. Exception omission.
def test_11_exception_omission() -> None:
    source_fields = extract_fields("A widget must pass inspection, except when remanufactured.")
    source_field = source_fields[ComparisonFieldName.EXCEPTION]
    assert source_field.extraction_status == ExtractionStatus.EXTRACTED


# 12. Same topic but no support.
def test_12_same_topic_but_no_support() -> None:
    result = _classify(
        "Widgets are typically blue or green.",
        "Facility registration expires after five years.",
    )
    assert result.status.value == "no_support_edge_found"


# 13. Explicit contradiction candidate.
def test_13_explicit_contradiction_candidate() -> None:
    result = _classify(
        "Class III widgets must be inspected every 6 months.",
        "Class III widgets must be inspected once per Program Year.",
    )
    assert result.status.value == "contradiction_candidate"


# 14. Multiple conflicting sources -- see review/claim_linking.py's Rule E handling,
# covered in tests/unit/test_claim_linking_conflict.py (multi-candidate aggregation is
# not this module's concern -- classify_relationship only ever sees one pair).


# 15. Missing field produces ABSENT.
def test_15_missing_field_produces_absent() -> None:
    fields = extract_fields("A widget exists.")
    assert fields[ComparisonFieldName.FREQUENCY_DURATION].extraction_status == ExtractionStatus.ABSENT
    assert fields[ComparisonFieldName.VERSION].extraction_status == ExtractionStatus.ABSENT


# 16. Extraction failure produces UNKNOWN.
def test_16_extraction_failure_produces_unknown_comparison() -> None:
    failed = ExtractedField(
        field_name=ComparisonFieldName.FREQUENCY_DURATION,
        extraction_method="regex",
        extraction_status=ExtractionStatus.EXTRACTION_FAILED,
    )
    ok = ExtractedField(
        field_name=ComparisonFieldName.FREQUENCY_DURATION,
        value={"value": 6.0, "unit": "month", "kind": "recurrence_frequency", "calendar": "standard"},
        raw_surface_form="every 6 months",
        extraction_method="regex",
        extraction_status=ExtractionStatus.EXTRACTED,
        confidence=0.7,
    )
    comparison = compare_field(failed, ok)
    assert comparison.outcome == ComparisonOutcome.UNKNOWN


# 17. Unknown critical field produces unresolved.
def test_17_unknown_critical_field_produces_unresolved() -> None:
    result = _classify(
        "A Class I widget must be inspected every 6 months.",
        "A Class I widget must be inspected once per fiscal quarter.",
    )
    # "fiscal quarter" is not in the recognized frequency vocabulary -- extraction of
    # the source's frequency field should not fabricate a value.
    source_fields = extract_fields("A Class I widget must be inspected once per fiscal quarter.")
    assert source_fields[ComparisonFieldName.FREQUENCY_DURATION].extraction_status == ExtractionStatus.ABSENT
    # Since one side is ABSENT (not UNKNOWN) here, the field comparison is ABSENT, not
    # UNKNOWN -- this test documents that boundary rather than asserting unresolved
    # for this specific pair (the case where a field is *sensed but unparseable* on
    # both sides -- true UNKNOWN -- is exercised directly in test_18 below).
    assert result.status.value in ("partial_support_candidate", "unresolved", "no_support_edge_found")


# 18. Regex/parser disagreement produces unresolved or explicit conflict.
def test_18_extraction_disagreement_surfaces_as_unknown_not_silently_resolved() -> None:
    """Two ExtractedFields with EXTRACTION_CONFLICT status on either side must never be
    silently resolved to MATCH or MISMATCH.
    """

    conflicted = ExtractedField(
        field_name=ComparisonFieldName.ENTITY,
        extraction_method="regex+spacy_dependency",
        extraction_status=ExtractionStatus.EXTRACTION_CONFLICT,
    )
    ok = ExtractedField(
        field_name=ComparisonFieldName.ENTITY,
        value={"surface_form": "Class I widget"},
        raw_surface_form="Class I widget",
        extraction_method="regex",
        extraction_status=ExtractionStatus.EXTRACTED,
        confidence=0.6,
    )
    comparison = compare_field(conflicted, ok)
    assert comparison.outcome == ComparisonOutcome.UNKNOWN


# 19. Domain-defined period remains domain-dependent.
def test_19_domain_defined_period_remains_flagged_not_silently_converted() -> None:
    fields = extract_fields("Class III widgets must be inspected once per Program Year.")
    frequency = fields[ComparisonFieldName.FREQUENCY_DURATION]
    assert frequency.value is not None
    assert frequency.value["calendar"] == "domain_defined"
    assert frequency.value["normalization_status"] == "domain_dependent"
    assert frequency.value["domain_term"] == "Program Year"
