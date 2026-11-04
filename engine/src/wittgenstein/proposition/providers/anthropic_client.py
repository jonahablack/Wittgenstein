"""An optional, opt-in `LLMClient` backed by the Anthropic API
(docs/review-loop-implementation-plan.md §2). Requires the `anthropic` package
(`pip install '.[anthropic]'`) -- imported lazily, inside methods only, so the base
install, the full test suite, and the offline demo never require it.

No provider-specific type (an `anthropic.*` class, exception, or response object)
is imported or referenced anywhere outside this module -- callers only ever see the
generic `proposition.llm_client.LLMCallResult`.

Not exercised against a live API in this pass (no credentials configured in this
environment); covered by unit tests for credential-absence and package-absence
behavior only (tests/unit/test_provider_client.py).
"""

from __future__ import annotations

import json
import os
import re
import time

from wittgenstein.proposition.llm_client import LLMCallResult

_DEFAULT_MODEL = "claude-haiku-4-5-20251001"
_JSON_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)\s*```", re.DOTALL)


def _extract_json_object(raw_text: str) -> dict | None:
    """Best-effort extraction of a JSON object from a model response -- tolerant of a
    ```json fenced block or plain JSON text. Returns None (never a guessed dict) if no
    valid JSON object is found; the caller (extract_tier3) treats a non-dict
    parsed_output as validation_failed, never a silent partial success.
    """

    candidates = [raw_text.strip()]
    fence_match = _JSON_FENCE_RE.search(raw_text)
    if fence_match:
        candidates.insert(0, fence_match.group(1).strip())

    for candidate in candidates:
        try:
            parsed = json.loads(candidate)
        except (ValueError, TypeError):
            continue
        if isinstance(parsed, dict):
            return parsed
    return None


class AnthropicProviderClient:
    """`is_available()` is False whenever either the `anthropic` package is not
    installed or the configured API-key environment variable is unset -- both degrade
    to `extract_tier3`'s existing `llm_unavailable` fallback, never a crash. The API key
    itself is read from the environment at call time only and is never assigned to any
    attribute, return value, or persisted object.
    """

    def __init__(
        self,
        *,
        model: str = _DEFAULT_MODEL,
        api_key_env_var: str = "ANTHROPIC_API_KEY",
        timeout_seconds: float = 30.0,
        max_retries: int = 2,
        store_raw_output: bool = False,
        max_output_tokens: int = 1024,
    ) -> None:
        self._model = model
        self._api_key_env_var = api_key_env_var
        self._timeout_seconds = timeout_seconds
        self._max_retries = max_retries
        self._store_raw_output = store_raw_output
        self._max_output_tokens = max_output_tokens

    def is_available(self) -> bool:
        if not os.environ.get(self._api_key_env_var):
            return False
        try:
            import anthropic  # noqa: F401
        except ImportError:
            return False
        return True

    def _build_client(self):
        import anthropic

        api_key = os.environ.get(self._api_key_env_var)
        if not api_key:
            raise RuntimeError(
                f"AnthropicProviderClient: environment variable {self._api_key_env_var!r} is not set. "
                "Call is_available() before extract()."
            )
        return anthropic.Anthropic(api_key=api_key, timeout=self._timeout_seconds)

    def extract(self, text: str, *, prompt_version: str, schema_version: str) -> LLMCallResult:
        prompt = (
            f"Extract a structured decomposition of the following text as a single JSON "
            f"object (prompt_version={prompt_version}, schema_version={schema_version}). "
            f"Respond with only the JSON object, no other text.\n\nText:\n{text}"
        )

        last_exception: Exception | None = None
        for attempt in range(self._max_retries + 1):
            try:
                client = self._build_client()
                message = client.messages.create(
                    model=self._model,
                    max_tokens=self._max_output_tokens,
                    messages=[{"role": "user", "content": prompt}],
                )
                raw_text = "".join(getattr(block, "text", "") for block in message.content)
                parsed = _extract_json_object(raw_text)
                usage = getattr(message, "usage", None)
                return LLMCallResult(
                    # LLMCallResult.raw_output is a required str -- "" means "not
                    # stored" (store_raw_output=False), distinguishable from a real
                    # empty response only by store_raw_output itself, which the caller
                    # already knows it configured.
                    raw_output=raw_text if self._store_raw_output else "",
                    parsed_output=parsed,
                    input_tokens=getattr(usage, "input_tokens", None) if usage else None,
                    output_tokens=getattr(usage, "output_tokens", None) if usage else None,
                )
            except Exception as exc:  # noqa: BLE001 -- retried here; final failure re-raised for extract_tier3's fallback
                last_exception = exc
                if attempt < self._max_retries:
                    time.sleep(min(0.5 * (attempt + 1), 5.0))
                    continue
        assert last_exception is not None  # loop always either returns or sets this before falling through
        raise last_exception

    def extract_batch(self, texts: list[str], *, prompt_version: str, schema_version: str) -> list[LLMCallResult]:
        return [self.extract(t, prompt_version=prompt_version, schema_version=schema_version) for t in texts]
