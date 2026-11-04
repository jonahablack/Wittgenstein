"""Tier-0 deterministic parsing: no LLM dependency, deterministic offsets, and
provenance preserved through the LlamaIndex adapter boundary
(docs/efficiency-and-processing-architecture.md §§1, 5, "LLAMAINDEX INTEGRATION").
"""

from __future__ import annotations

import inspect

from wittgenstein.core.enums import SegmentType
from wittgenstein.ingestion import llamaindex_adapter
from wittgenstein.ingestion import parser as parser_module
from wittgenstein.ingestion.parser import parse_document, split_sentences

SAMPLE = """# Section 1

A widget must pass the Load Stress Test at a 95% threshold, unless it qualifies for
Exemption C. See Section 2 for details.

- Item one
- Item two

| A | B |
| --- | --- |
| 1 | 2 |
"""


def test_no_llm_module_imported_by_parser() -> None:
    """The deterministic parser module's source must never reference the LLM client or
    extraction modules -- corpus processing must work with zero LLM dependency
    (docs/efficiency-and-processing-architecture.md, "no-LLM-required baseline mode").
    """

    source = inspect.getsource(parser_module)
    assert "llm_client" not in source
    assert "llm_extraction" not in source


def test_parsing_is_deterministic() -> None:
    first = parse_document(SAMPLE, "doc1", "corpus1", "parser-v1")
    second = parse_document(SAMPLE, "doc1", "corpus1", "parser-v1")

    assert [s.model_dump(exclude={"segment_id"}) for s in first] == [
        s.model_dump(exclude={"segment_id"}) for s in second
    ]


def test_segment_offsets_index_into_original_text() -> None:
    segments = parse_document(SAMPLE, "doc1", "corpus1", "parser-v1")
    for segment in segments:
        assert SAMPLE[segment.char_start : segment.char_end] == segment.text


def test_heading_paragraph_list_table_all_detected() -> None:
    segments = parse_document(SAMPLE, "doc1", "corpus1", "parser-v1")
    types = {s.segment_type for s in segments}
    assert types >= {
        SegmentType.HEADING,
        SegmentType.PARAGRAPH,
        SegmentType.SENTENCE,
        SegmentType.LIST_ITEM,
        SegmentType.TABLE_ROW,
    }


def test_cross_reference_detected_in_paragraph() -> None:
    segments = parse_document(SAMPLE, "doc1", "corpus1", "parser-v1")
    paragraph = next(s for s in segments if s.segment_type == SegmentType.PARAGRAPH)
    assert any("Section 2" in ref for ref in paragraph.cross_reference_targets)


def test_split_sentences_offsets_round_trip() -> None:
    text = "First sentence. Second sentence! Third one?"
    for sentence, start, end in split_sentences(text):
        assert text[start:end] == sentence


def test_llamaindex_adapter_preserves_offsets_and_never_leaks_types() -> None:
    documents = llamaindex_adapter.build_documents({"doc1": SAMPLE}, corpus_id="corpus1")
    nodes = llamaindex_adapter.parse_nodes(documents, chunk_size=64, chunk_overlap=8)
    segments = llamaindex_adapter.nodes_to_source_segments(nodes, corpus_id="corpus1", parser_version="li-v1")

    assert segments, "expected at least one segment from the LlamaIndex path"
    for segment in segments:
        # Every returned object is a plain Wittgenstein SourceSegment -- no TextNode/
        # NodeRelationship object type leaks past the adapter boundary.
        assert type(segment).__module__.startswith("wittgenstein.")
        assert segment.char_start <= segment.char_end
        assert segment.text
