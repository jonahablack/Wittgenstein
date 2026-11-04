"""ReviewAction, RiskEvent, and LocalValidationRecord.

ReviewAction is always a bounded, human-checkable question or comparison -- never an
instruction to blindly accept an automated truth value. This is enforced structurally:
`instructs_acceptance` cannot be True.
"""

from __future__ import annotations

from datetime import date

from pydantic import BaseModel, ConfigDict, Field, model_validator

from wittgenstein.core.enums import (
    EpistemicStatus,
    LocalValidationStatus,
    PriorityTier,
    RiskEventStatus,
    TransferLevel,
)

# ---------------------------------------------------------------------------------
# Multidimensional local-validation outcome layers (docs/local-validation-protocol.md).
#
# Four independent outcome layers (A-D) plus alert-fatigue/AI-burnout as its own
# explicit dimension -- never collapsed into a single accuracy or trust score. Each
# layer is `applicable: bool`-gated so a study can honestly report "not measured in
# this study" / "not applicable to this case" rather than a misleading None-as-zero.
# All rate/mean fields are optional floats: a study reports only what it actually
# measured, per this project's "never infer" discipline (CLAUDE.md).
# ---------------------------------------------------------------------------------


class AdjudicatedTraceEvidence(BaseModel):
    """Layer A: evidence/factual adjudication -- used only where a defensible
    adjudication target exists. Never required to provide a universal gold label for
    every task; `applicable=False` is a normal, honest outcome for contested or
    version-/jurisdiction-dependent material. See `core/enums.py::AdjudicationOutcome`
    for the per-case outcome vocabulary this layer's rates are computed over.
    """

    model_config = ConfigDict(extra="forbid")

    applicable: bool = Field(
        ...,
        description="Whether a defensible adjudication target existed for this study/"
        "case set at all. False is a normal, honest outcome, not a gap to fill in.",
    )
    adjudication_target: str | None = Field(
        default=None, description="What was being adjudicated (claim-level statement, query-level answer, etc.)."
    )
    adjudicator: str | None = Field(default=None, description="Who adjudicated (role, not necessarily name).")
    governing_source_or_version: str | None = Field(
        default=None, description="Which source/version was treated as authoritative for this adjudication pass."
    )
    label_granularity: str | None = Field(default=None, description='"claim_level" or "query_level".')
    material_support_issue_detection_rate: float | None = None
    unsupported_claim_detection_rate: float | None = None
    contradiction_recognition_rate: float | None = None
    qualification_preservation_rate: float | None = None
    false_approval_rate: float | None = Field(
        default=None, description="Rate at which reviewers approved a claim that adjudication found unsupported."
    )
    false_rejection_rate: float | None = Field(
        default=None, description="Rate at which reviewers rejected a claim that adjudication found supported."
    )
    appropriate_unresolved_escalation_rate: float | None = Field(
        default=None,
        description="Rate at which a genuinely contested/incomplete case was correctly left unresolved or "
        "escalated, rather than forced into a false supported/unsupported call.",
    )
    support_set_completeness_recognition_rate: float | None = None
    disagreement_handling: str | None = Field(
        default=None, description="How disagreement between adjudicators was represented, not silently resolved."
    )
    unresolved_or_contested_case_handling: str | None = None
    material_issue_definition: str | None = Field(
        default=None, description="What counted as a material issue for this study, stated in advance."
    )
    notes: str | None = None


class ContextualJudgmentEvidence(BaseModel):
    """Layer B: whether reviewers noticed context-sensitivity signals in the material
    (population, jurisdiction, date, version, ... applicability boundaries) -- distinct
    from whether they reached the "right" factual answer.
    """

    model_config = ConfigDict(extra="forbid")

    applicable: bool = True
    population_awareness_rate: float | None = None
    jurisdiction_awareness_rate: float | None = None
    date_awareness_rate: float | None = None
    version_awareness_rate: float | None = None
    source_authority_awareness_rate: float | None = None
    condition_awareness_rate: float | None = None
    exception_awareness_rate: float | None = None
    threshold_awareness_rate: float | None = None
    cross_reference_awareness_rate: float | None = None
    missing_dependency_awareness_rate: float | None = None
    conflicting_source_awareness_rate: float | None = None
    applicability_boundary_awareness_rate: float | None = None
    notes: str | None = None


