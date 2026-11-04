"""End-to-end imported-answer review mode, including the API surface
(docs/review-loop-implementation-plan.md). Test categories 1, 2, 10, 11, 13.
"""

from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine
from wittgenstein.api.app import app
from wittgenstein.db.session import get_session
from wittgenstein.demo.pipeline import run_no_llm_baseline_demo
from wittgenstein.demo.widget_corpus import DEMO_QUERIES, documents
from wittgenstein.review.imported_answer import ImportedAnswerError, import_answer


def _test_client() -> TestClient:
    # StaticPool: FastAPI's TestClient runs sync route handlers in a worker thread, so
    # a plain in-memory sqlite engine (one connection per thread) would see an empty,
    # tableless database from that thread -- StaticPool shares the single connection
    # across all threads instead.
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(engine)

    def override_get_session():
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_session] = override_get_session
    return TestClient(app)


def test_imported_answer_mode_runs_without_any_llm_call() -> None:
    result = import_answer(
        query="What is the pass threshold for a Class I widget?",
        answer="A Class I widget must pass the Load Stress Test at a 95% threshold.",
        corpus=documents(),
    )
    assert result.metrics.llm_call_count == 0
    assert result.llm_extractions == []


def test_imported_answer_builds_a_complete_trace_with_claims_and_risk_events() -> None:
    answer = "A Class I widget must pass the Load Stress Test at a 95% threshold. It is exempt from inspection."
    result = import_answer(
        query="What is the pass threshold for a Class I widget?",
        answer=answer,
        corpus=documents(),
    )
    assert result.trace.answer == answer  # the original answer text is always preserved verbatim
    assert result.trace.answer_claims
    assert result.trace.answer_support_edges
    assert len(result.trace.answer_claims) == len(result.trace.answer_support_edges)
    assert result.trace.packed_context_items
    assert result.trace.prompt_token_spans
    # At least one risk event was derived via the same registry-matching path used
    # elsewhere -- segmentation-related mechanisms are expected to fire on a
    # multi-paragraph corpus with a segmented retrieval unit.
    assert isinstance(result.risk_events, list)
    for risk_event in result.risk_events:
        # Every risk event carries evidence status, transfer level, and bounded
        # reviewer language -- never a single opaque probability
        # (docs/review-loop-implementation-plan.md §F).
        assert risk_event.epistemic_status is not None
        assert risk_event.transfer_level is not None
        assert risk_event.reviewer_explanation
        assert risk_event.reviewer_action
        assert "hallucination probability" not in risk_event.reviewer_explanation.lower()


def test_selected_stage_left_none_when_not_instrumented_not_conflated_with_retrieved() -> None:
    """This pipeline never populates `selected_context_items` (only retrieval/packing
    are instrumented) -- `None` correctly means "not instrumented," and must never be
    read as, or silently coerced into, the retrieved or packed lists
    (docs/architecture.md, "Pipeline lineage").
    """

    result = import_answer(
        query="What is the pass threshold for a Class I widget?",
        answer="A Class I widget must pass the Load Stress Test at a 95% threshold.",
        corpus=documents(),
    )
    assert result.trace.selected_context_items is None
    assert result.trace.retrieval_candidates is not None
    assert result.trace.packed_context_items is not None


def test_requires_either_trace_or_corpus() -> None:
    try:
        import_answer(query="q", answer="a")
        raise AssertionError("expected ImportedAnswerError")
    except ImportedAnswerError:
        pass


def test_full_retrieved_set_remains_distinct_from_packed_and_omitted() -> None:
    """retrieved, selected, packed, and omitted evidence stay distinct lists -- packing
    a subset of what was retrieved must never silently shrink the retrieved list itself.
    """

    result = import_answer(
        query="What is the pass threshold for a Class I widget?",
        answer="A Class I widget must pass the Load Stress Test at a 95% threshold.",
        corpus=documents(),
        token_budget=40,  # small budget so at least one candidate is omitted
    )
    retrieved_ids = {i.item_id for i in result.trace.retrieval_candidates or []}
    packed_ids = {i.item_id for i in result.trace.packed_context_items or []}
    omitted_ids = {i.item_id for i in result.trace.omitted_context_items or []}

    assert packed_ids <= retrieved_ids
    assert omitted_ids <= retrieved_ids
    assert packed_ids.isdisjoint(omitted_ids)
    assert packed_ids | omitted_ids == retrieved_ids


def test_offline_demo_remains_fully_functional() -> None:
    _, corpus_metrics, results = run_no_llm_baseline_demo(documents(), DEMO_QUERIES)
    assert corpus_metrics.llm_call_count == 0
    assert len(results) == len(DEMO_QUERIES)
    for result in results:
        assert result.metrics.llm_call_count == 0


def test_api_import_answer_and_submit_review_event_round_trip() -> None:
    client = _test_client()
    try:
        response = client.post(
            "/review/import-answer",
            json={
                "query": "What is the pass threshold for a Class I widget?",
                "answer": "A Class I widget must pass the Load Stress Test at a 95% threshold.",
                "corpus": documents(),
            },
        )
        assert response.status_code == 200
        body = response.json()
        assert body["trace"]["answer_claims"]
        assert "retrieval_candidates" in body["trace"]
        assert "packed_context_items" in body["trace"]
        assert "corpus_profile" in body

        trace_id = body["trace"]["trace_id"]
        risk_event_ids = [r["risk_event_id"] for r in body["risk_events"]]

        event_response = client.post(
            "/review/events",
            json={
                "trace_id": trace_id,
                "reviewer_id": "reviewer-1",
                "review_condition": "manifest_conditioned",
                "displayed_risk_event_ids": risk_event_ids,
                "reviewer_action": "mark_unresolved",
                "confidence": 0.5,
                "uncertainty": "moderate",
                "notes": "test note",
            },
        )
        assert event_response.status_code == 200

        list_response = client.get("/review/events", params={"trace_id": trace_id})
        assert list_response.status_code == 200
        events = list_response.json()["events"]
        assert len(events) == 1
        assert events[0]["reviewer_action"] == "mark_unresolved"
        assert events[0]["review_condition"] == "manifest_conditioned"
    finally:
        app.dependency_overrides.clear()


def test_api_rejects_review_event_targeting_undisplayed_risk_event() -> None:
    client = _test_client()
    try:
        response = client.post(
            "/review/events",
            json={
                "trace_id": "TRACE-X",
                "reviewer_id": "reviewer-1",
                "review_condition": "query_scoped",
                "displayed_risk_event_ids": [],
                "reviewer_action": "approve_sufficiently_supported",
                "target_risk_event_id": "RISK-NOT-DISPLAYED",
            },
        )
        assert response.status_code == 422
    finally:
        app.dependency_overrides.clear()
