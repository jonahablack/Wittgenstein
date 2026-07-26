"""Rule-based risk triage for (english claim, formal string) pairs.

Flags likely formalization errors with a human-readable reason, so a
reviewer can prioritize attention instead of reading every claim equally
or trusting an opaque score. No trained model, no bare boolean/numeric
score is ever the end product of a flag -- the reason string is it.

Each detector below targets a specific failure mode documented in the
formalization/RAG/NLI literature. Citations are attached at each detector
so the empirical basis for every flag category is traceable without
needing external notes:

  [1] Revisiting Negation Blindness in Large Language Models, EMNLP 2025.
      https://aclanthology.org/2025.emnlp-main.1088/
      LLMs unreliably reverse entailment under negation.

  [2] SemEval Task: NLI4CT, 2023-2024.
      https://arxiv.org/abs/2305.02993
      Best clinical NLI systems cap ~80% F1 on entailment-direction tasks,
      the same underlying skill formalization depends on.

  [3] Leung et al., Classifying and Addressing the Diversity of Errors in
      Retrieval-Augmented Generation Systems, 2025.
      https://arxiv.org/abs/2510.13975
      "Context Mismatch" (E3): chunks split at arbitrary points, severing
      a claim from the antecedent/definition it depends on. The single
      largest error category observed (~25% of all errors).

  [4] Datla et al., Policy->Tests, AAAI 2026.
      https://arxiv.org/abs/2512.04408
      LLM rule-extraction from policy/regulatory text documents models
      "softening or dropping qualifiers," "over-normalizing nuanced
      qualifiers into coarse schema slots, blurring distinctions between
      'may,' 'should,' and 'shall,'" and mishandling "scope misassignment
      when key cues are nonlocal or cross-referenced" and "nested
      exceptions and negations, overlapping or multi-party scopes."

MATCHING NOTE: every phrase list below is matched with word-boundary
regex via _contains_phrase / _find_phrases, never plain Python `in`
substring checks. Plain substring checks on short tokens are a real bug
class here -- e.g. the strong-modal token "no" as a bare substring check
matches inside "nonprofit", "all" matches inside "small", "can"/"may"
match inside "canada"/"mayor"/"mayonnaise", etc. All matching in this
file goes through the helpers below so this class of bug can't silently
reappear when a new phrase is added to a list.

MODAL-MISMATCH AND FORMALIZATION MODE: logic_formalization.py supports
two formal-output modes with fundamentally different expressive power:

  - "english": the model rewrites the claim as precise, logically
    explicit plain English ("For every X, ..."). Modal/deontic language
    ("must", "required", "may") is fully expressible here, and its
    disappearance from the formal string relative to the source claim is
    real, checkable evidence of a dropped qualifier.

  - "logic": the model produces ASCII symbolic notation (&, |, ~, >>)
    parsed downstream by sympy (check_contradictions() calls sympify()
    directly on the "formal" field). sympy.logic.boolalg implements
    classical propositional logic only -- there is no deontic operator
    for "must" vs. "may" vs. "is predicted to" anywhere in that algebra,
    and the prompt's own worked example ("Every event has a cause" ->
    "Event(x) >> Cause(y, x)") establishes the Predicate(x) >>
    Predicate(y, x) shape for every claim regardless of the source
    claim's modal force. A symbolic formal string therefore has no
    modal marker *by construction*, not because a qualifier was dropped
    in this particular instance. Flagging every symbolic-mode claim for
    "missing modal marker" would be noise, not signal, and would
    reintroduce the undifferentiated-alert problem this tool exists to
    prevent.

  detect_modal_mismatch therefore takes a `formal_mode` argument and is
  a no-op whenever formal_mode == "logic". It still runs normally for
  "english" mode, and for "both" mode should be called against the
  formal_english field specifically (see annotate_axiom).
"""

import re

# --- matching helpers -------------------------------------------------------


def _boundary_pattern(phrase):
    """Build a word-boundary-safe regex for a phrase.

    Plain \\b doesn't work cleanly for multi-word phrases with internal
    spaces or for phrases ending in punctuation-adjacent characters, so
    this builds the boundary condition explicitly: the phrase must not
    be immediately preceded or followed by an alphanumeric character.
    """
    core = phrase.strip()
    escaped = re.escape(core)
    return re.compile(rf"(?<![a-z0-9]){escaped}(?![a-z0-9])")


def _contains_phrase(text, phrase):
    return _boundary_pattern(phrase).search(text) is not None


def _find_phrases(text, phrases):
    """Return the subset of `phrases` that appear in `text` as whole
    words/phrases, in order of first appearance.
    """
    hits = []
    for p in phrases:
        if _contains_phrase(text, p):
            hits.append(p)
    hits.sort(key=lambda p: _boundary_pattern(p).search(text).start())
    return hits


