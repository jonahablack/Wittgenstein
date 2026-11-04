"""Severance detection: two independent ways to check whether an
atomized claim set preserves a Condition/Exception/Concession/
Elaboration relation identified in a source sentence.

LLM-judge: a single structured yes/no question to the model, given the
original sentence, the elicited relation, and the atomized claims,
asking whether a reader of ONLY the atomized claims would still
correctly understand the satellite-governs-nucleus relationship.
Reasoning is logged for every call so disagreements can be audited by a
human later.

Rule-based check: a cheap, fully inspectable proxy that does NOT call
the model. It checks whether a discourse connective from a fixed
wordlist (matched against the ORIGINAL sentence, not the LLM-elicited
"connective" field, so this check is independent of whether the
elicitation call itself succeeded) survives in at least one atomized
claim, AND whether some claim's content still overlaps with the
nucleus's key terms. This is a COARSER PROXY than the LLM-judge: it
cannot tell whether the connective and the nucleus-reference ended up in
the SAME claim (still properly attached) or in two different claims
(connective present somewhere, nucleus-reference present somewhere else,
but not necessarily still governing each other) -- the spec for this
experiment treats "both exist somewhere in the atomized set" as the
proxy signal, which will sometimes call something "preserved" that the
LLM-judge (reading the claims the way an actual downstream reader would)
correctly calls severed, and vice versa. Both numbers are reported;
disagreement between them is itself part of what run_experiments.py
reports, not smoothed over.

Word-boundary-safe matching is reused directly from risk_triage.py
(_contains_phrase / _boundary_pattern) per this task's instruction not
to reimplement that logic -- see risk_triage.py's own MATCHING NOTE for
why plain substring checks are a real bug class here (e.g. "if" as a
bare substring would match inside "modified").
"""

import os
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SERVER_DIR = os.path.dirname(os.path.dirname(SCRIPT_DIR))
if SERVER_DIR not in sys.path:
    sys.path.insert(0, SERVER_DIR)

from api_call import generate_response  # noqa: E402
from components.response_parsing import extract_json_from_response  # noqa: E402
from components.risk_triage import _contains_phrase  # noqa: E402
from scripts.discourse_severance.corpus import content_keywords  # noqa: E402

# Condition/Exception/Concession connectives, per the task spec. Matched
# against the ORIGINAL sentence (not the elicited "connective" field) so
# the rule-based check is a fully independent signal from the elicitation
# LLM call, not chained to another LLM output.
CONNECTIVE_WORDLIST = [
    "if", "unless", "provided that", "provided", "except when",
    "except that", "except if", "except", "although", "even though",
    "though", "in the event that", "only if", "in case", "assuming",
    "despite", "notwithstanding", "whereas", "otherwise",
]

# Distinctive substring used by self_test.py to recognize this prompt when
# stubbing generate_response.
LLM_JUDGE_PROMPT_MARKER = "Reading ONLY the atomized claims above"


_RELATION_DESCRIPTIONS = {
    "Condition": (
        "a Condition relation: the nucleus is asserted to hold ONLY WHEN/IF "
        "the satellite holds -- if the satellite's truth is not knowable or "
        "is false, the nucleus's applicability here is not established."
    ),
    "Exception": (
        "an Exception relation: the nucleus holds EXCEPT WHEN/UNLESS the "
        "satellite holds -- the satellite carves out a case where the "
        "nucleus does NOT apply."
    ),
    "Concession": (
        "a Concession relation: the nucleus holds EVEN THOUGH/DESPITE the "
        "satellite also being true -- the satellite is acknowledged but "
        "does not defeat the nucleus."
    ),
    "Elaboration": (
        "an Elaboration relation: the satellite is independently-true "
        "supporting detail, example, or restatement about the nucleus. "
        "The satellite does NOT govern, condition, or except the nucleus "
        "-- the nucleus would still be true even if the satellite were "
        "removed. For this relation type, judge whether a reader would "
        "still understand that the satellite's content is additional "
        "detail ABOUT the nucleus (as opposed to being lost, contradicted, "
        "or wrongly attached to something else) -- do NOT judge it against "
        "a governing/conditioning standard that does not apply to "
        "Elaboration."
    ),
    "None": (
        "no specific governing relation -- judge only whether the "
        "atomized claims still convey the same overall content as the "
        "nucleus/satellite text."
    ),
}


