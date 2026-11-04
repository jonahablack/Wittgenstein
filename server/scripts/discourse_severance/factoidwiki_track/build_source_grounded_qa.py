"""Task-grounded correctness reframe (see the task that authorized this):
replace "is the relationship preserved" (abstract, interpretively
unstable -- kappa=0.62 on the Elaboration audit, and the ensemble-
disagreement check this supersedes found no signal at all, Mann-Whitney
p=0.118) with a constrained, checkable QA task: construct one natural
question per case that specifically probes the relation at risk, answer
it from the atomized/repaired claims ALONE, and score that answer
against the ORIGINAL SOURCE SENTENCE directly.

v2 of the question-construction step (STEP 1), rewritten after a 12-case
review found five real problems in v1 -- see the round of review that
authorized these fixes, applied in this order:

  1. Negation-preservation bug (case 5, exp3-3397): the nucleus's own
     polarity ("not mutually exclusive") got flipped in the constructed
     question ("remain mutually exclusive"). Fixed by an EXPLICIT
     instruction that nucleus polarity is never touched, plus a
     post-hoc automated check (compare negation-bearing dependency
     structure between nucleus and question). exp3-3397 is ALSO flagged
     for exclusion regardless -- its connective ("according to the
     circumstance") is a likely-hallucinated marker, same family as
     prior CFR-track empty-satellite artifacts.
  2. Already-negated-satellite handling (case 1): quantified first --
     12/153 satellites (7.8%) contain a negation marker, rising to
     4/26 (15.4%) for Condition specifically -- not a rare edge case.
     Fixed with an explicit 4-way branch (exceptive/positive x
     negated/positive satellite) with a worked example for each.
  3. Concession pattern REDESIGNED, not patched: "does the nucleus
     still hold given the satellite?" doesn't discriminate a properly-
     concessive reading from two flattened, unlinked facts, because it
     never tests whether the READER understands the satellite was ever
     in apparent tension with the nucleus. Grounded directly in Mann &
     Thompson's own Concession definition (quoted verbatim below, same
     text this project already used and verified in
     ../exception_reclassification.json's addendum): "the writer
     acknowledges a potential or apparent incompatibility between N and
     S, but regards them as compatible." The redesigned question asks
     whether the satellite PREVENTS/CONTRADICTS/RULES OUT the nucleus
     -- correct answer is always NO -- which specifically tests whether
     that resolved incompatibility survives atomization.
  4. Groundedness checker now uses spaCy lemmas (en_core_web_sm),
     replacing the v1 regex word-set diff that false-flagged
     "betrayed"/"betray" and "told"/"tell" as ungrounded.
  5. Deterministic relation-type/connective mismatch flag: a small
     canonical wordlist per relation type (not the full CONNECTIVE_
     WORDLIST from ../severance_detection.py, which pools Condition/
     Concession together) flags cases like exp2-item12 ("While" labeled
     Condition, but "while" here reads concessively) for manual
     exclusion rather than silently applying the wrong pattern.

Usage:
    venv/bin/python server/scripts/discourse_severance/factoidwiki_track/build_source_grounded_qa.py --sample
    venv/bin/python server/scripts/discourse_severance/factoidwiki_track/build_source_grounded_qa.py --full
"""
import json
import os
import re
import sys

import spacy

HERE = os.path.dirname(os.path.abspath(__file__))
PARENT = os.path.dirname(HERE)
SERVER_DIR = os.path.dirname(os.path.dirname(PARENT))
sys.path.insert(0, HERE)
sys.path.insert(0, SERVER_DIR)

from validate_ensemble_disagreement import load_36, load_125  # noqa: E402
from api_call import generate_response  # noqa: E402
from components.response_parsing import extract_json_from_response  # noqa: E402

DEFAULT_MODEL = None  # gpt-4o-mini default, matching every other judge in this project

_NLP = spacy.load("en_core_web_sm")

