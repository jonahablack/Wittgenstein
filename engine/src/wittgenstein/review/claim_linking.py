"""Links each AnswerClaim to packed evidence via the conservative field-comparison
engine (docs/claim-linking-improvement-plan.md) -- a programmatic, pre-review
candidate classification, never a final correctness verdict. Replaces the earlier
pure-lexical-overlap decision, which conflated topical relevance with evidential
support (see the smoke-003 case in docs/real-trace-smoke-test-results.md: a claim
asserting "every 6 months" against a source stating "once per Program Year" scored
`partial_support_candidate` from token overlap alone, despite an incompatible
frequency).

Lexical overlap (`retrieval/lexical.py::tokenize`) is retained, but only as one
diagnostic feature (`ClaimEvidenceComparison.lexical_features`) alongside the
field-comparison vector -- never the sole determinant of `relationship_status`.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from wittgenstein.core.enums import (
    ClaimSupportCandidateStatus,
    ComparisonFieldName,
    ComparisonOutcome,
    SegmentType,
)
from wittgenstein.ingestion.parser import split_sentences
from wittgenstein.proposition.annotations import contains_negation
from wittgenstein.proposition.candidates import split_candidates
from wittgenstein.retrieval.lexical import tokenize
from wittgenstein.review.field_comparison import compare_all_fields
from wittgenstein.review.field_extraction import extract_fields
from wittgenstein.review.relationship_classification import RelationshipResult, classify_relationship
from wittgenstein.schemas.claim_comparison import ClaimEvidenceComparison, FieldComparison
from wittgenstein.schemas.proposition import SourceSegment
from wittgenstein.schemas.trace import AnswerClaim, AnswerSupportEdge, ContextItem

#: How informative each relationship status is, for picking the most representative
#: sentence within a multi-sentence candidate excerpt (see `compare_claim_to_candidate`)
#: -- lower is preferred. A candidate excerpt is often a full packed paragraph with
#: several clauses; comparing against the *whole* blob at once means the first verb
#: anchor found (which may belong to an unrelated clause) drives the entire
#: comparison. Splitting into sentences and keeping the most informative one avoids
#: that.
_STATUS_INFORMATIVENESS_RANK = {
    ClaimSupportCandidateStatus.DIRECT_SUPPORT_CANDIDATE: 0,
    ClaimSupportCandidateStatus.CONTRADICTION_CANDIDATE: 1,
    ClaimSupportCandidateStatus.QUALIFICATION_REQUIRED: 2,
    ClaimSupportCandidateStatus.PARTIAL_SUPPORT_CANDIDATE: 3,
    ClaimSupportCandidateStatus.UNRESOLVED: 4,
    ClaimSupportCandidateStatus.NO_SUPPORT_EDGE_FOUND: 5,
}


@dataclass
class CandidateScore:
    """One (claim, candidate item) lexical scoring -- exposed publicly so diagnostic
    tooling (e.g. the real-trace smoke-test runner's "link scores/features" inspection
    report, docs/real-trace-smoke-test-plan.md) can inspect every candidate's lexical
    overlap, not just the field-comparison verdict. No longer the decision mechanism --
    see `compare_claim_to_candidate` for that.
    """

    item_id: str
    overlap_ratio: float
    claim_has_negation: bool
    item_has_negation: bool


def _overlap_ratio(claim_tokens: set[str], item_tokens: set[str]) -> float:
    if not claim_tokens:
        return 0.0
    return len(claim_tokens & item_tokens) / len(claim_tokens)


def score_candidates(claim: AnswerClaim, packed_items: list[ContextItem]) -> list[CandidateScore]:
    """Lexical-overlap scoring, highest first -- a diagnostic feature now, not the
    linking decision.
    """

    claim_tokens = set(tokenize(claim.text))
    claim_has_negation = contains_negation(claim.text)
    scores = [
        CandidateScore(
            item_id=item.item_id,
            overlap_ratio=_overlap_ratio(claim_tokens, set(tokenize(item.excerpt or ""))),
            claim_has_negation=claim_has_negation,
            item_has_negation=contains_negation(item.excerpt or ""),
        )
        for item in packed_items
    ]
    scores.sort(key=lambda s: s.overlap_ratio, reverse=True)
    return scores


def _clause_spans(excerpt: str) -> list[str]:
    """Decomposes `excerpt` (often a full packed paragraph) into clause-level spans --
    Tier-0 sentence splitting (`ingestion/parser.py::split_sentences`) followed by
    Tier-1 clause splitting (`proposition/candidates.py::split_candidates`, which
    additionally splits on semicolons/conjunctions/relative clauses/condition markers)
    -- the same two-stage composition `review/answer_claims.py` already uses for
    answer text, reused here rather than reimplemented.
    """

    sentences = [s for s, _start, _end in split_sentences(excerpt)] or [excerpt]
    clauses: list[str] = []
    for i, sentence in enumerate(sentences):
        segment = SourceSegment(
            segment_id=f"clause-split-tmp-{i}",
            source_document_id="clause-split-tmp",
            corpus_id="clause-split-tmp",
            segment_type=SegmentType.SENTENCE,
            location="clause-split-tmp",
            text=sentence,
            char_start=0,
            char_end=len(sentence),
            parser_version="claim-linking-clause-split-1",
        )
        clauses.extend(candidate.text for candidate in split_candidates(segment))
    return clauses or [excerpt]


def _best_field_comparisons(claim_text: str, excerpt: str) -> tuple[list[FieldComparison], RelationshipResult]:
    """Compares `claim_text` against every clause in `excerpt` and returns the most
    informative result -- rather than treating the whole multi-clause excerpt as one
    blob, which lets whichever verb happens to appear first (possibly in an unrelated
    clause) silently drive the entire comparison.
    """

    best: tuple[list[FieldComparison], RelationshipResult] | None = None
    best_rank = len(_STATUS_INFORMATIVENESS_RANK)
    claim_fields = extract_fields(claim_text)
    for clause in _clause_spans(excerpt):
        source_fields = extract_fields(clause)
        field_comparisons = compare_all_fields(claim_fields, source_fields)
        relationship = classify_relationship(field_comparisons)
        rank = _STATUS_INFORMATIVENESS_RANK.get(relationship.status, len(_STATUS_INFORMATIVENESS_RANK))
        if best is None or rank < best_rank:
            best = (field_comparisons, relationship)
            best_rank = rank
    assert best is not None  # _clause_spans always returns at least one element
    return best


def compare_claim_to_candidate(claim: AnswerClaim, item: ContextItem) -> ClaimEvidenceComparison:
    """The full field-comparison record for one (claim, candidate) pair -- what the
    aggregate `AnswerSupportEdge` for a claim is built from (see `link_claim_detailed`).
    """

    field_comparisons, relationship = _best_field_comparisons(claim.text, item.excerpt or "")

    claim_tokens = set(tokenize(claim.text))
    item_tokens = set(tokenize(item.excerpt or ""))
    entity_comparison = next((c for c in field_comparisons if c.field_name == ComparisonFieldName.ENTITY), None)
    predicate_comparison = next(
        (c for c in field_comparisons if c.field_name == ComparisonFieldName.PREDICATE), None
    )

    return ClaimEvidenceComparison(
        comparison_id=f"CMP-{uuid.uuid4().hex[:12]}",
        claim_id=claim.claim_id,
        context_item_id=item.item_id,
        relationship_status=relationship.status,
        field_comparisons=field_comparisons,
        mismatch_types=relationship.mismatch_types,
        lexical_features={"overlap_ratio": _overlap_ratio(claim_tokens, item_tokens)},
        structural_features={
            "entity_match": entity_comparison is not None and entity_comparison.outcome == ComparisonOutcome.MATCH,
            "predicate_match": predicate_comparison is not None
            and predicate_comparison.outcome == ComparisonOutcome.MATCH,
        },
        semantic_features=None,
        uncertainty_reason=relationship.uncertainty_reason,
        assessment_method="programmatic_field_comparison",
        assessment_version="1",
        explanation=relationship.explanation,
    )


#: Priority order used to aggregate multiple per-candidate comparisons for one claim
#: into a single AnswerSupportEdge.candidate_support_status -- see `link_claim_detailed`.
_STATUS_PRIORITY = [
    ClaimSupportCandidateStatus.DIRECT_SUPPORT_CANDIDATE,
    ClaimSupportCandidateStatus.CONTRADICTION_CANDIDATE,
    ClaimSupportCandidateStatus.QUALIFICATION_REQUIRED,
    ClaimSupportCandidateStatus.PARTIAL_SUPPORT_CANDIDATE,
]


def link_claim_detailed(
    claim: AnswerClaim, packed_items: list[ContextItem]
) -> tuple[AnswerSupportEdge, list[ClaimEvidenceComparison]]:
    """Compares `claim` against every packed (model-visible) item -- never against
    omitted items, since those were never available to whatever produced the answer
    (docs/architecture.md, "Pipeline lineage") -- and aggregates the per-candidate
    comparisons into one AnswerSupportEdge.

    Rule E (conflict_candidate): if at least one candidate reaches
    DIRECT_SUPPORT_CANDIDATE and at least one other reaches CONTRADICTION_CANDIDATE for
    the same claim, the system cannot determine which source governs -- both are
    reported as CONFLICT_CANDIDATE rather than the aggregate silently picking a winner.
    """

    if not claim.text or not claim.text.strip():
        edge = AnswerSupportEdge(
            claim_id=claim.claim_id,
            context_item_ids=[],
            support_status="unknown",
            judged_by="unreviewed",
            candidate_support_status=ClaimSupportCandidateStatus.UNRESOLVED,
        )
        return edge, []

    if not packed_items:
        edge = AnswerSupportEdge(
            claim_id=claim.claim_id,
            context_item_ids=[],
            support_status="unknown",
            judged_by="unreviewed",
            candidate_support_status=ClaimSupportCandidateStatus.NO_SUPPORT_EDGE_FOUND,
        )
        return edge, []

    comparisons = [compare_claim_to_candidate(claim, item) for item in packed_items]

    direct = [
        c for c in comparisons if c.relationship_status == ClaimSupportCandidateStatus.DIRECT_SUPPORT_CANDIDATE
    ]
    contradiction = [
        c for c in comparisons if c.relationship_status == ClaimSupportCandidateStatus.CONTRADICTION_CANDIDATE
    ]

    if direct and contradiction:
        conflicting_ids = [c.context_item_id for c in (*direct, *contradiction)]
        for c in comparisons:
            if c.context_item_id in conflicting_ids:
                c.relationship_status = ClaimSupportCandidateStatus.CONFLICT_CANDIDATE
        edge = AnswerSupportEdge(
            claim_id=claim.claim_id,
            context_item_ids=conflicting_ids,
            support_status="unknown",
            judged_by="unreviewed",
            candidate_support_status=ClaimSupportCandidateStatus.CONFLICT_CANDIDATE,
        )
        return edge, comparisons

    for status in _STATUS_PRIORITY:
        matching = [c for c in comparisons if c.relationship_status == status]
        if matching:
            edge = AnswerSupportEdge(
                claim_id=claim.claim_id,
                context_item_ids=[c.context_item_id for c in matching],
                support_status="unknown",
                judged_by="unreviewed",
                candidate_support_status=status,
            )
            return edge, comparisons

    all_no_support = all(
        c.relationship_status == ClaimSupportCandidateStatus.NO_SUPPORT_EDGE_FOUND for c in comparisons
    )
    final_status = (
        ClaimSupportCandidateStatus.NO_SUPPORT_EDGE_FOUND
        if all_no_support
        else ClaimSupportCandidateStatus.UNRESOLVED
    )
    edge = AnswerSupportEdge(
        claim_id=claim.claim_id,
        context_item_ids=[],
        support_status="unknown",
        judged_by="unreviewed",
        candidate_support_status=final_status,
    )
    return edge, comparisons


def link_claim(claim: AnswerClaim, packed_items: list[ContextItem]) -> AnswerSupportEdge:
    edge, _ = link_claim_detailed(claim, packed_items)
    return edge


def link_claims(claims: list[AnswerClaim], packed_items: list[ContextItem]) -> list[AnswerSupportEdge]:
    return [link_claim(claim, packed_items) for claim in claims]


def link_claims_detailed(
    claims: list[AnswerClaim], packed_items: list[ContextItem]
) -> tuple[list[AnswerSupportEdge], list[ClaimEvidenceComparison]]:
    edges: list[AnswerSupportEdge] = []
    all_comparisons: list[ClaimEvidenceComparison] = []
    for claim in claims:
        edge, comparisons = link_claim_detailed(claim, packed_items)
        edges.append(edge)
        all_comparisons.extend(comparisons)
    return edges, all_comparisons
