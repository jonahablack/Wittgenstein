"""Optional, provider-neutral semantic/NLI comparison interface --
docs/claim-linking-improvement-plan.md §7. Mirrors
`proposition/llm_client.py::LLMClient`/`NullLLMClient` exactly: `NullSemanticProvider`
is the default (always unavailable), so this layer is never required for the no-LLM
baseline or for any test in this pass. Used only *after* programmatic field
comparison, as an additional signal that can raise support/contradiction priority --
never a factual judgment by itself.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Protocol

from wittgenstein.core.enums import SemanticComparisonOutcome
from wittgenstein.ingestion.content_hash import cache_key as compute_cache_key
from wittgenstein.ingestion.kv_cache import KVCache, MemoryKVCache
from wittgenstein.schemas.claim_comparison import SemanticComparisonResult

SCHEMA_VERSION = "semantic-comparison-result-v1"
PROMPT_VERSION = "claim-evidence-comparison-v1"


@dataclass
class SemanticCallResult:
    """What a real SemanticProvider.compare() call returns on success."""

    outcome: SemanticComparisonOutcome
    raw_response: str
    input_tokens: int | None
    output_tokens: int | None


class SemanticProvider(Protocol):
    def is_available(self) -> bool: ...

    def compare(self, claim_text: str, passage_text: str) -> SemanticCallResult: ...


class NullSemanticProvider:
    """Always reports unavailable -- the default, and how the no-LLM/no-semantic-call
    baseline is implemented: not a special case in the caller.
    """

    def is_available(self) -> bool:
        return False

    def compare(self, claim_text: str, passage_text: str) -> SemanticCallResult:
        raise RuntimeError("NullSemanticProvider has no model configured -- call is_available() first.")


def compare_with_semantic_provider(
    claim_text: str,
    passage_text: str,
    *,
    provider: SemanticProvider | None = None,
    cache: KVCache | None = None,
    provider_name: str = "unconfigured",
    model_id: str = "unconfigured",
    normalization_version: str = "1",
    store_raw_response: bool = False,
) -> SemanticComparisonResult:
    """Cache-first, typed-fallback orchestration -- the semantic-layer analogue of
    `proposition/llm_extraction.py::extract_tier3`, reusing the same cache/fallback
    discipline rather than a second implementation of it.
    """

    cache = cache if cache is not None else MemoryKVCache()
    key = compute_cache_key(
        claim_text, passage_text, provider_name, model_id, PROMPT_VERSION, normalization_version
    )

    cached = cache.get(key)
    if cached is not None:
        result = SemanticComparisonResult.model_validate(cached)
        return result.model_copy(update={"from_cache": True})

    now_start = time.perf_counter()
    effective_provider = provider if provider is not None else NullSemanticProvider()

    if not effective_provider.is_available():
        result = SemanticComparisonResult(
            cache_key=key,
            provider=None,
            model=None,
            prompt_version=PROMPT_VERSION,
            schema_version=SCHEMA_VERSION,
            outcome="provider_unavailable",
            validation_errors=["No semantic/NLI provider configured or provider reported unavailable."],
            latency_seconds=time.perf_counter() - now_start,
        )
        cache.put(key, result.model_dump(mode="json"))
        return result

    try:
        call_result = effective_provider.compare(claim_text, passage_text)
    except Exception as exc:  # noqa: BLE001 -- any provider failure must fall back, not propagate
        result = SemanticComparisonResult(
            cache_key=key,
            provider=provider_name,
            model=model_id,
            prompt_version=PROMPT_VERSION,
            schema_version=SCHEMA_VERSION,
            outcome=SemanticComparisonOutcome.PROVIDER_ERROR.value,
            validation_errors=[f"Semantic provider call raised: {exc!r}"],
            latency_seconds=time.perf_counter() - now_start,
        )
        cache.put(key, result.model_dump(mode="json"))
        return result

    result = SemanticComparisonResult(
        cache_key=key,
        provider=provider_name,
        model=model_id,
        prompt_version=PROMPT_VERSION,
        schema_version=SCHEMA_VERSION,
        outcome=call_result.outcome.value,
        raw_response=call_result.raw_response if store_raw_response else None,
        input_tokens=call_result.input_tokens,
        output_tokens=call_result.output_tokens,
        latency_seconds=time.perf_counter() - now_start,
    )
    cache.put(key, result.model_dump(mode="json"))
    return result
