"""Multi-candidate aggregation into CONFLICT_CANDIDATE (rule E) --
docs/claim-linking-improvement-plan.md. Required test category 14.
"""

from __future__ import annotations

from wittgenstein.core.enums import ClaimSupportCandidateStatus
from wittgenstein.review.claim_linking import link_claim
from wittgenstein.schemas.trace import AnswerClaim, ContextItem


def test_14_multiple_conflicting_sources_yield_conflict_candidate() -> None:
    """One packed candidate directly supports the claim; another, equally plausible
    (same entity/predicate) candidate contradicts it -- the system cannot determine
    which source governs, so both are reported as CONFLICT_CANDIDATE rather than the
    aggregate silently picking a winner.
    """

    claim = AnswerClaim(claim_id="c1", text="Class III widgets must be inspected every 6 months.")
    supporting = ContextItem(item_id="i1", excerpt="Class III widgets must be inspected every 6 months.", rank=1)
    contradicting = ContextItem(
        item_id="i2", excerpt="Class III widgets must be inspected once per Program Year.", rank=2
    )

    edge = link_claim(claim, [supporting, contradicting])

    assert edge.candidate_support_status == ClaimSupportCandidateStatus.CONFLICT_CANDIDATE
    assert set(edge.context_item_ids) == {"i1", "i2"}


def test_conflict_not_triggered_by_a_single_supporting_candidate() -> None:
    claim = AnswerClaim(claim_id="c1", text="Class III widgets must be inspected every 6 months.")
    supporting = ContextItem(item_id="i1", excerpt="Class III widgets must be inspected every 6 months.", rank=1)

    edge = link_claim(claim, [supporting])

    assert edge.candidate_support_status == ClaimSupportCandidateStatus.DIRECT_SUPPORT_CANDIDATE
