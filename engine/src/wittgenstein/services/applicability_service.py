"""Orchestrates eligibility + transferability + explanation into an ApplicabilityAssessment,
and derives RiskEvents from a manifest/trace pair.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from wittgenstein.core.enums import (
    ActivationPolicy,
    ConfidenceTier,
    EpistemicStatus,
    PriorityTier,
    TransferLevel,
)
from wittgenstein.core.identifiers import new_assessment_id, new_risk_event_id
from wittgenstein.matching.eligibility import evaluate_eligibility
from wittgenstein.matching.explanation import render_explanation
from wittgenstein.matching.transferability import (
    EnvelopeComparison,
    best_transfer_across_evidence,
    confidence_for,
)
from wittgenstein.profiling.manifest_profile import build_envelope
from wittgenstein.registry.repository import Registry
from wittgenstein.schemas.applicability import ApplicabilityAssessment
from wittgenstein.schemas.manifest import PipelineManifest
from wittgenstein.schemas.review import RiskEvent
from wittgenstein.schemas.trace import QueryTrace


def _priority_tier(epistemic_status: EpistemicStatus, transfer_level: TransferLevel) -> PriorityTier:
    if (
        transfer_level == TransferLevel.DIRECTLY_MATCHED
        and epistemic_status == EpistemicStatus.EXTERNALLY_ESTABLISHED
    ):
        return PriorityTier.HIGH
    if transfer_level in (TransferLevel.DIRECTLY_MATCHED, TransferLevel.MECHANISTICALLY_MATCHED):
        return PriorityTier.MEDIUM
    if transfer_level == TransferLevel.PARTIALLY_MATCHED:
        return PriorityTier.LOW
    return PriorityTier.INFORMATIONAL


def _capped_priority_tier(
    policy: ActivationPolicy, epistemic_status: EpistemicStatus, transfer_level: TransferLevel
) -> PriorityTier:
    """`_priority_tier`, capped below `PriorityTier.HIGH` for activation policies that
    have not yet earned full (`TRIAGE_ENABLED`) reviewer-priority trust.

    A `MANIFEST_CONDITIONED` mechanism can be `externally_established` and reach
    `directly_matched` transfer -- evidence-wise, that is exactly what `_priority_tier`
    treats as `HIGH` -- but evidence status alone does not certify that this specific
    mechanism is trustworthy for queue ordering in a specific deployment; that requires
    a `LocalValidationRecord.reviewer_yield`-backed promotion to `TRIAGE_ENABLED`. See
    docs/registry-governance.md, "Default activation is distinct from evidence status".
    """

    tier = _priority_tier(epistemic_status, transfer_level)
    if policy in _PRIORITY_CAPPED and tier == PriorityTier.HIGH:
        return PriorityTier.MEDIUM
    return tier


def assess_mechanism(
    registry: Registry,
    mechanism_id: str,
    manifest: PipelineManifest,
    trace: QueryTrace | None,
) -> ApplicabilityAssessment:
    mechanism = registry.mechanism(mechanism_id)
    eligibility = evaluate_eligibility(mechanism_id, manifest, trace)
    evidence_records = registry.evidence_for_mechanism(mechanism_id)
    manifest_env = build_envelope(manifest, trace)

    best_evidence = None
    if eligibility.eligible is False:
        transfer_level = TransferLevel.NOT_APPLICABLE
        comparison = EnvelopeComparison([], [], [])
    elif eligibility.eligible is None:
        transfer_level = TransferLevel.INSUFFICIENT_MANIFEST_INFORMATION
        comparison = EnvelopeComparison([], [], [])
    elif mechanism.epistemic_status == EpistemicStatus.TRACE_INTEGRITY_CONDITION:
        # No external empirical envelope to transfer from -- for this status the
        # mechanism's evidence IS the directly observed trace condition itself, so
        # evidence-envelope comparison (which is about transferring an *external
        # study's* setting) does not apply, even if a placeholder EvidenceRecord is
        # linked for literature-search tracking purposes. See docs/evidence-grading.md
        # for why this is the one case TransferLevel.DIRECTLY_MATCHED is used without
        # an evidence-envelope comparison.
        transfer_level = TransferLevel.DIRECTLY_MATCHED
        comparison = EnvelopeComparison([], [], [])
    else:
        transfer_level, comparison, best_evidence = best_transfer_across_evidence(manifest_env, evidence_records)

    rendered = render_explanation(
        mechanism, eligibility.gate_results, transfer_level, comparison, evidence_records
    )

    if transfer_level == TransferLevel.NOT_APPLICABLE:
        confidence = ConfidenceTier.HIGH
    elif transfer_level == TransferLevel.INSUFFICIENT_MANIFEST_INFORMATION:
        confidence = ConfidenceTier.INSUFFICIENT_DATA
    elif mechanism.epistemic_status == EpistemicStatus.TRACE_INTEGRITY_CONDITION and best_evidence is None:
        confidence = ConfidenceTier.HIGH
    else:
        confidence = confidence_for(comparison)

    review_action_ids = [
        ra.id for ra in registry.review_actions.values() if mechanism_id in ra.applicable_mechanism_ids
    ]

    return ApplicabilityAssessment(
        assessment_id=new_assessment_id(),
        failure_mechanism_id=mechanism_id,
        evidence_record_ids=[e.id for e in evidence_records],
        manifest_id=manifest.manifest_id,
        trace_id_optional=trace.trace_id if trace is not None else None,
        eligibility_gate_results=eligibility.gate_results,
        transfer_level=transfer_level,
        matching_dimensions=comparison.matching_dimensions,
        mismatching_dimensions=comparison.mismatching_dimensions,
        unknown_dimensions=comparison.unknown_dimensions,
        explanation=rendered.explanation,
        allowed_claim_language=rendered.allowed_claim_language,
        recommended_review_action_ids=review_action_ids,
        confidence=confidence,
        created_at=datetime.now(UTC),
    )


@dataclass
class RiskDerivationResult:
    applicable: list[ApplicabilityAssessment]
    audited_non_applicable: list[ApplicabilityAssessment]
    risk_events: list[RiskEvent]


_NON_ACTIVATABLE = {ActivationPolicy.DISABLED_BY_DEFAULT_OR_RESEARCH_MODE, ActivationPolicy.RETIRED}
#: Evaluated and logged (still produces an ApplicabilityAssessment) but never
#: contributes a priority-bearing RiskEvent -- observability only, distinct from
#: _NON_ACTIVATABLE, which skips evaluation entirely outside audit mode.
_NEVER_PRIORITY_BEARING = {ActivationPolicy.SHADOW}
#: Displayed once eligible, but not yet fully trusted for queue ordering: capped below
#: PriorityTier.HIGH until promoted to TRIAGE_ENABLED via local reviewer-yield
#: validation (docs/registry-governance.md).
_PRIORITY_CAPPED = {ActivationPolicy.MANIFEST_CONDITIONED}
_APPLICABLE_LEVELS = {
    TransferLevel.DIRECTLY_MATCHED,
    TransferLevel.MECHANISTICALLY_MATCHED,
    TransferLevel.PARTIALLY_MATCHED,
}


def derive_risk_events(
    registry: Registry,
    manifest: PipelineManifest,
    trace: QueryTrace,
    include_disabled_for_audit: bool = False,
) -> RiskDerivationResult:
    """Deterministically evaluate every mechanism with a registered evaluator.

    By default, only mechanisms whose default_activation_policy permits activation are
    considered -- this is what keeps unverified/hypothesis mechanisms out of default
    output. `include_disabled_for_audit=True` additionally evaluates disabled
    mechanisms, clearly labeled, for audit reporting.
    """

    from wittgenstein.matching.eligibility import MECHANISM_EVALUATORS

    applicable: list[ApplicabilityAssessment] = []
    audited_non_applicable: list[ApplicabilityAssessment] = []
    risk_events: list[RiskEvent] = []

    for mechanism_id, mechanism in registry.mechanisms.items():
        if mechanism_id not in MECHANISM_EVALUATORS:
            continue
        is_active_by_default = mechanism.default_activation_policy not in _NON_ACTIVATABLE
        if not is_active_by_default and not include_disabled_for_audit:
            continue

        assessment = assess_mechanism(registry, mechanism_id, manifest, trace)
        policy = mechanism.default_activation_policy
        is_priority_bearing = is_active_by_default and policy not in _NEVER_PRIORITY_BEARING

        if assessment.transfer_level in _APPLICABLE_LEVELS and is_priority_bearing:
            applicable.append(assessment)
            trigger = next(iter(registry.triggers_for_mechanism(mechanism_id)), None)
            observed = "; ".join(
                r.reason for r in assessment.eligibility_gate_results if r.status.value == "satisfied"
            )
            priority_tier = _capped_priority_tier(policy, mechanism.epistemic_status, assessment.transfer_level)
            risk_events.append(
                RiskEvent(
                    risk_event_id=new_risk_event_id(),
                    trace_id=trace.trace_id,
                    mechanism_id=mechanism_id,
                    trace_trigger_id=trigger.id if trigger else None,
                    observed_evidence=observed or "See eligibility_gate_results in the linked assessment.",
                    transfer_level=assessment.transfer_level,
                    epistemic_status=mechanism.epistemic_status,
                    priority_tier=priority_tier,
                    causal_claim_allowed=(
                        "Do not phrase this as having caused" not in assessment.allowed_claim_language
                    ),
                    reviewer_explanation=assessment.explanation,
                    reviewer_action=(
                        assessment.recommended_review_action_ids[0]
                        if assessment.recommended_review_action_ids
                        else "RA_GENERIC_REVIEW_REQUIRED"
                    ),
                    source_evidence_links=assessment.evidence_record_ids,
                )
            )
        else:
            audited_non_applicable.append(assessment)

    return RiskDerivationResult(
        applicable=applicable,
        audited_non_applicable=audited_non_applicable,
        risk_events=risk_events,
    )
