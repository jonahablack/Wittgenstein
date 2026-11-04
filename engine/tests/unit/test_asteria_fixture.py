"""The Asteria controlled synthetic corpus -- docs/controlled-synthetic-corpus-plan.md.
Covers the milestone's 22 required test categories (numbering preserved in each test's
docstring/name for traceability). Entirely fictional, tracked, redistribution-safe
content -- no restricted or real-source material is read or asserted about here.
"""

from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine
from wittgenstein.api.app import app
from wittgenstein.core.enums import (
    ClaimSupportCandidateStatus,
    CrossReferenceResolutionGranularity,
    CrossReferenceTargetState,
    CueEpistemicLabel,
    ExactTargetAvailability,
)
from wittgenstein.db.session import get_session
from wittgenstein.demo.asteria_corpus import documents
from wittgenstein.evidence_set_diagnostics.runner import run_diagnostic_case
from wittgenstein.fixtures.asteria_validator import validate_asteria_fixture
from wittgenstein.ingestion.corpus_index import index_corpus
from wittgenstein.ingestion.parser import parse_document
from wittgenstein.matching.eligibility import evaluate_eligibility
from wittgenstein.review.cross_reference_diagnostics import detect_cross_reference_markers
from wittgenstein.review.imported_answer import import_answer
from wittgenstein.schemas.smoke_test import SmokeTestCaseFile
from wittgenstein.smoke_test.manifest_registry import load_manifests

_REPO_ROOT = Path(__file__).resolve().parents[2]
_FIXTURE_DIR = _REPO_ROOT / "data/fixtures/asteria_manual"


def _test_client() -> TestClient:
    # Same pattern as tests/integration/test_imported_answer_review.py::_test_client --
    # StaticPool shares one in-memory sqlite connection across TestClient's worker
    # thread, so review_events actually persists.
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(engine)

    def override_get_session():
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_session] = override_get_session
    return TestClient(app)


def _manifests():
    return load_manifests(_FIXTURE_DIR / "manifests.json")


def _case_file():
    return SmokeTestCaseFile.model_validate(json.loads((_FIXTURE_DIR / "cases" / "cases.json").read_text()))


def _case(case_id: str):
    (case,) = [c for c in _case_file().cases if c.case_id == case_id]
    return case


def _run(case_id: str, manifest_id: str | None = None):
    case = _case(case_id)
    manifests = _manifests()
    if manifest_id is not None:
        case = case.model_copy(update={"pipeline_manifest_id": manifest_id})
    manifest = manifests[case.pipeline_manifest_id]
    return run_diagnostic_case(
        case,
        manifests,
        top_k=manifest.retrieval_manifest.candidate_depth,
        token_budget=manifest.packing_manifest.evidence_budget_tokens,
    )


# 1. Fixture corpus parsing and source-offset round trips.
def test_01_corpus_parsing_and_offset_round_trip() -> None:
    corpus = documents()
    assert len(corpus) == 4
    for source_document_id, text in corpus.items():
        segments = parse_document(
            text, source_document_id=source_document_id, corpus_id="asteria-manual", parser_version="v1"
        )
        assert segments
        for segment in segments:
            assert text[segment.char_start : segment.char_end].strip() != "" or segment.text == ""
            # The segment's own text must appear at its recorded offset once whitespace
            # collapse from multi-line paragraphs is accounted for -- a looser but still
            # meaningful round-trip check, matching this repo's existing offset tests.
            if "\n" not in segment.text:
                assert text[segment.char_start : segment.char_end] == segment.text


# 2. Stable document, section, clause, annex, and table IDs.
def test_02_stable_structural_ids() -> None:
    corpus = documents()
    corpus_index = index_corpus(corpus, "asteria-manual")
    article_numbers = {s.legal_article_number for s in corpus_index.segments.values() if s.legal_article_number}
    assert article_numbers == {"2", "3", "4", "5", "6"}
    annex_identifiers = {
        s.legal_annex_identifier for s in corpus_index.segments.values() if s.legal_annex_identifier
    }
    assert annex_identifiers == {"I"}
    paragraph_numbers = {
        (s.legal_article_number, s.legal_paragraph_number)
        for s in corpus_index.segments.values()
        if s.legal_article_number == "5" and s.legal_paragraph_number
    }
    assert paragraph_numbers == {("5", "1"), ("5", "2"), ("5", "3"), ("5", "4")}
    table_rows = [s for s in corpus_index.segments.values() if s.segment_type.value == "table_row"]
    assert len(table_rows) == 3  # header + 2 data rows


