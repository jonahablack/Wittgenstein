"""Pipeline-lineage helpers over a QueryTrace.

These exist specifically to prevent the collapses the project's design explicitly
forbids: "retrieved" is not "available to the generator," and "available to the
generator" is not "used correctly by the generator."
"""

from __future__ import annotations

from wittgenstein.schemas.trace import ContextItem, QueryTrace


def item_ids(items: list[ContextItem] | None) -> set[str]:
    return {i.item_id for i in items} if items is not None else set()


def was_retrieved(trace: QueryTrace, item_id: str) -> bool:
    return item_id in item_ids(trace.retrieval_candidates)


def was_selected(trace: QueryTrace, item_id: str) -> bool:
    return item_id in item_ids(trace.selected_context_items)


def was_packed(trace: QueryTrace, item_id: str) -> bool:
    """True only if the item actually reached the final prompt -- i.e. was available to
    the generator. Do not conflate with `was_selected` (selection precedes packing and
    can still be dropped by budget/compression before generation).
    """

    return item_id in item_ids(trace.packed_context_items)


def is_answer_supported(trace: QueryTrace, claim_id: str) -> bool | None:
    """True/False if a reviewer/pipeline judgment exists for this claim, else None
    (unreviewed) -- never coerced to False just because no edge was found, since an
    absent edge could mean "not yet reviewed," not "confirmed unsupported."
    """

    for edge in trace.answer_support_edges:
        if edge.claim_id == claim_id:
            if edge.support_status == "unknown":
                return None
            return edge.support_status == "supported"
    return None


def selected_but_not_packed(trace: QueryTrace) -> list[str]:
    """Items that were selected as relevant but never reached the packed context.

    This is the correct trace-level source for a PACK_OMISSION_OR_TRUNCATION signal --
    it is explicitly NOT the same claim as "the model ignored retrieved evidence" (that
    would conflate retrieval with packing, and packing with generator attention).
    """

    if trace.selected_context_items is None or trace.packed_context_items is None:
        return []
    packed_ids = item_ids(trace.packed_context_items)
    return [item.item_id for item in trace.selected_context_items if item.item_id not in packed_ids]


def stages_fully_logged(trace: QueryTrace) -> bool:
    return (
        trace.retrieval_candidates is not None
        and trace.selected_context_items is not None
        and trace.packed_context_items is not None
    )
