"""Task 6, Stage 2: adversarial/skeptical verification of a Stage-1
(relation_classifier.py) Condition/Concession candidate that has already
survived Stage 1.5's free hallucination filter (candidate_prefilter.py).

WHY A SECOND, SEPARATE CALL WITH A DIFFERENT PROMPT STRUCTURE: two rounds
of prompt tuning on the single-stage classifier (Task 5 -> Task 5b, see
README.md) failed to reach reliable precision -- Concession improved
(46.5-53.5%) but Condition did not (24.5-34.0%), and a 5th failure mode
(nucleus/satellite misattachment and hallucinated connectives) emerged
that neither revision targeted. Asking the SAME model, with a re-worded
version of the SAME "classify this paragraph" question, to double-check
its own kind of output risks reproducing the same blind spots that
produced the error in the first place. This module instead asks a
DIFFERENT question in a DIFFERENT frame: not "what is the relation here"
(generative, classify-from-scratch) but "here is a specific claim someone
already made about this paragraph -- try to prove it wrong" (adversarial,
falsification-first). The candidate is presented as something to
stress-test, not as a proposal to charitably confirm, and the model must
explicitly rule out five specific, named failure modes (four already
catalogued by Task 5's and Task 5b's spot-checks, plus the 5th) before it
is allowed to confirm anything.

MODEL CHOICE FOR STAGE 2: gpt-4o (see DEFAULT_STAGE2_MODEL), not
gpt-4o-mini (Stage 1's model). Reasoning, so this is a decision and not
just a default:
  - Same-family, larger/more-capable sibling of Stage 1's model, which
    the task brief itself gave as the representative example of
    "stronger or differently configured" -- and it is a real capability
    step up from mini, which is what actually matters here (asking a
    materially more careful reader to find the mistakes a cheaper, faster
    reader made), not a difference in family/vendor per se.
  - A reasoning-tier model (o1/o3-mini) was considered and rejected for
    THIS step specifically: (a) this task is bounded reading-comprehension
    plus rule-application against five explicitly named checks, not open-
    ended multi-step search or math, where reasoning models earn their
    extra cost/latency most clearly; (b) o-series models have historically
    restricted or rejected standard chat-completion sampling parameters,
    and this project's api_call.generate_response hard-codes
    temperature=0/seed=13 on every call for run-to-run determinism --
    silently special-casing that shared call path for one model family
    is exactly the kind of implicit, non-obvious behavior this repo's
    "no hidden fallbacks" philosophy warns against; (c) gpt-4o's behavior,
    latency, and cost are well-characterized already, whereas this API
    key also exposes several newer model names this project has no prior
    experience with -- given the goal is a defensible, inspectable
    pipeline rather than a model-shopping exercise, the known, explicitly-
    suggested choice was preferred over speculating about unfamiliar ones.
  - Verified callable with this project's existing generate_response()
    call path (same temperature=0/seed=13 args) before building this
    module around it.
  - Cost/latency at this validation run's scale (survivors are a MINORITY
    of paragraphs screened, not all of them) is not a real constraint --
    consistent with this track's repeated finding that LLM cost/time has
    never been the binding constraint here, only precision has.

CONFIRMATION IS COMPUTED PROGRAMMATICALLY, NOT SELF-REPORTED: the model is
asked to answer each of the five checks independently (an "applies"
boolean plus a one-sentence reason each), and this module's
verify_candidate() computes the final confirmed/rejected verdict itself,
as (NOT check_1.applies) AND (NOT check_2.applies) AND ... AND (NOT
check_5.applies) -- it does NOT trust a single top-level "is this
genuine?" field from the model as authoritative, even though one is also
requested (as "verifier_verdict", logged for comparison only). This is a
deliberate response to a concrete, already-observed failure mode in this
very project: task5b's spot-check found cases where a model's own stated
rationale was internally incoherent with the label it ultimately picked
(results/task5b_revised_precision_report.json, e.g. pool_index 1383/1488
-- "the model's own rationale text is internally incoherent... while
still landing on Concession"). Deriving the verdict mechanically from the
five individual answers, rather than asking the model to also aggregate
them itself, removes exactly that failure mode from the aggregation step
(it can of course still occur within a single check's own applies/reason
pair, which is why the spot-check in Task 6's results file re-reads
actual reasons, not just booleans).

DEFAULT PROMPT WORDING, UPDATED (2026-08, full-scale run): verify_candidate()
now defaults to build_verification_prompt_check4_revision, not
build_verification_prompt. See verify_candidate()'s own docstring below for
the full rationale (human-audit-validated: 84.6% vs 46.2% agreement with
independent human judgment) -- the short version is that the ORIGINAL
check_4 wording was found to mechanically reject essentially all genuine
Concessions, and the revision fixes that without a corresponding loss of
precision on the audited sample. build_verification_prompt is unchanged and
stays fully usable for provenance/reproducibility via an explicit
prompt_builder= argument.
"""

