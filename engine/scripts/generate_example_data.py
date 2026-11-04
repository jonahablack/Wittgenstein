#!/usr/bin/env python
"""Generate the five bundled synthetic manifest/trace example pairs.

Usage: uv run python scripts/generate_example_data.py [output_dir]

These are synthetic fixtures for exercising the matching engine end-to-end -- they are
not real production traces, and are labeled as such in each file's `system_name` /
`query`.
"""

from __future__ import annotations

import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from wittgenstein.core.enums import TraceStatus
from wittgenstein.schemas.manifest import (
    CorpusManifest,
    GenerationManifest,
    PackingManifest,
    PipelineManifest,
    RerankingManifest,
    RetrievalManifest,
    SelectionManifest,
)
from wittgenstein.schemas.trace import (
    AnswerClaim,
    AnswerSupportEdge,
    ContextConflict,
    ContextItem,
    PromptTokenSpan,
    QueryRewrite,
    QueryTrace,
    SupportRequirement,
)

NOW = datetime(2026, 9, 2, tzinfo=UTC)


def _manifest(**kwargs: Any) -> PipelineManifest:
    base: dict[str, Any] = dict(system_version="0.1.0-synthetic", created_at=NOW)
    base.update(kwargs)
    return PipelineManifest(**base)


def scenario_single_passage() -> tuple[PipelineManifest, QueryTrace]:
    manifest = _manifest(
        manifest_id="MANIFEST-single-passage-001",
        system_name="synthetic-single-passage-rag",
        corpus_manifest=CorpusManifest(corpus_id="CORPUS-faq-001", domain="internal_faq", document_count=120),
        retrieval_manifest=RetrievalManifest(
            retriever_family="bm25",
            retrieval_unit="passage",
            chunking_method="fixed_size",
            chunk_size_or_distribution="256_tokens",
            candidate_depth=5,
        ),
        reranking_manifest=RerankingManifest(reranking_enabled=False),
        selection_manifest=SelectionManifest(selection_policy="top_1", max_selected_items=1),
        packing_manifest=PackingManifest(
            packing_method="single_item",
            context_window_tokens=2000,
            evidence_budget_tokens=500,
        ),
        generation_manifest=GenerationManifest(generator_family="small_instruct_llm"),
    )
    item = ContextItem(
        item_id="item-1",
        source_document_id="doc-42",
        excerpt="Refunds are processed within 5 business days.",
        rank=1,
        is_query_related=True,
        is_answer_supporting=True,
        token_count=14,
    )
    trace = QueryTrace(
        trace_id="TRACE-single-passage-001",
        manifest_id=manifest.manifest_id,
        corpus_id="CORPUS-faq-001",
        query="How long do refunds take?",
        query_timestamp=NOW,
        retrieval_candidates=[item],
        selected_context_items=[item],
        packed_context_items=[item],
        omitted_context_items=[],
        compressed_context_items=[],
        final_prompt="Context: Refunds are processed within 5 business days.\nQ: How long do refunds take?",
        final_prompt_token_count=40,
        prompt_token_spans=[
            PromptTokenSpan(context_item_id="item-1", start_token=0, end_token=14, position_rank=1)
        ],
        answer="Refunds take 5 business days.",
        answer_claims=[AnswerClaim(claim_id="claim-1", text="Refunds take 5 business days.")],
        answer_support_edges=[
            AnswerSupportEdge(claim_id="claim-1", context_item_ids=["item-1"], support_status="supported")
        ],
        trace_status=TraceStatus.COMPLETE,
    )
    return manifest, trace


