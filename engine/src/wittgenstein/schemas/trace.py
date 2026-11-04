"""QueryTrace and its item-level submodels.

Item lists are kept at separate pipeline stages (retrieval_candidates,
reranked_candidates, selected_context_items, packed_context_items,
omitted_context_items, compressed_context_items) so that "retrieved" is never
conflated with "available to the generator," and "available to the generator" is
never conflated with "used correctly" (that last question is answered only by
answer_support_edges, which is a separate, explicit judgment).
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from wittgenstein.core.enums import ClaimSupportCandidateStatus, TraceStatus


class ContextItem(BaseModel):
    """One retrieval/selection/packing-stage item. The same logical item is expected to
    carry the same `item_id` across stage lists so lineage can be tracked.
    """

    model_config = ConfigDict(extra="forbid")

    item_id: str
    source_document_id: str | None = None
    segment_id: str | None = None
    excerpt: str | None = None
    rank: int | None = None
    relevance_score: float | None = None
    is_query_related: bool | None = Field(
        default=None,
        description="Whether the item is topically related to the query, independent of "
        "whether it actually supports the answer. Distinguishes a 'hard distractor' "
        "(query-related, non-supporting) from random irrelevant noise.",
    )
    is_answer_supporting: bool | None = Field(
        default=None,
        description="Whether this item actually supports (part of) the answer. Set by "
        "reviewer judgment or gold-label lookup, not inferred from relevance_score.",
    )
    token_count: int | None = None
    omission_reason: str | None = Field(
        default=None, description='e.g. "context_budget_exceeded", "compressed_away".'
    )


class QueryRewrite(BaseModel):
    model_config = ConfigDict(extra="forbid")

    step: int
    original_query: str
    rewritten_query: str
    method: str | None = None


class PromptTokenSpan(BaseModel):
    """An actual span of the final prompt attributable to one context item."""

    model_config = ConfigDict(extra="forbid")

    context_item_id: str
    start_token: int
    end_token: int
    position_rank: int | None = Field(
        default=None,
        description="1 = earliest in the prompt. Used for position-sensitivity checks.",
    )


class AnswerClaim(BaseModel):
    model_config = ConfigDict(extra="forbid")

    claim_id: str
    text: str
    extraction_method: str | None = Field(
        default=None,
        description='How this claim was produced: "programmatic_rule_based", "llm_extracted", or '
        '"fallback_whole_answer" (one claim covering the entire answer text, used when neither of the '
        "other two tiers succeeded -- the original answer text is always preserved regardless).",
    )


class AnswerSupportEdge(BaseModel):
    """A reviewer- or pipeline-asserted link between an answer claim and context.

    `support_status` is intentionally not boolean: "supported" / "unsupported" /
    "contradicted" / "unknown" are distinct outcomes with distinct reviewer-facing
    meanings, and collapsing "unknown" into "unsupported" would misrepresent an
    unreviewed claim as a confirmed failure.
    """

    model_config = ConfigDict(extra="forbid")

    claim_id: str
    context_item_ids: list[str] = Field(default_factory=list)
    support_status: str = Field(..., description="supported | unsupported | contradicted | unknown")
    judged_by: str | None = Field(default=None, description='"reviewer" or "unreviewed".')
    candidate_support_status: ClaimSupportCandidateStatus | None = Field(
        default=None,
        description="A programmatic, pre-review candidate classification (see core/enums.py -- "
        "never a final correctness verdict, and independent of support_status, which remains the "
        "reviewer-facing/final field. A programmatically produced edge sets support_status='unknown', "
        "judged_by='unreviewed', and expresses its actual finding here instead.",
    )


class SupportRequirement(BaseModel):
    """The assessed support-set requirement for a query, if it has been assessed at all.

    Presence of this object does not by itself mean "multi-hop" -- `is_multi_hop`
    carries that, and can be explicitly False (assessed single-span) as distinct from
    the object being absent entirely (not assessed at all, i.e. unknown).
    """

    model_config = ConfigDict(extra="forbid")

    is_multi_hop: bool
    required_support_item_ids: list[str] = Field(default_factory=list)
    assessment_method: str = Field(default="reviewer_assessed")


class ContextConflict(BaseModel):
    """A reviewer- or pipeline-normalized conflict between two or more packed items."""

    model_config = ConfigDict(extra="forbid")

    conflict_id: str
    context_item_ids: list[str] = Field(..., min_length=2)
    dimension: str = Field(
        ...,
        description="entity | predicate | value | polarity | condition | time_version | jurisdiction | authority",
    )
    description: str


class RiskEventRef(BaseModel):
    """Lightweight reference embedded in a trace; the full RiskEvent lives separately."""

    model_config = ConfigDict(extra="forbid")

    risk_event_id: str
    mechanism_id: str


class QueryTrace(BaseModel):
    model_config = ConfigDict(extra="forbid")

    trace_id: str
    manifest_id: str
    corpus_id: str | None = None
    query: str
    query_timestamp: datetime
    query_constraints: dict[str, str] = Field(default_factory=dict)
    support_requirement: SupportRequirement | None = None
    query_rewrites: list[QueryRewrite] = Field(default_factory=list)
    # NOTE: these six stage lists are `| None`, not just `list[...] = []`, on purpose:
    # `None` means "this pipeline stage was not instrumented/logged for this trace,"
    # while `[]` means "the stage was logged and genuinely produced zero items." A gate
    # that requires "candidate/selected/packed stages are all logged" checks for `None`,
    # not for emptiness -- collapsing the two would misreport an uninstrumented stage as
    # a stage that legitimately retrieved/packed nothing.
    retrieval_candidates: list[ContextItem] | None = None
    reranked_candidates: list[ContextItem] | None = None
    selected_context_items: list[ContextItem] | None = None
    packed_context_items: list[ContextItem] | None = None
    omitted_context_items: list[ContextItem] | None = None
    compressed_context_items: list[ContextItem] | None = None
    final_prompt: str | None = None
    final_prompt_token_count: int | None = None
    final_prompt_evidence_budget: int | None = None
    prompt_token_spans: list[PromptTokenSpan] = Field(default_factory=list)
    generation_parameters: dict[str, str] = Field(default_factory=dict)
    answer: str | None = None
    answer_claims: list[AnswerClaim] = Field(default_factory=list)
    answer_support_edges: list[AnswerSupportEdge] = Field(default_factory=list)
    context_conflicts: list[ContextConflict] = Field(default_factory=list)
    conflict_ids_addressed_in_answer: list[str] = Field(
        default_factory=list,
        description="conflict_id values the answer explicitly flagged or resolved with a stated "
        "rationale, as opposed to silently picking/synthesizing one side.",
    )
    segment_boundary_dependency_flags: list[str] = Field(
        default_factory=list,
        description="Human-readable flags identifying a support/dependency relation that crosses "
        "a retrieval-segment boundary, e.g. detected during trace instrumentation.",
    )
    risk_events: list[RiskEventRef] = Field(default_factory=list)
    trace_status: TraceStatus
