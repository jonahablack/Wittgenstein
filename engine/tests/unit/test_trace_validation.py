from __future__ import annotations

from datetime import UTC, datetime

from wittgenstein.schemas.trace import (
    AnswerClaim,
    AnswerSupportEdge,
    ContextItem,
    PromptTokenSpan,
    QueryTrace,
    SupportRequirement,
)
from wittgenstein.trace.validator import validate_trace

NOW = datetime(2026, 9, 2, tzinfo=UTC)


def _trace(**overrides) -> QueryTrace:
    base = dict(trace_id="T1", manifest_id="M1", query="q", query_timestamp=NOW, trace_status="complete")
    base.update(overrides)
    return QueryTrace(**base)


def test_unlogged_stage_is_none_not_empty_list():
    trace = _trace()
    assert trace.packed_context_items is None
    assert trace.selected_context_items is None


def test_logged_empty_stage_is_distinguishable_from_unlogged():
    trace = _trace(packed_context_items=[])
    assert trace.packed_context_items == []
    assert trace.packed_context_items is not None


def test_packed_item_not_in_selected_is_flagged():
    trace = _trace(
        selected_context_items=[ContextItem(item_id="i1")],
        packed_context_items=[ContextItem(item_id="i2")],
    )
    problems = validate_trace(trace)
    assert any("not present in selected_context_items" in p for p in problems)


def test_valid_lineage_has_no_problems():
    trace = _trace(
        selected_context_items=[ContextItem(item_id="i1")],
        packed_context_items=[ContextItem(item_id="i1")],
    )
    assert validate_trace(trace) == []


def test_dangling_support_edge_claim_is_flagged():
    trace = _trace(
        answer_claims=[AnswerClaim(claim_id="c1", text="x")],
        answer_support_edges=[AnswerSupportEdge(claim_id="c2", support_status="supported")],
    )
    problems = validate_trace(trace)
    assert any("unknown claim_id" in p for p in problems)


def test_prompt_token_span_end_before_start_is_flagged():
    trace = _trace(
        packed_context_items=[ContextItem(item_id="i1")],
        prompt_token_spans=[PromptTokenSpan(context_item_id="i1", start_token=10, end_token=5)],
    )
    problems = validate_trace(trace)
    assert any("end_token < start_token" in p for p in problems)


def test_multihop_requirement_without_ids_is_flagged():
    trace = _trace(support_requirement=SupportRequirement(is_multi_hop=True, required_support_item_ids=[]))
    problems = validate_trace(trace)
    assert any("required_support_item_ids is empty" in p for p in problems)
