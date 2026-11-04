"""Cross-reference target-state measurement -- docs/cross-reference-diagnostic-spec.md.
Fixtures 1-4 from docs/evidence-set-real-corpus-diagnostics-plan.md ("FIXTURES AND
TESTS"): target present and packed; target present but not retrieved; target
retrieved but omitted by budget; target needed for interpretation but unresolved.
"""

from __future__ import annotations

from datetime import UTC, datetime

from wittgenstein.core.enums import CrossReferenceTargetState, SegmentType, TraceStatus
from wittgenstein.ingestion.corpus_index import CorpusIndex
from wittgenstein.review.cross_reference_diagnostics import cross_reference_warning, detect_cross_reference_markers
from wittgenstein.schemas.proposition import SourceSegment
from wittgenstein.schemas.trace import AnswerClaim, ContextItem, QueryTrace


def _segment(segment_id: str, location: str, text: str = "placeholder text") -> SourceSegment:
    return SourceSegment(
        segment_id=segment_id,
        source_document_id="doc-1",
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


# Fixture 1: explicit cross-reference target present and packed.
def test_01_target_present_and_packed() -> None:
    claim = AnswerClaim(
        claim_id="c1", text="Widgets qualify for Exemption D, defined in Section 4 of the Handbook."
    )
    segment = _segment("seg-4", "Handbook > Section 4")
    corpus_index = _corpus_index(segment)
    trace = _trace(packed_context_items=[_item("seg-4")])

    markers = detect_cross_reference_markers(claim, corpus_index, trace)
    section_marker = next(m for m in markers if m.marker_text == "Section 4")
    assert section_marker.target_state == CrossReferenceTargetState.PACKED
    assert cross_reference_warning(section_marker) is None


# Fixture 2: explicit cross-reference target present but not retrieved.
def test_02_target_present_but_not_retrieved() -> None:
    claim = AnswerClaim(claim_id="c1", text="See Section 4 for the full exemption list.")
    segment = _segment("seg-4", "Handbook > Section 4")
    corpus_index = _corpus_index(segment)
    trace = _trace(
        retrieval_candidates=[], selected_context_items=[], packed_context_items=[], omitted_context_items=[]
    )

    markers = detect_cross_reference_markers(claim, corpus_index, trace)
    section_marker = next(m for m in markers if m.marker_text == "Section 4")
    assert section_marker.target_state == CrossReferenceTargetState.IN_CORPUS
    warning = cross_reference_warning(section_marker)
    assert warning == (
        "An explicit reference may require additional source context. The referenced "
        "target was present in the corpus but not retrieved for this query. Human "
        "review is recommended."
    )
    for prohibited in ("unsupported", "caused an error", "resolves the claim"):
        assert prohibited not in warning


# Fixture 3: target retrieved but omitted by budget.
def test_03_target_retrieved_but_omitted_by_budget() -> None:
    claim = AnswerClaim(claim_id="c1", text="See Section 4 for the full exemption list.")
    segment = _segment("seg-4", "Handbook > Section 4")
    corpus_index = _corpus_index(segment)
    trace = _trace(
        retrieval_candidates=[_item("seg-4")],
        selected_context_items=[_item("seg-4")],
        packed_context_items=[],
        omitted_context_items=[_item("seg-4")],
    )

    markers = detect_cross_reference_markers(claim, corpus_index, trace)
    section_marker = next(m for m in markers if m.marker_text == "Section 4")
    assert section_marker.target_state == CrossReferenceTargetState.OMITTED
    assert "omitted from the packed context by the token budget" in cross_reference_warning(section_marker)


# Fixture 4: target needed for interpretation but unresolved (no segment matches at all).
def test_04_target_needed_but_unresolved() -> None:
    claim = AnswerClaim(claim_id="c1", text="Exemption D applies as described in Appendix Z of the Handbook.")
    corpus_index = _corpus_index(_segment("seg-1", "Handbook > Section 1"))
    trace = _trace(packed_context_items=[_item("seg-1")])

    markers = detect_cross_reference_markers(claim, corpus_index, trace)
    appendix_marker = next(m for m in markers if m.marker_text == "Appendix Z")
    assert appendix_marker.target_state == CrossReferenceTargetState.UNKNOWN
    assert appendix_marker.target_segment_ids == []
    warning = cross_reference_warning(appendix_marker)
    assert warning is not None
    assert "Human review is recommended" in warning


def test_no_marker_when_claim_has_no_cross_reference() -> None:
    claim = AnswerClaim(claim_id="c1", text="Widgets must be inspected annually.")
    corpus_index = _corpus_index(_segment("seg-1", "Handbook > Section 1"))
    trace = _trace(packed_context_items=[])
    assert detect_cross_reference_markers(claim, corpus_index, trace) == []


def test_selected_state_between_retrieved_and_packed() -> None:
    claim = AnswerClaim(claim_id="c1", text="See Section 4 for the full exemption list.")
    segment = _segment("seg-4", "Handbook > Section 4")
    corpus_index = _corpus_index(segment)
    trace = _trace(
        retrieval_candidates=[_item("seg-4")],
        selected_context_items=[_item("seg-4")],
        packed_context_items=[],
        omitted_context_items=[],
    )
    markers = detect_cross_reference_markers(claim, corpus_index, trace)
    section_marker = next(m for m in markers if m.marker_text == "Section 4")
    assert section_marker.target_state == CrossReferenceTargetState.SELECTED


# Test category: no factual-causality claim from the cross-reference warning.
def test_warning_never_asserts_factual_causality_or_resolution() -> None:
    claim = AnswerClaim(claim_id="c1", text="See Section 4 for the full exemption list.")
    corpus_index = _corpus_index(_segment("seg-4", "Handbook > Section 4"))
    for trace, expected_state in (
        (
            _trace(
                retrieval_candidates=[],
                selected_context_items=[],
                packed_context_items=[],
                omitted_context_items=[],
            ),
            CrossReferenceTargetState.IN_CORPUS,
        ),
        (
            _trace(
                retrieval_candidates=[_item("seg-4")],
                selected_context_items=[],
                packed_context_items=[],
                omitted_context_items=[],
            ),
            CrossReferenceTargetState.RETRIEVED,
        ),
    ):
        markers = detect_cross_reference_markers(claim, corpus_index, trace)
        marker = next(m for m in markers if m.marker_text == "Section 4")
        assert marker.target_state == expected_state
        warning = cross_reference_warning(marker)
        assert warning is not None
        for prohibited in (
            "The answer is unsupported.",
            "The reference caused an error.",
            "The target resolves the claim.",
        ):
            assert prohibited not in warning
        assert warning.startswith("An explicit reference may require additional source context.")
        assert warning.endswith("Human review is recommended.")


# Test category: deterministic diagnostic output.
def test_deterministic_marker_detection() -> None:
    claim = AnswerClaim(claim_id="c1", text="See Section 4 and Exemption D for details.")
    corpus_index = _corpus_index(_segment("seg-4", "Handbook > Section 4"))
    trace = _trace(packed_context_items=[_item("seg-4")])

    first = detect_cross_reference_markers(claim, corpus_index, trace)
    second = detect_cross_reference_markers(claim, corpus_index, trace)
    assert [(m.marker_text, m.target_state) for m in first] == [(m.marker_text, m.target_state) for m in second]
