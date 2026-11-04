"""The four-state field-comparison lattice and mismatch classification --
docs/claim-linking-improvement-plan.md §3, §4.
"""

from __future__ import annotations

from wittgenstein.core.enums import ComparisonFieldName, ComparisonOutcome, ExtractionStatus, MismatchType
from wittgenstein.review.normalization import approximate_months
from wittgenstein.schemas.claim_comparison import ExtractedField, FieldComparison

#: Ratio (larger-over-smaller approximate-months) above which two frequency/duration
#: values are treated as MISMATCH rather than UNKNOWN, even when one side's period is
#: domain-defined (e.g. "Program Year") and therefore only approximately convertible.
#: Conservative and documented, not a claim of exact equivalence -- see
#: docs/claim-linking-improvement-plan.md's NORMALIZATION section on "Program Year."
_FREQUENCY_MISMATCH_RATIO_THRESHOLD = 1.5

_MISMATCH_TYPE_BY_FIELD: dict[ComparisonFieldName, MismatchType] = {
    ComparisonFieldName.FREQUENCY_DURATION: MismatchType.FREQUENCY_MISMATCH,
    ComparisonFieldName.NUMERIC_VALUE: MismatchType.NUMERIC_MISMATCH,
    ComparisonFieldName.UNIT: MismatchType.UNIT_MISMATCH,
    ComparisonFieldName.COMPARATOR: MismatchType.COMPARATOR_MISMATCH,
    ComparisonFieldName.POLARITY: MismatchType.POLARITY_MISMATCH,
    ComparisonFieldName.TEMPORAL: MismatchType.TEMPORAL_MISMATCH,
    ComparisonFieldName.VERSION: MismatchType.VERSION_MISMATCH,
    ComparisonFieldName.JURISDICTION: MismatchType.JURISDICTION_MISMATCH,
    ComparisonFieldName.ENTITY: MismatchType.ENTITY_BINDING_MISMATCH,
    ComparisonFieldName.PREDICATE: MismatchType.PREDICATE_MISMATCH,
    ComparisonFieldName.OBJECT_VALUE: MismatchType.VALUE_MISMATCH,
}


#: Comparators return (outcome, explanation, confidence). Confidence here is the
#: comparator's own confidence in its verdict given both sides' parsed values -- a
#: distinct concept from `ExtractedField.confidence` (how sure the extractor was it
#: found the field at all). Conflating the two would let a domain-dependent but
#: still-clearly-mismatched value (e.g. the frequency field in the smoke-003 case)
#: fall through to UNRESOLVED just because one side's raw extraction confidence was
#: low, even though the comparator itself is reasonably sure about the verdict.
_ComparatorResult = tuple[ComparisonOutcome, str, float | None]


def _compare_generic(claim: ExtractedField, source: ExtractedField) -> _ComparatorResult:
    """Fallback comparator for fields without dedicated comparison logic: exact
    (case-insensitive) surface-form match after conservative whitespace normalization.

    Unlike the dedicated comparators above (which reason about their field and set
    their own confidence), this fallback has no field-specific basis for judging its
    own reliability -- its confidence is derived from the underlying extractions'
    confidence instead. This matters concretely: `object_value`'s extraction (a "rest
    of the sentence" heuristic) is deliberately low-confidence, and without this, a
    near-identical claim/source pair that merely has extra trailing text (e.g. ", per
    Section 3.") would otherwise register as a same-confidence "hard" mismatch as a
    genuinely reliable field like `entity`.
    """

    claim_form = (claim.raw_surface_form or "").strip().lower()
    source_form = (source.raw_surface_form or "").strip().lower()
    base_confidence = (
        min(claim.confidence, source.confidence)
        if claim.confidence is not None and source.confidence is not None
        else 0.4
    )
    if claim_form == source_form:
        return (
            ComparisonOutcome.MATCH,
            f"Both sides express {claim.field_name.value} as {claim_form!r}.",
            min(base_confidence + 0.1, 0.9),
        )
    return (
        ComparisonOutcome.MISMATCH,
        f"Claim expresses {claim.field_name.value} as {claim_form!r}; source expresses it as {source_form!r}.",
        base_confidence,
    )


