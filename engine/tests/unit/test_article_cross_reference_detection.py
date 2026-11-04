"""Legal citation (Article/Articles/Annex) cross-reference detection --
docs/eu-ai-act-article-cross-reference-fix-plan.md. Covers the milestone's 22 required
test categories (numbering preserved in each test's docstring/name for traceability).
Backward-compatibility categories (10, 17, 18, 20, 21) confirm the pre-existing
Section/Table/... path and the diagnostic module's other guarantees are unaffected.
"""

from __future__ import annotations

import subprocess
from datetime import UTC, datetime
from pathlib import Path

from wittgenstein.core.enums import CrossReferenceTargetState, SegmentType, TraceStatus
from wittgenstein.ingestion.corpus_index import CorpusIndex
from wittgenstein.review.cross_reference_diagnostics import cross_reference_warning, detect_cross_reference_markers
from wittgenstein.schemas.proposition import SourceSegment
from wittgenstein.schemas.trace import AnswerClaim, ContextItem, QueryTrace

_REPO_ROOT = Path(__file__).resolve().parents[2]


def _segment(
    segment_id: str, location: str, *, source_document_id: str = "doc-1", text: str = "placeholder text"
) -> SourceSegment:
    return SourceSegment(
        segment_id=segment_id,
        source_document_id=source_document_id,
        corpus_id="test-corpus",
        segment_type=SegmentType.PARAGRAPH,
        location=location,
        text=text,
        char_start=0,
        char_end=len(text),
        parser_version="test-fixture-1",
    )


def _corpus_index(*segments: SourceSegment) -> CorpusIndex:
    index = CorpusIndex(corpus_id="test-corpus")
    for segment in segments:
        index.segments[segment.segment_id] = segment
    return index


def _trace(
    *,
    retrieval_candidates=None,
    selected_context_items=None,
    packed_context_items=None,
    omitted_context_items=None,
) -> QueryTrace:
    return QueryTrace(
        trace_id="t1",
        manifest_id="m1",
        corpus_id="test-corpus",
        query="q",
        query_timestamp=datetime.now(UTC),
        answer="a",
        trace_status=TraceStatus.COMPLETE,
        retrieval_candidates=retrieval_candidates,
        selected_context_items=selected_context_items,
        packed_context_items=packed_context_items,
        omitted_context_items=omitted_context_items,
    )


def _item(segment_id: str) -> ContextItem:
    return ContextItem(item_id=segment_id, segment_id=segment_id, rank=1)


def _markers(text: str, *segments: SourceSegment, trace: QueryTrace | None = None):
    claim = AnswerClaim(claim_id="c1", text=text)
    corpus_index = _corpus_index(*segments)
    return detect_cross_reference_markers(claim, corpus_index, trace or _trace(packed_context_items=[]))


# 1. Article 49
def test_01_article_49() -> None:
    markers = _markers("See Article 49 for details.")
    assert len(markers) == 1
    assert markers[0].marker_text == "Article 49"
    assert markers[0].reference_type == "article"
    assert markers[0].target_identifier == "article:49"


# 2. Article 6(4)
def test_02_article_6_paragraph_4() -> None:
    markers = _markers("Article 6(4) applies here.")
    assert len(markers) == 1
    assert markers[0].marker_text == "Article 6(4)"
    assert markers[0].target_identifier == "article:6:paragraph:4"
    assert markers[0].targets[0].article_number == "6"
    assert markers[0].targets[0].paragraph_number == "4"


# 3. Article 6(4), point (a)
def test_03_article_6_paragraph_4_point_a() -> None:
    markers = _markers("Article 6(4), point (a) applies.")
    assert len(markers) == 1
    assert markers[0].marker_text == "Article 6(4), point (a)"
    assert markers[0].target_identifier == "article:6:paragraph:4:point:a"
    target = markers[0].targets[0]
    assert target.subdivision_type == "point"
    assert target.subdivision_identifier == "a"


# 4. Article 50(1), point (b)
def test_04_article_50_paragraph_1_point_b() -> None:
    markers = _markers("Article 50(1), point (b) applies.")
    assert len(markers) == 1
    assert markers[0].target_identifier == "article:50:paragraph:1:point:b"


