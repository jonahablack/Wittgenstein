"""initial audit tables

Revision ID: 0001
Revises:
Create Date: 2026-09-02

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "pipeline_manifests",
        sa.Column("manifest_id", sa.String(), primary_key=True),
        sa.Column("system_name", sa.String(), nullable=False, index=True),
        sa.Column("system_version", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
    )
    op.create_table(
        "query_traces",
        sa.Column("trace_id", sa.String(), primary_key=True),
        sa.Column("manifest_id", sa.String(), nullable=False, index=True),
        sa.Column("query_timestamp", sa.DateTime(), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
    )
    op.create_table(
        "applicability_assessments",
        sa.Column("assessment_id", sa.String(), primary_key=True),
        sa.Column("failure_mechanism_id", sa.String(), nullable=False, index=True),
        sa.Column("manifest_id", sa.String(), nullable=False, index=True),
        sa.Column("trace_id_optional", sa.String(), nullable=True, index=True),
        sa.Column("transfer_level", sa.String(), nullable=False, index=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
    )
    op.create_table(
        "risk_events",
        sa.Column("risk_event_id", sa.String(), primary_key=True),
        sa.Column("trace_id", sa.String(), nullable=False, index=True),
        sa.Column("mechanism_id", sa.String(), nullable=False, index=True),
        sa.Column("priority_tier", sa.String(), nullable=False, index=True),
        sa.Column("status", sa.String(), nullable=False, index=True),
        sa.Column("payload", sa.JSON(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("risk_events")
    op.drop_table("applicability_assessments")
    op.drop_table("query_traces")
    op.drop_table("pipeline_manifests")
