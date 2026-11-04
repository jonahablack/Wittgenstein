"""Behavioral characterization of an embedding model (docs/live-pipeline-plan.md §3.2).

The live pipeline must work on top of embedders it has never seen, so nothing here
relies on what a model is *supposed* to do. Each property is measured by probing the
model with controlled inputs built from the corpus's own text, and recorded in an
`EmbedderProfile`. Query-time probes (live/probes.py) judge a measurement against this
model's own baseline, never against a universal threshold.

Every measurement is deterministic for a given (model, corpus): sampling is by even
spacing, never random.
"""

from __future__ import annotations

import re
import threading
from datetime import UTC, datetime

import numpy as np
from pydantic import BaseModel, ConfigDict, Field

from wittgenstein.core.enums import ConstraintKind, EmbedderFamily
from wittgenstein.live.corpus import LiveCorpus
from wittgenstein.live.embedding import Embedder

METHOD_VERSION = "characterize-1"

#: Prefix lengths (words) at which the input window is probed.
_WINDOW_PROBE_WORDS = [16, 32, 64, 96, 128, 192, 256, 320, 384, 448, 512, 640, 768, 1024, 1536, 2048]
#: Vectors this close are treated as identical (float32 noise floor, well below any
#: real content change).
_IDENTICAL_COS = 0.99995
_DILUTION_CONTEXT_WORDS = [0, 25, 50, 100, 200, 400]


#: A baseline with fewer examples than this is reported as insufficient, never used.
MIN_BASELINE_N = 8

#: Neutral sentences that contain negatable verbs, numbers and identifiers. Used only to
#: top up an edit kind the corpus itself cannot supply enough examples of (a novel has
#: few identifiers); every baseline records how many examples came from here.
TEMPLATE_SENTENCES = [
    "The operator must submit the report within 30 days of the inspection.",
    "Applicants with more than 12 employees are required to register under Section 4.",
    "The device is approved for use in Class B environments.",
    "Patients receiving 50 mg daily should be monitored for side effects.",
    "The committee meets 4 times a year to review Article 9 compliance.",
    "The fee is 250 dollars for applications filed after 2021.",
    "Units in Zone C may operate for up to 8 hours without inspection.",
    "The bridge was closed for 6 weeks while engineers repaired Pier 3.",
    "Students who complete Module 2 can enroll in the advanced course.",
    "The contract requires delivery of 400 units before the end of Quarter 2.",
    "She arrived at the station 20 minutes before the train left Platform 5.",
    "The warranty covers repairs for 24 months under Plan A.",
    "Tenants are permitted to keep 2 pets in Building D.",
    "The trial enrolled 180 participants across Site 7 and Site 8.",
    "The vessel can carry 35 passengers when operating in Region E.",
    "Employees will receive a bonus of 5 percent under Policy 11.",
]


class Spread(BaseModel):
    model_config = ConfigDict(extra="forbid")

    n: int
    template_n: int = Field(default=0, description="How many of the n examples came from TEMPLATE_SENTENCES.")
    p10: float
    p50: float
    p90: float
    mean: float

    @classmethod
    def of(cls, values: list[float]) -> Spread | None:
        if not values:
            return None
        a = np.asarray(values, dtype=np.float64)
        return cls(
            n=len(values),
            p10=float(np.percentile(a, 10)),
            p50=float(np.percentile(a, 50)),
            p90=float(np.percentile(a, 90)),
            mean=float(a.mean()),
        )


