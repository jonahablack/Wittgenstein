"""Structural validation of a QueryTrace beyond what Pydantic's field types enforce.

Checks referential integrity across stage lists (e.g. an answer_support_edges entry
pointing at a context_item_id that doesn't exist anywhere in the trace) and basic
lineage sanity (a packed item must also appear among selected items). Returns a plain
list of human-readable problem strings rather than raising, so callers (CLI/API) can
decide how to report a non-empty list.
"""

from __future__ import annotations

from wittgenstein.schemas.trace import QueryTrace
from wittgenstein.trace.lineage import item_ids


def validate_trace(trace: QueryTrace) -> list[str]:
    problems: list[str] = []

    known_ids = (
        item_ids(trace.retrieval_candidates)
        | item_ids(trace.reranked_candidates)
        | item_ids(trace.selected_context_items)
        | item_ids(trace.packed_context_items)
        | item_ids(trace.omitted_context_items)
        | item_ids(trace.compressed_context_items)
    )

    if trace.packed_context_items is not None and trace.selected_context_items is not None:
        packed_ids = item_ids(trace.packed_context_items)
        selected_ids = item_ids(trace.selected_context_items)
        orphan_packed = packed_ids - selected_ids
        if orphan_packed:
            problems.append(
                "packed_context_items contains item id(s) not present in "
                f"selected_context_items: {sorted(orphan_packed)}. A packed item must have "
                "passed through selection."
            )

    for span in trace.prompt_token_spans:
        if span.context_item_id not in known_ids:
            problems.append(f"prompt_token_spans references unknown context_item_id {span.context_item_id!r}.")
        if span.end_token < span.start_token:
            problems.append(f"prompt_token_spans entry for {span.context_item_id!r} has end_token < start_token.")

    claim_ids = {c.claim_id for c in trace.answer_claims}
    for edge in trace.answer_support_edges:
        if edge.claim_id not in claim_ids:
            problems.append(f"answer_support_edges references unknown claim_id {edge.claim_id!r}.")
        for cid in edge.context_item_ids:
            if cid not in known_ids:
                problems.append(
                    f"answer_support_edges for claim {edge.claim_id!r} references unknown context_item_id {cid!r}."
                )

    for conflict in trace.context_conflicts:
        for cid in conflict.context_item_ids:
            if cid not in known_ids:
                problems.append(
                    f"context_conflicts {conflict.conflict_id!r} references unknown context_item_id {cid!r}."
                )

    addressed_ids = set(trace.conflict_ids_addressed_in_answer)
    conflict_ids = {c.conflict_id for c in trace.context_conflicts}
    unknown_addressed = addressed_ids - conflict_ids
    if unknown_addressed:
        problems.append(
            f"conflict_ids_addressed_in_answer references unknown conflict_id(s): {sorted(unknown_addressed)}."
        )

    if (
        trace.support_requirement is not None
        and trace.support_requirement.is_multi_hop
        and not trace.support_requirement.required_support_item_ids
    ):
        problems.append("support_requirement.is_multi_hop=true but required_support_item_ids is empty.")

    return problems
