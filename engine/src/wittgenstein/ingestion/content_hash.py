"""Content-addressed hashing, shared by corpus-time document caching and the Tier-3 LLM
cache -- one hashing scheme, not two (docs/efficiency-and-processing-architecture.md
§3, and CLAUDE.md's "avoid two lists/tables describing the same category" rule).
"""

from __future__ import annotations

import hashlib


def content_hash(text: str) -> str:
    """sha256 of UTF-8 encoded text, hex-encoded. Used for both raw-document hashing
    (SourceDocument.content_hash) and as one component of the LLM cache key.
    """

    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def cache_key(*parts: str) -> str:
    """A stable, order-sensitive composite key from named parts, e.g.
    `cache_key(source_text, extractor_version, model_id, prompt_version, schema_version)`.
    Each part is length-prefixed before joining so that no ambiguous concatenation
    (e.g. ("ab", "c") vs ("a", "bc")) can collide.
    """

    joined = "\x1f".join(f"{len(p)}:{p}" for p in parts)
    return hashlib.sha256(joined.encode("utf-8")).hexdigest()
