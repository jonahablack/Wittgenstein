"""AnthropicProviderClient: credential/package-absence behavior, typed fallback via
extract_tier3, and that no credential ever appears in persisted output
(docs/review-loop-implementation-plan.md §2, §6). Test categories 3, 4, 5.

None of these tests require the `anthropic` package to be installed or make a network
call -- that is exactly the point being tested.
"""

from __future__ import annotations

import os

import pytest
from wittgenstein.core.enums import ExtractionValidationStatus
from wittgenstein.proposition.llm_extraction import extract_tier3


def test_module_imports_without_anthropic_package_installed() -> None:
    # If this import fails, the provider module is doing a module-level `import
    # anthropic` instead of a lazy one -- exactly what must not happen.
    from wittgenstein.proposition.providers.anthropic_client import AnthropicProviderClient

    AnthropicProviderClient()  # construction alone must never require the package


def test_is_available_false_when_no_api_key_set(monkeypatch: pytest.MonkeyPatch) -> None:
    from wittgenstein.proposition.providers.anthropic_client import AnthropicProviderClient

    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    client = AnthropicProviderClient()
    assert client.is_available() is False


def test_is_available_false_with_custom_env_var_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    from wittgenstein.proposition.providers.anthropic_client import AnthropicProviderClient

    monkeypatch.delenv("MY_CUSTOM_KEY", raising=False)
    client = AnthropicProviderClient(api_key_env_var="MY_CUSTOM_KEY")
    assert client.is_available() is False


def test_extract_tier3_falls_back_when_provider_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    from wittgenstein.proposition.providers.anthropic_client import AnthropicProviderClient

    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    client = AnthropicProviderClient()

    result = extract_tier3("cand1", "some answer text", client=client)
    assert result.validation_status == ExtractionValidationStatus.LLM_UNAVAILABLE
    assert result.parsed_output is None


def test_extract_raises_when_called_without_available_check(monkeypatch: pytest.MonkeyPatch) -> None:
    """extract() itself does not silently no-op -- callers must go through
    extract_tier3 (or check is_available() themselves) for the typed-fallback
    guarantee; calling extract() directly on an unconfigured client raises, which
    extract_tier3's own try/except is what converts to the typed fallback.
    """

    from wittgenstein.proposition.providers.anthropic_client import AnthropicProviderClient

    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    client = AnthropicProviderClient(max_retries=0)
    with pytest.raises(Exception):  # noqa: B017, PT011 -- exact exception type depends on the (absent) package
        client.extract("text", prompt_version="v1", schema_version="v1")


def test_api_key_never_appears_in_extract_tier3_result(monkeypatch: pytest.MonkeyPatch) -> None:
    from wittgenstein.proposition.providers.anthropic_client import AnthropicProviderClient

    fake_key = "sk-ant-test-secret-value-should-never-leak"
    monkeypatch.setenv("ANTHROPIC_API_KEY", fake_key)
    client = AnthropicProviderClient(max_retries=0)  # package still not installed -> raises -> typed fallback

    result = extract_tier3("cand1", "some text", client=client)
    dumped = result.model_dump_json()
    assert fake_key not in dumped
    assert os.environ["ANTHROPIC_API_KEY"] == fake_key  # confirm the env var itself was actually set for this test


def test_store_raw_output_defaults_to_not_stored() -> None:
    from wittgenstein.proposition.providers.anthropic_client import AnthropicProviderClient

    client = AnthropicProviderClient()
    assert client._store_raw_output is False  # noqa: SLF001 -- verifying the documented default directly


def test_extract_tier3_falls_back_when_call_itself_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    """Distinct from `is_available()` returning False up front: here the client
    reports available (key set) but the underlying call raises mid-flight (in this
    environment, because the `anthropic` package is not installed) -- extract_tier3's
    own try/except must still convert that into the same typed fallback, not propagate
    the exception to the caller.
    """

    from wittgenstein.proposition.providers.anthropic_client import AnthropicProviderClient

    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-fake-for-this-test-only")
    client = AnthropicProviderClient(max_retries=0)

    result = extract_tier3("cand1", "some answer text", client=client)
    assert result.validation_status == ExtractionValidationStatus.LLM_UNAVAILABLE
    assert result.parsed_output is None
    assert result.validation_errors
