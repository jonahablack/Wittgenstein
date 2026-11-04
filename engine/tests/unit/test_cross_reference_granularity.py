"""Cross-reference paragraph/point-level granularity and exactness --
docs/cross-reference-granularity-resolution-plan.md. Covers the milestone's 20
required test categories (numbering preserved in each test's docstring/name for
traceability). Categories 13/14/15/16/17/18/19/20 confirm the pre-existing coarse
`CrossReferenceTargetState` layer, non-legal cross-references, claim-linking/
evidence-set behavior, and the preserved pilot artifacts are all unaffected.
"""

from __future__ import annotations

import subprocess
from datetime import UTC, datetime
from pathlib import Path

from wittgenstein.core.enums import (
    CrossReferenceResolutionGranularity,
    CrossReferenceTargetState,
    ExactTargetAvailability,
    SegmentType,
    TraceStatus,
)
from wittgenstein.evidence_set_diagnostics.runner import run_diagnostic_case
from wittgenstein.ingestion.corpus_index import CorpusIndex
from wittgenstein.review.cross_reference_diagnostics import (
    cross_reference_warning,
    detect_cross_reference_markers,
    exactness_explanation,
)
from wittgenstein.review.imported_answer import import_answer
from wittgenstein.schemas.proposition import SourceSegment
from wittgenstein.schemas.smoke_test import SmokeTestCaseFile
from wittgenstein.schemas.trace import AnswerClaim, ContextItem, QueryTrace
from wittgenstein.smoke_test.corpus_registry import resolve_corpus
from wittgenstein.smoke_test.manifest_registry import load_manifests

_REPO_ROOT = Path(__file__).resolve().parents[2]