class BehavioralWorkflowEvidence(BaseModel):
    """Layer C: reviewer experience and workflow behavior. `willingness_to_continue_mean`
    and `willingness_to_reuse_mean` live here as their one canonical home -- the
    alert-fatigue layer (`AlertFatigueEvidence`) reads these rather than duplicating
    them, to avoid two fields describing the same measure drifting out of sync
    (CLAUDE.md, "General engineering lessons").
    """

    model_config = ConfigDict(extra="forbid")

    applicable: bool = True
    perceived_usefulness_mean: float | None = None
    ease_of_verification_mean: float | None = None
    evidence_navigation_effort_mean: float | None = None
    review_time_seconds_mean: float | None = None
    source_text_opened_rate: float | None = None
    dependency_links_followed_rate: float | None = None
    full_context_request_rate: float | None = None
    clarification_request_rate: float | None = None
    escalation_rate: float | None = None
    perceived_review_burden_mean: float | None = None
    perceived_alert_relevance_mean: float | None = None
    willingness_to_continue_mean: float | None = None
    willingness_to_reuse_mean: float | None = None
    notes: str | None = None


class AutonomyAndTrustEvidence(BaseModel):
    """Layer D: human autonomy and trust calibration."""

    model_config = ConfigDict(extra="forbid")

    applicable: bool = True
    perceived_autonomy_mean: float | None = None
    supported_independent_judgment_mean: float | None = None
    encouraged_blind_acceptance_mean: float | None = Field(
        default=None, description="Higher is worse: the tool encouraged blind acceptance rather than review."
    )
    felt_pressured_to_follow_tool_mean: float | None = None
    confidence_in_answer_mean: float | None = None
    confidence_in_evidence_mean: float | None = None
    confidence_in_tool_warning_mean: float | None = None
    recognized_need_for_more_information_rate: float | None = None
    override_or_reject_rate: float | None = Field(
        default=None, description="Rate at which reviewers overrode or rejected the tool's prioritization."
    )
    notes: str | None = None


class AlertFatigueEvidence(BaseModel):
    """Alert fatigue and AI burnout, tracked as an explicit evaluation dimension, not an
    informal motivation only. A low alert volume does not by itself mean low fatigue --
    a warning can be low-volume but still opaque, repetitive, or unhelpful; that is why
    `actionable_alert_rate` and the perception measures are reported alongside raw
    counts, not instead of them.
    """

    model_config = ConfigDict(extra="forbid")

    applicable: bool = True
    perceived_alert_volume_mean: float | None = None
    perceived_alert_actionability_mean: float | None = None
    repeated_warning_annoyance_mean: float | None = None
    alerts_displayed_count: int | None = None
    alerts_dismissed_count: int | None = None
    alerts_leading_to_meaningful_action_count: int | None = Field(
        default=None,
        description="A meaningful action includes: opening a dependency, inspecting omitted context, checking a "
        "competing source, requesting clarification, qualifying the answer, escalating, or marking unresolved.",
    )
    actionable_alert_rate: float | None = Field(
        default=None,
        description="alerts_leading_to_meaningful_action_count / alerts_displayed_count. Reported directly (not "
        "silently inferred from the counts) so a study can report it even when only aggregate rates, not raw "
        "counts, were collected -- but see _actionable_rate_consistent_with_counts for the cross-check when both "
        "are given.",
    )
    unnecessary_escalation_count: int | None = Field(
        default=None,
        description="Escalations that increased review burden without improving reviewer-perceived understanding "
        "or usefulness -- a distinct risk from a mechanism simply having a low actionable_alert_rate.",
    )
    mental_workload_mean: float | None = None
    frustration_mean: float | None = None
    fatigue_after_block_mean: float | None = None
    perceived_repetitiveness_mean: float | None = None
    notes: str | None = None

    @model_validator(mode="after")
    def _actionable_rate_consistent_with_counts(self) -> AlertFatigueEvidence:
        if (
            self.actionable_alert_rate is not None
            and self.alerts_displayed_count is not None
            and self.alerts_leading_to_meaningful_action_count is not None
            and self.alerts_displayed_count > 0
        ):
            implied = self.alerts_leading_to_meaningful_action_count / self.alerts_displayed_count
            if abs(implied - self.actionable_alert_rate) > 0.01:
                raise ValueError(
                    "AlertFatigueEvidence: actionable_alert_rate "
                    f"({self.actionable_alert_rate}) is inconsistent with "
                    f"alerts_leading_to_meaningful_action_count/alerts_displayed_count ({implied:.4f}). "
                    "Report a consistent rate, or omit one of the three fields rather than let them drift."
                )
        return self


class FalseReassuranceAnalysis(BaseModel):
    """Whether the tool made reviewers prematurely comfortable or less likely to
    investigate when investigation remained warranted -- tracked as its own named risk,
    never inferred from a low disagreement rate or a high usefulness score alone. A
    tool that reduces review time but increases false reassurance is not a success --
    docs/local-validation-protocol.md.
    """

    model_config = ConfigDict(extra="forbid")

    definition: str = Field(
        default=(
            "The tool appears to make reviewers prematurely comfortable or less likely "
            "to investigate when investigation remains warranted."
        )
    )
    observed: bool = Field(..., description="Whether this study looked for false reassurance at all.")
    method: str | None = Field(default=None, description="How false reassurance was operationally detected.")
    rate: float | None = None
    cases_identified: int | None = None
    notes: str | None = None