# 5. Articles 6 and 49
def test_05_articles_6_and_49() -> None:
    markers = _markers("Articles 6 and 49 are relevant.")
    assert len(markers) == 1
    marker = markers[0]
    assert marker.marker_text == "Articles 6 and 49"
    assert marker.reference_type == "article"
    assert marker.target_identifier is None  # ambiguous which single target -- multi-target marker
    assert {t.target_identifier for t in marker.targets} == {"article:6", "article:49"}


# 6. Articles 6, 13 and 50
def test_06_articles_6_13_and_50() -> None:
    markers = _markers("Articles 6, 13 and 50 apply.")
    assert len(markers) == 1
    assert {t.target_identifier for t in markers[0].targets} == {"article:6", "article:13", "article:50"}


# 7. Articles 6 to 13 (range expansion, not reduced to only Article 6)
def test_07_articles_6_to_13_range_expanded() -> None:
    markers = _markers("Articles 6 to 13 apply.")
    assert len(markers) == 1
    marker = markers[0]
    assert marker.range_start == "6"
    assert marker.range_end == "13"
    expanded = {t.article_number for t in marker.targets}
    assert expanded == {str(n) for n in range(6, 14)}


# 8. Articles 6-13 (en dash / hyphen range expansion)
def test_08_articles_en_dash_range_expanded() -> None:
    markers = _markers("Articles 6–13 apply.")  # en dash
    assert len(markers) == 1
    assert markers[0].range_start == "6"
    assert markers[0].range_end == "13"
    assert len(markers[0].targets) == 8


# 9. Annex III
def test_09_annex_iii() -> None:
    markers = _markers("See Annex III for the list.")
    assert len(markers) == 1
    assert markers[0].reference_type == "annex"
    assert markers[0].target_identifier == "annex:III"


# 10. Existing Section/Table/Figure/Exemption/Appendix/Clause patterns still detected.
def test_10_existing_non_legal_patterns_still_detected() -> None:
    for keyword, text in (
        ("Section", "See Section 4 for details."),
        ("Table", "See Table 3 for details."),
        ("Figure", "See Figure 2 for details."),
        ("Exemption", "See Exemption C for details."),
        ("Appendix", "See Appendix A for details."),
        ("Clause", "See Clause 5 for details."),
    ):
        markers = _markers(text)
        assert len(markers) == 1, keyword
        assert markers[0].marker_text.startswith(keyword), keyword


# 11. Original surface span preservation.
def test_11_surface_span_preserved() -> None:
    text = "Prefix text. Article 6(4) applies here."
    markers = _markers(text)
    assert len(markers) == 1
    start, end = markers[0].source_span
    assert text[start:end] == "Article 6(4)"


# 12. Canonical target normalization.
def test_12_canonical_target_normalization() -> None:
    assert _markers("Article 49")[0].target_identifier == "article:49"
    assert _markers("Article 6(4)")[0].target_identifier == "article:6:paragraph:4"
    assert _markers("Article 6(4), point (a)")[0].target_identifier == "article:6:paragraph:4:point:a"
    assert _markers("Annex III")[0].target_identifier == "annex:III"


# 13. Multi-target reference preservation (no silent reduction).
def test_13_multi_target_reference_preservation() -> None:
    markers = _markers("Articles 6, 13 and 50 apply.")
    assert len(markers[0].targets) == 3
    identifiers = [t.target_identifier for t in markers[0].targets]
    assert identifiers == ["article:6", "article:13", "article:50"]  # order preserved


# 14. Local unambiguous target resolution.
def test_14_local_unambiguous_target_resolution() -> None:
    seg = _segment("art49-seg1", "Paragraph 1", source_document_id="article-49-registration")
    markers = _markers(
        "See Article 49 for details.",
        seg,
        trace=_trace(packed_context_items=[_item("art49-seg1")]),
    )
    assert markers[0].target_state == CrossReferenceTargetState.PACKED
    assert markers[0].targets[0].target_segment_ids == ["art49-seg1"]


# 15. Ambiguous target remaining unknown.
def test_15_ambiguous_target_remains_unknown() -> None:
    seg_a = _segment("dup-a", "Paragraph 1", source_document_id="article-49-first-copy")
    seg_b = _segment("dup-b", "Paragraph 1", source_document_id="article-49-second-copy")
    markers = _markers("See Article 49 for details.", seg_a, seg_b)
    assert markers[0].target_state == CrossReferenceTargetState.UNKNOWN
    assert markers[0].targets[0].target_segment_ids == []


