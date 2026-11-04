"""Content-hash caching for corpus-time indexing
(docs/efficiency-and-processing-architecture.md §3): an unchanged document is never
reparsed; a changed one always is.
"""

from __future__ import annotations

from wittgenstein.ingestion.content_hash import content_hash
from wittgenstein.ingestion.corpus_index import index_corpus
from wittgenstein.ingestion.kv_cache import MemoryKVCache
from wittgenstein.metrics.processing_metrics import ProcessingMetrics

DOC = "# Heading\n\nA paragraph with some text."


def test_identical_content_hits_cache_on_second_index() -> None:
    cache = MemoryKVCache()
    metrics1 = ProcessingMetrics()
    metrics2 = ProcessingMetrics()

    first = index_corpus({"doc1": DOC}, "corpus1", cache=cache, metrics=metrics1)
    second = index_corpus({"doc1": DOC}, "corpus1", cache=cache, metrics=metrics2)

    assert metrics1.cache_misses == 1
    assert metrics1.cache_hits == 0
    assert metrics2.cache_hits == 1
    assert metrics2.cache_misses == 0
    assert {s.segment_id for s in first.segments.values()} == {s.segment_id for s in second.segments.values()}


def test_changed_content_is_a_cache_miss() -> None:
    cache = MemoryKVCache()
    metrics = ProcessingMetrics()

    index_corpus({"doc1": DOC}, "corpus1", cache=cache, metrics=metrics)
    index_corpus({"doc1": DOC + " Extra sentence."}, "corpus1", cache=cache, metrics=metrics)

    assert metrics.cache_misses == 2
    assert metrics.cache_hits == 0


def test_content_hash_changes_with_content() -> None:
    assert content_hash(DOC) != content_hash(DOC + " ")
    assert content_hash(DOC) == content_hash(DOC)


def test_corpus_profile_reflects_actual_corpus_not_a_guess() -> None:
    index = index_corpus({"doc1": DOC}, "corpus1")
    assert index.corpus_profile is not None
    assert index.corpus_profile.document_count == 1
    assert index.corpus_profile.token_count is None  # not computed by the deterministic path -- never guessed
