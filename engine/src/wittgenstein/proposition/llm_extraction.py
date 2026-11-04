"""Tier-3 orchestration: content-addressed cache lookup, then (only on a miss) an LLM
call, with graceful fallback whenever the client is unavailable or its output fails
validation -- docs/efficiency-and-processing-architecture.md §§3, 7.

This is the *only* place in the codebase that decides whether to call an LLM at all;
every caller (query-time proposition enrichment, the demo's "enhanced mode") goes
through `extract_tier3` / `extract_tier3_batch`, never the client directly, so the
cache and fallback behavior can never be bypassed.
"""

from __future__ import annotations

import time
from datetime import UTC, datetime

from wittgenstein.core.enums import ExtractionValidationStatus
from wittgenstein.ingestion.content_hash import cache_key as compute_cache_key
from wittgenstein.ingestion.kv_cache import KVCache, MemoryKVCache
from wittgenstein.metrics.processing_metrics import ProcessingMetrics
from wittgenstein.proposition.llm_client import LLMClient, NullLLMClient
from wittgenstein.schemas.proposition import LLMExtractionResult

EXTRACTOR_VERSION = "tier3-extractor-1"
PROMPT_VERSION = "proposition-decomposition-v1"
SCHEMA_VERSION = "llm-extraction-result-v1"


def extract_tier3(
    candidate_id: str,
    text: str,
    *,
    client: LLMClient | None = None,
    cache: KVCache | None = None,
    model_id: str = "unconfigured",
    prompt_version: str = PROMPT_VERSION,
    schema_version: str = SCHEMA_VERSION,
    extractor_version: str = EXTRACTOR_VERSION,
    metrics: ProcessingMetrics | None = None,
) -> LLMExtractionResult:
    """Look up (source_text, extractor_version, model_id, prompt_version,
    schema_version) in `cache`; on a hit, return the cached result unchanged
    (`from_cache=True`, no client call). On a miss: if `client` is None or
    `client.is_available()` is False, return a fallback result
    (`validation_status=llm_unavailable`, `parsed_output=None`) -- never raise. If the
    client call itself raises, or its output fails to parse as a dict, return
    `validation_status=validation_failed`, again with `parsed_output=None`. Every
    non-cache-hit outcome is written to the cache, including fallbacks, so an
    unavailable-LLM run does not retry the same call every time it is queried again
    within the same cache scope.
    """

    cache = cache if cache is not None else MemoryKVCache()
    key = compute_cache_key(text, extractor_version, model_id, prompt_version, schema_version)

    cached = cache.get(key)
    if cached is not None:
        if metrics is not None:
            metrics.record_cache_result(hit=True)
        result = LLMExtractionResult.model_validate(cached)
        return result.model_copy(update={"from_cache": True})

    if metrics is not None:
        metrics.record_cache_result(hit=False)

    now = datetime.now(UTC)
    effective_client = client if client is not None else NullLLMClient()

    if not effective_client.is_available():
        result = LLMExtractionResult(
            cache_key=key,
            candidate_id=candidate_id,
            model=None,
            prompt_version=prompt_version,
            schema_version=schema_version,
            extractor_version=extractor_version,
            raw_output=None,
            parsed_output=None,
            validation_status=ExtractionValidationStatus.LLM_UNAVAILABLE,
            validation_errors=["No LLM client configured or client reported unavailable."],
            requested_at=now,
        )
        cache.put(key, result.model_dump(mode="json"))
        return result

    start = time.perf_counter()
    try:
        call_result = effective_client.extract(text, prompt_version=prompt_version, schema_version=schema_version)
    except Exception as exc:  # noqa: BLE001 -- any client failure must fall back, not propagate
        latency = time.perf_counter() - start
        result = LLMExtractionResult(
            cache_key=key,
            candidate_id=candidate_id,
            model=model_id,
            prompt_version=prompt_version,
            schema_version=schema_version,
            extractor_version=extractor_version,
            raw_output=None,
            parsed_output=None,
            validation_status=ExtractionValidationStatus.LLM_UNAVAILABLE,
            validation_errors=[f"LLM call raised: {exc!r}"],
            latency_seconds=latency,
            requested_at=now,
        )
        cache.put(key, result.model_dump(mode="json"))
        return result
    latency = time.perf_counter() - start

    if metrics is not None:
        metrics.record_llm_call(input_tokens=call_result.input_tokens, output_tokens=call_result.output_tokens)

    if not isinstance(call_result.parsed_output, dict):
        result = LLMExtractionResult(
            cache_key=key,
            candidate_id=candidate_id,
            model=model_id,
            prompt_version=prompt_version,
            schema_version=schema_version,
            extractor_version=extractor_version,
            raw_output=call_result.raw_output,
            parsed_output=None,
            validation_status=ExtractionValidationStatus.VALIDATION_FAILED,
            validation_errors=["Client output did not parse as a dict matching schema_version."],
            input_tokens=call_result.input_tokens,
            output_tokens=call_result.output_tokens,
            latency_seconds=latency,
            requested_at=now,
        )
        cache.put(key, result.model_dump(mode="json"))
        return result

    result = LLMExtractionResult(
        cache_key=key,
        candidate_id=candidate_id,
        model=model_id,
        prompt_version=prompt_version,
        schema_version=schema_version,
        extractor_version=extractor_version,
        raw_output=call_result.raw_output,
        parsed_output=call_result.parsed_output,
        validation_status=ExtractionValidationStatus.VALIDATED,
        input_tokens=call_result.input_tokens,
        output_tokens=call_result.output_tokens,
        latency_seconds=latency,
        requested_at=now,
    )
    cache.put(key, result.model_dump(mode="json"))
    return result


def extract_tier3_batch(
    items: list[tuple[str, str]],  # (candidate_id, text)
    **kwargs,
) -> list[LLMExtractionResult]:
    """Batch entry point -- calls `extract_tier3` per item, but is the interface callers
    should use so a future batched-client implementation (one HTTP call for many items)
    can be substituted here without changing call sites (§4, "Batching")."""

    return [extract_tier3(candidate_id, text, **kwargs) for candidate_id, text in items]