def _compare_frequency_duration(claim: ExtractedField, source: ExtractedField) -> _ComparatorResult:
    claim_value, source_value = claim.value, source.value
    if not claim_value or not source_value:
        return ComparisonOutcome.UNKNOWN, "Frequency/duration values present but could not be compared.", None

    if claim_value.get("kind") != source_value.get("kind"):
        return (
            ComparisonOutcome.UNKNOWN,
            f"Claim expresses a {claim_value.get('kind')} while source expresses a {source_value.get('kind')} -- "
            "not directly comparable kinds.",
            None,
        )

    class _TemporalLike:
        def __init__(self, d: dict) -> None:
            self.value = d.get("value")
            self.unit = d.get("unit")
            self.calendar = d.get("calendar")

    claim_months = approximate_months(_TemporalLike(claim_value))  # type: ignore[arg-type]
    source_months = approximate_months(_TemporalLike(source_value))  # type: ignore[arg-type]
    if claim_months is None or source_months is None:
        return (
            ComparisonOutcome.UNKNOWN,
            "Could not convert one or both frequency/duration values for comparison.",
            None,
        )

    ratio = (
        max(claim_months, source_months) / min(claim_months, source_months)
        if min(claim_months, source_months)
        else None
    )
    if ratio is None:
        return ComparisonOutcome.UNKNOWN, "Frequency/duration comparison could not be computed.", None

    domain_dependent = (
        claim_value.get("calendar") == "domain_defined" or source_value.get("calendar") == "domain_defined"
    )
    approx_note = (
        " (one side is a domain-defined period, e.g. 'Program Year' -- compared only approximately, "
        "never assumed equal to a calendar year)"
        if domain_dependent
        else ""
    )

    if ratio >= _FREQUENCY_MISMATCH_RATIO_THRESHOLD:
        # The ratio itself is large enough that even a generous margin for the
        # domain-defined side's uncertain exact boundaries doesn't erase the
        # mismatch -- confident, though slightly less so than a standard-calendar
        # comparison, hence 0.6 vs 0.75.
        return (
            ComparisonOutcome.MISMATCH,
            f"Claim implies roughly every {claim_months:.1f} months; source implies roughly every "
            f"{source_months:.1f} months -- a possible frequency mismatch was detected.{approx_note}",
            0.6 if domain_dependent else 0.75,
        )
    if domain_dependent:
        return (
            ComparisonOutcome.UNKNOWN,
            f"Claim ({claim_months:.1f} months) and source ({source_months:.1f} months, domain-defined period) "
            f"are close enough that the comparison is not confident.{approx_note}",
            None,
        )
    return (
        ComparisonOutcome.MATCH,
        f"Both sides imply roughly every {claim_months:.1f} months.",
        0.7,
    )


def _compare_numeric_value(claim: ExtractedField, source: ExtractedField) -> _ComparatorResult:
    claim_num = (claim.value or {}).get("value")
    source_num = (source.value or {}).get("value")
    if claim_num is None or source_num is None:
        return ComparisonOutcome.UNKNOWN, "Numeric values present but could not be compared.", None
    if claim_num == source_num:
        return ComparisonOutcome.MATCH, f"Both sides state the numeric value {claim_num}.", 0.75
    return ComparisonOutcome.MISMATCH, f"Claim states {claim_num}; source states {source_num}.", 0.75


#: Scope tokens (from `_POPULATION_SCOPE_RE`) are grouped by axis before comparison,
#: since a claim commonly asserts more than one independent scope qualifier at once
#: (e.g. both a widget class and a zone) and a single passage may confirm only one of
#: them -- see `_compare_population_scope` and `population_scope_conflict` below.
_SCOPE_AXIS_PREFIXES = ("class", "zone", "region", "district", "area")


