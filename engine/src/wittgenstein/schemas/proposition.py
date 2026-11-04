"""Corpus-time and query-time processing artifacts: SourceDocument, SourceSegment
(Tier 0), PropositionCandidate (Tier 1), PropositionAnnotation (Tier 2), and
LLMExtractionResult (Tier 3) -- see docs/efficiency-and-processing-architecture.md.

These are a distinct layer from the registry/manifest/trace schemas: they describe
*how a corpus was processed*, not a mechanism claim, an evidence record, or one query's
execution. A SourceSegment can be converted into a `schemas.trace.ContextItem` once it
is retrieved/selected/packed for a specific query -- the two are related but not the
same type, matching this project's "never collapse related-but-distinct concepts" rule
(CLAUDE.md).
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator

from wittgenstein.core.enums import (
    AnnotationCueType,
    CueEpistemicLabel,
    ExtractionValidationStatus,
    SegmentType,
)


class SourceDocument(BaseModel):
    """One corpus-time-indexed document. `content_hash` is what makes corpus-time
    caching possible (docs/efficiency-and-processing-architecture.md §3): a document
    whose hash and `parser_version` are unchanged from a prior index run is not
    reparsed or re-segmented.
    """

    model_config = ConfigDict(extra="forbid")

    source_document_id: str
    corpus_id: str
    content_hash: str = Field(..., description="sha256 of the raw document bytes/text.")
    source_version: str | None = Field(
        default=None,
        description="Author/publisher-declared version or revision identifier, if any -- distinct "
        "from content_hash, which is derived, not declared.",
    )
    parser_version: str
    title: str | None = None
    char_length: int
    ingested_at: datetime


class SourceSegment(BaseModel):
    """A Tier-0 structural segment, created programmatically from existing document
    structure -- never by an LLM. Offsets and provenance are always preserved
    (docs/efficiency-and-processing-architecture.md §5).
    """

    model_config = ConfigDict(extra="forbid")

    segment_id: str
    source_document_id: str
    corpus_id: str
    source_version: str | None = None
    segment_type: SegmentType
    location: str = Field(..., description='Human-readable structural path, e.g. "Section 2 > Paragraph 3".')
    text: str
    char_start: int = Field(..., description="Always present -- character offsets are always computable.")
    char_end: int
    token_start: int | None = Field(
        default=None, description="Present only when a tokenizer actually ran; never inferred from char offsets."
    )
    token_end: int | None = None
    parent_segment_id: str | None = None
    cross_reference_targets: list[str] = Field(
        default_factory=list, description="Raw Tier-2 pattern matches (e.g. 'Section 4.2') -- not resolved to ids."
    )
    legal_article_number: str | None = Field(
        default=None,
        description="Set only when this segment's document contains an explicit 'Article <N>' title "
        "paragraph, carried forward to later segments in the same document. Never inferred from "
        "source_document_id/filename -- see docs/cross-reference-granularity-resolution-plan.md §4.",
    )
    legal_paragraph_number: str | None = Field(
        default=None,
        description="Set only when this segment's own leading marker (or, for a carried-forward "
        "continuation/point, the most recent preceding marker in document order) is an explicit "
        "bare-number list marker ('1. ', '2. ', ...) -- never inferred from position/filename alone.",
    )
    legal_point_identifier: str | None = Field(
        default=None,
        description="Set only when this segment's own text begins with an explicit '(<letter>) ' "
        "marker. Always paired with whatever legal_paragraph_number is in force at that point.",
    )
    legal_annex_identifier: str | None = Field(
        default=None,
        description="Set only when this segment's document contains an explicit 'Annex <roman "
        "numeral>' title paragraph, carried forward the same way as legal_article_number.",
    )
    parser_version: str

    @model_validator(mode="after")
    def _char_end_not_before_start(self) -> SourceSegment:
        if self.char_end < self.char_start:
            raise ValueError(f"SourceSegment {self.segment_id}: char_end < char_start.")
        return self


class PropositionCandidate(BaseModel):
    """A Tier-1 candidate proposition: a programmatically derived span within a
    SourceSegment. The original segment is never rewritten -- `source_segment_id`
    always points at the untouched Tier-0 text; `char_start`/`char_end` are offsets
    *within that segment's text*, not into the whole document.
    """

    model_config = ConfigDict(extra="forbid")

    candidate_id: str
    source_segment_id: str
    text: str = Field(
        ..., description="The derived candidate span's own text, for convenience -- never rewritten."
    )
    char_start: int
    char_end: int
    split_method: str = Field(
        ...,
        description='Which rule produced this candidate, e.g. "sentence_boundary", "semicolon", '
        '"conjunction", "relative_clause", "condition_marker", "list_item".',
    )
    is_ambiguous: bool = Field(
        default=False,
        description="Set when the rule-based splitter could not confidently separate multiple clauses/claims -- "
        "a Tier-3 escalation trigger, not a Tier-1 semantic judgment.",
    )

    @model_validator(mode="after")
    def _char_end_not_before_start(self) -> PropositionCandidate:
        if self.char_end < self.char_start:
            raise ValueError(f"PropositionCandidate {self.candidate_id}: char_end < char_start.")
        return self


class PropositionAnnotation(BaseModel):
    """A Tier-2 lightweight annotation: a candidate risk cue or dependency link, never a
    guaranteed semantic interpretation (docs/efficiency-and-processing-architecture.md
    §1). `epistemic_label` is always `research_hypothesis` or `experimental_review_cue`
    -- this type structurally cannot assert a confirmed error, matching the registry's
    own epistemic-status discipline for the mechanisms these cues might feed into.
    """

    model_config = ConfigDict(extra="forbid")

    annotation_id: str
    candidate_id: str
    cue_type: AnnotationCueType
    matched_text: str
    char_start: int = Field(..., description="Offset within the PropositionCandidate's text.")
    char_end: int
    epistemic_label: CueEpistemicLabel = CueEpistemicLabel.EXPERIMENTAL_REVIEW_CUE
    detector_version: str

    @model_validator(mode="after")
    def _char_end_not_before_start(self) -> PropositionAnnotation:
        if self.char_end < self.char_start:
            raise ValueError(f"PropositionAnnotation {self.annotation_id}: char_end < char_start.")
        return self


class LLMExtractionResult(BaseModel):
    """The result of one Tier-3 LLM extraction attempt -- also the LLM cache's value
    type (docs/efficiency-and-processing-architecture.md §3), not a separate shape.
    Fallback (§7) always populates this with a non-`validated` status and leaves
    `parsed_output` `None` rather than raising or guessing.
    """

    model_config = ConfigDict(extra="forbid")

    cache_key: str
    candidate_id: str
    model: str | None = Field(default=None, description="None when no call was attempted (llm_unavailable).")
    prompt_version: str
    schema_version: str
    extractor_version: str
    raw_output: str | None = None
    parsed_output: dict | None = Field(
        default=None, description="Parsed semantic result, only present when validation_status=validated."
    )
    validation_status: ExtractionValidationStatus
    validation_errors: list[str] = Field(default_factory=list)
    input_tokens: int | None = None
    output_tokens: int | None = None
    latency_seconds: float | None = None
    requested_at: datetime
    from_cache: bool = False

    @model_validator(mode="after")
    def _validated_requires_parsed_output(self) -> LLMExtractionResult:
        if self.validation_status == ExtractionValidationStatus.VALIDATED and self.parsed_output is None:
            raise ValueError(
                f"LLMExtractionResult {self.cache_key}: validation_status=validated requires parsed_output."
            )
        if self.validation_status != ExtractionValidationStatus.VALIDATED and self.parsed_output is not None:
            raise ValueError(
                f"LLMExtractionResult {self.cache_key}: parsed_output must be None unless "
                "validation_status=validated -- never present a guess as if it were validated output."
            )
        return self
