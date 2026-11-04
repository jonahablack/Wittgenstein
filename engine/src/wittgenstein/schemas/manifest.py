"""PipelineManifest and its per-stage section models.

Every optional field defaults to `None`, and `None` must be read as "unknown" by any
downstream consumer -- never silently defaulted to a "typical" value. `missing_information`
lets a manifest author additionally flag, by dotted path, fields they know are unknown
(useful when a field is present but the author wants to explicitly assert
non-knowledge rather than have it read as "not yet filled in").
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class CorpusManifest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    corpus_id: str | None = None
    source_type: str | None = None
    domain: str | None = None
    language: str | None = None
    document_count: int | None = None
    corpus_versioning: str | None = None


class IngestionManifest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    parser: str | None = None
    ocr_used: bool | None = None
    table_extraction_method: str | None = None
    structure_extraction_method: str | None = None


class RepresentationManifest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    index_unit: str | None = None
    embedding_family: str | None = None
    embedding_model_identifier: str | None = None


class RetrievalManifest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    retriever_family: str | None = None
    retrieval_topology: str | None = None
    retrieval_unit: str | None = None
    chunking_method: str | None = None
    chunk_size_or_distribution: str | None = None
    overlap_or_stride: str | None = None
    candidate_depth: int | None = None
    query_transformation_enabled: bool | None = None
    query_transformation_method: str | None = None
    parent_child_expansion: bool | None = None
    graph_retrieval: bool | None = None


class RerankingManifest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reranking_enabled: bool | None = None
    reranker_family: str | None = None
    rerank_depth: int | None = None


class SelectionManifest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    selection_policy: str | None = None
    max_selected_items: int | None = None


class PackingManifest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    packing_method: str | None = None
    ordering_method: str | None = None
    compression_enabled: bool | None = None
    compression_type: str | None = None
    compression_ratio: float | None = None
    context_window_tokens: int | None = None
    evidence_budget_tokens: int | None = None


class GenerationManifest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    generator_family: str | None = None
    model_identifier: str | None = None
    prompting_policy: str | None = None
    citation_policy: str | None = None
    abstention_policy: str | None = None


class EvaluationManifest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    evaluation_metrics: list[str] = Field(default_factory=list)
    human_review_enabled: bool | None = None


class PipelineManifest(BaseModel):
    """Declares the shape of a deployed (or synthetic) RAG system for a given run."""

    model_config = ConfigDict(extra="forbid")

    manifest_id: str
    system_name: str
    system_version: str
    created_at: datetime
    corpus_manifest: CorpusManifest = Field(default_factory=CorpusManifest)
    ingestion_manifest: IngestionManifest = Field(default_factory=IngestionManifest)
    representation_manifest: RepresentationManifest = Field(default_factory=RepresentationManifest)
    retrieval_manifest: RetrievalManifest = Field(default_factory=RetrievalManifest)
    reranking_manifest: RerankingManifest = Field(default_factory=RerankingManifest)
    selection_manifest: SelectionManifest = Field(default_factory=SelectionManifest)
    packing_manifest: PackingManifest = Field(default_factory=PackingManifest)
    generation_manifest: GenerationManifest = Field(default_factory=GenerationManifest)
    evaluation_manifest: EvaluationManifest = Field(default_factory=EvaluationManifest)
    missing_information: list[str] = Field(
        default_factory=list,
        description="Dotted paths the manifest author explicitly asserts are unknown.",
    )