# 16. Missing target remaining unknown.
def test_16_missing_target_remains_unknown() -> None:
    seg = _segment("unrelated-seg1", "Paragraph 1", source_document_id="article-6-classification")
    markers = _markers("See Article 999 for details.", seg)
    assert markers[0].target_state == CrossReferenceTargetState.UNKNOWN
    assert markers[0].targets[0].target_segment_ids == []


# 17. No automatic retrieval, selection, packing, or closure.
def test_17_no_automatic_retrieval_selection_packing_or_closure() -> None:
    seg = _segment("art49-seg1", "Paragraph 1", source_document_id="article-49-registration")
    trace = _trace(packed_context_items=[])
    before_packed = list(trace.packed_context_items or [])
    _markers("See Article 49 for details.", seg, trace=trace)
    # detect_cross_reference_markers never mutates the trace it was given.
    assert list(trace.packed_context_items or []) == before_packed


# 18. No legal/factual causal claim in reviewer-facing explanations.
def test_18_no_legal_or_causal_claim_in_warning() -> None:
    seg = _segment("art49-seg1", "Paragraph 1", source_document_id="article-49-registration")
    markers = _markers("See Article 49 for details.", seg)  # not packed -> warning expected
    warning = cross_reference_warning(markers[0])
    assert warning is not None
    for prohibited in (
        "unsupported",
        "caused an error",
        "resolves the claim",
        "governs",
        "legal advice",
    ):
        assert prohibited not in warning.lower()
    assert warning.startswith("An explicit reference may require additional source context.")


# 19. Baseline pilot output is not overwritten.
def test_19_baseline_pilot_output_not_overwritten() -> None:
    baseline_dir = (
        _REPO_ROOT
        / "data/examples/evidence_set_diagnostics/local_corpora/eu-ai-act-2024"
        / "output-baseline-before-article-xref"
    )
    if not baseline_dir.exists():
        return  # local-only artifact; nothing to check in an environment without it
    case3 = baseline_dir / "euaia-003-explicit-cross-reference-registration.diagnostic.json"
    assert case3.exists()
    # The pre-fix baseline must still show zero cross-reference markers for case 3 --
    # exactly the finding this fix addresses; if this ever becomes non-empty, the
    # baseline was overwritten by a later (post-fix) run and is no longer a baseline.
    import json

    data = json.loads(case3.read_text())
    all_markers = [m for markers in data.get("cross_reference_markers", {}).values() for m in markers]
    assert all_markers == []


# 20. Existing widget cross-reference behavior remains unchanged.
def test_20_existing_widget_style_behavior_unchanged() -> None:
    seg = _segment("widget-seg1", "Handbook > Section 4", source_document_id="certification-handbook")
    markers = _markers(
        "See Section 4 for the full requirements.",
        seg,
        trace=_trace(packed_context_items=[_item("widget-seg1")]),
    )
    assert len(markers) == 1
    assert markers[0].marker_text == "Section 4"
    assert markers[0].target_state == CrossReferenceTargetState.PACKED
    assert cross_reference_warning(markers[0]) is None


# 21. Existing diagnostics remain deterministic.
def test_21_deterministic_output() -> None:
    seg = _segment("art49-seg1", "Paragraph 1", source_document_id="article-49-registration")
    text = "Articles 6, 13 and 50 apply, see also Article 49(2) and Annex III."
    first = _markers(text, seg)
    second = _markers(text, seg)
    assert [(m.marker_text, m.target_identifier, [t.target_identifier for t in m.targets]) for m in first] == [
        (m.marker_text, m.target_identifier, [t.target_identifier for t in m.targets]) for m in second
    ]


# 22. No raw EU Act source text is added to git.
def test_22_no_raw_eu_act_source_text_tracked_by_git() -> None:
    result = subprocess.run(
        ["git", "ls-files", "data/examples/evidence_set_diagnostics/local_corpora/"],
        cwd=_REPO_ROOT,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert result.stdout.strip() == ""
