"""Tests for the 2026-09-09 registry-governance decision on
REP_SEGMENTATION_GRANULARITY_MISMATCH's activation policy (docs/registry-governance.md).

Covers: the mechanism activates only under its five manifest+trace gate conditions
(never merely because chunking exists, the chunker is a particular kind, a passage is
short, or the answer is wrong); its risk event carries the exact bounded reviewer
language and no unsupported causal claim; its priority is capped below HIGH under
manifest_conditioned; and the new ActivationPolicy tiers behave correctly for other
policies (backward compatibility -- other mechanisms are unaffected).
"""

from __future__ import annotations

from datetime import UTC, datetime

from wittgenstein.core.enums import ActivationPolicy, EpistemicStatus, PriorityTier, TransferLevel
from wittgenstein.schemas.manifest import PipelineManifest, RetrievalManifest
from wittgenstein.schemas.trace import QueryTrace
from wittgenstein.services.applicability_service import _capped_priority_tier, derive_risk_events

NOW = datetime(2026, 9, 9, tzinfo=UTC)
MECHANISM_ID = "REP_SEGMENTATION_GRANULARITY_MISMATCH"


def _bare_manifest(**overrides) -> PipelineManifest:
    base = dict(manifest_id="M1", system_name="test", system_version="0.0.1", created_at=NOW)
    base.update(overrides)
    return PipelineManifest(**base)


def _bare_trace(**overrides) -> QueryTrace:
    base = dict(trace_id="T1", manifest_id="M1", query="q", query_timestamp=NOW, trace_status="complete")
    base.update(overrides)
    return QueryTrace(**base)


def _segmented_manifest(**overrides) -> PipelineManifest:
    base = dict(
        retrieval_manifest=RetrievalManifest(
            retrieval_unit="proposition", chunking_method="proposition_segmentation"
        )
    )
    base.update(overrides)
    return _bare_manifest(**base)


def _rep_segmentation_events(registry, manifest, trace, **kwargs):
    result = derive_risk_events(registry, manifest, trace, **kwargs)
    return [e for e in result.risk_events if e.mechanism_id == MECHANISM_ID], result


class TestActivatesOnlyUnderItsFiveGateConditions:
    def test_activates_for_matching_segmented_trace_with_cross_boundary_dependency(self, registry, example_pair):
        # (1) segmented units, (2) known chunking method/retrieval unit, (3)+(4) a
        # support relation crossing a segment boundary that is actually absent from
        # the packed path -- data/examples/{manifests,traces}/parent_child_omitted_crossref.json.
        manifest, trace = example_pair("parent_child_omitted_crossref")
        events, _ = _rep_segmentation_events(registry, manifest, trace)
        assert len(events) == 1

    def test_does_not_activate_for_whole_document_retrieval(self, registry):
        # Gate (1): no independently retrievable segmented units at all -- disqualified
        # even though a boundary-dependency flag is (implausibly) present in the trace.
        manifest = _bare_manifest(
            retrieval_manifest=RetrievalManifest(retrieval_unit="whole_document", chunking_method="none")
        )
        trace = _bare_trace(segment_boundary_dependency_flags=["a support relation crosses a boundary"])
        events, _ = _rep_segmentation_events(registry, manifest, trace)
        assert events == []

    def test_does_not_activate_when_segmentation_metadata_is_unknown(self, registry):
        # Gate (2)+(5): chunking_method/retrieval_unit unknown -> insufficient
        # information, never an assumed pass, regardless of trace content.
        manifest = _bare_manifest()
        trace = _bare_trace(segment_boundary_dependency_flags=["a support relation crosses a boundary"])
        events, _ = _rep_segmentation_events(registry, manifest, trace)
        assert events == []

    def test_does_not_activate_merely_because_chunking_is_present(self, registry):
        # Gates (1)+(2) satisfied, but no trace-level boundary dependency at all --
        # chunking existing is not sufficient on its own.
        manifest = _segmented_manifest()
        trace = _bare_trace()
        events, _ = _rep_segmentation_events(registry, manifest, trace)
        assert events == []

    def test_does_not_activate_without_an_observed_boundary_dependency(self, registry):
        # Trace stage instrumented but genuinely empty -- distinct from "not
        # instrumented" (None), and still correctly non-activating either way.
        manifest = _segmented_manifest()
        trace = _bare_trace(segment_boundary_dependency_flags=[])
        events, _ = _rep_segmentation_events(registry, manifest, trace)
        assert events == []

    def test_remains_separate_from_a_generic_answer_incorrectness_claim(self, registry):
        # This mechanism has no field that reads answer correctness at all -- an
        # incorrect-looking answer with no segmentation signal must not activate it.
        manifest = _segmented_manifest()
        trace = _bare_trace(answer="a wrong-looking answer", answer_claims=[])
        events, _ = _rep_segmentation_events(registry, manifest, trace)
        assert events == []


