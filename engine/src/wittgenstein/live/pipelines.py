"""Declarative pipeline specs and presets (docs/live-pipeline-plan.md §7).

A `PipelineSpec` fully determines one live pipeline. It compiles to an honest
`PipelineManifest`: every field it sets corresponds to a runtime choice actually made,
and every field it does not determine stays `None` (unknown) -- CLAUDE.md, "never infer
missing manifest values".
"""

from __future__ import annotations

from datetime import UTC, datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator

from wittgenstein.core.enums import KPolicy, RetrievalChannel
from wittgenstein.live.corpus import STRUCTURAL, parse_chunker
from wittgenstein.live.embedding import EMBEDDER_CHOICES, EmbedderInfo
from wittgenstein.schemas.manifest import (
    CorpusManifest,
    PackingManifest,
    PipelineManifest,
    RepresentationManifest,
    RerankingManifest,
    RetrievalManifest,
    SelectionManifest,
)


class Remediation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    severed_neighbor: bool = True
    cross_reference: bool = True
    definition: bool = True

    @property
    def any(self) -> bool:
        return self.severed_neighbor or self.cross_reference or self.definition


class PipelineSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    pipeline_id: str
    label: str
    description: str
    chunker: str = STRUCTURAL
    channels: list[RetrievalChannel] = Field(default_factory=lambda: [RetrievalChannel.LEXICAL])
    embedder: str | None = None
    facet_queries: bool = False
    candidate_depth: int = Field(default=60, ge=1, le=500)
    k_policy: KPolicy = KPolicy.FIXED
    k: int = Field(default=5, ge=1, le=100, description="Fixed k; for adaptive, the starting estimate only.")
    k_min: int = Field(default=2, ge=1)
    k_max: int = Field(default=16, ge=1)
    token_budget: int = Field(default=1800, ge=64)
    remediation: Remediation = Field(
        default_factory=lambda: Remediation(severed_neighbor=False, cross_reference=False, definition=False)
    )

    @model_validator(mode="after")
    def _consistent(self) -> PipelineSpec:
        parse_chunker(self.chunker)
        if not self.channels or RetrievalChannel.REMEDIATION in self.channels:
            raise ValueError("channels must be a non-empty subset of lexical/dense/facet")
        needs_vectors = RetrievalChannel.DENSE in self.channels or self.facet_queries
        if needs_vectors and self.embedder is None:
            raise ValueError("dense retrieval or facet queries need an embedder")
        if self.embedder is not None and self.embedder not in EMBEDDER_CHOICES:
            raise ValueError(f"unknown embedder {self.embedder!r}")
        if self.k_min > self.k_max:
            raise ValueError("k_min > k_max")
        return self

    @property
    def uses_dense(self) -> bool:
        return RetrievalChannel.DENSE in self.channels

    @property
    def uses_lexical(self) -> bool:
        return RetrievalChannel.LEXICAL in self.channels

    def to_manifest(self, corpus_id: str, embedder: EmbedderInfo | None) -> PipelineManifest:
        topology = "+".join(c.value for c in self.channels) + ("+facet_subqueries" if self.facet_queries else "")
        fused = len(self.channels) > 1 or self.facet_queries
        return PipelineManifest(
            manifest_id=f"live:{self.pipeline_id}",
            system_name="wittgenstein-live",
            system_version="phase1",
            created_at=datetime.now(UTC),
            corpus_manifest=CorpusManifest(corpus_id=corpus_id),
            representation_manifest=RepresentationManifest(
                index_unit="passage_with_heading_context" if self.chunker == STRUCTURAL else "fixed_word_window",
                embedding_family=embedder.family.value if embedder else None,
                embedding_model_identifier=embedder.model_identifier if embedder else None,
            ),
            retrieval_manifest=RetrievalManifest(
                retriever_family=topology,
                retrieval_topology="reciprocal_rank_fusion" if fused else "single_retriever",
                retrieval_unit="passage" if self.chunker == STRUCTURAL else "window",
                chunking_method=self.chunker,
                candidate_depth=self.candidate_depth,
                query_transformation_enabled=self.facet_queries,
                query_transformation_method="facet_subqueries" if self.facet_queries else None,
                parent_child_expansion=self.remediation.severed_neighbor,
                graph_retrieval=False,
            ),
            reranking_manifest=RerankingManifest(reranking_enabled=False),
            selection_manifest=SelectionManifest(
                selection_policy=(
                    "coverage_aware_adaptive_k" if self.k_policy == KPolicy.ADAPTIVE else f"fixed_top_{self.k}"
                ),
                max_selected_items=self.k_max if self.k_policy == KPolicy.ADAPTIVE else self.k,
            ),
            packing_manifest=PackingManifest(
                packing_method="greedy_rank_order_token_budget",
                ordering_method="selection_order",
                compression_enabled=False,
                evidence_budget_tokens=self.token_budget,
            ),
        )


PRESETS: dict[str, PipelineSpec] = {
    p.pipeline_id: p
    for p in [
        PipelineSpec(
            pipeline_id="aware",
            label="Self-aware hybrid",
            description="Keyword + meaning search, a separate search per part of the question, coverage-aware "
            "selection, and automatic follow-up on severed context, cross-references and definitions.",
            channels=[RetrievalChannel.LEXICAL, RetrievalChannel.DENSE],
            embedder="potion-retrieval",
            facet_queries=True,
            k_policy=KPolicy.ADAPTIVE,
            k=6,
            k_min=3,
            remediation=Remediation(),
        ),
        PipelineSpec(
            pipeline_id="semantic-top5",
            label="Typical semantic RAG",
            description="Meaning-based search only, fixed top 5 -- the most common default setup.",
            channels=[RetrievalChannel.DENSE],
            embedder="potion-retrieval",
            k=5,
        ),
        PipelineSpec(
            pipeline_id="keyword-top5",
            label="Keyword search",
            description="Classic BM25 keyword search, fixed top 5.",
            channels=[RetrievalChannel.LEXICAL],
            k=5,
        ),
        PipelineSpec(
            pipeline_id="window-semantic",
            label="Fixed-window chunks",
            description="Meaning-based search over 120-word windows that ignore paragraph boundaries, "
            "fixed top 5.",
            chunker="window:120:20",
            channels=[RetrievalChannel.DENSE],
            embedder="potion-retrieval",
            k=5,
        ),
    ]
}
DEFAULT_PIPELINE = "aware"
