"""Review-loop endpoints -- docs/review-loop-implementation-plan.md §4, §5.

`POST /review/import-answer` is stateless (computes and returns the full audit record,
never writes to the database -- see the plan doc's §8 "deferred" note on why the other
audit tables remain unused in this pass). `POST /review/events` and
`GET /review/events` are the one place this milestone persists anything.
"""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ValidationError
from sqlmodel import Session

from wittgenstein.core.enums import ReviewCondition, ReviewerAction
from wittgenstein.core.identifiers import new_review_event_id
from wittgenstein.db.session import get_session
from wittgenstein.schemas.manifest import PipelineManifest
from wittgenstein.schemas.review_event import ReviewEvent
from wittgenstein.schemas.trace import QueryTrace
from wittgenstein.services.review_service import list_review_events_for_trace, save_review_event

router = APIRouter(prefix="/review", tags=["review"])


class ImportAnswerRequest(BaseModel):
    query: str
    answer: str
    corpus: dict[str, str] | None = None
    corpus_id: str = "imported-answer-corpus"
    manifest: dict | None = None
    trace: dict | None = None
    token_budget: int = 300
    top_k: int = 5


@router.post("/import-answer")
def import_answer_endpoint(request: ImportAnswerRequest) -> dict:
    from wittgenstein.ingestion.corpus_index import index_corpus
    from wittgenstein.review.cross_reference_diagnostics import detect_cross_reference_markers, marker_to_dict
    from wittgenstein.review.imported_answer import ImportedAnswerError, import_answer

    manifest = PipelineManifest.model_validate(request.manifest) if request.manifest is not None else None
    trace = QueryTrace.model_validate(request.trace) if request.trace is not None else None

    try:
        result = import_answer(
            request.query,
            request.answer,
            corpus=request.corpus,
            corpus_id=request.corpus_id,
            manifest=manifest,
            trace=trace,
            token_budget=request.token_budget,
            top_k=request.top_k,
        )
    except ImportedAnswerError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    # Cross-reference markers are diagnostic-only (never closure, never a claim about
    # the answer's correctness) -- recomputed read-only here exactly as
    # evidence_set_diagnostics/runner.py does, reusing corpus text only when supplied
    # (a caller-supplied `trace` with no corpus has nothing local to resolve against).
    cross_reference_markers: dict[str, list[dict]] = {}
    if request.corpus:
        corpus_index = index_corpus(request.corpus, request.corpus_id)
        for claim in result.trace.answer_claims:
            markers = detect_cross_reference_markers(claim, corpus_index, result.trace)
            if markers:
                cross_reference_markers[claim.claim_id] = [marker_to_dict(m) for m in markers]

    return {
        "trace": result.trace.model_dump(mode="json"),
        "manifest": result.manifest.model_dump(mode="json"),
        "corpus_profile": result.corpus_profile.model_dump(mode="json") if result.corpus_profile else None,
        "risk_events": [r.model_dump(mode="json") for r in result.risk_events],
        "audited_non_applicable_assessments": [
            a.model_dump(mode="json") for a in result.audited_non_applicable_assessments
        ],
        "candidates": [c.model_dump(mode="json") for c in result.candidates],
        "annotations": [a.model_dump(mode="json") for a in result.annotations],
        "context_item_provenance": result.context_item_provenance,
        "claim_evidence_comparisons": [c.model_dump(mode="json") for c in result.claim_evidence_comparisons],
        "evidence_sets": [e.model_dump(mode="json") for e in result.evidence_sets],
        "cross_reference_markers": cross_reference_markers,
    }


class ReviewEventRequest(BaseModel):
    trace_id: str
    reviewer_id: str
    session_id: str | None = None
    review_condition: ReviewCondition
    displayed_risk_event_ids: list[str] = []
    opened_evidence_item_ids: list[str] = []
    reviewer_action: ReviewerAction
    target_risk_event_id: str | None = None
    target_claim_id: str | None = None
    confidence: float | None = None
    uncertainty: str | None = None
    notes: str | None = None
    experience_measures: dict[str, float] = {}


@router.post("/events")
def submit_review_event(request: ReviewEventRequest, session: Session = Depends(get_session)) -> dict:
    try:
        event = ReviewEvent(
            review_event_id=new_review_event_id(),
            trace_id=request.trace_id,
            reviewer_id=request.reviewer_id,
            session_id=request.session_id,
            review_condition=request.review_condition,
            displayed_risk_event_ids=request.displayed_risk_event_ids,
            opened_evidence_item_ids=request.opened_evidence_item_ids,
            reviewer_action=request.reviewer_action,
            target_risk_event_id=request.target_risk_event_id,
            target_claim_id=request.target_claim_id,
            confidence=request.confidence,
            uncertainty=request.uncertainty,
            notes=request.notes,
            timestamp=datetime.now(UTC),
            experience_measures=request.experience_measures,
        )
    except ValidationError as exc:
        # Build the error detail by hand rather than passing exc.errors() straight
        # through: pydantic's error dicts can carry non-JSON-serializable values (a
        # raw datetime as "input", or the raised exception object itself as "ctx"),
        # which would otherwise crash the error *response* instead of returning a
        # clean 422.
        detail = [{"loc": list(e["loc"]), "msg": e["msg"], "type": e["type"]} for e in exc.errors()]
        raise HTTPException(status_code=422, detail=detail) from exc

    save_review_event(session, event)
    return {"review_event_id": event.review_event_id}


@router.get("/events")
def list_review_events(trace_id: str, session: Session = Depends(get_session)) -> dict:
    events = list_review_events_for_trace(session, trace_id)
    return {"events": [e.model_dump(mode="json") for e in events]}
