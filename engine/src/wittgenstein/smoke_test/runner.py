"""The smoke-test runner: load cases -> resolve corpus/manifest -> run imported-answer
mode -> write an inspection report and a manual-labels template per case
(docs/real-trace-smoke-test-plan.md).

Never calls an LLM unless `enhanced=True` is passed explicitly -- the default
(`enhanced=False`) path exercises `import_answer(..., llm_client=None)`, identical to
every other no-LLM-required path in this codebase.
"""

from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

from wittgenstein.core.enums import (
    ClaimLinkingDiagnosticLabel,
    PropositionProvenanceDiagnosticLabel,
    RetrievalDiagnosticLabel,
    ReviewInterfaceDiagnosticLabel,
)
from wittgenstein.proposition.llm_client import LLMClient
from wittgenstein.review.claim_linking import CandidateScore, score_candidates
from wittgenstein.review.imported_answer import ImportedAnswerResult, import_answer
from wittgenstein.schemas.smoke_test import SmokeTestCase, SmokeTestCaseFile
from wittgenstein.smoke_test.corpus_registry import resolve_corpus
from wittgenstein.smoke_test.manifest_registry import SmokeTestManifestError, load_manifests


@dataclass
class SmokeTestCaseResult:
    case: SmokeTestCase
    imported_answer: ImportedAnswerResult
    link_scores: dict[str, list[CandidateScore]] = field(default_factory=dict)
    processing_time_seconds: float = 0.0


def _default_enhanced_client() -> LLMClient:
    """Prefers a real, configured `AnthropicProviderClient` (env var + package both
    present); falls back to the deterministic, offline `DemoLLMClient` otherwise -- so
    `--enhanced` is exercisable (and testable) without requiring live credentials, per
    docs/review-loop-implementation-plan.md's "no external provider necessary for
    tests" rule, which applies equally here.
    """

    from wittgenstein.proposition.providers.anthropic_client import AnthropicProviderClient

    anthropic_client = AnthropicProviderClient()
    if anthropic_client.is_available():
        return anthropic_client

    from wittgenstein.demo.pipeline import DemoLLMClient

    return DemoLLMClient()


def run_case(
    case: SmokeTestCase,
    manifests: dict,
    *,
    llm_client: LLMClient | None = None,
) -> SmokeTestCaseResult:
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
        llm_client=llm_client,
    )
    elapsed = time.perf_counter() - start

    packed_items = result.trace.packed_context_items or []
    link_scores = {claim.claim_id: score_candidates(claim, packed_items) for claim in result.trace.answer_claims}

    return SmokeTestCaseResult(
        case=case, imported_answer=result, link_scores=link_scores, processing_time_seconds=elapsed
    )


def build_inspection_report(case_result: SmokeTestCaseResult) -> dict:
    trace = case_result.imported_answer.trace
    metrics = case_result.imported_answer.metrics
    result = case_result.imported_answer

    def _dump_items(items):
        return None if items is None else [item.model_dump(mode="json") for item in items]

    return {
        "case_id": case_result.case.case_id,
        "provenance_status": case_result.case.provenance_status.value,
        "processing_time_seconds": case_result.processing_time_seconds,
        "llm_call_count": metrics.llm_call_count,
        "cache_statistics": {
            "cache_hits": metrics.cache_hits,
            "cache_misses": metrics.cache_misses,
            "cache_hit_rate": metrics.cache_hit_rate,
        },
        "corpus_profile": result.corpus_profile.model_dump(mode="json") if result.corpus_profile else None,
        "retrieval_candidates": _dump_items(trace.retrieval_candidates),
        "selected_context_items": _dump_items(trace.selected_context_items),
        "packed_context_items": _dump_items(trace.packed_context_items),
        "omitted_context_items": _dump_items(trace.omitted_context_items),
        "compressed_context_items": _dump_items(trace.compressed_context_items),
        "answer_claims": [c.model_dump(mode="json") for c in trace.answer_claims],
        "answer_support_edges": [e.model_dump(mode="json") for e in trace.answer_support_edges],
        "claim_evidence_comparisons": [c.model_dump(mode="json") for c in result.claim_evidence_comparisons],
        "evidence_sets": [e.model_dump(mode="json") for e in result.evidence_sets],
        "evidence_set_metrics": [asdict(m) for m in result.evidence_set_metrics],
        "link_scores": {
            claim_id: [asdict(s) for s in scores] for claim_id, scores in case_result.link_scores.items()
        },
        "risk_events": [r.model_dump(mode="json") for r in result.risk_events],
        "expected_evidence_locations": case_result.case.expected_evidence_locations,
    }