class WindowMeasurement(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: str = Field(..., description="saturated | no_saturation_observed | insufficient_text")
    effective_window_tokens: int | None = Field(
        default=None, description="Smallest probed length past which the vector stopped changing."
    )
    lower_bound_tokens: int | None = Field(
        default=None, description="Largest probed length that still changed the vector."
    )
    probed_up_to_tokens: int


class EmbedderProfile(BaseModel):
    """Measured behavior of one embedding model on one corpus."""

    model_config = ConfigDict(extra="forbid")

    embedder_id: str
    model_identifier: str
    family: EmbedderFamily
    dimension: int
    declared_max_input_tokens: int | None
    corpus_id: str
    window: WindowMeasurement
    insufficient_baselines: list[str] = Field(
        default_factory=list, description=f"Edit kinds with fewer than {MIN_BASELINE_N} examples -- not used."
    )
    edit_shift_baselines: dict[str, Spread] = Field(
        default_factory=dict,
        description="Per edit kind (ConstraintKind values plus 'content_word'): distribution of "
        "1 - cosine(sentence, edited sentence) over corpus sentences.",
    )
    dilution_curve: dict[int, float] = Field(
        default_factory=dict,
        description="Context words around a sentence -> mean cosine(sentence alone, sentence in context).",
    )
    pairwise_similarity: Spread | None = Field(
        default=None, description="Cosine between evenly spaced unit pairs: this model's similarity geometry."
    )
    measured_at: datetime
    method_version: str = METHOD_VERSION


_WORD = re.compile(r"\S+")
_AUX = re.compile(
    r"\b(is|are|was|were|shall|must|may|can|will|does|do|did|has|have|had|should|would|could)\b", re.IGNORECASE
)
_NEG = re.compile(r"\s+(not|never)\b|n't\b", re.IGNORECASE)
_NUMBER = re.compile(r"\b\d+(?:\.\d+)?\b")
_IDENT = re.compile(r"\b([A-Z][a-z]+)\s+([A-Z]|\d+(?:\.\d+)*|[IVX]+)\b")
_STOP = frozenset(
    [
        "the",
        "a",
        "an",
        "and",
        "or",
        "of",
        "to",
        "in",
        "on",
        "for",
        "by",
        "with",
        "as",
        "at",
        "from",
        "that",
        "this",
        "these",
        "those",
        "is",
        "are",
        "was",
        "were",
        "be",
        "been",
        "it",
        "its",
        "their",
        "his",
        "her",
        "they",
        "he",
        "she",
        "we",
        "you",
        "i",
        "not",
        "no",
        "shall",
        "must",
        "may",
        "can",
        "will",
    ]
)


def _sentences(corpus: LiveCorpus, limit: int) -> list[str]:
    pool = [s for u in corpus.units().units for s, _, _ in u.sentences if 6 <= len(s.split()) <= 60]
    if len(pool) <= limit:
        return pool
    step = len(pool) / limit
    return [pool[int(i * step)] for i in range(limit)]


def edit_sentence(sentence: str, kind: str) -> str | None:
    """One controlled minimal edit of `kind`, or None if the sentence offers none.
    Public because query-time probes apply the same edits to the query."""
    if kind == ConstraintKind.NEGATION.value:
        if _NEG.search(sentence):
            return _NEG.sub("", sentence, count=1)
        m = _AUX.search(sentence)
        return f"{sentence[: m.end()]} not{sentence[m.end() :]}" if m else None
    if kind == ConstraintKind.NUMBER.value:
        m = _NUMBER.search(sentence)
        if not m:
            return None
        value = m.group(0)
        changed = str(int(float(value)) * 2 + 3) if "." not in value else f"{float(value) * 2 + 3:g}"
        return sentence[: m.start()] + changed + sentence[m.end() :]
    if kind == ConstraintKind.IDENTIFIER.value:
        m = _IDENT.search(sentence)
        if not m:
            return None
        tail = m.group(2)
        swapped = (
            str(int(tail) + 7)
            if tail.isdigit()
            else ("Q" if tail != "Q" and len(tail) == 1 else ("VII" if tail != "VII" else "IX"))
        )
        return sentence[: m.start(2)] + swapped + sentence[m.end(2) :]
    if kind == "content_word":
        words = [w for w in _WORD.findall(sentence) if w.strip(".,;:()\"'").lower() not in _STOP]
        if not words:
            return None
        target = max(words, key=len)
        return re.sub(rf"\s*{re.escape(target)}", "", sentence, count=1)
    return None


_EDIT_KINDS = [
    ConstraintKind.NEGATION.value,
    ConstraintKind.NUMBER.value,
    ConstraintKind.IDENTIFIER.value,
    "content_word",
]


def _measure_window(embedder: Embedder, corpus: LiveCorpus) -> WindowMeasurement:
    words: list[str] = []
    for u in corpus.units().units:
        words.extend(u.text.split())
        if len(words) >= _WINDOW_PROBE_WORDS[-1]:
            break
    lengths = [n for n in _WINDOW_PROBE_WORDS if n <= len(words)]
    if len(lengths) < 3:
        return WindowMeasurement(
            status="insufficient_text", probed_up_to_tokens=embedder.count_tokens(" ".join(words))
        )
    prefixes = [" ".join(words[:n]) for n in lengths]
    vecs = embedder.embed(prefixes)
    tokens = [embedder.count_tokens(p) for p in prefixes]
    final = vecs[-1]
    # Saturated at index i if every prefix from i onward is identical to the longest.
    sat_index = None
    for i in range(len(lengths) - 1):
        if all(float(vecs[j] @ final) >= _IDENTICAL_COS for j in range(i, len(lengths))):
            sat_index = i
            break
    if sat_index is None or sat_index == 0:
        return WindowMeasurement(
            status="no_saturation_observed" if sat_index is None else "saturated",
            effective_window_tokens=None if sat_index is None else tokens[0],
            probed_up_to_tokens=tokens[-1],
        )
    # Refine between the last changing length and the first saturated one.
    lo, hi = lengths[sat_index - 1], lengths[sat_index]
    while hi - lo > 4:
        mid = (lo + hi) // 2
        v = embedder.embed([" ".join(words[:mid])])[0]
        if float(v @ final) >= _IDENTICAL_COS:
            hi = mid
        else:
            lo = mid
    return WindowMeasurement(
        status="saturated",
        effective_window_tokens=embedder.count_tokens(" ".join(words[:hi])),
        lower_bound_tokens=embedder.count_tokens(" ".join(words[:lo])),
        probed_up_to_tokens=tokens[-1],
    )


def _pairs(sentences: list[str], kind: str) -> list[tuple[str, str]]:
    return [(s, e) for s in sentences if (e := edit_sentence(s, kind)) and e != s]


def _measure_edit_shifts(embedder: Embedder, sentences: list[str]) -> tuple[dict[str, Spread], list[str]]:
    out: dict[str, Spread] = {}
    insufficient: list[str] = []
    for kind in _EDIT_KINDS:
        pairs = _pairs(sentences, kind)
        template_n = 0
        if len(pairs) < MIN_BASELINE_N:
            extra = _pairs(TEMPLATE_SENTENCES, kind)
            template_n = len(extra)
            pairs += extra
        if len(pairs) < MIN_BASELINE_N:
            insufficient.append(kind)
            continue
        a = embedder.embed([p[0] for p in pairs])
        b = embedder.embed([p[1] for p in pairs])
        spread = Spread.of([float(1.0 - x) for x in np.sum(a * b, axis=1)])
        if spread is not None:
            out[kind] = spread.model_copy(update={"template_n": template_n})
    return out, insufficient


def _measure_dilution(embedder: Embedder, corpus: LiveCorpus, sentences: list[str]) -> dict[int, float]:
    filler: list[str] = []
    for u in reversed(corpus.units().units):
        filler.extend(u.text.split())
        if len(filler) >= 2 * _DILUTION_CONTEXT_WORDS[-1]:
            break
    targets = sentences[:: max(1, len(sentences) // 10)][:10]
    if not targets or len(filler) < _DILUTION_CONTEXT_WORDS[1] * 2:
        return {}
    curve: dict[int, float] = {}
    base = embedder.embed(targets)
    for n in _DILUTION_CONTEXT_WORDS:
        half = min(n // 2, len(filler) // 2)
        before, after = " ".join(filler[:half]), " ".join(filler[half : 2 * half])
        texts = [f"{before} {t} {after}".strip() for t in targets]
        v = embedder.embed(texts)
        curve[n] = float(np.mean(np.sum(base * v, axis=1)))
    return curve


def _measure_pairwise(embedder: Embedder, corpus: LiveCorpus, max_pairs: int = 400) -> Spread | None:
    vecs = corpus.units().vectors(embedder)
    n = len(vecs)
    if n < 3:
        return None
    pairs = [(i, (i * 7 + n // 2) % n) for i in range(0, n, max(1, n // max_pairs))]
    sims = [float(vecs[i] @ vecs[j]) for i, j in pairs if i != j]
    return Spread.of(sims)


def characterize(embedder: Embedder, corpus: LiveCorpus) -> EmbedderProfile:
    sentences = _sentences(corpus, limit=48)
    baselines, insufficient = _measure_edit_shifts(embedder, sentences)
    return EmbedderProfile(
        embedder_id=embedder.info.embedder_id,
        model_identifier=embedder.info.model_identifier,
        family=embedder.info.family,
        dimension=embedder.info.dimension,
        declared_max_input_tokens=embedder.info.max_input_tokens,
        corpus_id=corpus.corpus_id,
        window=_measure_window(embedder, corpus),
        edit_shift_baselines=baselines,
        insufficient_baselines=insufficient,
        dilution_curve=_measure_dilution(embedder, corpus, sentences),
        pairwise_similarity=_measure_pairwise(embedder, corpus),
        measured_at=datetime.now(UTC),
    )


_PROFILES: dict[tuple[str, str], EmbedderProfile] = {}
_LOCK = threading.Lock()


def get_profile(embedder: Embedder, corpus: LiveCorpus) -> EmbedderProfile:
    key = (embedder.info.embedder_id, corpus.corpus_id)
    with _LOCK:
        if key in _PROFILES:
            return _PROFILES[key]
    profile = characterize(embedder, corpus)
    with _LOCK:
        return _PROFILES.setdefault(key, profile)
