"""ReviewEvent: one reviewer action on one trace, during one review session.

Deliberately separate from `schemas/review.py::LocalValidationRecord`, which is an
aggregate *study*-level record produced later by analyzing many ReviewEvents -- this
project never collapses an atomic observation and its later aggregate summary into one
schema (CLAUDE.md, "never collapse distinct axes").
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator

from wittgenstein.core.enums import ReviewCondition, ReviewerAction


class ReviewEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    review_event_id: str
    trace_id: str
    reviewer_id: str = Field(..., description="Caller-supplied, opaque reviewer identifier -- not authenticated.")
    session_id: str | None = None
    review_condition: ReviewCondition
    displayed_risk_event_ids: list[str] = Field(
        default_factory=list, description="Every risk_event_id shown to the reviewer during this event."
    )
    opened_evidence_item_ids: list[str] = Field(
        default_factory=list, description="ContextItem item_ids the reviewer actually opened/inspected."
    )
    reviewer_action: ReviewerAction
    target_risk_event_id: str | None = Field(
        default=None, description="Which risk event this action applies to, if any."
    )
    target_claim_id: str | None = Field(
        default=None, description="Which answer claim this action applies to, if any."
    )
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    uncertainty: str | None = None
    notes: str | None = None
    timestamp: datetime
    experience_measures: dict[str, float] = Field(
        default_factory=dict,
        description="Optional ad hoc experience measures for this event, named per "
        "docs/reviewer-measures.md where applicable -- not a fixed schema, since a review "
        "condition may collect only a subset.",
    )

    @model_validator(mode="after")
    def _target_ids_are_plausible(self) -> ReviewEvent:
        if (
            self.target_risk_event_id is not None
            and self.target_risk_event_id not in self.displayed_risk_event_ids
        ):
            raise ValueError(
                f"ReviewEvent {self.review_event_id}: target_risk_event_id "
                f"{self.target_risk_event_id!r} was not among displayed_risk_event_ids -- a reviewer "
                "cannot act on a risk event that was not shown to them."
            )
        return self
