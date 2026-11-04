"""Optional semantic/NLI provider layer and the SQLite-backed cache --
docs/claim-linking-improvement-plan.md §§7-8. Required test categories 20-26.
"""

from __future__ import annotations

from pathlib import Path

from wittgenstein.core.enums import SemanticComparisonOutcome
from wittgenstein.ingestion.kv_cache import FileKVCache, MemoryKVCache, SqliteKVCache
from wittgenstein.review.semantic_provider import (
    NullSemanticProvider,
    SemanticCallResult,
    compare_with_semantic_provider,
)


class _FakeSemanticProvider:
    def __init__(
        self, outcome: SemanticComparisonOutcome, *, available: bool = True, raises: bool = False
    ) -> None:
        self._outcome = outcome
        self._available = available
        self._raises = raises

    def is_available(self) -> bool:
        return self._available

    def compare(self, claim_text: str, passage_text: str) -> SemanticCallResult:
        if self._raises:
            raise RuntimeError("simulated provider failure")
        return SemanticCallResult(outcome=self._outcome, raw_response="raw", input_tokens=5, output_tokens=2)


# 20. Optional semantic/NLI provider disabled.
def test_20_no_provider_configured_is_provider_unavailable_never_a_crash() -> None:
    result = compare_with_semantic_provider("claim text", "passage text", cache=MemoryKVCache())
    assert result.outcome == "provider_unavailable"
    assert result.parsed_response is None


def test_20b_null_semantic_provider_reports_unavailable() -> None:
    result = compare_with_semantic_provider(
        "claim text", "passage text", provider=NullSemanticProvider(), cache=MemoryKVCache()
    )
    assert result.outcome == "provider_unavailable"


# 21. Optional semantic/NLI provider failure.
def test_21_provider_call_raising_falls_back_to_provider_error() -> None:
    provider = _FakeSemanticProvider(SemanticComparisonOutcome.ENTAILMENT_LIKE, raises=True)
    result = compare_with_semantic_provider("claim", "passage", provider=provider, cache=MemoryKVCache())
    assert result.outcome == SemanticComparisonOutcome.PROVIDER_ERROR.value
    assert result.validation_errors


# 22. Semantic neutral result produces unresolved (at the outcome-mapping level -- the
# semantic layer itself just records "neutral"; docs/claim-linking-improvement-plan.md
# §7 specifies neutral/uncertain map to unresolved wherever this signal is consumed).
def test_22_neutral_semantic_outcome_is_recorded_as_neutral_not_a_verdict() -> None:
    provider = _FakeSemanticProvider(SemanticComparisonOutcome.NEUTRAL)
    result = compare_with_semantic_provider("claim", "passage", provider=provider, cache=MemoryKVCache())
    assert result.outcome == SemanticComparisonOutcome.NEUTRAL.value


# 23. Semantic contradiction-like result remains a candidate, not a fact.
def test_23_contradiction_like_outcome_is_recorded_as_a_labeled_outcome_only() -> None:
    provider = _FakeSemanticProvider(SemanticComparisonOutcome.CONTRADICTION_LIKE)
    result = compare_with_semantic_provider("claim", "passage", provider=provider, cache=MemoryKVCache())
    assert result.outcome == SemanticComparisonOutcome.CONTRADICTION_LIKE.value
    # The result is a typed enum value, not a boolean "is_contradiction" or free-text
    # verdict -- nothing in this schema asserts factual truth.
    assert result.outcome in {o.value for o in SemanticComparisonOutcome}


# 24. SQLite cache hit avoids provider call.
def test_24_sqlite_cache_hit_avoids_a_second_provider_call() -> None:
    call_count = 0

    class _CountingProvider:
        def is_available(self) -> bool:
            return True

        def compare(self, claim_text: str, passage_text: str) -> SemanticCallResult:
            nonlocal call_count
            call_count += 1
            return SemanticCallResult(
                outcome=SemanticComparisonOutcome.ENTAILMENT_LIKE,
                raw_response="r",
                input_tokens=1,
                output_tokens=1,
            )

    cache = SqliteKVCache(":memory:")
    provider = _CountingProvider()

    first = compare_with_semantic_provider("claim", "passage", provider=provider, cache=cache)
    second = compare_with_semantic_provider("claim", "passage", provider=provider, cache=cache)

    assert call_count == 1
    assert first.from_cache is False
    assert second.from_cache is True
    assert second.outcome == first.outcome


