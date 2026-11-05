"""What an answer sentence actually claims, read together with the question.

Small and terse models answer "Yes." or "2,550 mg." -- sentences that can't be checked
on their own (red-team cases M2, M3, C6: a bare "Yes" was once judged against the
source as if it were a statement, and read as contradicting it whether right or
wrong). `reconstruct` turns such an answer back into the claim it makes, using the
question: "Can X take Y?" + "Yes." -> "X can take Y."; "What is the maximum dose of
Z?" + "2,550 mg." -> "The maximum dose of Z is 2,550 mg." The reconstruction is shown
with any flag built on it, so a reader can see what was checked.

Also here: recognizing an answer that says the sources don't cover the question
(`abstains`), drug names by their official name stems (`drug_names`), and the
contrast sets used to tell *which* thing a number belongs to (`CONTRASTS`).
"""

from __future__ import annotations

import re

from wittgenstein.live import phrases as P
from wittgenstein.live.nlp import nlp

_YES_NO = re.compile(r"^\s*(yes|no)\b[\s,.:;!-]*", re.IGNORECASE)
_AUX = {"is", "are", "was", "were", "can", "could", "should", "does", "do", "did", "will", "would", "may",
        "must", "has", "have", "might"}  # fmt: skip
_WHAT_BE = re.compile(
    r"^\s*(?:what|which)\s+(?P<head>(?:[\w-]+\s+){0,3}?)(?P<be>is|are|was|were)\s+(?P<x>.+?)\s*\?*\s*$",
    re.IGNORECASE,
)


def is_fragment(text: str) -> bool:
    """No verb at all ("2,550 mg.", "Up to 2 g.") or a bare yes/no."""
    t = text.strip()
    if not t:
        return False
    if _YES_NO.match(t) and len(_YES_NO.sub("", t).split()) == 0:
        return True
    doc = nlp()(t)
    return not any(tok.pos_ in {"VERB", "AUX"} for tok in doc) and len(doc) <= 12


def yes_no(text: str) -> str | None:
    m = _YES_NO.match(text)
    return m.group(1).lower() if m else None


_ATTRIBUTIVE_NEXT = {"NOUN", "PROPN", "ADJ"}


def _copula_predicate(doc) -> int | None:  # noqa: ANN001 -- a spaCy Doc
    """Index where the predicate of "Is <subject> <predicate>?" starts, or None."""
    for t in doc[2:]:
        nxt = doc[t.i + 1] if t.i + 1 < len(doc) else None
        hyphenated = (nxt is not None and nxt.text == "-") or doc[t.i - 1].text == "-"
        if hyphenated:
            continue
        if t.tag_ in {"VBN", "JJ", "JJR", "JJS"} or t.pos_ == "ADJ":
            if nxt is not None and nxt.pos_ in _ATTRIBUTIVE_NEXT:
                continue  # "renal impairment": modifies a noun, still the subject
            return t.i
        if (t.pos_ == "ADP" and t.lower_ != "of") or t.pos_ == "NUM" or t.lower_ in {"a", "an", "the"}:
            return t.i
    return None


def _declarative(question: str, negate: bool) -> str | None:
    """ "Can a patient with X take Y?" -> "A patient with X can (not) take Y." """
    q = question.strip().rstrip("?").strip()
    doc = nlp()(q)
    if len(doc) < 3 or doc[0].lower_ not in _AUX:
        return None
    aux = doc[0]
    root = next((t for t in doc if t.dep_ == "ROOT"), doc[0])
    if root.i == 0:
        # Copula question ("Is X contraindicated in Y?"). The small parser often gets
        # these wrong ("metformin" as a verb, "extended-release" as the object), so the
        # predicate is found by word class: the first predicative adjective or
        # participle, preposition, number or article after the subject has started.
        end = _copula_predicate(doc)
        if end is None:
            subj = next((t for t in doc if t.dep_ in {"nsubj", "nsubjpass", "expl"} and t.i > 0), None)
            if subj is None:
                return None
            end = subj.right_edge.i + 1
    else:
        # The subject runs from after the auxiliary to the first auxiliary, negation or
        # verb that belongs to the main clause ("Should metformin | be started ...").
        end = next(
            (
                t.i
                for t in doc
                if 1 < t.i <= root.i and (t == root or (t.head == root and t.dep_ in {"aux", "auxpass", "neg"}))
            ),
            root.i,
        )
    if end <= 1:
        return None
    subject = q[doc[1].idx : doc[end].idx].strip() if end < len(doc) else q[doc[1].idx :].strip()
    rest = q[doc[end].idx :].strip() if end < len(doc) else ""
    verb = aux.lower_ + (" not" if negate else "")
    out = f"{subject} {verb} {rest}".strip()
    return out[0].upper() + out[1:] + "."