def scenario_multi_passage_rerank_budget() -> tuple[PipelineManifest, QueryTrace]:
    manifest = _manifest(
        manifest_id="MANIFEST-multi-passage-rerank-001",
        system_name="synthetic-multi-passage-dense-rag",
        corpus_manifest=CorpusManifest(corpus_id="CORPUS-policy-001", domain="hr_policy", document_count=4000),
        retrieval_manifest=RetrievalManifest(
            retriever_family="dense_bi_encoder",
            retrieval_unit="chunk",
            chunking_method="semantic_chunking",
            chunk_size_or_distribution="~400_tokens",
            candidate_depth=50,
        ),
        reranking_manifest=RerankingManifest(
            reranking_enabled=True, reranker_family="cross_encoder", rerank_depth=10
        ),
        selection_manifest=SelectionManifest(selection_policy="top_k", max_selected_items=6),
        packing_manifest=PackingManifest(
            packing_method="concatenate_ranked",
            ordering_method="rank_descending",
            context_window_tokens=8000,
            evidence_budget_tokens=6500,
        ),
        generation_manifest=GenerationManifest(generator_family="large_instruct_llm"),
    )
    items = [
        ContextItem(
            item_id="item-1",
            source_document_id="doc-1",
            excerpt="Vacation accrual is 1.5 days/month.",
            rank=1,
            is_query_related=True,
            is_answer_supporting=True,
            token_count=900,
        ),
        ContextItem(
            item_id="item-2",
            source_document_id="doc-2",
            excerpt="Parental leave policy overview (different topic, same department).",
            rank=2,
            is_query_related=True,
            is_answer_supporting=False,
            token_count=1100,
        ),
        ContextItem(
            item_id="item-3",
            source_document_id="doc-3",
            excerpt="Vacation payout on termination rules.",
            rank=3,
            is_query_related=True,
            is_answer_supporting=True,
            token_count=950,
        ),
        ContextItem(
            item_id="item-4",
            source_document_id="doc-4",
            excerpt="Office holiday calendar 2026.",
            rank=4,
            is_query_related=False,
            is_answer_supporting=False,
            token_count=800,
        ),
    ]
    spans = [
        PromptTokenSpan(context_item_id="item-1", start_token=0, end_token=900, position_rank=1),
        PromptTokenSpan(context_item_id="item-2", start_token=900, end_token=2000, position_rank=2),
        PromptTokenSpan(context_item_id="item-3", start_token=2000, end_token=2950, position_rank=3),
        PromptTokenSpan(context_item_id="item-4", start_token=2950, end_token=3750, position_rank=4),
    ]
    trace = QueryTrace(
        trace_id="TRACE-multi-passage-rerank-001",
        manifest_id=manifest.manifest_id,
        corpus_id="CORPUS-policy-001",
        query="How does vacation accrual work and what happens to unused days if I leave?",
        query_timestamp=NOW,
        retrieval_candidates=items,
        reranked_candidates=items,
        selected_context_items=items,
        packed_context_items=items,
        omitted_context_items=[],
        compressed_context_items=[],
        final_prompt="...(concatenated policy excerpts)...",
        final_prompt_token_count=4200,
        prompt_token_spans=spans,
        answer="Vacation accrues at 1.5 days/month and unused days are paid out on termination.",
        answer_claims=[
            AnswerClaim(claim_id="claim-1", text="Vacation accrues at 1.5 days/month."),
            AnswerClaim(claim_id="claim-2", text="Unused days are paid out on termination."),
        ],
        answer_support_edges=[
            AnswerSupportEdge(claim_id="claim-1", context_item_ids=["item-1"], support_status="supported"),
            AnswerSupportEdge(claim_id="claim-2", context_item_ids=["item-3"], support_status="supported"),
        ],
        trace_status=TraceStatus.COMPLETE,
    )
    return manifest, trace


def scenario_parent_child_omitted_crossref() -> tuple[PipelineManifest, QueryTrace]:
    manifest = _manifest(
        manifest_id="MANIFEST-parent-child-crossref-001",
        system_name="synthetic-parent-child-proposition-rag",
        corpus_manifest=CorpusManifest(
            corpus_id="CORPUS-regulatory-001", domain="regulatory_filings", document_count=900
        ),
        retrieval_manifest=RetrievalManifest(
            retriever_family="dense_bi_encoder",
            retrieval_unit="proposition",
            chunking_method="proposition_segmentation",
            candidate_depth=30,
            parent_child_expansion=True,
        ),
        reranking_manifest=RerankingManifest(
            reranking_enabled=True, reranker_family="cross_encoder", rerank_depth=8
        ),
        selection_manifest=SelectionManifest(selection_policy="top_k", max_selected_items=5),
        packing_manifest=PackingManifest(packing_method="concatenate_ranked", context_window_tokens=6000),
        generation_manifest=GenerationManifest(generator_family="large_instruct_llm"),
    )
    selected = [
        ContextItem(
            item_id="item-1",
            source_document_id="doc-12",
            segment_id="doc12-seg3",
            excerpt="Filers must submit Form 7 unless exempted under 12.3(a).",
            is_query_related=True,
            is_answer_supporting=True,
            token_count=200,
        ),
        ContextItem(
            item_id="item-2",
            source_document_id="doc-12",
            segment_id="doc12-seg4",
            excerpt="Exemption 12.3(a) applies to entities under $1M revenue.",
            is_query_related=True,
            is_answer_supporting=True,
            token_count=180,
        ),
    ]
    packed = [selected[0]]  # item-2 selected but not packed
    trace = QueryTrace(
        trace_id="TRACE-parent-child-crossref-001",
        manifest_id=manifest.manifest_id,
        corpus_id="CORPUS-regulatory-001",
        query="Does a $500K-revenue filer need to submit Form 7?",
        query_timestamp=NOW,
        support_requirement=SupportRequirement(is_multi_hop=True, required_support_item_ids=["item-1", "item-2"]),
        retrieval_candidates=selected,
        selected_context_items=selected,
        packed_context_items=packed,
        omitted_context_items=[
            ContextItem(
                item_id="item-2",
                source_document_id="doc-12",
                segment_id="doc12-seg4",
                omission_reason="context_budget_exceeded",
            )
        ],
        compressed_context_items=[],
        segment_boundary_dependency_flags=[
            "support proposition split between segment_id=doc12-seg3 and segment_id=doc12-seg4"
        ],
        final_prompt="...(Form 7 requirement excerpt only, exemption clause omitted)...",
        final_prompt_token_count=1800,
        prompt_token_spans=[
            PromptTokenSpan(context_item_id="item-1", start_token=0, end_token=200, position_rank=1)
        ],
        answer="Yes, this filer must submit Form 7.",
        answer_claims=[AnswerClaim(claim_id="claim-1", text="This filer must submit Form 7.")],
        answer_support_edges=[
            AnswerSupportEdge(claim_id="claim-1", context_item_ids=["item-1"], support_status="unsupported")
        ],
        trace_status=TraceStatus.COMPLETE,
    )
    return manifest, trace


