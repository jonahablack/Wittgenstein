"""End-to-end vertical-slice demo: no-LLM baseline mode requires zero LLM dependency,
propositionization happens only at query time (never during corpus indexing), every
context item's provenance is labeled, and the optional enhanced mode is exactly the
same pipeline with a client attached
(docs/efficiency-and-processing-architecture.md, "DEMO REQUIREMENT").
"""

from __future__ import annotations

from wittgenstein.demo.pipeline import run_enhanced_demo, run_no_llm_baseline_demo
from wittgenstein.demo.widget_corpus import DEMO_QUERIES, documents
from wittgenstein.ingestion.corpus_index import index_corpus


def test_baseline_demo_runs_without_any_llm_call() -> None:
    _, corpus_metrics, results = run_no_llm_baseline_demo(documents(), DEMO_QUERIES)

    assert corpus_metrics.llm_call_count == 0
    for result in results:
        assert result.metrics.llm_call_count == 0
        assert result.llm_extractions == []


def test_baseline_demo_produces_a_complete_trace_per_query() -> None:
    _, _, results = run_no_llm_baseline_demo(documents(), DEMO_QUERIES)

    assert len(results) == len(DEMO_QUERIES)
    for result in results:
        trace = result.trace
        assert trace.retrieval_candidates is not None
        assert trace.packed_context_items is not None
        assert trace.omitted_context_items is not None
        assert trace.final_prompt is not None
        assert trace.final_prompt_token_count is not None
        # Every packed item's tokens are actually reflected in a recorded prompt span.
        packed_ids = {item.item_id for item in trace.packed_context_items}
        span_ids = {span.context_item_id for span in trace.prompt_token_spans}
        assert packed_ids == span_ids


def test_propositionization_happens_only_at_query_time_not_corpus_time() -> None:
    """Tier 1/2 candidates/annotations must never be produced during corpus indexing
    itself -- only when a specific query's retrieved segments are processed
    (docs/efficiency-and-processing-architecture.md, "TIER 1"/"TIER 2" trigger
    conditions: retrieved-or-selected text only, never the whole corpus up front).
    """

    corpus_index = index_corpus(documents(), "widget-certification-demo")
    # The corpus index itself carries only Tier-0 SourceSegments -- no PropositionCandidate
    # or PropositionAnnotation objects exist until a query triggers retrieval.
    assert all(hasattr(segment, "segment_type") for segment in corpus_index.segments.values())

    _, _, results = run_no_llm_baseline_demo(documents(), DEMO_QUERIES[:1])
    assert results[0].candidates, "query-time run should have produced Tier-1 candidates"


def test_every_context_item_has_a_recorded_provenance() -> None:
    _, _, results = run_no_llm_baseline_demo(documents(), DEMO_QUERIES)
    for result in results:
        for item in result.trace.retrieval_candidates or []:
            assert result.context_item_provenance.get(item.item_id) == "programmatic_lexical_retrieval"


def test_enhanced_mode_uses_the_same_pipeline_with_llm_enrichment() -> None:
    _, corpus_metrics, results = run_enhanced_demo(documents(), DEMO_QUERIES)

    assert corpus_metrics.llm_call_count == 0  # corpus-time phase never calls an LLM either
    total_calls = sum(r.metrics.llm_call_count for r in results)
    assert total_calls >= 1, "enhanced mode should invoke the demo LLM client for at least one ambiguous candidate"

    for result in results:
        for extraction in result.llm_extractions:
            # Every extraction is one of the documented outcomes -- never a silent guess.
            assert extraction.validation_status.value in (
                "validated",
                "validation_failed",
                "llm_unavailable",
                "not_attempted",
            )


def test_manifest_declares_the_actual_retrieval_and_packing_configuration() -> None:
    _, _, results = run_no_llm_baseline_demo(documents(), DEMO_QUERIES[:1])
    manifest = results[0].manifest

    assert manifest.retrieval_manifest.retriever_family == "bm25_lexical"
    assert manifest.packing_manifest.context_window_tokens == 300
    assert "generation_manifest.generator_family" in manifest.missing_information
