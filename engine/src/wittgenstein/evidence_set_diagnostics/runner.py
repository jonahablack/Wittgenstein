"""The real-corpus evidence-set diagnostic runner: load cases -> resolve corpus/
manifest -> run imported-answer mode -> re-derive cross-reference/conflict/size-3
diagnostics -> write a per-case diagnostic report and a manual-labels template
(docs/evidence-set-real-corpus-diagnostics-plan.md).

Reuses `smoke_test/corpus_registry.py::resolve_corpus` and
`smoke_test/manifest_registry.py::load_manifests` unchanged -- no second corpus/
manifest resolution implementation. Never calls an LLM (imported_answer's `llm_client`
is never passed here, matching the smoke-test harness's default no-LLM run).
Deterministic: two runs of the same case produce the same diagnostic content, modulo
the fields already known to legitimately vary (uuids, timestamps, latency).
"""

from __future__ import annotations

import json
import math
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

from wittgenstein.core.enums import (
    ClaimSupportCandidateStatus,
    ConflictQualityDiagnosticLabel,
    CrossReferenceClosureDiagnosticLabel,
    EvidenceSetSizingDiagnosticLabel,
    ExtractionQualityDiagnosticLabel,
    ReviewerWorkflowDiagnosticLabel,
)
from wittgenstein.ingestion.corpus_index import index_corpus
from wittgenstein.review.conflict_diagnostics import ConflictFieldExplanation, explain_conflicts
from wittgenstein.review.cross_reference_diagnostics import (
    CrossReferenceMarker,
    detect_cross_reference_markers,
    marker_to_dict,
)
from wittgenstein.review.evidence_set import construct_evidence_set
from wittgenstein.review.imported_answer import ImportedAnswerResult, import_answer
from wittgenstein.schemas.smoke_test import SmokeTestCase, SmokeTestCaseFile
from wittgenstein.smoke_test.corpus_registry import resolve_corpus
from wittgenstein.smoke_test.manifest_registry import SmokeTestManifestError, load_manifests

#: Actual (not merely estimated) diagnostic size-3 search is only executed when the
#: pool's C(pool_size, 3) combination count is at or below this bound -- "only for
#: small diagnostic cases," per the milestone brief. Above it, only the closed-form
#: estimate is reported.
MAX_DIAGNOSTIC_SIZE3_COMBINATIONS = 500


@dataclass
class Size3Diagnostic:
    claim_id: str
    default_relationship_status: str | None
    uncovered_critical_component_ids: list[str]
    candidate_pool_size: int
    size3_combination_count: int
    estimated_size3_latency_seconds: float | None
    size3_search_run: bool
    size3_relationship_status: str | None
    size3_member_context_item_ids: list[str] | None
    warning: str | None


@dataclass
class DiagnosticCaseResult:
    case: SmokeTestCase
    imported_answer: ImportedAnswerResult
    cross_reference_markers: dict[str, list[CrossReferenceMarker]] = field(default_factory=dict)
    conflict_explanations: dict[str, list[ConflictFieldExplanation]] = field(default_factory=dict)
    size3_diagnostics: dict[str, Size3Diagnostic] = field(default_factory=dict)
    processing_time_seconds: float = 0.0


