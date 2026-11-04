"""Phase A orchestration: source texts -> SourceDocument/SourceSegment index +
CorpusProfile, with content-hash caching so an unchanged document is neither reparsed
nor re-segmented (docs/efficiency-and-processing-architecture.md §§2-3).

No LLM call anywhere in this module.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime

from wittgenstein.core.enums import SegmentType
from wittgenstein.ingestion import parser as deterministic_parser
from wittgenstein.ingestion.content_hash import cache_key, content_hash
from wittgenstein.ingestion.kv_cache import KVCache, MemoryKVCache
from wittgenstein.metrics.processing_metrics import ProcessingMetrics
from wittgenstein.schemas.corpus_profile import CorpusProfile, DistributionSummary
from wittgenstein.schemas.proposition import SourceDocument, SourceSegment

PARSER_VERSION = "deterministic-parser-1"


@dataclass
class CorpusIndex:
    corpus_id: str
    documents: dict[str, SourceDocument] = field(default_factory=dict)
    segments: dict[str, SourceSegment] = field(default_factory=dict)
    corpus_profile: CorpusProfile | None = None

    def segments_for_document(self, source_document_id: str) -> list[SourceSegment]:
        return [s for s in self.segments.values() if s.source_document_id == source_document_id]


def index_corpus(
    sources: dict[str, str],
    corpus_id: str,
    *,
    cache: KVCache | None = None,
    parser_version: str = PARSER_VERSION,
    metrics: ProcessingMetrics | None = None,
) -> CorpusIndex:
    """Index `sources` (source_document_id -> raw text) using the deterministic
    programmatic parser (Tier 0). A document whose content hash and `parser_version`
    match a cached entry is not reparsed -- its cached segments are reused as-is.
    """

    cache = cache if cache is not None else MemoryKVCache()
    index = CorpusIndex(corpus_id=corpus_id)
    now = datetime.now(UTC)

    for source_document_id, text in sources.items():
        doc_hash = content_hash(text)
        key = cache_key(source_document_id, doc_hash, parser_version, "deterministic")
        cached = cache.get(key)

        if cached is not None:
            if metrics is not None:
                metrics.record_cache_result(hit=True)
            segments = [SourceSegment.model_validate(s) for s in cached["segments"]]
        else:
            if metrics is not None:
                metrics.record_cache_result(hit=False)
            segments = deterministic_parser.parse_document(
                text,
                source_document_id=source_document_id,
                corpus_id=corpus_id,
                parser_version=parser_version,
            )
            cache.put(key, {"segments": [s.model_dump(mode="json") for s in segments]})

        for segment in segments:
            index.segments[segment.segment_id] = segment

        index.documents[source_document_id] = SourceDocument(
            source_document_id=source_document_id,
            corpus_id=corpus_id,
            content_hash=doc_hash,
            parser_version=parser_version,
            char_length=len(text),
            ingested_at=now,
        )

    index.corpus_profile = _build_corpus_profile(index, now)
    if metrics is not None:
        metrics.corpus_document_count = len(index.documents)
        metrics.corpus_segment_count = len(index.segments)
    return index


def _build_corpus_profile(index: CorpusIndex, now: datetime) -> CorpusProfile:
    segments = list(index.segments.values())
    doc_lengths = [doc.char_length for doc in index.documents.values()]
    table_rows = sum(1 for s in segments if s.segment_type == SegmentType.TABLE_ROW)
    list_items = sum(1 for s in segments if s.segment_type == SegmentType.LIST_ITEM)
    paragraphs_and_sentences = sum(
        1 for s in segments if s.segment_type in (SegmentType.PARAGRAPH, SegmentType.SENTENCE)
    )
    denominator = max(paragraphs_and_sentences, 1)
    cross_ref_count = sum(len(s.cross_reference_targets) for s in segments)

    return CorpusProfile(
        corpus_id=index.corpus_id,
        index_timestamp=now,
        document_count=len(index.documents),
        section_count=sum(1 for s in segments if s.segment_type == SegmentType.HEADING),
        token_count=None,  # not computed by the deterministic path -- see embedding/tokenizer step
        document_length_distribution=_distribution(doc_lengths),
        table_density=table_rows / denominator if denominator else None,
        list_density=list_items / denominator if denominator else None,
        cross_reference_density=cross_ref_count / denominator if denominator else None,
        profiling_method="deterministic_parser_v1",
        measurement_confidence="high",  # full corpus scan, not sampled
    )


def _distribution(values: list[int]) -> DistributionSummary | None:
    if not values:
        return None
    ordered = sorted(values)
    n = len(ordered)

    def percentile(p: float) -> float:
        idx = min(n - 1, max(0, int(round(p * (n - 1)))))
        return float(ordered[idx])

    return DistributionSummary(
        minimum=float(ordered[0]),
        p50=percentile(0.5),
        p90=percentile(0.9),
        maximum=float(ordered[-1]),
        mean=sum(ordered) / n,
        sample_size=n,
    )