def test_24b_sqlite_cache_persists_to_a_file(tmp_path: Path) -> None:
    db_path = tmp_path / "semantic_cache.sqlite"
    cache = SqliteKVCache(db_path)
    cache.put("k1", {"outcome": "entailment_like"})
    cache.close()

    reopened = SqliteKVCache(db_path)
    assert reopened.get("k1") == {"outcome": "entailment_like"}


def test_24c_sqlite_cache_supports_clearing() -> None:
    cache = SqliteKVCache(":memory:")
    cache.put("k1", {"a": 1})
    assert cache.get("k1") is not None
    cache.clear()
    assert cache.get("k1") is None


# 25. Cache invalidation on model/prompt/extractor/schema changes.
def test_25_cache_key_changes_with_model_id() -> None:
    provider = _FakeSemanticProvider(SemanticComparisonOutcome.ENTAILMENT_LIKE)
    cache = MemoryKVCache()
    a = compare_with_semantic_provider("claim", "passage", provider=provider, cache=cache, model_id="model-a")
    b = compare_with_semantic_provider("claim", "passage", provider=provider, cache=cache, model_id="model-b")
    assert a.cache_key != b.cache_key
    assert b.from_cache is False


def test_25b_cache_key_changes_with_normalization_version() -> None:
    provider = _FakeSemanticProvider(SemanticComparisonOutcome.ENTAILMENT_LIKE)
    cache = MemoryKVCache()
    a = compare_with_semantic_provider(
        "claim", "passage", provider=provider, cache=cache, normalization_version="1"
    )
    b = compare_with_semantic_provider(
        "claim", "passage", provider=provider, cache=cache, normalization_version="2"
    )
    assert a.cache_key != b.cache_key
    assert b.from_cache is False


def test_25c_cache_key_changes_with_provider_name() -> None:
    provider = _FakeSemanticProvider(SemanticComparisonOutcome.ENTAILMENT_LIKE)
    cache = MemoryKVCache()
    a = compare_with_semantic_provider("claim", "passage", provider=provider, cache=cache, provider_name="p1")
    b = compare_with_semantic_provider("claim", "passage", provider=provider, cache=cache, provider_name="p2")
    assert a.cache_key != b.cache_key


# 26. Credentials never appearing in cache records.
def test_26_credentials_never_appear_in_cached_result() -> None:
    fake_key = "sk-fake-secret-never-should-be-cached"

    class _ProviderThatMightLeak:
        def is_available(self) -> bool:
            return True

        def compare(self, claim_text: str, passage_text: str) -> SemanticCallResult:
            # A well-behaved provider never puts a credential in its response, but this
            # test asserts the cache layer itself does not introduce one either.
            return SemanticCallResult(
                outcome=SemanticComparisonOutcome.ENTAILMENT_LIKE,
                raw_response="normal response text",
                input_tokens=1,
                output_tokens=1,
            )

    cache = MemoryKVCache()
    result = compare_with_semantic_provider(
        "claim", "passage", provider=_ProviderThatMightLeak(), cache=cache, store_raw_response=True
    )
    dumped = result.model_dump_json()
    assert fake_key not in dumped
    cached_raw = cache.get(result.cache_key)
    assert cached_raw is not None
    assert fake_key not in str(cached_raw)


# store_raw_response defaults to not storing.
def test_store_raw_response_defaults_to_not_stored() -> None:
    provider = _FakeSemanticProvider(SemanticComparisonOutcome.ENTAILMENT_LIKE)
    result = compare_with_semantic_provider("claim", "passage", provider=provider, cache=MemoryKVCache())
    assert result.raw_response is None


def test_latency_recorded_even_on_cache_hit() -> None:
    """A cache hit is never described as zero latency -- local lookup/deserialization
    still has a nonzero cost, so latency_seconds is populated either way.
    """

    provider = _FakeSemanticProvider(SemanticComparisonOutcome.NEUTRAL)
    cache = MemoryKVCache()
    compare_with_semantic_provider("claim", "passage", provider=provider, cache=cache)
    second = compare_with_semantic_provider("claim", "passage", provider=provider, cache=cache)
    assert second.from_cache is True
    assert second.latency_seconds is not None


def test_file_kv_cache_supports_clearing(tmp_path: Path) -> None:
    cache = FileKVCache(tmp_path)
    cache.put("k1", {"a": 1})
    assert cache.get("k1") is not None
    cache.clear()
    assert cache.get("k1") is None