def scenario_compression_enabled() -> tuple[PipelineManifest, QueryTrace]:
    manifest = _manifest(
        manifest_id="MANIFEST-compression-001",
        system_name="synthetic-compression-enabled-rag",
        corpus_manifest=CorpusManifest(
            corpus_id="CORPUS-support-tickets-001", domain="customer_support", document_count=25000
        ),
        retrieval_manifest=RetrievalManifest(
            retriever_family="dense_bi_encoder",
            retrieval_unit="chunk",
            chunking_method="fixed_size",
            candidate_depth=40,
        ),
        reranking_manifest=RerankingManifest(
            reranking_enabled=True, reranker_family="cross_encoder", rerank_depth=12
        ),
        selection_manifest=SelectionManifest(selection_policy="top_k", max_selected_items=8),
        packing_manifest=PackingManifest(
            packing_method="compress_then_concatenate",
            compression_enabled=True,
            compression_type="extractive_summarization",
            compression_ratio=0.4,
            context_window_tokens=4000,
            evidence_budget_tokens=3000,
        ),
        generation_manifest=GenerationManifest(generator_family="mid_instruct_llm"),
    )
    selected = [
        ContextItem(
            item_id="item-1",
            source_document_id="doc-7",
            excerpt="Reset your password via Settings > Security.",
            is_query_related=True,
            is_answer_supporting=True,
            token_count=600,
        ),
        ContextItem(
            item_id="item-2",
            source_document_id="doc-8",
            excerpt="If SSO is enabled, password reset must go through your identity provider instead.",
            is_query_related=True,
            is_answer_supporting=True,
            token_count=500,
        ),
    ]
    trace = QueryTrace(
        trace_id="TRACE-compression-001",
        manifest_id=manifest.manifest_id,
        corpus_id="CORPUS-support-tickets-001",
        query="How do I reset my password?",
        query_timestamp=NOW,
        retrieval_candidates=selected,
        selected_context_items=selected,
        packed_context_items=[selected[0]],
        omitted_context_items=[],
        compressed_context_items=[
            ContextItem(
                item_id="item-2",
                source_document_id="doc-8",
                excerpt="If SSO is enabled, password reset must go through your identity provider instead.",
                omission_reason="compressed_away_below_relevance_threshold",
            )
        ],
        final_prompt="...(password reset via Settings > Security only; SSO caveat compressed away)...",
        final_prompt_token_count=700,
        prompt_token_spans=[
            PromptTokenSpan(context_item_id="item-1", start_token=0, end_token=600, position_rank=1)
        ],
        answer="Go to Settings > Security to reset your password.",
        answer_claims=[AnswerClaim(claim_id="claim-1", text="Go to Settings > Security to reset your password.")],
        answer_support_edges=[
            AnswerSupportEdge(claim_id="claim-1", context_item_ids=["item-1"], support_status="supported")
        ],
        trace_status=TraceStatus.COMPLETE,
    )
    return manifest, trace


