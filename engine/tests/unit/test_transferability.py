from __future__ import annotations

from datetime import date

from wittgenstein.core.enums import (
    ConfidenceTier,
    EvidenceDirection,
    EvidenceGrade,
    PeerReviewStatus,
    QuoteType,
    StudyType,
    TransferLevel,
    VerificationStatus,
)
from wittgenstein.matching.transferability import (
    compare_envelopes,
    confidence_for,
    transfer_level_for_evidence,
)
from wittgenstein.schemas.evidence import EvidenceRecord, ExperimentalEnvelope


def _evidence(**overrides) -> EvidenceRecord:
    base = dict(
        id="EV-TEST-001",
        failure_mechanism_id="TEST_MECHANISM",
        full_citation="Some citation",
        title="Some title",
        authors=["A"],
        venue="Some venue",
        publication_year=2024,
        peer_review_status=PeerReviewStatus.PEER_REVIEWED,
        persistent_identifier=None,
        source_url=None,
        exact_quote="A verified quote.",
        quote_location="Abstract",
        quote_type=QuoteType.FINDING_STATEMENT,
        study_type=StudyType.CAUSAL_INTERVENTION,
        direction=EvidenceDirection.SUPPORTS,
        task="task",
        dataset_or_corpus="dataset",
        experimental_envelope=ExperimentalEnvelope(),
        intervention_or_comparison="intervention",
        outcome_metrics=["metric"],
        effect_size_text=None,
        statistical_evidence=None,
        stated_limitations="limitations",
        evidence_grade=EvidenceGrade.A2_STRONG_COMPARATIVE_PEER_REVIEWED,
        extraction_reviewer="reviewer",
        extraction_date=date(2026, 1, 1),
        verification_status=VerificationStatus.VERIFIED,
    )
    base.update(overrides)
    return EvidenceRecord(**base)


def test_compare_envelopes_matching_and_unknown():
    manifest_env = ExperimentalEnvelope(retriever_family="bm25")
    evidence_env = ExperimentalEnvelope(retriever_family="bm25", reranker_family="cross_encoder")
    comparison = compare_envelopes(manifest_env, evidence_env)
    assert comparison.matching_dimensions == ["retriever_family"]
    assert comparison.unknown_dimensions == ["reranker_family"]
    assert comparison.mismatching_dimensions == []


def test_compare_envelopes_mismatch():
    manifest_env = ExperimentalEnvelope(retriever_family="dense")
    evidence_env = ExperimentalEnvelope(retriever_family="bm25")
    comparison = compare_envelopes(manifest_env, evidence_env)
    assert comparison.mismatching_dimensions == ["retriever_family"]


def test_mismatch_caps_transfer_at_partially_matched():
    manifest_env = ExperimentalEnvelope(retriever_family="dense")
    evidence = _evidence(experimental_envelope=ExperimentalEnvelope(rag_presence=True, retriever_family="bm25"))
    level, _ = transfer_level_for_evidence(manifest_env, evidence)
    assert level == TransferLevel.PARTIALLY_MATCHED


def test_non_rag_evidence_never_directly_matched():
    manifest_env = ExperimentalEnvelope(retriever_family="dense")
    evidence = _evidence(experimental_envelope=ExperimentalEnvelope(rag_presence=False, retriever_family="dense"))
    level, _ = transfer_level_for_evidence(manifest_env, evidence)
    assert level != TransferLevel.DIRECTLY_MATCHED
    assert level == TransferLevel.MECHANISTICALLY_MATCHED


def test_full_known_match_is_directly_matched():
    manifest_env = ExperimentalEnvelope(retriever_family="dense", rerank_depth=5)
    evidence = _evidence(
        experimental_envelope=ExperimentalEnvelope(rag_presence=True, retriever_family="dense", rerank_depth=5)
    )
    level, comparison = transfer_level_for_evidence(manifest_env, evidence)
    assert level == TransferLevel.DIRECTLY_MATCHED
    assert confidence_for(comparison) == ConfidenceTier.HIGH


def test_no_known_dimensions_is_insufficient():
    manifest_env = ExperimentalEnvelope()
    evidence = _evidence(experimental_envelope=ExperimentalEnvelope())
    level, comparison = transfer_level_for_evidence(manifest_env, evidence)
    assert level == TransferLevel.INSUFFICIENT_MANIFEST_INFORMATION
    assert confidence_for(comparison) == ConfidenceTier.INSUFFICIENT_DATA