def build_labels_template(case_result: SmokeTestCaseResult) -> dict:
    """An empty scaffold for a human researcher to fill in while reading the
    inspection report -- these labels are never computed automatically, and are
    diagnostic labels about this pipeline's behavior, never factual-truth labels about
    the underlying document (docs/real-trace-smoke-test-plan.md §§6-10).

    `expected_evidence_location_labels` is kept separate from
    `retrieval_candidate_labels`: a missed location has no retrieved item_id to key a
    per-candidate label against, so "was this expected location ever retrieved, and
    if so as which candidate" needs its own slot per expected location, not one
    squeezed into the per-retrieved-candidate dict.
    """

    trace = case_result.imported_answer.trace
    case = case_result.case
    packed_by_id = {item.item_id: item for item in trace.packed_context_items or []}
    claims_by_id = {claim.claim_id: claim for claim in trace.answer_claims}

    # Per (claim, candidate) pair manual annotation template -- distinct from
    # claim_linking_labels above (one label per claim, aggregated across candidates):
    # this is the richer, candidate-pair-level record docs/real-trace-smoke-test-plan.md
    # "SMOKE-TEST REPORTING" requires for real/licensed runs, pre-filled with the
    # read-only fields (answer claim, candidate passage, field-comparison vector,
    # programmatic candidate relationship) and empty reviewer slots.
    claim_evidence_annotations = {}
    for comparison in case_result.imported_answer.claim_evidence_comparisons:
        claim = claims_by_id.get(comparison.claim_id)
        candidate = packed_by_id.get(comparison.context_item_id)
        claim_evidence_annotations[comparison.comparison_id] = {
            "answer_claim": claim.text if claim else None,
            "candidate_passage": candidate.excerpt if candidate else None,
            "field_comparison_vector": [
                {"field_name": fc.field_name.value, "outcome": fc.outcome.value}
                for fc in comparison.field_comparisons
            ],
            "candidate_relationship": comparison.relationship_status.value,
            "reviewer_label": None,
            "reviewer_confidence": None,
            "reviewer_rationale": None,
            "unresolved_reason": None,
            "notes": None,
        }

    return {
        "case_id": case.case_id,
        "retrieval_candidate_labels": {item.item_id: None for item in trace.retrieval_candidates or []},
        "expected_evidence_location_labels": {
            location: {"label": None, "matched_item_id": None} for location in case.expected_evidence_locations
        },
        "claim_linking_labels": {edge.claim_id: None for edge in trace.answer_support_edges},
        "claim_evidence_annotations": claim_evidence_annotations,
        "proposition_provenance_labels": {item.item_id: None for item in trace.packed_context_items or []},
        "review_interface_labels": [],
        "case_level_notes": None,
        "allowed_values": {
            "retrieval_candidate_labels": [label.value for label in RetrievalDiagnosticLabel],
            "expected_evidence_location_labels": [label.value for label in RetrievalDiagnosticLabel],
            "claim_linking_labels": [label.value for label in ClaimLinkingDiagnosticLabel],
            "claim_evidence_annotations.reviewer_label": [label.value for label in ClaimLinkingDiagnosticLabel],
            "proposition_provenance_labels": [label.value for label in PropositionProvenanceDiagnosticLabel],
            "review_interface_labels": [label.value for label in ReviewInterfaceDiagnosticLabel],
        },
    }


def run_smoke_test(cases_path: Path, output_dir: Path, *, enhanced: bool = False) -> list[SmokeTestCaseResult]:
    case_file = SmokeTestCaseFile.model_validate(json.loads(cases_path.read_text()))
    manifests_path = cases_path.parent / "manifests.json"
    manifests = load_manifests(manifests_path)
    llm_client = _default_enhanced_client() if enhanced else None

    output_dir.mkdir(parents=True, exist_ok=True)
    results: list[SmokeTestCaseResult] = []
    for case in case_file.cases:
        case_result = run_case(case, manifests, llm_client=llm_client)
        results.append(case_result)
        (output_dir / f"{case.case_id}.inspection.json").write_text(
            json.dumps(build_inspection_report(case_result), indent=2, default=str)
        )
        (output_dir / f"{case.case_id}.labels_template.json").write_text(
            json.dumps(build_labels_template(case_result), indent=2)
        )

    summary = {
        "case_count": len(results),
        "enhanced": enhanced,
        "total_processing_time_seconds": sum(r.processing_time_seconds for r in results),
        "total_llm_call_count": sum(r.imported_answer.metrics.llm_call_count for r in results),
        "cases": [r.case.case_id for r in results],
    }
    (output_dir / "summary.json").write_text(json.dumps(summary, indent=2))

    return results
