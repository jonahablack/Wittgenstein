"""Deterministic query analysis (docs/live-pipeline-plan.md §4.1).

Breaks the query into what the user is asking about (facets), what must hold exactly
(hard constraints), and what kind of answer is wanted (question type). Every element
keeps its character span in the query, so any probe or flag about it can point at the
exact words it concerns. Rule-based throughout -- nothing here is a model judgment.
"""

from __future__ import annotations

import re
from collections.abc import Callable

from pydantic import BaseModel, ConfigDict, Field

from wittgenstein.core.enums import ConstraintKind, QuestionType
from wittgenstein.live import phrases as P
from wittgenstein.live.nlp import nlp

MAX_FACETS = 4

_WH = {"what", "which", "who", "whom", "whose", "when", "where", "why", "how"}
_STOP = {
    "a", "an", "the", "this", "that", "these", "those", "of", "in", "on", "for", "to", "by", "with", "at",
    "from", "and", "or", "is", "are", "was", "were", "be", "it", "its", "their", "any", "some", "do", "does",
    "did", "there", "i", "we", "you", "me", "my", "our", "your", "they", "them", "he", "she", "his", "her",
    "about", "into", "than", "as", "if", "all", "each", "every", "list", "name", "tell", "explain", "describe",
}  # fmt: skip
_MODAL_STARTS = {"should", "can", "could", "may", "might", "must", "shall", "will", "would", "do", "does", "did"}
_TOKEN = re.compile(r"[A-Za-z0-9][A-Za-z0-9'\-]*")

_NUMBER = re.compile(
    r"\b\d+(?:[.,]\d+)?(?:\s*(?:%|percent|mg|g|kg|ml|l|cm|mm|m|km|days?|weeks?|months?|years?|hours?|minutes?"
    r"|employees|units|dollars|euros?))?\b",
    re.IGNORECASE,
)
_YEAR = re.compile(r"\b(?:1[89]\d{2}|20\d{2}|2100)\b")
_DATE = re.compile(
    r"\b(?:\d{1,2}\s+)?(?:January|February|March|April|May|June|July|August|September|October|November|December)"
    r"(?:\s+\d{1,2})?(?:,?\s+\d{4})?\b|\b\d{4}-\d{2}-\d{2}\b"
)
_IDENTIFIER = re.compile(
    r"(?:§\s*\d+(?:\.\d+)*)|\b(?:[A-Z][a-z]+)\s+(?:[IVX]{1,5}|[A-Z](?:\.\d+)*|\d+(?:\.\d+)*)(?:\(\d+\))?(?:\([a-z]\))?"
    r"(?![a-z])"
)
_QUOTED = re.compile(r"[\"“]([^\"”]{2,80})[\"”]")


