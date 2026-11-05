"""Was each part of the question answered from the passage that answers it?

Published work on RAG failures finds that the damage from extra context comes mostly
from *hard distractors*: passages that look like the answer but aren't (Jin et al.,
ICLR 2025; Amiraz et al. 2025, "The Distracting Effect"). Trimming the context is a
blunt response (measured here: on 40 held-out questions it fixed 2 answers and broke
4). This check looks at the answer instead: for each part of the question it finds
the passage in the prompt that answers that part in the form asked, finds the passage
each part of the answer was taken from, and flags a mismatch, naming both.

The motivating case (Asteria manual): "...and who counts as a registered operator?"
The prompt held Definition D-04 ("A registered operator is a natural or legal person
who has completed registration under Article 5"); the answer was taken from Article
5(4) ("A registered operator is subject to the renewal obligation ... only if ..."),
which mentions registered operators but doesn't say who they are.

Deterministic and conservative: a part is checked only when its form is recognized
(a definition, an amount, a frequency), an answering sentence exists in the prompt,
and the answer's clause clearly restates some other sentence. Every flag quotes both.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from wittgenstein.core.enums import CheckOutcome, FlagDisposition, FlagKind, FlagOrigin, FlagSeverity
from wittgenstein.live import phrases as P
from wittgenstein.live.flags import FlagCollector
from wittgenstein.live.generate import ContextPassage
from wittgenstein.live.quantities import checkable, frequencies, quantities
from wittgenstein.retrieval.lexical import tokenize

_SPLIT = re.compile(
    r",?\s+and\s+(?=(?:what|who|which|when|how|where|is|are|does|do|can|should|must)\b)|;\s+", re.IGNORECASE
)
_DEFINE = re.compile(
    r"^(?:who|what)\s+(?:counts?\s+as|qualifies\s+as|is\s+considered(?:\s+to\s+be)?|is\s+meant\s+by|"
    r"is\s+defined\s+as|is|are)\s+(?:an?\s+|the\s+)?(?P<term>[^?]+?)\s*\??$",
    re.IGNORECASE,
)
_MEANS = re.compile(r"^what\s+does\s+(?:an?\s+|the\s+)?(?P<term>.+?)\s+mean\??$", re.IGNORECASE)
_AMOUNT_WORDS = (
    "dose", "dosage", "margin", "range", "fee", "rate", "level", "altitude", "duration", "limit", "maximum",
    "minimum", "threshold", "amount", "concentration", "interval", "target", "price", "distance", "time",
)  # fmt: skip
_HOW_MUCH = re.compile(
    r"^(?:how\s+(?:much|many|long|high|low|far)|what\s+(?:is|are|was)?\s*(?:the\s+)?(?:\w+[\s-]+){0,3}?(?:"
    + "|".join(_AMOUNT_WORDS)
    + r")s?)\b",
    re.IGNORECASE,
)
_HOW_OFTEN = re.compile(r"^how\s+(?:often|frequently)\b", re.IGNORECASE)
_STOP = {"what", "who", "which", "how", "is", "are", "the", "a", "an", "of", "for", "to", "in", "does", "do",
         "must",
         "should", "can", "be", "counts", "count", "as", "much", "many", "often", "applies", "apply", "on", "with",
         "when", "at", "by"}  # fmt: skip
#: "Class S", "Article 5(4)", "Tier 2", "category Amber": a class, rule or section the
#: answer must be about exactly, not a neighbouring one.
_ID = re.compile(
    r"\b(class|type|tier|grade|category|stage|schedule|group|level|phase|article|section|part|annex|table|"
    r"definition)\s+([A-Z0-9][\w.()-]*)",
    re.IGNORECASE,
)
#: A clause must share this much of its wording with a prompt sentence to count as taken from it.
_RESTATES = 0.5


@dataclass
class Part:
    text: str
    kind: str  # definition | amount | frequency
    terms: list[str]  # what the part is about
    term: str | None = None  # the defined term, for definitions
    ids: tuple[str, ...] = ()  # identifiers that must match exactly: "class s", "article 5", "tier 2"


def _ids(text: str) -> tuple[str, ...]:
    return tuple(f"{m.group(1).lower()} {m.group(2).lower()}" for m in _ID.finditer(text))


def _has_ids(sentence: str, ids: tuple[str, ...]) -> bool:
    low = P.lower(sentence)
    return all(re.search(rf"\b{re.escape(i)}(?![\w])", low) for i in ids)


def parts(question: str) -> list[Part]:
    out: list[Part] = []
    for raw in _SPLIT.split(question.strip()):
        q = raw.strip().rstrip("?").strip()
        if not q:
            continue
        q = q[0].upper() + q[1:]
        m = _MEANS.match(q + "?") or _DEFINE.match(q + "?")
        is_amount = bool(_HOW_MUCH.match(q))
        if m and not is_amount and not any(w in m.group("term").lower().split() for w in _AMOUNT_WORDS):
            term = m.group("term").strip().rstrip("?")
            out.append(Part(q, "definition", _terms(term), term, _ids(term)))
        elif is_amount:
            out.append(Part(q, "amount", _terms(q), None, _ids(q)))
        elif _HOW_OFTEN.match(q):
            out.append(Part(q, "frequency", _terms(q), None, _ids(q)))
    return out


def _terms(text: str) -> list[str]:
    return [t for t in tokenize(text) if t not in _STOP and len(t) > 1]


def _covers(sentence: str, terms: list[str]) -> float:
    """Share of `terms` the sentence mentions, by word prefix ("dose" / "dosage") or a
    known abbreviation."""
    low = P.lower(sentence)
    return (
        sum(1 for t in terms if P.covers_term(low, t) or P.covers_term(low, t[:4])) / len(terms) if terms else 0.0
    )


def answers(part: Part, sentence: str) -> bool:
    """Does `sentence` answer `part` in the form asked?"""
    low = P.lower(sentence)
    if part.ids and not _has_ids(sentence, part.ids):
        return False
    if part.kind == "definition" and part.term:
        term = re.escape(P.lower(part.term))
        return bool(
            re.search(
                rf"\b{term}\b[\"”']?\s+(?:is|are|means|shall\s+mean|refers\s+to|is\s+defined\s+as)\s+"
                r"(?:an?|the|any|each|every|one|a\s+natural)\b",
                low,
            )  # fmt: skip
            or re.search(rf"[\"“]{term}[\"”]\s+(?:means|refers)", low)
        )
    if part.kind == "amount":
        return _covers(sentence, part.terms) >= 0.5 and any(checkable(q) and q.unit for q in quantities(sentence))
    if part.kind == "frequency":
        return _covers(sentence, part.terms) >= 0.5 and bool(frequencies(sentence))
    return False


def _sentences(unit) -> list[str]:  # noqa: ANN001 -- a corpus Unit
    """The unit's sentences; units built from an API request may not carry them."""
    if unit.sentences:
        return [s for s, _, _ in unit.sentences]
    parts_ = re.split(r"(?<=[.;:!?])\s+(?=[A-Z0-9(•\-])|\n+", unit.text)
    return [p.strip(" •-") for p in parts_ if len(p.split()) >= 4]