def scenario_query_rewriting_multihop() -> tuple[PipelineManifest, QueryTrace]:
    manifest = _manifest(
        manifest_id="MANIFEST-query-rewrite-multihop-001",
        system_name="synthetic-query-rewriting-multihop-rag",
        corpus_manifest=CorpusManifest(
            corpus_id="CORPUS-product-docs-001", domain="product_documentation", document_count=1500
        ),
        retrieval_manifest=RetrievalManifest(
            retriever_family="dense_bi_encoder",
            retrieval_unit="chunk",
            chunking_method="semantic_chunking",
            candidate_depth=25,
            query_transformation_enabled=True,
            query_transformation_method="iterative_decomposition",
        ),
        reranking_manifest=RerankingManifest(
            reranking_enabled=True, reranker_family="cross_encoder", rerank_depth=10
        ),
        selection_manifest=SelectionManifest(selection_policy="top_k", max_selected_items=6),
        packing_manifest=PackingManifest(packing_method="concatenate_ranked", context_window_tokens=8000),
        generation_manifest=GenerationManifest(generator_family="large_instruct_llm"),
    )
    items = [
        ContextItem(
            item_id="item-1",
            source_document_id="doc-a",
            excerpt="Plan A supports up to 5 seats.",
            is_query_related=True,
            is_answer_supporting=True,
            token_count=200,
        ),
        ContextItem(
            item_id="item-2",
            source_document_id="doc-b",
            excerpt="Plan A pricing was $20/seat/month as of the March 2025 price sheet.",
            is_query_related=True,
            is_answer_supporting=True,
            token_count=220,
        ),
        ContextItem(
            item_id="item-3",
            source_document_id="doc-c",
            excerpt="Plan A pricing is $25/seat/month as of the January 2026 price sheet.",
            is_query_related=True,
            is_answer_supporting=True,
            token_count=225,
        ),
    ]
    trace = QueryTrace(
        trace_id="TRACE-query-rewrite-multihop-001",
        manifest_id=manifest.manifest_id,
        corpus_id="CORPUS-product-docs-001",
        query="What would 5 seats on Plan A cost per month?",
        query_timestamp=NOW,
        query_rewrites=[
            QueryRewrite(
                step=1,
                original_query="What would 5 seats on Plan A cost per month?",
                rewritten_query="Plan A seat capacity",
                method="decomposition",
            ),
            QueryRewrite(
                step=2,
                original_query="What would 5 seats on Plan A cost per month?",
                rewritten_query="Plan A price per seat",
                method="decomposition",
            ),
        ],
        support_requirement=SupportRequirement(
            is_multi_hop=True, required_support_item_ids=["item-1", "item-2", "item-3"]
        ),
        retrieval_candidates=items,
        selected_context_items=items,
        packed_context_items=items,
        omitted_context_items=[],
        compressed_context_items=[],
        context_conflicts=[
            ContextConflict(
                conflict_id="conflict-1",
                context_item_ids=["item-2", "item-3"],
                dimension="time_version",
                description="Two different effective price-sheet dates give different per-seat prices.",
            )
        ],
        conflict_ids_addressed_in_answer=[],
        final_prompt="...(all three excerpts concatenated)...",
        final_prompt_token_count=2100,
        prompt_token_spans=[
            PromptTokenSpan(context_item_id="item-1", start_token=0, end_token=200, position_rank=1),
            PromptTokenSpan(context_item_id="item-2", start_token=200, end_token=420, position_rank=2),
            PromptTokenSpan(context_item_id="item-3", start_token=420, end_token=645, position_rank=3),
        ],
        answer="5 seats on Plan A would cost $125/month.",
        answer_claims=[AnswerClaim(claim_id="claim-1", text="5 seats on Plan A would cost $125/month.")],
        answer_support_edges=[
            AnswerSupportEdge(
                claim_id="claim-1",
                context_item_ids=["item-1", "item-3"],
                support_status="supported",
            )
        ],
        trace_status=TraceStatus.COMPLETE,
    )
    return manifest, trace


SCENARIOS = {
    "single_passage": scenario_single_passage,
    "multi_passage_rerank_budget": scenario_multi_passage_rerank_budget,
    "parent_child_omitted_crossref": scenario_parent_child_omitted_crossref,
    "compression_enabled": scenario_compression_enabled,
    "query_rewriting_multihop": scenario_query_rewriting_multihop,
}


def main(output_dir: Path = Path("data/examples")) -> None:
    manifests_dir = output_dir / "manifests"
    traces_dir = output_dir / "traces"
    manifests_dir.mkdir(parents=True, exist_ok=True)
    traces_dir.mkdir(parents=True, exist_ok=True)

    for name, builder in SCENARIOS.items():
        manifest, trace = builder()
        (manifests_dir / f"{name}.json").write_text(
            json.dumps(json.loads(manifest.model_dump_json()), indent=2) + "\n"
        )
        (traces_dir / f"{name}.json").write_text(json.dumps(json.loads(trace.model_dump_json()), indent=2) + "\n")
        print(f"wrote {name}")


if __name__ == "__main__":
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("data/examples")
    main(out)