def build_llm_judge_prompt(sentence, relation, atomized_claims):
    claims_block = "\n".join(f"- {c}" for c in atomized_claims) or "(no claims produced)"
    relation_type = relation.get("relation_type", "None")
    nucleus = relation.get("nucleus")
    satellite = relation.get("satellite")
    description = _RELATION_DESCRIPTIONS.get(relation_type, _RELATION_DESCRIPTIONS["None"])
    return f"""
Original sentence (context ONLY -- do not base your answer on this,
only on the atomized claims below): "{sentence}"

Discourse relation identified in the original sentence: {relation_type}
Nucleus (the governed/asserted clause): {nucleus!r}
Satellite (the qualifying/supporting clause): {satellite!r}

This is specifically {description}

Atomized claims (this is what a downstream reader would actually see,
with no access to the original sentence):
{claims_block}

{LLM_JUDGE_PROMPT_MARKER}, not the original sentence, would a reader
correctly understand the relationship between the satellite ({satellite!r})
and the nucleus ({nucleus!r}) DESCRIBED ABOVE for this specific relation
type? Judge Condition/Exception/Concession against whether the nucleus's
governing condition/exception/concession is still evident. Judge
Elaboration against whether the satellite's content is still evident as
detail about the nucleus (NOT against a governing standard, since
Elaboration never governs). Answer "false" if the atomized claims would
lead a reader to a different understanding of the relationship than the
original sentence conveyed, or if the relationship is absent or garbled.

Output strict JSON with exactly these keys:
  "preserved": true or false
  "reasoning": one sentence explaining your answer

Return only valid JSON. Do not include Markdown code fences or
additional text.
"""


def llm_judge_severance(sentence, relation, atomized_claims, model=None):
    """Returns {"preserved": bool or None, "reasoning": str}. `preserved`
    is None only on an outright call/parse failure (logged in
    `reasoning`), never as a silent substitute for a real answer.
    """
    prompt = build_llm_judge_prompt(sentence, relation, atomized_claims)
    response = generate_response(prompt, model=model)
    if not response or not hasattr(response, "content"):
        return {"preserved": None, "reasoning": "LLM-judge call failed: no model response."}

    data = extract_json_from_response(response.content)
    if not data:
        return {"preserved": None, "reasoning": "LLM-judge call failed: unparseable JSON response."}

    return {
        "preserved": bool(data.get("preserved")),
        "reasoning": data.get("reasoning", ""),
    }


# --- A1 audit: sub-clause-scoped LLM-judge -----------------------------------
#
# TWO judge interpretations are kept side by side; NEITHER replaces the
# other, and headline numbers from the original run are NOT recomputed
# with the revised prompt:
#
#   judge_prompt_full_nucleus (= build_llm_judge_prompt, above): the
#     ORIGINAL judge. Asks whether the satellite's governing relationship
#     is evident against the FULL elicited nucleus. When the elicited
#     nucleus bundles two coordinated, independently-governed assertions
#     (e.g. "...contains the established name of the drug, AND identifies
#     the drug as a sunscreen" with satellite "if any"), this judge can
#     call "severed" an atomization that correctly narrowed the
#     connective's scope to the one sub-clause the satellite always
#     modified.
#
#   judge_prompt_subclause (= build_llm_judge_prompt_subclause, below):
#     the REVISED judge used ONLY by audit_severance.py (A1 audit) on the
#     bundled-nucleus subset. Asks whether the satellite governs the
#     SPECIFIC sub-clause it originally modified, explicitly telling the
#     judge that scope-narrowing to that sub-clause is correct
#     atomization, not severance.
#
# Distinctive substring for the sub-clause prompt (parallel to
# LLM_JUDGE_PROMPT_MARKER) so stubs/tests can tell the two prompts apart.
LLM_JUDGE_SUBCLAUSE_PROMPT_MARKER = (
    "Reading ONLY the atomized claims above, and judging ONLY against the "
    "specific sub-clause"
)


