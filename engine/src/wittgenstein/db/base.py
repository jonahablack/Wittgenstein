"""SQLModel metadata base. Import all table modules here so Alembic autogenerate and
`SQLModel.metadata.create_all()` both see the full table set.
"""

from __future__ import annotations

from sqlmodel import SQLModel

from wittgenstein.db.models.records import (  # noqa: F401
    ApplicabilityAssessmentRecord,
    PipelineManifestRecord,
    QueryTraceRecord,
    ReviewEventRecord,
    RiskEventRecord,
)

__all__ = ["SQLModel"]