# Explicit, hand-curated exclusions -- cases whose connective is a
# likely-hallucinated or content-free marker, found by inspection, not
# by this script's own automated checks (kept separate from the
# CONNECTIVE_TYPE_WORDLIST mismatch flag below, which is a broader net).
# Matched by POOL_INDEX, not exact case_id -- round-2 review found
# exp3-3397 has multiple arms (arm_2, arm_3, ...) sharing the same
# relation fields; matching by case_id alone silently let sibling arms
# through (caught only by the type-mismatch backstop that round).
HAND_EXCLUDED_POOL_INDICES = {
    3397,  # connective "according to the circumstance" -- vague, not a canonical Condition marker
    3980,  # satellite duplicates the nucleus's own clause verbatim ("However, " + repeat)
           # -- produced a self-contradictory question ("does X mean not-X").
           # 3 arms in the 153-set (arm_2/3/4), all sharing this relation.
    1964,  # connective "Rather" -- Mann & Thompson Antithesis/correction ("not X,
           # rather Y"), not Concession (N holds despite S). Single instance.
    2769,  # satellite is a VERBATIM duplicate of the nucleus ("However, " + repeat)
           # -- same self-contradictory-question pattern as pool 3980, found by
           # the satellite_nucleus_duplication_check scan this pattern motivated.
    4707,  # satellite is the nucleus's own first clause repeated (a "but"-
           # conjoined compound sentence where nucleus captured BOTH halves
           # and satellite re-states only the first) -- elicitation boundary
           # error, not necessarily unusable, but excluded for the same
           # duplication reason as 2769/3980 rather than judgment-called in.
    5132,  # satellite's entire content is nested verbatim inside the nucleus's
           # own parenthetical -- nucleus/satellite boundary elicitation error.
}
# Reviewed and KEPT despite tripping the >=60% duplication check (0.67
# overlap each): exp2-item5/item13 ("their system of descent was
# matrilineal" / "this has been challenged by..."). Unlike the pools
# above, the satellite here adds genuine new critical content (a named
# counter-argument) rather than restating the nucleus -- the lemma
# overlap is topical (both discuss "descent"/"matrilineal"/"system"),
# not duplication. Confirmed by re-reading both cases, not assumed.
# Exact-match exclusions for cases with no pool_index (the 36-item sheet
# uses "exp2-itemN" ids) or that need excluding individually rather than
# by whole pool: exp2-item6's satellite ("If this is not done") contains
# a dangling pronoun ("this") whose antecedent -- "double working" / "a
# piece of pear graft-work used as an intermediate" -- is in an EARLIER
# sentence of the source paragraph, present in NEITHER the elicited
# nucleus NOR satellite field. Confirmed non-random: regenerated the
# question independently 4 times (temperature/sampling variance only,
# same prompt) and the satellite-inversion step failed to fire on all 4
# -- not noise, a genuine under-specification given this project's own
# grounding rule (construct the question from nucleus/satellite/
# connective alone, never the source paragraph). A heuristic scan for
# the same "dangling pronoun" pattern flagged 16 more candidates, but
# spot-checking (exp2-item5/13, exp2-item7, exp2-item22/23/35,
# exp3-2004, exp3-3454, exp3-4099, exp3-4992) found each of those
# pronouns resolves to content already present IN the nucleus itself --
# not dangling. Only exp2-item6 has the genuine problem.
HAND_EXCLUDED_CASE_IDS = {
    "exp2-item6",   # dangling-pronoun satellite, antecedent outside nucleus/satellite (see docstring)
    "exp2-item12",  # relation-type/connective mismatch: "while" labeled Condition, reads Concession
    "exp2-item36",  # relation-type/connective mismatch: "while" labeled Condition, reads Concession
}
# Consolidated, persistent exclusions from the full round-4 review pass:
# relation-type/connective mismatches (3 distinct source relations,
# collapsed from 10 raw flagged instances across Exp3 arms -- see the
# limitations-language note below), degenerate/empty satellites, and a
# JSON-generation failure that didn't resolve on retry.
HAND_EXCLUDED_POOL_INDICES_EXTRA = {
    2965,  # "while" mislabeled Condition (survivin case, reads Concession)
    4351,  # "while" mislabeled Condition (Mister Donut case, reads Concession)
    2098,  # "except" mislabeled Concession (Duke of Devonshire case, reads Condition)
    2786,  # degenerate satellite: "However" alone, no content
    2901,  # degenerate satellite: "Though"/"Although" alone, no content
    3137,  # question generation failed twice (unparseable JSON), not resolved on retry
}
# LIMITATIONS-TEXT NOTE (verbatim framing agreed for the manuscript):
# "3 distinct source relations, primarily traceable to 'while''s
# documented discourse-marker polysemy, out of approximately 45-50
# underlying relations in the sample" -- NOT "10 out of 153", which
# would conflate repeated Exp3-arm instances of the same 3 underlying
# relations with independent elicitation failures.

CONDITION_EXCEPTIVE = {"unless", "except", "except when", "except that", "except if"}
CONDITION_POSITIVE = {"if", "when", "provided that", "provided", "upon", "once", "in the event of",
                       "in the event", "in case", "as soon as", "on condition that", "on the condition that",
                       "depending on", "whether"}
