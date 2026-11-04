"""Bounded, deterministic multi-passage evidence-set construction --
docs/multi-passage-evidence-plan.md. Only attempted when no single packed item reaches
`direct_support_candidate` for a claim (single-passage support is always preferred).
Never asserts factual truth; an `EvidenceSet.relationship_status` is a candidate
classification, exactly like a single-passage `ClaimEvidenceComparison`.
"""

from __future__ import annotations

import itertools
import re
import time
import uuid
from dataclasses import dataclass

from wittgenstein.core.enums import (
    ClaimSupportCandidateStatus,
    ComparisonFieldName,
    ComparisonOutcome,
    ComponentRequiredness,
    ExtractionStatus,
    MismatchType,
)
from wittgenstein.ingestion.kv_cache import KVCache
from wittgenstein.review.field_comparison import compare_field, population_scope_conflict
from wittgenstein.review.field_extraction import extract_fields
from wittgenstein.review.semantic_provider import SemanticProvider, compare_with_semantic_provider
from wittgenstein.schemas.claim_comparison import ClaimEvidenceComparison, ExtractedField, SemanticComparisonResult
from wittgenstein.schemas.evidence_set import ClaimComponent, EvidenceSet, EvidenceSetConflict, EvidenceSetMember
from wittgenstein.schemas.trace import AnswerClaim, ContextItem

DEFAULT_MAX_SET_SIZE = 2

#: Same qualification-vs-hard-mismatch split as
#: review/relationship_classification.py -- reused, not redefined, to keep one
#: vocabulary for "this kind of mismatch narrows/weakens rather than contradicts."
_QUALIFICATION_MISMATCH_TYPES = {
    MismatchType.MODALITY_ESCALATION,
    MismatchType.MODALITY_WEAKENING,
    MismatchType.SCOPE_BROADENING,
    MismatchType.SCOPE_NARROWING,
    MismatchType.CONDITION_OMISSION,
    MismatchType.EXCEPTION_OMISSION,
}
#: Fields checked pairwise between candidate-set members -- docs/multi-passage-evidence-plan.md
#: §6/§4 ("do not infer a shared time period/version/jurisdiction unless explicitly
#: compatible"). ENTITY is checked too since two members describing different entities
#: must never be combined. PREDICATE is deliberately excluded: a rule passage and a
#: condition/exception/applicability passage naturally use different verbs (e.g. "must
#: be inspected" vs. "applies to") without that being a conflict -- that is exactly the
#: rule+condition composition case this layer exists to support, not a case to block.
#: POPULATION_SCOPE is excluded too and checked separately via `population_scope_conflict`,
#: which is axis-aware (a class restriction and a zone restriction are complementary,
#: not conflicting) unlike the generic claim-vs-source comparator. NUMERIC_VALUE is
#: deliberately excluded from this list too (unlike FREQUENCY_DURATION, whose
#: comparator is unit/kind-aware): a bare number carries no unit of its own, so two
#: members could state an unrelated pair of numbers (a percentage in one, a year in the
#: other) and be flagged as an explicit conflict purely by coincidence -- too
#: unreliable a signal to block composition on.
_COMPATIBILITY_FIELDS = [
    ComparisonFieldName.ENTITY,
    ComparisonFieldName.VERSION,
    ComparisonFieldName.TEMPORAL,
    ComparisonFieldName.JURISDICTION,
    ComparisonFieldName.FREQUENCY_DURATION,
]

#: A bare demonstrative/pronoun subject ("this requirement", "it") is not affirmative
#: evidence that a member describes a *different* entity from another member -- it is
#: simply unresolved coreference (the same honest limitation accepted for claim-vs-
#: candidate entity matching, e.g. the smoke-004 case). Treating it as a hard conflict
#: would block every rule+condition composition where the condition passage refers back
#: to the rule anaphorically, which is the common case in regulatory prose.
_ANAPHORIC_ENTITY_HEADS = {"it", "this", "that", "these", "those"}


def _is_anaphoric_entity(field: ExtractedField) -> bool:
    form = (field.raw_surface_form or "").strip().lower()
    if not form:
        return False
    return form.split()[0] in _ANAPHORIC_ENTITY_HEADS