# 3. Cross-reference detection and exact-target resolution.
def test_03_cross_reference_detection_and_exact_target_resolution() -> None:
    case_result = _run("asteria-006-cross-reference-exact-target-packed")
    trace = case_result.imported_answer.trace
    corpus_index = index_corpus(documents(), "asteria-manual")
    found = False
    for claim in trace.answer_claims:
        for marker in detect_cross_reference_markers(claim, corpus_index, trace):
            if marker.marker_text == "Article 5(1)":
                found = True
                assert marker.target_state == CrossReferenceTargetState.PACKED
                (target,) = marker.targets
                assert target.resolution_granularity == CrossReferenceResolutionGranularity.PARAGRAPH
                assert target.exact_target_status == ExactTargetAvailability.EXACT_TARGET_PRESENT
    assert found


# 4. P1 baseline retrieval and packing.
def test_04_p1_baseline_retrieval_and_packing() -> None:
    case_result = _run("asteria-001-direct-single-span-class-s")
    trace = case_result.imported_answer.trace
    assert len(trace.retrieval_candidates or []) == 5
    assert len(trace.packed_context_items or []) == 5
    segment_ids = {i.segment_id for i in trace.packed_context_items or []}
    assert "d2-classification-seg10" in segment_ids


# 5. P2 budget-stressed omission behavior.
def test_05_p2_budget_stressed_omission() -> None:
    case_result = _run("asteria-007-cross-reference-budget-stressed")
    trace = case_result.imported_answer.trace
    assert len(trace.omitted_context_items or []) > 0
    assert trace.final_prompt_token_count <= 60
    for item in trace.omitted_context_items or []:
        assert item.omission_reason == "context_budget_exceeded"


# 6. P4 full-context segmentation-mismatch non-activation control.
def test_06_p4_non_activation_control() -> None:
    case_result = _run("asteria-001-direct-single-span-class-s", manifest_id="asteria-p4-full-context-control")
    trace = case_result.imported_answer.trace
    assert trace.segment_boundary_dependency_flags == []
    manifests = _manifests()
    manifest = manifests["asteria-p4-full-context-control"]
    result = evaluate_eligibility("REP_SEGMENTATION_GRANULARITY_MISMATCH", manifest, trace)
    assert result.eligible is False


# 7. Segmentation mismatch activation in a designed cross-boundary dependency case,
#    only because the existing mechanism gates genuinely pass -- verified directly.
def test_07_segmentation_mismatch_activation() -> None:
    case_result = _run("asteria-004-rule-plus-condition")
    trace = case_result.imported_answer.trace
    assert trace.segment_boundary_dependency_flags != []
    manifests = _manifests()
    manifest = manifests["asteria-p1-baseline"]
    result = evaluate_eligibility("REP_SEGMENTATION_GRANULARITY_MISMATCH", manifest, trace)
    assert result.eligible is True


# 8. Direct support.
def test_08_direct_support() -> None:
    case_result = _run("asteria-001-direct-single-span-class-s")
    statuses = [c.relationship_status for c in case_result.imported_answer.claim_evidence_comparisons]
    assert ClaimSupportCandidateStatus.DIRECT_SUPPORT_CANDIDATE in statuses


# 9. Multi-passage support (evidence-set construction genuinely attempted).
def test_09_multi_passage_support_attempted() -> None:
    case_result = _run("asteria-003-two-passage-complementary")
    evidence_sets = case_result.imported_answer.evidence_sets
    assert evidence_sets
    (es,) = evidence_sets
    # Both complementary passages were composed as members -- verified, not asserted.
    assert len(es.members) == 2