CONCESSION_CANONICAL = {"although", "though", "even though", "despite", "in spite of", "however",
                         "while", "whilst", "yet", "nevertheless", "nonetheless", "even so", "but",
                         "contrary to", "even when", "even if"}
# "rather" removed (round-4 finding): it marks Antithesis/correction
# ("not X, rather Y"), not Concession (N holds despite S) -- confirmed
# on exp3-1964, where the "prevent" framing produced a technically-
# answerable but structurally mismatched question. Now falls through to
# the "not in either canonical wordlist" branch and gets flagged.

NEG_RE = re.compile(r"\b(not|n't|never|cannot|can't|no longer|without)\b", re.IGNORECASE)


def connective_type_mismatch(relation_type, connective):
    """Deterministic check (fix 5): does the claimed relation_type match
    a canonical wordlist for that type? Returns a flag string or None.
    """
    c = connective.strip().lower()
    if relation_type == "Condition":
        if c in CONDITION_EXCEPTIVE or c in CONDITION_POSITIVE:
            return None
        if c in CONCESSION_CANONICAL:
            return f"connective {c!r} is canonically Concession, not Condition -- relation_type label suspect"
        return f"connective {c!r} not in either canonical wordlist -- verify manually"
    if relation_type == "Concession":
        if c in CONCESSION_CANONICAL:
            return None
        if c in CONDITION_EXCEPTIVE or c in CONDITION_POSITIVE:
            return f"connective {c!r} is canonically Condition, not Concession -- relation_type label suspect"
        return f"connective {c!r} not in either canonical wordlist -- verify manually"
    return f"unexpected relation_type {relation_type!r}"


CONDITION_PATTERN = """
This is a CONDITION relation. First determine which case applies, based
on the connective {connective!r}:

CASE A -- EXCEPTIVE (connective is "unless"/"except"/"except when"/
"except that"): the nucleus holds UNLESS/EXCEPT WHEN the satellite's
circumstance occurs. Construct a question asking whether the nucleus's
claim holds WHEN the satellite's circumstance DOES occur, using the
satellite's stated polarity EXACTLY AS WRITTEN (do not add or remove a
negation on the satellite side). Worked example: satellite "unless the
contract specifies otherwise" -> question "does the rule apply if the
contract specifies otherwise?" (satellite polarity untouched).

CASE B -- POSITIVE (connective is "if"/"when"/"provided that"/"upon"/
"once"/"in the event of"/etc.): the nucleus holds ONLY WHEN the
satellite's circumstance occurs. Construct a question asking whether the
nucleus's claim holds when the satellite's circumstance does NOT occur
-- this requires INVERTING the satellite's polarity:
  - If the satellite is already phrased negatively (contains "not",
    "n't", "never", "without", etc.), the inverted circumstance is the
    POSITIVE version (remove the negation). Worked example: satellite
    "if this is not done" -> inverted circumstance "this IS done" ->
    question "does the outcome still happen if this is done?"
  - If the satellite is phrased positively, the inverted circumstance
    ADDS a negation. Worked example: satellite "upon ratification by
    2/3 of members" -> inverted circumstance "NOT ratified" -> question
    "does it enter into force if it is not ratified?"

CRITICAL, applies to BOTH cases: the NUCLEUS's own polarity must be
preserved EXACTLY as stated in the question -- if the nucleus says
"...is NOT mutually exclusive", your question must refer to it as "not
mutually exclusive" or an accurate paraphrase that keeps the negation.
NEVER add or drop a negation on the nucleus side. Only the SATELLITE's
circumstance is inverted (Case B) or preserved as-is (Case A) -- the
rules above never touch the nucleus.
"""