@dataclass
class EvidenceSetConstructionMetrics:
    """A companion object, never folded into the trace schema -- same convention as
    `metrics/processing_metrics.py::ProcessingMetrics`.
    """

    attempted: bool = False
    candidate_pool_size: int = 0
    sets_considered: int = 0
    sets_discarded_redundant: int = 0
    sets_discarded_conflicting: int = 0
    construction_latency_seconds: float = 0.0
    skip_reason: str | None = None


def _requiredness_for(
    field_name: ComparisonFieldName, extraction_status: ExtractionStatus
) -> ComponentRequiredness:
    if extraction_status != ExtractionStatus.EXTRACTED:
        return ComponentRequiredness.NON_CRITICAL
    if field_name == ComparisonFieldName.CROSS_REFERENCE:
        return ComponentRequiredness.INFORMATIONAL
    return ComponentRequiredness.CRITICAL


def _slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def extract_claim_components(claim_text: str) -> list[ClaimComponent]:
    """Reuses `review/field_extraction.py::extract_fields` unchanged -- the claim
    "component" taxonomy is the same 17-field taxonomy the single-passage engine
    already extracts (docs/multi-passage-evidence-plan.md §2), not a second extractor.

    POPULATION_SCOPE is the one field decomposed further here (not at the single-
    passage field-extraction layer): a claim commonly asserts more than one
    independent scope qualifier at once (e.g. both a widget class and a zone), and
    each qualifier is its own critical, separately coverable component -- otherwise
    two passages that each confirm a different qualifier could never be recognized as
    jointly covering the claim's full asserted scope.
    """

    fields = extract_fields(claim_text)
    components: list[ClaimComponent] = []
    counter = 0
    for field_name, extracted in fields.items():
        if extracted.extraction_status == ExtractionStatus.ABSENT:
            continue
        if field_name == ComparisonFieldName.POPULATION_SCOPE:
            for scope_value in (extracted.value or {}).get("scopes", []):
                counter += 1
                components.append(
                    ClaimComponent(
                        component_id=f"COMP-{counter}-population_scope-{_slugify(scope_value)}",
                        component_type=field_name,
                        normalized_value={"scope": scope_value},
                        raw_surface_form=scope_value,
                        source_span=extracted.source_span,
                        extraction_method=extracted.extraction_method,
                        extraction_status=extracted.extraction_status,
                        confidence=extracted.confidence,
                        requiredness=ComponentRequiredness.CRITICAL,
                        dependencies=[],
                    )
                )
            continue
        counter += 1
        components.append(
            ClaimComponent(
                component_id=f"COMP-{counter}-{field_name.value}",
                component_type=field_name,
                normalized_value=extracted.value,
                raw_surface_form=extracted.raw_surface_form,
                source_span=extracted.source_span,
                extraction_method=extracted.extraction_method,
                extraction_status=extracted.extraction_status,
                confidence=extracted.confidence,
                requiredness=_requiredness_for(field_name, extracted.extraction_status),
                dependencies=[],
            )
        )
    return components


def _coverage_for_member(
    components: list[ClaimComponent],
    comparison: ClaimEvidenceComparison,
    member_fields: dict[ComparisonFieldName, ExtractedField],
) -> dict[str, ComparisonOutcome]:
    """Per-component coverage for one candidate-set member. POPULATION_SCOPE
    components are checked directly against this member's own extracted scope tokens
    (set membership), not against the whole-field single-passage FieldComparison
    outcome -- that outcome answers "does this member alone cover *every* scope axis
    the claim asserts," which is the wrong question here; a member covering only one
    of several asserted scope qualifiers should still get credit for that one.
    """

    scope_field = member_fields.get(ComparisonFieldName.POPULATION_SCOPE)
    member_scope_tokens = {s.lower() for s in ((scope_field.value or {}).get("scopes", []) if scope_field else [])}

    coverage: dict[str, ComparisonOutcome] = {}
    for component in components:
        if component.component_type == ComparisonFieldName.POPULATION_SCOPE:
            target = ((component.normalized_value or {}).get("scope") or "").lower()
            if not target:
                continue
            coverage[component.component_id] = (
                ComparisonOutcome.MATCH if target in member_scope_tokens else ComparisonOutcome.ABSENT
            )
            continue
        fc = next((f for f in comparison.field_comparisons if f.field_name == component.component_type), None)
        if fc is not None:
            coverage[component.component_id] = fc.outcome
    return coverage