import os
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DISCOURSE_SEVERANCE_DIR = os.path.dirname(SCRIPT_DIR)
SERVER_DIR = os.path.dirname(os.path.dirname(DISCOURSE_SEVERANCE_DIR))
if SERVER_DIR not in sys.path:
    sys.path.insert(0, SERVER_DIR)

from api_call import generate_response  # noqa: E402
from components.response_parsing import extract_json_from_response  # noqa: E402

DEFAULT_STAGE2_MODEL = "gpt-4o"

PROMPT_MARKER = "You are a skeptical discourse-relation AUDITOR."

CHECK_KEYS = [
    "check_1_causal",
    "check_2_purpose_goal",
    "check_3_narrated_past",
    "check_4_plain_contrast",
    "check_5_misattachment_or_fabrication",
]


def build_verification_prompt(content, relation_type, nucleus, satellite, connective):
    return f"""{PROMPT_MARKER} You are NOT being asked to classify a \
paragraph from scratch. A separate, less careful first-pass classifier \
has ALREADY labeled the paragraph below as containing a "{relation_type}" \
discourse relation, and has extracted the following spans as its \
evidence:

  - nucleus (the governed/asserted clause):       "{nucleus}"
  - satellite (the governing/qualifying clause):  "{satellite}"
  - connective (the signaling word/phrase):       "{connective}"

Your job is to try to PROVE THIS WRONG. Do not re-derive a classification \
charitably, and do not assume the first-pass labeler was careful -- it \
was not: it is known, from prior audits, to make specific, recurring \
mistakes (listed below as the five checks), and it never sees its own \
output being checked. Treat the label and spans above as a claim to be \
stress-tested, not as a starting point to agree with. Work through the \
five checks below, IN ORDER, actively trying to find a genuine reason to \
reject the claim under each one. Only if you cannot find grounds to \
reject it under ANY of the five checks may it be confirmed as genuine.

For reference, the two relation types being audited use these exact \
RST-derived definitions (the same ones the first-pass classifier was \
given -- unchanged here):

  CONDITION: satellite presents a hypothetical, future, or otherwise \
unrealized situation; the nucleus's realization depends on the \
satellite's realization. (Restrictive/exceptive framing -- "unless X", \
"except when X" -- counts as Condition, not a separate category.)

  CONCESSION: nucleus and satellite present an apparent-but-not-actual \
incompatibility; the writer's positive regard for the nucleus increases \
once the reader recognizes they're actually compatible.

Source paragraph: "{content}"

Work through EACH of these five checks. For each, decide whether the \
described failure mode APPLIES to this candidate -- if it applies, that \
is a reason to REJECT the candidate. Some checks will be trivially \
inapplicable depending on whether the candidate above was labeled \
Condition or Concession (e.g. check 2 is about a Condition-specific \
mistake, so it will usually not apply to a Concession candidate) -- even \
so, address every check explicitly with its own one-sentence reason \
rather than skipping it; do not leave a check's "applies" as false by \
default just because the candidate's label makes it seem irrelevant on \
its face.

  1. CAUSAL, NOT CONDITION/CONCESSION: is the connective actually a plain \
causal reason-giver ("because", "since", "due to", "as a result of", \
"therefore") explaining WHY the nucleus is true, rather than a genuine \
hypothetical dependency (Condition) or a resolved apparent incompatibility \
(Concession)? A cause-effect explanation is neither.
  2. PURPOSE/GOAL, NOT CONDITION: if labeled Condition, is the \
"satellite" actually a purpose/goal clause ("to X", "in order to X", "so \
that X", "aimed at X") stating the nucleus's MOTIVATION, rather than a \
hypothetical/unrealized situation the nucleus depends on? A goal is not a \
precondition.
  3. NARRATED PAST, NOT CONDITION: if labeled Condition, does the \
"satellite" describe something that ALREADY HAPPENED as a specific, \
completed, one-time historical event (regardless of whether "when", \
"where", or some other word introduces it), rather than a \
hypothetical/future/unrealized situation? A narrated fact is not \
"unrealized" merely because of how it happens to be introduced.
  4. PLAIN CONTRAST, NOT CONCESSION: if labeled Concession, is this just \
a bare factual contrast or sequence ("X, but Y"; "X. However, Y.") \
WITHOUT the writer surfacing a genuine apparent incompatibility and then \
signaling that positive regard for the nucleus survives or increases once \
it is resolved? A difference or tension alone is not Concession, and \
restating the contrast in the rationale is not the same as identifying a \
resolution.
  5. MISATTACHMENT OR FABRICATION: does the quoted "satellite" and/or \
"connective" EITHER (a) fail to appear, verbatim or near-verbatim, \
anywhere in the source paragraph at all (fabricated/hallucinated), OR (b) \
appear somewhere in the paragraph but NOT actually stand in the claimed \
governing relationship to the quoted "nucleus" specifically (the \
paragraph may contain real conditional/concessive language, but it \
governs a DIFFERENT clause than the one paired with it here)? Check this \
even if checks 1-4 all failed to find a problem -- a candidate can use a \
perfectly real relation type and still be wrong because the two spans \
don't actually govern each other.

Output strict JSON with exactly these keys, one entry per check plus a \
final overall field:
  "check_1_causal": {{"applies": true or false, "reason": "one sentence"}}
  "check_2_purpose_goal": {{"applies": true or false, "reason": "one sentence"}}
  "check_3_narrated_past": {{"applies": true or false, "reason": "one sentence"}}
  "check_4_plain_contrast": {{"applies": true or false, "reason": "one sentence"}}
  "check_5_misattachment_or_fabrication": {{"applies": true or false, "reason": "one sentence"}}
  "verifier_verdict": "genuine" or "not_genuine" -- your own overall \
judgment, recorded for comparison only (the pipeline computes the \
authoritative verdict mechanically from the five checks above, so answer \
each check on its own merits rather than picking a verdict first and \
reverse-engineering the five answers to match it).

"applies": true means the failure mode DOES apply, i.e. this check is a \
reason to REJECT the candidate. A genuine candidate should have \
"applies": false on all five checks.

Return only valid JSON. Do not include Markdown code fences or additional \
text.
"""