def build_llm_judge_prompt_subclause(sentence, relation, atomized_claims,
                                      governed_subclause):
    """REVISED (sub-clause-scoped) judge prompt -- see block comment above.

    `governed_subclause` is the specific coordinated sub-clause of the
    bundled elicited nucleus that the satellite originally modified in the
    source sentence (determined by the A1 audit's adjacency analysis, not
    by this function).
    """
    claims_block = "\n".join(f"- {c}" for c in atomized_claims) or "(no claims produced)"
    relation_type = relation.get("relation_type", "None")
    nucleus = relation.get("nucleus")
    satellite = relation.get("satellite")
    description = _RELATION_DESCRIPTIONS.get(relation_type, _RELATION_DESCRIPTIONS["None"])
    return f"""
Original sentence (context ONLY -- do not base your answer on this,
only on the atomized claims below): "{sentence}"

Discourse relation identified in the original sentence: {relation_type}
Full elicited nucleus: {nucleus!r}
Satellite (the qualifying clause): {satellite!r}

This is specifically {description}

IMPORTANT SCOPING NOTE: the full elicited nucleus above BUNDLES two (or
more) coordinated, independently-governed assertions. In the original
sentence, the satellite {satellite!r} modified ONLY this specific
sub-clause of the nucleus:

  Governed sub-clause: {governed_subclause!r}

The other coordinated assertion(s) in the nucleus were never governed by
the satellite. An atomization that attaches the satellite (or its
connective) to the governed sub-clause alone -- narrowing the
connective's scope to the sub-clause it always modified -- is CORRECT
atomization, not a severed relation. Do NOT answer "false" merely
because the satellite is no longer linked to the other, never-governed
assertion(s).

This scoping note does NOT relax the basic evidence requirement: your
answer must be based ONLY on what is actually written in the atomized
claims below. The satellite's qualifying content must still SURVIVE in
some claim, attached to (or clearly qualifying) the governed
sub-clause's content. If the satellite's qualification is missing from
every claim, or appears only as a free-standing assertion with no
qualifying link to the governed sub-clause's content, the relation is
severed and the answer is "false" -- no matter how obvious the
relationship is in the original sentence.

Atomized claims (this is what a downstream reader would actually see,
with no access to the original sentence):
{claims_block}

{LLM_JUDGE_SUBCLAUSE_PROMPT_MARKER} ({governed_subclause!r}), would a
reader correctly understand that the satellite ({satellite!r}) governs
THAT sub-clause, for this specific relation type? First check whether
any atomized claim still expresses the satellite's qualification at all
-- if none does, answer "false". Then answer "true" only if the
satellite's relationship to the governed sub-clause is evident in the
claims as written (whether expressed against the sub-clause alone or
against a span containing it). Answer "false" if the relationship
between the satellite and the governed sub-clause itself is absent,
garbled, or would lead a reader to a different understanding than the
original sentence conveyed.

Output strict JSON with exactly these keys:
  "preserved": true or false
  "reasoning": one sentence explaining your answer

Return only valid JSON. Do not include Markdown code fences or
additional text.
"""


def llm_judge_severance_subclause(sentence, relation, atomized_claims,
                                   governed_subclause, model=None):
    """Sub-clause-scoped variant of llm_judge_severance (A1 audit only).
    Same return shape: {"preserved": bool or None, "reasoning": str};
    `preserved` is None only on an outright call/parse failure.
    """
    prompt = build_llm_judge_prompt_subclause(
        sentence, relation, atomized_claims, governed_subclause
    )
    response = generate_response(prompt, model=model)
    if not response or not hasattr(response, "content"):
        return {"preserved": None, "reasoning": "LLM-judge call failed: no model response."}

    data = extract_json_from_response(response.content)
    if not data:
        return {"preserved": None, "reasoning": "LLM-judge call failed: unparseable JSON response."}

    return {
        "preserved": bool(data.get("preserved")),
        "reasoning": data.get("reasoning", ""),
    }


# Clearly-labeled aliases so both interpretations are addressable by name
# (per the A1 audit spec): the original full-nucleus judge vs the revised
# sub-clause-scoped judge.
judge_prompt_full_nucleus = build_llm_judge_prompt
judge_prompt_subclause = build_llm_judge_prompt_subclause


