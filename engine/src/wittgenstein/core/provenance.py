"""Shared provenance types: who/what asserted a fact, and how sure we are of it.

Used by evidence extraction (human reviewer provenance) and by matching output
(rule-engine provenance), so a reader can always tell whether a value came from a
verified human review step or from a deterministic rule evaluation.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ExtractionProvenance(BaseModel):
    """Who extracted a piece of evidence data, from what, and when."""

    model_config = ConfigDict(extra="forbid")

    reviewer: str = Field(..., description="Name or handle of the human who extracted this.")
    extracted_at: datetime
    method: str = Field(
        default="manual_primary_source_read",
        description="How the extraction was performed. No automated web-scraping methods "
        "are permitted by this project's design; see docs/literature-review-protocol.md.",
    )
    notes: str | None = None


class RuleEvaluationProvenance(BaseModel):
    """Which deterministic rule/engine version produced a matching-engine output."""

    model_config = ConfigDict(extra="forbid")

    engine: str = Field(..., description='e.g. "matching.eligibility", "matching.transferability".')
    engine_version: str
    evaluated_at: datetime
    registry_version: str = Field(..., description="Registry version the rules were evaluated against.")