def _count_phrase_occurrences(text, phrase):
    return len(_boundary_pattern(phrase).findall(text))


# --- phrase lists ------------------------------------------------------------

_HEDGE_WORDS = [
    "may", "might", "could", "can", "possibly", "perhaps", "arguably",
    "presumably", "seems", "seemingly", "appears", "appear", "suggests",
    "tends to", "somewhat", "largely", "generally", "typically", "often",
    "usually", "in some sense", "in some cases", "to some extent",
    "it could be argued", "one might say",
]

_WEAK_MODALS = ["may", "might", "could", "can", "possibly", "perhaps"]
_MEDIUM_MODALS = ["should", "ought to", "ought"]
_STRONG_MODALS = [
    "must", "shall", "always", "never", "necessarily", "required",
    "requires", "mandatory", "every", "all", "none", "no",
]

# Formal-string-side markers. These are checked against ENGLISH-MODE
# formal output only (see module docstring / detect_modal_mismatch) --
# symbolic "logic" mode is exempted entirely, since sympy's classical
# propositional logic has no deontic operators to look for.
#
# Previously this list only covered symbolic/logic-flavored tokens
# ("must", "necessarily", "always", "shall") and was missing every
# strong-modal word that _STRONG_MODALS already covers on the source
# side ("required", "requires", "every", "all", "none", "no"). Since
# _ENGLISH_INSTRUCTIONS explicitly produces plain English formal strings
# ("For every X, it is not required that..."), those words are exactly
# as likely to appear on the formal side as the source side, and their
# absence from this list caused false "modal marker dropped" flags on
# claims where the modal was carried over verbatim -- e.g. a source
# claim using "required"/"every" formalized into English retaining both
# words, incorrectly flagged because neither word was in this list.
_STRONG_FORMAL_MARKERS = [
    "must", "necessarily", "always", "shall",
    "required", "requires", "every", "all", "none", "no", "mandatory",
]
_WEAK_FORMAL_MARKERS = ["may", "possibly", "might", "could"]

_NEGATION_WORDS = [
    "not", "n't", "never", "no", "without", "fails to", "fail to",
    "lacks", "lack of", "isn't", "aren't", "doesn't", "don't", "cannot",
    "can't",
]
_CLAUSE_CONNECTORS = [
    "and", "or", "but", "if", "unless", "because", "while",
    "although", "though", ", which", ", who",
]

_CROSS_REFERENCE_PHRASES = [
    "as noted above", "as defined above", "as stated earlier",
    "as mentioned above", "as mentioned earlier", "the aforementioned",
    "aforementioned", "aforesaid", "as above", "given the prior",
    "the previous", "the latter", "the former", "unless otherwise specified",
    "unless otherwise stated", "as follows", "as discussed above",
    "as established above", "per the above", "see above",
]

_UNRESOLVED_REFERENCE_MARKERS = [
    "the country", "the company", "the agency", "the provision",
    "the requirement", "the agreement", "the policy", "the party",
    "the parties", "the applicant", "the recipient", "the vendor",
    "the contractor", "the employee", "the employer", "the licensee",
    "the licensor", "this requirement", "this provision", "this section",
    "this agreement", "this policy", "that requirement", "that provision",
    "that agreement", "such provision", "such requirement", "such agreement",
]

_CONDITIONAL_MARKERS = [
    "if", "unless", "provided that", "provided", "in case",
    "assuming", "except when", "except that", "except if", "only if",
    "in the event that",
]


def _lower(text):
    return (text or "").lower()


# --- flag detectors -----------------------------------------------------------


def detect_hedges(english):
    """Hedge detection.

    Basis: [4] Datla et al., AAAI 2026 -- documents LLM rule-extraction
    pipelines "softening or dropping qualifiers" during formalization.
    Hedge words are exactly the qualifiers at risk of being dropped.
    """
    text = _lower(english)
    hits = _find_phrases(text, _HEDGE_WORDS)
    if not hits:
        return None
    quoted = ", ".join(f'"{h}"' for h in hits)
    return {
        "type": "hedge",
        "reason": f"Source claim contains hedging language ({quoted}) that a formal statement may overstate.",
    }


def _modal_strength(text):
    text = _lower(text)
    if _find_phrases(text, _STRONG_MODALS):
        return "strong"
    if _find_phrases(text, _MEDIUM_MODALS):
        return "medium"
    if _find_phrases(text, _WEAK_MODALS):
        return "weak"
    return None


def _formal_strength(formal):
    text = _lower(formal)
    if _find_phrases(text, _STRONG_FORMAL_MARKERS):
        return "strong"
    if _find_phrases(text, _WEAK_FORMAL_MARKERS):
        return "weak"
    return None


