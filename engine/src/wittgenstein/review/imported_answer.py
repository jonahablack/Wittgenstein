"""Imported-answer review mode: the one entry point for "here is a query, an answer,
and (optionally) the evidence that produced it -- build the full reviewable audit
record" (docs/review-loop-implementation-plan.md §1).

Reuses, unmodified:
- `demo/pipeline.py::run_demo_query`/`build_manifest`/`build_bm25_index` for the
  retrieval/packing/Tier-1-2 path when no trace is supplied (see the plan doc's "Known
  layering note" for why this currently imports from `demo/pipeline.py`).
- `services/applicability_service.py::derive_risk_events` -- the same registry-matching
  code path every other part of this system already uses, so imported-answer mode
  inherits every existing epistemic-status/activation-policy guarantee without this
  module touching the registry at all.

Works with zero LLM calls by default (`llm_client=None`).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime

from wittgenstein.core.enums import SegmentType
from wittgenstein.demo.pipeline import build_bm25_index, build_manifest, run_demo_query
from wittgenstein.ingestion.corpus_index import CorpusIndex, index_corpus
from wittgenstein.ingestion.kv_cache import KVCache
from wittgenstein.metrics.processing_metrics import ProcessingMetrics
from wittgenstein.proposition.annotations import annotate_candidate
from wittgenstein.proposition.candidates import split_candidates
from wittgenstein.proposition.llm_client import LLMClient
from wittgenstein.registry.repository import Registry
from wittgenstein.review.answer_claims import extract_answer_claims
from wittgenstein.review.claim_linking import link_claims_detailed
from wittgenstein.review.evidence_set import EvidenceSetConstructionMetrics, construct_evidence_set
from wittgenstein.schemas.applicability import ApplicabilityAssessment
from wittgenstein.schemas.claim_comparison import ClaimEvidenceComparison
from wittgenstein.schemas.corpus_profile import CorpusProfile
from wittgenstein.schemas.evidence_set import EvidenceSet
from wittgenstein.schemas.manifest import PipelineManifest
from wittgenstein.schemas.proposition import (
    LLMExtractionResult,
    PropositionAnnotation,
    PropositionCandidate,
    SourceSegment,
)
from wittgenstein.schemas.review import RiskEvent
from wittgenstein.schemas.trace import QueryTrace, SupportRequirement
from wittgenstein.services.applicability_service import derive_risk_events
from wittgenstein.services.registry_service import get_registry


class ImportedAnswerError(ValueError):
    """Raised for a request this module cannot service -- e.g. neither a corpus nor an
    existing trace was supplied. Never silently guessed around.
    """


@dataclass
class ImportedAnswerResult:
    trace: QueryTrace
    manifest: PipelineManifest
    corpus_profile: CorpusProfile | None
    risk_events: list[RiskEvent]
    audited_non_applicable_assessments: list[ApplicabilityAssessment]
    candidates: list[PropositionCandidate] = field(default_factory=list)
    annotations: list[PropositionAnnotation] = field(default_factory=list)
    context_item_provenance: dict[str, str] = field(default_factory=dict)
    llm_extractions: list[LLMExtractionResult] = field(default_factory=list)
    claim_evidence_comparisons: list[ClaimEvidenceComparison] = field(default_factory=list)
    evidence_sets: list[EvidenceSet] = field(
        default_factory=list,
        metadata={
            "description": "Multi-passage candidate evidence sets (docs/multi-passage-evidence-plan.md), "
            "one per claim for which construction was attempted and did not skip -- never a factual "
            "adjudication, and disjoint from `claim_evidence_comparisons`, which stays single-passage only."
        },
    )
    evidence_set_metrics: list[EvidenceSetConstructionMetrics] = field(default_factory=list)
    metrics: ProcessingMetrics = field(default_factory=ProcessingMetrics)


def _unknown_manifest(manifest_id: str) -> PipelineManifest:
    """A manifest for an imported trace whose actual pipeline configuration is not
    known to this call -- every field left at its `None` default is genuinely unknown,
    not a guess (CLAUDE.md, "never infer missing manifest values").
    """

    return PipelineManifest(
        manifest_id=manifest_id,
        system_name="imported-answer-unknown-system",
        system_version="unknown",
        created_at=datetime.now(UTC),
        missing_information=[
            "Manifest not supplied with the imported trace; entire pipeline configuration unknown."
        ],
    )


def _process_packed_items_tier12(
    trace: QueryTrace,
) -> tuple[list[PropositionCandidate], list[PropositionAnnotation]]:
    """Run Tier 1/2 processing directly on an already-built trace's packed items'
    excerpts -- used when the caller supplied an existing trace rather than raw corpus
    text, so this mode does not require re-indexing a corpus it was never given.
    """

    candidates: list[PropositionCandidate] = []
    annotations: list[PropositionAnnotation] = []
    for item in trace.packed_context_items or []:
        if not item.excerpt:
            continue
        segment = SourceSegment(
            segment_id=item.segment_id or item.item_id,
            source_document_id=item.source_document_id or "unknown",
            corpus_id=trace.corpus_id or "unknown",
            segment_type=SegmentType.PARAGRAPH,
            location=item.segment_id or item.item_id,
            text=item.excerpt,
            char_start=0,
            char_end=len(item.excerpt),
            parser_version="review-imported-trace-1",
        )
        item_candidates = split_candidates(segment, id_prefix=item.item_id)
        candidates.extend(item_candidates)
        for candidate in item_candidates:
            annotations.extend(annotate_candidate(candidate))
    return candidates, annotations


def import_answer(
    query: str,
    answer: str,
    *,
    corpus: dict[str, str] | None = None,
    corpus_id: str = "imported-answer-corpus",
    manifest: PipelineManifest | None = None,
    trace: QueryTrace | None = None,
    registry: Registry | None = None,
    token_budget: int = 300,
    top_k: int = 5,
    llm_client: LLMClient | None = None,
    llm_cache: KVCache | None = None,
    corpus_cache: KVCache | None = None,
) -> ImportedAnswerResult:
    """Build the full reviewable audit record for one (query, answer) pair.

    Exactly one of `trace` or `corpus` must be usable to obtain evidence:
    - `trace`: an already-built QueryTrace (e.g. from a real production RAG run) is
      used as-is; its `packed_context_items` are the evidence base for claim linking
      and Tier 1/2 processing. `corpus`, if also given, is indexed only to compute a
      `CorpusProfile` -- it does not replace the supplied trace's retrieval.
    - `corpus`: a fresh `{source_document_id: text}` corpus is indexed and queried via
      the same BM25/packing path the offline demo uses (`demo/pipeline.py::run_demo_query`).

    Raises `ImportedAnswerError` if neither is usable.
    """

    if trace is None and not corpus:
        raise ImportedAnswerError(
            "import_answer requires either an existing `trace` or a `corpus` to retrieve from."
        )

    registry = registry or get_registry()
    corpus_profile: CorpusProfile | None = None
    corpus_index: CorpusIndex | None = None

    if corpus:
        corpus_index = index_corpus(corpus, corpus_id, cache=corpus_cache)
        corpus_profile = corpus_index.corpus_profile

    if trace is not None:
        resolved_manifest = manifest or _unknown_manifest(f"{trace.trace_id}-manifest")
        candidates, annotations = _process_packed_items_tier12(trace)
        context_item_provenance = {
            item.item_id: "caller_supplied_trace" for item in trace.retrieval_candidates or []
        }
        metrics = ProcessingMetrics()
        llm_extractions_pre: list[LLMExtractionResult] = []
        base_trace = trace
    else:
        assert corpus_index is not None  # guaranteed by the corpus-not-None branch above
        bm25_index = build_bm25_index(corpus_index)
        resolved_manifest = manifest or build_manifest(
            manifest_id=f"{corpus_id}-manifest", corpus_id=corpus_id, token_budget=token_budget, top_k=top_k
        )
        demo_result = run_demo_query(
            corpus_index,
            bm25_index,
            query,
            trace_id=f"{corpus_id}-imported-trace",
            manifest=resolved_manifest,
            token_budget=token_budget,
            top_k=top_k,
            llm_client=llm_client,
            llm_cache=llm_cache,
        )
        base_trace = demo_result.trace
        candidates = demo_result.candidates
        annotations = demo_result.annotations
        context_item_provenance = demo_result.context_item_provenance
        metrics = demo_result.metrics
        llm_extractions_pre = demo_result.llm_extractions

    claims, claim_llm_extractions = extract_answer_claims(
        answer, trace_id=base_trace.trace_id, llm_client=llm_client, llm_cache=llm_cache
    )
    packed_items = base_trace.packed_context_items or []
    edges, claim_evidence_comparisons = link_claims_detailed(claims, packed_items)

    comparisons_by_claim: dict[str, list[ClaimEvidenceComparison]] = {}
    for comparison in claim_evidence_comparisons:
        comparisons_by_claim.setdefault(comparison.claim_id, []).append(comparison)

    evidence_sets: list[EvidenceSet] = []
    evidence_set_metrics: list[EvidenceSetConstructionMetrics] = []
    for claim in claims:
        evidence_set, es_metrics = construct_evidence_set(
            claim,
            packed_items,
            comparisons_by_claim.get(claim.claim_id, []),
            trace_id=base_trace.trace_id,
        )
        evidence_set_metrics.append(es_metrics)
        if evidence_set is not None:
            evidence_sets.append(evidence_set)

    # Connects to the registered RET_MULTIHOP_SUPPORT_INCOMPLETE mechanism without
    # promoting or modifying it (docs/multi-passage-evidence-plan.md §8): populated
    # only when at least one evidence set was actually proposed with members (real
    # candidate evidence that composition was attempted), never merely because
    # construction was invoked -- an attempt that found nothing tells us evidence was
    # insufficient, not that the claim is (or isn't) genuinely multi-hop, so
    # `support_requirement` is left unset (not assessed) in that case, per
    # `SupportRequirement`'s own "absence means unknown" contract.
    composed_sets = [s for s in evidence_sets if s.members]
    support_requirement = (
        SupportRequirement(
            is_multi_hop=True,
            required_support_item_ids=sorted(
                {item_id for s in composed_sets for item_id in s.member_context_item_ids}
            ),
            assessment_method="evidence_set_construction",
        )
        if composed_sets
        else base_trace.support_requirement  # preserve any pre-existing (e.g. reviewer-assessed) value
    )

    final_trace = base_trace.model_copy(
        update={
            "query": query,
            "answer": answer,
            "answer_claims": claims,
            "answer_support_edges": edges,
            "support_requirement": support_requirement,
        }
    )

    risk_result = derive_risk_events(registry, resolved_manifest, final_trace)

    return ImportedAnswerResult(
        trace=final_trace,
        manifest=resolved_manifest,
        corpus_profile=corpus_profile,
        risk_events=risk_result.risk_events,
        audited_non_applicable_assessments=risk_result.audited_non_applicable,
        candidates=candidates,
        annotations=annotations,
        context_item_provenance=context_item_provenance,
        llm_extractions=[*llm_extractions_pre, *claim_llm_extractions],
        claim_evidence_comparisons=claim_evidence_comparisons,
        evidence_sets=evidence_sets,
        evidence_set_metrics=evidence_set_metrics,
        metrics=metrics,
    )
