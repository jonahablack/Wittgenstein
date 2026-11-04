"""Embedding backends for the live pipeline (docs/live-pipeline-plan.md §3.1).

Embedding is a declared pipeline stage: every backend states its family, dimension,
and input limit, because the awareness probes (live/probes.py) interpret their
measurements relative to exactly those properties. Vectors are always L2-normalized,
so a dot product is a cosine similarity.
"""

from __future__ import annotations

import hashlib
import re
import threading
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

import numpy as np

from wittgenstein.core.enums import EmbedderFamily


@dataclass(frozen=True)
class EmbedderInfo:
    embedder_id: str
    model_identifier: str
    family: EmbedderFamily
    dimension: int
    max_input_tokens: int | None
    """`None` means the model has no input window (static models embed any length);
    never a guessed default."""
    token_counting_method: str


@runtime_checkable
class Embedder(Protocol):
    info: EmbedderInfo

    def embed(self, texts: list[str]) -> np.ndarray:
        """Return an (n, dimension) float32 array of L2-normalized vectors."""
        ...

    def count_tokens(self, text: str) -> int:
        """Tokens as *this model* counts them, for input-window truncation checks."""
        ...


def _counting_tokenizer(tokenizer):  # noqa: ANN001,ANN202 -- a `tokenizers.Tokenizer`
    """A copy of a model's tokenizer with truncation and padding switched off, so token
    counts are real lengths. Counting with the model's own (truncating) tokenizer would
    cap every count at the window and hide exactly the truncation we need to detect."""
    from tokenizers import Tokenizer

    clone = Tokenizer.from_str(tokenizer.to_str())
    clone.no_truncation()
    clone.no_padding()
    return clone


def _declared_window(tokenizer) -> int | None:  # noqa: ANN001
    """The truncation length a model's tokenizer is configured with, if any. Recorded as
    *declared*; live/characterize.py measures the effective window independently."""
    trunc = getattr(tokenizer, "truncation", None)
    return int(trunc["max_length"]) if trunc and trunc.get("max_length") else None


