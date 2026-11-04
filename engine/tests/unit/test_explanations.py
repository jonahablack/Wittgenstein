from __future__ import annotations

from datetime import date, datetime

from wittgenstein.core.enums import (
    ActivationPolicy,
    EpistemicStatus,
    EvidenceDirection,
    EvidenceGrade,
    EvidenceSynthesis,
    GateResultStatus,
    PeerReviewStatus,
    PipelineFailureObject,
    PipelineStage,
    QuoteType,
    StudyType,
    TransferLevel,
    VerificationStatus,
)
from wittgenstein.matching.explanation import render_explanation
from wittgenstein.matching.transferability import EnvelopeComparison
from wittgenstein.schemas.applicability import EligibilityGateResult, GateKind
from wittgenstein.schemas.evidence import EvidenceRecord, ExperimentalEnvelope
from wittgenstein.schemas.failure_mode import FailureMechanism


def _mechanism(**overrides) -> FailureMechanism:
    base = dict(
        id="TEST_MECHANISM",
        canonical_name="Test mechanism",
        short_description="desc",
        causal_claim="claim",
        pipeline_stage=PipelineStage.PACKED_CONTEXT_ITEMS,
        failure_object=PipelineFailureObject.ANSWER_CORRECTNESS,
        necessary_causal_ingredients=["a"],
        known_boundary_conditions=["b"],
        epistemic_status=EpistemicStatus.EXTERNALLY_ESTABLISHED,
        default_evidence_grade=EvidenceGrade.A2_STRONG_COMPARATIVE_PEER_REVIEWED,
        default_activation_policy=ActivationPolicy.DISABLED_BY_DEFAULT_OR_RESEARCH_MODE,
        evidence_synthesis=EvidenceSynthesis.LIMITED,
        tags=[],
        created_at=datetime(2026, 1, 1),
        updated_at=datetime(2026, 1, 1),
        registry_version="0.1.0",
    )
    base.update(overrides)
    return FailureMechanism(**base)


def _evidence(**overrides) -> EvidenceRecord:
    base = dict(
        id="EV-TEST-001",
        failure_mechanism_id="TEST_MECHANISM",
        full_citation="citation",
        title="title",
        authors=["A"],
        venue="venue",
        publication_year=2024,
        peer_review_status=PeerReviewStatus.PEER_REVIEWED,
        persistent_identifier=None,
        source_url=None,
        exact_quote="verified quote",
        quote_location="Abstract",
        quote_type=QuoteType.FINDING_STATEMENT,
        study_type=StudyType.CAUSAL_INTERVENTION,
        direction=EvidenceDirection.SUPPORTS,
        task="task",
        dataset_or_corpus="dataset",
        experimental_envelope=ExperimentalEnvelope(),
        intervention_or_comparison="intervention",
        outcome_metrics=["metric"],
        effect_size_text=None,
        statistical_evidence=None,
        stated_limitations="limitations",
        evidence_grade=EvidenceGrade.A2_STRONG_COMPARATIVE_PEER_REVIEWED,
        extraction_reviewer="reviewer",
        extraction_date=date(2026, 1, 1),
        verification_status=VerificationStatus.VERIFIED,
    )
    base.update(overrides)
    return EvidenceRecord(**base)


_EMPTY_COMPARISON = EnvelopeComparison([], [], [])
_GATE = EligibilityGateResult(
    gate_id="G1",
    gate_kind=GateKind.REQUIRED_MANIFEST,
    status=GateResultStatus.SATISFIED,
    reason="ok",
)


