"""Wittgenstein for admissions review: checking an AI-written summary of an application
against the application itself.

Committees facing thousands of files increasingly read AI summaries or AI screening
output first. The same claim-by-claim verification Wittgenstein runs on RAG answers
applies: each summary sentence is checked against the parts of the file it draws on. What
changes for admissions:

- Skipped: search-side checks (query coverage, retriever agreement, cutoffs). The
  "question" here is "summarize this file", so they don't mean anything.
- Added, each surfaced to a person and never acted on automatically:
  * protected characteristic: the summary mentions race, ethnicity or national origin,
    and whether the file itself states it or the summary inferred it. After SFFA (2023)
    what reviewers see on this is a policy question for the school, not for a checker.
  * figures disagree: the file gives different figures for the same activity (hours in
    the experiences entry vs. the essay); the summary repeats one of them.
  * context omitted: the summary reports a setback (a grade drop, a withdrawal) and the
    file elsewhere gives the applicant's explanation, which the summary leaves out.

Deliberately not done: scoring, ranking or recommending applicants; guessing whether an
essay was written with AI (detectors misclassify non-native writers' essays at high
rates, Liang et al. 2023); inferring any demographic attribute.
"""

from __future__ import annotations

import re
from typing import Any

from wittgenstein.core.enums import FlagDisposition, FlagKind, FlagOrigin, FlagSeverity
from wittgenstein.live.external import ExternalCandidate, ExternalCheckRequest, check_external, summarize
from wittgenstein.live.flags import FlagCollector
from wittgenstein.live.verify import split_answer

#: Search-side flags with no meaning when the input is a whole file, not a search result.
SKIPPED_KINDS = {
    FlagKind.FACET_UNCOVERED,
    FlagKind.FACET_DOMINANCE,
    FlagKind.CONSTRAINT_INSENSITIVE,
    FlagKind.EMBEDDER_TRUNCATION,
    FlagKind.DILUTION,
    FlagKind.RETRIEVER_DISAGREEMENT,
    FlagKind.NEAR_MISS,
    FlagKind.WEAK_BEST_MATCH,
    FlagKind.AMBIGUOUS_CUTOFF,
    FlagKind.FLAT_TOP,
    FlagKind.BUDGET_OMISSION,
    FlagKind.ENUMERATION_INCOMPLETE,
    FlagKind.CROSS_REFERENCE_NOT_FOLLOWED,
    FlagKind.DEFINITION_NOT_IN_CONTEXT,
    FlagKind.REDUNDANCY,
    FlagKind.ANSWER_OFF_QUESTION,
    FlagKind.FALSE_ABSTENTION,
    FlagKind.SEVERED_CONTEXT,
    FlagKind.CONDITION_SATELLITE,
    FlagKind.CONCESSION_SATELLITE,
    FlagKind.BACKWARD_REFERENCE,
    FlagKind.UNRESOLVED_REFERENCE,
    FlagKind.RECOMMENDATION_STRENGTH_DROPPED,
}

DOC_LABELS = {
    "experiences": "experiences entry",
    "academics": "academic record",
    "personal_statement": "personal statement",
    "secondary": "secondary essay",
    "letters": "letter of evaluation",
}

_PROTECTED = re.compile(
    r"\b(?:latin[aoxe]|hispanic|african[- ]american|asian(?:[- ]american)?|caucasian|native american|"
    r"american indian|alaska native|indigenous|pacific islander|native hawaiian|middle eastern|"
    r"arab(?:ic)?[- ]american|"
    r"multiracial|biracial|(?:black|white) (?:student|applicant|woman|man|person|family|community|american)s?|"
    r"(?:person|people|student|applicant)s? of colou?r|ethnicity|ethnic|race|racial|national origin|immigrant)\b",
    re.IGNORECASE,
)
_HOURS = re.compile(
    r"(?:(?:more than|over|about|nearly|almost)\s+)?(\d[\d,]*)\+?\s*hours|total hours:\s*(\d[\d,]*)", re.I
)
_SETBACK = re.compile(
    r"\b(?:fell|fall|dropped|declin\w*|withdr\w*|failed|repeat\w*|retook|retake|lower|dip|probation|"
    r"leave of absence|gap in)\b",
    re.I,
)
_EXPLANATION = re.compile(
    r"\b(?:because|diagnos\w*|caregiv\w*|illness|ill|cancer|chemotherapy|treatment|family|leave|hospitali\w*|"
    r"death|died|passed away|pregnan\w*|full[- ]time|financial|emergency|injur\w*)\b",
    re.I,
)
_APPLICANT_ID = re.compile(r"\b[Aa]pplicant\s+#?(\d{3,})\b")
_STOP = {
    "applicant", "applicants", "their", "they", "them", "there", "which", "about", "after", "before", "while",
    "with", "from", "that", "this", "have", "hours", "completed", "more", "than", "over", "year", "years",
    "describes", "calls", "worked", "works",
}  # fmt: skip