# REPLACED (round after the "prevent" pattern was confirmed degenerate:
# flat 92.9%/94.1% correct across old-severed/old-preserved buckets,
# because "does S prevent N?" is theoretically "No" for EVERY genuine
# Concession relation by Mann & Thompson's own definition -- the
# question's correct answer never varies with whether severance
# happened, so no amount of prompt calibration could make it
# discriminate). The old CONCESSION_PATTERN string is intentionally not
# kept as a fallback; do not reintroduce it.
#
# New design: two-part structural-legibility check, kept as SEPARATE
# questions (not ANDed into one compound sentence) so each part can be
# independently answered and scored. Both must be affirmed for the
# relation to count as preserved.
#   Part (a): does the CLAIMS' OWN FRAMING present the satellite as
#     contrasting with/qualifying the nucleus? This is a direct check on
#     what the claims themselves assert (do they use any contrastive/
#     concessive connection, marked or unmarked), NOT a hypothetical
#     "would a reader expect X to argue against Y" simulation -- the
#     hypothetical-reader-expectation framing was flagged as an
#     abstract-reasoning risk and deliberately avoided here.
#   Part (b): is the nucleus's own content stated to be the case at all
#     (a bare recoverability check, independent of the contrast).
CONCESSION_PATTERN_PART_A = """
This is Part (a) of a two-part CONCESSION check. Mann & Thompson (2001)
define Concession as: the writer acknowledges a POTENTIAL OR APPARENT
INCOMPATIBILITY between the nucleus (N) and satellite (S), but treats
them as compatible.

Construct a question that checks, directly from the claims' own
framing, whether the satellite's circumstance is presented as something
that CONTRASTS WITH or QUALIFIES the nucleus -- i.e. whether the claims
themselves connect the two (with an explicit contrastive/concessive
marker, or an unmarked but clear juxtaposition), not whether a
hypothetical reader would expect one to argue against the other. Phrase
it as: "According to the claims, is [satellite, restated] presented as
a fact that contrasts with or qualifies [nucleus, restated]?"

Worked example: satellite "despite the rain" + nucleus "the game went
ahead" -> "According to the claims, is it presented that it rained, in
a way that contrasts with the game going ahead?"
"""

CONCESSION_PATTERN_PART_B = """
This is Part (b) of a two-part CONCESSION check -- a bare
recoverability check, independent of Part (a)'s contrast check.

Construct a question asking whether the nucleus's own content is stated
to be the case at all: "According to the claims, is [nucleus, restated]
stated to be the case?"

Worked example: nucleus "the game went ahead" -> "According to the
claims, did the game go ahead?"
"""

QUESTION_PATTERNS = {"Condition": CONDITION_PATTERN}  # Concession now uses the two-part builder below

# --- Concession, single-question synthesis pattern (3rd design) --------
# Third attempt at a Concession question pattern, after (1) "does S
# prevent N?" (confirmed degenerate: flat 92.9%/94.1%, theoretically
# always "No" for a genuine Concession relation) and (2) the two-part
# A/B contrast-legibility check (looked clean at n=20, 60%/80% gap,
# p not computed at the time; collapsed to 58.8%/63.8% at n=103, Fisher
# p=0.67, not significant). This one is deliberately the simplest
# possible design: ONE open-ended synthesis question, scored with the
# SAME answer-from-claims/answer-from-source/match-scoring machinery
# already used and validated for Condition (score_source_grounded_
# answers.score_case) -- no new scoring architecture, no AND-gate
# combining two sub-verdicts. If this also fails to discriminate at
# scale, that starts to look like a property of the Concession relation
# type under this whole evaluation paradigm, not of any one question
# design.
CONCESSION_SYNTHESIS_PATTERN = """
This is a CONCESSION relation. Construct ONE open-ended synthesis
question that asks the reader to state BOTH: (a) what is asserted about
the nucleus's content, and (b) what qualifying/complicating circumstance
(the satellite) is mentioned in connection with it. Phrase it naturally,
following this template: "What is stated about [nucleus, restated], and
what qualifying or complicating circumstance is mentioned in connection
with it?"

Worked example: satellite "despite the rain" + nucleus "the game went
ahead" -> "What is stated about the game going ahead, and what
qualifying or complicating circumstance is mentioned in connection with
it?" (a complete answer would need to mention both that the game went
ahead AND that it rained).

This is NOT a yes/no question -- it requires a short synthesis answer
naming both the nucleus's content and the satellite's content, which
means a claims-only reader who has lost the specific connection between
them, or lost either piece of content outright, cannot produce a
complete matching answer.
"""


def build_concession_synthesis_prompt(item):
    """Single-question Concession builder, output-compatible with
    build_question_construction_prompt (same "question" key) so it can
    be scored by score_source_grounded_answers.score_case() unmodified.
    """
    r = item["relation"]
    return f"""
You are constructing ONE natural-language question that probes a specific
discourse relation at risk of being lost during text splitting/repair.

Relation type: {item['relation_type']}
Nucleus (the governed/asserted clause): {r['nucleus']!r}
Satellite (the qualifying/conceding clause): {r['satellite']!r}
Connective: {r['connective']!r}

{CONCESSION_SYNTHESIS_PATTERN}

STRICT GROUNDING RULE: use ONLY the content in the nucleus and satellite
text above. Do not invent, assume, or add any fact, name, date, or detail
that is not already present in those two fields. Do not use the original
source paragraph (you have not been shown it) -- construct the question
from the nucleus/satellite/connective alone.

Output strict JSON with exactly these keys:
  "question": the single constructed question, as a natural sentence
  "expected_answer_if_relation_preserved": your best short answer to the
    question, reasoning ONLY from the nucleus/satellite/connective --
    this is a sanity-check field, not used as ground truth
  "grounding_note": one sentence confirming which words/phrases in the
    question trace back to the nucleus or satellite text

Return only valid JSON. Do not include Markdown code fences or additional
text.
"""