def _check_member_compatibility(
    members: list[ContextItem],
    fields_by_member: dict[str, dict[ComparisonFieldName, ExtractedField]],
) -> list[EvidenceSetConflict]:
    """Pairwise-compares every pair of candidate-set members against each other
    (not against the claim) on entity/version/temporal/jurisdiction/frequency_duration,
    plus a dedicated axis-aware population_scope check -- any explicit MISMATCH is a
    conflict. A field
    absent on one or both members is never inferred to match; it stays ABSENT/UNKNOWN
    and is simply not a conflict (per docs/multi-passage-evidence-plan.md §4: only an
    *explicit* mismatch blocks composition, nothing is inferred). An unresolved
    pronoun/demonstrative entity ("this requirement") is likewise never treated as
    affirmative evidence of a *different* entity -- see `_is_anaphoric_entity`.
    """

    conflicts: list[EvidenceSetConflict] = []
    for item_a, item_b in itertools.combinations(members, 2):
        fields_a = fields_by_member[item_a.item_id]
        fields_b = fields_by_member[item_b.item_id]
        for field_name in _COMPATIBILITY_FIELDS:
            comparison = compare_field(fields_a[field_name], fields_b[field_name])
            if comparison.outcome != ComparisonOutcome.MISMATCH:
                continue
            if field_name == ComparisonFieldName.ENTITY and (
                _is_anaphoric_entity(fields_a[field_name]) or _is_anaphoric_entity(fields_b[field_name])
            ):
                continue
            conflicts.append(
                EvidenceSetConflict(
                    member_a_context_item_id=item_a.item_id,
                    member_b_context_item_id=item_b.item_id,
                    field_name=field_name,
                    explanation=comparison.explanation,
                )
            )
        scope_conflict = population_scope_conflict(
            fields_a[ComparisonFieldName.POPULATION_SCOPE], fields_b[ComparisonFieldName.POPULATION_SCOPE]
        )
        if scope_conflict is not None:
            conflicts.append(
                EvidenceSetConflict(
                    member_a_context_item_id=item_a.item_id,
                    member_b_context_item_id=item_b.item_id,
                    field_name=ComparisonFieldName.POPULATION_SCOPE,
                    explanation=scope_conflict,
                )
            )
    return conflicts


def _matched_component_ids(coverage: dict[str, ComparisonOutcome]) -> set[str]:
    return {cid for cid, outcome in coverage.items() if outcome == ComparisonOutcome.MATCH}


def _bounded_evidence_set_explanation(status: ClaimSupportCandidateStatus, detail: str = "") -> str:
    templates = {
        ClaimSupportCandidateStatus.COMPOSITE_SUPPORT_CANDIDATE: "No single passage supports the full claim; "
        "these passages together may cover its components.",
        ClaimSupportCandidateStatus.COMPOSITE_PARTIAL_SUPPORT_CANDIDATE: "The proposed evidence set covers most, "
        "but not all, of the claim's components.",
        ClaimSupportCandidateStatus.COMPOSITE_QUALIFICATION_REQUIRED: "The proposed evidence set supports a "
        "qualified version of the claim.",
        ClaimSupportCandidateStatus.COMPOSITE_CONFLICT_CANDIDATE: "The evidence set contains a possible conflict.",
        ClaimSupportCandidateStatus.COMPOSITE_UNRESOLVED: "A required component remains unresolved. Review the "
        "linked passages together before approving the claim.",
    }
    base = templates.get(status, "Review the linked passages together before approving the claim.")
    return f"{base} {detail}".strip() if detail else base