def build_verification_prompt_check4_revision(content, relation_type, nucleus, satellite, connective):
    """EXPERIMENTAL, NOT used by the default pipeline (run_two_stage_pipeline.py
    never passes this in) -- see verify_candidate's "prompt_builder" docstring
    and run_check4_revision_experiment.py.

    Identical to build_verification_prompt() in every respect (framing,
    definitions, checks 1/2/3/5, output schema) EXCEPT check 4's wording,
    which this validation run's own spot-check found badly miscalibrated:
    of a 25-item random sample of Stage-2-REJECTED Concession candidates
    (see results/task6_two_stage_pipeline_report.json's
    "concession_rejected_false_negative_spot_check"), roughly 40% looked
    like genuine Concessions rejected via check_4 alone, almost always
    with a "reason" that just restated the sentence contains a contrast --
    without ever engaging whether that contrast created real doubt about
    the nucleus that the text then resolves. The adversarial "find a
    reason to reject" framing appears to have pushed the model toward
    treating the classic "X, although/even though/despite/but Y"
    connective pattern itself as automatically insufficient, always
    finding SOME redescription of it as "just a contrast" -- since nearly
    any two juxtaposed clauses can be loosely redescribed that way, this
    check was close to unsatisfiable as originally worded.

    This revision adds an explicit test (would a reader, seeing ONLY the
    satellite, have real grounds to doubt the nucleus? if so and the text
    asserts the nucleus anyway, that IS the resolution) and explicitly
    tells the model the classic concessive connective pattern satisfies
    this by construction, so it stops demanding some extra sentence of
    commentary beyond the two clauses themselves before crediting a
    resolution.
    """
    return f"""{PROMPT_MARKER} You are NOT being asked to classify a \
paragraph from scratch. A separate, less careful first-pass classifier \
has ALREADY labeled the paragraph below as containing a "{relation_type}" \
discourse relation, and has extracted the following spans as its \
evidence:

  - nucleus (the governed/asserted clause):       "{nucleus}"
  - satellite (the governing/qualifying clause):  "{satellite}"
  - connective (the signaling word/phrase):       "{connective}"

Your job is to try to PROVE THIS WRONG. Do not re-derive a classification \
charitably, and do not assume the first-pass labeler was careful -- it \
was not: it is known, from prior audits, to make specific, recurring \
mistakes (listed below as the five checks), and it never sees its own \
output being checked. Treat the label and spans above as a claim to be \
stress-tested, not as a starting point to agree with. Work through the \
five checks below, IN ORDER, actively trying to find a genuine reason to \
reject the claim under each one. Only if you cannot find grounds to \
reject it under ANY of the five checks may it be confirmed as genuine.

For reference, the two relation types being audited use these exact \
RST-derived definitions (the same ones the first-pass classifier was \
given -- unchanged here):

  CONDITION: satellite presents a hypothetical, future, or otherwise \
unrealized situation; the nucleus's realization depends on the \
satellite's realization. (Restrictive/exceptive framing -- "unless X", \
"except when X" -- counts as Condition, not a separate category.)

  CONCESSION: nucleus and satellite present an apparent-but-not-actual \
incompatibility; the writer's positive regard for the nucleus increases \
once the reader recognizes they're actually compatible.

Source paragraph: "{content}"

Work through EACH of these five checks. For each, decide whether the \
described failure mode APPLIES to this candidate -- if it applies, that \
is a reason to REJECT the candidate. Some checks will be trivially \
inapplicable depending on whether the candidate above was labeled \
Condition or Concession (e.g. check 2 is about a Condition-specific \
mistake, so it will usually not apply to a Concession candidate) -- even \
so, address every check explicitly with its own one-sentence reason \
rather than skipping it; do not leave a check's "applies" as false by \
default just because the candidate's label makes it seem irrelevant on \
its face.

  1. CAUSAL, NOT CONDITION/CONCESSION: is the connective actually a plain \
causal reason-giver ("because", "since", "due to", "as a result of", \
"therefore") explaining WHY the nucleus is true, rather than a genuine \
hypothetical dependency (Condition) or a resolved apparent incompatibility \
(Concession)? A cause-effect explanation is neither.
  2. PURPOSE/GOAL, NOT CONDITION: if labeled Condition, is the \
"satellite" actually a purpose/goal clause ("to X", "in order to X", "so \
that X", "aimed at X") stating the nucleus's MOTIVATION, rather than a \
hypothetical/unrealized situation the nucleus depends on? A goal is not a \
precondition.
  3. NARRATED PAST, NOT CONDITION: if labeled Condition, does the \
"satellite" describe something that ALREADY HAPPENED as a specific, \
completed, one-time historical event (regardless of whether "when", \
"where", or some other word introduces it), rather than a \
hypothetical/future/unrealized situation? A narrated fact is not \
"unrealized" merely because of how it happens to be introduced.
  4. PLAIN CONTRAST, NOT CONCESSION -- REVISED TEST: if labeled \
Concession, apply this specific test: if a reader saw ONLY the \
satellite, would they have genuine grounds to DOUBT, or be SURPRISED, \
that the nucleus is also true? If yes -- and the text asserts the \
nucleus anyway, rather than retracting or heavily qualifying it -- that \
doubt-raised-then-nucleus-affirmed-anyway structure IS a genuine resolved \
apparent incompatibility. The classic "X, although X' / even though X' / \
despite X' / but X'" concessive pattern satisfies this BY ITSELF; do NOT \
require some additional explicit sentence of commentary beyond the two \
clauses before crediting a resolution -- the resolution IS the writer \
asserting the nucleus in the same breath as the doubt-raising satellite. \
Only mark this check as APPLYING (i.e. reject) when the two clauses are \
merely SEQUENTIAL or PARALLEL facts that create no real doubt about each \
other in the first place -- a plain timeline ("X happened, but Y did not \
follow"), a bare list of separate attributes, or two facts that just \
happen to sit near each other with no doubt-then-affirm dynamic. Do NOT \
mark it as applying merely because the sentence COULD be loosely \
redescribed as "a contrast" in some generic sense -- nearly any \
concessive sentence can be redescribed that way, and that alone proves \
nothing; the question is specifically whether the satellite creates real \
doubt about the nucleus that the nucleus's assertion then overrides.
  5. MISATTACHMENT OR FABRICATION: does the quoted "satellite" and/or \
"connective" EITHER (a) fail to appear, verbatim or near-verbatim, \
anywhere in the source paragraph at all (fabricated/hallucinated), OR (b) \
appear somewhere in the paragraph but NOT actually stand in the claimed \
governing relationship to the quoted "nucleus" specifically (the \
paragraph may contain real conditional/concessive language, but it \
governs a DIFFERENT clause than the one paired with it here)? Check this \
even if checks 1-4 all failed to find a problem -- a candidate can use a \
perfectly real relation type and still be wrong because the two spans \
don't actually govern each other.

Output strict JSON with exactly these keys, one entry per check plus a \
final overall field:
  "check_1_causal": {{"applies": true or false, "reason": "one sentence"}}
  "check_2_purpose_goal": {{"applies": true or false, "reason": "one sentence"}}
  "check_3_narrated_past": {{"applies": true or false, "reason": "one sentence"}}
  "check_4_plain_contrast": {{"applies": true or false, "reason": "one sentence"}}
  "check_5_misattachment_or_fabrication": {{"applies": true or false, "reason": "one sentence"}}
  "verifier_verdict": "genuine" or "not_genuine" -- your own overall \
judgment, recorded for comparison only (the pipeline computes the \
authoritative verdict mechanically from the five checks above, so answer \
each check on its own merits rather than picking a verdict first and \
reverse-engineering the five answers to match it).

"applies": true means the failure mode DOES apply, i.e. this check is a \
reason to REJECT the candidate. A genuine candidate should have \
"applies": false on all five checks.

Return only valid JSON. Do not include Markdown code fences or additional \
text.
"""


