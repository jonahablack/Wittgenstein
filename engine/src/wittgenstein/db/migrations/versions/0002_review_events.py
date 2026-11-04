"""review events

Revision ID: 0002
Revises: 0001
Create Date: 2026-09-10

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "review_events",
        sa.Column("review_event_id", sa.String(), primary_key=True),
        sa.Column("trace_id", sa.String(), nullable=False, index=True),
        sa.Column("reviewer_id", sa.String(), nullable=False, index=True),
        sa.Column("session_id", sa.String(), nullable=True, index=True),
        sa.Column("review_condition", sa.String(), nullable=False, index=True),
        sa.Column("reviewer_action", sa.String(), nullable=False, index=True),
        sa.Column("timestamp", sa.DateTime(), nullable=False, index=True),
        sa.Column("payload", sa.JSON(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("review_events")
