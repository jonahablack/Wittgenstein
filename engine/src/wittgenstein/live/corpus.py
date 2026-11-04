"""LiveCorpus: parsed documents -> retrieval units, indexes, and layout positions.

A corpus is parsed once with the engine's deterministic parser (offsets and provenance
preserved), then cut into *retrieval units* by a declared chunker. Different pipelines
may chunk differently, so units, the BM25 index, and per-embedder vectors are cached per
chunker. Every unit keeps its document offsets so any flag can point at exact source text.
"""

from __future__ import annotations

import re
import threading
from dataclasses import dataclass, field

import numpy as np

from wittgenstein.core.enums import SegmentType
from wittgenstein.ingestion.corpus_index import CorpusIndex, index_corpus
from wittgenstein.ingestion.parser import split_sentences
from wittgenstein.live.embedding import Embedder
from wittgenstein.retrieval.lexical import BM25Index
from wittgenstein.schemas.corpus_profile import CorpusProfile
from wittgenstein.schemas.proposition import SourceSegment
from wittgenstein.trace.token_counting import TokenCounter, default_counter

_RETRIEVABLE = {SegmentType.PARAGRAPH, SegmentType.LIST_ITEM, SegmentType.TABLE_ROW}
_HEADING_MAX_WORDS = 6
_TERMINAL_PUNCT = (".", "?", "!", ":", ";", ")", '"', "'")

STRUCTURAL = "structural"


@dataclass
class Unit:
    unit_id: str
    order: int
    document_id: str
    text: str
    char_start: int
    char_end: int
    location: str
    heading_context: str | None
    segment_ids: list[str]
    token_count: int
    position: float
    """Fraction [0, 1) of the way through the whole corpus (documents in order) -- the
    angular coordinate of the evidence-field layout."""
    prev_id: str | None = None
    next_id: str | None = None
    sentences: list[tuple[str, int, int]] = field(default_factory=list)

    @property
    def index_text(self) -> str:
        """What retrieval actually indexes: the heading context (when present) followed
        by the passage. Declared in the manifest as the index unit."""
        return f"{self.heading_context}\n{self.text}" if self.heading_context else self.text


@dataclass
class _LexDoc:
    segment_id: str
    text: str


def _is_heading_like(seg: SourceSegment) -> bool:
    words = seg.text.split()
    return len(words) <= _HEADING_MAX_WORDS and not seg.text.rstrip().endswith(_TERMINAL_PUNCT)


def parse_chunker(spec: str) -> tuple[str, int, int]:
    """`structural` or `window:<words>:<overlap_words>`."""
    if spec == STRUCTURAL:
        return STRUCTURAL, 0, 0
    parts = spec.split(":")
    if len(parts) == 3 and parts[0] == "window":
        size, overlap = int(parts[1]), int(parts[2])
        if size <= 0 or not 0 <= overlap < size:
            raise ValueError(f"Invalid window chunker {spec!r}")
        return "window", size, overlap
    raise ValueError(f"Unknown chunker {spec!r}; use 'structural' or 'window:<words>:<overlap>'")


_DEF_HEADING_RE = re.compile(r"\bdefinition\b[^:]*:\s*(?P<term>.+)$", re.IGNORECASE)
_DEF_MEANS_RE = re.compile(
    r"(?:^|[.;]\s+)[\"“‘']?(?P<term>[A-Za-z][\w\- ]{1,60}?)[\"”’']?\s+"
    r"(?:means|shall mean|refers to|is defined as|has the meaning)\b"
)
_DEF_ARTICLE_RE = re.compile(r"^(?:an?|the)\s+(?P<term>[A-Za-z][\w\- ]{1,60}?)\s+(?:is|are)\s+(?:an?|the)\b", re.I)


class UnitSet:
    """All units for one (corpus, chunker), plus the indexes built over them."""

    def __init__(self, chunker: str, units: list[Unit]) -> None:
        self.chunker = chunker
        self.units = units
        self.by_id = {u.unit_id: u for u in units}
        self.bm25 = BM25Index([_LexDoc(u.unit_id, u.index_text) for u in units])
        self._vectors: dict[str, np.ndarray] = {}
        self._sentence_vectors: dict[tuple[str, str], np.ndarray] = {}
        self._lock = threading.Lock()
        self.definitions = self._find_definitions()

    def vectors(self, embedder: Embedder) -> np.ndarray:
        key = embedder.info.embedder_id
        with self._lock:
            cached = self._vectors.get(key)
        if cached is None:
            cached = embedder.embed([u.index_text for u in self.units])
            with self._lock:
                self._vectors[key] = cached
        return cached

    def sentence_vectors(self, embedder: Embedder, unit_id: str) -> np.ndarray:
        key = (embedder.info.embedder_id, unit_id)
        with self._lock:
            cached = self._sentence_vectors.get(key)
        if cached is None:
            cached = embedder.embed([s for s, _, _ in self.by_id[unit_id].sentences])
            with self._lock:
                self._sentence_vectors[key] = cached
        return cached

    def _find_definitions(self) -> dict[str, list[str]]:
        """term (lowercased) -> ids of units that define it. Three recognized forms:
        a 'Definition ...: TERM' heading context; 'TERM means/is defined as/...';
        and 'A TERM is a ...' -- the last only inside a definitions section, since in
        ordinary prose it is just a sentence."""
        found: dict[str, list[str]] = {}

        def add(term: str, unit_id: str) -> None:
            term = term.strip().strip("\"'“”‘’").lower()
            if len(term) >= 3 and unit_id not in found.setdefault(term, []):
                found[term].append(unit_id)

        for u in self.units:
            heading = u.heading_context or ""
            in_definitions = "definition" in heading.lower()
            m = _DEF_HEADING_RE.search(heading.splitlines()[-1]) if heading else None
            if m:
                add(m.group("term"), u.unit_id)
            for m2 in _DEF_MEANS_RE.finditer(u.text):
                add(m2.group("term"), u.unit_id)
            if in_definitions:
                m3 = _DEF_ARTICLE_RE.match(u.text)
                if m3:
                    add(m3.group("term"), u.unit_id)
        return found