def reconstruct(question: str, sentence: str) -> str | None:
    """The claim a fragment or a bare yes/no makes, in full -- or None when the sentence
    already states its claim (or the question's form isn't one this handles)."""
    if not question:
        return None
    s = sentence.strip()
    yn = yes_no(s)
    remainder = _YES_NO.sub("", s).strip() if yn else s
    if yn and (not remainder.strip(" .") or len(remainder.split()) <= 3):
        # "Yes." / "No, it isn't." -- the claim is the question, affirmed or denied.
        return _declarative(question, negate=yn == "no")
    if not is_fragment(remainder):
        return None
    m = _WHAT_BE.match(question)
    if m:
        head, x = m.group("head").strip(), m.group("x").strip()
        value = remainder.rstrip(".").strip()
        if value[:1].isupper() and not value[:2].isupper():
            value = value[0].lower() + value[1:]
        subject = f"the {head} {x}" if head else x
        subject = subject[0].upper() + subject[1:]
        return f"{subject} {m.group('be').lower()} {value}."
    return None


# --------------------------------------------------------------------------- abstention
_ABSTAIN = re.compile(
    r"\b(?:(?:do|does|did)\s+not|don't|doesn't|didn't|fail\s+to|neither)\s+"
    r"(?:\w+\s+){0,2}?(?:mention|say|state|specify|address|discuss|provide|contain|cover|include|indicate|"
    r"describe|give)\b"
    r"|\b(?:no|not\s+any)\s+(?:information|mention|details?|guidance|data|recommendations?)\b"
    r"|\bnot\s+(?:mentioned|stated|specified|addressed|covered|provided|included|discussed)\b"
    r"|\b(?:cannot|can't|unable\s+to)\s+(?:be\s+)?(?:determine|answer|find|found|determined|answered)\b",
    re.IGNORECASE,
)
_SOURCES = re.compile(
    r"\b(?:passages?|documents?|context|sources?|labels?|labeling|text|information\s+provided|provided)\b",
    re.IGNORECASE,
)


def abstains(sentence: str) -> bool:
    """The sentence says the sources don't cover something ("The passages do not
    mention ...", "No information is provided about ...")."""
    return bool(_ABSTAIN.search(sentence)) and (
        bool(_SOURCES.search(sentence)) or sentence.lower().startswith("no ")
    )


