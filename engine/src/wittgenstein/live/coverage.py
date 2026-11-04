"""Instruments: facet coverage and cross-channel scores, independent of the pipeline.

The awareness layer measures with its own instruments, whatever the observed pipeline
uses. A semantic-only pipeline is still scored lexically here (to see what keyword
search would have caught that it missed), and a keyword-only pipeline is still scored
semantically. Instrument scores never change what the pipeline retrieved; they are
only used to describe it.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from wittgenstein.live import phrases as P
from wittgenstein.live.characterize import EmbedderProfile
from wittgenstein.live.corpus import UnitSet
from wittgenstein.live.embedding import Embedder
from wittgenstein.live.query import QueryAnalysis, QueryFacet
from wittgenstein.live.retrieve import ChannelScores, _channel, dense_scores, lexical_scores

#: A unit covers a facet "by terms" when it contains at least this share of the facet's
#: content terms (whole-word matches). It covers it "by meaning" when its similarity to
#: the facet alone beats what off-topic phrases reach on this corpus with this model
#: (the measured 90th percentile, live/characterize.py). FALLBACK_MEANING_Z is used only
#: when no profile exists, and is reported as uncalibrated.
TERM_SHARE = 0.6
FALLBACK_MEANING_Z = 3.0


@dataclass
class FacetCoverage:
    covered: bool
    how: str | None  # "terms" | "meaning" | None
    term_share: float
    meaning_z: float | None


@dataclass
class _FacetScores:
    facet: QueryFacet
    dense: ChannelScores | None


class Instruments:
    """Both channels over every unit for the whole query, plus per-facet similarity."""

    def __init__(
        self,
        units: UnitSet,
        analysis: QueryAnalysis,
        embedder: Embedder | None,
        profile: EmbedderProfile | None = None,
    ) -> None:
        self.units = units
        self.profile = profile
        null = profile.null_best_z_phrase if profile else None
        self.meaning_bar = null.p90 if null else FALLBACK_MEANING_Z
        self.meaning_bar_calibrated = null is not None
        self.analysis = analysis
        self.embedder = embedder
        self.pos = {u.unit_id: i for i, u in enumerate(units.units)}
        self.lexical = _channel(lexical_scores(units, analysis.query))
        self.dense: ChannelScores | None = None
        self.query_vector: np.ndarray | None = None
        if embedder is not None:
            sims, self.query_vector = dense_scores(units, embedder, analysis.query)
            self.dense = _channel(sims)
        self._facets: dict[str, _FacetScores] = {}
        for f in analysis.facets:
            fd = None
            if embedder is not None:
                fs, _ = dense_scores(units, embedder, f.span.text)
                fd = _channel(fs)
            self._facets[f.facet_id] = _FacetScores(f, fd)
        self._lower_cache: dict[int, str] = {}

    def lower_text(self, i: int) -> str:
        if i not in self._lower_cache:
            self._lower_cache[i] = P.lower(self.units.units[i].index_text)
        return self._lower_cache[i]

    def facet_coverage(self, unit_id: str, facet_id: str) -> FacetCoverage:
        i = self.pos[unit_id]
        fs = self._facets[facet_id]
        terms = list(dict.fromkeys(fs.facet.terms))
        text = self.lower_text(i)
        share = sum(1 for t in terms if P.contains_word_prefix(text, t)) / len(terms) if terms else 0.0
        mz = fs.dense.z(i) if fs.dense is not None else None
        if share >= TERM_SHARE:
            return FacetCoverage(True, "terms", share, mz)
        if mz is not None and mz >= self.meaning_bar:
            return FacetCoverage(True, "meaning", share, mz)
        return FacetCoverage(False, None, share, mz)

    def facets_covered(self, unit_id: str) -> set[str]:
        return {f.facet_id for f in self.analysis.facets if self.facet_coverage(unit_id, f.facet_id).covered}

    def facet_best(self, facet_id: str, limit: int = 3) -> list[str]:
        """Units most strongly matching the facet alone (by meaning when available)."""
        fs = self._facets[facet_id]
        if fs.dense is not None:
            return [self.units.units[i].unit_id for i in fs.dense.ranking[:limit]]
        terms = fs.facet.terms
        scored = sorted(
            range(len(self.units.units)),
            key=lambda i: (-sum(P.contains_phrase(self.lower_text(i), t) for t in terms), i),
        )
        return [self.units.units[i].unit_id for i in scored[:limit]]

    def idf(self, term: str) -> float:
        return self.units.bm25._idf(term)

    def rare_terms(self, min_idf: float | None = None) -> list[str]:
        """Query terms rarer than the median term in the corpus vocabulary sense: the
        exact-match terms a meaning-based search is most likely to underweight."""
        n = max(len(self.units.units), 2)
        threshold = min_idf if min_idf is not None else math.log(1 + (n - 3 + 0.5) / (3 + 0.5)) * 0.6
        return [t for t in self.analysis.content_terms if self.idf(t) >= threshold and len(t) > 1]


def expected_null_max_z(n: int) -> float:
    """Expected maximum of n independent standard normal draws (leading-order extreme
    value approximation). A best match that is not more extreme than this does not
    stand out from what n unrelated passages would produce by chance."""
    if n < 3:
        return 1.0
    a = math.sqrt(2 * math.log(n))
    return a - (math.log(math.log(n)) + math.log(4 * math.pi)) / (2 * a)