class TestRiskEventShapeAndBoundedLanguage:
    def test_risk_event_carries_full_explainability_and_bounded_language(self, registry, example_pair):
        manifest, trace = example_pair("parent_child_omitted_crossref")
        events, result = _rep_segmentation_events(registry, manifest, trace)
        assert len(events) == 1
        event = events[0]

        # evidence status + transfer level
        assert event.epistemic_status == EpistemicStatus.EXTERNALLY_ESTABLISHED
        assert event.transfer_level is not None

        # manifest-gate results (predicate-level ids/statuses embedded in the
        # rendered explanation) + trace trigger
        assert "MP_REP_SEG" in event.reviewer_explanation
        assert event.trace_trigger_id == "TT_REP_SEGMENTATION_GRANULARITY_MISMATCH_01"

        # bounded reviewer language, exactly as specified by the governance decision
        assessment = next(a for a in result.applicable if a.failure_mechanism_id == MECHANISM_ID)
        assert (
            "This trace exhibits a segmentation/evidence-boundary configuration under "
            "which segmentation-related retrieval or answer-quality degradation has "
            "been experimentally observed." in assessment.allowed_claim_language
        )

        # no unsupported causal claim
        assert event.causal_claim_allowed is False
        assert "Do not phrase this as having caused" in assessment.allowed_claim_language

        # prohibited phrasing never appears
        combined = (event.reviewer_explanation + " " + assessment.allowed_claim_language).lower()
        assert "the chunker caused" not in combined
        assert "this answer is wrong" not in combined
        assert "generally unsafe" not in combined

    def test_priority_capped_below_high_for_manifest_conditioned(self):
        # Even in the best-possible case (directly_matched + externally_established,
        # which _priority_tier alone would call HIGH), a MANIFEST_CONDITIONED
        # mechanism must never reach HIGH -- that requires TRIAGE_ENABLED promotion.
        capped = _capped_priority_tier(
            ActivationPolicy.MANIFEST_CONDITIONED,
            EpistemicStatus.EXTERNALLY_ESTABLISHED,
            TransferLevel.DIRECTLY_MATCHED,
        )
        assert capped == PriorityTier.MEDIUM

    def test_priority_uncapped_for_triage_enabled(self):
        # The cap is specific to MANIFEST_CONDITIONED -- a (hypothetical, not used by
        # any mechanism yet) TRIAGE_ENABLED mechanism keeps full HIGH priority.
        uncapped = _capped_priority_tier(
            ActivationPolicy.TRIAGE_ENABLED,
            EpistemicStatus.EXTERNALLY_ESTABLISHED,
            TransferLevel.DIRECTLY_MATCHED,
        )
        assert uncapped == PriorityTier.HIGH

    def test_priority_uncapped_for_existing_enabled_with_manifest_gates_policy(self):
        # Backward compatibility: PACK_OMISSION_OR_TRUNCATION's existing policy value
        # must be entirely unaffected by the new cap.
        uncapped = _capped_priority_tier(
            ActivationPolicy.ENABLED_WITH_MANIFEST_GATES,
            EpistemicStatus.EXTERNALLY_ESTABLISHED,
            TransferLevel.DIRECTLY_MATCHED,
        )
        assert uncapped == PriorityTier.HIGH


class TestOtherMechanismsRetainTheirExistingActivationPolicies:
    def test_only_rep_segmentation_and_pack_omission_are_non_disabled(self, registry):
        expected = {
            "PACK_OMISSION_OR_TRUNCATION": ActivationPolicy.ENABLED_WITH_MANIFEST_GATES,
            "REP_SEGMENTATION_GRANULARITY_MISMATCH": ActivationPolicy.MANIFEST_CONDITIONED,
        }
        for mechanism in registry.mechanisms.values():
            if mechanism.id in expected:
                assert mechanism.default_activation_policy == expected[mechanism.id]
            else:
                assert mechanism.default_activation_policy in (
                    ActivationPolicy.DISABLED_BY_DEFAULT_OR_RESEARCH_MODE,
                    ActivationPolicy.RETIRED,
                )
