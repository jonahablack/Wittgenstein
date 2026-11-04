"""Persistence tables for submitted manifests/traces and computed assessments/risk
events -- an audit trail, not the registry itself (the registry stays YAML + git
versioned; see docs/registry-spec.md). Each row stores the full validated Pydantic
payload as JSON alongside a few indexed columns for lookup.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Column
from sqlalchemy.types import JSON
from sqlmodel import Field, SQLModel


class PipelineManifestRecord(SQLModel, table=True):
    __tablename__ = "pipeline_manifests"

    manifest_id: str = Field(primary_key=True)
    system_name: str = Field(index=True)
    system_version: str
    created_at: datetime
    payload: dict = Field(sa_column=Column(JSON))


class QueryTraceRecord(SQLModel, table=True):
    __tablename__ = "query_traces"

    trace_id: str = Field(primary_key=True)
    manifest_id: str = Field(index=True)
    query_timestamp: datetime
    payload: dict = Field(sa_column=Column(JSON))


class ApplicabilityAssessmentRecord(SQLModel, table=True):
    __tablename__ = "applicability_assessments"

    assessment_id: str = Field(primary_key=True)
    failure_mechanism_id: str = Field(index=True)
    manifest_id: str = Field(index=True)
    trace_id_optional: str | None = Field(default=None, index=True)
    transfer_level: str = Field(index=True)
    created_at: datetime
    payload: dict = Field(sa_column=Column(JSON))


class RiskEventRecord(SQLModel, table=True):
    __tablename__ = "risk_events"

    risk_event_id: str = Field(primary_key=True)
    trace_id: str = Field(index=True)
    mechanism_id: str = Field(index=True)
    priority_tier: str = Field(index=True)
    status: str = Field(index=True)
    payload: dict = Field(sa_column=Column(JSON))


class ReviewEventRecord(SQLModel, table=True):
    """One reviewer action, persisted -- see docs/review-loop-implementation-plan.md
    §5. Unlike the other tables above, this one is actually written to by the API
    (`api/routes/review.py`); the others are schema-only in this pass (§8, "deferred").
    """

    __tablename__ = "review_events"

    review_event_id: str = Field(primary_key=True)
    trace_id: str = Field(index=True)
    reviewer_id: str = Field(index=True)
    session_id: str | None = Field(default=None, index=True)
    review_condition: str = Field(index=True)
    reviewer_action: str = Field(index=True)
    timestamp: datetime = Field(index=True)
    payload: dict = Field(sa_column=Column(JSON))
