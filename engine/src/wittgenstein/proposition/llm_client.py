"""LLM client interface for Tier-3 extraction. `NullLLMClient` (always unavailable) is
the default -- this is what makes the no-LLM demo mode and the general fallback
behavior (docs/efficiency-and-processing-architecture.md §7) the *same* code path as
the "LLM configured" path, not a separate branch that could silently diverge.

No real provider-backed client is implemented in this pass (no API credentials
configured) -- see docs/efficiency-and-processing-architecture.md §8. A real client
only needs to satisfy this Protocol.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass
class LLMCallResult:
    """What a real LLMClient.extract() call returns on success. Kept separate from
    `schemas.proposition.LLMExtractionResult`, which additionally carries cache/
    provenance bookkeeping the client itself doesn't know about (cache_key, from_cache).
    """

    raw_output: str
    parsed_output: dict | None
    input_tokens: int | None
    output_tokens: int | None


class LLMClient(Protocol):
    """Any real client (OpenAI, Anthropic, a local model server, ...) satisfies this by
    implementing `is_available` and `extract`/`extract_batch`. `requests_per_minute` is
    accepted for rate-limit awareness but only a real client enforces it (§4).
    """

    def is_available(self) -> bool: ...

    def extract(self, text: str, *, prompt_version: str, schema_version: str) -> LLMCallResult: ...

    def extract_batch(
        self, texts: list[str], *, prompt_version: str, schema_version: str
    ) -> list[LLMCallResult]: ...


class NullLLMClient:
    """Always reports unavailable. This is the default client, and is exactly how the
    no-LLM demo mode is implemented -- not a special case in the caller.
    """

    def is_available(self) -> bool:
        return False

    def extract(self, text: str, *, prompt_version: str, schema_version: str) -> LLMCallResult:
        raise RuntimeError("NullLLMClient has no model configured -- call is_available() first.")

    def extract_batch(self, texts: list[str], *, prompt_version: str, schema_version: str) -> list[LLMCallResult]:
        raise RuntimeError("NullLLMClient has no model configured -- call is_available() first.")


class FakeLLMClient:
    """A deterministic, non-network test double -- never used in the demo or in
    production, only in tests that need to exercise the "LLM available and returns a
    valid result" path without a real API call. `responses` maps input text to a
    parsed_output dict.
    """

    def __init__(self, responses: dict[str, dict], *, fail_on: set[str] | None = None) -> None:
        self._responses = responses
        self._fail_on = fail_on or set()

    def is_available(self) -> bool:
        return True

    def extract(self, text: str, *, prompt_version: str, schema_version: str) -> LLMCallResult:
        if text in self._fail_on:
            return LLMCallResult(raw_output="{malformed", parsed_output=None, input_tokens=10, output_tokens=0)
        parsed = self._responses.get(text)
        return LLMCallResult(
            raw_output=str(parsed),
            parsed_output=parsed,
            input_tokens=len(text.split()),
            output_tokens=len(parsed) if parsed else 0,
        )

    def extract_batch(self, texts: list[str], *, prompt_version: str, schema_version: str) -> list[LLMCallResult]:
        return [self.extract(t, prompt_version=prompt_version, schema_version=schema_version) for t in texts]