# --- Elaboration correction (v2): content-recoverability judge -------------
#
# WHY THIS EXISTS, ADDED ALONGSIDE (NOT REPLACING) THE ORIGINAL: a
# full-population reading of every case the original Elaboration judge
# (_RELATION_DESCRIPTIONS["Elaboration"] + build_llm_judge_prompt, above)
# scored severed=false across all four FactoidWiki-track chunkers
# (Propositionizer, AtomicRAG, this project's own baseline, NuggetIndex --
# 126 cases total: 6 + 24 + 19 + 77) found the original judge measurably
# over-strict for this relation type specifically. Direct re-reading of a
# sample spanning all four chunkers (all 6 Propositionizer cases, all 19
# own_baseline cases, 24 AtomicRAG cases, and a stratified sample of 20 of
# NuggetIndex's 77) found roughly 74% of these "severed" verdicts had the
# satellite's actual content fully present in the atomized output -- just
# split into a separate claim/proposition/triple from the nucleus, or
# merged with different phrasing than the original judge's wording
# implicitly wanted -- not genuinely lost.
#
# ROOT CAUSE: the original prompt's closing question asks whether "a
# reader correctly understand[s] the relationship between the satellite
# and the nucleus... as opposed to being... wrongly ATTACHED to something
# else" -- a standard that implicitly demands an explicit textual/lexical
# link surviving between the two (a connective, an "as such"/"for
# example"-style transition, or both facts landing in the very same
# claim). That is a GOVERNING-relation standard (appropriate for
# Condition/Concession/Exception, where the satellite's qualification must
# still visibly attach to the nucleus for the reader not to be misled
# about what governs what) mistakenly applied to Elaboration, which by
# RST's own definition never governs anything.
#
# VERIFIED AGAINST THE RST SOURCE (Carlson & Marcu 2001, "Discourse Tagging
# Reference Manual", pages 53-54 -- read directly, not taken on faith):
#   ELABORATION-ADDITIONAL (#20, mononuclear): "the satellite gives
#     additional information or detail about the situation presented in
#     the nucleus... the default for the family of elaboration relations,
#     and should be used when none of the other, more specific, elaboration
#     relations apply."
#   ELABORATION-GENERAL-SPECIFIC (#21, mononuclear): "The satellite
#     provides specific information to help define a very general concept
#     introduced in the nucleus."
# Neither definition requires the satellite's content to remain in the
# same clause/claim/sentence as the nucleus, or to be linguistically
# marked as subordinate/additional. The test RST actually specifies is:
# is the specific content present, and is it about (topically relevant to,
# specifying/detailing) the nucleus's subject -- not whether a connective
# or shared-claim boundary survived atomization.
#
# ONE EXPLICIT EXCEPTION PRESERVED FROM THE ORIGINAL JUDGE'S INTUITION:
# 11 of the 126 read cases (5 AtomicRAG, 6 NuggetIndex) have the
# satellite's content present but the NUCLEUS itself missing from the
# atomized output entirely -- nothing for the satellite to be "detail
# about". These must still score severed: RST's own definition requires
# "the situation presented in the nucleus" to exist for the satellite to
# elaborate on it, so if the nucleus is not recoverable, Elaboration
# cannot be judged preserved no matter how faithfully the satellite's own
# content survived. The revised prompt below asks this as an explicit
# first-gate question, not left to the model's discretion.
#
# ALSO STILL SEVERED under this revised criterion (this is not a "always
# say preserved for Elaboration" prompt): the satellite's specific content
# is genuinely absent from every atomized unit (not just differently
# split/phrased -- actually missing), OR the atomized output actively
# contradicts or misattributes the content it does carry. The latter
# happens concretely in this project's own NuggetIndex triple-extraction
# output -- e.g. a diagnosis year mechanically mislabeled with the
# predicate "date of birth" (Hayworth's 1980 Alzheimer's diagnosis
# rendered as "Hayworth date of birth 1980"), or a single work's inspiring-
# year-of-composition triples mislabeled "founded in" and attached to the
# wrong subject across four different years. A reader seeing an actively
# wrong/misattributed fact is worse off than a reader seeing no fact at
# all, so this is scored severed, not preserved-with-caveats.
#
# Kept scoped to Elaboration ONLY: Condition/Concession/Exception's
# _RELATION_DESCRIPTIONS entries, judge functions, and prompts above are
# completely untouched by this addition.
LLM_JUDGE_ELABORATION_V2_PROMPT_MARKER = (
    "Reading ONLY the atomized claims above, taken together as a whole set"
)


