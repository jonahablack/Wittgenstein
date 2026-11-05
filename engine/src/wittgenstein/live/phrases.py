"""Word-boundary-safe phrase matching and the shared phrase lists.

Ported from the original app's `server/components/risk_triage.py`. Its edge-case log
(RISK_TRIAGE_EDGE_CASES.txt, Part 1) records that bare substring checks were that
module's single most common bug class: "no" inside "nonprofit", "all" inside "small",
"can" inside "canada", "if" inside "gift", "never" inside "nevertheless", "not" inside
"notwithstanding". Every phrase match in the live pipeline therefore goes through
`contains_phrase` / `find_phrases`; tests/unit/test_live_phrases.py scans the live
package's source for the bare `in text` anti-pattern.

There is exactly one list per category (that log's second lesson: two lists describing
"the same tiers" drift apart). Query analysis and passage/answer detectors import them
from here.
"""

from __future__ import annotations

import re
from functools import lru_cache


@lru_cache(maxsize=4096)
def boundary_pattern(phrase: str) -> re.Pattern[str]:
    """The phrase must not touch an alphanumeric character on either side. Built
    explicitly rather than with \\b, which misbehaves for multi-word phrases and phrases
    that begin or end with punctuation (e.g. "n't")."""
    return re.compile(rf"(?<![a-z0-9]){re.escape(phrase.strip())}(?![a-z0-9])")


def contains_phrase(text: str, phrase: str) -> bool:
    return boundary_pattern(phrase).search(text) is not None


def find_phrases(text: str, phrases: list[str]) -> list[str]:
    """Phrases from `phrases` present in `text` as whole words, in order of first
    appearance. `text` must already be lowercased via `lower()`."""
    hits = [p for p in phrases if contains_phrase(text, p)]
    hits.sort(key=lambda p: boundary_pattern(p).search(text).start())  # type: ignore[union-attr]
    return hits


def phrase_spans(text: str, phrases: list[str]) -> list[tuple[str, int, int]]:
    """Every (phrase, start, end) occurrence, longest phrase winning at a position."""
    spans: list[tuple[str, int, int]] = []
    for p in sorted(phrases, key=len, reverse=True):
        for m in boundary_pattern(p).finditer(text):
            if not any(s <= m.start() < e or s < m.end() <= e for _, s, e in spans):
                spans.append((p, m.start(), m.end()))
    return sorted(spans, key=lambda t: t[1])


def count_phrase(text: str, phrase: str) -> int:
    return len(boundary_pattern(phrase).findall(text))


# "no less than X" and similar are quantity idioms, not negation and not a strong
# modal. Masked centrally (edge-case log: a spurious negation-scope flag came from
# "no less than ninety days, and ..."). The mask keeps string length unchanged so that
# offsets computed on the masked text remain valid on the original.
_NO_THAN_IDIOM = re.compile(r"\bno(\s+(?:less|more|fewer|greater|later|earlier|sooner)\s+than)\b")


def lower(text: str | None) -> str:
    return _NO_THAN_IDIOM.sub(lambda m: "~~" + m.group(1), (text or "").lower())


WEAK_MODALS = ["may", "might", "could", "can", "possibly", "perhaps"]
MEDIUM_MODALS = ["should", "ought to", "ought"]
STRONG_MODALS = [
    "must", "shall", "always", "never", "necessarily", "required", "requires", "mandatory", "every", "all",
    "none", "no",
]  # fmt: skip

NEGATION_WORDS = [
    "not", "n't", "never", "no", "without", "fails to", "fail to", "lacks", "lack of", "isn't", "aren't",
    "doesn't", "don't", "cannot", "can't", "neither", "nor",
]  # fmt: skip

#: Query-side exclusion phrasing, in addition to NEGATION_WORDS.
EXCLUSION_WORDS = ["except", "excluding", "other than", "apart from", "aside from", "besides", "exempt"]

CLAUSE_CONNECTORS = [
    "and", "or", "but", "if", "unless", "because", "while", "although", "though", ", which", ", who", "until",
]  # fmt: skip

CROSS_REFERENCE_PHRASES = [
    "as noted above", "as defined above", "as stated earlier", "as mentioned above", "as mentioned earlier",
    "the aforementioned", "aforementioned", "aforesaid", "as above", "given the prior", "the previous",
    "the latter", "the former", "unless otherwise specified", "unless otherwise stated", "as follows",
    "as discussed above", "as established above", "per the above", "see above",
]  # fmt: skip

