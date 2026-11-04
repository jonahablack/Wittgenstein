"""Typed models for the multi-passage evidence-set layer --
docs/multi-passage-evidence-plan.md. An `EvidenceSet` is a candidate relationship,
exactly like `schemas/claim_comparison.py::ClaimEvidenceComparison`, never a factual
adjudication -- kept as its own object, never written back onto the existing
`schemas/trace.py::AnswerSupportEdge`, which stays single-passage only.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from wittgenstein.core.enums import (
    ClaimSupportCandidateStatus,
    ComparisonFieldName,
    ComponentRequiredness,
    EvidenceSetConstructionMethod,
    ExtractionStatus,
)
from wittgenstein.schemas.claim_comparison import FieldComparison


class ClaimComponent(BaseModel):
    """One structured component of an answer claim -- wraps an
    `ExtractedField` (schemas/claim_comparison.py) with the two additional judgments
    evidence-set construction needs: is this component load-bearing, and does covering
    it depend on another component being resolved first.
    """

    model_config = ConfigDict(extra="forbid")

    component_id: str
    component_type: ComparisonFieldName
    normalized_value: dict[str, Any] | None = None
    raw_surface_form: str | None = None
    source_span: tuple[int, int] | None = Field(default=None, description="Offset within the answer claim's text.")
    extraction_method: str
    extraction_status: ExtractionStatus
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    requiredness: ComponentRequiredness
    dependencies: list[str] = Field(
        default_factory=list, description="component_id values this component's resolution depends on, if any."
    )


class EvidenceSetMember(BaseModel):
    """One packed ContextItem's role within a candidate EvidenceSet."""

    model_config = ConfigDict(extra="forbid")

    context_item_id: str
    supplied_component_ids: list[str] = Field(
        default_factory=list,
        description="component_id values (from the parent EvidenceSet.claim_components) this member "
        "covers at MATCH.",
    )
    field_comparisons: list[FieldComparison] = Field(
        default_factory=list,
        description="This member's own field comparisons against the claim (its individual candidate assessment).",
    )
    source_location: str | None = None
    selection_rationale: str = Field(..., description="Bounded, reviewer-facing reason this member was included.")


class EvidenceSetConflict(BaseModel):
    """One detected incompatibility between two members of a candidate set."""

    model_config = ConfigDict(extra="forbid")

    member_a_context_item_id: str
    member_b_context_item_id: str
    field_name: ComparisonFieldName
    explanation: str


class EvidenceSet(BaseModel):
    """A candidate proposal that 2 (or, bounded, 3) packed items jointly cover the
    components one AnswerClaim requires -- never a factual adjudication, never written
    back onto AnswerSupportEdge (docs/multi-passage-evidence-plan.md §5).
    """

    model_config = ConfigDict(extra="forbid")

    evidence_set_id: str
    trace_id: str
    answer_claim_id: str
    member_context_item_ids: list[str] = Field(default_factory=list)
    members: list[EvidenceSetMember] = Field(default_factory=list)
    claim_components: list[ClaimComponent] = Field(default_factory=list)
    covered_component_ids: list[str] = Field(
        default_factory=list, description="component_id values covered at MATCH by the union of members."
    )
    redundant_component_ids: list[str] = Field(
        default_factory=list,
        description="component_id values covered by more than one member (recorded, not an error).",
    )
    unresolved_component_ids: list[str] = Field(
        default_factory=list, description="critical component_id values no member covers, or only UNKNOWN."
    )
    conflicts: list[EvidenceSetConflict] = Field(default_factory=list)
    relationship_status: ClaimSupportCandidateStatus
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    uncertainty_reason: str | None = None
    construction_method: EvidenceSetConstructionMethod = EvidenceSetConstructionMethod.BOUNDED_GREEDY_SET_COVER
    construction_rationale: str = Field(
        ..., description="Bounded, reviewer-facing summary of why this set was proposed."
    )
    explanation: str = Field(..., description="Bounded reviewer-facing text -- never a truth claim.")