def _clauses(answer: str) -> list[str]:
    text = re.sub(r"\[\d+(?:,\s*\d+)*\]", " ", answer)
    out: list[str] = []
    for s in re.split(r"(?<=[.!?])\s+", text):
        out.extend(c.strip() for c in re.split(r",?\s+and\s+(?=(?:an?|the|it|they|its)\s)|;\s+", s) if c.strip())
    return out


def check_answer_sources(question: str, answer: str, passages: list[ContextPassage], out: FlagCollector) -> None:
    label = "Each part of the question is answered from the passage that answers it"
    ps = parts(question) if question else []
    sentences = [(p.n, s) for p in passages for s in _sentences(p.unit)]
    if not ps or not sentences or not answer.strip():
        out.check(FlagKind.ANSWER_FROM_NEIGHBOR, label, CheckOutcome.NOT_APPLICABLE,
                  "No question part of a recognized form (a definition, an amount, a frequency).")  # fmt: skip
        return
    flags = []
    checked = 0
    clauses = _clauses(answer)
    for part in ps:
        bearing = [(n, s) for n, s in sentences if answers(part, s)]
        if not bearing:
            continue
        # The answer's clause about this part: the one that mentions what the part is about.
        key = _terms(part.term) if part.term else part.terms
        about = [c for c in clauses if _covers(c, key) >= (1.0 if part.term else 0.5)]
        for clause in about:
            ctoks = set(tokenize(clause))
            if len(ctoks) < 4:
                continue
            n_src, src = max(sentences, key=lambda x: len(ctoks & set(tokenize(x[1]))))
            if len(ctoks & set(tokenize(src))) / len(ctoks) < _RESTATES:
                continue  # not clearly taken from any one sentence
            checked += 1
            if answers(part, src) or answers(part, clause):
                continue
            n_ans, ans = bearing[0]
            f = out.flag(
                FlagKind.ANSWER_FROM_NEIGHBOR,
                origin=FlagOrigin.TEXT,
                stage="answer",
                severity=FlagSeverity.WARNING,
                disposition=FlagDisposition.NEEDS_REVIEW,
                title=f"“{part.text}” may be answered from the wrong passage",
                observation=f"The answer says “{clause[:160]}”, taken from [{n_src}] (“{src[:160]}”), which "
                f"doesn't answer it. [{n_ans}] does: “{ans[:200]}”.",
                why_it_matters="A passage that looks like the answer (the same term, a neighbouring class, rule "
                "or "
                "section) is the most common way extra context leads a model astray.",
                what_to_check=f"Passage [{n_ans}], against the answer.",
                refs=[],
                metrics={"part": part.text, "kind": part.kind, "from": n_src, "answering_passage": n_ans},
                measurement="pattern_match",
            )
            flags.append(f)
    out.check(
        FlagKind.ANSWER_FROM_NEIGHBOR,
        label,
        CheckOutcome.FLAGGED if flags else CheckOutcome.PASSED if checked else CheckOutcome.NOT_APPLICABLE,
        f"{len(ps)} question part(s) of a recognized form; {checked} answer clause(s) traced to their passage."
        if checked or flags
        else "No answer clause could be traced to one passage for a recognized question part.",
        flags,
    )


__all__ = ["Part", "parts", "answers", "check_answer_sources"]