def construct_concession_synthesis_question(item, model=None):
    model = model or DEFAULT_MODEL
    prompt = build_concession_synthesis_prompt(item)
    response = generate_response(prompt, model=model)
    if not response or not hasattr(response, "content"):
        return {"question": None, "expected_answer_if_relation_preserved": None,
                "grounding_note": None, "error": "call failed: no response"}
    data = extract_json_from_response(response.content)
    if not data:
        return {"question": None, "expected_answer_if_relation_preserved": None,
                "grounding_note": None, "error": "call failed: unparseable JSON"}
    return {
        "question": data.get("question"),
        "expected_answer_if_relation_preserved": data.get("expected_answer_if_relation_preserved"),
        "grounding_note": data.get("grounding_note"),
        "error": None,
    }


def build_question_construction_prompt(item):
    """Condition only -- Concession now uses build_concession_two_part_prompt."""
    r = item["relation"]
    pattern = QUESTION_PATTERNS["Condition"].format(connective=r["connective"])
    return f"""
You are constructing ONE natural-language question that probes a specific
discourse relation at risk of being lost during text splitting/repair.

Relation type: {item['relation_type']}
Nucleus (the governed/asserted clause): {r['nucleus']!r}
Satellite (the qualifying/conceding clause): {r['satellite']!r}
Connective: {r['connective']!r}

{pattern}

STRICT GROUNDING RULE: use ONLY the content in the nucleus and satellite
text above. Do not invent, assume, or add any fact, name, date, or detail
that is not already present in those two fields. Do not use the original
source paragraph (you have not been shown it) -- construct the question
from the nucleus/satellite/connective alone.

The question must be answerable with a short factual answer (ideally
yes/no, or a short phrase) by someone who has ONLY the text they are
given (either the atomized claims, or the original source) -- not
requiring outside knowledge.

Output strict JSON with exactly these keys:
  "question": the single constructed question, as a natural sentence
  "expected_answer_if_relation_preserved": your best short answer to the
    question, reasoning ONLY from the nucleus/satellite/connective
    (i.e., what the answer SHOULD be if the source's governing relation
    is correctly understood) -- this is a sanity-check field, not used
    as ground truth (ground truth is scored against the actual source
    sentence separately)
  "grounding_note": one sentence confirming which words/phrases in the
    question trace back to the nucleus or satellite text

Return only valid JSON. Do not include Markdown code fences or additional
text.
"""


def build_concession_two_part_prompt(item):
    r = item["relation"]
    return f"""
You are constructing TWO natural-language questions that together probe
a CONCESSION relation at risk of being lost during text splitting/repair.

Nucleus (the governed/asserted clause): {r['nucleus']!r}
Satellite (the qualifying/conceding clause): {r['satellite']!r}
Connective: {r['connective']!r}

{CONCESSION_PATTERN_PART_A}

{CONCESSION_PATTERN_PART_B}

STRICT GROUNDING RULE: use ONLY the content in the nucleus and satellite
text above. Do not invent, assume, or add any fact, name, date, or detail
not already present in those two fields. Do not use the original source
paragraph (you have not been shown it).

Both questions must be answerable with a short factual answer (ideally
yes/no) by someone who has ONLY the text they are given (either the
atomized claims, or the original source) -- not requiring outside
knowledge.

Output strict JSON with exactly these keys:
  "question_a": Part (a)'s constructed question (the contrast/
    qualification check)
  "question_b": Part (b)'s constructed question (the bare nucleus-
    recoverability check)
  "grounding_note": one sentence confirming which words/phrases in each
    question trace back to the nucleus or satellite text

Return only valid JSON. Do not include Markdown code fences or additional
text.
"""