class ReviewAction(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    applicable_mechanism_ids: list[str]
    prompt_text: str = Field(
        ..., description="The bounded question/comparison a human reviewer is asked to perform."
    )
    action_type: str = Field(
        ...,
        description='e.g. "compare_with_and_without_item", "confirm_support_status", "check_conflict_resolution".',
    )
    instructs_acceptance: bool = Field(
        default=False,
        description="Must always be False. Present as an explicit field (rather than omitted) so "
        "a reviewer/linter can grep for and reject any attempt to set it True.",
    )

    @model_validator(mode="after")
    def _never_instructs_blind_acceptance(self) -> ReviewAction:
        if self.instructs_acceptance:
            raise ValueError(
                f"ReviewAction {self.id}: instructs_acceptance must be False. A review action "
                "must always be a bounded, human-checkable question, never an instruction to "
                "blindly accept an automated truth value."
            )
        return self


class RiskEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    risk_event_id: str
    trace_id: str
    mechanism_id: str
    trace_trigger_id: str | None = None
    observed_evidence: str = Field(
        ...,
        description="Factual description of what was observed in the trace, stated as an "
        "observation, not a causal explanation.",
    )
    transfer_level: TransferLevel
    epistemic_status: EpistemicStatus
    priority_tier: PriorityTier
    causal_claim_allowed: bool
    reviewer_explanation: str
    reviewer_action: str = Field(..., description="ReviewAction id this event recommends.")
    source_evidence_links: list[str] = Field(default_factory=list)
    status: RiskEventStatus = RiskEventStatus.OPEN

    @model_validator(mode="after")
    def _causal_claim_requires_support(self) -> RiskEvent:
        # This single check already covers trace_integrity_condition mechanisms: a
        # trace_integrity_condition RiskEvent with causal_claim_allowed=True and no
        # linked evidence is exactly the "cannot claim causality without a linked
        # causal evidence record or local causal validation" case the spec calls out.
        if self.causal_claim_allowed and not self.source_evidence_links:
            raise ValueError(
                f"RiskEvent {self.risk_event_id}: causal_claim_allowed=True requires at least "
                "one linked evidence record (source_evidence_links) or local causal validation."
            )
        return self


class LocalValidationRecord(BaseModel):
    """A result from this project's own controlled tests or human-review study.

    Local evidence can improve triage priority *in the deployment it was collected
    from*, but must never be used to raise a mechanism's global epistemic_status to
    externally_established -- see docs/registry-governance.md. `external_evidence_status`,
    `local_validation_status`, and `deployment_priority` are kept as three deliberately
    separate fields (never merged into one "confidence") so a local result can move
    triage priority for this deployment without ever silently touching the mechanism's
    global, externally-reviewed status.
    """

    model_config = ConfigDict(extra="forbid")

    id: str
    mechanism_id: str
    deployment_scope: str = Field(
        ...,
        description="The specific deployment/dataset this validation applies to. Local "
        "validation is scoped, not a universal external claim.",
    )
    method: str
    sample_size: int | None = None
    result_summary: str
    causal_or_correlational: str = Field(..., description='"causal" or "correlational".')
    reviewers: list[str]
    date: date
    limitations: str
    external_evidence_status: EpistemicStatus = Field(
        ...,
        description="A frozen snapshot of the mechanism's global epistemic_status at the time "
        "this record was created -- an audit trail, not a live pointer. If the mechanism's "
        "global status later changes, this field is not retroactively updated.",
    )
    local_validation_status: LocalValidationStatus = Field(default=LocalValidationStatus.PROPOSED)
    deployment_priority: PriorityTier = Field(
        ...,
        description="How this record should weight triage priority within deployment_scope only. "
        "Never read as, or converted into, a global priority/status signal.",
    )
    preregistered: bool = Field(
        default=False,
        description="Whether the flag/outcome being tested was specified before the evaluation "
        "ran (a predefined flag and outcome), as opposed to selected after seeing results.",
    )
    evaluation_split: str | None = Field(
        default=None, description="Description of the held-out or preregistered evaluation split used."
    )
    corpus_description: str | None = None
    manifest_description: str | None = None
    query_distribution_description: str | None = None
    label_source: str | None = Field(default=None, description="How ground-truth labels were produced.")
    precision: float | None = None
    recall: float | None = None
    reviewer_yield: float | None = Field(
        default=None, description="Fraction of reviewed items that were confirmed true positives."
    )
    uncertainty: str | None = Field(
        default=None, description="e.g. a confidence interval or qualitative uncertainty statement."
    )
    replication_notes: str | None = Field(
        default=None, description="Replication across corpus slices or task types, where feasible."
    )
    reviewer_population: str | None = Field(
        default=None,
        description="Who the reviewers were (role/expertise/count) -- distinct from `reviewers`, "
        "which lists reviewer ids/names, not a population description.",
    )
    corpus_slices: list[str] = Field(
        default_factory=list,
        description="Named corpus slices or task types this study covered, e.g. for the TRIAGE_ENABLED "
        "replication-across-slices criterion (docs/registry-governance.md).",
    )
    study_design: str | None = Field(
        default=None,
        description="Narrative design description: review conditions used (see "
        "docs/local-validation-protocol.md), between/within-subjects, primary comparison.",
    )
    outcome_definitions: dict[str, str] = Field(
        default_factory=dict,
        description="Operational definition per reported outcome measure name -- the study's documented "
        "instrument, cross-referenced with docs/reviewer-measures.md.",
    )
    uncertainty_or_intervals: str | None = Field(
        default=None,
        description="Uncertainty reporting across the reported multidimensional outcome measures (means/rates in "
        "the evidence layers below) -- broader in scope than `uncertainty`, which is the legacy field for the "
        "core precision/recall adjudication metrics only. Kept separate rather than merged, per this project's "
        "rule against two fields silently describing the same thing.",
    )
    unresolved_limitations: str | None = Field(
        default=None,
        description="What remains open or unresolved even after this study -- distinct from `limitations` "
        "(methodological caveats on the study as designed); this field is what a promotion-review reader checks "
        "first to see what is NOT yet known.",
    )
    reviewer_experience_evidence: BehavioralWorkflowEvidence | None = None
    behavioral_workflow_evidence: BehavioralWorkflowEvidence | None = Field(
        default=None,
        description="Alias field for callers that distinguish 'self-reported experience' "
        "(reviewer_experience_evidence) from 'observed behavior' (this field) even though both use the same "
        "BehavioralWorkflowEvidence shape; a study may populate either or both.",
    )
    adjudicated_trace_evidence: AdjudicatedTraceEvidence | None = None
    contextual_judgment_evidence: ContextualJudgmentEvidence | None = None
    autonomy_and_trust_evidence: AutonomyAndTrustEvidence | None = None
    alert_fatigue_evidence: AlertFatigueEvidence | None = None
    false_reassurance_analysis: FalseReassuranceAnalysis | None = None

    def meets_promotion_bar(self) -> bool:
        """Whether this record is complete enough to support promoting its mechanism to
        `locally_validated` per docs/registry-governance.md. Does not itself perform the
        promotion -- that remains a deliberate, separate registry-governance edit, never
        automatic.
        """

        required_strings = [
            self.evaluation_split,
            self.corpus_description,
            self.manifest_description,
            self.query_distribution_description,
            self.label_source,
            self.uncertainty,
        ]
        return (
            self.preregistered
            and bool(self.reviewers)
            and all(bool(v) for v in required_strings)
            and self.precision is not None
            and self.recall is not None
            and self.reviewer_yield is not None
        )

    def meets_triage_promotion_bar(self) -> bool:
        """Whether this record is complete enough to make its mechanism *eligible for
        consideration* for `ActivationPolicy.TRIAGE_ENABLED` -- a distinct, separate gate
        from `meets_promotion_bar()` above (which governs `locally_validated`
        epistemic_status, a different axis entirely -- see ADR 0002 and
        docs/registry-governance.md).

        This method checks only what is mechanically checkable from this record's own
        completeness: reviewer-experience evidence and false-reassurance analysis are
        both present (their absence is instruction #6/#7 of the TRIAGE_ENABLED
        criteria), the study is preregistered with a documented design, corpus/reviewer
        coverage is described, and replication spans at least two corpus slices where
        the record claims replication at all. It does NOT evaluate the *substance* of
        the results (e.g. whether the actionable-alert rate is actually good, or
        whether false reassurance was actually low) -- that is always a human
        registry-governance judgment against the full ten-point checklist in
        docs/registry-governance.md, never automated. Returning True here is necessary,
        never sufficient, for a TRIAGE_ENABLED decision, and this method never itself
        changes any ActivationPolicy.
        """

        has_reviewer_experience_evidence = (
            self.reviewer_experience_evidence is not None and self.reviewer_experience_evidence.applicable
        ) or (self.behavioral_workflow_evidence is not None and self.behavioral_workflow_evidence.applicable)
        has_false_reassurance_analysis = (
            self.false_reassurance_analysis is not None and self.false_reassurance_analysis.observed
        )
        has_design_documentation = (
            bool(self.study_design) and bool(self.reviewer_population) and bool(self.outcome_definitions)
        )
        replication_adequate = len(self.corpus_slices) >= 2 or bool(self.replication_notes)

        return (
            self.preregistered
            and has_reviewer_experience_evidence
            and has_false_reassurance_analysis
            and has_design_documentation
            and replication_adequate
            and self.sample_size is not None
        )
