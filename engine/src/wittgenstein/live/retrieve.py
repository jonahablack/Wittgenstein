"""Retrieval channels and fusion (docs/live-pipeline-plan.md §§4, 7).

Lexical (BM25) and dense scores are computed for *every* unit, not just the top hits,
so each score can be expressed as a z-score against this query's own score distribution
over the corpus. That puts the two channels on one scale and makes "how unusually close
is this passage" comparable across embedding models whose raw cosines are not
(characterization showed one model's unrelated passages averaging 0.15 and another's 0.58).
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field

import numpy as np

from wittgenstein.core.enums import RetrievalChannel
from wittgenstein.live.corpus import UnitSet
from wittgenstein.live.embedding import Embedder
from wittgenstein.live.pipelines import PipelineSpec
from wittgenstein.live.query import QueryAnalysis

RRF_K = 60
FACET_DEPTH = 8
#: Facet hits count half as much as whole-query hits in fusion: a facet search is a
#: deliberate widening of the pool, not a stronger signal of relevance.
FACET_FUSION_WEIGHT = 0.5


@dataclass
class Candidate:
    unit_id: str
    channels: set[RetrievalChannel] = field(default_factory=set)
    lexical_rank: int | None = None
    lexical_score: float | None = None
    lexical_z: float | None = None
    dense_rank: int | None = None
    dense_sim: float | None = None
    dense_z: float | None = None
    facet_hits: dict[str, int] = field(default_factory=dict)
    fused_score: float = 0.0
    fused_rank: int = 0

    @property
    def relevance_z(self) -> float:
        """The strongest evidence of relevance from any channel that saw this unit."""
        zs = [z for z in (self.lexical_z, self.dense_z) if z is not None]
        return max(zs) if zs else 0.0


@dataclass
class ChannelScores:
    """One channel's scores over every unit, plus the distribution they are z-scored by."""

    scores: np.ndarray
    ranking: list[int]
    mean: float
    std: float

    def z(self, i: int) -> float:
        return float((self.scores[i] - self.mean) / self.std) if self.std > 0 else 0.0

    def rank_of(self, i: int) -> int:
        return int(self._rank_lookup[i])

    def __post_init__(self) -> None:
        self._rank_lookup = np.empty(len(self.ranking), dtype=np.int64)
        for r, i in enumerate(self.ranking):
            self._rank_lookup[i] = r + 1


@dataclass
class RetrievalResult:
    pool: list[Candidate]
    by_id: dict[str, Candidate]
    lexical: ChannelScores | None
    dense: ChannelScores | None
    query_vector: np.ndarray | None
    facet_rankings: dict[str, list[str]]
    timings_ms: dict[str, float]


def _channel(scores: np.ndarray, zero_means_absent: bool = False) -> ChannelScores:
    order = sorted(range(len(scores)), key=lambda i: (-float(scores[i]), i))
    return ChannelScores(scores=scores, ranking=order, mean=float(scores.mean()), std=float(scores.std()))


def lexical_scores(units: UnitSet, text: str) -> np.ndarray:
    scores = np.zeros(len(units.units), dtype=np.float64)
    pos = {u.unit_id: i for i, u in enumerate(units.units)}
    for hit in units.bm25.search(text, top_k=len(units.units)):
        scores[pos[hit.segment_id]] = hit.score
    return scores


def dense_scores(units: UnitSet, embedder: Embedder, text: str) -> tuple[np.ndarray, np.ndarray]:
    qv = embedder.embed([text])[0]
    return units.vectors(embedder) @ qv, qv


def retrieve(
    spec: PipelineSpec, units: UnitSet, analysis: QueryAnalysis, embedder: Embedder | None
) -> RetrievalResult:
    timings: dict[str, float] = {}
    n = len(units.units)
    lex: ChannelScores | None = None
    den: ChannelScores | None = None
    qv: np.ndarray | None = None

    t = time.perf_counter()
    if spec.uses_lexical:
        lex = _channel(lexical_scores(units, analysis.query))
    timings["retrieve.lexical"] = (time.perf_counter() - t) * 1000

    t = time.perf_counter()
    if spec.uses_dense and embedder is not None:
        sims, qv = dense_scores(units, embedder, analysis.query)
        den = _channel(sims)
    timings["retrieve.dense"] = (time.perf_counter() - t) * 1000

    cands: dict[int, Candidate] = {}

    def cand(i: int) -> Candidate:
        if i not in cands:
            cands[i] = Candidate(unit_id=units.units[i].unit_id)
        return cands[i]

    depth = min(spec.candidate_depth, n)
    if lex is not None:
        for r, i in enumerate(lex.ranking[:depth]):
            if lex.scores[i] <= 0:
                break  # no query-term overlap at all: not a lexical hit
            c = cand(i)
            c.channels.add(RetrievalChannel.LEXICAL)
            c.fused_score += 1.0 / (RRF_K + r + 1)
    if den is not None:
        for r, i in enumerate(den.ranking[:depth]):
            c = cand(i)
            c.channels.add(RetrievalChannel.DENSE)
            c.fused_score += 1.0 / (RRF_K + r + 1)

    t = time.perf_counter()
    facet_rankings: dict[str, list[str]] = {}
    if spec.facet_queries and analysis.is_multi_facet:
        for f in analysis.facets:
            fused: dict[int, float] = {}
            parts: list[list[int]] = []
            if embedder is not None:
                fs, _ = dense_scores(units, embedder, f.span.text)
                parts.append(np.argsort(-fs, kind="stable")[:FACET_DEPTH].tolist())
            fl = lexical_scores(units, f.span.text)
            parts.append([i for i in np.argsort(-fl, kind="stable")[:FACET_DEPTH].tolist() if fl[i] > 0])
            for ranking in parts:
                for r, i in enumerate(ranking):
                    fused[i] = fused.get(i, 0.0) + 1.0 / (RRF_K + r + 1)
            order = sorted(fused, key=lambda i: (-fused[i], i))[:FACET_DEPTH]
            facet_rankings[f.facet_id] = [units.units[i].unit_id for i in order]
            for r, i in enumerate(order):
                c = cand(i)
                c.channels.add(RetrievalChannel.FACET)
                c.facet_hits[f.facet_id] = r + 1
                c.fused_score += FACET_FUSION_WEIGHT / (RRF_K + r + 1)
    timings["retrieve.facets"] = (time.perf_counter() - t) * 1000

    for i, c in cands.items():
        if lex is not None:
            c.lexical_rank, c.lexical_score, c.lexical_z = lex.rank_of(i), float(lex.scores[i]), lex.z(i)
        if den is not None:
            c.dense_rank, c.dense_sim, c.dense_z = den.rank_of(i), float(den.scores[i]), den.z(i)

    pool = sorted(cands.values(), key=lambda c: (-c.fused_score, c.unit_id))
    for r, c in enumerate(pool):
        c.fused_rank = r + 1
    return RetrievalResult(
        pool=pool,
        by_id={c.unit_id: c for c in pool},
        lexical=lex,
        dense=den,
        query_vector=qv,
        facet_rankings=facet_rankings,
        timings_ms=timings,
    )