def _structural_units(
    doc_ids: list[str], index: CorpusIndex, counter: TokenCounter, offsets: dict[str, int], total: int
) -> list[Unit]:
    units: list[Unit] = []
    for doc_id in doc_ids:
        segs = sorted(
            (
                s
                for s in index.segments_for_document(doc_id)
                if s.segment_type in _RETRIEVABLE or s.segment_type == SegmentType.HEADING
            ),
            key=lambda s: s.char_start,
        )
        # Heading context = the latest markdown heading plus any short heading-like
        # paragraphs since it ("Article 2" / "Classification requirement"). It persists
        # for every passage in the section; a heading-like paragraph that follows body
        # text starts a new sub-section.
        md_heading: str | None = None
        sub: list[str] = []
        last_was_body = False
        for seg in segs:
            if seg.segment_type == SegmentType.HEADING:
                md_heading, sub, last_was_body = seg.text.strip().lstrip("#").strip(), [], False
                continue
            if seg.segment_type == SegmentType.PARAGRAPH and _is_heading_like(seg):
                if last_was_body:
                    sub = []
                sub = [*sub, seg.text.strip()][-3:]
                last_was_body = False
                continue
            last_was_body = True
            headings = [h for h in [md_heading, *sub] if h]
            units.append(
                Unit(
                    unit_id=seg.segment_id,
                    order=len(units),
                    document_id=doc_id,
                    text=seg.text,
                    char_start=seg.char_start,
                    char_end=seg.char_end,
                    location=seg.location,
                    heading_context="\n".join(headings) or None,
                    segment_ids=[seg.segment_id],
                    token_count=counter.count(seg.text),
                    position=(offsets[doc_id] + seg.char_start) / total,
                    sentences=split_sentences(seg.text),
                )
            )
    return units


def _window_units(
    doc_ids: list[str],
    index: CorpusIndex,
    counter: TokenCounter,
    offsets: dict[str, int],
    total: int,
    size: int,
    overlap: int,
    texts: dict[str, str],
) -> list[Unit]:
    """Fixed-size word windows built from whole sentences, crossing paragraph
    boundaries -- the classic chunker whose boundaries ignore document structure."""
    units: list[Unit] = []
    for doc_id in doc_ids:
        sents: list[tuple[str, int, int, str]] = []
        for seg in sorted(index.segments_for_document(doc_id), key=lambda s: s.char_start):
            if seg.segment_type not in _RETRIEVABLE:
                continue
            for text, start, end in split_sentences(seg.text):
                sents.append((text, seg.char_start + start, seg.char_start + end, seg.segment_id))
        i = 0
        n = 0
        while i < len(sents):
            j, words = i, 0
            while j < len(sents) and (words == 0 or words + len(sents[j][0].split()) <= size):
                words += len(sents[j][0].split())
                j += 1
            chunk = sents[i:j]
            start, end = chunk[0][1], chunk[-1][2]
            text = texts[doc_id][start:end]
            n += 1
            units.append(
                Unit(
                    unit_id=f"{doc_id}-w{n}",
                    order=len(units),
                    document_id=doc_id,
                    text=text,
                    char_start=start,
                    char_end=end,
                    location=f"Window {n}",
                    heading_context=None,
                    segment_ids=list(dict.fromkeys(s[3] for s in chunk)),
                    token_count=counter.count(text),
                    position=(offsets[doc_id] + start) / total,
                    sentences=split_sentences(text),
                )
            )
            if j >= len(sents):
                break
            # step back by whole sentences until `overlap` words are repeated
            back, k = 0, j
            while k > i + 1 and back < overlap:
                k -= 1
                back += len(sents[k][0].split())
            i = k if back and k > i else j
    return units


class LiveCorpus:
    def __init__(self, corpus_id: str, documents: dict[str, str], titles: dict[str, str] | None = None) -> None:
        if not documents:
            raise ValueError("A corpus needs at least one document.")
        self.corpus_id = corpus_id
        self.documents = dict(documents)
        self.titles = titles or {}
        self.index = index_corpus(self.documents, corpus_id)
        self.counter = default_counter()
        self._unit_sets: dict[str, UnitSet] = {}
        self._lock = threading.Lock()
        self.doc_ids = list(self.documents)
        self._offsets: dict[str, int] = {}
        running = 0
        for d in self.doc_ids:
            self._offsets[d] = running
            running += len(self.documents[d]) + 1
        self._total = max(running, 1)

    @property
    def profile(self) -> CorpusProfile | None:
        return self.index.corpus_profile

    def units(self, chunker: str = STRUCTURAL) -> UnitSet:
        with self._lock:
            if chunker in self._unit_sets:
                return self._unit_sets[chunker]
        kind, size, overlap = parse_chunker(chunker)
        if kind == STRUCTURAL:
            units = _structural_units(self.doc_ids, self.index, self.counter, self._offsets, self._total)
        else:
            units = _window_units(
                self.doc_ids, self.index, self.counter, self._offsets, self._total, size, overlap, self.documents
            )
        for prev, nxt in zip(units, units[1:], strict=False):
            if prev.document_id == nxt.document_id:
                prev.next_id, nxt.prev_id = nxt.unit_id, prev.unit_id
        unit_set = UnitSet(chunker, units)
        with self._lock:
            self._unit_sets.setdefault(chunker, unit_set)
            return self._unit_sets[chunker]
