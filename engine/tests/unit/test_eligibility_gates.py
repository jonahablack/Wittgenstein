from __future__ import annotations

from datetime import UTC, datetime

from wittgenstein.matching.eligibility import evaluate_eligibility
from wittgenstein.schemas.manifest import (
    PipelineManifest,
    RetrievalManifest,
    SelectionManifest,
)
from wittgenstein.schemas.trace import (
    AnswerClaim,
    AnswerSupportEdge,
    ContextItem,
    QueryTrace,
    SupportRequirement,
)
from wittgenstein.trace.lineage import is_answer_supported, was_packed, was_retrieved

NOW = datetime(2026, 9, 2, tzinfo=UTC)


def _bare_manifest(**overrides) -> PipelineManifest:
    base = dict(manifest_id="M1", system_name="test", system_version="0.0.1", created_at=NOW)
    base.update(overrides)
    return PipelineManifest(**base)


def _bare_trace(**overrides) -> QueryTrace:
    base = dict(trace_id="T1", manifest_id="M1", query="q", query_timestamp=NOW, trace_status="complete")
    base.update(overrides)
    return QueryTrace(**base)


# ---------------------------------------------------------------------------------
# 1. Unknown manifest fields: no default assumption, result is insufficient info.
# ---------------------------------------------------------------------------------


class TestUnknownManifestFieldsYieldInsufficientInformation:
    def test_completely_bare_manifest_no_trace_is_insufficient_for_every_mechanism(self):
        manifest = _bare_manifest()
        for mechanism_id in [
            "RET_HARD_DISTRACTOR",
            "RET_MULTIHOP_SUPPORT_INCOMPLETE",
            "CTX_POSITION_SENSITIVE_USE",
            "REP_SEGMENTATION_GRANULARITY_MISMATCH",
            "PACK_OMISSION_OR_TRUNCATION",
            "GEN_CONTEXT_CONFLICT_UNRESOLVED",
            "GEN_UNSUPPORTED_DESPITE_CONTEXT",
        ]:
            result = evaluate_eligibility(mechanism_id, manifest, None)
            assert result.eligible is None, f"{mechanism_id} should be insufficient, got {result.eligible}"

    def test_no_default_assumption_about_reranker(self):
        manifest = _bare_manifest(selection_manifest=SelectionManifest(max_selected_items=3))
        result = evaluate_eligibility("RET_HARD_DISTRACTOR", manifest, None)
        # max_items known and >1, but trace absent -> still insufficient, not "eligible".
        assert result.eligible is None

    def test_no_default_assumption_about_compression(self):
        manifest = _bare_manifest()
        result = evaluate_eligibility("PACK_OMISSION_OR_TRUNCATION", manifest, None)
        assert result.eligible is None


# ---------------------------------------------------------------------------------
# 2. Hard gating.
# ---------------------------------------------------------------------------------


class TestHardGating:
    def test_position_risk_does_not_activate_for_single_short_packed_passage(self, example_pair):
        manifest, trace = example_pair("single_passage")
        result = evaluate_eligibility("CTX_POSITION_SENSITIVE_USE", manifest, trace)
        assert result.eligible is False

    def test_query_rewrite_dependent_mechanism_does_not_assume_drift_when_rewriting_absent(self):
        # No dedicated "query-rewrite drift" mechanism is seeded in this bootstrap
        # registry; RET_MULTIHOP_SUPPORT_INCOMPLETE is the closest manifest/trace
        # combination exercising query-rewrite-adjacent multi-hop retrieval. With
        # query rewriting disabled/absent and no support_requirement assessed, the
        # mechanism must not assume incompleteness -- it must report insufficient
        # information, not a false "violated" or "satisfied".
        manifest = _bare_manifest(retrieval_manifest=RetrievalManifest(query_transformation_enabled=False))
        trace = _bare_trace()
        result = evaluate_eligibility("RET_MULTIHOP_SUPPORT_INCOMPLETE", manifest, trace)
        assert result.eligible is None

    def test_compression_loss_mode_does_not_activate_without_compression_or_truncation(self, example_pair):
        manifest, trace = example_pair("single_passage")
        result = evaluate_eligibility("PACK_OMISSION_OR_TRUNCATION", manifest, trace)
        assert result.eligible is False

    def test_multihop_mode_does_not_activate_for_known_single_span_support(self):
        manifest = _bare_manifest()
        trace = _bare_trace(
            support_requirement=SupportRequirement(is_multi_hop=False),
            packed_context_items=[ContextItem(item_id="i1")],
        )
        result = evaluate_eligibility("RET_MULTIHOP_SUPPORT_INCOMPLETE", manifest, trace)
        assert result.eligible is False

    def test_distractor_mode_disqualified_when_only_one_item_can_be_packed(self):
        manifest = _bare_manifest(selection_manifest=SelectionManifest(max_selected_items=1))
        trace = _bare_trace(
            packed_context_items=[ContextItem(item_id="i1", is_query_related=True, is_answer_supporting=False)]
        )
        result = evaluate_eligibility("RET_HARD_DISTRACTOR", manifest, trace)
        assert result.eligible is False

    def test_segmentation_mismatch_disqualified_for_whole_document_unit(self):
        manifest = _bare_manifest(
            retrieval_manifest=RetrievalManifest(retrieval_unit="whole_document", chunking_method="none")
        )
        trace = _bare_trace(segment_boundary_dependency_flags=["some flag"])
        result = evaluate_eligibility("REP_SEGMENTATION_GRANULARITY_MISMATCH", manifest, trace)
        assert result.eligible is False