def _normalize(vectors: np.ndarray) -> np.ndarray:
    vectors = np.asarray(vectors, dtype=np.float32)
    norms = np.linalg.norm(vectors, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    return vectors / norms


class Model2VecEmbedder:
    """Static (distilled) embeddings: fast on CPU and mean-pooled, so a long passage's
    vector is an average that a single relevant sentence can be diluted in (probe D4).
    Note: model2vec's tokenizer is configured to truncate (512 tokens by default) -- an
    assumption that static models have no window was wrong, and was caught by the
    window measurement in live/characterize.py."""

    def __init__(self, model_identifier: str = "minishlab/potion-retrieval-32M") -> None:
        from model2vec import StaticModel

        self._model = StaticModel.from_pretrained(model_identifier)
        dim = int(self._model.encode(["probe"]).shape[1])
        self._counter = _counting_tokenizer(self._model.tokenizer)
        self.info = EmbedderInfo(
            embedder_id=f"model2vec:{model_identifier}",
            model_identifier=model_identifier,
            family=EmbedderFamily.STATIC,
            dimension=dim,
            max_input_tokens=_declared_window(self._model.tokenizer),
            token_counting_method="model_tokenizer_untruncated",
        )

    def embed(self, texts: list[str]) -> np.ndarray:
        if not texts:
            return np.zeros((0, self.info.dimension), dtype=np.float32)
        return _normalize(self._model.encode(texts))

    def count_tokens(self, text: str) -> int:
        return len(self._counter.encode(text, add_special_tokens=False).ids)


class FastEmbedEmbedder:
    """Contextual ONNX embeddings (optional `quality` extra). Has a fixed input window:
    text past it is not seen by the model at all (probe D3)."""

    def __init__(self, model_identifier: str = "BAAI/bge-small-en-v1.5") -> None:
        from fastembed import TextEmbedding

        self._model = TextEmbedding(model_name=model_identifier)
        dim = int(np.asarray(next(iter(self._model.embed(["probe"])))).shape[0])
        tokenizer = getattr(getattr(self._model, "model", None), "tokenizer", None)
        self._counter = _counting_tokenizer(tokenizer) if tokenizer is not None else None
        self.info = EmbedderInfo(
            embedder_id=f"fastembed:{model_identifier}",
            model_identifier=model_identifier,
            family=EmbedderFamily.CONTEXTUAL,
            dimension=dim,
            max_input_tokens=_declared_window(tokenizer) if tokenizer is not None else None,
            token_counting_method="model_tokenizer_untruncated" if self._counter else "whitespace_x1.3_estimate",
        )

    def embed(self, texts: list[str]) -> np.ndarray:
        """Batches are padded to their longest member, so texts are embedded in length
        order (similar lengths share a batch) and returned in the caller's order."""
        if not texts:
            return np.zeros((0, self.info.dimension), dtype=np.float32)
        order = sorted(range(len(texts)), key=lambda i: len(texts[i]))
        vectors = list(self._model.embed([texts[i] for i in order], batch_size=32))
        out = np.empty((len(texts), self.info.dimension), dtype=np.float32)
        for slot, i in enumerate(order):
            out[i] = np.asarray(vectors[slot], dtype=np.float32)
        return _normalize(out)

    def count_tokens(self, text: str) -> int:
        if self._counter is not None:
            return len(self._counter.encode(text, add_special_tokens=False).ids)
        return int(len(text.split()) * 1.3)


_WORD_RE = re.compile(r"[a-z0-9]+")


class HashingEmbedder:
    """Deterministic, non-semantic feature hashing of word unigrams. TEST ONLY: it lets
    probes be tested on cases whose correct outcome is known by construction (e.g. this
    model provably ignores a word it never sees), with no model download. Every manifest
    built with it says so via `EmbedderFamily.HASHING_TEST_ONLY`."""

    def __init__(self, dimension: int = 256, ignored_words: frozenset[str] = frozenset()) -> None:
        self._ignored = ignored_words
        self.info = EmbedderInfo(
            embedder_id=f"hashing:{dimension}",
            model_identifier="feature-hashing-unigram",
            family=EmbedderFamily.HASHING_TEST_ONLY,
            dimension=dimension,
            max_input_tokens=None,
            token_counting_method="regex_words",
        )

    def _vector(self, text: str) -> np.ndarray:
        v = np.zeros(self.info.dimension, dtype=np.float32)
        for word in _WORD_RE.findall(text.lower()):
            if word in self._ignored:
                continue
            h = int.from_bytes(hashlib.blake2b(word.encode(), digest_size=8).digest(), "little")
            v[h % self.info.dimension] += 1.0 if (h >> 63) & 1 else -1.0
        return v

    def embed(self, texts: list[str]) -> np.ndarray:
        if not texts:
            return np.zeros((0, self.info.dimension), dtype=np.float32)
        return _normalize(np.vstack([self._vector(t) for t in texts]))

    def count_tokens(self, text: str) -> int:
        return len(_WORD_RE.findall(text.lower()))


class CachingEmbedder:
    """Wraps any embedder with a content-hash vector cache, so a corpus is embedded once
    per model and repeated query-time embeddings (probes re-embed query variants) are
    free. Thread-safe: the live runner embeds from worker threads."""

    def __init__(self, inner: Embedder) -> None:
        self._inner = inner
        self.info = inner.info
        self._cache: dict[str, np.ndarray] = {}
        self._lock = threading.Lock()

    @staticmethod
    def _key(text: str) -> str:
        return hashlib.sha256(text.encode()).hexdigest()

    def embed(self, texts: list[str]) -> np.ndarray:
        keys = [self._key(t) for t in texts]
        with self._lock:
            missing = sorted({k: t for k, t in zip(keys, texts, strict=True) if k not in self._cache}.items())
        if missing:
            vectors = self._inner.embed([t for _, t in missing])
            with self._lock:
                for (k, _), v in zip(missing, vectors, strict=True):
                    self._cache[k] = v
        if not texts:
            return np.zeros((0, self.info.dimension), dtype=np.float32)
        with self._lock:
            return np.vstack([self._cache[k] for k in keys])

    def count_tokens(self, text: str) -> int:
        return self._inner.count_tokens(text)


_REGISTRY: dict[str, Embedder] = {}
_REGISTRY_LOCK = threading.Lock()

#: Selectable embedders by short name. Loading is lazy and memoized per process.
EMBEDDER_CHOICES = {
    "potion-retrieval": ("model2vec", "minishlab/potion-retrieval-32M"),
    "potion-base": ("model2vec", "minishlab/potion-base-8M"),
    "bge-small": ("fastembed", "BAAI/bge-small-en-v1.5"),
    "hashing-test": ("hashing", "256"),
}
DEFAULT_EMBEDDER = "potion-retrieval"


def get_embedder(name: str = DEFAULT_EMBEDDER) -> Embedder:
    if name not in EMBEDDER_CHOICES:
        raise ValueError(f"Unknown embedder {name!r}; choose one of {sorted(EMBEDDER_CHOICES)}")
    with _REGISTRY_LOCK:
        if name not in _REGISTRY:
            backend, ident = EMBEDDER_CHOICES[name]
            inner: Embedder
            if backend == "model2vec":
                inner = Model2VecEmbedder(ident)
            elif backend == "fastembed":
                inner = FastEmbedEmbedder(ident)
            else:
                inner = HashingEmbedder(int(ident))
            _REGISTRY[name] = CachingEmbedder(inner)
        return _REGISTRY[name]
