"""ApplicabilityAssessment: the transparent, explainable output of the matching engine."""

from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field

from wittgenstein.core.enums import ConfidenceTier, GateResultStatus, TransferLevel


class GateKind(str, Enum):
    REQUIRED_MANIFEST = "required_manifest"
    DISQUALIFYING = "disqualifying"
    STRENGTHENING = "strengthening"
    TRACE_OBSERVABLE = "trace_observable"


class EligibilityGateResult(BaseModel):
    """The result of evaluating one declared ManifestGate/TraceTrigger predicate."""

    model_config = ConfigDict(extra="forbid")

    gate_id: str
    gate_kind: GateKind
    status: GateResultStatus
    reason: str = Field(..., description="Human-readable reason, citing the specific field checked.")


class ApplicabilityAssessment(BaseModel):
    model_config = ConfigDict(extra="forbid")

    assessment_id: str
    failure_mechanism_id: str
    evidence_record_ids: list[str] = Field(default_factory=list)
    manifest_id: str
    trace_id_optional: str | None = None
    eligibility_gate_results: list[EligibilityGateResult] = Field(default_factory=list)
    transfer_level: TransferLevel
    matching_dimensions: list[str] = Field(default_factory=list)
    mismatching_dimensions: list[str] = Field(default_factory=list)
    unknown_dimensions: list[str] = Field(default_factory=list)
    explanation: str
    allowed_claim_language: str = Field(
        ..., description="The exact reviewer-facing phrasing this assessment is permitted to use."
    )
    recommended_review_action_ids: list[str] = Field(default_factory=list)
    confidence: ConfidenceTier
    created_at: datetime