def _scope_axis(token: str) -> str:
    lowered = token.strip().lower()
    for prefix in _SCOPE_AXIS_PREFIXES:
        if lowered.startswith(prefix):
            return prefix
    return "general"


def _group_scopes_by_axis(scopes: list[str]) -> dict[str, set[str]]:
    grouped: dict[str, set[str]] = {}
    for token in scopes:
        grouped.setdefault(_scope_axis(token), set()).add(token.strip().lower())
    return grouped


def _compare_population_scope(claim: ExtractedField, source: ExtractedField) -> _ComparatorResult:
    """Population/scope tokens are grouped by axis (widget class, zone, region,
    district, area, or an unqualified "general" quantifier like "all widgets") before
    comparison, since a claim commonly asserts more than one independent scope
    qualifier at once and a single passage may confirm only one of them. A shared axis
    with disjoint values is an explicit, conflicting scope claim (MISMATCH). An axis
    the claim asserts but the source simply never mentions is not a conflict, only an
    omission -- still MISMATCH here (a single passage is never assumed to cover a scope
    axis it never addresses), but classified as a qualification-type mismatch, not a
    contradiction; the evidence-set layer (review/evidence_set.py), not this
    single-field comparison, is what checks whether a *second* passage supplies the
    missing axis (docs/multi-passage-evidence-plan.md).
    """

    claim_scopes = (claim.value or {}).get("scopes", [])
    source_scopes = (source.value or {}).get("scopes", [])
    if not claim_scopes or not source_scopes:
        return ComparisonOutcome.UNKNOWN, "Population/scope present but could not be compared.", None

    claim_by_axis = _group_scopes_by_axis(claim_scopes)
    source_by_axis = _group_scopes_by_axis(source_scopes)
    shared_axes = sorted(set(claim_by_axis) & set(source_by_axis))
    conflicting_axes = [axis for axis in shared_axes if not (claim_by_axis[axis] & source_by_axis[axis])]
    if conflicting_axes:
        axis = conflicting_axes[0]
        return (
            ComparisonOutcome.MISMATCH,
            f"Claim asserts {axis} scope {sorted(claim_by_axis[axis])}; source asserts a conflicting "
            f"{axis} scope {sorted(source_by_axis[axis])}.",
            0.6,
        )

    covered_axes = {axis for axis in shared_axes if claim_by_axis[axis] & source_by_axis[axis]}
    if covered_axes == set(claim_by_axis):
        return (
            ComparisonOutcome.MATCH,
            f"Source confirms every scope axis the claim asserts ({sorted(covered_axes)}).",
            0.6,
        )
    missing_axes = sorted(set(claim_by_axis) - covered_axes)
    return (
        ComparisonOutcome.MISMATCH,
        f"Source does not address the claim's asserted {', '.join(missing_axes)} scope; a single passage "
        "is never assumed to cover a scope axis it never mentions.",
        0.55,
    )


def population_scope_conflict(field_a: ExtractedField, field_b: ExtractedField) -> str | None:
    """Cross-member (not claim-vs-source) scope compatibility, used by
    `review/evidence_set.py` when checking whether two candidate-set members are safe
    to combine. Two passages are only incompatible if they make an explicit, disjoint
    assertion about the *same* scope axis (e.g. both name a widget class, but different
    ones); passages addressing different axes (one a class restriction, the other a
    zone restriction) are complementary, not conflicting -- that is exactly the
    two-passage composition case docs/multi-passage-evidence-plan.md is built around,
    so this must not reuse `_compare_population_scope`'s claim-vs-source "does the
    source cover every axis" logic, which would otherwise flag every complementary pair
    as a conflict.
    """

    scopes_a = (field_a.value or {}).get("scopes", [])
    scopes_b = (field_b.value or {}).get("scopes", [])
    if not scopes_a or not scopes_b:
        return None
    by_axis_a = _group_scopes_by_axis(scopes_a)
    by_axis_b = _group_scopes_by_axis(scopes_b)
    for axis in sorted(set(by_axis_a) & set(by_axis_b)):
        if not (by_axis_a[axis] & by_axis_b[axis]):
            return (
                f"One passage asserts {axis} scope {sorted(by_axis_a[axis])}; the other asserts a "
                f"conflicting {axis} scope {sorted(by_axis_b[axis])}."
            )
    return None


