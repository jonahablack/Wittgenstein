from __future__ import annotations

from fastapi.testclient import TestClient
from wittgenstein.api.app import app
from wittgenstein.core.enums import TransferLevel
from wittgenstein.services.applicability_service import assess_mechanism

client = TestClient(app)


class TestServiceLevelMatching:
    def test_single_passage_disqualifies_position_and_distractor(self, registry, example_pair):
        manifest, trace = example_pair("single_passage")
        position = assess_mechanism(registry, "CTX_POSITION_SENSITIVE_USE", manifest, trace)
        distractor = assess_mechanism(registry, "RET_HARD_DISTRACTOR", manifest, trace)
        assert position.transfer_level == TransferLevel.NOT_APPLICABLE
        assert distractor.transfer_level == TransferLevel.NOT_APPLICABLE

    def test_multi_passage_scenario_surfaces_distractor(self, registry, example_pair):
        manifest, trace = example_pair("multi_passage_rerank_budget")
        distractor = assess_mechanism(registry, "RET_HARD_DISTRACTOR", manifest, trace)
        assert distractor.transfer_level != TransferLevel.NOT_APPLICABLE
        gate_reasons = [g.reason for g in distractor.eligibility_gate_results]
        assert any("item-2" in r for r in gate_reasons)

    def test_multi_passage_scenario_surfaces_position_sensitivity(self, registry, example_pair):
        manifest, trace = example_pair("multi_passage_rerank_budget")
        position = assess_mechanism(registry, "CTX_POSITION_SENSITIVE_USE", manifest, trace)
        assert position.transfer_level != TransferLevel.NOT_APPLICABLE
        assert position.transfer_level != TransferLevel.INSUFFICIENT_MANIFEST_INFORMATION

    def test_parent_child_scenario_surfaces_omission_and_segmentation(self, registry, example_pair):
        manifest, trace = example_pair("parent_child_omitted_crossref")
        omission = assess_mechanism(registry, "PACK_OMISSION_OR_TRUNCATION", manifest, trace)
        segmentation = assess_mechanism(registry, "REP_SEGMENTATION_GRANULARITY_MISMATCH", manifest, trace)
        assert omission.transfer_level == TransferLevel.DIRECTLY_MATCHED
        assert segmentation.transfer_level != TransferLevel.NOT_APPLICABLE

    def test_parent_child_omission_is_never_causal(self, registry, example_pair):
        manifest, trace = example_pair("parent_child_omitted_crossref")
        omission = assess_mechanism(registry, "PACK_OMISSION_OR_TRUNCATION", manifest, trace)
        assert "Do not phrase this as having caused" in omission.allowed_claim_language

    def test_compression_scenario_surfaces_omission(self, registry, example_pair):
        manifest, trace = example_pair("compression_enabled")
        omission = assess_mechanism(registry, "PACK_OMISSION_OR_TRUNCATION", manifest, trace)
        assert omission.transfer_level == TransferLevel.DIRECTLY_MATCHED

    def test_query_rewriting_multihop_scenario_surfaces_conflict(self, registry, example_pair):
        manifest, trace = example_pair("query_rewriting_multihop")
        conflict = assess_mechanism(registry, "GEN_CONTEXT_CONFLICT_UNRESOLVED", manifest, trace)
        assert conflict.transfer_level != TransferLevel.NOT_APPLICABLE
        assert "conflict-1" in conflict.explanation or "time_version" in conflict.explanation


class TestApiLevelMatching:
    def test_applicability_assess_endpoint_single_mechanism(self, example_pair):
        manifest, trace = example_pair("single_passage")
        response = client.post(
            "/applicability/assess",
            json={
                "manifest": manifest.model_dump(mode="json"),
                "trace": trace.model_dump(mode="json"),
                "mechanism_id": "CTX_POSITION_SENSITIVE_USE",
            },
        )
        assert response.status_code == 200
        assessments = response.json()["assessments"]
        assert len(assessments) == 1
        assert assessments[0]["transfer_level"] == "not_applicable"

    def test_applicability_assess_endpoint_unknown_mechanism_404(self, example_pair):
        manifest, trace = example_pair("single_passage")
        response = client.post(
            "/applicability/assess",
            json={"manifest": manifest.model_dump(mode="json"), "mechanism_id": "NOT_REAL"},
        )
        assert response.status_code == 404