def build_llm_judge_prompt_elaboration_v2(sentence, relation, atomized_claims):
    """Corrected Elaboration-only judge prompt -- see block comment above
    for the full rationale. Must only be used when
    relation["relation_type"] == "Elaboration"; Condition/Exception/
    Concession/None keep using `build_llm_judge_prompt` (the original)
    unchanged.
    """
    claims_block = "\n".join(f"- {c}" for c in atomized_claims) or "(no claims produced)"
    nucleus = relation.get("nucleus")
    satellite = relation.get("satellite")
    return f"""
Original sentence (context ONLY -- do not base your answer on this,
only on the atomized claims below): "{sentence}"

Discourse relation identified in the original sentence: Elaboration
Nucleus (the general situation being elaborated): {nucleus!r}
Satellite (the additional detail about that situation): {satellite!r}

This is an Elaboration relation: per RST's own definition (Carlson &
Marcu 2001, Elaboration-Additional / Elaboration-General-Specific), the
satellite simply gives additional information, detail, or specific
content about the situation presented in the nucleus. The satellite does
NOT govern, condition, or except the nucleus -- the nucleus would still
be true even if the satellite were removed, and unlike
Condition/Concession/Exception, RST does NOT require the satellite to
stay lexically or structurally attached to the nucleus (no connective,
shared clause, or explicit transition word is required by the relation
itself). The only thing that matters is whether the CONTENT is there and
is topically about the nucleus's subject.

Atomized claims (this is what a downstream reader would actually see,
with no access to the original sentence -- judge the claims TOGETHER, as
the full set a reader would have, not one at a time in isolation):
{claims_block}

{LLM_JUDGE_ELABORATION_V2_PROMPT_MARKER}, not the original sentence,
decide whether the relationship is preserved. Base your answer ONLY on
what is literally stated -- verbatim or as a clear, close paraphrase --
in the atomized claims below. Do not use outside/world knowledge or
plausible inference to fill in content the atomized claims do not
actually convey; but also do not demand every last word or secondary
nuance of the original phrasing survive -- minor loss of secondary
wording or emphasis is fine as long as the core content is genuinely
there.

Step 1 (nucleus gate): is the nucleus's situation ({nucleus!r}) stated
anywhere in the atomized claims -- in one claim, or built up from a
combination of claims, in any wording? If it is NOT stated anywhere at
all, set "nucleus_recoverable": false and answer "preserved": false
immediately -- there is no situation left for the satellite to be detail
about, no matter how well the satellite's own content survived elsewhere.

Step 2 (satellite content check): if the nucleus IS recoverable, set
"nucleus_recoverable": true, then check whether the satellite's SPECIFIC
content ({satellite!r}) is ALSO stated somewhere in the atomized claims
-- in the same claim as the nucleus (perfectly normal if they were
merged together) or a different one, split apart or merged, phrased
identically or paraphrased. No connective or transition word is
required. "Specific" means: if the satellite's original text names a
number, date, named entity, comparison, or reason/cause, that core
specific point should be recoverable somewhere in the atomized claims --
a claim that only gestures at the general topic while dropping the
actual specific point (replacing a concrete number/name/reason with
nothing, with something so generic the point is lost, or with an
unrelated specific from elsewhere in the source) does not satisfy this.

Step 3 (misattribution check -- run this even when steps 1-2 both look
satisfied): does any atomized claim actively CONTRADICT or MISATTRIBUTE
the nucleus's or satellite's content -- assign a fact to the wrong
subject, reverse who-did-what-to-whom, or assert a nonsensical/impossible
value (e.g. one entity with several different "founding"/"published"
dates, or a value that plainly belongs to a different event/person/year
than the one it is attached to)? Check the raw claim text for this, not
just its general topic. If yes, answer "preserved": false -- an actively
wrong claim is worse than a missing one, even if some other claim
elsewhere also carries correct content.

Answer "preserved": true only if step 1 and step 2 both succeed AND step
3 finds no contradiction/misattribution.

Do NOT answer "false" merely because: the satellite's content ended up in
a separate claim from the nucleus with no connective between them; the
claims were merged into one sentence differently than you might have
phrased it; the atomized wording paraphrases rather than quotes the
original; or some minor secondary detail (not the core specific point) is
missing. None of those are severance for Elaboration.

Output strict JSON with exactly these keys:
  "preserved": true or false
  "nucleus_recoverable": true or false
  "reasoning": one or two sentences explaining your answer, quoting or
    pointing to the specific atomized claim(s) that drove the verdict and
    naming which step (1/2/3) was decisive

Return only valid JSON. Do not include Markdown code fences or
additional text.
"""