def _compare_comparator(claim: ExtractedField, source: ExtractedField) -> _ComparatorResult:
    claim_cmp = (claim.value or {}).get("comparator")
    source_cmp = (source.value or {}).get("comparator")
    if claim_cmp is None or source_cmp is None:
        return ComparisonOutcome.UNKNOWN, "Comparator present but could not be compared.", None
    if claim_cmp == source_cmp:
        return ComparisonOutcome.MATCH, f"Both sides use a {claim_cmp!r} comparator.", 0.65
    return (
        ComparisonOutcome.MISMATCH,
        f"Claim uses a {claim_cmp!r} comparator; source uses a {source_cmp!r} comparator.",
        0.65,
    )


def _compare_polarity(claim: ExtractedField, source: ExtractedField) -> _ComparatorResult:
    claim_pol = (claim.value or {}).get("polarity")
    source_pol = (source.value or {}).get("polarity")
    if claim_pol is None or source_pol is None:
        return ComparisonOutcome.UNKNOWN, "Polarity could not be determined on one or both sides.", None
    if claim_pol == source_pol:
        return ComparisonOutcome.MATCH, f"Both sides are {claim_pol}.", 0.65
    return (
        ComparisonOutcome.MISMATCH,
        f"Claim is {claim_pol} while source is {source_pol} -- a possible polarity conflict was detected.",
        0.65,
    )


def _compare_modality(claim: ExtractedField, source: ExtractedField) -> _ComparatorResult:
    claim_value = claim.value or {}
    source_value = source.value or {}
    claim_strength = claim_value.get("strength")
    source_strength = source_value.get("strength")
    if claim_strength is None or source_strength is None:
        return ComparisonOutcome.UNKNOWN, "Modality strength could not be determined on one or both sides.", None
    if claim_strength == source_strength:
        return ComparisonOutcome.MATCH, "Claim and source express the same modal strength.", 0.6
    if claim_strength > source_strength:
        return (
            ComparisonOutcome.MISMATCH,
            f"Claim asserts a stronger obligation ({claim_value.get('modal')}) than the source "
            f"({source_value.get('modal')}) supports -- modality escalation.",
            0.6,
        )
    return (
        ComparisonOutcome.MISMATCH,
        f"Claim asserts a weaker obligation ({claim_value.get('modal')}) than the source "
        f"({source_value.get('modal')}) states -- modality weakening.",
        0.6,
    )


def _singularize(word: str) -> str:
    """A conservative, single-rule pluralization strip (trailing 's', not 'ies'/'es'
    irregulars) -- not a real lemmatizer, just enough to stop "Class A finding" and
    "Class A findings" (a genuinely common singular-claim-vs-plural-source pattern in
    regulatory prose) from registering as an entity_binding_mismatch.
    """

    return word[:-1] if word.endswith("s") and not word.endswith("ss") else word


def _compare_entity(claim: ExtractedField, source: ExtractedField) -> _ComparatorResult:
    claim_form = (claim.raw_surface_form or "").strip().lower()
    source_form = (source.raw_surface_form or "").strip().lower()
    claim_normalized = " ".join(_singularize(w) for w in claim_form.split())
    source_normalized = " ".join(_singularize(w) for w in source_form.split())
    if claim_normalized == source_normalized:
        return ComparisonOutcome.MATCH, f"Both sides refer to {claim_form!r} (singular/plural-normalized).", 0.65
    return (
        ComparisonOutcome.MISMATCH,
        f"Claim refers to {claim_form!r}; source refers to {source_form!r}.",
        0.55,
    )