def construct_evidence_set(
    claim: AnswerClaim,
    packed_items: list[ContextItem],
    single_comparisons: list[ClaimEvidenceComparison],
    *,
    trace_id: str,
    max_set_size: int = DEFAULT_MAX_SET_SIZE,
) -> tuple[EvidenceSet | None, EvidenceSetConstructionMetrics]:
    """Returns (evidence_set_or_None, metrics). `evidence_set` is None only when
    single-passage direct support already exists (search is skipped entirely) or the
    claim has no critical components to compose around -- in every other case where
    search was attempted, an EvidenceSet is returned (possibly `composite_unresolved`
    or `composite_conflict_candidate`), so a reviewer always sees *why* composition
    did or did not succeed, per the smoke-005 requirement.
    """

    metrics = EvidenceSetConstructionMetrics()
    start = time.perf_counter()

    if any(
        c.relationship_status == ClaimSupportCandidateStatus.DIRECT_SUPPORT_CANDIDATE for c in single_comparisons
    ):
        metrics.skip_reason = "A single packed item already directly supports the claim."
        metrics.construction_latency_seconds = time.perf_counter() - start
        return None, metrics

    claim_fields = extract_fields(claim.text)
    components = extract_claim_components(claim.text)
    critical_ids = {c.component_id for c in components if c.requiredness == ComponentRequiredness.CRITICAL}
    if not critical_ids:
        metrics.skip_reason = "The claim has no critical components to compose evidence around."
        metrics.construction_latency_seconds = time.perf_counter() - start
        return None, metrics

    metrics.attempted = True
    metrics.candidate_pool_size = len(packed_items)
    comparisons_by_item = {c.context_item_id: c for c in single_comparisons}
    fields_by_item = {item.item_id: extract_fields(item.excerpt or "") for item in packed_items}
    coverage_by_item = {
        item.item_id: _coverage_for_member(
            components, comparisons_by_item[item.item_id], fields_by_item[item.item_id]
        )
        for item in packed_items
        if item.item_id in comparisons_by_item
    }
    individual_best_coverage = max(
        (len(_matched_component_ids(cov)) for cov in coverage_by_item.values()), default=0
    )

    best_valid: tuple[list[ContextItem], set[str]] | None = None
    first_conflict: tuple[list[ContextItem], list[EvidenceSetConflict], set[str]] | None = None

    items_by_id = {item.item_id: item for item in packed_items}
    for size in range(2, max_set_size + 1):
        # Deterministic ordering: packed_items is already rank-ordered; itertools
        # .combinations preserves that order, so iteration (and therefore tie-breaking
        # via "first found wins") is deterministic given the same input.
        for combo_ids in itertools.combinations([i.item_id for i in packed_items], size):
            metrics.sets_considered += 1
            combo = [items_by_id[cid] for cid in combo_ids]
            union_matched: set[str] = set()
            for cid in combo_ids:
                union_matched |= _matched_component_ids(coverage_by_item.get(cid, {}))

            if len(union_matched) <= individual_best_coverage:
                metrics.sets_discarded_redundant += 1
                continue

            conflicts = _check_member_compatibility(combo, fields_by_item)
            if conflicts:
                metrics.sets_discarded_conflicting += 1
                if first_conflict is None:
                    first_conflict = (combo, conflicts, union_matched)
                continue

            if best_valid is None or len(union_matched) > len(best_valid[1]):
                best_valid = (combo, union_matched)

        # Prefer the smallest set size that produced a *complete* result (every
        # critical component covered) -- but a merely-improving, still-incomplete
        # combo found at this size is not reason enough to stop searching a larger
        # size before it's even been tried. For the default max_set_size=2 this has no
        # effect at all (range(2, 3) is a single size regardless); it only changes
        # behavior for a caller that explicitly asks for a larger bound (currently
        # only the diagnostic-only size-3 search,
        # evidence_set_diagnostics/runner.py::_size3_diagnostic).
        if best_valid is not None and not (critical_ids - best_valid[1]):
            break

    metrics.construction_latency_seconds = time.perf_counter() - start

    if best_valid is not None:
        combo, union_matched = best_valid
        return (
            _build_evidence_set(
                claim,
                combo,
                components,
                critical_ids,
                union_matched,
                coverage_by_item,
                comparisons_by_item,
                fields_by_item,
                claim_fields,
                conflicts=[],
                trace_id=trace_id,
            ),
            metrics,
        )

    if first_conflict is not None:
        combo, conflicts, union_matched = first_conflict
        return (
            _build_evidence_set(
                claim,
                combo,
                components,
                critical_ids,
                union_matched,
                coverage_by_item,
                comparisons_by_item,
                fields_by_item,
                claim_fields,
                conflicts=conflicts,
                trace_id=trace_id,
            ),
            metrics,
        )

    # No combination ever added coverage beyond the best single candidate, and no
    # conflict was found either -- there simply isn't a plausible composite set.
    return (
        EvidenceSet(
            evidence_set_id=f"EVSET-{uuid.uuid4().hex[:12]}",
            trace_id=trace_id,
            answer_claim_id=claim.claim_id,
            member_context_item_ids=[],
            members=[],
            claim_components=components,
            covered_component_ids=[],
            unresolved_component_ids=sorted(critical_ids),
            relationship_status=ClaimSupportCandidateStatus.COMPOSITE_UNRESOLVED,
            construction_rationale="No combination of packed items covered more claim components than the "
            "best single candidate already did.",
            explanation=_bounded_evidence_set_explanation(ClaimSupportCandidateStatus.COMPOSITE_UNRESOLVED),
        ),
        metrics,
    )