UNRESOLVED_REFERENCE_MARKERS = [
    "the country", "the company", "the agency", "the provision", "the requirement", "the agreement",
    "the policy", "the party", "the parties", "the applicant", "the recipient", "the vendor", "the contractor",
    "the employee", "the employer", "the licensee", "the licensor", "this requirement", "this provision",
    "this section", "this agreement", "this policy", "that requirement", "that provision", "that agreement",
    "such provision", "such requirement", "such agreement",
]  # fmt: skip

CONDITION_CONNECTIVES = [
    "if", "unless", "provided that", "provided", "only if", "even if", "given that", "assuming that",
    "in the event that", "so long as", "as long as", "in case", "on condition that", "except when",
    "except that", "were to",
]  # fmt: skip

CONCESSION_CONNECTIVES = [
    "although", "though", "even though", "even if", "whereas", "despite", "in spite of", "nevertheless",
    "nonetheless", "however", "yet", "granted that", "admittedly", "notwithstanding",
]  # fmt: skip

#: Ambiguous between a clause connector and a sentence-initial adverb; a well-formed
#: clause must precede them to count as a concession satellite.
CONCESSION_NEEDS_PRECEDING_CLAUSE = frozenset({"however", "yet"})

#: Openers that make a passage depend on the text before it when it starts a passage.
#: (Severed-context gap signal, live/gaps.py.)
DEPENDENT_OPENERS = [
    "however", "but", "yet", "nevertheless", "nonetheless", "moreover", "furthermore", "in addition",
    "additionally", "therefore", "thus", "hence", "consequently", "accordingly", "otherwise", "instead",
    "similarly", "likewise", "conversely", "in contrast", "on the other hand", "this", "these", "that",
    "those", "such", "it", "they", "he", "she", "the latter", "the former", "the above", "as a result",
    "for this reason", "in that case", "in such cases", "except",
]  # fmt: skip

#: Phrasing that announces content the passage itself may not contain.
FORWARD_POINTERS = ["the following", "as follows", "below", "listed below", "set out below"]

COMPARATOR_PHRASES = [
    "more than", "less than", "fewer than", "greater than", "at least", "at most", "no more than",
    "no less than", "up to", "exceeds", "exceeding", "over", "under", "below", "above", "minimum", "maximum",
    "before", "after", "prior to", "within",
]  # fmt: skip

MODALITY_PHRASES = [
    "must", "shall", "may", "should", "required", "requires", "require", "permitted", "allowed", "optional",
    "mandatory", "prohibited", "forbidden", "can", "cannot",
]  # fmt: skip

#: Who a statement applies to. In clinical text these are the qualifiers whose loss
#: turns "in adults" or "if eGFR is below 30" into a statement about everyone.
POPULATION_CUES = [
    "pediatric", "children", "child", "infants", "infant", "neonates", "neonatal", "newborns", "adolescents",
    "adults", "adult", "elderly", "geriatric", "older adults", "older patients", "pregnant", "pregnancy",
    "lactating", "lactation", "breastfeeding", "breastfed", "nursing", "renal impairment", "hepatic impairment",
    "kidney disease", "liver disease", "renal function", "kidney function", "hepatic function", "liver function",
    "debilitated", "asian patients", "egfr", "creatinine clearance", "crcl", "dialysis", "weighing",
    "body weight", "years of age", "years and older", "years or older", "months of age", "females", "males",
    "women", "men", "premenopausal", "postmenopausal",
]  # fmt: skip


def contains_word_prefix(text: str, term: str) -> bool:
    """Whole-word match, except terms of 4+ letters may take a short suffix ("elope" ->
    "eloped", "pregnan..." forms). Anchored at a word start, never mid-word."""
    if len(term) < 4:
        return contains_phrase(text, term)
    return re.search(rf"(?<![a-z0-9]){re.escape(term)}[a-z]{{0,5}}(?![a-z0-9])", text) is not None


ENUMERATION_CUES = ["list", "all", "every", "each", "how many", "enumerate", "name the", "what are the"]
COMPARISON_CUES = ["compare", "comparison", "difference", "differences", "differ", "versus", "vs", "compared"]
EXPLANATION_CUES = ["why", "explain", "how does", "how do", "how did", "reason", "reasons", "cause", "caused"]
