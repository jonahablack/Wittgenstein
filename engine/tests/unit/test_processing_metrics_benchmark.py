"""A larger-corpus benchmark fixture, per
docs/efficiency-and-processing-architecture.md §6 ("Performance instrumentation"): this
does not assert any specific throughput number (CLAUDE.md-equivalent rule in that doc,
"Do not set arbitrary throughput claims") -- it only asserts that `ProcessingMetrics`
is actually populated with real measurements on a non-trivial corpus, and that indexing
a larger corpus completes without pathological (e.g. quadratic-blowup) slowdown.
"""

from __future__ import annotations

import time
from datetime import UTC, datetime

from wittgenstein.demo.pipeline import build_bm25_index, run_demo_query
from wittgenstein.ingestion.corpus_index import index_corpus
from wittgenstein.metrics.processing_metrics import ProcessingMetrics
from wittgenstein.schemas.manifest import PipelineManifest

_PARAGRAPH_TEMPLATE = (
    "Section {n}: A widget of Class {cls} must pass its designated test at the "
    "threshold specified in Table 3, unless an exemption under Section 4 applies. "
    "Facilities are inspected once per Program Year {n}."
)


def _synthetic_corpus(n_documents: int, paragraphs_per_document: int) -> dict[str, str]:
    sources: dict[str, str] = {}
    for doc_i in range(n_documents):
        lines = [f"# Document {doc_i}", ""]
        for para_i in range(paragraphs_per_document):
            n = doc_i * paragraphs_per_document + para_i
            lines.append(_PARAGRAPH_TEMPLATE.format(n=n, cls=(n % 3) + 1))
            lines.append("")
        sources[f"doc-{doc_i}"] = "\n".join(lines)
    return sources


def test_indexing_a_larger_corpus_populates_real_metrics_and_completes_promptly() -> None:
    sources = _synthetic_corpus(n_documents=50, paragraphs_per_document=20)  # 1000 paragraphs

    metrics = ProcessingMetrics()
    start = time.perf_counter()
    index_corpus(sources, "benchmark-corpus", metrics=metrics)
    elapsed = time.perf_counter() - start

    assert metrics.corpus_document_count == 50
    assert metrics.corpus_segment_count is not None and metrics.corpus_segment_count > 1000
    # A generous ceiling, not a throughput claim -- this guards against a pathological
    # regression (e.g. an accidental O(n^2) rescan), not a performance target.
    assert elapsed < 15.0


def test_query_time_pipeline_scales_to_a_larger_corpus() -> None:
    sources = _synthetic_corpus(n_documents=50, paragraphs_per_document=20)
    corpus_index = index_corpus(sources, "benchmark-corpus")
    bm25_index = build_bm25_index(corpus_index)
    manifest = PipelineManifest(
        manifest_id="benchmark-manifest",
        system_name="benchmark",
        system_version="0.1.0",
        created_at=datetime.now(UTC),
    )

    start = time.perf_counter()
    result = run_demo_query(
        corpus_index,
        bm25_index,
        "What threshold applies to a Class 1 widget?",
        trace_id="bench-t1",
        manifest=manifest,
    )
    elapsed = time.perf_counter() - start

    assert result.metrics.candidate_count is not None and result.metrics.candidate_count > 0
    assert result.metrics.retrieval_latency_seconds is not None
    assert elapsed < 5.0
