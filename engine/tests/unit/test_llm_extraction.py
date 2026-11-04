"""Tier-3 orchestration: cache reuse/invalidation, graceful fallback on an unavailable
or failing client, and batch processing
(docs/efficiency-and-processing-architecture.md §§3, 7).
"""

from __future__ import annotations

from wittgenstein.core.enums import ExtractionValidationStatus
from wittgenstein.ingestion.kv_cache import MemoryKVCache
from wittgenstein.proposition.llm_client import FakeLLMClient, NullLLMClient
from wittgenstein.proposition.llm_extraction import extract_tier3, extract_tier3_batch


def test_no_client_falls_back_to_llm_unavailable_never_raises() -> None:
    result = extract_tier3("cand1", "some text", client=None)
    assert result.validation_status == ExtractionValidationStatus.LLM_UNAVAILABLE
    assert result.parsed_output is None


def test_null_client_falls_back_identically_to_no_client() -> None:
    result = extract_tier3("cand1", "some text", client=NullLLMClient())
    assert result.validation_status == ExtractionValidationStatus.LLM_UNAVAILABLE
    assert result.parsed_output is None


def test_client_exception_falls_back_without_raising() -> None:
    class RaisingClient:
        def is_available(self) -> bool:
            return True

        def extract(self, text, *, prompt_version, schema_version):
            raise RuntimeError("simulated provider failure")

        def extract_batch(self, texts, *, prompt_version, schema_version):
            raise RuntimeError("simulated provider failure")

    result = extract_tier3("cand1", "some text", client=RaisingClient())
    assert result.validation_status == ExtractionValidationStatus.LLM_UNAVAILABLE
    assert result.parsed_output is None
    assert result.validation_errors


def test_malformed_output_is_validation_failed_not_a_guess() -> None:
    client = FakeLLMClient(responses={}, fail_on={"bad text"})
    result = extract_tier3("cand1", "bad text", client=client)
    assert result.validation_status == ExtractionValidationStatus.VALIDATION_FAILED
    assert result.parsed_output is None


def test_successful_call_is_cached_and_reused() -> None:
    cache = MemoryKVCache()
    client = FakeLLMClient(responses={"hello": {"decomposed": ["hello"]}})

    first = extract_tier3("cand1", "hello", client=client, cache=cache, model_id="model-a")
    second = extract_tier3("cand1", "hello", client=client, cache=cache, model_id="model-a")

    assert first.from_cache is False
    assert second.from_cache is True
    assert second.parsed_output == first.parsed_output


def test_cache_key_changes_with_model_id() -> None:
    cache = MemoryKVCache()
    client = FakeLLMClient(responses={"hello": {"decomposed": ["hello"]}})

    a = extract_tier3("cand1", "hello", client=client, cache=cache, model_id="model-a")
    b = extract_tier3("cand1", "hello", client=client, cache=cache, model_id="model-b")

    assert a.cache_key != b.cache_key
    assert b.from_cache is False


def test_cache_key_changes_with_prompt_version() -> None:
    cache = MemoryKVCache()
    client = FakeLLMClient(responses={"hello": {"decomposed": ["hello"]}})

    a = extract_tier3("cand1", "hello", client=client, cache=cache, prompt_version="p1")
    b = extract_tier3("cand1", "hello", client=client, cache=cache, prompt_version="p2")

    assert a.cache_key != b.cache_key
    assert b.from_cache is False


def test_cache_key_changes_with_extractor_version() -> None:
    cache = MemoryKVCache()
    client = FakeLLMClient(responses={"hello": {"decomposed": ["hello"]}})

    a = extract_tier3("cand1", "hello", client=client, cache=cache, extractor_version="e1")
    b = extract_tier3("cand1", "hello", client=client, cache=cache, extractor_version="e2")

    assert a.cache_key != b.cache_key
    assert b.from_cache is False


def test_extract_tier3_batch_processes_every_item() -> None:
    client = FakeLLMClient(responses={"a": {"x": 1}, "b": {"x": 2}})
    results = extract_tier3_batch([("cand1", "a"), ("cand2", "b")], client=client)
    assert [r.candidate_id for r in results] == ["cand1", "cand2"]
    assert all(r.validation_status == ExtractionValidationStatus.VALIDATED for r in results)
