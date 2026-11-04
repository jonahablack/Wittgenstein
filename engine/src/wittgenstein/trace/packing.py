"""Packing-stage distinctions: identifying omissions/truncations/compressions and their reasons."""

from __future__ import annotations

from dataclasses import dataclass

from wittgenstein.schemas.trace import ContextItem, QueryTrace
from wittgenstein.trace.lineage import selected_but_not_packed


@dataclass
class OmissionRecord:
    item_id: str
    reason: str | None
    found_in_omitted_list: bool
    found_in_compressed_list: bool


def identify_omissions(trace: QueryTrace) -> list[OmissionRecord]:
    """Identify selected items that never reached the packed context, with whatever
    reason metadata is available (never fabricated if absent -- `reason` stays None).
    """

    missing_ids = set(selected_but_not_packed(trace))
    if not missing_ids:
        return []

    omitted_by_id: dict[str, ContextItem] = (
        {i.item_id: i for i in trace.omitted_context_items} if trace.omitted_context_items else {}
    )
    compressed_by_id: dict[str, ContextItem] = (
        {i.item_id: i for i in trace.compressed_context_items} if trace.compressed_context_items else {}
    )

    records = []
    for item_id in missing_ids:
        omitted_item = omitted_by_id.get(item_id)
        compressed_item = compressed_by_id.get(item_id)
        reason = None
        if omitted_item is not None:
            reason = omitted_item.omission_reason
        elif compressed_item is not None:
            reason = compressed_item.omission_reason or "compressed"
        records.append(
            OmissionRecord(
                item_id=item_id,
                reason=reason,
                found_in_omitted_list=omitted_item is not None,
                found_in_compressed_list=compressed_item is not None,
            )
        )
    return records


def has_identifiable_omission(trace: QueryTrace) -> bool:
    """True only if at least one omission has *some* identifying trail (present in the
    omitted/compressed lists, or has a reason) -- a bare id mismatch with zero
    supporting metadata is treated conservatively as not yet identifiable.
    """

    return any(
        r.found_in_omitted_list or r.found_in_compressed_list or r.reason is not None
        for r in identify_omissions(trace)
    )
