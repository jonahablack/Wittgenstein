"""FailureMechanism and its attached rule records (ManifestGate, TraceTrigger).

ManifestGate/TraceTrigger records here are the *declarative, documented* form of a
mechanism's activation predicates -- they exist so the predicates are visible in the
registry data, exportable, and renderable in a dossier. The *executable* form that
actually evaluates a manifest/trace lives in `matching/eligibility.py` and is written
to reference these records by `id`, so a reviewer can always trace "why did/didn't
this fire" back to a human-readable predicate description.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, model_validator

from wittgenstein.core.enums import (
    ActivationPolicy,
    EpistemicStatus,
    EvidenceGrade,
    EvidenceSynthesis,
    PipelineFailureObject,
    PipelineStage,
)


class PredicateOperator(str, Enum):
    EQUALS = "equals"
    NOT_EQUALS = "not_equals"
    GREATER_THAN = "greater_than"
    GREATER_OR_EQUAL = "greater_or_equal"
    LESS_THAN = "less_than"
    LESS_OR_EQUAL = "less_or_equal"
    IS_TRUE = "is_true"
    IS_FALSE = "is_false"
    IN_SET = "in_set"
    NOT_IN_SET = "not_in_set"
    IS_KNOWN = "is_known"
    EXISTS_AND_NONEMPTY = "exists_and_nonempty"


class ManifestPredicate(BaseModel):
    """One documented predicate over a manifest-derived field.

    `field_path` is a dotted path into either the manifest-derived
    `ExperimentalEnvelope` (preferred, e.g. "packed_item_count") or a raw
    `PipelineManifest` section (e.g. "packing_manifest.compression_type"). The engine
    implementation for the owning mechanism is expected to evaluate exactly this
    predicate; tests assert code and registry text stay consistent.
    """

    model_config = ConfigDict(extra="forbid")

    id: str
    description: str
    field_path: str
    operator: PredicateOperator
    expected_value: str | int | float | bool | list[str] | None = None


class ManifestGate(BaseModel):
    """A hard predicate set determining whether a mechanism could apply at all."""

    model_config = ConfigDict(extra="forbid")

    id: str
    failure_mechanism_id: str
    description: str
    required_manifest_predicates: list[ManifestPredicate] = Field(default_factory=list)
    disqualifying_predicates: list[ManifestPredicate] = Field(default_factory=list)
    strengthening_predicates: list[ManifestPredicate] = Field(default_factory=list)
    unknown_manifest_behavior: str = Field(
        default=(
            "If any required field's value is unknown, the gate result is "
            "unknown_insufficient_data (never inferred as satisfied or violated)."
        )
    )


class TraceObservableRequirement(BaseModel):
    """A measurable condition a query-level mechanism requires the trace to carry."""

    model_config = ConfigDict(extra="forbid")

    id: str
    description: str
    trace_field_path: str


class TraceTrigger(BaseModel):
    """A registry-declared, measurable trace-level trigger condition for a mechanism."""

    model_config = ConfigDict(extra="forbid")

    id: str
    failure_mechanism_id: str
    description: str
    required_trace_observables: list[TraceObservableRequirement] = Field(default_factory=list)
    causal_claim_permitted: bool = Field(
        default=False,
        description="Whether this trigger, on its own, may be described causally. True only "
        "if a linked causal evidence record or local causal validation exists.",
    )


class FailureMechanism(BaseModel):
    """A stable, mechanism-level claim about how a RAG pipeline can fail.

    Not a paper, not a detector, not a UI warning, not a specific answer failure --
    see docs/architecture.md section on entity separation.
    """

    model_config = ConfigDict(extra="forbid")

    id: str
    canonical_name: str
    short_description: str
    causal_claim: str = Field(..., description="The precise mechanism-level causal claim, stated conservatively.")
    pipeline_stage: PipelineStage
    failure_object: PipelineFailureObject
    necessary_causal_ingredients: list[str] = Field(
        ..., description="Conditions that must all hold for the mechanism to be able to fire."
    )
    known_boundary_conditions: list[str] = Field(
        ..., description="Documented conditions under which the mechanism does NOT apply."
    )
    epistemic_status: EpistemicStatus
    default_evidence_grade: EvidenceGrade
    default_activation_policy: ActivationPolicy
    evidence_synthesis: EvidenceSynthesis = Field(
        ...,
        description="How this mechanism's linked evidence records, taken together, agree or "
        "disagree: convergent (independent studies broadly agree) | mixed (studies "
        "genuinely disagree, e.g. REP_SEGMENTATION_GRANULARITY_MISMATCH) | limited (one "
        "study, or too few/weak to call convergent) | unresolved (no qualifying evidence "
        "yet, including every research_hypothesis mechanism). Never averaged into a "
        "single confidence score -- see docs/registry-governance.md.",
    )
    tags: list[str] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime
    registry_version: str

    @model_validator(mode="after")
    def _research_hypothesis_cannot_be_a_graded(self) -> FailureMechanism:
        if self.epistemic_status == EpistemicStatus.RESEARCH_HYPOTHESIS:
            if self.default_evidence_grade != EvidenceGrade.E_HYPOTHESIS:
                raise ValueError(
                    f"{self.id}: epistemic_status=research_hypothesis requires "
                    "default_evidence_grade=E_hypothesis, got "
                    f"{self.default_evidence_grade.value}."
                )
            if self.default_activation_policy != ActivationPolicy.DISABLED_BY_DEFAULT_OR_RESEARCH_MODE:
                raise ValueError(
                    f"{self.id}: epistemic_status=research_hypothesis requires "
                    "default_activation_policy=disabled_by_default_or_research_mode, got "
                    f"{self.default_activation_policy.value}."
                )
            if self.evidence_synthesis != EvidenceSynthesis.UNRESOLVED:
                raise ValueError(
                    f"{self.id}: epistemic_status=research_hypothesis requires "
                    f"evidence_synthesis=unresolved, got {self.evidence_synthesis.value}."
                )
        if (
            self.epistemic_status == EpistemicStatus.UNSUPPORTED_OR_RETIRED
            and self.default_activation_policy != ActivationPolicy.RETIRED
        ):
            raise ValueError(
                f"{self.id}: epistemic_status=unsupported_or_retired requires default_activation_policy=retired."
            )
        return self
