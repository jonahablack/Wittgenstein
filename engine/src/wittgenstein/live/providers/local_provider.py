"""Open-weights answer provider: any server speaking the OpenAI-compatible Chat
Completions API (mlx_lm.server, llama.cpp's llama-server, vLLM, Ollama's /v1).

Configure with WITTGENSTEIN_LOCAL_LLM_URL (the base URL, e.g. http://127.0.0.1:8200/v1)
and optionally WITTGENSTEIN_LOCAL_LLM_MODEL. Like embedding callbacks, the URL must be
on this machine unless WITTGENSTEIN_ALLOW_REMOTE_LLM=1. Decoding is greedy
(temperature 0) so a run can be reproduced.
"""

from __future__ import annotations

import json
import os
from collections.abc import Iterator
from urllib.parse import urlparse

import httpx

from wittgenstein.live.generate import SYSTEM_PROMPT, ContextPassage, ProviderError, ProviderInfo, user_prompt

_LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1"}
MAX_TOKENS = 500


def local_url() -> str | None:
    url = os.environ.get("WITTGENSTEIN_LOCAL_LLM_URL", "").strip().rstrip("/")
    return url or None


def local_url_allowed(url: str) -> bool:
    p = urlparse(url)
    if p.scheme not in {"http", "https"} or not p.hostname:
        return False
    return p.hostname in _LOCAL_HOSTS or os.environ.get("WITTGENSTEIN_ALLOW_REMOTE_LLM") == "1"


class LocalProvider:
    def __init__(self, base_url: str | None = None, model: str | None = None, timeout: float = 120.0) -> None:
        url = base_url or local_url()
        if not url:
            raise ProviderError("No local model configured (set WITTGENSTEIN_LOCAL_LLM_URL).")
        if not local_url_allowed(url):
            raise ProviderError(
                "The local model URL must be on this machine unless WITTGENSTEIN_ALLOW_REMOTE_LLM=1."
            )
        self._url = url.rstrip("/") + "/chat/completions"
        self._model = model or os.environ.get("WITTGENSTEIN_LOCAL_LLM_MODEL", "local")
        self._timeout = timeout
        self.info = ProviderInfo("local", "Open-weights model (local)", self._model, True)

    def complete(self, system: str, user: str, max_tokens: int = MAX_TOKENS) -> str:
        """One non-streamed completion (used by probes that regenerate an answer)."""
        return "".join(self._stream(system, user, max_tokens))

    def stream(self, question: str, passages: list[ContextPassage]) -> Iterator[str]:
        yield from self._stream(SYSTEM_PROMPT, user_prompt(question, passages), MAX_TOKENS)

    def _stream(self, system: str, user: str, max_tokens: int) -> Iterator[str]:
        body = {
            "model": self._model,
            "stream": True,
            "temperature": 0,
            "max_tokens": max_tokens,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
        }
        try:
            with httpx.stream("POST", self._url, json=body, timeout=self._timeout) as r:
                if r.status_code >= 400:
                    raise ProviderError(f"The local model server returned an error ({r.status_code}).")
                for line in r.iter_lines():
                    if not line.startswith("data:"):
                        continue
                    data = line[5:].strip()
                    if data == "[DONE]":
                        break
                    try:
                        chunk = json.loads(data)
                    except json.JSONDecodeError:
                        continue
                    choices = chunk.get("choices") or []
                    delta = (choices[0].get("delta") or {}).get("content") if choices else None
                    if delta:
                        yield delta
        except httpx.HTTPError as e:
            raise ProviderError("Couldn't reach the local model server.") from e