#: A member asserting an explicit CONDITION/EXCEPTION the claim's own text never
#: mentions is not a gap in *coverage* (the claim didn't ask for that component, so it
#: is never added to `components`/`critical_ids`) -- but it is still reviewer-relevant:
#: the claim, taken alone, reads as unconditional, while the evidence set shows it is
#: actually narrower. This is the multi-passage analogue of single-passage Rule C
#: (qualification_required).
_QUALIFIER_INTRODUCING_FIELDS = (ComparisonFieldName.CONDITION, ComparisonFieldName.EXCEPTION)


def _member_introduced_qualifiers(
    combo: list[ContextItem],
    fields_by_item: dict[str, dict[ComparisonFieldName, ExtractedField]],
    claim_fields: dict[ComparisonFieldName, ExtractedField],
) -> list[str]:
    notes: list[str] = []
    for item in combo:
        member_fields = fields_by_item.get(item.item_id, {})
        for field_name in _QUALIFIER_INTRODUCING_FIELDS:
            member_field = member_fields.get(field_name)
            claim_field = claim_fields.get(field_name)
            if member_field is None or member_field.extraction_status != ExtractionStatus.EXTRACTED:
                continue
            if claim_field is not None and claim_field.extraction_status == ExtractionStatus.EXTRACTED:
                continue  # the claim already asserts this component; tracked as a normal component instead
            notes.append(
                f"{item.item_id} introduces a {field_name.value} not stated in the claim "
                f"({member_field.raw_surface_form!r})."
            )
    return notes