def _mismatch_type_for(
    field_name: ComparisonFieldName, claim: ExtractedField, source: ExtractedField
) -> MismatchType:
    if field_name == ComparisonFieldName.MODALITY:
        claim_strength = (claim.value or {}).get("strength") or 0
        source_strength = (source.value or {}).get("strength") or 0
        return (
            MismatchType.MODALITY_ESCALATION
            if claim_strength > source_strength
            else MismatchType.MODALITY_WEAKENING
        )
    if field_name == ComparisonFieldName.POPULATION_SCOPE:
        return MismatchType.SCOPE_BROADENING
    if field_name == ComparisonFieldName.CONDITION:
        return MismatchType.CONDITION_OMISSION
    if field_name == ComparisonFieldName.EXCEPTION:
        return MismatchType.EXCEPTION_OMISSION
    return _MISMATCH_TYPE_BY_FIELD.get(field_name, MismatchType.VALUE_MISMATCH)


_DEDICATED_COMPARATORS = {
    ComparisonFieldName.FREQUENCY_DURATION: _compare_frequency_duration,
    ComparisonFieldName.NUMERIC_VALUE: _compare_numeric_value,
    ComparisonFieldName.COMPARATOR: _compare_comparator,
    ComparisonFieldName.POLARITY: _compare_polarity,
    ComparisonFieldName.MODALITY: _compare_modality,
    ComparisonFieldName.ENTITY: _compare_entity,
    ComparisonFieldName.POPULATION_SCOPE: _compare_population_scope,
}


def compare_field(claim: ExtractedField, source: ExtractedField) -> FieldComparison:
    """Compares one field between a claim and a candidate excerpt, returning the
    four-state outcome plus (for MISMATCH) a classified mismatch type.
    """

    field_name = claim.field_name
    claim_absent = claim.extraction_status == ExtractionStatus.ABSENT
    source_absent = source.extraction_status == ExtractionStatus.ABSENT
    claim_failed = claim.extraction_status in (
        ExtractionStatus.EXTRACTION_FAILED,
        ExtractionStatus.EXTRACTION_CONFLICT,
    )
    source_failed = source.extraction_status in (
        ExtractionStatus.EXTRACTION_FAILED,
        ExtractionStatus.EXTRACTION_CONFLICT,
    )

    if claim_absent or source_absent:
        return FieldComparison(
            field_name=field_name,
            claim_value=claim.value,
            source_value=source.value,
            claim_span=claim.source_span,
            source_span=source.source_span,
            outcome=ComparisonOutcome.ABSENT,
            extraction_method=claim.extraction_method,
            confidence=None,
            explanation=f"{field_name.value} is not expressed on at least one side.",
        )

    if claim_failed or source_failed:
        return FieldComparison(
            field_name=field_name,
            claim_value=claim.value,
            source_value=source.value,
            claim_span=claim.source_span,
            source_span=source.source_span,
            outcome=ComparisonOutcome.UNKNOWN,
            extraction_method=claim.extraction_method,
            confidence=None,
            explanation=f"{field_name.value} extraction failed or conflicted on at least one side.",
        )

    comparator = _DEDICATED_COMPARATORS.get(field_name, _compare_generic)
    outcome, explanation, confidence = comparator(claim, source)

    mismatch_type = (
        _mismatch_type_for(field_name, claim, source) if outcome == ComparisonOutcome.MISMATCH else None
    )

    return FieldComparison(
        field_name=field_name,
        claim_value=claim.value,
        source_value=source.value,
        claim_span=claim.source_span,
        source_span=source.source_span,
        outcome=outcome,
        mismatch_type=mismatch_type,
        extraction_method=claim.extraction_method,
        normalization_method="review.normalization"
        if field_name == ComparisonFieldName.FREQUENCY_DURATION
        else None,
        confidence=confidence,
        explanation=explanation,
    )


def compare_all_fields(
    claim_fields: dict[ComparisonFieldName, ExtractedField],
    source_fields: dict[ComparisonFieldName, ExtractedField],
) -> list[FieldComparison]:
    return [
        compare_field(claim_fields[name], source_fields[name]) for name in claim_fields if name in source_fields
    ]