def detect_modal_mismatch(english, formal, formal_mode="english"):
    """Modal strength mismatch between source claim and formal string.

    Basis: [4] Datla et al., AAAI 2026 -- "over-normalize nuanced
    qualifiers into coarse schema slots, blurring distinctions between
    'may,' 'should,' and 'shall.'"

    formal_mode controls whether this check runs at all. When
    formal_mode == "logic", this is a no-op: symbolic output parsed by
    sympy (see check_contradictions() in logic_formalization.py) has no
    deontic operators in its algebra, so *every* symbolic formal string
    lacks an explicit modal marker by construction, regardless of the
    source claim's modal force. Checking for one there would flag
    essentially every obligation-bearing claim run through symbolic
    mode, which is noise, not signal. For "english" mode (or "both",
    checked against formal_english -- see annotate_axiom), modal
    language is fully expressible in the formal string, so its absence
    is real, checkable evidence.

    Covers two distinct failure patterns, both only meaningful outside
    "logic" mode:
      1. Source has a modal, formal string has a *different* modal
         (source "may" formalized as though it were mandatory).
      2. Source has a modal, formal string has *no* modal marker at all --
         the qualifier was dropped rather than mistranslated. This is
         the more common pattern per [4] ("softening or dropping
         qualifiers").
    """
    if formal_mode == "logic":
        return None

    source_strength = _modal_strength(english)
    if not source_strength:
        return None

    formal_strength = _formal_strength(formal)

    if not formal_strength:
        return {
            "type": "modal_mismatch",
            "reason": (
                f"Source claim reads as {source_strength} certainty, but the "
                "formal string carries no explicit modal marker at all -- "
                "the qualifier may have been dropped during formalization."
            ),
        }

    if source_strength == formal_strength:
        return None

    severity = (
        "strong mismatch"
        if {source_strength, formal_strength} == {"weak", "strong"}
        else "mismatch"
    )
    return {
        "type": "modal_mismatch",
        "reason": (
            f"Source claim reads as {source_strength} certainty but the formal "
            f"string reads as {formal_strength} certainty ({severity})."
        ),
    }


def detect_negation_scope(english):
    """Negation combined with multiple clauses -- scope is ambiguous.

    Basis: [1] Revisiting Negation Blindness in LLMs, EMNLP 2025, and
    [2] SemEval NLI4CT, 2023-2024 -- both document that LLMs unreliably
    resolve entailment/negation direction, and clinical NLI systems cap
    ~80% F1 on this exact skill. A negation with more than one candidate
    clause to attach to is the structural condition under which that
    unreliability is most likely to produce a formalization error.
    """
    text = _lower(english)
    if not _find_phrases(text, _NEGATION_WORDS):
        return None
    connector_count = sum(
        _count_phrase_occurrences(text, c) for c in _CLAUSE_CONNECTORS
    )
    if connector_count == 0:
        return None
    return {
        "type": "negation_scope",
        "reason": (
            "Claim combines a negation with multiple clauses, so it is "
            "ambiguous which clause the negation applies to."
        ),
    }


def detect_cross_reference(english):
    """Explicit backward-reference phrases ("as noted above", etc.)

    Basis: [4] Datla et al., AAAI 2026 -- "scope misassignment when key
    cues are nonlocal or cross-referenced." This detector catches the
    explicit-phrase case; see detect_unresolved_reference for the
    implicit/anaphoric case.
    """
    text = _lower(english)
    hits = _find_phrases(text, _CROSS_REFERENCE_PHRASES)
    if not hits:
        return None
    return {
        "type": "cross_reference",
        "reason": (
            f'Claim depends on context defined elsewhere ("{hits[0]}"), '
            "which the formal string may not capture."
        ),
    }


def detect_unresolved_reference(english):
    """Implicit anaphora: a definite description or demonstrative standing
    in for an antecedent not present in this segment.

    Basis: [3] Leung et al., 2025 -- "Context Mismatch" (E3), the single
    largest RAG error category observed (~25% of all errors). Their
    worked example: a chunk reads "the country faces the Pacific Ocean"
    without naming the country, so the retriever/formalizer has no way
    to recover the antecedent once the chunk is separated from its
    source context.

    This is a coarse keyword proxy, not real anaphora resolution -- it
    will both miss real cases and occasionally fire on self-contained
    claims -- but it targets the failure pattern most heavily documented
    in the retrieval-error literature specifically, as opposed to
    detect_cross_reference, which only catches explicit backward-
    reference phrases.
    """
    text = _lower(english)
    hits = _find_phrases(text, _UNRESOLVED_REFERENCE_MARKERS)
    if not hits:
        return None
    return {
        "type": "unresolved_reference",
        "reason": (
            f'Claim refers to "{hits[0]}" without naming it directly in this '
            "segment. The antecedent may have been separated from this "
            "claim during chunking, so the formal string may bind to the "
            "wrong entity."
        ),
    }


