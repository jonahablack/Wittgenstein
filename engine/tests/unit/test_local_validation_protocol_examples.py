"""Loads and validates the local-validation example fixtures
(data/examples/local_validation/) against the real schemas and the real registry,
and cross-checks the fixture catalog (scenarios.json) against the vocabulary enums
introduced for the local-validation protocol (docs/local-validation-protocol.md).

This is deliberately a fixture/data-integrity test file, not a study-results test file:
it proves the example scenarios are well-formed and that
REP_SEGMENTATION_GRANULARITY_MISMATCH activates exactly where the catalog says it
should -- it does not assert any reviewer-study outcome, because no study has been run.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from wittgenstein.core.enums import AdjudicationOutcome, IntentSource, ReviewerAction
from wittgenstein.schemas.manifest import PipelineManifest
from wittgenstein.schemas.trace import QueryTrace
from wittgenstein.services.applicability_service import derive_risk_events

REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURE_DIR = REPO_ROOT / "data" / "examples" / "local_validation"
MECHANISM_ID = "REP_SEGMENTATION_GRANULARITY_MISMATCH"


def _load_scenarios() -> list[dict]:
    catalog = json.loads((FIXTURE_DIR / "scenarios.json").read_text())
    return catalog["scenarios"]


def _load_manifest(filename: str) -> PipelineManifest:
    return PipelineManifest.model_validate(json.loads((FIXTURE_DIR / "manifests" / filename).read_text()))


def _load_trace(filename: str) -> QueryTrace:
    return QueryTrace.model_validate(json.loads((FIXTURE_DIR / "traces" / filename).read_text()))


SCENARIOS = _load_scenarios()


class TestScenarioCatalogIsWellFormed:
    def test_catalog_has_eleven_scenarios(self):
        assert len(SCENARIOS) == 11

    @pytest.mark.parametrize("scenario", SCENARIOS, ids=[s["id"] for s in SCENARIOS])
    def test_every_scenario_references_files_that_exist_and_parse(self, scenario):
        manifest = _load_manifest(scenario["manifest_file"])
        trace = _load_trace(scenario["trace_file"])
        assert manifest.manifest_id
        assert trace.manifest_id == manifest.manifest_id

    @pytest.mark.parametrize("scenario", SCENARIOS, ids=[s["id"] for s in SCENARIOS])
    def test_expected_adjudication_outcome_is_a_real_enum_value(self, scenario):
        assert scenario["expected_adjudication_outcome"] in {o.value for o in AdjudicationOutcome}

    @pytest.mark.parametrize("scenario", SCENARIOS, ids=[s["id"] for s in SCENARIOS])
    def test_intent_source_is_a_real_enum_value(self, scenario):
        assert scenario["intent_source"] in {s.value for s in IntentSource}

    @pytest.mark.parametrize("scenario", SCENARIOS, ids=[s["id"] for s in SCENARIOS])
    def test_appropriate_reviewer_actions_are_real_enum_values(self, scenario):
        valid = {a.value for a in ReviewerAction}
        assert scenario["appropriate_reviewer_actions"], f"{scenario['id']} lists no reviewer actions"
        assert set(scenario["appropriate_reviewer_actions"]) <= valid

    def test_at_least_one_scenario_has_adjudication_not_applicable(self):
        # Requirement: factual adjudication is optional where no defensible ground
        # truth exists -- the catalog must actually contain such a case, not just
        # claim the capability in prose.
        not_applicable = [s for s in SCENARIOS if s["adjudication_applicable"] is False]
        assert len(not_applicable) >= 1
        assert not_applicable[0]["expected_adjudication_outcome"] == "requires_clarification"

    def test_at_least_one_scenario_has_an_unresolved_or_contested_outcome(self):
        contested = {"unresolved", "source_conflict", "version_dependent", "jurisdiction_dependent"}
        assert any(s["expected_adjudication_outcome"] in contested for s in SCENARIOS)

    def test_both_activating_and_non_activating_scenarios_are_present(self):
        activating = [s for s in SCENARIOS if s["mechanism_should_activate"]]
        non_activating = [s for s in SCENARIOS if not s["mechanism_should_activate"]]
        assert activating
        assert non_activating


class TestScenariosMatchActualMechanismBehavior:
    @pytest.mark.parametrize("scenario", SCENARIOS, ids=[s["id"] for s in SCENARIOS])
    def test_activation_matches_catalog_claim(self, registry, scenario):
        manifest = _load_manifest(scenario["manifest_file"])
        trace = _load_trace(scenario["trace_file"])
        result = derive_risk_events(registry, manifest, trace, include_disabled_for_audit=False)
        activated = any(e.mechanism_id == MECHANISM_ID for e in result.risk_events)
        assert activated == scenario["mechanism_should_activate"], (
            f"{scenario['id']}: catalog claims mechanism_should_activate="
            f"{scenario['mechanism_should_activate']}, actual={activated}"
        )

    def test_active_risk_events_retain_full_explainability_and_bounded_language(self, registry):
        # Requirement 14: every active risk event retains evidence status, transfer
        # level, trace trigger, bounded explanation, and reviewer action -- checked
        # across every activating scenario in the catalog, not just one hand-picked case.
        for scenario in SCENARIOS:
            if not scenario["mechanism_should_activate"]:
                continue
            manifest = _load_manifest(scenario["manifest_file"])
            trace = _load_trace(scenario["trace_file"])
            result = derive_risk_events(registry, manifest, trace, include_disabled_for_audit=False)
            events = [e for e in result.risk_events if e.mechanism_id == MECHANISM_ID]
            assert len(events) == 1, scenario["id"]
            event = events[0]
            assert event.epistemic_status is not None
            assert event.transfer_level is not None
            assert event.trace_trigger_id == "TT_REP_SEGMENTATION_GRANULARITY_MISMATCH_01"
            assert event.reviewer_explanation
            assert event.reviewer_action
            assert event.causal_claim_allowed is False

            assessment = next(a for a in result.applicable if a.failure_mechanism_id == MECHANISM_ID)
            assert "segmentation/evidence-boundary configuration" in assessment.allowed_claim_language, scenario[
                "id"
            ]
