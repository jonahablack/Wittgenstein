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

  [5] Mann, W.C. & Thompson, S.A. -- Rhetorical Structure Theory (RST).
      This project's verified bibliographic anchor for RST is Carlson &
      Marcu, "Discourse Tagging Reference Manual", ISI, 2001 (cited in
      the paper as carlson2001discourse). RST defines discourse relations
      between a nucleus and a satellite. detect_condition_satellite and
      detect_concession_satellite below are grounded in RST's Condition
      and Concession relation definitions specifically (quoted verbatim
      in each detector's own docstring), NOT in [1]-[4] above -- those
      remain the basis for negation_scope, modal_mismatch,
      cross_reference, and unresolved_reference, all unchanged by this
      rebuild.

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

import spacy

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


# --- spaCy: subject+finite-verb well-formedness gate -------------------------
#
# Loaded ONCE at module level (not per-call) -- en_core_web_sm specifically,
# not en_core_web_md or a transformer model, so this stays runnable on
# free-tier infrastructure (no GPU, small RAM/disk footprint). ner and
# lemmatizer are disabled: detect_condition_satellite/
# detect_concession_satellite below use spaCy for EXACTLY ONE purpose --
# checking whether a candidate satellite clause has its own subject and
# finite verb (i.e. is an independently well-formed clause, not just a
# phrase) -- which needs only tagging and dependency parsing. This is
# RST's own segmentation criterion applied before anything counts as a
# separate discourse unit at all, not a full discourse parse: spaCy is
# never asked to identify a relation, a nucleus, or a satellite here --
# only "does this span have a subject and a finite verb."

_NLP = spacy.load("en_core_web_sm", disable=["ner", "lemmatizer"])

_SUBJECT_DEPS = {"nsubj", "nsubjpass", "expl"}


def _has_subject_and_finite_verb(text):
    """True if `text` parses to a span with its own subject AND its own
    finite verb -- e.g. "the parties agree otherwise in writing" (subject
    "parties", finite verb "agree") is a well-formed clause; "if
    applicable" or "except for good cause" are not (no subject at all),
    and "even if properly notified" is not (no subject; "notified" is a
    bare participle, not a finite verb). Modal auxiliaries ("may", "must",
    "should") count as finite -- spaCy tags them VerbForm=Fin -- so
    "although the applicant may request an extension" is correctly
    well-formed even though its main verb ("request") is a bare
    infinitive.
    """
    text = (text or "").strip()
    if not text:
        return False
    doc = _NLP(text)
    has_subject = any(tok.dep_ in _SUBJECT_DEPS for tok in doc)
    has_finite_verb = any("Fin" in tok.morph.get("VerbForm") for tok in doc)
    return has_subject and has_finite_verb


# --- phrase lists ------------------------------------------------------------
#
# _HEDGE_WORDS (used only by the retired detect_hedges) is removed. Its
# role -- flagging qualifiers at risk of being softened or dropped -- is
# now covered by detect_modal_mismatch's "no explicit modal marker at
# all" branch for weak/medium modals, and by condition_satellite/
# concession_satellite for hypothetical/concessive qualifiers specifically.

# Modal-strength tiers, one shared set of word lists used for BOTH the
# source claim and the formal string. These used to be two separate pairs
# of lists (_STRONG_MODALS vs _STRONG_FORMAL_MARKERS, and an implicit
# medium-tier gap on the formal side with no list at all), which had to be
# kept in sync by hand -- and didn't stay in sync. Two confirmed bugs came
# directly from that duplication:
#   - "can" and "perhaps" were in _WEAK_MODALS but missing from
#     _WEAK_FORMAL_MARKERS, so a formal string that preserved "can"
#     verbatim from the source ("...can generate entirely new
#     possibilities") was still reported as having "no explicit modal
#     marker at all."
#   - There was no medium-tier formal list at all, so "should"/"ought"
#     preserved verbatim in a formal string ("...should be deployed...")
#     could never be recognized on the formal side, guaranteeing a false
#     "modal marker dropped" flag on every medium-modal source claim
#     whose formal string kept the same word.
# A single shared set of tiers makes this whole bug class structurally
# impossible: there is nothing left to fall out of sync.
_WEAK_MODALS = ["may", "might", "could", "can", "possibly", "perhaps"]
_MEDIUM_MODALS = ["should", "ought to", "ought"]
_STRONG_MODALS = [
    "must", "shall", "always", "never", "necessarily", "required",
    "requires", "mandatory", "every", "all", "none", "no",
]

_NEGATION_WORDS = [
    "not", "n't", "never", "no", "without", "fails to", "fail to",
    "lacks", "lack of", "isn't", "aren't", "doesn't", "don't", "cannot",
    "can't", "neither", "nor",
]
_CLAUSE_CONNECTORS = [
    "and", "or", "but", "if", "unless", "because", "while",
    "although", "though", ", which", ", who", "until",
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

# _CONDITIONAL_MARKERS (generic marker-counting, used only by the retired
# detect_nested_conditionals / detect_segment_nested_conditionals) is
# removed. Nested conditionals are now caught as Condition or Concession
# satellites directly -- see _CONDITION_CONNECTIVES / _CONCESSION_CONNECTIVES
# below -- rather than by counting markers with no regard to which
# relation a marker signals or whether it introduces a real clause at all.

# RST Condition connectives -- see detect_condition_satellite for the
# exact Mann & Thompson definition this grounds. "should [clause]" was
# considered and deliberately dropped: it is too ambiguous a trigger on
# its own and would over-fire on ordinary modal obligation language.
_CONDITION_CONNECTIVES = [
    "if", "unless", "provided that", "provided", "only if", "even if",
    "given that", "assuming that", "in the event that", "so long as",
    "as long as", "in case", "on condition that", "except when",
    "except that", "were to",
]

# RST Concession connectives -- see detect_concession_satellite for the
# exact Mann & Thompson definition this grounds. "even if" legitimately
# triggers Condition too depending on use -- both detectors independently
# check it, on purpose, since Condition and Concession are different
# relations even when the same connective can signal either.
_CONCESSION_CONNECTIVES = [
    "although", "though", "even though", "even if", "whereas", "despite",
    "in spite of", "nevertheless", "nonetheless", "however", "yet",
    "granted that", "admittedly", "notwithstanding",
]

# "however" and "yet" are ambiguous between a clause-connecting
# subordinator ("The plan failed, however the team adapted.") and a
# standalone sentence-initial adverb with nothing to connect ("However,
# the team adapted."). _find_satellite additionally requires a
# well-formed clause BEFORE these two connectives specifically -- see its
# docstring -- to tell the two apart.
_CONCESSION_NEEDS_PRECEDING_CLAUSE = frozenset({"however", "yet"})


# "no less than X" / "no more than X" / "no later than X" / "no fewer than
# X" / "no greater than X" / "no earlier than X" / "no sooner than X" are
# quantity/degree idioms -- "no" here isn't negating a clause a reviewer
# would need to disambiguate scope for, and it isn't asserting a strong
# deontic claim either. Left unmasked, bare "no" inside these idioms was
# matching both _NEGATION_WORDS (a false negation_scope/segment_negation_
# scope trigger on sentences with no real negation at all -- e.g. "must
# retain logs for no less than ninety days, and this requirement applies
# ...", where "no" + the unrelated "and" elsewhere in the sentence
# combined to produce a spurious segment-level negation flag) and
# _STRONG_MODALS (a latent false-strong-modal reading via the same
# mechanism, not yet observed in practice but structurally identical).
# Masked centrally in _lower(), which every detector routes through, so
# this is fixed once rather than needing a special case in each affected
# detector separately.
_NO_THAN_IDIOM = re.compile(
    r"\bno\s+(?:less|more|fewer|greater|later|earlier|sooner)\s+than\b"
)


def _lower(text):
    text = (text or "").lower()
    return _NO_THAN_IDIOM.sub("some threshold", text)


# --- flag detectors -----------------------------------------------------------


# detect_hedges was retired in this rebuild (see "What gets retired"):
# its logic, its _FLAG_WEIGHTS entry, its _DETECTORS_ENGLISH_ONLY entry,
# and its _OVERLAPPING_GROUPS entry ({"hedge", "modal_mismatch"}) are all
# gone -- that overlap group is removed too, since one of its two members
# no longer exists.


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
    """Same tiers, same word lists as _modal_strength -- see the comment
    above _WEAK_MODALS for why this used to be two separate lists and
    what that caused.
    """
    text = _lower(formal)
    if _find_phrases(text, _STRONG_MODALS):
        return "strong"
    if _find_phrases(text, _MEDIUM_MODALS):
        return "medium"
    if _find_phrases(text, _WEAK_MODALS):
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

    This is an INDEPENDENT failure mode from the Condition/Concession
    satellite detectors below -- this one is grounded in the
    entailment/negation-scope-resolution literature ([1], [2]), not RST,
    and fires on negation-plus-connector structure regardless of whether
    any Condition/Concession connective is present at all. Logic
    unchanged by this rebuild -- only the reason string below was updated
    to make that independence explicit.
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
            "Negation combined with multiple clauses: scope of negation "
            "is ambiguous across clauses -- a formalization may attach "
            "the negation to the wrong clause, changing the assertion's "
            "polarity. (Independent of Condition/Concession relations "
            "above; grounded in negation-scope-resolution literature, "
            "not RST.)"
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


# detect_nested_conditionals and detect_segment_nested_conditionals were
# retired in this rebuild (see "What gets retired"): nested conditionals
# are now caught as Condition or Concession satellites directly, below,
# which distinguish WHICH relation a connective signals and require the
# connective to introduce an actual clause (subject + finite verb, via
# spaCy) before counting it at all -- generic marker-counting did neither.
# _CONDITIONAL_MARKERS is removed for the same reason.


# --- satellite clause extraction (Condition / Concession) -------------------
#
# Shared machinery for detect_condition_satellite, detect_concession_
# satellite, and their segment-level fallbacks below.

_CLAUSE_BOUNDARY = re.compile(r"[,;:.]")


def _clause_after(text, end_pos):
    """Text from `end_pos` to the next clause boundary (comma, semicolon,
    colon, or period) or the end of the string, stripped -- a coarse,
    non-parsing approximation of "the rest of this clause," good enough
    to hand to _has_subject_and_finite_verb for the well-formedness gate.
    """
    rest = text[end_pos:]
    boundary = _CLAUSE_BOUNDARY.search(rest)
    clause = rest[:boundary.start()] if boundary else rest
    return clause.strip()


def _find_satellite(text, connectives, needs_preceding_clause=frozenset()):
    """Find the earliest, most specific connective from `connectives`
    (word-boundary safe, via _boundary_pattern -- never a new ad hoc
    matcher) whose introduced clause is well-formed: has its own subject
    and finite verb, per _has_subject_and_finite_verb. This is the
    "independence" check RST's own segmentation criteria require before
    a span counts as a separate discourse unit at all -- e.g. "if
    applicable" or "except for good cause" are bare phrases, not clauses,
    and are correctly never flagged.

    `text` must already be lowercased (via _lower), matching every other
    detector in this module -- so the connective and clause text returned
    are lowercase too, the same convention as e.g. detect_cross_reference's
    quoted hits.

    When two connectives from the list start at the same position (e.g.
    "provided" is a prefix of "provided that"), the longer/more specific
    one wins.

    needs_preceding_clause: connectives ambiguous between a
    clause-connecting subordinator and a standalone sentence-initial
    adverb with nothing to connect (_CONCESSION_NEEDS_PRECEDING_CLAUSE:
    "however", "yet"). For these, ALSO require a well-formed clause
    BEFORE the connective -- otherwise "However, the team adapted."
    would be flagged just because "the team adapted" is a well-formed
    clause on its own, even though there is nothing before "however" to
    concede against.

    Known limitation, documented rather than silently papered over:
    "were to" as an inverted subjunctive ("Were the applicant to
    withdraw...") places the subject BEFORE the connective, so this
    from-connective-forward slicing will not find a subject after it and
    the well-formedness gate will reject it. In practice this
    construction almost always co-occurs with "if" ("if the applicant
    were to withdraw"), which this function does catch.

    Returns (connective, clause_text) for the first qualifying match, or
    None.
    """
    candidates = []
    for phrase in connectives:
        m = _boundary_pattern(phrase).search(text)
        if m:
            candidates.append((m.start(), -len(phrase), phrase, m.end()))
    candidates.sort()
    for start, _, phrase, end in candidates:
        if phrase in needs_preceding_clause:
            preceding = text[:start].strip(" \t.,;:")
            if not _has_subject_and_finite_verb(preceding):
                continue
        clause = _clause_after(text, end)
        if not clause or not _has_subject_and_finite_verb(clause):
            continue
        return phrase, clause
    return None


# Minimal closed-class stopword list for the content-word overlap check in
# _classify_severance -- excluded so a shared function word ("the", "is")
# doesn't count as evidence the satellite's own CONTENT survived
# formalization. Deliberately small and local to this one check, not a
# general-purpose NLP stopword list.
_CLAUSE_STOPWORDS = {
    "the", "a", "an", "and", "or", "but", "that", "this", "these", "those",
    "is", "are", "was", "were", "be", "been", "being", "to", "of", "in",
    "on", "at", "for", "with", "as", "by", "it", "its", "not", "no",
    "may", "might", "could", "can", "will", "would", "shall", "should",
    "must", "do", "does", "did",
}


def _classify_severance(clause_text, connective, formal):
    """Classify how a satellite's connective and clause content fared in
    `formal`, relative to the source claim. This is a coarse keyword-
    overlap proxy -- consistent with spaCy being used ONLY for the
    well-formedness gate in _find_satellite, never as a discourse parser
    over the formal output -- not a claim that the formal string's
    logical structure was actually inspected.

    Three outcomes:
      - None ("present-no-flag"): the connective AND the clause's own
        content both appear in `formal` -- treated as still co-occurring
        with the nucleus in the same claim, i.e. no evidence the
        conditional/concessive relation was lost.
      - "dropped": NEITHER the connective NOR any recognizable content
        word from the clause appears in `formal` -- the satellite did
        not survive formalization at all.
      - "severed": some trace survives but not both together -- the
        clause's propositional content may have survived detached from
        the connective that marked it as conditional/concessive (or vice
        versa), so it reads as an independent, unconditional assertion
        rather than a satellite the nucleus depends on / an acknowledged
        exception.
    """
    formal_text = _lower(formal or "")
    connective_present = bool(formal_text) and _contains_phrase(formal_text, connective)
    connective_words = set(re.findall(r"[a-z']+", connective))
    content_words = [
        w for w in re.findall(r"[a-z']+", clause_text)
        if w not in _CLAUSE_STOPWORDS and w not in connective_words
    ]
    content_present = bool(formal_text) and any(
        _contains_phrase(formal_text, w) for w in content_words
    )
    if connective_present and content_present:
        return None
    if not connective_present and not content_present:
        return "dropped"
    return "severed"


def detect_condition_satellite(english, formal):
    """RST Condition relation between a nucleus and a satellite.

    Mann & Thompson's definition, quoted verbatim (this project's
    verified bibliographic anchor for RST is Carlson & Marcu, Discourse
    Tagging Reference Manual, ISI, 2001 -- carlson2001discourse in the
    paper):

        CONDITION -- constraints on the nucleus (N): none. Constraints on
        the satellite (S): S presents a hypothetical, future, or
        otherwise unrealized situation (relative to S's own situational
        context). Constraint on the N+S combination: realization of the
        situation presented in N depends on realization of the situation
        presented in S.

    Detection: find a Condition connective ("if", "unless", "provided
    that", ...; see _CONDITION_CONNECTIVES) that introduces a well-formed
    clause (_find_satellite -- the independence check RST's own
    segmentation criteria require). Then check whether that satellite
    survived formalization intact (_classify_severance):

      - "dropped": the whole satellite (connective + clause content) is
        absent from `formal` -- a reader of the formal string alone
        would wrongly conclude the nucleus holds unconditionally.
      - "severed": some trace of the satellite survives in `formal`, but
        not the connective and clause content together -- a reader
        would wrongly treat the satellite's content as an independent,
        unconditional fact rather than a condition the nucleus depends
        on.
      - neither (co-occurring in the same claim): no flag.

    formal_mode is NOT a parameter here (unlike detect_modal_mismatch):
    this function is mode-agnostic by design (Implementation vs
    Orchestration -- this is the HOW). flag_claim decides WHETHER to call
    this at all based on formal_mode (the WHEN/WHETHER), for exactly the
    reason detect_modal_mismatch is a no-op in "logic" mode: a symbolic
    formal string can no more contain the English word "unless" than it
    can contain "must" -- by construction, not because a connective was
    dropped in this particular instance. See flag_claim.
    """
    text = _lower(english)
    found = _find_satellite(text, _CONDITION_CONNECTIVES)
    if not found:
        return None
    connective, clause = found
    outcome = _classify_severance(clause, connective, formal)
    if outcome is None:
        return None
    if outcome == "dropped":
        reason = (
            f'Source claim makes its nucleus conditional on a satellite '
            f'introduced by "{connective}" ("{clause}"), but the formal '
            "string shows no trace of that satellite at all. A reader of "
            "the formal string alone would wrongly conclude the nucleus "
            "holds unconditionally, when the source claim only asserted "
            "it contingent on that condition."
        )
    else:
        reason = (
            f'Source claim makes its nucleus conditional on a satellite '
            f'introduced by "{connective}" ("{clause}"), but the formal '
            "string does not keep the connective and the clause's "
            "content together as one condition. The satellite's content "
            "may have survived formalization detached from the "
            "connective that tied it to the nucleus, so a reader of the "
            "formal string alone would wrongly treat it as an "
            "independent, unconditional fact rather than a condition the "
            "nucleus depends on."
        )
    return {"type": "condition_satellite", "reason": reason}


def detect_concession_satellite(english, formal):
    """RST Concession relation between a nucleus and a satellite.

    Mann & Thompson's definition, quoted verbatim (same bibliographic
    anchor as detect_condition_satellite):

        CONCESSION -- constraints on N: the writer has positive regard
        for the situation in N. Constraints on S: the writer is not
        claiming the situation in S doesn't hold. Constraint on N+S: the
        writer acknowledges a potential or apparent incompatibility
        between N and S, but regards them as compatible, and recognizing
        that compatibility increases the reader's positive regard for N.

    Same detection structure as detect_condition_satellite: find a
    Concession connective ("although", "though", "despite", ...; see
    _CONCESSION_CONNECTIVES) introducing a well-formed clause, then
    classify severance against `formal`. "however" and "yet" additionally
    require a well-formed clause BEFORE the connective too (see
    _find_satellite / _CONCESSION_NEEDS_PRECEDING_CLAUSE), so a
    standalone sentence-initial "However, ..." with nothing to concede
    against is not flagged. "even if" legitimately triggers
    detect_condition_satellite too, depending on use -- both
    independently check it; that is intentional, not deduped (see
    _OVERLAPPING_GROUPS).

    See flag_claim for why this, like detect_condition_satellite, is
    skipped in "logic" formal_mode.
    """
    text = _lower(english)
    found = _find_satellite(
        text, _CONCESSION_CONNECTIVES,
        needs_preceding_clause=_CONCESSION_NEEDS_PRECEDING_CLAUSE,
    )
    if not found:
        return None
    connective, clause = found
    outcome = _classify_severance(clause, connective, formal)
    if outcome is None:
        return None
    if outcome == "dropped":
        reason = (
            f'Source claim concedes an exception via a satellite '
            f'introduced by "{connective}" ("{clause}"), but the formal '
            "string shows no trace of that satellite at all. A reader of "
            "the formal string alone would wrongly conclude the nucleus "
            "holds without the qualification the source claim "
            "acknowledged."
        )
    else:
        reason = (
            f'Source claim concedes an exception via a satellite '
            f'introduced by "{connective}" ("{clause}"), but the formal '
            "string does not keep the connective and the clause's "
            "content together as one concession. The acknowledged "
            "exception's content may have survived formalization "
            "detached from the connective that marked it as a "
            "concession, so a reader of the formal string alone would "
            "wrongly treat it as an unrelated, independent fact rather "
            "than an acknowledged exception to the nucleus."
        )
    return {"type": "concession_satellite", "reason": reason}


def detect_segment_condition_satellite(segment_text):
    """Same connective-plus-well-formedness logic as
    detect_condition_satellite, but run against the full ORIGINAL SEGMENT
    (the source sentence before claim extraction split it into separate
    claims), not an individual extracted claim's text.

    Basis: same atomization-fragmentation argument as the retired
    detect_segment_nested_conditionals (claim extraction is deliberately
    atomic -- one assertion per claim, see response_parsing.py's
    extraction prompt -- so a sentence like "Unless the parties agree
    otherwise in writing, the fee is due within 30 days." can be split so
    the satellite ("unless the parties agree...") lands in a different
    claim than the nucleus ("the fee is due..."), and neither claim's own
    text shows a Condition connective attached to the other's content),
    retargeted at Condition specifically rather than generic
    marker-counting: this checks for an actual Condition connective
    introducing an actual well-formed clause, not just a raw marker
    count.

    No severed/dropped distinction here (there is no single per-segment
    formal string to compare against) -- one reason string, same as
    detect_segment_negation_scope. Only meaningful when
    detect_condition_satellite did NOT already fire on this claim's own
    text -- see flag_claim.
    """
    text = _lower(segment_text)
    found = _find_satellite(text, _CONDITION_CONNECTIVES)
    if not found:
        return None
    connective, clause = found
    return {
        "type": "segment_condition_satellite",
        "reason": (
            f'This claim was extracted from a source sentence containing '
            f'the Condition connective "{connective}" introducing '
            f'"{clause}", but this claim\'s own text does not show that '
            "structure. Claim extraction may have split the satellite "
            "condition into a different claim than the nucleus it "
            "constrains, so this claim's formal string may be read as "
            "unconditional when the source sentence made it conditional."
        ),
    }


def detect_segment_concession_satellite(segment_text):
    """Same connective-plus-well-formedness logic as
    detect_concession_satellite, but run against the full original
    SEGMENT text -- see detect_segment_condition_satellite's docstring
    for the shared rationale, retargeted at Concession.

    Only meaningful when detect_concession_satellite did NOT already
    fire on this claim's own text -- see flag_claim.
    """
    text = _lower(segment_text)
    found = _find_satellite(
        text, _CONCESSION_CONNECTIVES,
        needs_preceding_clause=_CONCESSION_NEEDS_PRECEDING_CLAUSE,
    )
    if not found:
        return None
    connective, clause = found
    return {
        "type": "segment_concession_satellite",
        "reason": (
            f'This claim was extracted from a source sentence containing '
            f'the Concession connective "{connective}" introducing '
            f'"{clause}", but this claim\'s own text does not show that '
            "structure. Claim extraction may have split the acknowledged "
            "exception into a different claim than the nucleus it "
            "qualifies, so this claim's formal string may be read "
            "without the qualification the source sentence acknowledged."
        ),
    }


# detect_segment_negation_scope (below) is KEPT, unchanged, alongside the
# two segment-level satellite detectors above -- do not read its survival
# as an oversight. detect_segment_nested_conditionals was retired because
# its claim-level parent, detect_nested_conditionals, was ALSO retired --
# both superseded by the Condition/Concession satellite detectors above.
# By contrast detect_negation_scope (this function's claim-level parent)
# is explicitly KEPT, unchanged, in this rebuild, so its segment-level
# fallback stays too, for the same reason every other kept detector's
# segment fallback would: to catch negation-plus-connector structure that
# atomization scattered across claims before detect_negation_scope ever
# saw it.
def detect_segment_negation_scope(segment_text):
    """Same negation-plus-connector logic as detect_negation_scope, but run
    against the full original SEGMENT text.

    Basis: same mechanism as detect_segment_nested_conditionals above --
    a compound sentence like "should not transfer X, and should not permit
    Y" gets split into two claims, each with one negation and no
    connector, so detect_negation_scope never fires on either fragment
    even though the source sentence combined a negation with multiple
    clauses.

    Only meaningful when the corresponding claim-level check did NOT
    already fire -- see annotate_axiom.
    """
    text = _lower(segment_text)
    if not _find_phrases(text, _NEGATION_WORDS):
        return None
    connector_count = sum(
        _count_phrase_occurrences(text, c) for c in _CLAUSE_CONNECTORS
    )
    if connector_count == 0:
        return None
    return {
        "type": "segment_negation_scope",
        "reason": (
            "This claim was extracted from a source sentence combining a "
            "negation with multiple clauses, but this claim's own text does "
            "not show that structure. Claim extraction may have separated "
            "this claim from the clause that determines what the negation "
            "in the original sentence applied to."
        ),
    }


_DETECTORS_ENGLISH_ONLY = [
    detect_negation_scope,
    detect_cross_reference,
    detect_unresolved_reference,
]
# detect_condition_satellite and detect_concession_satellite are NOT in
# this list: unlike the three above, they need `formal` too (they are
# formal-side checks, like detect_modal_mismatch), so flag_claim calls
# them directly rather than through this english-only loop.

# --- tiering ----------------------------------------------------------------

_FLAG_WEIGHTS = {
    "condition_satellite": 3,
    "concession_satellite": 2,
    "segment_condition_satellite": 3,
    "segment_concession_satellite": 2,
    "negation_scope": 2,
    "modal_mismatch": 2,
    "unresolved_reference": 1,
    "cross_reference": 1,  # kept, unweighted-change
    "segment_negation_scope": 2,  # kept, unweighted-change
}

# Flag types that overlap in what they detect used to include just
# {"hedge", "modal_mismatch"} (e.g. "may" triggering both off the same
# word) -- removed along with detect_hedges, since "hedge" no longer
# exists as a flag type. condition_satellite and concession_satellite are
# deliberately NOT added here even though the same connective ("even if")
# can trigger both: they are different RST relations, not the same
# underlying signal counted twice, so both are meant to count
# independently (see detect_concession_satellite's docstring). No other
# entry existed in this list before hedge/modal_mismatch, so there is
# nothing else to re-examine here.
_OVERLAPPING_GROUPS = []


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


def flag_claim(english, formal, formal_mode="english", segment_text=None):
    """Return a list of {type, reason} flags for one (english, formal) pair.

    formal_mode should be "english", "logic", or "both" -- matching the
    mode values used in logic_formalization.py -- and controls whether
    detect_modal_mismatch, detect_condition_satellite, and
    detect_concession_satellite run. For "both" mode, pass the
    formal_english string here, not formal_logic; see annotate_axiom for
    the caller-facing version that handles this automatically from a raw
    axiom dict.

    detect_condition_satellite and detect_concession_satellite are
    skipped entirely when formal_mode == "logic", for the same reason
    detect_modal_mismatch is (see its docstring): a symbolic formal
    string parsed by sympy has no English connective ("unless",
    "although", ...) any more than it has an English modal marker, by
    construction. Unlike detect_modal_mismatch, this mode check lives
    here in flag_claim rather than inside the detector functions
    themselves -- they take just (english, formal), mode-agnostic, and
    flag_claim (the orchestrator) decides WHETHER calling them is
    meaningful, matching this project's Implementation-vs-Orchestration
    split (HOW vs WHEN/WHETHER).

    segment_text, if given, is the original source sentence this claim was
    extracted from (before claim extraction split it into one or more
    claims). When present, detect_segment_condition_satellite,
    detect_segment_concession_satellite, and detect_segment_negation_scope
    run against it -- but ONLY for whichever of the three checks didn't
    already fire at the claim level, so a claim that genuinely retains
    the structure on its own isn't flagged twice for the same underlying
    signal. See those functions' docstrings for why this exists: claim
    extraction's atomization can silently strip Condition/Concession-
    satellite and compound-negation structure that existed in the source
    sentence before any claim-level detector ever sees the claim.
    """
    flags = []
    flag_types_present = set()
    for detector in _DETECTORS_ENGLISH_ONLY:
        flag = detector(english)
        if flag:
            flags.append(flag)
            flag_types_present.add(flag["type"])

    if formal_mode != "logic":
        cond_flag = detect_condition_satellite(english, formal)
        if cond_flag:
            flags.append(cond_flag)
            flag_types_present.add(cond_flag["type"])
        conc_flag = detect_concession_satellite(english, formal)
        if conc_flag:
            flags.append(conc_flag)
            flag_types_present.add(conc_flag["type"])

    modal_flag = detect_modal_mismatch(english, formal, formal_mode=formal_mode)
    if modal_flag:
        flags.append(modal_flag)

    if segment_text:
        if "condition_satellite" not in flag_types_present:
            seg_flag = detect_segment_condition_satellite(segment_text)
            if seg_flag:
                flags.append(seg_flag)
        if "concession_satellite" not in flag_types_present:
            seg_flag = detect_segment_concession_satellite(segment_text)
            if seg_flag:
                flags.append(seg_flag)
        if "negation_scope" not in flag_types_present:
            seg_flag = detect_segment_negation_scope(segment_text)
            if seg_flag:
                flags.append(seg_flag)

    return flags


def compute_tier(flags):
    """Transparent, inspectable tiering rule: sum of per-flag-type weights,
    with overlapping flag types deduplicated first (via _OVERLAPPING_GROUPS,
    currently empty -- see the comment above it) so a single linguistic
    feature can't be counted twice under two different flag types.
    """
    scoring_flags = _dedupe_for_scoring(flags)
    score = sum(_FLAG_WEIGHTS.get(f["type"], 1) for f in scoring_flags)
    if score >= 4:
        return "High"
    if score >= 2:
        return "Medium"
    return "Low"


def annotate_axiom(axiom, mode="english", segment_text=None):
    """Add risk_flags and risk_tier to a single axiom dict, in place.

    Axioms with no formal representation at all (formalize_claims()
    reconciliation left a placeholder because the model dropped that
    claim -- see logic_formalization.py's _reconcile_batch) are given
    risk_tier "Unformalized" and no flags, rather than running the normal
    detectors. Without this check, a claim with e.g. a strong modal in
    the source and formal=None would trip detect_modal_mismatch's "no
    explicit modal marker" branch -- technically true, but misleading:
    the real issue is that formalization failed outright, not that a
    qualifier was quietly softened. "Unformalized" is a distinct,
    differently-actionable signal from the usual Low/Medium/High tiers
    and should be surfaced as such.

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

    Segment-level checks (see flag_claim's docstring) are skipped
    entirely for Unformalized axioms, for the same reason as above --
    piling more flags onto a claim with no formal representation at all
    would dilute that already-distinct signal.

    segment_text, if given, is passed through to flag_claim -- see its
    docstring for what this enables (recovering Condition/Concession-
    satellite/negation-scope structure that claim extraction's atomization
    can strip out of an individual claim before it's ever seen here).
    """
    english = axiom.get("english", "")

    has_formal = bool(
        axiom.get("formal") or axiom.get("formal_logic") or axiom.get("formal_english")
    )
    if not has_formal:
        axiom["risk_flags"] = []
        axiom["risk_tier"] = "Unformalized"
        return axiom

    if mode == "both":
        formal_for_modal_check = axiom.get("formal_english", axiom.get("formal", ""))
        effective_mode = "english"
    else:
        formal_for_modal_check = axiom.get("formal", "")
        effective_mode = mode

    flags = flag_claim(
        english, formal_for_modal_check, formal_mode=effective_mode,
        segment_text=segment_text,
    )
    axiom["risk_flags"] = flags
    axiom["risk_tier"] = compute_tier(flags)
    return axiom


def annotate_axioms(axioms, mode="english", segment_lookup=None):
    """
    segment_lookup: optional dict mapping segment_index -> original source
    sentence text, so annotate_axiom can recover Condition/Concession-
    satellite/negation-scope structure claim extraction stripped out of
    individual claims. See annotate_axiom's and flag_claim's docstrings.
    If not given, segment-level checks are simply skipped (backward
    compatible with existing callers that don't have this lookup handy).
    """
    segment_lookup = segment_lookup or {}
    return [
        annotate_axiom(
            ax, mode=mode,
            segment_text=segment_lookup.get(ax.get("segment_index")),
        )
        for ax in axioms
    ]