def construct_question(item, model=None):
    """Condition only."""
    model = model or DEFAULT_MODEL
    prompt = build_question_construction_prompt(item)
    response = generate_response(prompt, model=model)
    if not response or not hasattr(response, "content"):
        return {"question": None, "expected_answer_if_relation_preserved": None,
                "grounding_note": None, "error": "call failed: no response"}
    data = extract_json_from_response(response.content)
    if not data:
        return {"question": None, "expected_answer_if_relation_preserved": None,
                "grounding_note": None, "error": "call failed: unparseable JSON"}
    return {
        "question": data.get("question"),
        "expected_answer_if_relation_preserved": data.get("expected_answer_if_relation_preserved"),
        "grounding_note": data.get("grounding_note"),
        "error": None,
    }


def construct_concession_two_part_questions(item, model=None):
    model = model or DEFAULT_MODEL
    prompt = build_concession_two_part_prompt(item)
    response = generate_response(prompt, model=model)
    if not response or not hasattr(response, "content"):
        return {"question_a": None, "question_b": None, "grounding_note": None,
                "error": "call failed: no response"}
    data = extract_json_from_response(response.content)
    if not data:
        return {"question_a": None, "question_b": None, "grounding_note": None,
                "error": "call failed: unparseable JSON"}
    return {
        "question_a": data.get("question_a"),
        "question_b": data.get("question_b"),
        "grounding_note": data.get("grounding_note"),
        "error": None,
    }


def _lemmas(text, min_len=4):
    doc = _NLP(text)
    return {t.lemma_.lower() for t in doc if t.is_alpha and len(t.lemma_) >= min_len and not t.is_stop}


def _has_neg(text):
    doc = _NLP(text)
    return any(t.dep_ == "neg" for t in doc) or bool(NEG_RE.search(text))


# Scaffold vocabulary introduced BY THE QUESTION TEMPLATES THEMSELVES
# (CONDITION_PATTERN / CONCESSION_PATTERN), not extracted from any
# case's nucleus/satellite -- e.g. every Concession question contains
# "prevent" by design (see the pattern's worked example), which is not
# invented content and must not be flagged as such. Found by spot-
# checking round-3's "UNGROUNDED" flags: all 4 sampled were either this
# scaffold vocabulary or a legitimate paraphrase (nominalization: "too
# dusty, too rough" -> "dustiness, roughness") the lemmatizer doesn't
# resolve -- not one was genuine invented content.
_SCAFFOLD_LEMMAS = {
    "prevent", "contradict", "rule", "stop", "case", "true", "hold",
    "apply", "outcome", "circumstance", "claim", "assertion",
}


def satellite_nucleus_duplication_check(nucleus, satellite, threshold=0.6):
    """Round-4 addition: flags cases where the satellite substantially
    duplicates the nucleus's own content (found on exp3-3980, whose
    satellite restated the nucleus's clause verbatim plus extra
    material -- produced a self-contradictory question, "does X mean
    not-X"). Crude lemma-overlap threshold, not exact; a positive flag
    means "verify manually," not "definitely broken."
    """
    nuc_lemmas = _lemmas(nucleus)
    sat_lemmas = _lemmas(satellite)
    if not nuc_lemmas or not sat_lemmas:
        return {"duplicated": False, "overlap": 0.0}
    overlap = len(nuc_lemmas & sat_lemmas) / min(len(nuc_lemmas), len(sat_lemmas))
    return {"duplicated": overlap >= threshold, "overlap": round(overlap, 2)}


# Scaffold verbs the Concession pattern uses to frame its question (see
# CONCESSION_PATTERN) -- everything BEFORE this verb in the constructed
# question is satellite-derived (its negation is inherited from the
# satellite's own wording and must NOT be checked against the nucleus);
# everything AFTER is nucleus-derived (its negation SHOULD match the
# nucleus's own polarity). Round-4 fix: the v1 checker compared negation
# counts across the WHOLE question, which false-flagged cases like
# exp3-3759 where the satellite legitimately carries its own "not"
# (confirmed via spot-check last round -- the checker, not the question,
# was wrong there).
_CONCESSION_SCAFFOLD_VERBS = ("prevent", "contradict", "rule out", "stop")


def _split_at_scaffold_verb(question):
    ql = question.lower()
    for v in _CONCESSION_SCAFFOLD_VERBS:
        idx = ql.find(v)
        if idx != -1:
            return question[:idx], question[idx + len(v):]
    return None, None


