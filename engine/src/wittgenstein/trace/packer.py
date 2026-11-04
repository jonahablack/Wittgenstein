"""Deterministic, programmatic context packing -- never an LLM decision
(docs/efficiency-and-processing-architecture.md, "CONTEXT PACKING"). Given a ranked
list of candidate items and a token budget, decides what is packed, omitted, or
truncated, and records exact prompt token positions -- the same
selected/omitted/truncated/compressed vocabulary `QueryTrace` already defines
(`docs/trace-spec.md`), this module is simply what *produces* those lists rather than
only analyzing them after the fact (that remains `trace/packing.py`'s job).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from wittgenstein.schemas.trace import ContextItem, PromptTokenSpan
from wittgenstein.trace.token_counting import TokenCounter, default_counter


@dataclass
class PackingResult:
    packed_context_items: list[ContextItem] = field(default_factory=list)
    omitted_context_items: list[ContextItem] = field(default_factory=list)
    compressed_context_items: list[ContextItem] = field(default_factory=list)
    prompt_token_spans: list[PromptTokenSpan] = field(default_factory=list)
    final_prompt: str = ""
    final_prompt_token_count: int = 0
    duplicate_or_redundant_item_ids: list[str] = field(default_factory=list)
    token_counting_method: str = ""


def pack_context(
    candidates: list[ContextItem],
    token_budget: int,
    *,
    counter: TokenCounter | None = None,
    separator: str = "\n\n",
) -> PackingResult:
    """Pack `candidates` (already rank-ordered by the caller -- this function never
    re-ranks) into `token_budget` tokens. Deterministic: the same candidates and budget
    always produce the same result. An item that does not fit in the remaining budget
    is omitted with `omission_reason="context_budget_exceeded"` -- never partially
    included without being recorded as such.

    Exact duplicate excerpts (after whitespace normalization) are flagged in
    `duplicate_or_redundant_item_ids` but are not auto-removed -- the caller/reviewer
    decides what to do with redundant content; this function only ever surfaces the
    fact.
    """

    counter = counter or default_counter()
    result = PackingResult(token_counting_method=counter.method)

    separator_tokens = counter.count(separator) if separator else 0
    remaining_budget = token_budget
    running_token_position = 0
    prompt_parts: list[str] = []
    seen_normalized_excerpts: dict[str, str] = {}

    for rank, item in enumerate(candidates, start=1):
        excerpt = item.excerpt or ""
        item_tokens = item.token_count if item.token_count is not None else counter.count(excerpt)
        needed = item_tokens + (separator_tokens if prompt_parts else 0)

        if needed > remaining_budget:
            omitted = item.model_copy(update={"omission_reason": "context_budget_exceeded"})
            result.omitted_context_items.append(omitted)
            continue

        normalized = " ".join(excerpt.split()).lower()
        if normalized and normalized in seen_normalized_excerpts:
            result.duplicate_or_redundant_item_ids.append(item.item_id)

        seen_normalized_excerpts[normalized] = item.item_id
        result.packed_context_items.append(item)
        prompt_parts.append(excerpt)
        start_token = running_token_position + (separator_tokens if len(prompt_parts) > 1 else 0)
        end_token = start_token + item_tokens
        result.prompt_token_spans.append(
            PromptTokenSpan(
                context_item_id=item.item_id,
                start_token=start_token,
                end_token=end_token,
                position_rank=rank,
            )
        )
        running_token_position = end_token
        remaining_budget -= needed

    result.final_prompt = separator.join(prompt_parts)
    result.final_prompt_token_count = running_token_position
    return result
