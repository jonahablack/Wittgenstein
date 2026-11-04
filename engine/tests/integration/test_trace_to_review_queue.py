from __future__ import annotations

from fastapi.testclient import TestClient
from wittgenstein.api.app import app
from wittgenstein.core.enums import EpistemicStatus
from wittgenstein.services.applicability_service import derive_risk_events

client = TestClient(app)


class TestRiskDerivationDefaultsToActivatedMechanismsOnly:
    def test_default_output_excludes_disabled_mechanisms(self, registry, example_pair):
        manifest, trace = example_pair("parent_child_omitted_crossref")
        result = derive_risk_events(registry, manifest, trace, include_disabled_for_audit=False)
        # Every registered mechanism except PACK_OMISSION_OR_TRUNCATION (enabled_with_
        # manifest_gates) and REP_SEGMENTATION_GRANULARITY_MISMATCH (manifest_conditioned,
        # since the 2026-09-09 registry-governance decision -- docs/registry-governance.md)
        # is currently disabled pending evidence verification/promotion in this bootstrap
        # registry (see data/registry/README.md) -- so only those two can appear as a
        # default risk event.
        mechanism_ids = {e.mechanism_id for e in result.risk_events}
        assert mechanism_ids <= {"PACK_OMISSION_OR_TRUNCATION", "REP_SEGMENTATION_GRANULARITY_MISMATCH"}

    def test_audit_mode_includes_disabled_mechanisms_in_non_applicable_bucket(self, registry, example_pair):
        manifest, trace = example_pair("parent_child_omitted_crossref")
        result = derive_risk_events(registry, manifest, trace, include_disabled_for_audit=True)
        audited_ids = {a.failure_mechanism_id for a in result.audited_non_applicable}
        assert "RET_HARD_DISTRACTOR" in audited_ids or "REP_SEGMENTATION_GRANULARITY_MISMATCH" in audited_ids

    def test_every_risk_event_carries_full_explainability_fields(self, registry, example_pair):
        manifest, trace = example_pair("parent_child_omitted_crossref")
        result = derive_risk_events(registry, manifest, trace, include_disabled_for_audit=False)
        assert result.risk_events, "expected at least one default risk event for this scenario"
        for event in result.risk_events:
            assert event.observed_evidence
            assert event.reviewer_explanation
            assert event.reviewer_action
            assert event.transfer_level is not None
            assert event.epistemic_status is not None

    def test_trace_integrity_risk_event_never_allows_causal_claim(self, registry, example_pair):
        manifest, trace = example_pair("parent_child_omitted_crossref")
        result = derive_risk_events(registry, manifest, trace, include_disabled_for_audit=False)
        for event in result.risk_events:
            if event.epistemic_status == EpistemicStatus.TRACE_INTEGRITY_CONDITION:
                assert event.causal_claim_allowed is False


class TestRiskEventsApiEndpoint:
    def test_derive_endpoint_default_response_shape(self, example_pair):
        manifest, trace = example_pair("parent_child_omitted_crossref")
        response = client.post(
            "/risk-events/derive",
            json={
                "manifest": manifest.model_dump(mode="json"),
                "trace": trace.model_dump(mode="json"),
            },
        )
        assert response.status_code == 200
        body = response.json()
        assert "risk_events" in body
        assert "audited_non_applicable_assessments" not in body  # not requested

    def test_derive_endpoint_audit_mode_includes_non_applicable(self, example_pair):
        manifest, trace = example_pair("parent_child_omitted_crossref")
        response = client.post(
            "/risk-events/derive",
            json={
                "manifest": manifest.model_dump(mode="json"),
                "trace": trace.model_dump(mode="json"),
                "include_non_applicable_for_audit": True,
            },
        )
        assert response.status_code == 200
        assert "audited_non_applicable_assessments" in response.json()

    def test_response_never_contains_a_numeric_hallucination_probability_field(self, example_pair):
        manifest, trace = example_pair("parent_child_omitted_crossref")
        response = client.post(
            "/risk-events/derive",
            json={
                "manifest": manifest.model_dump(mode="json"),
                "trace": trace.model_dump(mode="json"),
            },
        )
        body_text = response.text.lower()
        assert "hallucination_probability" not in body_text
        assert "hallucination_score" not in body_text
