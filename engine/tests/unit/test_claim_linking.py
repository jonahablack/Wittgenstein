"""Claim-to-evidence linking: a programmatic, pre-review candidate classification,
never a final verdict (docs/review-loop-implementation-plan.md §3;
docs/claim-linking-improvement-plan.md for the field-comparison engine `link_claim`
now delegates to). Test categories 7, 11.
"""

from __future__ import annotations

from wittgenstein.core.enums import ClaimSupportCandidateStatus
from wittgenstein.review.claim_linking import link_claim, link_claims
from wittgenstein.schemas.trace import AnswerClaim, ContextItem


def _item(item_id: str, excerpt: str) -> ContextItem:
    return ContextItem(item_id=item_id, excerpt=excerpt, rank=1)


def test_high_overlap_and_matching_fields_yields_direct_support_candidate() -> None:
    claim = AnswerClaim(claim_id="c1", text="A Class I widget must pass the Load Stress Test at a 95% threshold.")
    item = _item("i1", "A Class I widget must pass the Load Stress Test at a 95% threshold, per Section 3.")
    edge = link_claim(claim, [item])
    assert edge.candidate_support_status == ClaimSupportCandidateStatus.DIRECT_SUPPORT_CANDIDATE
    assert edge.context_item_ids == ["i1"]


def test_low_overlap_yields_no_support_edge_found() -> None:
    claim = AnswerClaim(claim_id="c1", text="Widgets are typically blue or green.")
    item = _item("i1", "Facility registration expires after five years.")
    edge = link_claim(claim, [item])
    assert edge.candidate_support_status == ClaimSupportCandidateStatus.NO_SUPPORT_EDGE_FOUND
    assert edge.context_item_ids == []


def test_no_packed_items_yields_no_support_edge_found() -> None:
    claim = AnswerClaim(claim_id="c1", text="A Class I widget must pass the Load Stress Test.")
    edge = link_claim(claim, [])
    assert edge.candidate_support_status == ClaimSupportCandidateStatus.NO_SUPPORT_EDGE_FOUND


def test_empty_claim_text_yields_unresolved() -> None:
    claim = AnswerClaim(claim_id="c1", text="")
    item = _item("i1", "Some evidence text.")
    edge = link_claim(claim, [item])
    assert edge.candidate_support_status == ClaimSupportCandidateStatus.UNRESOLVED


def test_negation_mismatch_yields_contradiction_candidate() -> None:
    """A single-source negation mismatch is a contradiction_candidate (rule D) --
    CONFLICT_CANDIDATE is now reserved for genuine multi-source disagreement (rule E),
    never a single (claim, candidate) pair.
    """

    claim = AnswerClaim(claim_id="c1", text="A Class I widget is not exempt from testing.")
    item = _item("i1", "A Class I widget is exempt from testing under Exemption C.")
    edge = link_claim(claim, [item])
    assert edge.candidate_support_status == ClaimSupportCandidateStatus.CONTRADICTION_CANDIDATE


def test_incompatible_frequency_yields_contradiction_not_partial_support() -> None:
    """The exact smoke-003 regression this milestone fixes: topical/lexical overlap
    must not be conflated with evidential support when a specific field (here,
    frequency) is explicitly incompatible.
    """

    claim = AnswerClaim(claim_id="c1", text="Class III widgets must be inspected every 6 months.")
    item = _item("i1", "Class III widgets must be inspected once per Program Year.")
    edge = link_claim(claim, [item])
    assert edge.candidate_support_status not in (
        ClaimSupportCandidateStatus.DIRECT_SUPPORT_CANDIDATE,
        ClaimSupportCandidateStatus.PARTIAL_SUPPORT_CANDIDATE,
    )
    assert edge.candidate_support_status in (
        ClaimSupportCandidateStatus.CONTRADICTION_CANDIDATE,
        ClaimSupportCandidateStatus.QUALIFICATION_REQUIRED,
        ClaimSupportCandidateStatus.UNRESOLVED,
        ClaimSupportCandidateStatus.NO_SUPPORT_EDGE_FOUND,
    )


def test_never_asserts_final_support_status() -> None:
    """Never converts a programmatic linking outcome into a final "supported"/
    "unsupported"/"contradicted" support_status -- that field stays reserved for a
    reviewer's judgment.
    """

    claim = AnswerClaim(claim_id="c1", text="A Class I widget must pass the Load Stress Test at a 95% threshold.")
    item = _item("i1", "A Class I widget must pass the Load Stress Test at a 95% threshold, per Section 3.")
    edge = link_claim(claim, [item])
    assert edge.support_status == "unknown"
    assert edge.judged_by == "unreviewed"


def test_only_packed_items_considered_not_omitted() -> None:
    """link_claims is only ever called with packed items by the orchestration layer --
    this test documents that contract at the function-signature level by confirming
    an item simply not passed in cannot be linked.
    """

    claim = AnswerClaim(claim_id="c1", text="A Class I widget must pass the Load Stress Test at a 95% threshold.")
    edges = link_claims([claim], [])
    assert edges[0].context_item_ids == []


def test_link_claims_preserves_claim_order() -> None:
    claims = [
        AnswerClaim(claim_id="c1", text="First claim about widgets."),
        AnswerClaim(claim_id="c2", text="Second claim about facilities."),
    ]
    edges = link_claims(claims, [])
    assert [e.claim_id for e in edges] == ["c1", "c2"]
