"""ReviewEvent schema and persistence (docs/review-loop-implementation-plan.md §5).
Test categories 9, 12.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError
from sqlmodel import Session, SQLModel, create_engine
from wittgenstein.core.identifiers import new_review_event_id
from wittgenstein.schemas.review_event import ReviewEvent
from wittgenstein.services.review_service import list_review_events_for_trace, save_review_event


def _engine():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    return engine


def _event(**overrides) -> ReviewEvent:
    defaults = dict(
        review_event_id=new_review_event_id(),
        trace_id="TRACE-1",
        reviewer_id="reviewer-1",
        review_condition="query_scoped",
        displayed_risk_event_ids=["RISK-1"],
        reviewer_action="approve_sufficiently_supported",
        target_risk_event_id="RISK-1",
        confidence=0.8,
        timestamp=datetime.now(UTC),
    )
    defaults.update(overrides)
    return ReviewEvent(**defaults)


def test_target_risk_event_must_have_been_displayed() -> None:
    with pytest.raises(ValidationError):
        _event(displayed_risk_event_ids=["RISK-2"], target_risk_event_id="RISK-1")


def test_confidence_bounded_zero_to_one() -> None:
    with pytest.raises(ValidationError):
        _event(confidence=1.5)


def test_save_and_list_round_trips() -> None:
    engine = _engine()
    event = _event()
    with Session(engine) as session:
        save_review_event(session, event)

    with Session(engine) as session:
        events = list_review_events_for_trace(session, "TRACE-1")
    assert len(events) == 1
    assert events[0].review_event_id == event.review_event_id
    assert events[0].review_condition == event.review_condition
    assert events[0].reviewer_action == event.reviewer_action


def test_list_only_returns_events_for_the_requested_trace() -> None:
    engine = _engine()
    with Session(engine) as session:
        save_review_event(session, _event(trace_id="TRACE-A"))
        save_review_event(session, _event(trace_id="TRACE-B"))

    with Session(engine) as session:
        events_a = list_review_events_for_trace(session, "TRACE-A")
        events_b = list_review_events_for_trace(session, "TRACE-B")
    assert len(events_a) == 1
    assert len(events_b) == 1
    assert events_a[0].trace_id == "TRACE-A"


def test_review_condition_preserved_exactly_across_the_three_values() -> None:
    engine = _engine()
    conditions = ["undifferentiated", "query_scoped", "manifest_conditioned"]
    with Session(engine) as session:
        for i, condition in enumerate(conditions):
            save_review_event(
                session,
                _event(review_event_id=f"REVIEW-{i}", trace_id="TRACE-COND", review_condition=condition),
            )

    with Session(engine) as session:
        events = list_review_events_for_trace(session, "TRACE-COND")
    assert sorted(e.review_condition.value for e in events) == sorted(conditions)


def test_events_ordered_by_timestamp() -> None:
    engine = _engine()
    early = datetime(2026, 1, 1, tzinfo=UTC)
    late = datetime(2026, 6, 1, tzinfo=UTC)
    with Session(engine) as session:
        save_review_event(session, _event(review_event_id="REVIEW-late", trace_id="TRACE-ORDER", timestamp=late))
        save_review_event(session, _event(review_event_id="REVIEW-early", trace_id="TRACE-ORDER", timestamp=early))

    with Session(engine) as session:
        events = list_review_events_for_trace(session, "TRACE-ORDER")
    assert [e.review_event_id for e in events] == ["REVIEW-early", "REVIEW-late"]