def groundedness_check(question, nucleus, satellite, connective):
    """Fix 4: lemma-based (spaCy), not raw word-form regex. Excludes the
    question templates' own scaffold vocabulary (see _SCAFFOLD_LEMMAS)
    from the ungrounded count -- that vocabulary is intentional test
    framing, not content the model invented.
    """
    if not question:
        return {"grounded": False, "ungrounded_words": None}
    q_lemmas = _lemmas(question) - _SCAFFOLD_LEMMAS
    source_lemmas = _lemmas(f"{nucleus} {satellite} {connective}")
    ungrounded = sorted(q_lemmas - source_lemmas)
    grounded = len(ungrounded) <= 2
    return {"grounded": grounded, "ungrounded_words": ungrounded}


def nucleus_polarity_check(question, nucleus, relation_type=None, connective=None):
    """Fix 1 (round 3) + round-4 fix for inherited-negation blindness on
    Concession questions. Heuristic, not exact -- flags for human
    review, does not silently drop cases.

    Three cases:
    1. Condition positive-branch (connective in CONDITION_POSITIVE): the
       satellite's circumstance is INTENTIONALLY inverted by design (see
       CONDITION_PATTERN Case B) -- skipped, not checked, since a
       negation change there is expected, not an error.
    2. Concession ("prevent"-pattern) questions: round-4 fix. The v1
       check compared negation counts across the WHOLE question, which
       false-flagged real cases (exp3-3759) where the SATELLITE
       legitimately carries its own "not" -- confirmed by spot-check,
       the checker was wrong there, not the question. Now splits the
       question at its scaffold verb ("prevent"/"contradict"/etc, see
       _CONCESSION_SCAFFOLD_VERBS): the clause BEFORE it is satellite-
       derived (its negation is never checked -- inherited, expected);
       the clause AFTER it ("...from being true?") is nucleus-derived,
       and ONLY that clause's negation is compared to the nucleus's own.
       This still cannot resolve every case (verbs like "protect from"
       carry an implicit negation no token-level check sees -- e.g. a
       nucleus reading "X didn't protect Y from Z" vs. a question asking
       "does [satellite] prevent Y from experiencing Z" are semantically
       equivalent but token-level opposite; that specific pattern is
       not resolved here and would still need a human glance if it
       recurs) -- reported as a known residual limitation, not silently
       claimed as solved.
    3. Everything else (Condition exceptive, or no scaffold verb found):
       falls back to the v1 whole-question comparison, gated by the
       overlap check (skip if the question isn't substantially a
       restatement of the nucleus).
    """
    if relation_type == "Condition" and connective and connective.strip().lower() in CONDITION_POSITIVE:
        return {"polarity_ok": True, "note": "skipped: Condition positive-branch intentionally inverts satellite polarity"}
    if not question:
        return {"polarity_ok": False, "note": "no question generated"}

    nuc_neg = _has_neg(nucleus)

    if relation_type == "Concession":
        before, after = _split_at_scaffold_verb(question)
        if after is not None:
            after_neg = _has_neg(after)
            ok = nuc_neg == after_neg
            return {
                "polarity_ok": ok,
                "note": f"[scaffold-split] nucleus_neg={nuc_neg}, post-scaffold-clause_neg={after_neg} "
                        f"(satellite-derived clause {'before' if before else ''!r} not checked)",
            }

    # Fallback: v1 whole-question comparison (Condition-exceptive, or no
    # scaffold verb matched).
    nuc_lemmas = _lemmas(nucleus)
    q_lemmas = _lemmas(question)
    overlap = len(nuc_lemmas & q_lemmas) / len(nuc_lemmas) if nuc_lemmas else 0
    if overlap < 0.4:
        return {"polarity_ok": True, "note": "question does not substantially restate the nucleus; skipped", "overlap": round(overlap, 2)}
    q_neg = _has_neg(question)
    ok = nuc_neg == q_neg
    return {"polarity_ok": ok, "note": f"[whole-question] nucleus_neg={nuc_neg}, question_neg={q_neg}", "overlap": round(overlap, 2)}


def is_hand_excluded(item):
    if item["case_id"] in HAND_EXCLUDED_CASE_IDS:
        return True
    if item["source_set"] == "exp3_125":
        pool_index = int(item["case_id"].split("-")[1])
        if pool_index in HAND_EXCLUDED_POOL_INDICES or pool_index in HAND_EXCLUDED_POOL_INDICES_EXTRA:
            return True
    return False


def pick_review_sample(items, n=12, extra_concession=0):
    seen_connectives = set()
    sample = []
    for it in sorted(items, key=lambda x: x["relation_type"] != "Condition"):
        if is_hand_excluded(it):
            continue
        c = it["relation"]["connective"].strip().lower()
        if c not in seen_connectives:
            seen_connectives.add(c)
            sample.append(it)
        if len(sample) >= n:
            break
    if extra_concession:
        used_ids = {it["case_id"] for it in sample}
        extra = [it for it in items if it["relation_type"] == "Concession"
                 and it["case_id"] not in used_ids and not is_hand_excluded(it)]
        sample += extra[:extra_concession]
    return sample


