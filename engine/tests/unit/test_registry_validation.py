from __future__ import annotations

from datetime import date, datetime

import pytest
from pydantic import ValidationError
from wittgenstein.core.enums import (
    ActivationPolicy,
    AdjudicationOutcome,
    EpistemicStatus,
    EvidenceDirection,
    EvidenceGrade,
    EvidenceSynthesis,
    IntentSource,
    LocalValidationStatus,
    PeerReviewStatus,
    PipelineFailureObject,
    PipelineStage,
    PriorityTier,
    QuoteType,
    ReviewerAction,
    StudyType,
    VerificationStatus,
)
from wittgenstein.registry.repository import Registry
from wittgenstein.registry.validator import RegistrySeedIntegrityError, validate_registry
from wittgenstein.schemas.evidence import EvidenceRecord, ExperimentalEnvelope
from wittgenstein.schemas.failure_mode import FailureMechanism
from wittgenstein.schemas.review import (
    AdjudicatedTraceEvidence,
    AlertFatigueEvidence,
    AutonomyAndTrustEvidence,
    BehavioralWorkflowEvidence,
    ContextualJudgmentEvidence,
    FalseReassuranceAnalysis,
    LocalValidationRecord,
    ReviewAction,
    RiskEvent,
)


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
        epistemic_status=EpistemicStatus.RESEARCH_HYPOTHESIS,
        default_evidence_grade=EvidenceGrade.E_HYPOTHESIS,
        default_activation_policy=ActivationPolicy.DISABLED_BY_DEFAULT_OR_RESEARCH_MODE,
        evidence_synthesis=EvidenceSynthesis.UNRESOLVED,
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
        full_citation="Some citation",
        title="Some title",
        authors=["A"],
        venue="Some venue",
        publication_year=2024,
        peer_review_status=PeerReviewStatus.PEER_REVIEWED,
        persistent_identifier=None,
        source_url=None,
        exact_quote="A verified quote.",
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


class TestFailureMechanismSelfValidation:
    def test_research_hypothesis_cannot_get_a_grade(self):
        with pytest.raises(ValidationError):
            _mechanism(
                epistemic_status=EpistemicStatus.RESEARCH_HYPOTHESIS,
                default_evidence_grade=EvidenceGrade.A1_DIRECT_CAUSAL_PEER_REVIEWED,
            )

    def test_research_hypothesis_requires_disabled_activation(self):
        with pytest.raises(ValidationError):
            _mechanism(
                epistemic_status=EpistemicStatus.RESEARCH_HYPOTHESIS,
                default_activation_policy=ActivationPolicy.ENABLED_BY_DEFAULT,
            )

    def test_valid_research_hypothesis_ok(self):
        m = _mechanism()
        assert m.epistemic_status == EpistemicStatus.RESEARCH_HYPOTHESIS

    def test_retired_status_requires_retired_policy(self):
        with pytest.raises(ValidationError):
            _mechanism(
                epistemic_status=EpistemicStatus.UNSUPPORTED_OR_RETIRED,
                default_activation_policy=ActivationPolicy.ENABLED_BY_DEFAULT,
            )


