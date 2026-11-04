"""Typed models for the claim-evidence field-comparison engine --
docs/claim-linking-improvement-plan.md. A `ClaimEvidenceComparison` is a programmatic,
pre-review candidate assessment; its `relationship_status` is never a factual
adjudication (that remains a human/reviewer act, tracked separately -- e.g. via
`core/enums.py::AdjudicationOutcome` in the local-validation protocol, not by this
schema).
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from wittgenstein.core.enums import (
    ClaimSupportCandidateStatus,
    ComparisonFieldName,
    ComparisonOutcome,
    ExtractionStatus,
    MismatchType,
)


class ExtractedField(BaseModel):
    """One structured field extracted from one text (a claim or a candidate excerpt).
    Never authoritative on its own -- see `extraction_status`/`confidence`.
    """

    model_config = ConfigDict(extra="forbid")

    field_name: ComparisonFieldName
    value: dict[str, Any] | None = Field(
        default=None,
        description="Structured representation, e.g. a normalized frequency dict -- never a bare string "
        "when the field has normalized structure (see review/normalization.py).",
    )
    raw_surface_form: str | None = None
    source_span: tuple[int, int] | None = Field(default=None, description="Character offsets within the text.")
    extraction_method: str = Field(
        ..., description='e.g. "regex", "lexicon", "annotation_reuse", "spacy_dependency".'
    )
    extraction_status: ExtractionStatus
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)


class FieldComparison(BaseModel):
    """One field's four-state comparison outcome between a claim and a candidate."""

    model_config = ConfigDict(extra="forbid")

    field_name: ComparisonFieldName
    claim_value: dict[str, Any] | None = None
    source_value: dict[str, Any] | None = None
    claim_span: tuple[int, int] | None = None
    source_span: tuple[int, int] | None = None
    outcome: ComparisonOutcome
    mismatch_type: MismatchType | None = Field(
        default=None, description="Set only when outcome=MISMATCH -- never implies contradiction by itself."
    )
    extraction_method: str
    normalization_method: str | None = None
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    explanation: str = Field(..., description="A bounded, single-field explanation -- never a truth claim.")


class SemanticComparisonResult(BaseModel):
    """The result of one optional semantic/NLI provider call (or cache hit) comparing
    one (claim, passage) pair -- also the cache *value* type
    (docs/claim-linking-improvement-plan.md §8), matching the existing
    `LLMExtractionResult` pattern (`schemas/proposition.py`) rather than inventing a
    second cache-record shape.
    """

    model_config = ConfigDict(extra="forbid")

    cache_key: str
    provider: str | None = Field(
        default=None, description="None when no call was attempted (provider_unavailable)."
    )
    model: str | None = None
    prompt_version: str | None = None
    schema_version: str
    outcome: str = Field(
        ..., description="core/enums.py::SemanticComparisonOutcome value, or 'provider_unavailable'."
    )
    raw_response: str | None = Field(default=None, description="Present only when the caller configured storage.")
    parsed_response: dict[str, Any] | None = None
    validation_errors: list[str] = Field(default_factory=list)
    input_tokens: int | None = None
    output_tokens: int | None = None
    latency_seconds: float | None = Field(
        default=None,
        description="Wall-clock time for this call/lookup -- present even on a cache hit, since local lookup and "
        "deserialization still have a nonzero cost; a cache hit is never described as zero latency.",
    )
    from_cache: bool = False


class ClaimEvidenceComparison(BaseModel):
    """The full comparison record for one (claim, candidate) pair -- what
    `review/relationship_classification.py` produces and what an `AnswerSupportEdge`
    is derived from. `relationship_status` reuses the existing
    `ClaimSupportCandidateStatus` vocabulary (extended, not duplicated) and is a
    candidate classification, never a factual adjudication.
    """

    model_config = ConfigDict(extra="forbid")

    comparison_id: str
    claim_id: str
    context_item_id: str
    relationship_status: ClaimSupportCandidateStatus
    field_comparisons: list[FieldComparison] = Field(default_factory=list)
    mismatch_types: list[MismatchType] = Field(default_factory=list)
    lexical_features: dict[str, Any] = Field(
        default_factory=dict,
        description="e.g. token-overlap ratio -- one signal among many now, not the decision.",
    )
    structural_features: dict[str, Any] = Field(
        default_factory=dict, description="e.g. entity/predicate alignment booleans."
    )
    semantic_features: SemanticComparisonResult | None = None
    uncertainty_reason: str | None = None
    support_spans: list[tuple[int, int]] = Field(default_factory=list)
    qualification_spans: list[tuple[int, int]] = Field(default_factory=list)
    contradiction_spans: list[tuple[int, int]] = Field(default_factory=list)
    assessment_method: str = Field(default="programmatic_field_comparison")
    assessment_version: str = Field(default="1")
    explanation: str = Field(
        ..., description="Bounded reviewer-facing text -- see relationship_classification.py."
    )