_WORDING = [
    (r"\bAn answer sentence\b", "A summary sentence"),
    (r"\ban answer sentence\b", "a summary sentence"),
    (r"\bThe answer\b", "The summary"),
    (r"\bthe answer\b", "the summary"),
    (r"\bthis part of the answer\b", "this part of the summary"),
    (r"\bThis part of the answer\b", "This part of the summary"),
    (r"\bthe document\b", "the application"),
]


def _as_summary(text: str) -> str:
    for pattern, repl in _WORDING:
        text = re.sub(pattern, repl, text)
    return text


def sections(documents: dict[str, str]) -> list[tuple[str, str]]:
    """(ref, text) for every part of the file: "experiences.md#Medical Scribe" for each
    "## " section, or the file name alone for a document without sections."""
    out: list[tuple[str, str]] = []
    for name, text in documents.items():
        body = re.sub(r"^# .*\n", "", text).strip()
        parts = [p.strip() for p in re.split(r"(?m)^(?=## )", body) if p.strip()]
        if len(parts) <= 1 and not body.startswith("## "):
            out.append((name, body))
            continue
        for p in parts:
            head = p.splitlines()[0].removeprefix("## ").strip() if p.startswith("## ") else ""
            out.append((f"{name}#{head}" if head else name, p))
    return out


def label(ref: str) -> str:
    stem = ref.split("#")[0].rsplit(".", 1)[0]
    return DOC_LABELS.get(stem, stem.replace("_", " "))


def _words(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-z][a-z-]{3,}", text.lower()) if w not in _STOP}


def _first_sentence_with(text: str, pattern: re.Pattern[str]) -> str:
    for s in re.split(r"(?<=[.!?])\s+", text):
        if pattern.search(s):
            return s.strip()
    return text[:200].strip()