def main():
    items = load_36() + load_125()
    mode = sys.argv[1] if len(sys.argv) > 1 else "--sample"

    if mode == "--sample":
        sample = pick_review_sample(items, n=12, extra_concession=4)
        print(f"Reviewing {len(sample)} cases (same 12 as round 1, plus 4 new Concession cases)\n")
        results, n_flagged = process_items(sample, verbose=True)
        print(f"SUMMARY: {n_flagged}/{len(sample)} cases flagged by at least one automated check")
        out_path = os.path.join(HERE, "results", "qa_question_sample_review_v2.json")
        json.dump(results, open(out_path, "w", encoding="utf-8"), indent=2)
        print(f"Saved to {out_path}")

    elif mode == "--full":
        excluded = [it for it in items if is_hand_excluded(it)]
        kept = [it for it in items if not is_hand_excluded(it)]
        print(f"Total cases: {len(items)} | hand-excluded: {len(excluded)} "
              f"({[it['case_id'] for it in excluded]}) | proceeding on: {len(kept)}")

        # Reuse round-2's already-generated results (16 cases) instead of
        # re-spending API budget on them.
        prior_path = os.path.join(HERE, "results", "qa_question_sample_review_v2.json")
        prior_by_id = {}
        if os.path.exists(prior_path):
            for r in json.load(open(prior_path, encoding="utf-8")):
                prior_by_id[r["case_id"]] = r
        already_done = [it for it in kept if it["case_id"] in prior_by_id]
        remaining = [it for it in kept if it["case_id"] not in prior_by_id]
        print(f"Reusing {len(already_done)} already-generated results from round-2 review; "
              f"generating {len(remaining)} new.")

        new_results, n_flagged_new = process_items(remaining, verbose=False)
        all_results = [prior_by_id[it["case_id"]] for it in already_done] + new_results
        n_flagged_total = sum(
            1 for r in all_results
            if r.get("connective_type_mismatch") or not r["groundedness"]["grounded"]
            or not r["polarity_check"]["polarity_ok"]
        )
        print(f"\nFull run: {len(all_results)} questions constructed, "
              f"{n_flagged_total} flagged by at least one automated check.")
        out_path = os.path.join(HERE, "results", "qa_questions_full.json")
        json.dump(all_results, open(out_path, "w", encoding="utf-8"), indent=2)
        print(f"Saved to {out_path}")
    else:
        print(f"Unknown mode {mode!r}")


def process_items(sample, verbose=True):
    results = []
    n_flagged = 0
    for i, item in enumerate(sample, 1):
        r = item["relation"]
        mismatch = connective_type_mismatch(item["relation_type"], r["connective"])
        q = construct_question(item)
        gc = groundedness_check(q["question"], r["nucleus"], r["satellite"], r["connective"])
        pc = nucleus_polarity_check(q["question"], r["nucleus"], item["relation_type"], r["connective"])
        rec = {**item, "question_construction": q, "groundedness": gc, "polarity_check": pc,
               "connective_type_mismatch": mismatch}
        results.append(rec)
        flags = []
        if mismatch:
            flags.append("TYPE-MISMATCH")
        if not gc["grounded"]:
            flags.append("UNGROUNDED")
        if not pc["polarity_ok"]:
            flags.append("POLARITY-MISMATCH")
        if flags:
            n_flagged += 1
        tag = f" | FLAGS: {', '.join(flags)}" if flags else ""
        if verbose:
            print(f"[{i}/{len(sample)}] {item['case_id']} | {item['relation_type']} | "
                  f"connective={r['connective']!r}{tag}")
            print(f"    nucleus:   {r['nucleus']}")
            print(f"    satellite: {r['satellite']}")
            print(f"    QUESTION: {q['question']}")
            print(f"    expected answer: {q['expected_answer_if_relation_preserved']}")
            if mismatch:
                print(f"    connective_type_mismatch: {mismatch}")
            if not pc["polarity_ok"]:
                print(f"    polarity_check: {pc['note']}")
            print()
        else:
            sys.stderr.write(f"[{i}/{len(sample)}] {item['case_id']}{tag}\n")
            sys.stderr.flush()
    return results, n_flagged


if __name__ == "__main__":
    main()
