"""Persistence for ReviewEvents -- the one place this milestone actually writes to the
database (docs/review-loop-implementation-plan.md §5, §8).
"""

from __future__ import annotations

from sqlmodel import Session, select

from wittgenstein.db.models.records import ReviewEventRecord
from wittgenstein.schemas.review_event import ReviewEvent


def save_review_event(session: Session, event: ReviewEvent) -> None:
    record = ReviewEventRecord(
        review_event_id=event.review_event_id,
        trace_id=event.trace_id,
        reviewer_id=event.reviewer_id,
        session_id=event.session_id,
        review_condition=event.review_condition.value,
        reviewer_action=event.reviewer_action.value,
        timestamp=event.timestamp,
        payload=event.model_dump(mode="json"),
    )
    session.add(record)
    session.commit()


def list_review_events_for_trace(session: Session, trace_id: str) -> list[ReviewEvent]:
    statement = (
        select(ReviewEventRecord)
        .where(ReviewEventRecord.trace_id == trace_id)
        .order_by(ReviewEventRecord.timestamp.asc())  # type: ignore[attr-defined]
    )
    records = session.exec(statement).all()
    return [ReviewEvent.model_validate(r.payload) for r in records]