def check_summary(documents: dict[str, str], summary: str, cited: list[str]) -> dict[str, Any]:
    """Check an AI summary of one application. `documents` maps file names to text;
    `cited` lists the section refs the summary's [n] markers point to, in order (see
    `sections`). Returns the usual check response, with admissions flags added and
    search-side flags removed, plus `admissions` (what was skipped and why)."""
    # The file is the applicant's own, written in the first person; the applicant number
    # is only its label. Read "Applicant 0582" as "the applicant", or the number becomes an
    # unverifiable claim ("0582 doesn't appear in the source") and costs every sentence
    # naming it its support.
    applicant_id = m.group(1) if (m := _APPLICANT_ID.search(summary)) else None
    summary = _APPLICANT_ID.sub(
        lambda m: (
            "The applicant"
            if m.start() == 0 or summary[: m.start()].rstrip().endswith((".", "!", "?"))
            else "the applicant"
        ),
        summary,
    )
    parts = sections(documents)
    by_ref = dict(parts)
    unknown = [r for r in cited if r not in by_ref]
    if unknown:
        raise ValueError(f"unknown section refs: {unknown}")
    ids = {ref: f"s{i + 1}" for i, (ref, _) in enumerate(parts)}
    order = list(cited) + [r for r, _ in parts if r not in cited]
    req = ExternalCheckRequest(
        query="Summarize this application.",
        candidates=[ExternalCandidate(id=ids[r], text=by_ref[r]) for r in order],
        context_ids=[ids[r] for r in cited],
        answer=summary,
    )
    result = check_external(req)
    result["flags"] = [f for f in result["flags"] if f["kind"] not in {k.value for k in SKIPPED_KINDS}]
    for f in result["flags"]:  # here the text being checked is a summary, not an answer
        for key in ("title", "observation", "why_it_matters", "what_to_check"):
            if f.get(key):
                f[key] = _as_summary(f[key])
    extra = FlagCollector("admissions")
    sentences = split_answer(summary)
    whole_file = "\n".join(documents.values())

    for n, (sent, cites) in enumerate(sentences, start=1):
        sid = f"s{n}"
        # 1. Protected characteristic.
        for m in _PROTECTED.finditer(sent):
            term = m.group(0)
            in_file = re.search(r"\b" + re.escape(term) + r"\b", whole_file, re.I)
            extra.flag(
                FlagKind.PROTECTED_CHARACTERISTIC,
                origin=FlagOrigin.TEXT,
                stage="answer",
                severity=FlagSeverity.WARNING,
                disposition=FlagDisposition.NEEDS_REVIEW,
                title=f"The summary mentions race or ethnicity (“{term}”)",
                observation=(
                    f"“{sent}” says “{term}”. "
                    + (
                        "The applicant's file uses this word too."
                        if in_file
                        else "Nothing in the applicant's file says this: the summary inferred it."
                    )
                ),
                why_it_matters=(
                    "Since SFFA (2023), race can't be a factor in admissions decisions, and 2026 federal "
                    "reviews have treated race-revealing details in files as proxies. A summary that surfaces "
                    "it puts it in front of every reviewer."
                ),
                what_to_check="Whether this belongs in what reviewers see, under your school's policy.",
                metrics={"sentence_id": sid, "term": term, "stated_in_file": bool(in_file)},
                measurement="pattern_match",
            )
            break
        # 2. The file gives different figures for the same activity.
        claimed = [int((a or b).replace(",", "")) for a, b in _HOURS.findall(sent)]
        if claimed:
            topic = _words(sent)
            seen: dict[int, str] = {}
            for ref, text in parts:
                if len(topic & _words(text)) < 1:
                    continue
                for a, b in _HOURS.findall(text):
                    seen.setdefault(int((a or b).replace(",", "")), ref)
            if len(seen) > 1 and any(c in seen for c in claimed):
                listing = "; ".join(f"{v:,} hours in the {label(r)}" for v, r in sorted(seen.items()))
                extra.flag(
                    FlagKind.SOURCE_FIGURES_DISAGREE,
                    origin=FlagOrigin.TEXT,
                    stage="answer",
                    severity=FlagSeverity.CAUTION,
                    disposition=FlagDisposition.NEEDS_REVIEW,
                    title="The file gives different figures for this activity",
                    observation=f"The summary says {claimed[0]:,} hours. The file says {listing}.",
                    why_it_matters=(
                        "When an application disagrees with itself, the summary picks one figure and the "
                        "disagreement disappears from view."
                    ),
                    what_to_check="Which figure the applicant reported for this activity, and whether to ask.",
                    metrics={"sentence_id": sid, "figures": {str(k): v for k, v in seen.items()}},
                    measurement="measured",
                )
        # 3. A setback reported without the explanation the file gives.
        if _SETBACK.search(sent):
            topic = _words(sent)
            cited_refs = {cited[c - 1] for c in cites if 0 < c <= len(cited)}
            best: tuple[int, str, str] | None = None
            for ref, text in parts:
                if ref in cited_refs or not _EXPLANATION.search(text):
                    continue
                shared = len(topic & _words(text))
                if shared >= 2 and (best is None or shared > best[0]):
                    best = (shared, ref, text)
            if best and not _EXPLANATION.search(summary):
                _, ref, text = best
                quote = _first_sentence_with(text, _EXPLANATION)
                extra.flag(
                    FlagKind.CONTEXT_OMITTED,
                    origin=FlagOrigin.TEXT,
                    stage="answer",
                    severity=FlagSeverity.CAUTION,
                    disposition=FlagDisposition.NEEDS_REVIEW,
                    title="The file explains this; the summary doesn't",
                    observation=f"The summary reports “{sent}”. The {label(ref)} says: “{quote}”",
                    why_it_matters=(
                        "A setback reported without the reason the applicant gave reads very differently, and "
                        "holistic review is meant to weigh that context."
                    ),
                    what_to_check=f"Read the applicant's explanation in the {label(ref)} before weighing this.",
                    metrics={"sentence_id": sid, "explained_in": ref},
                    measurement="pattern_match",
                )

    result["flags"] += [f.model_dump(mode="json") for f in extra.flags]
    result["summary"] = summarize(result["flags"], result.get("sentences", []))
    result["admissions"] = {
        "applicant_id": applicant_id,
        "summary_checked": summary,
        "sections": [r for r, _ in parts],
        "skipped_checks": sorted(k.value for k in SKIPPED_KINDS),
        "not_done": [
            "No score, ranking or recommendation: decisions stay with the committee.",
            "No guess at whether an essay was written with AI: detectors misclassify non-native writers.",
            "No inference of race, ethnicity or any other demographic attribute.",
        ],
    }
    return result
