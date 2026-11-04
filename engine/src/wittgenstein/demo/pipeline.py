"""Phase A (corpus-time) + Phase B (query-time) orchestration for the vertical-slice
demo (docs/efficiency-and-processing-architecture.md, "DOCUMENT PROCESSING"). This is
the module the CLI's `demo` command and the tests both call -- it is the concrete
no-LLM-baseline / optional-enhanced-mode pipeline described in that doc, not a new
architecture of its own.

No-LLM baseline mode is not a special code path: it is simply what happens when the
caller passes no `llm_client` (or a `NullLLMClient`), because `proposition.llm_extraction`
already treats "no client" and "client unavailable" identically.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime

from wittgenstein.core.enums import (
    AnnotationCueType,
    ExtractionValidationStatus,
    SegmentType,
    TraceStatus,
)
from wittgenstein.ingestion.content_hash import content_hash
from wittgenstein.ingestion.corpus_index import CorpusIndex, index_corpus
from wittgenstein.ingestion.kv_cache import KVCache, MemoryKVCache
from wittgenstein.metrics.processing_metrics import ProcessingMetrics, timed
from wittgenstein.proposition.annotations import annotate_candidate
from wittgenstein.proposition.candidates import split_candidates
from wittgenstein.proposition.llm_client import LLMCallResult, LLMClient
from wittgenstein.proposition.llm_extraction import extract_tier3
from wittgenstein.retrieval.lexical import BM25Index, RetrievalCandidate
from wittgenstein.schemas.manifest import (
    CorpusManifest,
    IngestionManifest,
    PackingManifest,
    PipelineManifest,
    RepresentationManifest,
    RetrievalManifest,
)
from wittgenstein.schemas.proposition import LLMExtractionResult, PropositionAnnotation, PropositionCandidate
from wittgenstein.schemas.trace import ContextItem, QueryTrace
from wittgenstein.trace.packer import PackingResult, pack_context
from wittgenstein.trace.token_counting import TokenCounter, default_counter

#: Segment types actually offered to retrieval. SENTENCE segments are Tier-0 children
#: of a PARAGRAPH used for Tier-1 splitting, not independent retrieval units -- indexing
#: both would put duplicate text in the BM25 corpus. HEADING/CAPTION/FOOTNOTE are
#: structural, not retrievable content on their own.
_RETRIEVAL_UNIT_TYPES = {SegmentType.PARAGRAPH, SegmentType.LIST_ITEM, SegmentType.TABLE_ROW}

DEMO_CORPUS_ID = "widget-certification-demo"
RETRIEVER_FAMILY = "bm25_lexical"
PACKING_METHOD = "greedy_rank_order_token_budget"


class DemoLLMClient:
    """A deterministic, offline stand-in for a real LLM provider, used only by the
    demo's "enhanced mode" -- `proposition.llm_client.FakeLLMClient` is documented as
    test-only, so the demo needs its own client rather than repurposing that one. This
    makes no network call and has no configuration; it deterministically splits
    candidate text on internal punctuation to produce a toy "decomposed_clauses" result,
    which is enough to exercise the Tier-3 cache/validation/provenance code paths
    without claiming any real semantic quality. A real provider-backed client only
    needs to satisfy the same `LLMClient` protocol (see llm_client.py's module
    docstring, §8 of the architecture doc).
    """

    def is_available(self) -> bool:
        return True

    def extract(self, text: str, *, prompt_version: str, schema_version: str) -> LLMCallResult:
        clauses = [c.strip() for c in text.replace(";", ",").split(",") if c.strip()]
        parsed = {"decomposed_clauses": clauses}
        return LLMCallResult(
            raw_output=str(parsed),
            parsed_output=parsed,
            input_tokens=len(text.split()),
            output_tokens=len(clauses),
        )

    def extract_batch(self, texts: list[str], *, prompt_version: str, schema_version: str) -> list[LLMCallResult]:
        return [self.extract(t, prompt_version=prompt_version, schema_version=schema_version) for t in texts]


@dataclass
class DemoResult:
    """Everything one demo query run produces, plus the field-provenance map the
    "DEMO REQUIREMENT" section asks for: every context item and every annotation is
    labeled by how it was produced, so a UI/API consumer never has to guess.
    """

    trace: QueryTrace
    manifest: PipelineManifest
    metrics: ProcessingMetrics
    candidates: list[PropositionCandidate] = field(default_factory=list)
    annotations: list[PropositionAnnotation] = field(default_factory=list)
    llm_extractions: list[LLMExtractionResult] = field(default_factory=list)
    context_item_provenance: dict[str, str] = field(default_factory=dict)


def build_manifest(
    *,
    manifest_id: str,
    corpus_id: str,
    token_budget: int,
    top_k: int,
) -> PipelineManifest:
    """A manifest describing exactly the pipeline this module runs -- never a template
    or a guess about what a "typical" RAG system looks like (CLAUDE.md, "never infer
    missing manifest values"); every field here corresponds to an actual runtime choice
    made below.
    """

    return PipelineManifest(
        manifest_id=manifest_id,
        system_name="wittgenstein-vertical-slice-demo",
        system_version="0.1.0",
        created_at=datetime.now(UTC),
        corpus_manifest=CorpusManifest(
            corpus_id=corpus_id, source_type="synthetic_markdown", domain="widget_certification"
        ),
        ingestion_manifest=IngestionManifest(
            parser="deterministic_parser_v1",
            ocr_used=False,
            table_extraction_method="markdown_table_row_regex",
            structure_extraction_method="heading_and_blank_line_rules",
        ),
        representation_manifest=RepresentationManifest(
            index_unit="paragraph_list_item_table_row",
            embedding_family=None,
            embedding_model_identifier=None,
        ),
        retrieval_manifest=RetrievalManifest(
            retriever_family=RETRIEVER_FAMILY,
            retrieval_topology="single_corpus_flat",
            retrieval_unit="paragraph_list_item_table_row",
            chunking_method="structural_segmentation_no_fixed_window",
            candidate_depth=top_k,
            query_transformation_enabled=False,
        ),
        packing_manifest=PackingManifest(
            packing_method=PACKING_METHOD,
            ordering_method="retrieval_rank",
            compression_enabled=False,
            context_window_tokens=token_budget,
            evidence_budget_tokens=token_budget,
        ),
        # No real answer generator is wired in this vertical slice (see architecture
        # doc §8) -- generation_manifest is left at its all-`None` default, and the gap
        # is declared explicitly below rather than left to be misread as "not yet
        # filled in."
        missing_information=[
            "generation_manifest.generator_family",
            "generation_manifest.model_identifier",
        ],
    )


def build_bm25_index(corpus_index: CorpusIndex) -> BM25Index:
    retrieval_segments = [
        segment for segment in corpus_index.segments.values() if segment.segment_type in _RETRIEVAL_UNIT_TYPES
    ]
    return BM25Index(retrieval_segments)


def _annotation_cue_flags(annotations: list[PropositionAnnotation]) -> list[str]:
    """Turn Tier-2 cues that specifically indicate a cross-segment dependency risk
    (condition/exception language, or an explicit cross-reference) into the trace's
    existing `segment_boundary_dependency_flags` vocabulary -- human-readable strings,
    never a registry mechanism id or a causal claim (CLAUDE.md, "never infer causality
    from a trace fact alone").
    """

    flag_types = {AnnotationCueType.CONDITION, AnnotationCueType.EXCEPTION, AnnotationCueType.CROSS_REFERENCE}
    flags = []
    for annotation in annotations:
        if annotation.cue_type in flag_types:
            flags.append(f"{annotation.cue_type.value}_cue:{annotation.candidate_id}:{annotation.matched_text!r}")
    return flags


def run_demo_query(
    corpus_index: CorpusIndex,
    bm25_index: BM25Index,
    query: str,
    *,
    trace_id: str,
    manifest: PipelineManifest,
    token_budget: int = 300,
    top_k: int = 5,
    counter: TokenCounter | None = None,
    llm_client: LLMClient | None = None,
    llm_cache: KVCache | None = None,
    metrics: ProcessingMetrics | None = None,
) -> DemoResult:
    """Run one query through Phase B: lexical retrieval -> Tier 1/2 annotation of the
    retrieved text -> programmatic packing -> (optional) Tier-3 LLM enrichment of
    ambiguous packed candidates -> QueryTrace. No LLM call is ever made to decide
    retrieval ranking or what fits in the context window.
    """

    metrics = metrics if metrics is not None else ProcessingMetrics()
    counter = counter or default_counter()

    with timed(metrics, "retrieval_latency_seconds"):
        raw_candidates: list[RetrievalCandidate] = bm25_index.search(query, top_k=top_k)

    retrieval_context_items = [
        ContextItem(
            item_id=f"{trace_id}-ret{i}",
            source_document_id=bm25_index.segment(rc.segment_id).source_document_id,
            segment_id=rc.segment_id,
            excerpt=bm25_index.segment(rc.segment_id).text,
            rank=rc.rank,
            relevance_score=rc.score,
            is_query_related=None,
            is_answer_supporting=None,
            token_count=counter.count(bm25_index.segment(rc.segment_id).text),
        )
        for i, rc in enumerate(raw_candidates, start=1)
    ]
    metrics.candidate_count = len(retrieval_context_items)
    context_item_provenance = {item.item_id: "programmatic_lexical_retrieval" for item in retrieval_context_items}

    with timed(metrics, "proposition_extraction_latency_seconds"):
        candidates: list[PropositionCandidate] = []
        annotations: list[PropositionAnnotation] = []
        for item in retrieval_context_items:
            segment = bm25_index.segment(item.segment_id)  # type: ignore[arg-type]
            segment_candidates = split_candidates(segment)
            candidates.extend(segment_candidates)
            for candidate in segment_candidates:
                annotations.extend(annotate_candidate(candidate))

    with timed(metrics, "indexing_latency_seconds"):
        packing_result: PackingResult = pack_context(retrieval_context_items, token_budget, counter=counter)
    metrics.packed_token_count = packing_result.final_prompt_token_count

    llm_extractions: list[LLMExtractionResult] = []
    if llm_client is not None:
        llm_cache = llm_cache if llm_cache is not None else MemoryKVCache()
        ambiguous = [c for c in candidates if c.is_ambiguous]
        for candidate in ambiguous:
            result = extract_tier3(
                candidate.candidate_id,
                candidate.text,
                client=llm_client,
                cache=llm_cache,
                model_id="demo-enhanced-mode",
                metrics=metrics,
            )
            llm_extractions.append(result)
            context_item_provenance[candidate.candidate_id] = (
                "llm_extracted" if result.validation_status == ExtractionValidationStatus.VALIDATED else "unknown"
            )

    trace = QueryTrace(
        trace_id=trace_id,
        manifest_id=manifest.manifest_id,
        corpus_id=corpus_index.corpus_id,
        query=query,
        query_timestamp=datetime.now(UTC),
        retrieval_candidates=retrieval_context_items,
        packed_context_items=packing_result.packed_context_items,
        omitted_context_items=packing_result.omitted_context_items,
        compressed_context_items=packing_result.compressed_context_items or None,
        final_prompt=packing_result.final_prompt,
        final_prompt_token_count=packing_result.final_prompt_token_count,
        final_prompt_evidence_budget=token_budget,
        prompt_token_spans=packing_result.prompt_token_spans,
        segment_boundary_dependency_flags=_annotation_cue_flags(annotations),
        trace_status=TraceStatus.COMPLETE,
    )

    return DemoResult(
        trace=trace,
        manifest=manifest,
        metrics=metrics,
        candidates=candidates,
        annotations=annotations,
        llm_extractions=llm_extractions,
        context_item_provenance=context_item_provenance,
    )


def run_demo(
    sources: dict[str, str],
    queries: list[str],
    *,
    corpus_id: str = DEMO_CORPUS_ID,
    token_budget: int = 300,
    top_k: int = 5,
    cache: KVCache | None = None,
    llm_client: LLMClient | None = None,
) -> tuple[CorpusIndex, ProcessingMetrics, list[DemoResult]]:
    """The full workflow: ingest -> segment -> index -> (per query) retrieve, annotate,
    pack, trace. Passing no `llm_client` (or leaving the default) *is* the no-LLM
    baseline mode -- not a separate branch -- because `run_demo_query` simply forwards
    whatever it's given to `proposition.llm_extraction`, which already treats "no
    client" and "client unavailable" identically. `run_enhanced_demo` below is a thin
    wrapper that passes a `DemoLLMClient`.

    Returns the corpus-time (Phase A) `ProcessingMetrics` separately from each
    `DemoResult.metrics` (Phase B, query-time only) -- consistent with
    `ProcessingMetrics` being "a companion object to one corpus-indexing OR query run,"
    never both merged into one.
    """

    corpus_metrics = ProcessingMetrics()
    with timed(corpus_metrics, "ingestion_latency_seconds"):
        corpus_index = index_corpus(sources, corpus_id, cache=cache, metrics=corpus_metrics)
    bm25_index = build_bm25_index(corpus_index)

    manifest = build_manifest(
        manifest_id=f"{corpus_id}-manifest",
        corpus_id=corpus_id,
        token_budget=token_budget,
        top_k=top_k,
    )

    llm_cache = MemoryKVCache() if llm_client is not None else None
    results = [
        run_demo_query(
            corpus_index,
            bm25_index,
            query,
            trace_id=f"{corpus_id}-trace{i}",
            manifest=manifest,
            token_budget=token_budget,
            top_k=top_k,
            llm_client=llm_client,
            llm_cache=llm_cache,
        )
        for i, query in enumerate(queries, start=1)
    ]
    return corpus_index, corpus_metrics, results


def run_no_llm_baseline_demo(
    sources: dict[str, str],
    queries: list[str],
    *,
    corpus_id: str = DEMO_CORPUS_ID,
    token_budget: int = 300,
    top_k: int = 5,
    cache: KVCache | None = None,
) -> tuple[CorpusIndex, ProcessingMetrics, list[DemoResult]]:
    """The no-LLM baseline: `run_demo` with no `llm_client`."""

    return run_demo(sources, queries, corpus_id=corpus_id, token_budget=token_budget, top_k=top_k, cache=cache)


def run_enhanced_demo(
    sources: dict[str, str],
    queries: list[str],
    *,
    corpus_id: str = DEMO_CORPUS_ID,
    token_budget: int = 300,
    top_k: int = 5,
    cache: KVCache | None = None,
) -> tuple[CorpusIndex, ProcessingMetrics, list[DemoResult]]:
    """The optional enhanced mode: `run_demo` with the deterministic, offline
    `DemoLLMClient` enriching ambiguous Tier-1 candidates.
    """

    return run_demo(
        sources,
        queries,
        corpus_id=corpus_id,
        token_budget=token_budget,
        top_k=top_k,
        cache=cache,
        llm_client=DemoLLMClient(),
    )


def corpus_content_hashes(sources: dict[str, str]) -> dict[str, str]:
    """Exposed for cache-behavior tests/reporting: the content hash each document would
    be cached under, without actually indexing anything.
    """

    return {source_document_id: content_hash(text) for source_document_id, text in sources.items()}