# ---------------------------------------------------------------------------------
# 3. Trace distinctions.
# ---------------------------------------------------------------------------------


class TestTraceDistinctions:
    def test_retrieved_but_not_packed_is_not_available_to_generator(self):
        item = ContextItem(item_id="i1")
        trace = _bare_trace(retrieval_candidates=[item], selected_context_items=[], packed_context_items=[])
        assert was_retrieved(trace, "i1") is True
        assert was_packed(trace, "i1") is False

    def test_gen_unsupported_only_considers_packed_supporting_material_not_candidates(self):
        # A candidate that is answer-supporting but never packed must not make
        # GEN_UNSUPPORTED_DESPITE_CONTEXT think supporting material was available.
        manifest = _bare_manifest()
        supporting_but_not_packed = ContextItem(item_id="i1", is_answer_supporting=True)
        trace = _bare_trace(
            retrieval_candidates=[supporting_but_not_packed],
            selected_context_items=[],
            packed_context_items=[],
            answer_claims=[AnswerClaim(claim_id="c1", text="claim")],
        )
        result = evaluate_eligibility("GEN_UNSUPPORTED_DESPITE_CONTEXT", manifest, trace)
        gate = next(r for r in result.gate_results if r.gate_id == "TO_GEN_UNSUPPORTED_supporting_material_packed")
        assert gate.status.value == "violated"

    def test_packed_evidence_with_no_support_edge_is_unreviewed_not_falsely_supported(self):
        trace = _bare_trace(
            packed_context_items=[ContextItem(item_id="i1", is_answer_supporting=True)],
            answer_claims=[AnswerClaim(claim_id="c1", text="claim")],
            answer_support_edges=[],
        )
        assert is_answer_supported(trace, "c1") is None  # not False -- genuinely unreviewed

    def test_explicit_unsupported_edge_is_distinct_from_unreviewed(self):
        trace = _bare_trace(
            answer_claims=[AnswerClaim(claim_id="c1", text="claim")],
            answer_support_edges=[AnswerSupportEdge(claim_id="c1", support_status="unsupported")],
        )
        assert is_answer_supported(trace, "c1") is False

    def test_hard_distractor_flag_distinct_from_random_irrelevant_noise(self):
        manifest = _bare_manifest(selection_manifest=SelectionManifest(max_selected_items=3))
        random_noise = ContextItem(item_id="noise", is_query_related=False, is_answer_supporting=False)
        trace = _bare_trace(packed_context_items=[random_noise])
        result = evaluate_eligibility("RET_HARD_DISTRACTOR", manifest, trace)
        # Random noise (not query-related) must not satisfy the distractor trace observable.
        gate = next(r for r in result.gate_results if r.gate_id == "TO_RET_HARD_DISTRACTOR_relatedness_known")
        assert gate.status.value == "violated"

        true_distractor = ContextItem(item_id="distractor", is_query_related=True, is_answer_supporting=False)
        trace2 = _bare_trace(packed_context_items=[true_distractor])
        result2 = evaluate_eligibility("RET_HARD_DISTRACTOR", manifest, trace2)
        gate2 = next(r for r in result2.gate_results if r.gate_id == "TO_RET_HARD_DISTRACTOR_relatedness_known")
        assert gate2.status.value == "satisfied"

    def test_answer_conflict_with_context_distinct_from_conflicting_context(self):
        # "conflicting context" (GEN_CONTEXT_CONFLICT_UNRESOLVED) is driven by
        # trace.context_conflicts; an answer merely contradicting one packed item
        # (support_status="contradicted") is a different, unrelated signal and must
        # not by itself make the conflict mechanism eligible.
        manifest = _bare_manifest(selection_manifest=SelectionManifest(max_selected_items=3))
        trace = _bare_trace(
            packed_context_items=[ContextItem(item_id="i1"), ContextItem(item_id="i2")],
            answer_claims=[AnswerClaim(claim_id="c1", text="claim")],
            answer_support_edges=[
                AnswerSupportEdge(claim_id="c1", context_item_ids=["i1"], support_status="contradicted")
            ],
            context_conflicts=[],
        )
        result = evaluate_eligibility("GEN_CONTEXT_CONFLICT_UNRESOLVED", manifest, trace)
        assert result.eligible is False
