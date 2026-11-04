"""Deterministic, dependency-free parsing of markdown-like plain text into Tier-0
structural SourceSegments (headings/paragraphs/sentences/list items/table rows/
captions/footnotes), with full character-offset provenance.

No LLM, no heavy NLP dependency -- regex and line-oriented parsing only, per
docs/efficiency-and-processing-architecture.md §1. Supports the subset of markdown
needed for the demo corpus (ATX headings, blank-line paragraphs, "-"/"*"/numbered list
items, pipe tables, figure/table captions, footnote-style lines) -- documented as a
scoping decision, not a claim of general-purpose document parsing (see
docs/efficiency-and-processing-architecture.md §8, "optional / future").
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from itertools import pairwise

from wittgenstein.core.enums import SegmentType
from wittgenstein.schemas.proposition import SourceSegment

_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*)$")
_LIST_ITEM_RE = re.compile(r"^\s*(?:[-*]|\d+\.)\s+(.*)$")
_TABLE_ROW_RE = re.compile(r"^\s*\|(.*)\|\s*$")
_TABLE_SEPARATOR_RE = re.compile(r"^\s*\|?[\s:|-]+\|?\s*$")
_CAPTION_RE = re.compile(r"^\s*(Figure|Table)\s+\d+[:.]", re.IGNORECASE)
_FOOTNOTE_RE = re.compile(r"^\s*\[\^?\d+\]:?\s")

#: Explicit legal-structure markers, additive to the segment types above -- never used
#: to change segment_type/location/text/offsets, only to populate the new
#: legal_article_number/legal_paragraph_number/legal_point_identifier/
#: legal_annex_identifier fields (docs/cross-reference-granularity-resolution-plan.md
#: §4). A numbered list marker ("1. ...") is exactly what _LIST_ITEM_RE already
#: recognizes; this pattern additionally captures the digit itself, which the existing
#: list-item branch discards after matching.
_NUMBERED_PARAGRAPH_MARKER_RE = re.compile(r"^\s*(\d+)\.\s+")
#: A lettered point marker on its own line -- "(a) ...". Deliberately does not match
#: _LIST_ITEM_RE (bullets/numbers only), so points are found via the paragraph-flush
#: path, not the list-item path.
_POINT_MARKER_RE = re.compile(r"^\(([a-z])\)\s")
#: A standalone "Article <N>" / "Annex <roman numeral>" title paragraph -- the whole
#: paragraph text must be just this (not merely contain it), matching this corpus's
#: convention of the article/annex number as its own line.
_ARTICLE_TITLE_RE = re.compile(r"^Article\s+(\d+)$", re.IGNORECASE)
_ANNEX_TITLE_RE = re.compile(r"^Annex\s+([IVXLCDM]+)$", re.IGNORECASE)

# Sentence boundary: '.', '?', or '!' followed by whitespace and a capital letter or
# end of string. Deliberately simple -- a common set of abbreviations is protected from
# false splits, but this is not a full sentence tokenizer (documented scoping decision).
_ABBREVIATIONS = {"e.g.", "i.e.", "etc.", "vs.", "dr.", "mr.", "mrs.", "ms.", "no."}
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.?!])\s+(?=[A-Z(\"'])")


def _local_offset(haystack: str, needle: str) -> int:
    """Offset of a stripped/derived substring within the line it came from -- so
    char_start/char_end always index the segment's own `text`, not the raw line
    including markdown syntax or leading whitespace stripped away.
    """

    return haystack.index(needle) if needle else 0


def _looks_like_abbreviation_boundary(text: str, split_pos: int) -> bool:
    preceding = text[:split_pos].rstrip()
    return any(preceding.lower().endswith(abbrev) for abbrev in _ABBREVIATIONS)


def split_sentences(text: str) -> list[tuple[str, int, int]]:
    """Return (sentence_text, char_start, char_end) triples, offsets relative to `text`."""

    if not text.strip():
        return []
    boundaries = [0]
    for match in _SENTENCE_SPLIT_RE.finditer(text):
        pos = match.start()
        if _looks_like_abbreviation_boundary(text, pos):
            continue
        boundaries.append(match.end())
    boundaries.append(len(text))
    boundaries = sorted(set(boundaries))

    sentences: list[tuple[str, int, int]] = []
    for start, end in pairwise(boundaries):
        raw = text[start:end]
        stripped = raw.strip()
        if not stripped:
            continue
        local_start = start + raw.index(stripped)
        local_end = local_start + len(stripped)
        sentences.append((stripped, local_start, local_end))
    return sentences


@dataclass
class _Line:
    text: str
    char_start: int
    char_end: int


def _split_lines_with_offsets(text: str) -> list[_Line]:
    lines: list[_Line] = []
    pos = 0
    for raw_line in text.splitlines(keepends=True):
        stripped = raw_line.rstrip("\n").rstrip("\r")
        lines.append(_Line(text=stripped, char_start=pos, char_end=pos + len(stripped)))
        pos += len(raw_line)
    return lines


def parse_document(
    text: str,
    source_document_id: str,
    corpus_id: str,
    parser_version: str,
    source_version: str | None = None,
) -> list[SourceSegment]:
    """Parse `text` into Tier-0 SourceSegments with full offset/provenance tracking.
    Deterministic and dependency-free -- calling this twice on identical input always
    produces identical output (up to segment_id numbering).
    """

    lines = _split_lines_with_offsets(text)
    segments: list[SourceSegment] = []
    seg_counter = 0

    def next_id() -> str:
        nonlocal seg_counter
        seg_counter += 1
        return f"{source_document_id}-seg{seg_counter}"

    heading_stack: list[tuple[int, str, str]] = []  # (level, segment_id, text)
    current_heading_id: str | None = None
    heading_path: list[str] = []

    # Legal-structure context, carried forward across segments until an explicit new
    # marker updates it -- never inferred from source_document_id/filename, never
    # guessed when no marker is present (docs/cross-reference-granularity-resolution-plan.md
    # §4). A point identifier is per-segment only (never carried forward) -- it is
    # re-derived fresh for each paragraph-flushed segment.
    current_article_number: str | None = None
    current_paragraph_number: str | None = None
    current_annex_identifier: str | None = None

    paragraph_buffer: list[_Line] = []
    paragraph_counter_by_section = 0

    def flush_paragraph() -> None:
        nonlocal paragraph_buffer, paragraph_counter_by_section
        nonlocal current_article_number, current_paragraph_number, current_annex_identifier
        if not paragraph_buffer:
            return
        para_text = "\n".join(line.text for line in paragraph_buffer)
        para_start = paragraph_buffer[0].char_start
        para_end = paragraph_buffer[-1].char_end
        paragraph_counter_by_section += 1
        para_id = next_id()
        location = " > ".join([*heading_path, f"Paragraph {paragraph_counter_by_section}"])

        article_title_match = _ARTICLE_TITLE_RE.match(para_text)
        annex_title_match = _ANNEX_TITLE_RE.match(para_text)
        if article_title_match:
            current_article_number = article_title_match.group(1)
            current_paragraph_number = None
        elif annex_title_match:
            current_annex_identifier = annex_title_match.group(1).upper()
            current_paragraph_number = None
        point_match = _POINT_MARKER_RE.match(para_text)
        point_identifier = point_match.group(1) if point_match else None

        segments.append(
            SourceSegment(
                segment_id=para_id,
                source_document_id=source_document_id,
                corpus_id=corpus_id,
                source_version=source_version,
                segment_type=SegmentType.PARAGRAPH,
                location=location,
                text=para_text,
                char_start=para_start,
                char_end=para_end,
                parent_segment_id=current_heading_id,
                cross_reference_targets=_find_cross_references(para_text),
                legal_article_number=current_article_number,
                legal_paragraph_number=current_paragraph_number,
                legal_point_identifier=point_identifier,
                legal_annex_identifier=current_annex_identifier,
                parser_version=parser_version,
            )
        )
        for sent_idx, (sent_text, rel_start, rel_end) in enumerate(split_sentences(para_text), start=1):
            segments.append(
                SourceSegment(
                    segment_id=next_id(),
                    source_document_id=source_document_id,
                    corpus_id=corpus_id,
                    source_version=source_version,
                    segment_type=SegmentType.SENTENCE,
                    location=f"{location} > Sentence {sent_idx}",
                    text=sent_text,
                    char_start=para_start + rel_start,
                    char_end=para_start + rel_end,
                    parent_segment_id=para_id,
                    cross_reference_targets=_find_cross_references(sent_text),
                    legal_article_number=current_article_number,
                    legal_paragraph_number=current_paragraph_number,
                    legal_point_identifier=point_identifier,
                    legal_annex_identifier=current_annex_identifier,
                    parser_version=parser_version,
                )
            )
        paragraph_buffer = []

    list_item_counter = 0
    table_row_counter = 0
    idx = 0
    while idx < len(lines):
        line = lines[idx]
        stripped = line.text.strip()

        if not stripped:
            flush_paragraph()
            idx += 1
            continue

        heading_match = _HEADING_RE.match(line.text)
        if heading_match:
            flush_paragraph()
            level = len(heading_match.group(1))
            raw_heading_group = heading_match.group(2)
            heading_text = raw_heading_group.strip()
            heading_local_start = heading_match.start(2) + _local_offset(raw_heading_group, heading_text)
            heading_stack = [entry for entry in heading_stack if entry[0] < level]
            heading_id = next_id()
            parent_heading_id = heading_stack[-1][1] if heading_stack else None
            heading_path = [*(text for _, _, text in heading_stack), heading_text]
            segments.append(
                SourceSegment(
                    segment_id=heading_id,
                    source_document_id=source_document_id,
                    corpus_id=corpus_id,
                    source_version=source_version,
                    segment_type=SegmentType.HEADING,
                    location=" > ".join(heading_path),
                    text=heading_text,
                    char_start=line.char_start + heading_local_start,
                    char_end=line.char_start + heading_local_start + len(heading_text),
                    parent_segment_id=parent_heading_id,
                    cross_reference_targets=_find_cross_references(heading_text),
                    legal_article_number=current_article_number,
                    legal_paragraph_number=current_paragraph_number,
                    legal_annex_identifier=current_annex_identifier,
                    parser_version=parser_version,
                )
            )
            heading_stack.append((level, heading_id, heading_text))
            current_heading_id = heading_id
            paragraph_counter_by_section = 0
            list_item_counter = 0
            table_row_counter = 0
            idx += 1
            continue

        if _CAPTION_RE.match(line.text):
            flush_paragraph()
            segments.append(
                SourceSegment(
                    segment_id=next_id(),
                    source_document_id=source_document_id,
                    corpus_id=corpus_id,
                    source_version=source_version,
                    segment_type=SegmentType.CAPTION,
                    location=" > ".join([*heading_path, "Caption"]),
                    text=stripped,
                    char_start=line.char_start + _local_offset(line.text, stripped),
                    char_end=line.char_start + _local_offset(line.text, stripped) + len(stripped),
                    parent_segment_id=current_heading_id,
                    cross_reference_targets=_find_cross_references(stripped),
                    legal_article_number=current_article_number,
                    legal_paragraph_number=current_paragraph_number,
                    legal_annex_identifier=current_annex_identifier,
                    parser_version=parser_version,
                )
            )
            idx += 1
            continue

        if _FOOTNOTE_RE.match(line.text):
            flush_paragraph()
            segments.append(
                SourceSegment(
                    segment_id=next_id(),
                    source_document_id=source_document_id,
                    corpus_id=corpus_id,
                    source_version=source_version,
                    segment_type=SegmentType.FOOTNOTE,
                    location=" > ".join([*heading_path, "Footnote"]),
                    text=stripped,
                    char_start=line.char_start + _local_offset(line.text, stripped),
                    char_end=line.char_start + _local_offset(line.text, stripped) + len(stripped),
                    parent_segment_id=current_heading_id,
                    cross_reference_targets=_find_cross_references(stripped),
                    legal_article_number=current_article_number,
                    legal_paragraph_number=current_paragraph_number,
                    legal_annex_identifier=current_annex_identifier,
                    parser_version=parser_version,
                )
            )
            idx += 1
            continue

        list_match = _LIST_ITEM_RE.match(line.text)
        if list_match:
            flush_paragraph()
            list_item_counter += 1
            raw_list_group = list_match.group(1)
            list_text = raw_list_group.strip()
            list_local_start = list_match.start(1) + _local_offset(raw_list_group, list_text)
            numbered_marker_match = _NUMBERED_PARAGRAPH_MARKER_RE.match(line.text)
            if numbered_marker_match:
                current_paragraph_number = numbered_marker_match.group(1)
            segments.append(
                SourceSegment(
                    segment_id=next_id(),
                    source_document_id=source_document_id,
                    corpus_id=corpus_id,
                    source_version=source_version,
                    segment_type=SegmentType.LIST_ITEM,
                    location=" > ".join([*heading_path, f"List item {list_item_counter}"]),
                    text=list_text,
                    char_start=line.char_start + list_local_start,
                    char_end=line.char_start + list_local_start + len(list_text),
                    parent_segment_id=current_heading_id,
                    cross_reference_targets=_find_cross_references(list_text),
                    legal_article_number=current_article_number,
                    legal_paragraph_number=current_paragraph_number,
                    legal_annex_identifier=current_annex_identifier,
                    parser_version=parser_version,
                )
            )
            idx += 1
            continue

        table_row_match = _TABLE_ROW_RE.match(line.text)
        if table_row_match and not _TABLE_SEPARATOR_RE.match(line.text):
            flush_paragraph()
            table_row_counter += 1
            raw_row_group = table_row_match.group(1)
            row_text = raw_row_group.strip()
            row_local_start = table_row_match.start(1) + _local_offset(raw_row_group, row_text)
            segments.append(
                SourceSegment(
                    segment_id=next_id(),
                    source_document_id=source_document_id,
                    corpus_id=corpus_id,
                    source_version=source_version,
                    segment_type=SegmentType.TABLE_ROW,
                    location=" > ".join([*heading_path, f"Table row {table_row_counter}"]),
                    text=row_text,
                    char_start=line.char_start + row_local_start,
                    char_end=line.char_start + row_local_start + len(row_text),
                    parent_segment_id=current_heading_id,
                    cross_reference_targets=_find_cross_references(row_text),
                    legal_article_number=current_article_number,
                    legal_paragraph_number=current_paragraph_number,
                    legal_annex_identifier=current_annex_identifier,
                    parser_version=parser_version,
                )
            )
            idx += 1
            continue

        if _TABLE_SEPARATOR_RE.match(line.text) and line.text.strip():
            idx += 1
            continue

        paragraph_buffer.append(line)
        idx += 1

    flush_paragraph()
    return segments


_CROSS_REF_RE = re.compile(
    r"\b(Section|Table|Figure|Exemption|Appendix|Clause)\s+[A-Za-z0-9.]+(?:\([a-z]\))?", re.IGNORECASE
)


def _find_cross_references(text: str) -> list[str]:
    return sorted(set(m.group(0) for m in _CROSS_REF_RE.finditer(text)))
