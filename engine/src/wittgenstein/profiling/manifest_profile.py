"""Build an ExperimentalEnvelope describing a deployed system from its manifest
(+ optional corpus profile, + optional per-query trace).

Reuses the same ExperimentalEnvelope schema an EvidenceRecord uses to describe a
study's setting, so `matching/transferability.py` can do a plain field-by-field
comparison. A field left `None` here must be read as "unknown," never defaulted.
"""

from __future__ import annotations

from wittgenstein.profiling.corpus_profile import document_structure_summary
from wittgenstein.schemas.corpus_profile import CorpusProfile
from wittgenstein.schemas.evidence import ExperimentalEnvelope
from wittgenstein.schemas.manifest import PipelineManifest
from wittgenstein.schemas.trace import QueryTrace


def build_envelope(
    manifest: PipelineManifest,
    trace: QueryTrace | None = None,
    corpus_profile: CorpusProfile | None = None,
) -> ExperimentalEnvelope:
    retrieval = manifest.retrieval_manifest
    reranking = manifest.reranking_manifest
    packing = manifest.packing_manifest
    generation = manifest.generation_manifest
    corpus = manifest.corpus_manifest

    packed_item_count = (
        len(trace.packed_context_items) if trace is not None and trace.packed_context_items is not None else None
    )
    context_window_tokens = packing.context_window_tokens
    evidence_budget_tokens = packing.evidence_budget_tokens
    if trace is not None and trace.final_prompt_evidence_budget is not None:
        evidence_budget_tokens = trace.final_prompt_evidence_budget

    return ExperimentalEnvelope(
        rag_presence=True,
        domain=corpus_profile.domain if corpus_profile is not None else corpus.domain,
        document_structure=(document_structure_summary(corpus_profile) if corpus_profile is not None else None),
        corpus_size=str(corpus.document_count) if corpus.document_count is not None else None,
        corpus_versioning=corpus.corpus_versioning,
        retrieval_topology=retrieval.retrieval_topology,
        retriever_family=retrieval.retriever_family,
        embedding_family=manifest.representation_manifest.embedding_family,
        retrieval_unit=retrieval.retrieval_unit,
        chunking_method=retrieval.chunking_method,
        chunk_size_or_distribution=retrieval.chunk_size_or_distribution,
        overlap_or_stride=retrieval.overlap_or_stride,
        candidate_depth=retrieval.candidate_depth,
        rerank_depth=reranking.rerank_depth,
        reranker_family=reranking.reranker_family,
        query_transformation=retrieval.query_transformation_method,
        parent_child_expansion=retrieval.parent_child_expansion,
        graph_retrieval=retrieval.graph_retrieval,
        compression_type=packing.compression_type,
        compression_ratio=packing.compression_ratio,
        packing_method=packing.packing_method,
        ordering_method=packing.ordering_method,
        packed_item_count=packed_item_count,
        context_window_tokens=context_window_tokens,
        evidence_budget_tokens=evidence_budget_tokens,
        generator_family=generation.generator_family,
        model_identifier=generation.model_identifier,
        prompting_policy=generation.prompting_policy,
        citation_policy=generation.citation_policy,
        abstention_policy=generation.abstention_policy,
    )
