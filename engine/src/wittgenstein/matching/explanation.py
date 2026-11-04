"""Render reviewer-facing explanation text and enforce allowed-vs-prohibited claim
language per epistemic status.

This is the single choke point where epistemic status is translated into words a
human reads -- every other module deals in typed enums and structured data. Keeping
the language logic here means there is exactly one place to audit for overclaiming.
"""

from __future__ import annotations

from dataclasses import dataclass

from wittgenstein.core.enums import EpistemicStatus, EvidenceGrade, StudyType, TransferLevel
from wittgenstein.matching.transferability import EnvelopeComparison
from wittgenstein.schemas.applicability import EligibilityGateResult
from wittgenstein.schemas.evidence import EvidenceRecord
from wittgenstein.schemas.failure_mode import FailureMechanism

_A_GRADES = {
    EvidenceGrade.A1_DIRECT_CAUSAL_PEER_REVIEWED,
    EvidenceGrade.A2_STRONG_COMPARATIVE_PEER_REVIEWED,
}

#: Per-mechanism bounded reviewer language, overriding the generic epistemic-status
#: text in _CLAIM_LANGUAGE below. Reserved for mechanisms whose product-facing wording
#: must be precisely scoped (e.g. by a registry-governance decision on activation
#: policy) rather than the generic per-status sentence -- most mechanisms use no
#: override and get the generic text. See docs/registry-governance.md.
_MECHANISM_BOUNDED_CLAIM_LANGUAGE: dict[str, str] = {
    "REP_SEGMENTATION_GRANULARITY_MISMATCH": (
        "This trace exhibits a segmentation/evidence-boundary configuration under "
        "which segmentation-related retrieval or answer-quality degradation has "
        "been experimentally observed."
    ),
}

_CLAIM_LANGUAGE = {
    EpistemicStatus.EXTERNALLY_ESTABLISHED: (
        "This mechanism is externally established in peer-reviewed research. The condition "
        "observed here is consistent with that known pattern; review this specific instance "
        "before treating it as a confirmed cause of any answer error."
    ),
    EpistemicStatus.MANIFEST_CONDITIONED_TRANSFER: (
        "This mechanism is established in a related experimental setting and transfers to "
        "this system only under specific manifest conditions. Those conditions are met (or "
        "partially met) here. This is a risk to review, not proof that a specific answer "
        "error occurred."
    ),
    EpistemicStatus.TRACE_INTEGRITY_CONDITION: (
        "This is a directly observed condition in the pipeline trace. It does not, by "
        "itself, establish that this condition caused an answer error."
    ),
    EpistemicStatus.RESEARCH_HYPOTHESIS: (
        "This is an unproven, research-hypothesis-stage review cue, not an established RAG "
        "failure mode. It is surfaced only in research/audit mode."
    ),
    EpistemicStatus.LOCALLY_VALIDATED: (
        "This mechanism has local validation evidence collected in this deployment's own "
        "testing. That local result does not constitute a universal external claim."
    ),
    EpistemicStatus.UNSUPPORTED_OR_RETIRED: (
        "This mechanism has been retired or found unsupported and should not be surfaced."
    ),
}


@dataclass
class RenderedExplanation:
    explanation: str
    allowed_claim_language: str
    causal_claim_allowed: bool


def _causal_claim_allowed(
    mechanism: FailureMechanism,
    transfer_level: TransferLevel,
    evidence_records: list[EvidenceRecord],
) -> bool:
    if mechanism.epistemic_status != EpistemicStatus.EXTERNALLY_ESTABLISHED:
        return False
    if transfer_level not in (
        TransferLevel.DIRECTLY_MATCHED,
        TransferLevel.MECHANISTICALLY_MATCHED,
    ):
        return False
    return any(
        e.study_type == StudyType.CAUSAL_INTERVENTION
        and e.evidence_grade in _A_GRADES
        and e.verification_status.value == "verified"
        for e in evidence_records
    )


def render_explanation(
    mechanism: FailureMechanism,
    gate_results: list[EligibilityGateResult],
    transfer_level: TransferLevel,
    comparison: EnvelopeComparison,
    evidence_records: list[EvidenceRecord],
) -> RenderedExplanation:
    causal_ok = _causal_claim_allowed(mechanism, transfer_level, evidence_records)

    gate_lines = "; ".join(f"{r.gate_id}={r.status.value} ({r.reason})" for r in gate_results)
    dims = (
        f"matching dimensions: {comparison.matching_dimensions or 'none'}; "
        f"mismatching dimensions: {comparison.mismatching_dimensions or 'none'}; "
        f"unknown dimensions: {comparison.unknown_dimensions or 'none'}"
    )
    evidence_note = (
        f"Linked evidence: {[e.id for e in evidence_records]}."
        if evidence_records
        else "No evidence record is currently linked; this is a trace-observed condition only."
    )

    explanation = (
        f"{mechanism.canonical_name} ({mechanism.id}): observed condition, not a confirmed cause. "
        f"Gate evaluation: {gate_lines}. Transfer level: {transfer_level.value} ({dims}). "
        f"{evidence_note}"
    )

    allowed = _MECHANISM_BOUNDED_CLAIM_LANGUAGE.get(mechanism.id, _CLAIM_LANGUAGE[mechanism.epistemic_status])
    if not causal_ok:
        allowed = allowed + " Do not phrase this as having caused the observed answer error."

    return RenderedExplanation(
        explanation=explanation, allowed_claim_language=allowed, causal_claim_allowed=causal_ok
    )
