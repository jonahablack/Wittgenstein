"""BM25 lexical retrieval: the retrieval baseline, requiring no embeddings and no LLM
(docs/efficiency-and-processing-architecture.md, "RETRIEVAL").
"""

from __future__ import annotations

from wittgenstein.retrieval.lexical import BM25Index, tokenize
from wittgenstein.schemas.proposition import SourceSegment


def _segment(segment_id: str, text: str) -> SourceSegment:
    return SourceSegment(
        segment_id=segment_id,
        source_document_id="doc1",
        corpus_id="corpus1",
        segment_type="paragraph",
        location="loc",
        text=text,
        char_start=0,
        char_end=len(text),
        parser_version="test-v1",
    )


def test_tokenize_lowercases_and_strips_punctuation() -> None:
    assert tokenize("Widget-Class I, please!") == ["widget", "class", "i", "please"]


def test_search_ranks_the_more_relevant_document_first() -> None:
    index = BM25Index(
        [
            _segment("s1", "The Load Stress Test requires a 95 percent pass threshold for Class I widgets."),
            _segment("s2", "Facility registration must be renewed every five years for Class I facilities."),
        ]
    )
    results = index.search("Load Stress Test threshold Class I", top_k=2)
    assert results[0].segment_id == "s1"
    assert results[0].rank == 1
    assert len(results) == 2
    assert results[0].score > results[1].score


def test_document_with_no_matching_terms_is_excluded_not_scored_zero() -> None:
    index = BM25Index(
        [
            _segment("s1", "The Load Stress Test requires a 95 percent pass threshold."),
            _segment("s2", "Facility registration must be renewed every five years."),
        ]
    )
    results = index.search("Load Stress Test threshold", top_k=2)
    assert [r.segment_id for r in results] == ["s1"]


def test_search_returns_at_most_top_k() -> None:
    index = BM25Index([_segment(f"s{i}", f"widget test number {i}") for i in range(10)])
    results = index.search("widget test", top_k=3)
    assert len(results) == 3


def test_query_with_no_matching_terms_returns_empty() -> None:
    index = BM25Index([_segment("s1", "widgets and certification")])
    assert index.search("completely unrelated zzzqqq", top_k=5) == []