def _size3_diagnostic(
    claim,
    packed_items,
    single_comparisons,
    default_evidence_set,
    default_metrics,
    *,
    run_size3: bool,
    trace_id: str,
) -> Size3Diagnostic | None:
    if not default_metrics.attempted:
        return None  # construction wasn't attempted at default size 2 -- nothing to diagnose

    pool_size = default_metrics.candidate_pool_size
    combo_count_3 = math.comb(pool_size, 3) if pool_size >= 3 else 0
    per_combo_cost = (
        default_metrics.construction_latency_seconds / default_metrics.sets_considered
        if default_metrics.sets_considered
        else None
    )
    estimated_latency = per_combo_cost * combo_count_3 if per_combo_cost is not None else None

    size3_search_run = False
    size3_status: str | None = None
    size3_members: list[str] | None = None
    warning: str | None = None
    already_fully_supported = (
        default_evidence_set is not None
        and default_evidence_set.relationship_status == ClaimSupportCandidateStatus.COMPOSITE_SUPPORT_CANDIDATE
    )

    if run_size3 and combo_count_3 > 0 and not already_fully_supported:
        if combo_count_3 <= MAX_DIAGNOSTIC_SIZE3_COMBINATIONS:
            size3_set, _size3_metrics = construct_evidence_set(
                claim, packed_items, single_comparisons, trace_id=trace_id, max_set_size=3
            )
            size3_search_run = True
            if size3_set is not None:
                size3_status = size3_set.relationship_status.value
                size3_members = size3_set.member_context_item_ids
            warning = (
                f"Diagnostic-only size-3 search executed ({combo_count_3} combination(s) considered) -- "
                "never used in normal demo/review flow, never the default max_set_size."
            )
        else:
            warning = (
                f"Diagnostic-only size-3 search skipped: {combo_count_3} combinations exceeds the "
                f"diagnostic safety bound ({MAX_DIAGNOSTIC_SIZE3_COMBINATIONS}); only the closed-form "
                "estimate below is reported."
            )

    return Size3Diagnostic(
        claim_id=claim.claim_id,
        default_relationship_status=(
            default_evidence_set.relationship_status.value if default_evidence_set else None
        ),
        uncovered_critical_component_ids=(
            default_evidence_set.unresolved_component_ids if default_evidence_set else []
        ),
        candidate_pool_size=pool_size,
        size3_combination_count=combo_count_3,
        estimated_size3_latency_seconds=estimated_latency,
        size3_search_run=size3_search_run,
        size3_relationship_status=size3_status,
        size3_member_context_item_ids=size3_members,
        warning=warning,
    )


def run_diagnostic_case(
    case: SmokeTestCase,
    manifests: dict,
    *,
    diagnostic_max_set_size: int | None = None,
    top_k: int | None = None,
    token_budget: int | None = None,
) -> DiagnosticCaseResult:
    """Runs one case through `import_answer` (default `max_set_size=2`, unchanged),
    then re-derives cross-reference/conflict/size-3 diagnostics read-only.
    `diagnostic_max_set_size=3` opts a case into the (bounded, explicitly warned) size-3
    diagnostic search -- it never changes `import_answer`'s own construction, which
    always uses the library default. `top_k`/`token_budget` default to `None`
    (unchanged behavior -- `import_answer` uses its own defaults); passing explicit
    values is additive, used by `wittgenstein fixture run` to honor a manifest's own
    declared `retrieval_manifest.candidate_depth`/`packing_manifest.evidence_budget_tokens`
    (docs/controlled-synthetic-corpus-plan.md §11) -- otherwise (like every existing
    caller of `import_answer`) a manifest's packing/retrieval-depth fields stay
    descriptive only and are never silently assumed to already be applied.
    """

    if case.pipeline_manifest_id not in manifests:
        raise SmokeTestManifestError(
            f"Case {case.case_id!r} references unknown pipeline_manifest_id {case.pipeline_manifest_id!r}."
        )
    manifest = manifests[case.pipeline_manifest_id]
    corpus_text = resolve_corpus(case.corpus)

    start = time.perf_counter()
    result = import_answer(
        case.query,
        case.answer,
        corpus=corpus_text,
        corpus_id=case.corpus.corpus_id,
        manifest=manifest,
        token_budget=token_budget if token_budget is not None else 300,
        top_k=top_k if top_k is not None else 5,
    )

    corpus_index = index_corpus(corpus_text, case.corpus.corpus_id)
    packed_items = result.trace.packed_context_items or []
    packed_by_id = {item.item_id: item for item in packed_items}
    comparisons_by_claim: dict[str, list] = {}
    for comparison in result.claim_evidence_comparisons:
        comparisons_by_claim.setdefault(comparison.claim_id, []).append(comparison)
    evidence_sets_by_claim = {es.answer_claim_id: es for es in result.evidence_sets}

    cross_reference_markers: dict[str, list[CrossReferenceMarker]] = {}
    for claim in result.trace.answer_claims:
        markers = detect_cross_reference_markers(claim, corpus_index, result.trace)
        if markers:
            cross_reference_markers[claim.claim_id] = markers

    conflict_explanations: dict[str, list[ConflictFieldExplanation]] = {}
    for evidence_set in result.evidence_sets:
        if evidence_set.conflicts:
            explanations = explain_conflicts(evidence_set, packed_by_id)
            if explanations:
                conflict_explanations[evidence_set.evidence_set_id] = explanations

    size3_diagnostics: dict[str, Size3Diagnostic] = {}
    for es_metrics, claim in zip(result.evidence_set_metrics, result.trace.answer_claims, strict=True):
        diagnostic = _size3_diagnostic(
            claim,
            packed_items,
            comparisons_by_claim.get(claim.claim_id, []),
            evidence_sets_by_claim.get(claim.claim_id),
            es_metrics,
            run_size3=(diagnostic_max_set_size == 3),
            trace_id=result.trace.trace_id,
        )
        if diagnostic is not None:
            size3_diagnostics[claim.claim_id] = diagnostic

    elapsed = time.perf_counter() - start
    return DiagnosticCaseResult(
        case=case,
        imported_answer=result,
        cross_reference_markers=cross_reference_markers,
        conflict_explanations=conflict_explanations,
        size3_diagnostics=size3_diagnostics,
        processing_time_seconds=elapsed,
    )


