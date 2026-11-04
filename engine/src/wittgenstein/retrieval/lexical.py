"""A pure-Python, dependency-free BM25 scorer -- the default retrieval baseline
(docs/efficiency-and-processing-architecture.md, "RETRIEVAL"). No embeddings, no LLM,
no external retrieval package: this is deliberately a from-scratch, auditable
implementation of the standard Okapi BM25 formula (Robertson & Walker, as widely
reimplemented; not asserted as any specific paper's exact evaluated variant), so a
demo corpus never requires network access or a model download for baseline retrieval.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from typing import Protocol


class _Indexable(Protocol):
    """Anything with an id and text -- a `SourceSegment`, or a live retrieval unit."""

    segment_id: str
    text: str

_TOKEN_RE = re.compile(r"[a-z0-9]+")

_K1 = 1.5
_B = 0.75


def tokenize(text: str) -> list[str]:
    return _TOKEN_RE.findall(text.lower())


@dataclass
class RetrievalCandidate:
    segment_id: str
    score: float
    rank: int


class BM25Index:
    """Built once per corpus (or corpus slice); `search` is O(query terms * postings),
    no re-tokenization of the corpus per query.
    """

    def __init__(self, segments: list[_Indexable]) -> None:
        self._segments = {s.segment_id: s for s in segments}
        self._doc_tokens: dict[str, list[str]] = {s.segment_id: tokenize(s.text) for s in segments}
        self._doc_lengths: dict[str, int] = {sid: len(toks) for sid, toks in self._doc_tokens.items()}
        self._avg_doc_length = (
            sum(self._doc_lengths.values()) / len(self._doc_lengths) if self._doc_lengths else 0.0
        )
        self._postings: dict[str, dict[str, int]] = {}  # term -> {segment_id: term_frequency}
        for sid, toks in self._doc_tokens.items():
            counts: dict[str, int] = {}
            for tok in toks:
                counts[tok] = counts.get(tok, 0) + 1
            for tok, tf in counts.items():
                self._postings.setdefault(tok, {})[sid] = tf
        self._n_docs = len(segments)

    def _idf(self, term: str) -> float:
        df = len(self._postings.get(term, {}))
        if df == 0:
            return 0.0
        # Standard BM25 idf with a +1 floor so common-but-not-universal terms don't go negative.
        return math.log(1 + (self._n_docs - df + 0.5) / (df + 0.5))

    def search(self, query: str, top_k: int = 10) -> list[RetrievalCandidate]:
        query_terms = tokenize(query)
        scores: dict[str, float] = {}
        for term in query_terms:
            idf = self._idf(term)
            if idf == 0.0:
                continue
            for sid, tf in self._postings.get(term, {}).items():
                doc_len = self._doc_lengths[sid]
                denom = tf + _K1 * (1 - _B + _B * doc_len / (self._avg_doc_length or 1))
                scores[sid] = scores.get(sid, 0.0) + idf * (tf * (_K1 + 1)) / (denom or 1)

        ranked = sorted(scores.items(), key=lambda kv: (-kv[1], kv[0]))[:top_k]
        return [
            RetrievalCandidate(segment_id=sid, score=score, rank=i + 1) for i, (sid, score) in enumerate(ranked)
        ]

    def segment(self, segment_id: str) -> _Indexable:
        return self._segments[segment_id]