# --------------------------------------------------------------------------- drug names
#: Official (USAN/INN) name stems: a word ending in one of these is almost certainly a
#: drug name. Used to notice a drug in the answer that its sources never mention.
DRUG_STEMS = (
    "mycin", "micin", "cillin", "cycline", "floxacin", "azole", "conazole", "pril", "sartan", "statin", "olol",
    "dipine", "parin", "xaban", "gatran", "gliptin", "gliflozin", "glutide", "formin", "glitazone", "prazole",
    "tidine", "setron", "triptan", "oxetine", "aline", "azepam", "azolam", "barbital", "caine", "dronate",
    "lukast", "mab", "tinib", "ciclib", "vir", "virine", "navir", "previr", "asvir", "buvir", "sone", "olone",
    "terol", "tropium", "afil", "semide", "thiazide", "triptyline", "pramine", "peridol", "apine", "idone",
    "profen", "coxib", "fenac", "thyroxine", "warfarin", "amine",
)  # fmt: skip
_NOT_DRUGS = {"examine", "determine", "amine", "famine", "mine", "imagine", "machine", "routine", "medicine",
              "vaccine", "jasmine", "feminine", "doctrine", "online", "baseline", "guideline", "decline",
              "outline", "airline", "deadline", "pipeline", "timeline", "saline", "alkaline", "discipline",
              "line", "fine", "nine", "wine", "define", "combine", "underline", "marine", "turbine",
              "canine", "equine", "bovine", "porcine", "midline", "hairline", "creatinine", "glycine", "lysine",
              "taurine", "person", "reason", "season", "lesson", "poison", "comparison", "prison",
              "unison", "venison", "caisson", "abandon", "virus", "devoir", "reservoir", "provir", "sone",
              "ozone", "zone", "cortisone", "hormone", "someone", "anyone", "everyone", "alone", "done",
              "gone", "none", "bone", "tone", "phone", "stone", "prone", "throne", "drone", "clone",
              "condone", "postpone", "milestone", "ketone", "acetone", "testosterone", "aldosterone",
              "progesterone", "cholesterol", "april", "until", "oral", "olol"}  # fmt: skip
_WORD = re.compile(r"[a-z][a-z-]{4,}")


def drug_names(text: str) -> set[str]:
    out = set()
    for w in _WORD.findall(P.lower(text)):
        w = w.strip("-")
        if w in _NOT_DRUGS or len(w) < 6:
            continue
        if any((w.endswith(s) and len(w) > len(s) + 2) or (w == s and len(s) >= 7) for s in DRUG_STEMS):
            out.add(w)
    return out


# --------------------------------------------------------------------------- contrasts
#: Words that name mutually exclusive variants of the same thing. A number stated for
#: one member (the immediate-release maximum) is not a fact about another (the
#: extended-release maximum) -- red-team case M1.
CONTRASTS: list[frozenset[str]] = [
    frozenset({"immediate-release", "extended-release", "delayed-release", "sustained-release",
               "modified-release", "controlled-release"}),
    frozenset({"oral", "intravenous", "intramuscular", "subcutaneous", "topical", "inhaled"}),
    frozenset({"starting", "initial", "maintenance", "maximum", "minimum", "loading"}),
    frozenset({"mild", "moderate", "severe"}),
    frozenset({"monotherapy", "combination"}),
    frozenset({"tablet", "tablets", "capsule", "capsules", "suspension", "solution", "injection"}),
]  # fmt: skip
_CANON = {"tablets": "tablet", "capsules": "capsule", "initial": "starting"}


def contrast_terms(text: str) -> list[tuple[int, str, frozenset[str]]]:
    """(character offset, member, its set) for every contrast-set member in `text`."""
    low = P.lower(text)
    out = []
    for group in CONTRASTS:
        for member in group:
            for m in re.finditer(rf"(?<![a-z-]){re.escape(member)}(?![a-z-])", low):
                out.append((m.start(), _CANON.get(member, member), group))
    return sorted(out)


def referent_conflict(claim: str, source_sentence: str, value_offset: int) -> tuple[str, str] | None:
    """(what the source attaches the value to, what the claim says) when the nearest
    contrast term before the value in the source names a different member of a set
    than the claim does -- "2,550 mg" stated for immediate-release, claimed for
    extended-release. None when they agree or the claim names no member of that set."""
    claim_terms = contrast_terms(claim)
    if not claim_terms:
        return None
    before = [t for t in contrast_terms(source_sentence[:value_offset])]
    for group in {g for _, _, g in claim_terms}:
        mine = {m for _, m, g in claim_terms if g == group}
        theirs = [m for _, m, g in before if g == group]
        if not theirs:
            continue
        nearest = theirs[-1]
        if nearest not in mine:
            return nearest, sorted(mine)[0]
    return None