def build_diagnostic_report(case_result: DiagnosticCaseResult) -> dict:
    """The per-case `<case_id>.diagnostic.json` report -- candidate propositions, all
    field comparisons, all evidence sets considered (including rejected ones' rejection
    reasons via metrics), cross-reference target states + warnings, conflict-driver
    explanations, size-3 diagnostics, and processing metrics
    (docs/evidence-set-real-corpus-diagnostics-plan.md, "IMPLEMENT DIAGNOSTIC HARNESS").
    """

    result = case_result.imported_answer
    trace = result.trace

    def _dump_items(items):
        return None if items is None else [item.model_dump(mode="json") for item in items]

    return {
        "case_id": case_result.case.case_id,
        "provenance_status": case_result.case.provenance_status.value,
        "processing_time_seconds": case_result.processing_time_seconds,
        "llm_call_count": result.metrics.llm_call_count,
        "corpus_profile": result.corpus_profile.model_dump(mode="json") if result.corpus_profile else None,
        "retrieval_candidates": _dump_items(trace.retrieval_candidates),
        "selected_context_items": _dump_items(trace.selected_context_items),
        "packed_context_items": _dump_items(trace.packed_context_items),
        "omitted_context_items": _dump_items(trace.omitted_context_items),
        "answer_claims": [c.model_dump(mode="json") for c in trace.answer_claims],
        "answer_support_edges": [e.model_dump(mode="json") for e in trace.answer_support_edges],
        "claim_evidence_comparisons": [c.model_dump(mode="json") for c in result.claim_evidence_comparisons],
        "evidence_sets": [e.model_dump(mode="json") for e in result.evidence_sets],
        "evidence_set_metrics": [asdict(m) for m in result.evidence_set_metrics],
        "cross_reference_markers": {
            claim_id: [marker_to_dict(m) for m in markers]
            for claim_id, markers in case_result.cross_reference_markers.items()
        },
        "conflict_explanations": {
            evidence_set_id: [
                {
                    "field_name": e.conflict.field_name.value,
                    "member_a_context_item_id": e.conflict.member_a_context_item_id,
                    "member_b_context_item_id": e.conflict.member_b_context_item_id,
                    "member_a_value": e.field_comparison.claim_value,
                    "member_a_span": e.field_comparison.claim_span,
                    "member_b_value": e.field_comparison.source_value,
                    "member_b_span": e.field_comparison.source_span,
                    "extraction_method": e.field_comparison.extraction_method,
                    "confidence": e.field_comparison.confidence,
                    "rests_on_low_confidence_field": e.rests_on_low_confidence_field,
                    "alternative_non_conflict_classification_plausible": (
                        e.alternative_non_conflict_classification_plausible
                    ),
                }
                for e in explanations
            ]
            for evidence_set_id, explanations in case_result.conflict_explanations.items()
        },
        "size3_diagnostics": {
            claim_id: asdict(diagnostic) for claim_id, diagnostic in case_result.size3_diagnostics.items()
        },
        "risk_events": [r.model_dump(mode="json") for r in result.risk_events],
        "expected_evidence_locations": case_result.case.expected_evidence_locations,
    }