# 10. Cross-reference target packed / in-corpus-but-not-retrieved states.
def test_10_cross_reference_target_states() -> None:
    packed_case = _run("asteria-006-cross-reference-exact-target-packed")
    in_corpus_case = _run("asteria-007-cross-reference-budget-stressed")
    corpus_index = index_corpus(documents(), "asteria-manual")

    def _states(case_result):
        trace = case_result.imported_answer.trace
        states = set()
        for claim in trace.answer_claims:
            for marker in detect_cross_reference_markers(claim, corpus_index, trace):
                states.add(marker.target_state)
        return states

    assert CrossReferenceTargetState.PACKED in _states(packed_case)
    assert CrossReferenceTargetState.IN_CORPUS in _states(in_corpus_case)


# 11. Same-topic non-supporting distractor.
def test_11_same_topic_distractor_does_not_satisfy_claim() -> None:
    case_result = _run("asteria-008-distractor-same-topic")
    trace = case_result.imported_answer.trace
    distractor_item_ids = {
        i.item_id for i in (trace.packed_context_items or []) if i.segment_id == "d2-classification-seg10"
    }
    assert distractor_item_ids
    distractor_statuses = [
        c.relationship_status
        for c in case_result.imported_answer.claim_evidence_comparisons
        if c.context_item_id in distractor_item_ids
    ]
    assert distractor_statuses
    assert ClaimSupportCandidateStatus.DIRECT_SUPPORT_CANDIDATE not in distractor_statuses


# 12. Frequency/numeric/threshold mismatch.
def test_12_numeric_threshold_mismatch_perturbation() -> None:
    expected = json.loads(
        (_FIXTURE_DIR / "expected/asteria-009-numeric-threshold-mismatch.expected.json").read_text()
    )
    manifests = _manifests()
    manifest = manifests["asteria-p1-baseline"]
    corpus = documents()

    source_result = import_answer(
        _case("asteria-009-numeric-threshold-mismatch").query,
        expected["source_supported_answer"],
        corpus=corpus,
        corpus_id="asteria-manual",
        manifest=manifest,
    )
    perturbed_result = import_answer(
        _case("asteria-009-numeric-threshold-mismatch").query,
        expected["perturbed_answer"],
        corpus=corpus,
        corpus_id="asteria-manual",
        manifest=manifest,
    )
    source_statuses = [c.relationship_status for c in source_result.claim_evidence_comparisons]
    perturbed_statuses = [c.relationship_status for c in perturbed_result.claim_evidence_comparisons]
    assert ClaimSupportCandidateStatus.DIRECT_SUPPORT_CANDIDATE in source_statuses
    assert ClaimSupportCandidateStatus.CONTRADICTION_CANDIDATE in perturbed_statuses


# 13. Negation/modality/condition/exception research cues remain properly labeled as
#     experimental rather than externally established.
def test_13_research_cues_remain_experimental_only() -> None:
    case_result = _run("asteria-005-rule-plus-exception")
    annotations = case_result.imported_answer.annotations
    exception_annotations = [a for a in annotations if a.cue_type.value == "exception"]
    assert exception_annotations
    for annotation in exception_annotations:
        assert annotation.epistemic_label in (
            CueEpistemicLabel.RESEARCH_HYPOTHESIS,
            CueEpistemicLabel.EXPERIMENTAL_REVIEW_CUE,
        )


# 14. User-intent underspecification.
def test_14_underspecified_user_intent() -> None:
    case_result = _run("asteria-010-underspecified-intent")
    statuses = [c.relationship_status for c in case_result.imported_answer.claim_evidence_comparisons]
    assert ClaimSupportCandidateStatus.DIRECT_SUPPORT_CANDIDATE not in statuses
    case = _case("asteria-010-underspecified-intent")
    assert case.user_intent_notes and "class" in case.user_intent_notes.lower()


