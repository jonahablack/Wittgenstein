"""Programmatic, token-budget-enforcing context packing -- never an LLM decision
(docs/efficiency-and-processing-architecture.md, "CONTEXT PACKING").
"""

from __future__ import annotations

from wittgenstein.schemas.trace import ContextItem
from wittgenstein.trace.packer import pack_context
from wittgenstein.trace.token_counting import ApproximateCounter


def _item(item_id: str, text: str, rank: int) -> ContextItem:
    return ContextItem(item_id=item_id, excerpt=text, rank=rank)


def test_all_items_fit_when_budget_is_generous() -> None:
    items = [_item("a", "short text", 1), _item("b", "more short text", 2)]
    result = pack_context(items, token_budget=1000, counter=ApproximateCounter())
    assert [i.item_id for i in result.packed_context_items] == ["a", "b"]
    assert result.omitted_context_items == []


def test_items_beyond_budget_are_omitted_with_a_reason() -> None:
    items = [_item("a", "word " * 20, 1), _item("b", "word " * 20, 2), _item("c", "word " * 20, 3)]
    result = pack_context(items, token_budget=30, counter=ApproximateCounter())

    packed_ids = {i.item_id for i in result.packed_context_items}
    omitted_ids = {i.item_id for i in result.omitted_context_items}
    assert packed_ids | omitted_ids == {"a", "b", "c"}
    assert packed_ids.isdisjoint(omitted_ids)
    for omitted in result.omitted_context_items:
        assert omitted.omission_reason == "context_budget_exceeded"


def test_packing_is_deterministic_given_same_inputs() -> None:
    items = [_item("a", "alpha beta", 1), _item("b", "gamma delta", 2)]
    first = pack_context(items, token_budget=10, counter=ApproximateCounter())
    second = pack_context(items, token_budget=10, counter=ApproximateCounter())
    assert [i.item_id for i in first.packed_context_items] == [i.item_id for i in second.packed_context_items]
    assert first.final_prompt == second.final_prompt


def test_prompt_token_spans_cover_the_final_prompt_without_overlap() -> None:
    items = [_item("a", "alpha beta gamma", 1), _item("b", "delta epsilon zeta", 2)]
    result = pack_context(items, token_budget=1000, counter=ApproximateCounter())

    spans = sorted(result.prompt_token_spans, key=lambda s: s.start_token)
    for previous, current in zip(spans, spans[1:], strict=False):
        assert current.start_token >= previous.end_token
    for span in spans:
        assert span.end_token <= result.final_prompt_token_count


def test_duplicate_excerpts_are_flagged_not_dropped() -> None:
    items = [_item("a", "the same excerpt text", 1), _item("b", "the same excerpt text", 2)]
    result = pack_context(items, token_budget=1000, counter=ApproximateCounter())

    assert len(result.packed_context_items) == 2  # never silently dropped
    assert "b" in result.duplicate_or_redundant_item_ids


def test_final_prompt_contains_only_packed_excerpts() -> None:
    items = [_item("a", "alpha", 1), _item("b", "beta", 2), _item("c", "gamma", 3)]
    result = pack_context(items, token_budget=2, counter=ApproximateCounter())

    for packed in result.packed_context_items:
        assert packed.excerpt in result.final_prompt
    for omitted in result.omitted_context_items:
        assert omitted.excerpt not in result.final_prompt


def test_empty_candidate_list_produces_empty_result() -> None:
    result = pack_context([], token_budget=100, counter=ApproximateCounter())
    assert result.packed_context_items == []
    assert result.omitted_context_items == []
    assert result.final_prompt == ""
    assert result.final_prompt_token_count == 0


def test_token_counting_method_is_recorded() -> None:
    result = pack_context([_item("a", "text", 1)], token_budget=100, counter=ApproximateCounter())
    assert result.token_counting_method == "approximate_chars_div_4"