def detect_nested_conditionals(english):
    """Multiple conditional/exception markers in one claim.

    Basis: [4] Datla et al., AAAI 2026 -- "nested exceptions and
    negations, overlapping or multi-party scopes" are documented as a
    recurring source of formalization error; more embedded conditions
    increase the chance one gets flattened or dropped.
    """
    text = _lower(english)
    count = sum(
        _count_phrase_occurrences(text, marker) for marker in _CONDITIONAL_MARKERS
    )
    if count < 2:
        return None
    return {
        "type": "nested_conditional",
        "reason": (
            f"Claim contains {count} conditional/exception markers; nested "
            "conditions are easy to flatten or drop when formalizing."
        ),
    }


_DETECTORS_ENGLISH_ONLY = [
    detect_hedges,
    detect_negation_scope,
    detect_cross_reference,
    detect_unresolved_reference,
    detect_nested_conditionals,
]

# --- tiering ----------------------------------------------------------------

_FLAG_WEIGHTS = {
    "hedge": 1,
    "cross_reference": 1,
    "unresolved_reference": 1,
    "nested_conditional": 1,
    "negation_scope": 2,
    "modal_mismatch": 2,
}

# Flag types that overlap in what they detect (e.g. "may" can trigger both
# a hedge flag and a modal_mismatch flag off the same word). When both fire
# for the same underlying signal, only the higher-weighted flag counts
# toward the tier score, so one linguistic feature isn't double-counted
# as two independent pieces of evidence.
_OVERLAPPING_GROUPS = [
    {"hedge", "modal_mismatch"},
]


def _dedupe_for_scoring(flags):
    """Collapse overlapping flag types to their highest-weight member
    before scoring. All flags are still returned to the caller/UI --
    this only affects the tier score, not what's displayed.
    """
    present_types = {f["type"] for f in flags}
    drop_types = set()
    for group in _OVERLAPPING_GROUPS:
        present_in_group = group & present_types
        if len(present_in_group) > 1:
            keep = max(present_in_group, key=lambda t: _FLAG_WEIGHTS.get(t, 1))
            drop_types |= (present_in_group - {keep})
    return [f for f in flags if f["type"] not in drop_types]


def flag_claim(english, formal, formal_mode="english"):
    """Return a list of {type, reason} flags for one (english, formal) pair.

    formal_mode should be "english", "logic", or "both" -- matching the
    mode values used in logic_formalization.py -- and controls whether
    detect_modal_mismatch runs (see its docstring). For "both" mode,
    pass the formal_english string here, not formal_logic; see
    annotate_axiom for the caller-facing version that handles this
    automatically from a raw axiom dict.
    """
    flags = []
    for detector in _DETECTORS_ENGLISH_ONLY:
        flag = detector(english)
        if flag:
            flags.append(flag)
    modal_flag = detect_modal_mismatch(english, formal, formal_mode=formal_mode)
    if modal_flag:
        flags.append(modal_flag)
    return flags


def compute_tier(flags):
    """Transparent, inspectable tiering rule: sum of per-flag-type weights,
    with overlapping flag types deduplicated first so a single linguistic
    feature (e.g. one hedge word) can't be counted twice.
    """
    scoring_flags = _dedupe_for_scoring(flags)
    score = sum(_FLAG_WEIGHTS.get(f["type"], 1) for f in scoring_flags)
    if score >= 4:
        return "High"
    if score >= 2:
        return "Medium"
    return "Low"


def annotate_axiom(axiom, mode="english"):
    """Add risk_flags and risk_tier to a single axiom dict, in place.

    `mode` should match the mode passed to formalize_claims(): "logic",
    "english", or "both". This determines which field is checked for
    modal-mismatch and whether that check runs at all:

      - "english": checks axiom["formal"] normally.
      - "logic": checks axiom["formal"], but detect_modal_mismatch is a
        no-op in this mode regardless (see its docstring) -- sympy-
        parsed symbolic output has no modal marker to find by
        construction, so this is skipped rather than flagged.
      - "both": checks axiom["formal_english"] specifically for modal
        mismatch, since that's the field where modal language is
        expressible; axiom["formal_logic"] is not checked for modal
        mismatch for the same reason "logic" mode is skipped.
    """
    english = axiom.get("english", "")

    if mode == "both":
        formal_for_modal_check = axiom.get("formal_english", axiom.get("formal", ""))
        effective_mode = "english"
    else:
        formal_for_modal_check = axiom.get("formal", "")
        effective_mode = mode

    flags = flag_claim(english, formal_for_modal_check, formal_mode=effective_mode)
    axiom["risk_flags"] = flags
    axiom["risk_tier"] = compute_tier(flags)
    return axiom


def annotate_axioms(axioms, mode="english"):
    return [annotate_axiom(ax, mode=mode) for ax in axioms]