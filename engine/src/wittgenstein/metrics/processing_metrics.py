"""ProcessingMetrics: a companion object to one corpus-indexing or query run, never
folded into QueryTrace/PipelineManifest (docs/efficiency-and-processing-architecture.md
§6 -- same reasoning as LocalValidationRecord being its own object).

No arbitrary throughput claim is made here or anywhere in this codebase; this object
only ever reports what was actually measured for one specific run.
"""

from __future__ import annotations

import time
from contextlib import contextmanager
from dataclasses import dataclass, field

try:
    import resource

    _HAS_RESOURCE = True
except ImportError:  # pragma: no cover -- resource is POSIX-only
    _HAS_RESOURCE = False


@dataclass
class ProcessingMetrics:
    ingestion_latency_seconds: float | None = None
    parsing_latency_seconds: float | None = None
    indexing_latency_seconds: float | None = None
    embedding_latency_seconds: float | None = None
    retrieval_latency_seconds: float | None = None
    proposition_extraction_latency_seconds: float | None = None
    answer_generation_latency_seconds: float | None = None

    llm_call_count: int = 0
    input_tokens: int = 0
    output_tokens: int = 0

    cache_hits: int = 0
    cache_misses: int = 0

    memory_usage_kb: float | None = field(
        default=None,
        metadata={
            "description": "Best-effort (getrusage ru_maxrss on POSIX); None where unavailable, never estimated."
        },
    )

    corpus_document_count: int | None = None
    corpus_segment_count: int | None = None
    candidate_count: int | None = None
    packed_token_count: int | None = None

    def record_cache_result(self, *, hit: bool) -> None:
        if hit:
            self.cache_hits += 1
        else:
            self.cache_misses += 1

    def record_llm_call(self, *, input_tokens: int | None, output_tokens: int | None) -> None:
        self.llm_call_count += 1
        self.input_tokens += input_tokens or 0
        self.output_tokens += output_tokens or 0

    def capture_memory_usage(self) -> None:
        if not _HAS_RESOURCE:
            return
        usage = resource.getrusage(resource.RUSAGE_SELF)
        self.memory_usage_kb = float(usage.ru_maxrss)

    @property
    def cache_hit_rate(self) -> float | None:
        total = self.cache_hits + self.cache_misses
        if total == 0:
            return None
        return self.cache_hits / total


@contextmanager
def timed(metrics: ProcessingMetrics, field_name: str):
    """Context manager that sets `metrics.<field_name>` to the elapsed wall-clock time
    of the `with` block, in seconds. `field_name` must name a `*_latency_seconds`
    attribute on ProcessingMetrics.
    """

    if not hasattr(metrics, field_name):
        raise AttributeError(f"ProcessingMetrics has no field {field_name!r}")
    start = time.perf_counter()
    try:
        yield
    finally:
        setattr(metrics, field_name, time.perf_counter() - start)
