"""Adaptive-set-size measurement (diagnostic only, never a default behavior change)
-- docs/evidence-set-real-corpus-diagnostics-plan.md §9. Fixtures 9-12 from
"FIXTURES AND TESTS": two-item incomplete composition with a third item available;
size-3 diagnostic run; a redundant third item; missing evidence outside the pool.
"""

from __future__ import annotations

from wittgenstein.evidence_set_diagnostics.runner import (
    MAX_DIAGNOSTIC_SIZE3_COMBINATIONS,
    _size3_diagnostic,
)
from wittgenstein.review.claim_linking import compare_claim_to_candidate
from wittgenstein.review.evidence_set import construct_evidence_set
from wittgenstein.schemas.trace import AnswerClaim, ContextItem

_CLAIM = AnswerClaim(claim_id="c1", text="Class III widgets in Zone A under Program Year 2024 must be tested.")
_ITEM_CLASS = ContextItem(item_id="class-item", excerpt="Class III widgets must be tested.", rank=1)
_ITEM_ZONE = ContextItem(
    item_id="zone-item", excerpt="This requirement applies only to widgets operating in Zone A.", rank=2
)
_ITEM_VERSION = ContextItem(
    item_id="version-item", excerpt="This requirement is in effect for Program Year 2024.", rank=3
)
_ITEM_REDUNDANT = ContextItem(
    item_id="redundant-item", excerpt="This requirement applies only to widgets operating in Zone A.", rank=4
)
_ITEM_UNRELATED = ContextItem(
    item_id="unrelated-item", excerpt="Facility maintenance logs must be retained for five years.", rank=5
)


def _run_default(packed_items: list[ContextItem]):
    comparisons = [compare_claim_to_candidate(_CLAIM, item) for item in packed_items]
    evidence_set, metrics = construct_evidence_set(_CLAIM, packed_items, comparisons, trace_id="t1")
    return evidence_set, metrics, comparisons


# Fixture 9: two-item incomplete composition, with a third item available in the pool.
def test_09_two_item_incomplete_with_third_available() -> None:
    packed_items = [_ITEM_CLASS, _ITEM_ZONE, _ITEM_VERSION]
    evidence_set, metrics, comparisons = _run_default(packed_items)
    assert evidence_set is not None
    # class+zone is found first (smaller/first valid combo) and leaves the version
    # component uncovered -- exactly the "settles for an incomplete size-2 set" property
    # docs/multi-passage-evidence-plan.md's known limitation describes.
    diagnostic = _size3_diagnostic(
        _CLAIM, packed_items, comparisons, evidence_set, metrics, run_size3=False, trace_id="t1"
    )
    assert diagnostic is not None
    assert diagnostic.candidate_pool_size == 3
    assert diagnostic.size3_combination_count == 1
    assert diagnostic.size3_search_run is False  # run_size3=False -> never actually searched


# Fixture 10: size-3 diagnostic run (opted in) resolves what size-2 left incomplete.
def test_10_size3_diagnostic_run_resolves_the_gap() -> None:
    packed_items = [_ITEM_CLASS, _ITEM_ZONE, _ITEM_VERSION]
    evidence_set, metrics, comparisons = _run_default(packed_items)
    assert evidence_set is not None
    assert evidence_set.relationship_status.value != "composite_support_candidate"

    diagnostic = _size3_diagnostic(
        _CLAIM, packed_items, comparisons, evidence_set, metrics, run_size3=True, trace_id="t1"
    )
    assert diagnostic is not None
    assert diagnostic.size3_search_run is True
    assert diagnostic.warning is not None
    assert "never used in normal demo/review flow" in diagnostic.warning
    assert diagnostic.size3_member_context_item_ids is not None
    assert set(diagnostic.size3_member_context_item_ids) == {"class-item", "zone-item", "version-item"}
    assert diagnostic.size3_relationship_status == "composite_support_candidate"


# Fixture 11: a redundant third item (duplicates the zone item) adds nothing new.
def test_11_redundant_third_item() -> None:
    packed_items = [_ITEM_CLASS, _ITEM_ZONE, _ITEM_REDUNDANT]
    evidence_set, metrics, comparisons = _run_default(packed_items)
    assert evidence_set is not None
    diagnostic = _size3_diagnostic(
        _CLAIM, packed_items, comparisons, evidence_set, metrics, run_size3=True, trace_id="t1"
    )
    assert diagnostic is not None
    if diagnostic.size3_search_run:
        # The redundant item never becomes part of the chosen set -- it supplies
        # nothing zone-item doesn't already supply.
        assert "redundant-item" not in (diagnostic.size3_member_context_item_ids or [])


# Fixture 12: evidence needed to fully cover the claim is missing from the candidate
# pool entirely (no item ever mentions Program Year 2024) -- stays uncovered even with
# the size-3 diagnostic search.
def test_12_missing_evidence_outside_candidate_pool() -> None:
    packed_items = [_ITEM_CLASS, _ITEM_ZONE, _ITEM_UNRELATED]
    evidence_set, metrics, comparisons = _run_default(packed_items)
    assert evidence_set is not None
    diagnostic = _size3_diagnostic(
        _CLAIM, packed_items, comparisons, evidence_set, metrics, run_size3=True, trace_id="t1"
    )
    assert diagnostic is not None
    if diagnostic.size3_search_run:
        assert diagnostic.size3_relationship_status != "composite_support_candidate"


def test_size3_search_skipped_above_the_diagnostic_safety_bound() -> None:
    """A pool large enough that C(pool, 3) exceeds the safety bound must never
    actually run the search -- only the closed-form estimate is reported, with an
    explicit warning explaining why.
    """

    # math.comb(n, 3) > 500 once n >= 17.
    packed_items = [_ITEM_CLASS, _ITEM_ZONE, _ITEM_VERSION] + [
        ContextItem(item_id=f"filler-{i}", excerpt="Facility maintenance logs must be retained.", rank=4 + i)
        for i in range(15)
    ]
    evidence_set, metrics, comparisons = _run_default(packed_items)
    diagnostic = _size3_diagnostic(
        _CLAIM, packed_items, comparisons, evidence_set, metrics, run_size3=True, trace_id="t1"
    )
    assert diagnostic is not None
    assert diagnostic.size3_combination_count > MAX_DIAGNOSTIC_SIZE3_COMBINATIONS
    assert diagnostic.size3_search_run is False
    assert diagnostic.warning is not None
    assert "exceeds the diagnostic safety bound" in diagnostic.warning


def test_size3_diagnostic_none_when_construction_not_attempted() -> None:
    """A claim already resolved by direct single-passage support never gets a size-3
    diagnostic -- there is nothing to diagnose about set size when no set was ever
    needed.
    """

    direct_claim = AnswerClaim(claim_id="c2", text="Class III widgets must be tested.")
    packed_items = [_ITEM_CLASS]
    comparisons = [compare_claim_to_candidate(direct_claim, item) for item in packed_items]
    evidence_set, metrics = construct_evidence_set(direct_claim, packed_items, comparisons, trace_id="t1")
    assert evidence_set is None
    assert metrics.attempted is False

    diagnostic = _size3_diagnostic(
        direct_claim, packed_items, comparisons, evidence_set, metrics, run_size3=True, trace_id="t1"
    )
    assert diagnostic is None