def _segment(
    segment_id: str,
    location: str,
    *,
    source_document_id: str = "doc-1",
    text: str = "placeholder text",
    legal_article_number: str | None = None,
    legal_paragraph_number: str | None = None,
    legal_point_identifier: str | None = None,
    legal_annex_identifier: str | None = None,
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
        legal_article_number=legal_article_number,
        legal_paragraph_number=legal_paragraph_number,
        legal_point_identifier=legal_point_identifier,
        legal_annex_identifier=legal_annex_identifier,
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


# 1. Exact Article target resolution (bare citation -- no sub-target requested).
def test_01_exact_article_target_resolution() -> None:
    seg = _segment("a49-seg1", "Paragraph 1", source_document_id="article-49-registration")
    markers = _markers("See Article 49 for details.", seg, trace=_trace(packed_context_items=[_item("a49-seg1")]))
    target = markers[0].targets[0]
    assert target.resolution_granularity == CrossReferenceResolutionGranularity.ARTICLE
    assert target.exact_target_status == ExactTargetAvailability.EXACT_TARGET_PRESENT


# 2. Exact paragraph resolution.
def test_02_exact_paragraph_resolution() -> None:
    seg1 = _segment(
        "a49-seg5", "List item 1", source_document_id="article-49-registration", legal_paragraph_number="1"
    )
    seg2 = _segment(
        "a49-seg6", "List item 2", source_document_id="article-49-registration", legal_paragraph_number="2"
    )
    markers = _markers(
        "See Article 49(2) for details.", seg1, seg2, trace=_trace(packed_context_items=[_item("a49-seg6")])
    )
    target = markers[0].targets[0]
    assert target.resolution_granularity == CrossReferenceResolutionGranularity.PARAGRAPH
    assert target.exact_target_status == ExactTargetAvailability.EXACT_TARGET_PRESENT


# 3. Exact point resolution.
def test_03_exact_point_resolution() -> None:
    intro = _segment(
        "a49-seg8", "List item 4", source_document_id="article-49-registration", legal_paragraph_number="4"
    )
    point_a = _segment(
        "a49-seg9",
        "Paragraph 3",
        source_document_id="article-49-registration",
        legal_paragraph_number="4",
        legal_point_identifier="a",
    )
    point_b = _segment(
        "a49-seg11",
        "Paragraph 4",
        source_document_id="article-49-registration",
        legal_paragraph_number="4",
        legal_point_identifier="b",
    )
    markers = _markers(
        "See Article 49(4), point (b) for details.",
        intro,
        point_a,
        point_b,
        trace=_trace(packed_context_items=[_item("a49-seg11")]),
    )
    target = markers[0].targets[0]
    assert target.resolution_granularity == CrossReferenceResolutionGranularity.POINT
    assert target.exact_target_status == ExactTargetAvailability.EXACT_TARGET_PRESENT


# 4. Exact annex resolution.
def test_04_exact_annex_resolution() -> None:
    seg = _segment(
        "annex3-seg1",
        "Paragraph 1",
        source_document_id="annex-iii-scope",
        legal_annex_identifier="III",
    )
    markers = _markers(
        "See Annex III for details.", seg, trace=_trace(packed_context_items=[_item("annex3-seg1")])
    )
    target = markers[0].targets[0]
    assert target.resolution_granularity == CrossReferenceResolutionGranularity.ANNEX
    assert target.exact_target_status == ExactTargetAvailability.EXACT_TARGET_PRESENT


# 5. Parent article present with paragraph target unavailable.
def test_05_parent_article_present_paragraph_unavailable() -> None:
    # No legal_paragraph_number anywhere in this document -- the parser found no
    # internal numbered-paragraph structure at all.
    seg = _segment("a49-seg1", "Paragraph 1", source_document_id="article-49-registration")
    markers = _markers(
        "See Article 49(2) for details.", seg, trace=_trace(packed_context_items=[_item("a49-seg1")])
    )
    target = markers[0].targets[0]
    assert target.resolution_granularity == CrossReferenceResolutionGranularity.ARTICLE
    assert target.exact_target_status == ExactTargetAvailability.PARENT_ONLY_PRESENT


# 6. Sibling paragraph present but cited paragraph absent.
def test_06_sibling_paragraph_present_cited_paragraph_absent() -> None:
    seg1 = _segment(
        "a49-seg5", "List item 1", source_document_id="article-49-registration", legal_paragraph_number="1"
    )
    seg2 = _segment(
        "a49-seg6", "List item 2", source_document_id="article-49-registration", legal_paragraph_number="2"
    )
    markers = _markers(
        "See Article 49(2) for details.", seg1, seg2, trace=_trace(packed_context_items=[_item("a49-seg5")])
    )
    target = markers[0].targets[0]
    assert target.target_state == CrossReferenceTargetState.PACKED
    assert target.resolution_granularity == CrossReferenceResolutionGranularity.PARAGRAPH
    assert target.exact_target_status == ExactTargetAvailability.SIBLING_ONLY_PRESENT


# 7. Target in corpus but not retrieved.
def test_07_target_in_corpus_but_not_retrieved() -> None:
    seg2 = _segment(
        "a49-seg6", "List item 2", source_document_id="article-49-registration", legal_paragraph_number="2"
    )
    trace = _trace(
        retrieval_candidates=[], selected_context_items=[], packed_context_items=[], omitted_context_items=[]
    )
    markers = _markers("See Article 49(2) for details.", seg2, trace=trace)
    target = markers[0].targets[0]
    assert target.target_state == CrossReferenceTargetState.IN_CORPUS
    assert target.resolution_granularity == CrossReferenceResolutionGranularity.PARAGRAPH
    assert target.exact_target_status == ExactTargetAvailability.TARGET_MISSING


# 8. Target retrieved but not selected.
def test_08_target_retrieved_but_not_selected() -> None:
    seg2 = _segment(
        "a49-seg6", "List item 2", source_document_id="article-49-registration", legal_paragraph_number="2"
    )
    trace = _trace(
        retrieval_candidates=[_item("a49-seg6")],
        selected_context_items=[],
        packed_context_items=[],
        omitted_context_items=[],
    )
    markers = _markers("See Article 49(2) for details.", seg2, trace=trace)
    target = markers[0].targets[0]
    assert target.target_state == CrossReferenceTargetState.RETRIEVED
    assert target.exact_target_status == ExactTargetAvailability.EXACT_TARGET_PRESENT


# 9. Target selected but not packed.
def test_09_target_selected_but_not_packed() -> None:
    seg2 = _segment(
        "a49-seg6", "List item 2", source_document_id="article-49-registration", legal_paragraph_number="2"
    )
    trace = _trace(
        retrieval_candidates=[_item("a49-seg6")],
        selected_context_items=[_item("a49-seg6")],
        packed_context_items=[],
        omitted_context_items=[],
    )
    markers = _markers("See Article 49(2) for details.", seg2, trace=trace)
    target = markers[0].targets[0]
    assert target.target_state == CrossReferenceTargetState.SELECTED
    assert target.exact_target_status == ExactTargetAvailability.EXACT_TARGET_PRESENT


# 10. Target packed exactly.
def test_10_target_packed_exactly() -> None:
    seg2 = _segment(
        "a49-seg6", "List item 2", source_document_id="article-49-registration", legal_paragraph_number="2"
    )
    trace = _trace(
        retrieval_candidates=[_item("a49-seg6")],
        selected_context_items=[_item("a49-seg6")],
        packed_context_items=[_item("a49-seg6")],
        omitted_context_items=[],
    )
    markers = _markers("See Article 49(2) for details.", seg2, trace=trace)
    target = markers[0].targets[0]
    assert target.target_state == CrossReferenceTargetState.PACKED
    assert target.resolution_granularity == CrossReferenceResolutionGranularity.PARAGRAPH
    assert target.exact_target_status == ExactTargetAvailability.EXACT_TARGET_PRESENT
    explanation = exactness_explanation(target, markers[0].marker_text)
    assert explanation == (
        "The cited target, Article 49(2), is present in the packed context. "
        "Human review is recommended when the precise cited provision matters."
    )


# 11. Ambiguous structural target produces target_unknown.
def test_11_ambiguous_structural_target_produces_target_unknown() -> None:
    seg_a = _segment(
        "dup-a", "Paragraph 1", source_document_id="article-49-first-copy", legal_paragraph_number="2"
    )
    seg_b = _segment(
        "dup-b", "Paragraph 1", source_document_id="article-49-second-copy", legal_paragraph_number="2"
    )
    markers = _markers("See Article 49(2) for details.", seg_a, seg_b)
    target = markers[0].targets[0]
    assert target.target_segment_ids == []
    assert target.resolution_granularity == CrossReferenceResolutionGranularity.UNKNOWN
    assert target.exact_target_status == ExactTargetAvailability.TARGET_UNKNOWN


# 12. Whole-article file without internal parsed boundaries never yields
#     exact_target_present for a paragraph reference, even with full document coverage.
def test_12_whole_article_file_never_yields_exact_target_present_for_paragraph() -> None:
    seg1 = _segment("a49-seg1", "Paragraph 1", source_document_id="article-49-registration", text="Article 49")
    seg2 = _segment("a49-seg2", "Paragraph 2", source_document_id="article-49-registration", text="Registration")
    trace = _trace(packed_context_items=[_item("a49-seg1"), _item("a49-seg2")])
    markers = _markers("See Article 49(2) for details.", seg1, seg2, trace=trace)
    target = markers[0].targets[0]
    assert target.exact_target_status != ExactTargetAvailability.EXACT_TARGET_PRESENT
    assert target.exact_target_status == ExactTargetAvailability.PARENT_ONLY_PRESENT
    assert target.resolution_granularity == CrossReferenceResolutionGranularity.ARTICLE


# 13. Existing article-level (coarse) resolution remains backward compatible.
def test_13_existing_coarse_resolution_remains_backward_compatible() -> None:
    seg = _segment("a49-seg1", "Paragraph 1", source_document_id="article-49-registration")
    markers = _markers("See Article 49 for details.", seg, trace=_trace(packed_context_items=[_item("a49-seg1")]))
    assert markers[0].target_state == CrossReferenceTargetState.PACKED
    assert markers[0].targets[0].target_segment_ids == ["a49-seg1"]
    assert markers[0].targets[0].target_identifier == "article:49"
    assert cross_reference_warning(markers[0]) is None  # unchanged: no warning when packed


# 14. Existing non-legal cross-references remain unchanged (no ReferenceTarget/
#     granularity/exactness fields are fabricated for the old generic-cue path).
def test_14_existing_non_legal_cross_references_unchanged() -> None:
    seg = _segment("widget-seg1", "Handbook > Section 4", source_document_id="certification-handbook")
    markers = _markers(
        "See Section 4 for the full requirements.",
        seg,
        trace=_trace(packed_context_items=[_item("widget-seg1")]),
    )
    assert len(markers) == 1
    assert markers[0].marker_text == "Section 4"
    assert markers[0].target_state == CrossReferenceTargetState.PACKED
    assert markers[0].targets == []  # old path never populates structured targets
    assert cross_reference_warning(markers[0]) is None


# 15. No automatic retrieval, selection, packing, or closure.
def test_15_no_automatic_retrieval_selection_packing_or_closure() -> None:
    seg2 = _segment(
        "a49-seg6", "List item 2", source_document_id="article-49-registration", legal_paragraph_number="2"
    )
    trace = _trace(packed_context_items=[])
    before_packed = list(trace.packed_context_items or [])
    markers = _markers("See Article 49(2) for details.", seg2, trace=trace)
    exactness_explanation(markers[0].targets[0], markers[0].marker_text)
    assert list(trace.packed_context_items or []) == before_packed


# 16. No legal/factual causal language in any exactness-explanation template.
def test_16_no_legal_or_causal_claim_in_exactness_explanations() -> None:
    seg2 = _segment(
        "a49-seg6", "List item 2", source_document_id="article-49-registration", legal_paragraph_number="2"
    )
    fixtures = [
        ("Article 49(2) is exact.", [seg2], _trace(packed_context_items=[_item("a49-seg6")])),
        (
            "Article 49(2) is sibling.",
            [
                _segment(
                    "a49-seg5",
                    "List item 1",
                    source_document_id="article-49-registration",
                    legal_paragraph_number="1",
                ),
                seg2,
            ],
            _trace(packed_context_items=[_item("a49-seg5")]),
        ),
        (
            "Article 49(2) is parent-only.",
            [_segment("a49-seg1", "Paragraph 1", source_document_id="article-49-registration")],
            _trace(packed_context_items=[_item("a49-seg1")]),
        ),
        (
            "Article 49(2) is missing.",
            [seg2],
            _trace(
                retrieval_candidates=[],
                selected_context_items=[],
                packed_context_items=[],
                omitted_context_items=[],
            ),
        ),
        ("Article 49(2) is unknown.", [], _trace()),
    ]
    prohibited = (
        "the answer is supported",
        "the cited provision governs",
        "the target resolves the claim",
        "the answer is legally correct",
        "the system has verified the reference",
    )
    for text, segments, trace in fixtures:
        markers = _markers(text, *segments, trace=trace)
        explanation = exactness_explanation(markers[0].targets[0], markers[0].marker_text)
        assert explanation is not None
        assert explanation.endswith("Human review is recommended when the precise cited provision matters.")
        lowered = explanation.lower()
        for phrase in prohibited:
            assert phrase not in lowered


# 17. Baseline and prior post-fix pilot outputs are unchanged by this plan.
def test_17_baseline_and_prior_post_fix_outputs_unchanged() -> None:
    base = _REPO_ROOT / "data/examples/evidence_set_diagnostics/local_corpora/eu-ai-act-2024"
    baseline_case3 = (
        base
        / "output-baseline-before-article-xref"
        / "euaia-003-explicit-cross-reference-registration.diagnostic.json"
    )
    post_fix_case3 = (
        base / "output-after-article-xref" / "euaia-003-explicit-cross-reference-registration.diagnostic.json"
    )
    if not baseline_case3.exists() or not post_fix_case3.exists():
        return  # local-only artifacts; nothing to check in an environment without them
    import json

    baseline_data = json.loads(baseline_case3.read_text())
    post_fix_data = json.loads(post_fix_case3.read_text())
    # The post-fix run predates this plan -- its marker dicts must not carry the new
    # granularity/exactness keys (those are only ever added by a run made after this
    # plan's code landed, written to a distinct third output directory, never here).
    for markers in post_fix_data.get("cross_reference_markers", {}).values():
        for marker in markers:
            for target in marker.get("targets", []):
                assert "resolution_granularity" not in target
                assert "exact_target_status" not in target
    assert baseline_data.get("cross_reference_markers", {}) == {}


# 18. Third-output path is gitignored.
def test_18_third_output_path_is_gitignored() -> None:
    third_output_dir = (
        "data/examples/evidence_set_diagnostics/local_corpora/eu-ai-act-2024/"
        "output-after-granularity-resolution/placeholder.diagnostic.json"
    )
    result = subprocess.run(
        ["git", "check-ignore", "-q", third_output_dir], cwd=_REPO_ROOT, capture_output=True, text=True
    )
    assert result.returncode == 0


# 19. Claim-linking/evidence-set outputs unchanged under the same inputs.
def test_19_claim_linking_and_evidence_set_outputs_unchanged() -> None:
    cases_path = _REPO_ROOT / "data/examples/evidence_set_diagnostics/cases.example.json"
    manifests_path = _REPO_ROOT / "data/examples/evidence_set_diagnostics/manifests.json"
    case_file = SmokeTestCaseFile.model_validate(__import__("json").loads(cases_path.read_text()))
    manifests = load_manifests(manifests_path)
    case = case_file.cases[0]

    # Path A: the diagnostic runner, which calls detect_cross_reference_markers
    # (and, through it, the new granularity/exactness computation) after import_answer.
    diagnostic_result = run_diagnostic_case(case, manifests)

    # Path B: import_answer called directly, bypassing cross-reference detection
    # entirely -- if the two paths' claim-linking/evidence-set output differ, the new
    # detection code must have had a side effect on the imported-answer result, which
    # it must never have.
    manifest = manifests[case.pipeline_manifest_id]
    corpus_text = resolve_corpus(case.corpus)
    direct_result = import_answer(
        case.query, case.answer, corpus=corpus_text, corpus_id=case.corpus.corpus_id, manifest=manifest
    )

    def _stable(dumped: dict) -> dict:
        # comparison_id/evidence_set_id are freshly random per call (uuid4) even for
        # otherwise-identical input -- excluded here as the one legitimately-varying
        # field, exactly like the existing "deterministic diagnostics" test pattern
        # elsewhere in this suite (test_20's own docstring note).
        return {k: v for k, v in dumped.items() if k not in ("comparison_id", "evidence_set_id")}

    assert [
        _stable(c.model_dump(mode="json")) for c in diagnostic_result.imported_answer.claim_evidence_comparisons
    ] == [_stable(c.model_dump(mode="json")) for c in direct_result.claim_evidence_comparisons]
    assert [_stable(e.model_dump(mode="json")) for e in diagnostic_result.imported_answer.evidence_sets] == [
        _stable(e.model_dump(mode="json")) for e in direct_result.evidence_sets
    ]


# 20. Deterministic results.
def test_20_deterministic_granularity_and_exactness_output() -> None:
    seg1 = _segment(
        "a49-seg5", "List item 1", source_document_id="article-49-registration", legal_paragraph_number="1"
    )
    seg2 = _segment(
        "a49-seg6", "List item 2", source_document_id="article-49-registration", legal_paragraph_number="2"
    )
    text = "Articles 6, 13 and 50 apply, see also Article 49(2) and Annex III."
    trace = _trace(packed_context_items=[_item("a49-seg6")])

    def _snapshot():
        markers = _markers(text, seg1, seg2, trace=trace)
        return [
            (
                m.marker_text,
                m.target_identifier,
                [
                    (t.target_identifier, t.resolution_granularity.value, t.exact_target_status.value)
                    for t in m.targets
                ],
                [exactness_explanation(t, m.marker_text) for t in m.targets],
            )
            for m in markers
        ]

    assert _snapshot() == _snapshot()