class Span(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str
    start: int
    end: int


class QueryConstraint(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: ConstraintKind
    span: Span


class QueryFacet(BaseModel):
    model_config = ConfigDict(extra="forbid")

    facet_id: str
    span: Span
    terms: list[str] = Field(..., description="Lowercased content terms of the facet.")
    weight: float = Field(..., description="Specificity: max corpus IDF of its terms (1.0 when no corpus).")


class QueryAnalysis(BaseModel):
    model_config = ConfigDict(extra="forbid")

    query: str
    question_type: QuestionType
    facets: list[QueryFacet]
    dropped_facets: list[str] = Field(default_factory=list, description="Lower-weight facets beyond MAX_FACETS.")
    constraints: list[QueryConstraint]
    content_terms: list[str]
    enumeration_target: str | None = None

    @property
    def is_multi_facet(self) -> bool:
        return len(self.facets) > 1


_POSSESSIVE = re.compile(r"(?:'s|’s|s'|')$")


def _content_terms(text: str) -> list[str]:
    """Lowercased content words, possessives stripped ("Elizabeth's" -> "elizabeth")."""
    out = []
    for m in _TOKEN.findall(text):
        t = m.lower()
        if t not in _STOP and t not in _WH:
            stripped = _POSSESSIVE.sub("", t) if len(t) > 3 else t
            out.append(stripped or t)
    return out


def _overlaps(a: tuple[int, int], b: tuple[int, int]) -> bool:
    return a[0] < b[1] and b[0] < a[1]


def _constraints(query: str) -> list[QueryConstraint]:
    out: list[QueryConstraint] = []
    taken: list[tuple[int, int]] = []

    def add(kind: ConstraintKind, start: int, end: int) -> None:
        if any(_overlaps((start, end), t) for t in taken):
            return
        taken.append((start, end))
        out.append(QueryConstraint(kind=kind, span=Span(text=query[start:end], start=start, end=end)))

    low = P.lower(query)
    for m in _QUOTED.finditer(query):
        add(ConstraintKind.QUOTED, m.start(), m.end())
    for m in _DATE.finditer(query):
        add(ConstraintKind.DATE, m.start(), m.end())
    for m in _IDENTIFIER.finditer(query):
        add(ConstraintKind.IDENTIFIER, m.start(), m.end())
    for m in _YEAR.finditer(query):
        add(ConstraintKind.DATE, m.start(), m.end())
    for m in _NUMBER.finditer(query):
        add(ConstraintKind.NUMBER, m.start(), m.end())
    for _phrase, s, e in P.phrase_spans(low, P.NEGATION_WORDS + P.EXCLUSION_WORDS):
        add(ConstraintKind.NEGATION, s, e)
    for _phrase, s, e in P.phrase_spans(low, P.COMPARATOR_PHRASES):
        add(ConstraintKind.COMPARATOR, s, e)
    for _phrase, s, e in P.phrase_spans(low, P.MODALITY_PHRASES):
        add(ConstraintKind.MODALITY, s, e)
    return sorted(out, key=lambda c: c.span.start)


def _question_type(low: str) -> QuestionType:
    if P.find_phrases(low, P.COMPARISON_CUES):
        return QuestionType.COMPARISON
    if P.find_phrases(low, P.ENUMERATION_CUES):
        return QuestionType.ENUMERATION
    if P.find_phrases(low, P.EXPLANATION_CUES):
        return QuestionType.EXPLANATION
    if P.find_phrases(low, sorted(_WH)):
        return QuestionType.FACTOID
    return QuestionType.UNKNOWN


def _enumeration_target(query: str, low: str) -> str | None:
    m = re.search(r"\b(?:all|every|each|how many|list(?: all)?(?: the)?|what are the)\s+(.+?)(?:[?.,;]|$)", low)
    if not m:
        return None
    terms = _content_terms(query[m.start(1) : m.end(1)])
    return " ".join(terms[:4]) or None


def analyze_query(query: str, term_weight: Callable[[str], float] | None = None) -> QueryAnalysis:
    """`term_weight` (e.g. the corpus BM25 IDF) ranks facets by specificity; without it
    every term weighs 1.0 and facets keep query order."""
    query = query.strip()
    low = P.lower(query)
    weight = term_weight or (lambda _t: 1.0)

    constraints = _constraints(query)
    idents = [c.span for c in constraints if c.kind == ConstraintKind.IDENTIFIER]
    value_spans = [c.span for c in constraints if c.kind in {ConstraintKind.DATE, ConstraintKind.NUMBER}]

    def facet(start: int, end: int) -> QueryFacet | None:
        while start < end and query[start] in "\"“”'‘’":
            start += 1
        while end > start and query[end - 1] in "\"“”'‘’":
            end -= 1
        terms = _content_terms(query[start:end])
        if not terms:
            return None
        return QueryFacet(
            facet_id="",
            span=Span(text=query[start:end], start=start, end=end),
            terms=terms,
            weight=max(weight(t) for t in terms),
        )

    facets: list[QueryFacet] = []
    from wittgenstein.live.nlp import _CALL_LOCK

    pipeline = nlp()
    with _CALL_LOCK:
        doc = pipeline(query)
    for chunk in doc.noun_chunks:
        toks = [t for t in chunk if t.lower_ not in _WH and t.pos_ not in {"DET", "PRON"}]
        # A chunk can swallow a leading modal or auxiliary ("should adults"); a question
        # part is what is asked about, so those are dropped from its start.
        while toks and (toks[0].pos_ == "AUX" or toks[0].lower_ in _MODAL_STARTS):
            toks = toks[1:]
        if not toks:
            continue
        start, end = toks[0].idx, toks[-1].idx + len(toks[-1].text)
        # A date or bare number is a constraint, not a topic.
        if any(v.start <= start and end <= v.end for v in value_spans):
            continue
        inside = [i for i in idents if _overlaps((start, end), (i.start, i.end))]
        # Absorb an identifier the chunk only partly covers ("Article" -> "Article 3").
        for i in inside:
            start, end = min(start, i.start), max(end, i.end)
        if len(inside) >= 2:
            # "Class R and Class S units": one facet per identifier, each keeping the
            # shared head noun after the last identifier, so a comparison's sides are
            # probed separately.
            head = query[inside[-1].end : end]
            for i in inside:
                f = facet(i.start, i.end)
                if f is not None:
                    terms = f.terms + [t for t in _content_terms(head) if t not in f.terms]
                    facets.append(f.model_copy(update={"terms": terms, "weight": max(weight(t) for t in terms)}))
            continue
        f = facet(start, end)
        if f is not None:
            facets.append(f)
    dropped: list[str] = []
    if len(facets) > MAX_FACETS:
        keep = sorted(range(len(facets)), key=lambda i: (-facets[i].weight, i))[:MAX_FACETS]
        dropped = [f.span.text for i, f in enumerate(facets) if i not in keep]
        facets = [f for i, f in enumerate(facets) if i in keep]
    facets = [f.model_copy(update={"facet_id": f"f{i + 1}"}) for i, f in enumerate(facets)]

    qtype = _question_type(low)
    return QueryAnalysis(
        query=query,
        question_type=qtype,
        facets=facets,
        dropped_facets=dropped,
        constraints=constraints,
        content_terms=list(dict.fromkeys(_content_terms(query))),
        enumeration_target=_enumeration_target(query, low) if qtype == QuestionType.ENUMERATION else None,
    )