def _empty_verification(error=None, prompt_version=None):
    result = {
        "checks": {k: None for k in CHECK_KEYS},
        "confirmed": False,
        "model_stated_verdict": None,
        "verdict_agrees_with_model": None,
        "verification_prompt_version": prompt_version,
    }
    if error:
        result["_error"] = error
    return result


def _prompt_version_label(prompt_builder):
    if prompt_builder is build_verification_prompt_check4_revision:
        return "check4_revision"
    if prompt_builder is build_verification_prompt:
        return "original"
    return getattr(prompt_builder, "__name__", "custom")


def verify_candidate(content, relation_type, nucleus, satellite, connective, model=None,
                      prompt_builder=None):
    """One LLM call: adversarially re-examine a Stage-1 Condition/Concession
    candidate. Returns a dict; on any failure (no response, unparseable
    JSON, a missing/malformed check) returns _empty_verification() with an
    "_error" key set and confirmed=False, rather than raising -- same
    fail-safe-but-keep-the-batch-going pattern as
    relation_classifier.classify_paragraph. Treating an unparseable
    verification call as "not confirmed" (rather than dropping it, or
    counting it as confirmed) is a deliberate choice: a candidate this
    pipeline could not successfully stress-test never earns the higher bar
    Stage 2 exists to enforce.

    prompt_builder: DEFAULTS TO build_verification_prompt_check4_revision as
    of the full-scale run (2026-08). This is a PROMOTION, not a new
    experiment -- a stratified 26-item human audit (manual_concession_audit.md
    / manual_concession_audit_manifest.json, tallied by
    tally_manual_concession_audit.py) found the revised check_4 wording
    agrees with independent human judgment 84.6% of the time (22/26) versus
    46.2% (12/26) for the ORIGINAL wording (which had mechanically rejected
    100% of Concession candidates via check_4 alone -- see
    results/task6_check4_revision_experiment_report.json and
    results/task6_two_stage_pipeline_report.json's Concession funnel). That
    audit is now the authoritative basis for which wording the pipeline
    should use by default, so run_two_stage_pipeline.py's Stage 2 (and its
    --retry-stage2-errors path), which never pass this argument explicitly,
    now get the revised wording automatically.

    The ORIGINAL build_verification_prompt is kept in this module UNCHANGED
    and remains fully callable via an explicit
    prompt_builder=build_verification_prompt argument -- e.g.
    run_check4_revision_experiment.py's existing usage, or anyone
    reproducing the earlier validation run's numbers -- it has simply
    stopped being what a bare verify_candidate(...) call uses. Every Stage-2
    log record now also carries a "verification_prompt_version" field
    ("original" vs "check4_revision") precisely because
    logs/task6_stage2_log.jsonl spans both eras (pool_index 1803-2802 was
    verified under the original wording before this promotion; pool_index
    >= 2803 is verified under the revised wording by default) -- so no
    downstream analysis has to guess which checklist wording produced a
    given verdict.
    """
    model = model or DEFAULT_STAGE2_MODEL
    prompt_builder = prompt_builder or build_verification_prompt_check4_revision
    prompt_version = _prompt_version_label(prompt_builder)
    prompt = prompt_builder(content, relation_type, nucleus, satellite, connective)
    response = generate_response(prompt, model=model)
    if not response or not hasattr(response, "content"):
        return _empty_verification(error="no_response", prompt_version=prompt_version)

    data = extract_json_from_response(response.content)
    if not data:
        return _empty_verification(error="unparseable_json", prompt_version=prompt_version)

    checks = {}
    for key in CHECK_KEYS:
        entry = data.get(key)
        if not isinstance(entry, dict) or "applies" not in entry:
            return _empty_verification(error=f"missing_or_malformed_check:{key}", prompt_version=prompt_version)
        applies = entry.get("applies")
        if isinstance(applies, str):
            applies = applies.strip().lower() in ("true", "yes", "1")
        checks[key] = {
            "applies": bool(applies),
            "reason": entry.get("reason"),
        }

    confirmed = not any(c["applies"] for c in checks.values())

    model_stated_verdict = data.get("verifier_verdict")
    verdict_agrees_with_model = None
    if model_stated_verdict in ("genuine", "not_genuine"):
        model_says_confirmed = model_stated_verdict == "genuine"
        verdict_agrees_with_model = (model_says_confirmed == confirmed)

    return {
        "checks": checks,
        "confirmed": confirmed,
        "model_stated_verdict": model_stated_verdict,
        "verdict_agrees_with_model": verdict_agrees_with_model,
        "model": model,
        "verification_prompt_version": prompt_version,
    }