class TestEvidenceRecordSelfValidation:
    def test_verified_record_cannot_contain_todo(self):
        with pytest.raises(ValidationError):
            _evidence(exact_quote="TODO: verify against primary source")

    def test_unverified_record_may_contain_todo(self):
        e = _evidence(
            exact_quote="TODO: verify against primary source",
            verification_status=VerificationStatus.UNVERIFIED,
        )
        assert e.is_unverified_or_incomplete()

    def test_a_grade_requires_peer_reviewed(self):
        with pytest.raises(ValidationError):
            _evidence(
                evidence_grade=EvidenceGrade.A1_DIRECT_CAUSAL_PEER_REVIEWED,
                peer_review_status=PeerReviewStatus.PREPRINT,
            )

    def test_direction_is_required(self):
        base = dict(
            id="EV-TEST-001",
            failure_mechanism_id="TEST_MECHANISM",
            full_citation="Some citation",
            title="Some title",
            authors=["A"],
            venue="Some venue",
            publication_year=2024,
            peer_review_status=PeerReviewStatus.PEER_REVIEWED,
            persistent_identifier=None,
            source_url=None,
            exact_quote="A verified quote.",
            quote_location="Abstract",
            quote_type=QuoteType.FINDING_STATEMENT,
            study_type=StudyType.CAUSAL_INTERVENTION,
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
        with pytest.raises(ValidationError):
            EvidenceRecord(**base)  # direction omitted entirely, never defaulted


class TestLocalValidationRecordSelfValidation:
    def _record(self, **overrides) -> LocalValidationRecord:
        base = dict(
            id="LV-TEST-001",
            mechanism_id="TEST_MECHANISM",
            deployment_scope="acme-corp/prod-kb-v3",
            method="controlled intervention: rerun with/without candidate distractor",
            sample_size=40,
            result_summary="preliminary",
            causal_or_correlational="causal",
            reviewers=["alice"],
            date=date(2026, 1, 1),
            limitations="single reviewer, not yet blinded",
            external_evidence_status=EpistemicStatus.RESEARCH_HYPOTHESIS,
            deployment_priority=PriorityTier.MEDIUM,
        )
        base.update(overrides)
        return LocalValidationRecord(**base)

    def test_defaults_do_not_meet_promotion_bar(self):
        record = self._record()
        assert record.local_validation_status == LocalValidationStatus.PROPOSED
        assert record.meets_promotion_bar() is False

    def test_fully_specified_preregistered_record_meets_promotion_bar(self):
        record = self._record(
            local_validation_status=LocalValidationStatus.COMPLETED_SUPPORTS,
            preregistered=True,
            evaluation_split="held-out 20% of queries, sampled before the study ran",
            corpus_description="acme prod KB, 2026-08 snapshot",
            manifest_description="dense retrieval, top-8, no reranking",
            query_distribution_description="production query log, stratified by intent",
            label_source="two independent reviewers, adjudicated disagreements",
            precision=0.82,
            recall=0.74,
            reviewer_yield=0.9,
            uncertainty="95% CI [0.71, 0.90] on precision (n=40)",
        )
        assert record.meets_promotion_bar() is True

    def test_missing_preregistration_fails_promotion_bar_even_if_otherwise_complete(self):
        record = self._record(
            preregistered=False,
            evaluation_split="held-out split",
            corpus_description="desc",
            manifest_description="desc",
            query_distribution_description="desc",
            label_source="desc",
            precision=0.8,
            recall=0.8,
            reviewer_yield=0.8,
            uncertainty="desc",
        )
        assert record.meets_promotion_bar() is False

    def test_external_and_local_status_are_independent_fields(self):
        """A strong local result must never silently change the mechanism's own,
        separately-tracked external_evidence_status -- see docs/registry-governance.md."""

        record = self._record(
            external_evidence_status=EpistemicStatus.RESEARCH_HYPOTHESIS,
            local_validation_status=LocalValidationStatus.COMPLETED_SUPPORTS,
        )
        assert record.external_evidence_status == EpistemicStatus.RESEARCH_HYPOTHESIS
        assert record.local_validation_status == LocalValidationStatus.COMPLETED_SUPPORTS

    # ---- Req 1: factual adjudication is optional where no defensible target exists ----

    def test_adjudication_layer_can_be_marked_not_applicable(self):
        record = self._record(
            adjudicated_trace_evidence=AdjudicatedTraceEvidence(
                applicable=False, notes="contested/versioned material; no defensible single gold label"
            )
        )
        assert record.adjudicated_trace_evidence.applicable is False
        # Not requiring a universal gold label does not block the record's other layers.
        assert (
            record.meets_promotion_bar() is False
        )  # unrelated to adjudication -- still incomplete on its own axis

    # ---- Req 2: adjudicated outcomes and reviewer-experience outcomes stay separate ----

    def test_adjudicated_and_reviewer_experience_layers_are_independent(self):
        experience_only = self._record(
            adjudicated_trace_evidence=None,
            behavioral_workflow_evidence=BehavioralWorkflowEvidence(perceived_usefulness_mean=6.2),
        )
        assert experience_only.adjudicated_trace_evidence is None
        assert experience_only.behavioral_workflow_evidence.perceived_usefulness_mean == 6.2

        adjudication_only = self._record(
            adjudicated_trace_evidence=AdjudicatedTraceEvidence(
                applicable=True, material_support_issue_detection_rate=0.4
            ),
            behavioral_workflow_evidence=None,
        )
        assert adjudication_only.behavioral_workflow_evidence is None
        assert adjudication_only.adjudicated_trace_evidence.material_support_issue_detection_rate == 0.4

    # ---- Req 3: a factual disagreement can be unresolved / jurisdiction- or version-dependent ----

    def test_adjudication_outcome_vocabulary_distinguishes_contested_from_wrong(self):
        contested = {
            AdjudicationOutcome.SOURCE_CONFLICT,
            AdjudicationOutcome.VERSION_DEPENDENT,
            AdjudicationOutcome.JURISDICTION_DEPENDENT,
            AdjudicationOutcome.REQUIRES_CLARIFICATION,
            AdjudicationOutcome.REQUIRES_EXPERT_ESCALATION,
            AdjudicationOutcome.UNRESOLVED,
        }
        # These are not the same outcome as a factual miss -- both vocabularies are
        # members of the one enum, never collapsed into a single correct/incorrect bit.
        assert AdjudicationOutcome.UNSUPPORTED not in contested
        assert AdjudicationOutcome.CONTRADICTED not in contested
        assert contested <= set(AdjudicationOutcome)

    # ---- Req 4: local validation cannot alter external evidence grade ----

    def test_local_validation_record_has_no_evidence_grade_field(self):
        # LocalValidationRecord has no field that could touch EvidenceRecord.evidence_grade
        # at all -- that axis belongs only to externally-reviewed EvidenceRecords.
        assert "evidence_grade" not in LocalValidationRecord.model_fields
        assert "default_evidence_grade" not in LocalValidationRecord.model_fields

    # ---- Req 5: local validation cannot automatically set TRIAGE_ENABLED ----

    def test_meets_triage_promotion_bar_is_read_only_advisory(self):
        # Calling this method never mutates the record or returns anything but a bool;
        # there is no code path from a LocalValidationRecord to an ActivationPolicy
        # mutation anywhere in this schema.
        record = self._fully_specified_triage_candidate()
        result = record.meets_triage_promotion_bar()
        assert isinstance(result, bool)
        assert result is True
        # The record itself carries no activation_policy field to mutate.
        assert "default_activation_policy" not in LocalValidationRecord.model_fields
        assert "activation_policy" not in LocalValidationRecord.model_fields

    def _fully_specified_triage_candidate(self, **overrides) -> LocalValidationRecord:
        base = dict(
            preregistered=True,
            study_design="3-condition between-subjects; conditions 2 vs 3 primary comparison",
            reviewer_population="8 domain-familiar reviewers, non-expert",
            corpus_slices=["regulatory-filings-slice-a", "regulatory-filings-slice-b"],
            outcome_definitions={"perceived_usefulness_mean": "5-point Likert, docs/reviewer-measures.md"},
            sample_size=48,
            behavioral_workflow_evidence=BehavioralWorkflowEvidence(perceived_usefulness_mean=5.6),
            false_reassurance_analysis=FalseReassuranceAnalysis(observed=True, rate=0.05),
        )
        base.update(overrides)
        return self._record(**base)

    # ---- Req 6: missing reviewer-experience evidence blocks TRIAGE_ENABLED ----

    def test_missing_reviewer_experience_evidence_blocks_triage_eligibility(self):
        record = self._fully_specified_triage_candidate(
            reviewer_experience_evidence=None, behavioral_workflow_evidence=None
        )
        assert record.meets_triage_promotion_bar() is False

    # ---- Req 7: missing false-reassurance analysis blocks TRIAGE_ENABLED ----

    def test_missing_false_reassurance_analysis_blocks_triage_eligibility(self):
        record = self._fully_specified_triage_candidate(false_reassurance_analysis=None)
        assert record.meets_triage_promotion_bar() is False

    def test_false_reassurance_analysis_not_observed_also_blocks_triage_eligibility(self):
        record = self._fully_specified_triage_candidate(
            false_reassurance_analysis=FalseReassuranceAnalysis(observed=False)
        )
        assert record.meets_triage_promotion_bar() is False

    # ---- Req 8: deployment priority is separate from epistemic status ----

    def test_deployment_priority_independent_of_epistemic_status(self):
        # A LOW-priority deployment decision can coexist with a HIGH-status-implying
        # external_evidence_status, and vice versa -- neither field derives the other.
        record = self._record(
            external_evidence_status=EpistemicStatus.EXTERNALLY_ESTABLISHED,
            deployment_priority=PriorityTier.LOW,
        )
        assert record.external_evidence_status == EpistemicStatus.EXTERNALLY_ESTABLISHED
        assert record.deployment_priority == PriorityTier.LOW

    # ---- Req 9: a warning can be useful without asserting the answer is false ----

    def test_high_usefulness_result_does_not_require_asserting_the_answer_is_false(self):
        record = self._record(
            behavioral_workflow_evidence=BehavioralWorkflowEvidence(perceived_usefulness_mean=6.8)
        )
        # The record itself has no field asserting factual wrongness, and none is implied
        # by a high usefulness score -- usefulness and factual correctness are on
        # different layers (C vs. A) by construction.
        assert record.behavioral_workflow_evidence.perceived_usefulness_mean == 6.8
        assert record.adjudicated_trace_evidence is None

    # ---- Req 10: a negative reviewer-experience result can be recorded without ----
    # ---- deleting the external mechanism ----

    def test_negative_result_does_not_touch_the_registry_mechanism(self, registry):
        before = registry.mechanisms["REP_SEGMENTATION_GRANULARITY_MISMATCH"].model_copy(deep=True)
        negative = self._record(
            mechanism_id="REP_SEGMENTATION_GRANULARITY_MISMATCH",
            behavioral_workflow_evidence=BehavioralWorkflowEvidence(
                perceived_usefulness_mean=1.5, perceived_review_burden_mean=6.5
            ),
            local_validation_status=LocalValidationStatus.COMPLETED_DOES_NOT_SUPPORT,
        )
        assert negative.local_validation_status == LocalValidationStatus.COMPLETED_DOES_NOT_SUPPORT
        after = registry.mechanisms["REP_SEGMENTATION_GRANULARITY_MISMATCH"]
        assert after == before

    # ---- Req 11: alert burden and unnecessary escalation are measurable ----

    def test_alert_fatigue_evidence_is_measurable_and_internally_consistent(self):
        evidence = AlertFatigueEvidence(
            alerts_displayed_count=200,
            alerts_leading_to_meaningful_action_count=40,
            actionable_alert_rate=0.2,
            unnecessary_escalation_count=3,
            mental_workload_mean=3.1,
        )
        assert evidence.actionable_alert_rate == 0.2
        assert evidence.unnecessary_escalation_count == 3

    def test_alert_fatigue_evidence_rejects_inconsistent_actionable_rate(self):
        with pytest.raises(ValidationError):
            AlertFatigueEvidence(
                alerts_displayed_count=200,
                alerts_leading_to_meaningful_action_count=40,
                actionable_alert_rate=0.9,  # inconsistent with 40/200 = 0.2
            )

    # ---- Req 12: reviewer autonomy and override behavior are measurable ----

    def test_autonomy_and_trust_evidence_is_measurable(self):
        evidence = AutonomyAndTrustEvidence(
            perceived_autonomy_mean=5.4,
            override_or_reject_rate=0.12,
            encouraged_blind_acceptance_mean=1.8,
        )
        assert evidence.override_or_reject_rate == 0.12
        assert evidence.encouraged_blind_acceptance_mean == 1.8

    # ---- Req 13: user-stated / system-inferred / reviewer-confirmed / unresolved intent ----

    def test_intent_source_values_are_distinct(self):
        assert {s.value for s in IntentSource} == {
            "user_stated",
            "system_inferred",
            "reviewer_confirmed",
            "unresolved",
        }

    def test_contextual_judgment_and_reviewer_action_vocabularies_exist(self):
        # Sanity check that the vocabularies referenced by the local-validation protocol
        # docs are real, importable, and non-empty -- not just prose. 12, not 11: the
        # review-loop milestone (docs/review-loop-implementation-plan.md) added
        # OVERRIDE_RISK_PRIORITY as an additive member for the reviewer-action list
        # there ("override risk priority").
        assert len(list(ReviewerAction)) == 12
        evidence = ContextualJudgmentEvidence(
            jurisdiction_awareness_rate=0.5, missing_dependency_awareness_rate=0.3
        )
        assert evidence.jurisdiction_awareness_rate == 0.5


class TestReviewActionSelfValidation:
    def test_cannot_instruct_blind_acceptance(self):
        with pytest.raises(ValidationError):
            ReviewAction(
                id="RA_TEST",
                applicable_mechanism_ids=["TEST_MECHANISM"],
                prompt_text="Just accept it.",
                action_type="confirm_support_status",
                instructs_acceptance=True,
            )


class TestRiskEventSelfValidation:
    def test_causal_claim_requires_evidence_link(self):
        with pytest.raises(ValidationError):
            RiskEvent(
                risk_event_id="RISK-1",
                trace_id="TRACE-1",
                mechanism_id="TEST_MECHANISM",
                observed_evidence="observed",
                transfer_level="directly_matched",
                epistemic_status=EpistemicStatus.EXTERNALLY_ESTABLISHED,
                priority_tier="high",
                causal_claim_allowed=True,
                reviewer_explanation="explanation",
                reviewer_action="RA_TEST",
                source_evidence_links=[],
            )

    def test_trace_integrity_condition_cannot_claim_causality_without_evidence(self):
        with pytest.raises(ValidationError):
            RiskEvent(
                risk_event_id="RISK-1",
                trace_id="TRACE-1",
                mechanism_id="TEST_MECHANISM",
                observed_evidence="observed",
                transfer_level="directly_matched",
                epistemic_status=EpistemicStatus.TRACE_INTEGRITY_CONDITION,
                priority_tier="high",
                causal_claim_allowed=True,
                reviewer_explanation="explanation",
                reviewer_action="RA_TEST",
                source_evidence_links=[],
            )

    def test_non_causal_trace_integrity_condition_is_fine(self):
        event = RiskEvent(
            risk_event_id="RISK-1",
            trace_id="TRACE-1",
            mechanism_id="TEST_MECHANISM",
            observed_evidence="observed",
            transfer_level="directly_matched",
            epistemic_status=EpistemicStatus.TRACE_INTEGRITY_CONDITION,
            priority_tier="medium",
            causal_claim_allowed=False,
            reviewer_explanation="explanation",
            reviewer_action="RA_TEST",
            source_evidence_links=[],
        )
        assert event.causal_claim_allowed is False


class TestCrossRecordRegistryValidation:
    def test_externally_established_requires_a_grade_peer_reviewed_evidence(self):
        registry = Registry()
        registry.mechanisms["TEST_MECHANISM"] = _mechanism(
            epistemic_status=EpistemicStatus.EXTERNALLY_ESTABLISHED,
            default_evidence_grade=EvidenceGrade.A2_STRONG_COMPARATIVE_PEER_REVIEWED,
            default_activation_policy=ActivationPolicy.DISABLED_BY_DEFAULT_OR_RESEARCH_MODE,
        )
        # No evidence at all linked.
        with pytest.raises(RegistrySeedIntegrityError):
            validate_registry(registry)

    def test_externally_established_with_b_grade_only_fails(self):
        registry = Registry()
        registry.mechanisms["TEST_MECHANISM"] = _mechanism(
            epistemic_status=EpistemicStatus.EXTERNALLY_ESTABLISHED,
            default_activation_policy=ActivationPolicy.DISABLED_BY_DEFAULT_OR_RESEARCH_MODE,
        )
        registry.evidence["EV-TEST-001"] = _evidence(
            evidence_grade=EvidenceGrade.B1_MECHANISTIC_TRANSFER_PEER_REVIEWED
        )
        with pytest.raises(RegistrySeedIntegrityError):
            validate_registry(registry)

    def test_externally_established_with_qualifying_evidence_passes(self):
        """Path A of the two-path threshold rule: one closely-matched, RAG-native A1 study."""

        registry = Registry()
        registry.mechanisms["TEST_MECHANISM"] = _mechanism(
            epistemic_status=EpistemicStatus.EXTERNALLY_ESTABLISHED,
            default_activation_policy=ActivationPolicy.DISABLED_BY_DEFAULT_OR_RESEARCH_MODE,
        )
        registry.evidence["EV-TEST-001"] = _evidence(
            evidence_grade=EvidenceGrade.A1_DIRECT_CAUSAL_PEER_REVIEWED,
            experimental_envelope=ExperimentalEnvelope(rag_presence=True),
        )
        validate_registry(registry)  # should not raise

    def test_externally_established_single_a2_rag_evidence_insufficient(self):
        """A single A2-grade record is no longer enough on its own (docs/evidence-grading.md,
        "Evidence thresholds"): a single narrow benchmark must not be presented as a
        universal law. Needs either one A1, or >=2 independent qualifying records."""

        registry = Registry()
        registry.mechanisms["TEST_MECHANISM"] = _mechanism(
            epistemic_status=EpistemicStatus.EXTERNALLY_ESTABLISHED,
            default_activation_policy=ActivationPolicy.DISABLED_BY_DEFAULT_OR_RESEARCH_MODE,
        )
        registry.evidence["EV-TEST-001"] = _evidence(
            evidence_grade=EvidenceGrade.A2_STRONG_COMPARATIVE_PEER_REVIEWED,
            experimental_envelope=ExperimentalEnvelope(rag_presence=True),
        )
        with pytest.raises(RegistrySeedIntegrityError):
            validate_registry(registry)

    def test_externally_established_two_independent_a2_records_pass(self):
        """Path B of the two-path threshold rule: >=2 independent, broadly consistent
        A1/A2 studies, even with no single A1 among them."""

        registry = Registry()
        registry.mechanisms["TEST_MECHANISM"] = _mechanism(
            epistemic_status=EpistemicStatus.EXTERNALLY_ESTABLISHED,
            default_activation_policy=ActivationPolicy.DISABLED_BY_DEFAULT_OR_RESEARCH_MODE,
        )
        registry.evidence["EV-TEST-001"] = _evidence(
            evidence_grade=EvidenceGrade.A2_STRONG_COMPARATIVE_PEER_REVIEWED,
            experimental_envelope=ExperimentalEnvelope(rag_presence=True),
        )
        registry.evidence["EV-TEST-002"] = _evidence(
            id="EV-TEST-002",
            evidence_grade=EvidenceGrade.A2_STRONG_COMPARATIVE_PEER_REVIEWED,
            experimental_envelope=ExperimentalEnvelope(rag_presence=True),
        )
        validate_registry(registry)  # should not raise

    def test_externally_established_non_rag_evidence_never_qualifies(self):
        """A study conducted in a non-RAG setting can never by itself establish
        externally_established, however strong its grade -- it transfers only via
        manifest_conditioned_transfer (docs/evidence-grading.md, "Long-context transfer";
        mirrors CTX_POSITION_SENSITIVE_USE / "Lost in the Middle" in the seed registry)."""

        registry = Registry()
        registry.mechanisms["TEST_MECHANISM"] = _mechanism(
            epistemic_status=EpistemicStatus.EXTERNALLY_ESTABLISHED,
            default_activation_policy=ActivationPolicy.DISABLED_BY_DEFAULT_OR_RESEARCH_MODE,
        )
        registry.evidence["EV-TEST-001"] = _evidence(
            evidence_grade=EvidenceGrade.A1_DIRECT_CAUSAL_PEER_REVIEWED,
            experimental_envelope=ExperimentalEnvelope(rag_presence=False),
        )
        with pytest.raises(RegistrySeedIntegrityError):
            validate_registry(registry)

    def test_externally_established_refuting_evidence_does_not_count(self):
        """A record whose direction is not `supports` cannot by itself ground
        establishment, even if RAG-native and A1-grade."""

        registry = Registry()
        registry.mechanisms["TEST_MECHANISM"] = _mechanism(
            epistemic_status=EpistemicStatus.EXTERNALLY_ESTABLISHED,
            default_activation_policy=ActivationPolicy.DISABLED_BY_DEFAULT_OR_RESEARCH_MODE,
        )
        registry.evidence["EV-TEST-001"] = _evidence(
            evidence_grade=EvidenceGrade.A1_DIRECT_CAUSAL_PEER_REVIEWED,
            experimental_envelope=ExperimentalEnvelope(rag_presence=True),
            direction=EvidenceDirection.REFUTES,
        )
        with pytest.raises(RegistrySeedIntegrityError):
            validate_registry(registry)

    def test_activation_blocked_while_evidence_unverified(self):
        registry = Registry()
        registry.mechanisms["TEST_MECHANISM"] = _mechanism(
            epistemic_status=EpistemicStatus.EXTERNALLY_ESTABLISHED,
            default_activation_policy=ActivationPolicy.ENABLED_BY_DEFAULT,
        )
        registry.evidence["EV-TEST-001"] = _evidence(
            evidence_grade=EvidenceGrade.A1_DIRECT_CAUSAL_PEER_REVIEWED,
            experimental_envelope=ExperimentalEnvelope(rag_presence=True),
            verification_status=VerificationStatus.UNVERIFIED,
            exact_quote="TODO: verify against primary source",
        )
        with pytest.raises(RegistrySeedIntegrityError):
            validate_registry(registry)

    def test_disputed_evidence_is_treated_as_unverified(self):
        """A record left in an unresolved second-review disagreement is marked
        `disputed`, not `verified` -- and `is_unverified_or_incomplete()` (the method
        driving the activation-gating check) must treat `disputed` the same as
        `unverified`: never activation-eligible while a disagreement is unresolved."""

        record = _evidence(verification_status=VerificationStatus.DISPUTED)
        assert record.is_unverified_or_incomplete() is True

    def test_activation_blocked_by_single_disputed_record(self):
        """Prevention of activation from a single unresolved-disagreement record: even
        a single A1, RAG-native, supporting record cannot unlock non-disabled
        activation while its verification_status is `disputed` rather than
        `verified` -- mirrors test_activation_blocked_while_evidence_unverified but for
        the disputed case specifically (the second-review "unresolved_disagreement"
        outcome)."""

        registry = Registry()
        registry.mechanisms["TEST_MECHANISM"] = _mechanism(
            epistemic_status=EpistemicStatus.EXTERNALLY_ESTABLISHED,
            default_activation_policy=ActivationPolicy.ENABLED_BY_DEFAULT,
        )
        registry.evidence["EV-TEST-001"] = _evidence(
            evidence_grade=EvidenceGrade.A1_DIRECT_CAUSAL_PEER_REVIEWED,
            experimental_envelope=ExperimentalEnvelope(rag_presence=True),
            verification_status=VerificationStatus.DISPUTED,
        )
        with pytest.raises(RegistrySeedIntegrityError):
            validate_registry(registry)

    def test_trace_integrity_condition_may_activate_without_evidence(self):
        registry = Registry()
        registry.mechanisms["TEST_MECHANISM"] = _mechanism(
            epistemic_status=EpistemicStatus.TRACE_INTEGRITY_CONDITION,
            default_activation_policy=ActivationPolicy.ENABLED_WITH_MANIFEST_GATES,
        )
        validate_registry(registry)  # should not raise: no external evidence required

    def test_dangling_evidence_reference_fails(self):
        registry = Registry()
        registry.evidence["EV-TEST-001"] = _evidence(failure_mechanism_id="NONEXISTENT_MECHANISM")
        with pytest.raises(RegistrySeedIntegrityError):
            validate_registry(registry)


class TestSeedRegistryIntegrity:
    def test_seed_registry_loads_and_validates(self, registry):
        assert len(registry.mechanisms) == 18

    def test_every_research_hypothesis_is_disabled(self, registry):
        for m in registry.mechanisms.values():
            if m.epistemic_status == EpistemicStatus.RESEARCH_HYPOTHESIS:
                assert m.default_activation_policy == ActivationPolicy.DISABLED_BY_DEFAULT_OR_RESEARCH_MODE

    def test_no_established_mechanism_lacks_qualifying_evidence(self, registry):
        """Defensive/forward-looking: applies the full two-path threshold rule (one A1, or
        >=2 independent A1/A2, all RAG-native and direction=supports) to whatever the seed
        registry currently claims is externally_established -- currently zero mechanisms,
        since all three single-A2-record candidates were reclassified to
        manifest_conditioned_transfer (see docs/evidence-grading.md). This test exists so a
        future addition that violates the rule is caught here too, not only by the loader's
        own validate_registry() call."""

        for m in registry.mechanisms.values():
            if m.epistemic_status != EpistemicStatus.EXTERNALLY_ESTABLISHED:
                continue
            qualifying = [
                e
                for e in registry.evidence_for_mechanism(m.id)
                if e.peer_review_status == PeerReviewStatus.PEER_REVIEWED
                and e.evidence_grade
                in (
                    EvidenceGrade.A1_DIRECT_CAUSAL_PEER_REVIEWED,
                    EvidenceGrade.A2_STRONG_COMPARATIVE_PEER_REVIEWED,
                )
                and e.experimental_envelope.rag_presence is True
                and e.direction == EvidenceDirection.SUPPORTS
            ]
            has_a1 = any(e.evidence_grade == EvidenceGrade.A1_DIRECT_CAUSAL_PEER_REVIEWED for e in qualifying)
            assert has_a1 or len(qualifying) >= 2, (
                f"{m.id} is externally_established without meeting the two-path evidence "
                "threshold (one A1, or >=2 independent RAG-native supporting A1/A2 records)"
            )

    def test_all_evidence_backed_activation_is_currently_disabled_pending_verification(self, registry):
        """As of the 2026-09-09 second-review pass, several mechanisms now have verified
        evidence (see docs/literature-review-second-review-results.md) -- but reaching
        externally_established/manifest_conditioned_transfer with verified evidence does
        not by itself flip default_activation_policy. Every evidence-dependent mechanism
        must still be disabled, with exactly one deliberate exception:
        REP_SEGMENTATION_GRANULARITY_MISMATCH, whose manifest_conditioned policy was a
        separate, explicit 2026-09-09 registry-governance decision (see
        docs/registry-governance.md), not an automatic consequence of status or
        verification -- and even that exception is capped below full (triage_enabled)
        trust, never enabled_by_default."""

        evidence_dependent = {
            EpistemicStatus.EXTERNALLY_ESTABLISHED,
            EpistemicStatus.MANIFEST_CONDITIONED_TRANSFER,
        }
        deliberate_exceptions = {"REP_SEGMENTATION_GRANULARITY_MISMATCH": ActivationPolicy.MANIFEST_CONDITIONED}
        for m in registry.mechanisms.values():
            if m.epistemic_status not in evidence_dependent:
                continue
            if m.id in deliberate_exceptions:
                assert m.default_activation_policy == deliberate_exceptions[m.id]
            else:
                assert m.default_activation_policy == ActivationPolicy.DISABLED_BY_DEFAULT_OR_RESEARCH_MODE

    def test_rep_segmentation_now_externally_established_with_verified_evidence(self, registry):
        """Regression test locking in the 2026-09-09 literature-review + second-review
        outcome: REP_SEGMENTATION_GRANULARITY_MISMATCH is the first (and, as of this
        pass, only) mechanism to reach externally_established, backed by two
        independent, RAG-native, verified A2 records."""

        mechanism = registry.mechanisms["REP_SEGMENTATION_GRANULARITY_MISMATCH"]
        assert mechanism.epistemic_status == EpistemicStatus.EXTERNALLY_ESTABLISHED
        evidence = registry.evidence_for_mechanism("REP_SEGMENTATION_GRANULARITY_MISMATCH")
        assert len(evidence) == 2
        for e in evidence:
            assert e.verification_status == VerificationStatus.VERIFIED
            assert e.direction == EvidenceDirection.SUPPORTS
            assert e.experimental_envelope.rag_presence is True
            assert e.evidence_grade in (
                EvidenceGrade.A1_DIRECT_CAUSAL_PEER_REVIEWED,
                EvidenceGrade.A2_STRONG_COMPARATIVE_PEER_REVIEWED,
            )

    def test_rep_segmentation_activation_policy_is_manifest_conditioned_not_triage_enabled(self, registry):
        """2026-09-09 registry-governance decision (docs/registry-governance.md):
        externally_established plus verified evidence made REP_SEGMENTATION_GRANULARITY_MISMATCH
        activation-eligible, but that is necessary, not sufficient, for full trust. It
        moved from disabled to manifest_conditioned specifically -- displayed once its
        manifest+trace gates pass, but not enabled_by_default and not (yet)
        triage_enabled, which requires a separate LocalValidationRecord.reviewer_yield
        promotion this pass did not perform."""

        mechanism = registry.mechanisms["REP_SEGMENTATION_GRANULARITY_MISMATCH"]
        assert mechanism.default_activation_policy == ActivationPolicy.MANIFEST_CONDITIONED
        assert mechanism.default_activation_policy != ActivationPolicy.DISABLED_BY_DEFAULT_OR_RESEARCH_MODE
        assert mechanism.default_activation_policy != ActivationPolicy.ENABLED_BY_DEFAULT
        assert mechanism.default_activation_policy != ActivationPolicy.TRIAGE_ENABLED

    def test_preprint_graded_records_stay_below_a_grade_floor(self, registry):
        """Regression test for the two records whose peer-review status could not be
        confirmed (RET_MULTIHOP_SUPPORT_INCOMPLETE, GEN_UNSUPPORTED_DESPITE_CONTEXT):
        both must stay preprint/below-A-grade even after the second-review pass
        re-confirmed that classification via full-document re-reads."""

        for mechanism_id in ("RET_MULTIHOP_SUPPORT_INCOMPLETE", "GEN_UNSUPPORTED_DESPITE_CONTEXT"):
            evidence = registry.evidence_for_mechanism(mechanism_id)
            assert len(evidence) == 1
            record = evidence[0]
            assert record.peer_review_status == PeerReviewStatus.PREPRINT
            assert record.evidence_grade not in (
                EvidenceGrade.A1_DIRECT_CAUSAL_PEER_REVIEWED,
                EvidenceGrade.A2_STRONG_COMPARATIVE_PEER_REVIEWED,
            )

    def test_scope_mismatched_records_retain_null_direction(self, registry):
        """Regression test for the two records found to measure a related-but-not-
        identical construct to their mechanism's exact claim
        (GEN_CONTEXT_CONFLICT_UNRESOLVED, GEN_UNSUPPORTED_DESPITE_CONTEXT): both must
        stay direction=null rather than being forced to "supports", and both remain
        verified (extraction accuracy is independent of construct fit)."""

        for mechanism_id in ("GEN_CONTEXT_CONFLICT_UNRESOLVED", "GEN_UNSUPPORTED_DESPITE_CONTEXT"):
            evidence = registry.evidence_for_mechanism(mechanism_id)
            assert len(evidence) == 1
            record = evidence[0]
            assert record.direction == EvidenceDirection.NULL
            assert record.verification_status == VerificationStatus.VERIFIED
