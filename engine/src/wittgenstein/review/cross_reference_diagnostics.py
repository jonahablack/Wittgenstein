"""Cross-reference target-state measurement -- docs/cross-reference-diagnostic-spec.md,
docs/eu-ai-act-article-cross-reference-fix-plan.md. Detection and location-text/
document-id matching only; never implements closure (pulling a referenced target into
an evidence set), never resolves a reference semantically, and never changes any
`ClaimSupportCandidateStatus`/`EvidenceSet.relationship_status`. Used by the real-corpus
diagnostic harness only.

Two independent detection passes, unioned:
- the pre-existing, unmodified `ComparisonFieldName.CROSS_REFERENCE` cue field
  (Section/Table/Figure/Exemption/Appendix/Clause -- `proposition/annotations.py`,
  untouched by this module);
- a dedicated legal-citation regex/parser (Article/Articles/Annex forms) added here
  only -- kept out of the shared extractor so this fix cannot change claim-linking's
  field-comparison behavior on any corpus (docs/eu-ai-act-article-cross-reference-fix-plan.md,
  "Design: isolated to the diagnostic layer").
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from wittgenstein.core.enums import (
    ComparisonFieldName,
    CrossReferenceResolutionGranularity,
    CrossReferenceTargetState,
    ExactTargetAvailability,
    ExtractionStatus,
)
from wittgenstein.ingestion.corpus_index import CorpusIndex
from wittgenstein.review.field_extraction import extract_fields
from wittgenstein.schemas.trace import AnswerClaim, QueryTrace

_STATE_PHRASES = {
    CrossReferenceTargetState.IN_CORPUS: "present in the corpus but not retrieved for this query",
    CrossReferenceTargetState.RETRIEVED: "retrieved but not included in the packed context",
    CrossReferenceTargetState.SELECTED: "selected but not included in the packed context",
    CrossReferenceTargetState.PACKED: "packed",
    CrossReferenceTargetState.OMITTED: "retrieved but omitted from the packed context by the token budget",
    CrossReferenceTargetState.UNKNOWN: "in an unknown location relative to the retrieval/packing pipeline",
}

_WARNING_TEMPLATE = (
    "An explicit reference may require additional source context. The referenced "
    "target was {state}. Human review is recommended."
)

#: Bounded, non-adjudicative reviewer-facing phrases per pipeline stage -- used only by
#: `exactness_explanation`, never by `cross_reference_warning` (unchanged). Mirrors
#: `_STATE_PHRASES`'s tone but describes *where* the surfaced content sits, since
#: `exactness_explanation` is always about content that already appeared somewhere in
#: the pipeline (a bare "nothing surfaced" case is handled by TARGET_MISSING's fixed
#: text below, independent of stage).
_STAGE_LOCATION_PHRASES = {
    CrossReferenceTargetState.PACKED: "packed context",
    CrossReferenceTargetState.OMITTED: "context considered for packing but omitted by the token budget",
    CrossReferenceTargetState.SELECTED: "selected context",
    CrossReferenceTargetState.RETRIEVED: "retrieved candidates",
    CrossReferenceTargetState.IN_CORPUS: "local corpus (not retrieved for this query)",
}

_HUMAN_REVIEW_SUFFIX = " Human review is recommended when the precise cited provision matters."

#: Fixed, bounded per-exactness templates (docs/cross-reference-granularity-resolution-plan.md
#: §6/reviewer-facing language). Never an adjudicative claim -- deliberately does not
#: say the answer is supported, that the provision governs, that the reference is
#: resolved, or that the reference has been verified as correct.
_EXACT_TARGET_PRESENT_TEMPLATE = "The cited target, {marker_text}, is present in the {stage_phrase}."
_PARENT_ONLY_PRESENT_TEMPLATE = (
    "The parent article is present in the {stage_phrase}, but the cited paragraph was not "
    "independently identified."
)
_SIBLING_ONLY_PRESENT_TEMPLATE = (
    "A different paragraph of the cited article is present in the {stage_phrase}; the cited "
    "paragraph was not identified."
)
_BROADER_CONTEXT_PRESENT_TEMPLATE = (
    "Only surrounding material from the cited article, not the cited paragraph itself, is "
    "present in the {stage_phrase}."
)
_TARGET_MISSING_TEXT = (
    "The cited target is available in the local corpus but was not present in the retrieved or packed evidence."
)
_TARGET_UNKNOWN_TEXT = (
    "The system could not determine whether the cited target is present because paragraph-level "
    "structure was unavailable."
)

#: A single article citation, with optional paragraph and point --
#: "Article 49", "Article 6(4)", "Article 6(4), point (a)". Deliberately does not
#: match "Articles" (plural handled separately, _ARTICLE_LIST_RE below) -- "Article"
#: followed immediately by "s" fails `\s` and never matches here.
#: The trailing boundary is a negative lookahead, not `\b`, deliberately: `\b` fails
#: right after a closing `)` followed by a space (both are non-word characters, so no
#: word-boundary transition exists there), which would otherwise force the engine to
#: backtrack the optional paragraph/point groups away and silently drop them --
#: exactly the "Article 6(4)" -> "Article 6" bug this pattern was rewritten to avoid.
_ARTICLE_SINGLE_RE = re.compile(
    r"\bArticle\s+(\d+)(?:\((\d+)\))?(?:,\s*point\s+\(([a-z])\))?(?!\w)", re.IGNORECASE
)
#: A list or range of bare article numbers -- "Articles 6 and 49",
#: "Articles 6, 13 and 50", "Articles 6 to 13", "Articles 6-13" / "Articles 6–13".
#: Per docs/eu-ai-act-article-cross-reference-fix-plan.md, paragraph/point refinement
#: on individual list members is out of scope (not in the required examples).
_ARTICLE_LIST_RE = re.compile(r"\bArticles\s+(\d+(?:\s*(?:,|and|to|–|-)\s*\d+)+)\b", re.IGNORECASE)
#: A simple annex reference -- "Annex III". Roman-numeral only, matching this
#: codebase's existing Annex-numbering convention elsewhere in the corpus.
_ANNEX_RE = re.compile(r"\bAnnex\s+([IVXLCDM]+)\b", re.IGNORECASE)
#: One combined pattern used only to *find* citation spans in claim text -- each match
#: is then re-parsed against the specific patterns above to build its structured
#: ReferenceTarget(s). Order matters: try the plural/list form before the singular
#: form so "Articles 6 and 49" is captured whole rather than only its first number
#: (which the singular pattern's `\bArticle\s+\d+` would never match here anyway,
#: since "Articles" has no `\s` immediately after "Article" -- listed first regardless,
#: for clarity).
_LEGAL_CITATION_RE = re.compile(
    r"\bArticles\s+\d+(?:\s*(?:,|and|to|–|-)\s*\d+)+\b"
    r"|\bArticle\s+\d+(?:\(\d+\))?(?:,\s*point\s+\([a-z]\))?(?!\w)"
    r"|\bAnnex\s+[IVXLCDM]+\b",
    re.IGNORECASE,
)
#: Word-boundary-aware split for a number list/range's connectors.
_RANGE_CONNECTOR_RE = re.compile(r"\bto\b|–|-", re.IGNORECASE)


@dataclass
class ReferenceTarget:
    """One individual cited article/annex within a `CrossReferenceMarker` -- a
    plural/range marker ("Articles 6 to 13") expands into multiple `ReferenceTarget`s,
    never silently reduced to the first.
    """

    target_identifier: str
    article_number: str | None
    paragraph_number: str | None
    subdivision_type: str | None
    subdivision_identifier: str | None
    target_segment_ids: list[str]
    target_state: CrossReferenceTargetState
    #: The finest granularity the corpus's parsed structure could actually resolve for
    #: this citation, capped at what was cited -- docs/cross-reference-granularity-resolution-plan.md
    #: §5. Never claims more precision than an explicit source-structure marker
    #: confirmed.
    resolution_granularity: CrossReferenceResolutionGranularity = CrossReferenceResolutionGranularity.UNKNOWN
    #: Whether the *specific* cited paragraph/point (not just "something" from the
    #: cited article) was found among the surfaced pipeline stages. Orthogonal to
    #: `target_state` -- see the plan doc §2.
    exact_target_status: ExactTargetAvailability = ExactTargetAvailability.TARGET_UNKNOWN


@dataclass
class CrossReferenceMarker:
    marker_text: str
    source_span: tuple[int, int] | None
    target_segment_ids: list[str]
    target_state: CrossReferenceTargetState
    reference_type: str = "unknown"
    range_start: str | None = None
    range_end: str | None = None
    #: Populated only when this marker has exactly one target (unambiguous) -- `None`
    #: for a plural/range marker; use `targets` for the full breakdown either way.
    target_identifier: str | None = None
    targets: list[ReferenceTarget] = field(default_factory=list)
    extraction_method: str = "regex"
    extraction_confidence: float | None = None


def _target_segment_ids(marker_text: str, corpus_index: CorpusIndex) -> list[str]:
    needle = marker_text.strip().lower()
    return [
        segment.segment_id
        for segment in corpus_index.segments.values()
        if segment.location and needle in segment.location.lower()
    ]


def _document_id_segment_ids(kind: str, number: str, corpus_index: CorpusIndex) -> list[str]:
    """Structural (not semantic) match: a corpus that names one document per article/
    annex -- exactly this pilot's `article-<N>-<slug>.txt` convention -- resolves at
    the whole-document level via `source_document_id`'s own leading tokens. An
    ambiguous match (more than one distinct document qualifies) is deliberately
    treated as no match, per docs/eu-ai-act-article-cross-reference-fix-plan.md
    ("Uncertainty behavior").
    """

    target_key = (kind.lower(), number.lower())
    matching_document_ids = {
        segment.source_document_id
        for segment in corpus_index.segments.values()
        if tuple(segment.source_document_id.lower().split("-", 2)[:2]) == target_key
    }
    if len(matching_document_ids) != 1:
        return []
    (document_id,) = matching_document_ids
    return [
        segment.segment_id
        for segment in corpus_index.segments.values()
        if segment.source_document_id == document_id
    ]


def _legal_article_number_segment_ids(number: str, corpus_index: CorpusIndex) -> list[str]:
    """Structural (not semantic) match via each segment's own parsed
    `legal_article_number` (docs/cross-reference-granularity-resolution-plan.md §4) --
    additive to `_document_id_segment_ids`. Unlike that filename-based match, this
    resolves correctly even when a single source document contains more than one
    article (e.g. a controlled fixture corpus deliberately kept to a small number of
    files), since it matches the parser's own explicit per-segment marker rather than
    the filename, and it returns only the cited article's own segments rather than the
    whole containing document. Ambiguity-safe the same way as
    `_document_id_segment_ids`: if segments carrying this article number span more
    than one distinct document, treated as no match rather than picking one.
    """

    matches = [
        segment
        for segment in corpus_index.segments.values()
        if segment.legal_article_number is not None and segment.legal_article_number.lower() == number.lower()
    ]
    if len({segment.source_document_id for segment in matches}) != 1:
        return []
    return [segment.segment_id for segment in matches]


def _resolve_target_state(target_segment_ids: list[str], trace: QueryTrace) -> CrossReferenceTargetState:
    if not target_segment_ids:
        # No segment's location/document-id matched the target at all -- the brief's
        # six-state vocabulary does not distinguish "target doesn't exist in this
        # corpus" from "cannot determine," and both recommend the same human review
        # either way.
        return CrossReferenceTargetState.UNKNOWN

    stage_lists = (
        trace.packed_context_items,
        trace.omitted_context_items,
        trace.selected_context_items,
        trace.retrieval_candidates,
    )
    if all(stage is None for stage in stage_lists):
        return CrossReferenceTargetState.UNKNOWN

    target_ids = set(target_segment_ids)
    for stage, state in (
        (trace.packed_context_items, CrossReferenceTargetState.PACKED),
        (trace.omitted_context_items, CrossReferenceTargetState.OMITTED),
        (trace.selected_context_items, CrossReferenceTargetState.SELECTED),
        (trace.retrieval_candidates, CrossReferenceTargetState.RETRIEVED),
    ):
        if stage is not None and any(item.segment_id in target_ids for item in stage):
            return state

    # The target exists in the corpus and the trace is instrumented, but this specific
    # target never appears in any stage list -- it was never retrieved at all.
    return CrossReferenceTargetState.IN_CORPUS


def _aggregate_state(states: list[CrossReferenceTargetState]) -> CrossReferenceTargetState:
    """The "best" state across a multi-target marker's individual targets, using the
    same precedence `_resolve_target_state` already applies to one target -- a marker
    is only as resolved as its *best*-resolved member, so a reviewer scanning the
    marker-level summary is never shown a falsely pessimistic aggregate.
    """

    precedence = [
        CrossReferenceTargetState.PACKED,
        CrossReferenceTargetState.OMITTED,
        CrossReferenceTargetState.SELECTED,
        CrossReferenceTargetState.RETRIEVED,
        CrossReferenceTargetState.IN_CORPUS,
        CrossReferenceTargetState.UNKNOWN,
    ]
    for state in precedence:
        if state in states:
            return state
    return CrossReferenceTargetState.UNKNOWN


def _surfaced_segment_ids(trace: QueryTrace) -> set[str]:
    """Every segment id that appears in *any* instrumented pipeline stage -- retrieved,
    selected, packed, or omitted. Used only to compute exactness (§5 of the plan),
    never to compute the existing coarse `target_state` (that precedence logic is
    unchanged, see `_resolve_target_state`).
    """

    surfaced: set[str] = set()
    for stage in (
        trace.retrieval_candidates,
        trace.selected_context_items,
        trace.packed_context_items,
        trace.omitted_context_items,
    ):
        if stage is not None:
            surfaced.update(item.segment_id for item in stage if item.segment_id is not None)
    return surfaced


def _resolve_granularity_and_exactness(
    *,
    kind: str,
    paragraph_number: str | None,
    subdivision_identifier: str | None,
    segment_ids: list[str],
    corpus_index: CorpusIndex,
    trace: QueryTrace,
) -> tuple[CrossReferenceResolutionGranularity, ExactTargetAvailability]:
    """Deterministic, structural-only decision rules --
    docs/cross-reference-granularity-resolution-plan.md §5. Never infers legal
    necessity/correctness; only restates, at finer granularity, exactly what the
    parser's explicit legal_paragraph_number/legal_point_identifier markers and the
    trace's own stage lists already show.
    """

    if not segment_ids:
        return CrossReferenceResolutionGranularity.UNKNOWN, ExactTargetAvailability.TARGET_UNKNOWN

    surfaced = _surfaced_segment_ids(trace)
    doc_segments = [corpus_index.segments[sid] for sid in segment_ids if sid in corpus_index.segments]
    doc_surfaced_ids = {s.segment_id for s in doc_segments if s.segment_id in surfaced}

    base_granularity = (
        CrossReferenceResolutionGranularity.ANNEX
        if kind == "annex"
        else CrossReferenceResolutionGranularity.ARTICLE
    )

    if paragraph_number is None:
        # A bare article/annex citation -- no sub-target was cited, so there is
        # nothing finer to resolve. Restates the same fact `target_state` already
        # carries, in the new vocabulary, never contradicting it.
        exactness = (
            ExactTargetAvailability.EXACT_TARGET_PRESENT
            if doc_surfaced_ids
            else ExactTargetAvailability.TARGET_MISSING
        )
        return base_granularity, exactness

    paragraph_segments = [s for s in doc_segments if s.legal_paragraph_number is not None]
    if not paragraph_segments:
        # The matched document has no parsed internal paragraph structure at all --
        # cannot claim more precision than the corpus's own explicit markers support.
        exactness = (
            ExactTargetAvailability.PARENT_ONLY_PRESENT
            if doc_surfaced_ids
            else ExactTargetAvailability.TARGET_MISSING
        )
        return CrossReferenceResolutionGranularity.ARTICLE, exactness

    point_segments = [s for s in doc_segments if s.legal_point_identifier is not None]
    resolution_granularity = (
        CrossReferenceResolutionGranularity.POINT
        if subdivision_identifier is not None and point_segments
        else CrossReferenceResolutionGranularity.PARAGRAPH
    )

    def _matches_cited(segment) -> bool:  # noqa: ANN001
        if segment.legal_paragraph_number != paragraph_number:
            return False
        if (
            subdivision_identifier is not None
            and resolution_granularity == CrossReferenceResolutionGranularity.POINT
        ):
            return segment.legal_point_identifier == subdivision_identifier
        return True

    exact_segment_ids = {s.segment_id for s in paragraph_segments if _matches_cited(s)}
    if exact_segment_ids & surfaced:
        return resolution_granularity, ExactTargetAvailability.EXACT_TARGET_PRESENT
    if not doc_surfaced_ids:
        return resolution_granularity, ExactTargetAvailability.TARGET_MISSING
    sibling_surfaced = any(s.segment_id in doc_surfaced_ids for s in paragraph_segments)
    if sibling_surfaced:
        return resolution_granularity, ExactTargetAvailability.SIBLING_ONLY_PRESENT
    return resolution_granularity, ExactTargetAvailability.BROADER_CONTEXT_PRESENT


def _build_target(
    kind: str,
    number: str,
    *,
    paragraph_number: str | None,
    subdivision_type: str | None,
    subdivision_identifier: str | None,
    corpus_index: CorpusIndex,
    trace: QueryTrace,
) -> ReferenceTarget:
    target_identifier = f"{kind}:{number}"
    if paragraph_number:
        target_identifier += f":paragraph:{paragraph_number}"
    if subdivision_type and subdivision_identifier:
        target_identifier += f":{subdivision_type}:{subdivision_identifier}"

    segment_ids = sorted(
        set(_target_segment_ids(f"{kind} {number}", corpus_index))
        | set(_document_id_segment_ids(kind, number, corpus_index))
        | (set(_legal_article_number_segment_ids(number, corpus_index)) if kind == "article" else set())
    )
    resolution_granularity, exact_target_status = _resolve_granularity_and_exactness(
        kind=kind,
        paragraph_number=paragraph_number,
        subdivision_identifier=subdivision_identifier,
        segment_ids=segment_ids,
        corpus_index=corpus_index,
        trace=trace,
    )
    return ReferenceTarget(
        target_identifier=target_identifier,
        article_number=number if kind == "article" else None,
        paragraph_number=paragraph_number,
        subdivision_type=subdivision_type,
        subdivision_identifier=subdivision_identifier,
        target_segment_ids=segment_ids,
        target_state=_resolve_target_state(segment_ids, trace),
        resolution_granularity=resolution_granularity,
        exact_target_status=exact_target_status,
    )


def _expand_article_number_list(number_list_text: str) -> tuple[list[str], str | None, str | None]:
    """ "6, 13 and 50" -> (["6", "13", "50"], None, None). "6 to 13" / "6–13" ->
    (["6", "7", ..., "13"], "6", "13") -- a pure two-number range is expanded in full,
    never silently reduced to its first member. A mixed list containing a range
    connector alongside "," or "and" is treated conservatively as a plain list (each
    number taken as its own target, no expansion) rather than guessing which pair is
    the range.
    """

    numbers = re.findall(r"\d+", number_list_text)
    has_range_connector = bool(_RANGE_CONNECTOR_RE.search(number_list_text))
    has_list_connector = "," in number_list_text or re.search(r"\band\b", number_list_text, re.IGNORECASE)
    if has_range_connector and not has_list_connector and len(numbers) == 2:
        start, end = int(numbers[0]), int(numbers[1])
        if end >= start:
            return [str(n) for n in range(start, end + 1)], numbers[0], numbers[1]
    return numbers, None, None


def _parse_legal_citation(
    match_text: str, span: tuple[int, int], corpus_index: CorpusIndex, trace: QueryTrace
) -> CrossReferenceMarker:
    list_match = _ARTICLE_LIST_RE.fullmatch(match_text)
    if list_match:
        numbers, range_start, range_end = _expand_article_number_list(list_match.group(1))
        targets = [
            _build_target(
                "article",
                number,
                paragraph_number=None,
                subdivision_type=None,
                subdivision_identifier=None,
                corpus_index=corpus_index,
                trace=trace,
            )
            for number in numbers
        ]
        return CrossReferenceMarker(
            marker_text=match_text,
            source_span=span,
            target_segment_ids=sorted({sid for t in targets for sid in t.target_segment_ids}),
            target_state=_aggregate_state([t.target_state for t in targets]),
            reference_type="article",
            range_start=range_start,
            range_end=range_end,
            target_identifier=targets[0].target_identifier if len(targets) == 1 else None,
            targets=targets,
            extraction_confidence=1.0,
        )

    single_match = _ARTICLE_SINGLE_RE.fullmatch(match_text)
    if single_match:
        number, paragraph, point = single_match.groups()
        target = _build_target(
            "article",
            number,
            paragraph_number=paragraph,
            subdivision_type="point" if point else None,
            subdivision_identifier=point,
            corpus_index=corpus_index,
            trace=trace,
        )
        return CrossReferenceMarker(
            marker_text=match_text,
            source_span=span,
            target_segment_ids=list(target.target_segment_ids),
            target_state=target.target_state,
            reference_type="article",
            target_identifier=target.target_identifier,
            targets=[target],
            extraction_confidence=1.0,
        )

    annex_match = _ANNEX_RE.fullmatch(match_text)
    if annex_match:
        (roman_numeral,) = annex_match.groups()
        target = _build_target(
            "annex",
            roman_numeral.upper(),
            paragraph_number=None,
            subdivision_type=None,
            subdivision_identifier=None,
            corpus_index=corpus_index,
            trace=trace,
        )
        return CrossReferenceMarker(
            marker_text=match_text,
            source_span=span,
            target_segment_ids=list(target.target_segment_ids),
            target_state=target.target_state,
            reference_type="annex",
            target_identifier=target.target_identifier,
            targets=[target],
            extraction_confidence=1.0,
        )

    raise AssertionError(
        f"unreachable: {match_text!r} matched _LEGAL_CITATION_RE but no sub-pattern"
    )  # pragma: no cover


def _detect_legal_citation_markers(
    text: str, corpus_index: CorpusIndex, trace: QueryTrace
) -> list[CrossReferenceMarker]:
    return [
        _parse_legal_citation(match.group(0), (match.start(), match.end()), corpus_index, trace)
        for match in _LEGAL_CITATION_RE.finditer(text)
    ]


def _detect_generic_cue_markers(
    claim: AnswerClaim, corpus_index: CorpusIndex, trace: QueryTrace
) -> list[CrossReferenceMarker]:
    """The pre-existing Section/Table/Figure/Exemption/Appendix/Clause path, unchanged
    in behavior -- reuses `ComparisonFieldName.CROSS_REFERENCE` unmodified.
    """

    cross_ref_field = extract_fields(claim.text or "").get(ComparisonFieldName.CROSS_REFERENCE)
    if cross_ref_field is None or cross_ref_field.extraction_status != ExtractionStatus.EXTRACTED:
        return []

    matches = (cross_ref_field.value or {}).get("all_matches") or (
        [cross_ref_field.raw_surface_form] if cross_ref_field.raw_surface_form else []
    )
    markers = []
    for marker_text in matches:
        target_segment_ids = _target_segment_ids(marker_text, corpus_index)
        target_state = _resolve_target_state(target_segment_ids, trace)
        reference_type = (marker_text.split() or [""])[0].strip(".,;:").lower() or "unknown"
        markers.append(
            CrossReferenceMarker(
                marker_text=marker_text,
                source_span=cross_ref_field.source_span,
                target_segment_ids=target_segment_ids,
                target_state=target_state,
                reference_type=reference_type,
                target_identifier=None,
                targets=[],
                extraction_confidence=None,
            )
        )
    return markers


def detect_cross_reference_markers(
    claim: AnswerClaim, corpus_index: CorpusIndex, trace: QueryTrace
) -> list[CrossReferenceMarker]:
    """One `CrossReferenceMarker` per explicit cross-reference match in `claim.text`
    (docs/cross-reference-diagnostic-spec.md, docs/eu-ai-act-article-cross-reference-fix-plan.md).
    Returns `[]` when the claim carries no such marker -- never a guessed marker.
    Combines the pre-existing generic cue detection (Section/Table/...) with the
    dedicated legal-citation detection (Article/Articles/Annex) added here; the two
    can never double-detect the same span (disjoint keyword sets).
    """

    markers = _detect_generic_cue_markers(claim, corpus_index, trace)
    markers.extend(_detect_legal_citation_markers(claim.text or "", corpus_index, trace))
    return markers


def cross_reference_warning(marker: CrossReferenceMarker) -> str | None:
    """The fixed, bounded warning text, or `None` when the target is already packed
    (no warning needed) -- docs/cross-reference-diagnostic-spec.md's exact template,
    never a causal/adjudicative claim. For a multi-target marker, `marker.target_state`
    is already the best-resolved state across all targets (`_aggregate_state`), so
    "packed" here means *at least one* cited target is packed -- the per-target
    breakdown in `marker.targets` shows which.
    """

    if marker.target_state == CrossReferenceTargetState.PACKED:
        return None
    return _WARNING_TEMPLATE.format(state=_STATE_PHRASES[marker.target_state])


def exactness_explanation(target: ReferenceTarget, marker_text: str) -> str | None:
    """Bounded, paragraph/point-aware reviewer text for one `ReferenceTarget` --
    docs/cross-reference-granularity-resolution-plan.md §6. Additive to, never a
    replacement for, `cross_reference_warning` (which keeps its existing behavior
    unchanged for every caller). Returns `None` for a bare article/annex citation
    (`paragraph_number is None`) -- there is no sub-target to say anything new about,
    preserving "do not change plain `Article 49` semantics" exactly. Otherwise always
    returns bounded, non-adjudicative text, even when the exact target is present --
    the whole point is to stop silence (a suppressed warning) from being read as an
    unstated confirmation.
    """

    if target.paragraph_number is None:
        return None

    stage_phrase = _STAGE_LOCATION_PHRASES.get(target.target_state)

    if target.exact_target_status == ExactTargetAvailability.TARGET_UNKNOWN:
        body = _TARGET_UNKNOWN_TEXT
    elif target.exact_target_status == ExactTargetAvailability.TARGET_MISSING:
        body = _TARGET_MISSING_TEXT
    elif stage_phrase is None:
        # Defensive only -- every non-UNKNOWN/TARGET_MISSING branch of
        # _resolve_granularity_and_exactness requires at least one surfaced segment,
        # which implies target_state is one of the four stage-bearing states above.
        body = _TARGET_UNKNOWN_TEXT  # pragma: no cover
    elif target.exact_target_status == ExactTargetAvailability.EXACT_TARGET_PRESENT:
        body = _EXACT_TARGET_PRESENT_TEMPLATE.format(marker_text=marker_text, stage_phrase=stage_phrase)
    elif target.exact_target_status == ExactTargetAvailability.PARENT_ONLY_PRESENT:
        body = _PARENT_ONLY_PRESENT_TEMPLATE.format(stage_phrase=stage_phrase)
    elif target.exact_target_status == ExactTargetAvailability.SIBLING_ONLY_PRESENT:
        body = _SIBLING_ONLY_PRESENT_TEMPLATE.format(stage_phrase=stage_phrase)
    else:
        body = _BROADER_CONTEXT_PRESENT_TEMPLATE.format(stage_phrase=stage_phrase)

    return body + _HUMAN_REVIEW_SUFFIX


def marker_to_dict(marker: CrossReferenceMarker) -> dict:
    """The full JSON-serializable shape of one `CrossReferenceMarker`, including its
    per-target coarse state, resolution granularity, exact-target availability, and
    bounded reviewer explanation -- the single source of this shape, used by both
    `evidence_set_diagnostics/runner.py::build_diagnostic_report` and
    `api/routes/review.py`'s `/review/import-answer` response, so the two never drift
    apart (CLAUDE.md, "avoid two lists describing the same categories").
    """

    return {
        "marker_text": marker.marker_text,
        "source_span": marker.source_span,
        "target_segment_ids": marker.target_segment_ids,
        "target_state": marker.target_state.value,
        "warning": cross_reference_warning(marker),
        "reference_type": marker.reference_type,
        "range_start": marker.range_start,
        "range_end": marker.range_end,
        "target_identifier": marker.target_identifier,
        "extraction_method": marker.extraction_method,
        "extraction_confidence": marker.extraction_confidence,
        "targets": [
            {
                "target_identifier": t.target_identifier,
                "article_number": t.article_number,
                "paragraph_number": t.paragraph_number,
                "subdivision_type": t.subdivision_type,
                "subdivision_identifier": t.subdivision_identifier,
                "target_segment_ids": t.target_segment_ids,
                "target_state": t.target_state.value,
                "resolution_granularity": t.resolution_granularity.value,
                "exact_target_status": t.exact_target_status.value,
                "exactness_explanation": exactness_explanation(t, marker.marker_text),
            }
            for t in marker.targets
        ],
    }