def _build_evidence_set(
    claim: AnswerClaim,
    combo: list[ContextItem],
    components: list[ClaimComponent],
    critical_ids: set[str],
    union_matched: set[str],
    coverage_by_item: dict[str, dict[str, ComparisonOutcome]],
    comparisons_by_item: dict[str, ClaimEvidenceComparison],
    fields_by_item: dict[str, dict[ComparisonFieldName, ExtractedField]],
    claim_fields: dict[ComparisonFieldName, ExtractedField],
    *,
    conflicts: list[EvidenceSetConflict],
    trace_id: str,
) -> EvidenceSet:
    unresolved_critical = critical_ids - union_matched
    redundant_ids = {
        cid
        for cid in union_matched
        if sum(1 for item in combo if coverage_by_item.get(item.item_id, {}).get(cid) == ComparisonOutcome.MATCH)
        > 1
    }

    # POPULATION_SCOPE is excluded here: its coverage is already tracked precisely at
    # the decomposed-component level above (`unresolved_critical`/`union_matched`), so
    # a member's own whole-field "doesn't cover every asserted scope axis" mismatch
    # would otherwise double-count as a qualification even when the *set* fully covers
    # the claim's scope -- every real multi-passage composition would then be
    # incorrectly downgraded, since no single member ever covers a compound scope alone.
    qualification_mismatches = [
        fc
        for item in combo
        for fc in comparisons_by_item[item.item_id].field_comparisons
        if fc.outcome == ComparisonOutcome.MISMATCH
        and fc.mismatch_type in _QUALIFICATION_MISMATCH_TYPES
        and fc.field_name != ComparisonFieldName.POPULATION_SCOPE
    ]
    introduced_qualifier_notes = _member_introduced_qualifiers(combo, fields_by_item, claim_fields)

    if conflicts:
        status = ClaimSupportCandidateStatus.COMPOSITE_CONFLICT_CANDIDATE
    elif unresolved_critical:
        status = ClaimSupportCandidateStatus.COMPOSITE_UNRESOLVED
    elif qualification_mismatches or introduced_qualifier_notes:
        status = ClaimSupportCandidateStatus.COMPOSITE_QUALIFICATION_REQUIRED
    else:
        non_critical_ids = {c.component_id for c in components} - critical_ids
        if non_critical_ids - union_matched:
            status = ClaimSupportCandidateStatus.COMPOSITE_PARTIAL_SUPPORT_CANDIDATE
        else:
            status = ClaimSupportCandidateStatus.COMPOSITE_SUPPORT_CANDIDATE

    members = [
        EvidenceSetMember(
            context_item_id=item.item_id,
            supplied_component_ids=sorted(
                cid
                for cid, outcome in coverage_by_item.get(item.item_id, {}).items()
                if outcome == ComparisonOutcome.MATCH
            ),
            field_comparisons=comparisons_by_item[item.item_id].field_comparisons,
            source_location=item.segment_id,
            selection_rationale="Included because it adds non-redundant component coverage beyond any single "
            "candidate alone.",
        )
        for item in combo
    ]

    detail_parts = []
    if unresolved_critical:
        detail_parts.append(f"{len(unresolved_critical)} required component(s) remain uncovered.")
    if conflicts:
        detail_parts.append(f"{len(conflicts)} conflict(s) detected between set members.")
    detail_parts.extend(introduced_qualifier_notes)

    return EvidenceSet(
        evidence_set_id=f"EVSET-{uuid.uuid4().hex[:12]}",
        trace_id=trace_id,
        answer_claim_id=claim.claim_id,
        member_context_item_ids=[item.item_id for item in combo],
        members=members,
        claim_components=components,
        covered_component_ids=sorted(union_matched),
        redundant_component_ids=sorted(redundant_ids),
        unresolved_component_ids=sorted(unresolved_critical),
        conflicts=conflicts,
        relationship_status=status,
        construction_rationale=f"Combined {len(combo)} packed item(s) cover {len(union_matched)} claim "
        f"component(s), more than any single candidate alone.",
        explanation=_bounded_evidence_set_explanation(status, " ".join(detail_parts)),
    )


def semantic_evidence_set_hint(
    text_a: str,
    text_b: str,
    *,
    provider: SemanticProvider | None = None,
    cache: KVCache | None = None,
    provider_name: str = "unconfigured",
    model_id: str = "unconfigured",
) -> SemanticComparisonResult:
    """Optional semantic/NLI hook for the evidence-set layer -- mirrors
    `review/semantic_provider.py::compare_with_semantic_provider` exactly (same
    provider protocol, same cache-first orchestration, same `NullSemanticProvider`
    default) so this layer never grows a second semantic-comparison implementation.

    `construct_evidence_set` never calls this -- deterministic, bounded field
    comparison is the entire default construction path, and this hook exists only for
    a future, explicitly-opted-into caller to use as an *additional* signal at one of
    three points docs/multi-passage-evidence-plan.md's OPTIONAL SEMANTIC LAYER section
    names: (1) semantic compatibility between two candidate-set members (pass their
    excerpts as `text_a`/`text_b`), (2) the semantic relation between two propositions
    being considered for the same set, or (3) semantic confirmation of a composed
    (qualified) condition against its source. In every case the result is a
    `SemanticComparisonResult` -- an additional signal that can raise a set's priority
    for reviewer attention, never a standalone factual judgment, and never required
    for deterministic construction.
    """

    return compare_with_semantic_provider(
        text_a, text_b, provider=provider, cache=cache, provider_name=provider_name, model_id=model_id
    )
