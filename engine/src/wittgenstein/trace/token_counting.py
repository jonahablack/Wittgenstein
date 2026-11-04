"""Token counting used by the context packer. Uses `tiktoken` (a transitive dependency
via `llama-index-core`) when available for an accurate count; falls back to a documented
word-count-based approximation otherwise -- never silently substitutes one for the
other without saying which was used (`TokenCounter.method`).
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class TokenCounter:
    method: str

    def count(self, text: str) -> int:
        raise NotImplementedError


class TiktokenCounter(TokenCounter):
    def __init__(self, encoding_name: str = "cl100k_base") -> None:
        import tiktoken

        self._encoding = tiktoken.get_encoding(encoding_name)
        super().__init__(method=f"tiktoken:{encoding_name}")

    def count(self, text: str) -> int:
        return len(self._encoding.encode(text))


class ApproximateCounter(TokenCounter):
    """~4 characters per token, the commonly cited English-text approximation.
    Documented as approximate -- never presented as an exact count.
    """

    def __init__(self) -> None:
        super().__init__(method="approximate_chars_div_4")

    def count(self, text: str) -> int:
        return max(1, len(text) // 4) if text else 0


def default_counter() -> TokenCounter:
    try:
        return TiktokenCounter()
    except Exception:  # noqa: BLE001 -- any tiktoken load failure falls back, never crashes packing
        return ApproximateCounter()