def llm_judge_severance_elaboration_v2(sentence, relation, atomized_claims, model=None):
    """Corrected Elaboration-only severance judge. Returns
    {"preserved": bool or None, "nucleus_recoverable": bool or None,
    "reasoning": str}. `preserved` is None only on an outright call/parse
    failure, never as a silent substitute for a real answer -- same
    contract as `llm_judge_severance`. `reasoning` is logged verbatim for
    every call (asked to point to the specific atomized claim(s) that
    drove the verdict) so disagreements can be audited later, per this
    project's established "reasoning is logged for every call" convention
    (see module docstring).

    PROMPT ITERATION NOTE (kept here, not just in git history, since this
    project's convention is to document design decisions in-place): this
    prompt went through three iterations against a hand-classified
    validation set before landing here. An early "quote separate,
    non-overlapping evidence for the nucleus and the satellite" framing
    was tried and DISCARDED -- it measurably over-corrected gpt-4o-mini
    (this judge's fixed model choice, kept for comparability with the
    original judge's headline numbers) into fabricating deficiencies even
    on cases where the satellite's content was verbatim present, once the
    nucleus and satellite happened to share one merged claim. The
    surviving design below keeps the two things that validation showed
    actually mattered (the nucleus-recoverable gate, and the
    misattribution carve-out) without the evidence-separation machinery
    that destabilized the model's judgment on straightforward merged
    cases.

    Callers MUST route Elaboration relations to this function and every
    other relation type to `llm_judge_severance` (the original) --
    this function does not itself branch on relation_type, since the
    prompt text above is specific to the Elaboration relation description
    and would misrepresent Condition/Exception/Concession if reused for
    them. See module-level comment block above for why the correction is
    scoped to Elaboration only.
    """
    if relation.get("relation_type") != "Elaboration":
        raise ValueError(
            "FATAL: llm_judge_severance_elaboration_v2 is Elaboration-only; "
            f"got relation_type={relation.get('relation_type')!r}. Use "
            "llm_judge_severance (the original judge) for "
            "Condition/Exception/Concession/None."
        )
    prompt = build_llm_judge_prompt_elaboration_v2(sentence, relation, atomized_claims)
    response = generate_response(prompt, model=model)
    if not response or not hasattr(response, "content"):
        return {
            "preserved": None,
            "nucleus_recoverable": None,
            "reasoning": "LLM-judge call failed: no model response.",
        }

    data = extract_json_from_response(response.content)
    if not data:
        return {
            "preserved": None,
            "nucleus_recoverable": None,
            "reasoning": "LLM-judge call failed: unparseable JSON response.",
        }

    return {
        "preserved": bool(data.get("preserved")),
        "nucleus_recoverable": data.get("nucleus_recoverable"),
        "reasoning": data.get("reasoning", ""),
    }


def rule_based_severance(sentence, relation, atomized_claims):
    """Cheap, non-LLM proxy for severance. See module docstring for the
    coarseness caveat versus the LLM-judge.

    Returns {"rule_based_preserved": bool or None, "rule_based_detail": str}.
    `rule_based_preserved` is None when the check does not apply (no
    wordlist connective found in the original sentence, or no nucleus was
    elicited) -- this is a genuinely different outcome from False and
    must not be conflated with it when aggregating rates.
    """
    nucleus = (relation.get("nucleus") or "").strip()
    sentence_connectives = [
        w for w in CONNECTIVE_WORDLIST if _contains_phrase(sentence.lower(), w)
    ]
    if not sentence_connectives or not nucleus:
        return {
            "rule_based_preserved": None,
            "rule_based_detail": (
                "not applicable: no wordlist connective found in the "
                "original sentence, or no nucleus was elicited."
            ),
        }
    if not atomized_claims:
        return {
            "rule_based_preserved": False,
            "rule_based_detail": "no atomized claims were produced at all.",
        }

    claims_lower = [c.lower() for c in atomized_claims]
    connective_hit = next(
        (
            w for w in sentence_connectives
            if any(_contains_phrase(c, w) for c in claims_lower)
        ),
        None,
    )
    nucleus_keywords = content_keywords(nucleus)
    nucleus_hit = bool(nucleus_keywords) and any(
        content_keywords(c) & nucleus_keywords for c in atomized_claims
    )

    preserved = connective_hit is not None and nucleus_hit
    detail = (
        f"connective {'survives (' + connective_hit + ')' if connective_hit else 'ABSENT'} "
        f"in >=1 atomized claim; nucleus-referencing content "
        f"{'present' if nucleus_hit else 'ABSENT'} in >=1 atomized claim "
        "(coarse proxy: does not require both in the SAME claim)."
    )
    return {"rule_based_preserved": preserved, "rule_based_detail": detail}


def run_severance_checks(sentence, relation, atomized_claims, model=None):
    """Runs both severance checks and returns the combined per-sentence,
    per-condition result shape specified for this experiment.
    """
    llm = llm_judge_severance(sentence, relation, atomized_claims, model=model)
    rb = rule_based_severance(sentence, relation, atomized_claims)
    return {
        "llm_judge_preserved": llm["preserved"],
        "llm_judge_reasoning": llm["reasoning"],
        "rule_based_preserved": rb["rule_based_preserved"],
        "rule_based_detail": rb["rule_based_detail"],
    }
