"""CorpusProfile: decomposed, observed corpus-structure dimensions.

Deliberately no singular "complexity score" field -- complexity must be read off the
individual observed dimensions below, each with its own measurement_confidence.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class DistributionSummary(BaseModel):
    """A minimal, honest distribution summary -- not a single scalar."""

    model_config = ConfigDict(extra="forbid")

    minimum: float | None = None
    p50: float | None = None
    p90: float | None = None
    maximum: float | None = None
    mean: float | None = None
    sample_size: int | None = None


class CorpusProfile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    corpus_id: str
    source_type: str | None = None
    domain: str | None = None
    language: str | None = None
    corpus_version: str | None = None
    index_timestamp: datetime | None = None
    document_count: int | None = None
    section_count: int | None = None
    token_count: int | None = None
    document_length_distribution: DistributionSummary | None = None
    hierarchy_depth_distribution: DistributionSummary | None = None
    table_density: float | None = Field(
        default=None, description="Fraction of documents/sections containing tables."
    )
    list_density: float | None = None
    cross_reference_density: float | None = Field(
        default=None, description="Cross-references per document, or per 1k tokens."
    )
    citation_density: float | None = None
    version_or_effective_date_density: float | None = Field(
        default=None,
        description="Density of version/effective-date markers (regulatory/legal corpora).",
    )
    redundancy_metrics: dict[str, float] = Field(default_factory=dict)
    topic_heterogeneity_metrics: dict[str, float] = Field(default_factory=dict)
    terminology_variability_metrics: dict[str, float] = Field(default_factory=dict)
    evidence_dispersion_metrics: dict[str, float] = Field(
        default_factory=dict,
        description="How spread out the support for a typical answer is across the corpus, e.g. "
        "documents per answer, or a computed dispersion index. A profiling variable only -- "
        "see docs/registry-governance.md on when a corpus property may become its own mechanism.",
    )
    structured_content_notes: str | None = None
    profiling_method: str | None = Field(
        default=None, description="How this profile was computed, e.g. tool name/version."
    )
    measurement_confidence: str | None = Field(
        default=None, description='e.g. "high" (full corpus scan), "low" (sampled).'
    )