# 15. Unresolved / source-expansion review outcome.
def test_15_unresolved_source_expansion_outcome() -> None:
    expected = json.loads(
        (_FIXTURE_DIR / "expected/asteria-007-cross-reference-budget-stressed.expected.json").read_text()
    )
    assert expected["expected_reviewer_action"] in ("request_additional_context", "mark_unresolved")
    assert expected["expected_reviewer_action_is_advisory_only"] is True


# 16. Imported-answer review (end to end, no LLM).
def test_16_imported_answer_review_end_to_end() -> None:
    case_result = _run("asteria-002-definition-plus-requirement")
    result = case_result.imported_answer
    assert result.trace.answer_claims
    assert result.trace.answer_support_edges
    assert result.llm_extractions == []


# 17. Review-event persistence (against an Asteria trace).
def test_17_review_event_persistence() -> None:
    client = _test_client()
    corpus = documents()
    case = _case("asteria-001-direct-single-span-class-s")
    resp = client.post(
        "/review/import-answer",
        json={"query": case.query, "answer": case.answer, "corpus": corpus, "corpus_id": "asteria-manual"},
    )
    assert resp.status_code == 200
    trace_id = resp.json()["trace"]["trace_id"]

    event_resp = client.post(
        "/review/events",
        json={
            "trace_id": trace_id,
            "reviewer_id": "asteria-fixture-test",
            "review_condition": "query_scoped",
            "reviewer_action": "approve_sufficiently_supported",
        },
    )
    assert event_resp.status_code == 200
    review_event_id = event_resp.json()["review_event_id"]

    list_resp = client.get("/review/events", params={"trace_id": trace_id})
    assert list_resp.status_code == 200
    saved_ids = [e["review_event_id"] for e in list_resp.json()["events"]]
    assert review_event_id in saved_ids


# 18. Frontend/API smoke test (no browser automation) -- confirms the API response
#     carries every field the frontend's new render functions read.
def test_18_api_response_carries_frontend_required_fields() -> None:
    client = _test_client()
    corpus = documents()
    case = _case("asteria-006-cross-reference-exact-target-packed")
    resp = client.post(
        "/review/import-answer",
        json={"query": case.query, "answer": case.answer, "corpus": corpus, "corpus_id": "asteria-manual"},
    )
    assert resp.status_code == 200
    data = resp.json()
    for key in (
        "trace",
        "risk_events",
        "claim_evidence_comparisons",
        "evidence_sets",
        "cross_reference_markers",
    ):
        assert key in data
    assert data["cross_reference_markers"]  # at least one marker for this case


# 19. No LLM calls in baseline.
def test_19_no_llm_calls_in_baseline() -> None:
    for case in _case_file().cases:
        case_result = _run(case.case_id)
        assert case_result.imported_answer.llm_extractions == [], case.case_id


# 20. Deterministic repeated execution.
def test_20_deterministic_repeated_execution() -> None:
    def _snapshot(case_result):
        result = case_result.imported_answer
        return (
            [i.segment_id for i in (result.trace.packed_context_items or [])],
            [
                (c.claim_id, c.context_item_id, c.relationship_status.value)
                for c in result.claim_evidence_comparisons
            ],
        )

    first = _snapshot(_run("asteria-004-rule-plus-condition"))
    second = _snapshot(_run("asteria-004-rule-plus-condition"))
    assert first == second


# 21. Existing 489-test baseline remains green -- exercised by running the full suite
#     (`pytest -q`), not repeated here; this test only pins the fixture-integrity
#     validator itself as an always-green gate for this corpus.
def test_21_fixture_integrity_validator_passes() -> None:
    report = validate_asteria_fixture(_FIXTURE_DIR)
    assert report.ok, report.issues
    assert report.case_count == 10


# 22. Registry and activation policies remain unchanged.
def test_22_registry_and_activation_policies_unchanged() -> None:
    from wittgenstein.services.registry_service import get_registry

    registry = get_registry()
    mechanism = registry.mechanism("REP_SEGMENTATION_GRANULARITY_MISMATCH")
    assert mechanism.default_activation_policy.value == "manifest_conditioned"
    assert mechanism.epistemic_status.value == "externally_established"
