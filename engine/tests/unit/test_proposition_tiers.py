"""Tier 1 (rule-based candidate splitting) and Tier 2 (lightweight annotation):
programmatic-only, never a guaranteed semantic interpretation, and never a causal claim
(docs/efficiency-and-processing-architecture.md §§1, 5; CLAUDE.md, "never infer
causality from a trace fact alone").
"""

from __future__ import annotations

from wittgenstein.core.enums import CueEpistemicLabel, SegmentType
from wittgenstein.ingestion.parser import parse_document
from wittgenstein.proposition.annotations import annotate_candidate
from wittgenstein.proposition.candidates import split_candidates

_CAUSAL_WORDS = ("caused", "wrong", "unsafe", "error", "hallucinat")


def _paragraph_segment(text: str):
    segments = parse_document(text, "doc1", "corpus1", "parser-v1")
    return next(s for s in segments if s.segment_type == SegmentType.PARAGRAPH)


def test_candidates_never_rewrite_the_source_segment() -> None:
    segment = _paragraph_segment(
        "A widget qualifies if it passes the Load Stress Test, and it is manufactured "
        "before January 2023, unless it has been substantially modified."
    )
    candidates = split_candidates(segment)

    assert len(candidates) > 1
    for candidate in candidates:
        assert candidate.source_segment_id == segment.segment_id
        assert segment.text[candidate.char_start : candidate.char_end] == candidate.text


def test_split_candidate_offsets_are_relative_to_segment_not_document() -> None:
    segment = _paragraph_segment("Short sentence one. A second sentence follows here.")
    candidates = split_candidates(segment)
    for candidate in candidates:
        assert 0 <= candidate.char_start <= candidate.char_end <= len(segment.text)


def test_ambiguous_flag_set_only_for_conjunction_or_relative_clause_splits() -> None:
    segment = _paragraph_segment(
        "The applicant must submit Form W-100, and evidence of registration, which must be current."
    )
    candidates = split_candidates(segment)
    assert any(c.is_ambiguous for c in candidates)
    for candidate in candidates:
        if candidate.is_ambiguous:
            assert candidate.split_method in ("conjunction", "relative_clause")


def test_annotation_cues_always_carry_a_non_causal_epistemic_label() -> None:
    segment = _paragraph_segment(
        "A widget must pass the test unless it qualifies for Exemption C, except when "
        "remanufactured, according to Section 4."
    )
    candidates = split_candidates(segment)
    annotations = [a for c in candidates for a in annotate_candidate(c)]

    assert annotations, "expected condition/exception/attribution cues to fire on this text"
    for annotation in annotations:
        assert annotation.epistemic_label in (
            CueEpistemicLabel.RESEARCH_HYPOTHESIS,
            CueEpistemicLabel.EXPERIMENTAL_REVIEW_CUE,
        )


def test_annotations_never_contain_causal_or_error_language() -> None:
    segment = _paragraph_segment(
        "A widget must pass the test unless it qualifies for Exemption C, except when "
        "remanufactured, according to Section 4."
    )
    candidates = split_candidates(segment)
    annotations = [a for c in candidates for a in annotate_candidate(c)]

    for annotation in annotations:
        matched_lower = annotation.matched_text.lower()
        assert not any(word in matched_lower for word in _CAUSAL_WORDS)


def test_annotation_offsets_are_relative_to_candidate_text() -> None:
    segment = _paragraph_segment("This applies unless the exemption is granted.")
    for candidate in split_candidates(segment):
        for annotation in annotate_candidate(candidate):
            assert candidate.text[annotation.char_start : annotation.char_end] == annotation.matched_text


def test_no_annotations_on_plain_declarative_text() -> None:
    segment = _paragraph_segment("The widget is blue.")
    candidates = split_candidates(segment)
    annotations = [a for c in candidates for a in annotate_candidate(c)]
    assert annotations == []