class TestCausalClaimGating:
    def test_established_plus_causal_evidence_plus_directly_matched_allows_causal_language(self):
        mechanism = _mechanism(epistemic_status=EpistemicStatus.EXTERNALLY_ESTABLISHED)
        evidence = _evidence(
            study_type=StudyType.CAUSAL_INTERVENTION,
            evidence_grade=EvidenceGrade.A1_DIRECT_CAUSAL_PEER_REVIEWED,
        )
        rendered = render_explanation(
            mechanism, [_GATE], TransferLevel.DIRECTLY_MATCHED, _EMPTY_COMPARISON, [evidence]
        )
        assert rendered.causal_claim_allowed is True
        assert "Do not phrase this as having caused" not in rendered.allowed_claim_language

    def test_established_without_causal_study_type_disallows_causal_language(self):
        mechanism = _mechanism(epistemic_status=EpistemicStatus.EXTERNALLY_ESTABLISHED)
        evidence = _evidence(study_type=StudyType.OBSERVATIONAL_BENCHMARK)
        rendered = render_explanation(
            mechanism, [_GATE], TransferLevel.DIRECTLY_MATCHED, _EMPTY_COMPARISON, [evidence]
        )
        assert rendered.causal_claim_allowed is False
        assert "Do not phrase this as having caused" in rendered.allowed_claim_language

    def test_trace_integrity_condition_never_allows_causal_language(self):
        mechanism = _mechanism(
            epistemic_status=EpistemicStatus.TRACE_INTEGRITY_CONDITION,
            default_evidence_grade=EvidenceGrade.D_LOCAL_EMPIRICAL,
        )
        evidence = _evidence(
            study_type=StudyType.CAUSAL_INTERVENTION,
            evidence_grade=EvidenceGrade.A1_DIRECT_CAUSAL_PEER_REVIEWED,
        )
        rendered = render_explanation(
            mechanism, [_GATE], TransferLevel.DIRECTLY_MATCHED, _EMPTY_COMPARISON, [evidence]
        )
        assert rendered.causal_claim_allowed is False

    def test_research_hypothesis_never_allows_causal_language(self):
        mechanism = _mechanism(
            epistemic_status=EpistemicStatus.RESEARCH_HYPOTHESIS,
            default_evidence_grade=EvidenceGrade.E_HYPOTHESIS,
            evidence_synthesis=EvidenceSynthesis.UNRESOLVED,
        )
        rendered = render_explanation(mechanism, [_GATE], TransferLevel.NOT_APPLICABLE, _EMPTY_COMPARISON, [])
        assert rendered.causal_claim_allowed is False
        assert "unproven, research-hypothesis-stage review cue" in rendered.allowed_claim_language

    def test_unverified_evidence_never_supports_causal_claim(self):
        mechanism = _mechanism(epistemic_status=EpistemicStatus.EXTERNALLY_ESTABLISHED)
        evidence = _evidence(
            study_type=StudyType.CAUSAL_INTERVENTION,
            evidence_grade=EvidenceGrade.A1_DIRECT_CAUSAL_PEER_REVIEWED,
            verification_status=VerificationStatus.UNVERIFIED,
        )
        rendered = render_explanation(
            mechanism, [_GATE], TransferLevel.DIRECTLY_MATCHED, _EMPTY_COMPARISON, [evidence]
        )
        assert rendered.causal_claim_allowed is False

    def test_partially_matched_transfer_never_allows_causal_claim(self):
        mechanism = _mechanism(epistemic_status=EpistemicStatus.EXTERNALLY_ESTABLISHED)
        evidence = _evidence(
            study_type=StudyType.CAUSAL_INTERVENTION,
            evidence_grade=EvidenceGrade.A1_DIRECT_CAUSAL_PEER_REVIEWED,
        )
        rendered = render_explanation(
            mechanism, [_GATE], TransferLevel.PARTIALLY_MATCHED, _EMPTY_COMPARISON, [evidence]
        )
        assert rendered.causal_claim_allowed is False


class TestExplanationContent:
    def test_explanation_includes_gate_reasons_and_transfer_level(self):
        mechanism = _mechanism()
        rendered = render_explanation(mechanism, [_GATE], TransferLevel.PARTIALLY_MATCHED, _EMPTY_COMPARISON, [])
        assert "G1=satisfied" in rendered.explanation
        assert "partially_matched" in rendered.explanation

    def test_no_evidence_notes_trace_observed_condition_only(self):
        mechanism = _mechanism(epistemic_status=EpistemicStatus.TRACE_INTEGRITY_CONDITION)
        rendered = render_explanation(mechanism, [_GATE], TransferLevel.DIRECTLY_MATCHED, _EMPTY_COMPARISON, [])
        assert "trace-observed condition only" in rendered.explanation