def build_diagnostic_labels_template(case_result: DiagnosticCaseResult) -> dict:
    """An empty scaffold for a human researcher to fill in -- categories A-E
    (docs/evidence-set-real-corpus-diagnostics-plan.md §6). Diagnostic labels about
    this pipeline's behavior, never factual-truth labels about the underlying document.
    """

    case = case_result.case

    extraction_quality_labels = {
        c.comparison_id: None for c in case_result.imported_answer.claim_evidence_comparisons
    }
    conflict_quality_labels = {
        f"{evidence_set_id}:{i}": None
        for evidence_set_id, explanations in case_result.conflict_explanations.items()
        for i in range(len(explanations))
    }
    cross_reference_closure_labels = {
        f"{claim_id}:{i}": None
        for claim_id, markers in case_result.cross_reference_markers.items()
        for i in range(len(markers))
    }
    evidence_set_sizing_labels = {claim_id: None for claim_id in case_result.size3_diagnostics}

    return {
        "case_id": case.case_id,
        "extraction_quality_labels": extraction_quality_labels,
        "conflict_quality_labels": conflict_quality_labels,
        "cross_reference_closure_labels": cross_reference_closure_labels,
        "evidence_set_sizing_labels": evidence_set_sizing_labels,
        "reviewer_workflow_labels": [],
        "case_level_notes": None,
        "allowed_values": {
            "extraction_quality_labels": [label.value for label in ExtractionQualityDiagnosticLabel],
            "conflict_quality_labels": [label.value for label in ConflictQualityDiagnosticLabel],
            "cross_reference_closure_labels": [label.value for label in CrossReferenceClosureDiagnosticLabel],
            "evidence_set_sizing_labels": [label.value for label in EvidenceSetSizingDiagnosticLabel],
            "reviewer_workflow_labels": [label.value for label in ReviewerWorkflowDiagnosticLabel],
        },
    }


def run_evidence_set_diagnostics(
    cases_path: Path, output_dir: Path, *, diagnostic_max_set_size: int | None = None
) -> list[DiagnosticCaseResult]:
    case_file = SmokeTestCaseFile.model_validate(json.loads(cases_path.read_text()))
    manifests_path = cases_path.parent / "manifests.json"
    manifests = load_manifests(manifests_path)

    output_dir.mkdir(parents=True, exist_ok=True)
    results: list[DiagnosticCaseResult] = []
    for case in case_file.cases:
        case_result = run_diagnostic_case(case, manifests, diagnostic_max_set_size=diagnostic_max_set_size)
        results.append(case_result)
        (output_dir / f"{case.case_id}.diagnostic.json").write_text(
            json.dumps(build_diagnostic_report(case_result), indent=2, default=str)
        )
        (output_dir / f"{case.case_id}.diagnostic_labels.json").write_text(
            json.dumps(build_diagnostic_labels_template(case_result), indent=2)
        )

    summary = {
        "case_count": len(results),
        "diagnostic_max_set_size": diagnostic_max_set_size,
        "total_processing_time_seconds": sum(r.processing_time_seconds for r in results),
        "cases": [r.case.case_id for r in results],
    }
    (output_dir / "summary.json").write_text(json.dumps(summary, indent=2))

    return results
