"""OpenAI answer provider (optional `openai` extra), via streaming Chat Completions --
the same API and default model (`gpt-4o-mini`) the original Wittgenstein app used.
Override the model with WITTGENSTEIN_OPENAI_MODEL.
"""

from __future__ import annotations

import os
from collections.abc import Iterator

from wittgenstein.live.generate import SYSTEM_PROMPT, ContextPassage, ProviderError, ProviderInfo, user_prompt

DEFAULT_MODEL = "gpt-4o-mini"


class OpenAIProvider:
    def __init__(self, model: str | None = None) -> None:
        import openai

        self._openai = openai
        self._client = openai.OpenAI()
        self._model = model or os.environ.get("WITTGENSTEIN_OPENAI_MODEL", DEFAULT_MODEL)
        self.info = ProviderInfo("openai", "OpenAI", self._model, True)

    def stream(self, question: str, passages: list[ContextPassage]) -> Iterator[str]:
        o = self._openai
        try:
            chunks = self._client.chat.completions.create(
                model=self._model,
                stream=True,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt(question, passages)},
                ],
            )
            for chunk in chunks:
                if chunk.choices and chunk.choices[0].delta and chunk.choices[0].delta.content:
                    yield chunk.choices[0].delta.content
        except o.AuthenticationError as e:
            raise ProviderError("OpenAI credentials were rejected.") from e
        except o.RateLimitError as e:
            raise ProviderError("OpenAI is rate-limiting requests; try again shortly.") from e
        except o.APIStatusError as e:
            raise ProviderError(f"OpenAI API error ({e.status_code}).") from e
        except o.APIConnectionError as e:
            raise ProviderError("Couldn't reach the OpenAI API.") from e
