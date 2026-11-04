"""Claude answer provider (optional `anthropic` extra).

Streams with `client.beta.messages.stream` so the server-side refusal fallback can be
enabled (`fallbacks="default"`, beta `server-side-fallback-2026-07-01`): if a request is
declined by a safety classifier, the API re-runs it on Anthropic's recommended fallback
model inside the same call. The final message's `stop_reason` is still checked, since
the fallback can decline too.

Model: `claude-opus-5-5` by default; override with WITTGENSTEIN_CLAUDE_MODEL. Effort is
set explicitly to `medium` (grounded question answering over a few passages).
"""

from __future__ import annotations

import os
from collections.abc import Iterator

from wittgenstein.live.generate import SYSTEM_PROMPT, ContextPassage, ProviderError, ProviderInfo, user_prompt

DEFAULT_MODEL = "claude-opus-5-5"


class ClaudeProvider:
    def __init__(self, model: str | None = None) -> None:
        import anthropic

        self._anthropic = anthropic
        self._client = anthropic.Anthropic()
        self._model = model or os.environ.get("WITTGENSTEIN_CLAUDE_MODEL", DEFAULT_MODEL)
        self.info = ProviderInfo("claude", "Claude", self._model, True)

    def stream(self, question: str, passages: list[ContextPassage]) -> Iterator[str]:
        a = self._anthropic
        try:
            with self._client.beta.messages.stream(
                model=self._model,
                max_tokens=16000,
                system=SYSTEM_PROMPT,
                output_config={"effort": "medium"},
                betas=["server-side-fallback-2026-07-01"],
                fallbacks="default",
                messages=[{"role": "user", "content": user_prompt(question, passages)}],
            ) as stream:
                yield from stream.text_stream
                final = stream.get_final_message()
            if final.stop_reason == "refusal":
                category = getattr(final.stop_details, "category", None) if final.stop_details else None
                raise ProviderError(
                    f"Claude declined to answer this request (category: {category or 'unspecified'})."
                )
            if final.stop_reason == "max_tokens":
                yield " [answer truncated at the length limit]"
        except a.AuthenticationError as e:
            raise ProviderError("Claude credentials were rejected.") from e
        except a.RateLimitError as e:
            raise ProviderError("Claude is rate-limiting requests; try again shortly.") from e
        except a.APIStatusError as e:
            raise ProviderError(f"Claude API error ({e.status_code}).") from e
        except a.APIConnectionError as e:
            raise ProviderError("Couldn't reach the Claude API.") from e
