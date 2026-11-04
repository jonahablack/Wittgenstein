"""Task 3 (full-scale run): paragraph-level severance judge for
FactoidWiki, adapted from ../severance_detection.py's
`judge_prompt_full_nucleus` (= `build_llm_judge_prompt`) design -- same
judge FRAMING (does the atomized output convey that the satellite governs/
limits the nucleus? "reading ONLY the atomized output, not the original
text, would a reader still correctly understand the relationship?") -- but
re-implemented self-contained in this track (per env_utils.py's
established convention: factoidwiki_track/ does not import its siblings
outside the directory) and adapted for paragraph-level input:

  - "sentence" -> "paragraph": the source text being atomized here is a
    whole (possibly multi-sentence) Wikipedia paragraph, not one CFR
    sentence.
  - "claims" -> "propositions": matches this track's/dataset's own
    vocabulary (train.jsonl's `targets` field and this project's
    Propositionizer nomenclature both say "proposition", not "claim").
  - Only Condition/Concession/Elaboration/None relation descriptions are
    needed (this track never uses an "Exception" category -- see
    relation_classifier.py's docstring on why), so `_RELATION_DESCRIPTIONS`
    here is a trimmed copy of ../severance_detection.py's dict, verbatim
    for the three types both tracks share.
  - Only the LLM-judge is reused/adapted, not the rule-based proxy check
    (severance_detection.rule_based_severance) -- the task brief's Task 3
    section frames the judge question specifically ("does the atomized
    output convey that the satellite governs/limits the nucleus"), and the
    rule-based check is a CFR/sentence-specific, wordlist-driven proxy
    (CONNECTIVE_WORDLIST tuned for regulatory-style connectives) that was
    never validated against Wikipedia prose; introducing it here
    un-validated would risk a second, silently-miscalibrated metric rather
    than reusing "established, validated infrastructure" as instructed.

MODEL CHOICE: gpt-4o-mini (generate_response's own default), matching
../severance_detection.py's llm_judge_severance (model=None there too) --
this is the SAME model/default the parent track's own headline severance
numbers were computed with, so this track's numbers stay comparable to it
along that dimension.
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

DEFAULT_JUDGE_MODEL = None  # None -> generate_response's own default (gpt-4o-mini)

# Distinctive substring, parallel to severance_detection.LLM_JUDGE_PROMPT_MARKER.
LLM_JUDGE_PROMPT_MARKER = "Reading ONLY the atomized propositions above"

# Verbatim copy (for the three shared relation types) of
# ../severance_detection.py's _RELATION_DESCRIPTIONS -- kept textually
# identical on purpose so this track's judge asks the same underlying
# question the parent track validated, not a paraphrase that could
# silently shift calibration.
_RELATION_DESCRIPTIONS = {
    "Condition": (
        "a Condition relation: the nucleus is asserted to hold ONLY WHEN/IF "
        "the satellite holds -- if the satellite's truth is not knowable or "
        "is false, the nucleus's applicability here is not established."
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
        "atomized propositions still convey the same overall content as "
        "the nucleus/satellite text."
    ),
}


def build_paragraph_judge_prompt(paragraph, relation, propositions):
    props_block = "\n".join(f"- {p}" for p in propositions) or "(no propositions produced)"
    relation_type = relation.get("relation_type", "None")
    nucleus = relation.get("nucleus")
    satellite = relation.get("satellite")
    description = _RELATION_DESCRIPTIONS.get(relation_type, _RELATION_DESCRIPTIONS["None"])
    return f"""
Original paragraph (context ONLY -- do not base your answer on this, only
on the atomized propositions below): "{paragraph}"

Discourse relation identified in the original paragraph: {relation_type}
Nucleus (the governed/asserted clause): {nucleus!r}
Satellite (the qualifying/supporting clause): {satellite!r}

This is specifically {description}

Atomized propositions (this is what a downstream reader would actually
see, with NO access to the original paragraph):
{props_block}

{LLM_JUDGE_PROMPT_MARKER}, not the original paragraph, would a reader
correctly understand the relationship between the satellite ({satellite!r})
and the nucleus ({nucleus!r}) DESCRIBED ABOVE for this specific relation
type? Judge Condition/Concession against whether the nucleus's governing
condition/concession is still evident. Judge Elaboration against whether
the satellite's content is still evident as detail about the nucleus (NOT
against a governing standard, since Elaboration never governs). Answer
"false" if the atomized propositions would lead a reader to a different
understanding of the relationship than the original paragraph conveyed, or
if the relationship is absent, garbled, or split so that the satellite no
longer attaches to the nucleus.

Output strict JSON with exactly these keys:
  "preserved": true or false
  "reasoning": one sentence explaining your answer

Return only valid JSON. Do not include Markdown code fences or additional
text.
"""


def llm_judge_paragraph_severance(paragraph, relation, propositions, model=None):
    """Returns {"preserved": bool or None, "reasoning": str}. `preserved` is
    None only on an outright call/parse failure (logged in `reasoning`),
    never as a silent substitute for a real answer -- same convention as
    ../severance_detection.py's llm_judge_severance.
    """
    model = model or DEFAULT_JUDGE_MODEL
    prompt = build_paragraph_judge_prompt(paragraph, relation, propositions)
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


# --- Elaboration correction (v2): content-recoverability judge -------------
#
# Paragraph-level port of ../severance_detection.py's
# `llm_judge_severance_elaboration_v2` / `build_llm_judge_prompt_elaboration_v2`
# -- see that module's block comment for the full root-cause writeup (the
# original judge's closing question implicitly demands an explicit
# textual/lexical link between satellite and nucleus, which is a
# governing-relation standard RST never imposes on Elaboration). Reading
# every case this paragraph-level original judge scored severed=false for
# Elaboration across the Propositionizer/AtomicRAG/own_baseline tracks (49
# of the 126 total: 6 + 24 + 19) found the same over-strict pattern: the
# large majority had the satellite's content fully present, just split
# into a different proposition/claim than the nucleus, or merged into one
# claim with paraphrased wording -- not lost.
#
# Ported, not re-derived from scratch: the underlying judge QUESTION
# (nucleus-recoverable gate, then satellite-content-recoverable check,
# then the genuine-absence / active-misattribution severance carve-outs)
# is copied in substance from severance_detection.py's v2 prompt, only the
# "claims" -> "propositions" and "sentence" -> "paragraph" vocabulary swap
# applied -- same adaptation relationship build_paragraph_judge_prompt
# above already has to build_llm_judge_prompt.
#
# Elaboration-only, same as the sentence-level version: Condition/
# Concession/None's _RELATION_DESCRIPTIONS entries and
# build_paragraph_judge_prompt/llm_judge_paragraph_severance above are
# completely untouched.
LLM_JUDGE_ELABORATION_V2_PROMPT_MARKER = (
    "Reading ONLY the atomized propositions above, taken together as a whole set"
)


def build_paragraph_judge_prompt_elaboration_v2(paragraph, relation, propositions):
    """Corrected Elaboration-only judge prompt, paragraph-adapted. Must
    only be used when relation["relation_type"] == "Elaboration".
    """
    props_block = "\n".join(f"- {p}" for p in propositions) or "(no propositions produced)"
    nucleus = relation.get("nucleus")
    satellite = relation.get("satellite")
    return f"""
Original paragraph (context ONLY -- do not base your answer on this, only
on the atomized propositions below): "{paragraph}"

Discourse relation identified in the original paragraph: Elaboration
Nucleus (the general situation being elaborated): {nucleus!r}
Satellite (the additional detail about that situation): {satellite!r}

This is an Elaboration relation: per RST's own definition (Carlson &
Marcu 2001, Elaboration-Additional / Elaboration-General-Specific), the
satellite simply gives additional information, detail, or specific
content about the situation presented in the nucleus. The satellite does
NOT govern, condition, or except the nucleus -- the nucleus would still
be true even if the satellite were removed, and unlike
Condition/Concession, RST does NOT require the satellite to stay
lexically or structurally attached to the nucleus (no connective, shared
sentence, or explicit transition word is required by the relation
itself). The only thing that matters is whether the CONTENT is there and
is topically about the nucleus's subject.

Atomized propositions (this is what a downstream reader would actually
see, with NO access to the original paragraph -- judge the propositions
TOGETHER, as the full set a reader would have, not one at a time in
isolation):
{props_block}

{LLM_JUDGE_ELABORATION_V2_PROMPT_MARKER}, not the original paragraph,
decide whether the relationship is preserved. Base your answer ONLY on
what is literally stated -- verbatim or as a clear, close paraphrase --
in the atomized propositions below. Do not use outside/world knowledge or
plausible inference to fill in content the atomized propositions do not
actually convey; but also do not demand every last word or secondary
nuance of the original phrasing survive -- minor loss of secondary
wording or emphasis is fine as long as the core content is genuinely
there.

Step 1 (nucleus gate): is the nucleus's situation ({nucleus!r}) stated
anywhere in the atomized propositions -- in one proposition, or built up
from a combination of propositions, in any wording? If it is NOT stated
anywhere at all, set "nucleus_recoverable": false and answer "preserved":
false immediately -- there is no situation left for the satellite to be
detail about, no matter how well the satellite's own content survived
elsewhere.

Step 2 (satellite content check): if the nucleus IS recoverable, set
"nucleus_recoverable": true, then check whether the satellite's SPECIFIC
content ({satellite!r}) is ALSO stated somewhere in the atomized
propositions -- in the same proposition as the nucleus (perfectly normal
if they were merged together) or a different one, split apart or merged,
phrased identically or paraphrased. No connective or transition word is
required. "Specific" means: if the satellite's original text names a
number, date, named entity, comparison, or reason/cause, that core
specific point should be recoverable somewhere in the atomized
propositions -- a proposition that only gestures at the general topic
while dropping the actual specific point (replacing a concrete
number/name/reason with nothing, with something so generic the point is
lost, or with an unrelated specific from elsewhere in the source) does
not satisfy this.

Step 3 (misattribution check -- run this even when steps 1-2 both look
satisfied): does any atomized proposition actively CONTRADICT or
MISATTRIBUTE the nucleus's or satellite's content -- assign a fact to the
wrong subject, reverse who-did-what-to-whom, or assert a
nonsensical/impossible value (e.g. one entity with several different
"founding"/"published" dates, or a value that plainly belongs to a
different event/person/year than the one it is attached to)? Check the
raw proposition text for this, not just its general topic. If yes, answer
"preserved": false -- an actively wrong proposition is worse than a
missing one, even if some other proposition elsewhere also carries
correct content.

Answer "preserved": true only if step 1 and step 2 both succeed AND step
3 finds no contradiction/misattribution.

Do NOT answer "false" merely because: the satellite's content ended up in
a separate proposition from the nucleus with no connective between them;
the propositions were merged into one differently than you might have
phrased it; the atomized wording paraphrases rather than quotes the
original; or some minor secondary detail (not the core specific point) is
missing. None of those are severance for Elaboration.

Output strict JSON with exactly these keys:
  "preserved": true or false
  "nucleus_recoverable": true or false
  "reasoning": one or two sentences explaining your answer, quoting or
    pointing to the specific atomized proposition(s) that drove the
    verdict and naming which step (1/2/3) was decisive

Return only valid JSON. Do not include Markdown code fences or additional
text.
"""


# --- Condition/Concession correction (v2): attachment-preserving judge ----
#
# Root cause (confirmed by direct audit of the 82 mislabeled-actually-correct
# cases found in a from-scratch hand-audit of task8's 125-case
# Condition/Concession dangerous_failure pool, results/dangerous_failure_full_audit.json):
# the original judge's closing question ("...or if the relationship is
# absent, garbled, or split so that the satellite no longer attaches to the
# nucleus") is ambiguous between "a reader can still infer the relationship"
# and "the propositions must explicitly narrate why the connective creates
# the relationship." The model resolves it toward the stricter,
# narration-demanding reading: 87% of the 82 mislabeled cases' own
# `original_judge.reasoning` strings hedge with "not explicitly" / "does
# not clearly convey" language, and 78% have the exact connective word
# present verbatim in the propositions and were STILL scored
# preserved=false.
#
# Same bug FAMILY as the Elaboration v2 fix above (an implicit standard
# neither RST nor the prompt's own relation description requires) but NOT
# the same fix: Condition/Concession genuinely require the governing
# relationship to be evident, unlike Elaboration, where no attachment is
# required at all. Dropping the narration requirement while ALSO dropping
# the attachment requirement would be too permissive -- it would pass real
# misattachment failures such as pool 3278/arm_4_contextual_retrieval
# ("despite" governs a paraphrased-but-wrong satellite about political
# conflict, while the real ground-truth satellite, "he died a staunch
# Lancastrian", sits in a separate, disconnected proposition) and pool
# 4200/arm_4_contextual_retrieval (same pattern: "despite" attached to
# "his desire to stay with the Pittsburgh Penguins", not the ground-truth
# satellite "was playing in the NHL the next year", which appears
# elsewhere with no connective at all). So this v2 keeps attachment/
# binding as a hard, explicit requirement and drops only the narration
# demand.
LLM_JUDGE_CC_V2_PROMPT_MARKER = (
    "Reading ONLY the atomized propositions above, taken together as a whole set"
)

_CC_MARKER_EXAMPLES = {
    "Condition": "if, only if, when, unless, provided that, as long as, in the event that",
    "Concession": "although, though, but, however, yet, despite, in spite of, nonetheless, still, even so, rather",
}

_CC_RELATION_GLOSS = {
    "Condition": (
        "a Condition relation: the nucleus is asserted to hold ONLY WHEN/IF "
        "the satellite holds -- if the satellite's truth is not knowable or "
        "is false, the nucleus's applicability here is not established."
    ),
    "Concession": (
        "a Concession relation: the nucleus holds EVEN THOUGH/DESPITE the "
        "satellite also being true -- the satellite is acknowledged but does "
        "not defeat the nucleus."
    ),
}


# PROMPT ITERATION NOTE (v1/v2 below, kept as a historical record, NOT
# validated, DO NOT call in production code):
#   v1 (single holistic call, "connective governs matching satellite
#   content, split-proposition attachment explicitly allowed"): 44.5%
#   agreement (53/119) against the hand-audited validation set. The model
#   ignored the explicit "split across propositions is fine" instruction
#   and kept demanding same-proposition co-location -- 49/119 false
#   negatives, plus one of the two known misattachment negative controls
#   slipped through as a false positive.
#   v2 (forced quote-then-compare, 4 mechanical steps, JSON list output):
#   33.6% agreement (40/119), WORSE than v1, plus 39/119 calls (33%)
#   failed to parse as valid JSON (the quoted-clause list field broke on
#   embedded quotes/apostrophes). Root design flaw found on inspection,
#   not just model unreliability: the rule assumed the connective always
#   sits adjacent to and introduces the SATELLITE specifically. Real
#   cases don't work that way -- pool 4351/2272's satellite is stated
#   plainly with no marker, and "However" instead sits adjacent to the
#   NUCLEUS, marking the turn away from the already-stated satellite, a
#   legitimate RST-consistent pattern v2's rule rejected outright.
#   Superseded by the v3 two-call architecture below (locator call, pure
#   extraction with no judgment, followed by a narrow mismatch-detection
#   call only when needed) -- separating "where is the content" from "is
#   it correctly attached" instead of asking one call to do both in a
#   single holistic or four-step pass.
def build_paragraph_judge_prompt_condition_concession_v2(paragraph, relation, propositions):
    """Corrected Condition/Concession-only judge prompt, paragraph-adapted.
    Must only be used when relation["relation_type"] is "Condition" or
    "Concession".
    """
    props_block = "\n".join(f"- {p}" for p in propositions) or "(no propositions produced)"
    relation_type = relation.get("relation_type", "Concession")
    nucleus = relation.get("nucleus")
    satellite = relation.get("satellite")
    connective = relation.get("connective", "")
    relation_gloss = _CC_RELATION_GLOSS.get(relation_type, _CC_RELATION_GLOSS["Concession"])
    marker_examples = _CC_MARKER_EXAMPLES.get(relation_type, _CC_MARKER_EXAMPLES["Concession"])
    return f"""
Original paragraph (context ONLY -- do not base your answer on this, only
on the atomized propositions below): "{paragraph}"

Discourse relation identified in the original paragraph: {relation_type}
Nucleus (the governed/asserted clause): {nucleus!r}
Satellite (the qualifying/conceding clause): {satellite!r}
Connective in the original text: {connective!r}

This is specifically {relation_gloss}

Atomized propositions (this is what a downstream reader would actually
see, with NO access to the original paragraph -- judge the propositions
TOGETHER, as the full set a reader would have, not one at a time in
isolation):
{props_block}

{LLM_JUDGE_CC_V2_PROMPT_MARKER}, not the original paragraph, decide
whether the {relation_type} relationship is preserved.

IMPORTANT, read carefully: unlike Elaboration, the connective's
ATTACHMENT to the correct content matters here -- a connective merely
appearing somewhere in the output, unattached to the actual
nucleus/satellite pairing, does not preserve the relationship. But
unlike the original criterion this prompt replaces, no additional
narration of the connective's logical effect is required, and the
marker does NOT need to be in the same proposition as the nucleus --
splitting the marker and its content into a separate, adjacent
proposition from the nucleus is completely normal and does NOT count
against preservation by itself.

Do this in four steps, QUOTING the exact proposition text at each step
before drawing any conclusion from it -- do not judge from memory or
paraphrase of the propositions, copy the actual words:

Step 1 (quote the nucleus evidence): copy, verbatim, the specific
proposition(s) that state the nucleus's content ({nucleus!r}). If no
proposition states it, in any wording, set "nucleus_recoverable": false
and answer "preserved": false immediately.

Step 2 (quote the marker's own clause): find every occurrence of a
{relation_type.lower()} marker in the propositions -- the original
connective ({connective!r}) or a clear synonym/equivalent (for example:
{marker_examples}). For EACH occurrence, copy, verbatim, only the
specific content that marker directly introduces within its own clause
or sentence -- i.e. what that exact marker is sitting next to and
modifying in the text, not any other proposition's content, however
correct that other content might be elsewhere. If no marker occurrence
exists anywhere, set "marker_attached_to_correct_satellite": false and
answer "preserved": false.

Step 3 (compare): does ANY one of the quoted marker-clauses from Step 2
match the ground-truth satellite ({satellite!r}) -- verbatim, or as a
paraphrase that keeps its specific point (a name, number, date,
comparison, or reason, not just the general topic)? Judge this by
comparing the text you actually quoted in Step 2 against the satellite,
not by recalling whether the satellite's content appears "somewhere" in
the propositions as a whole. A marker whose own quoted clause names a
DIFFERENT fact is a mismatch even if the real satellite content also
happens to sit, unconnected, in some other proposition elsewhere --
correct content sitting elsewhere with no marker attached to it does
NOT rescue a marker that is attached to the wrong thing. Set
"marker_attached_to_correct_satellite" to whether any quoted clause
matched.
  Worked example (attachment despite a proposition split -- COUNTS as
  preserved): proposition A = "X happened.", proposition B = "However, Y
  also happened." -- if Y matches the ground-truth satellite, this
  counts as attached even though the marker "However" is in a different
  proposition (B) than the nucleus (A).
  Worked example (false attachment -- does NOT count as preserved): a
  proposition reads "...despite Q, X happened." where Q is some OTHER,
  different fact, not the ground-truth satellite -- while the real
  ground-truth satellite content appears as its own separate,
  marker-free proposition elsewhere. The marker's own clause names Q,
  not the satellite, so this is a mismatch regardless of the correct
  content existing elsewhere.

Step 4 (bind to nucleus and decide): if Step 3 found a match, confirm
that matching marker-clause and the nucleus content quoted in Step 1
are about the same specific event/entity, not different subjects that
merely resemble each other. Answer "preserved": true only if the
nucleus is recoverable (Step 1) AND a marker-clause matching the correct
satellite was found (Step 3) AND that pairing binds to the correct
nucleus (Step 4). Do NOT answer "false" merely because: the propositions
don't additionally explain the marker's logical consequence in separate
narrative language; the marker and its content ended up in a different
proposition than the nucleus; the wording paraphrases rather than
quotes the original; or the presentation is a rewritten preamble rather
than a merged sentence -- AS LONG AS the marker's own quoted clause
genuinely matches the correct satellite content.

Output strict JSON with exactly these keys:
  "preserved": true or false
  "nucleus_recoverable": true or false
  "quoted_nucleus_evidence": the exact proposition text quoted in Step 1
  "quoted_marker_clauses": a list of the exact marker-clause text(s)
    quoted in Step 2 (empty list if no marker was found)
  "marker_attached_to_correct_satellite": true or false
  "reasoning": one or two sentences explaining your answer, referring
    back to the quotes above and naming which step (1/2/3/4) was
    decisive

Return only valid JSON. Do not include Markdown code fences or additional
text.
"""


def llm_judge_paragraph_severance_condition_concession_v2(paragraph, relation, propositions, model=None):
    """Corrected Condition/Concession-only severance judge, paragraph-
    adapted. Returns {"preserved": bool or None, "nucleus_recoverable":
    bool or None, "quoted_nucleus_evidence": str or None,
    "quoted_marker_clauses": list or None,
    "marker_attached_to_correct_satellite": bool or None, "reasoning":
    str}. `preserved` is None only on an outright call/parse failure --
    same contract as llm_judge_paragraph_severance.

    Callers MUST route Condition/Concession relations to this function,
    Elaboration to llm_judge_paragraph_severance_elaboration_v2, and None
    to llm_judge_paragraph_severance (the original) -- this function does
    not itself branch on relation_type beyond the guard below.
    """
    if relation.get("relation_type") not in ("Condition", "Concession"):
        raise ValueError(
            "FATAL: llm_judge_paragraph_severance_condition_concession_v2 is "
            f"Condition/Concession-only; got relation_type={relation.get('relation_type')!r}. "
            "Use llm_judge_paragraph_severance_elaboration_v2 for Elaboration or "
            "llm_judge_paragraph_severance (the original) for None."
        )
    model = model or DEFAULT_JUDGE_MODEL
    prompt = build_paragraph_judge_prompt_condition_concession_v2(paragraph, relation, propositions)
    response = generate_response(prompt, model=model)
    if not response or not hasattr(response, "content"):
        return {
            "preserved": None,
            "nucleus_recoverable": None,
            "quoted_nucleus_evidence": None,
            "quoted_marker_clauses": None,
            "marker_attached_to_correct_satellite": None,
            "reasoning": "LLM-judge call failed: no model response.",
        }

    data = extract_json_from_response(response.content)
    if not data:
        return {
            "preserved": None,
            "nucleus_recoverable": None,
            "quoted_nucleus_evidence": None,
            "quoted_marker_clauses": None,
            "marker_attached_to_correct_satellite": None,
            "reasoning": "LLM-judge call failed: unparseable JSON response.",
        }

    return {
        "preserved": bool(data.get("preserved")),
        "nucleus_recoverable": data.get("nucleus_recoverable"),
        "quoted_nucleus_evidence": data.get("quoted_nucleus_evidence"),
        "quoted_marker_clauses": data.get("quoted_marker_clauses"),
        "marker_attached_to_correct_satellite": data.get("marker_attached_to_correct_satellite"),
        "reasoning": data.get("reasoning", ""),
    }


# --- Condition/Concession correction (v3): two-call locator + narrow ------
# mismatch-detection architecture, superseding v1/v2 above (see the
# PROMPT ITERATION NOTE preceding build_paragraph_judge_prompt_condition_concession_v2).
#
# Design: separate "where is the content" (pure extraction, no judgment
# call for the model to get wrong) from "is it correctly attached" (one
# narrow question, asked only when the deterministic index logic below
# can't already answer it for free). Proposition INDICES are used for all
# "where is this" fields, never quoted substrings, since v2's quoted-list
# fields are what broke JSON parsing on embedded quotes/apostrophes.
_CC_LOCATOR_PROMPT_MARKER = "Reading the numbered propositions below"


def build_cc_locator_prompt(paragraph, relation, propositions):
    """Pure-extraction locator prompt: find where the nucleus content,
    the satellite content, and any connective/marker occurrences are,
    by proposition index. Makes no judgment about whether they are
    correctly attached to each other -- that is the second call's job,
    and only when the deterministic logic in the orchestrator can't
    already resolve it.
    """
    props_block = "\n".join(f"{i}: {p}" for i, p in enumerate(propositions)) or "(no propositions produced)"
    relation_type = relation.get("relation_type", "Concession")
    nucleus = relation.get("nucleus")
    satellite = relation.get("satellite")
    connective = relation.get("connective", "")
    marker_examples = _CC_MARKER_EXAMPLES.get(relation_type, _CC_MARKER_EXAMPLES["Concession"])
    return f"""
Original paragraph (context ONLY -- do not base your answer on this, only
on the numbered propositions below): "{paragraph}"

Discourse relation identified in the original paragraph: {relation_type}
Nucleus (the governed/asserted clause): {nucleus!r}
Satellite (the qualifying/conceding clause): {satellite!r}
Connective in the original text: {connective!r}

Numbered atomized propositions (this is what a downstream reader would
actually see, with NO access to the original paragraph):
{props_block}

{_CC_LOCATOR_PROMPT_MARKER}, answer three SEPARATE, independent
lookup questions. Do not judge whether things are correctly related to
each other here -- only report WHERE content is found, verbatim or
paraphrased, in any wording.

1. Which proposition number(s) state the nucleus's specific content
   ({nucleus!r})? List every index that contains it, in whole or in
   part. Empty list if it is not stated anywhere.

2. Which proposition number(s) state the satellite's SPECIFIC content
   ({satellite!r})? "Specific" means: if the satellite names a number,
   date, named entity, comparison, or reason, that specific point must
   be present, not just the general topic. List every index that
   contains it. Empty list if it is not stated anywhere.

3. Every proposition number containing a {relation_type.lower()} marker
   -- the original connective ({connective!r}) or a clear
   synonym/equivalent (for example: {marker_examples}). For each one,
   give a short (under 15 words) description, in your own words, of
   WHAT SPECIFIC CONTENT that marker sits next to and appears to
   introduce or connect in that proposition's own text -- not whether
   it's "correct", just what it plainly says. Empty list if no marker
   appears anywhere.

Output strict JSON with exactly these keys:
  "nucleus_indices": [list of integers]
  "satellite_indices": [list of integers]
  "connective_occurrences": [list of objects, each
    {{"index": integer, "nearby_content": "short description"}}]

Return only valid JSON. Do not include Markdown code fences or additional
text.
"""


def build_cc_attachment_mismatch_prompt(relation_type, anchor_label, anchor_content, nearby_content_description):
    """Narrow mismatch-detection call: given a marker's own nearby
    content (already described in plain language by the locator call)
    and the ground-truth content it is being checked against, ask only
    whether they mismatch -- same shape as the already-validated
    Elaboration judge's misattribution check, which this project found
    more reliable for these models than a positive compositional proof.
    """
    return f"""
A {relation_type} relation's marker/connective was found in a piece of
atomized text. Its own nearby content, in the writer's words, was
described as: "{nearby_content_description}"

The specific ground-truth {anchor_label} content it needs to match is:
{anchor_content!r}

Does the marker's nearby content genuinely match this specific
ground-truth {anchor_label} content -- verbatim, or as a paraphrase that
keeps its specific point (a name, number, date, comparison, or reason,
not just the general topic)? Or does the marker's nearby content
actually describe something ELSE, a different, non-matching fact?

Output strict JSON with exactly these keys:
  "attached_correctly": true or false
  "reasoning": one sentence explaining your answer

Return only valid JSON. Do not include Markdown code fences or additional
text.
"""


def llm_judge_paragraph_severance_condition_concession_v3(paragraph, relation, propositions, model=None):
    """Corrected Condition/Concession-only severance judge, v3
    (two-call locator + narrow mismatch-detection architecture).

    Returns {"preserved": bool or None, "nucleus_found": bool or None,
    "satellite_found": bool or None, "marker_found": bool or None,
    "attachment_check_ran": bool, "attachment_correct": bool or None,
    "flagged_marker_floating": bool, "reasoning": str}.

    `preserved` is None only on an outright call/parse failure in the
    locator call -- same contract as llm_judge_paragraph_severance.

    Deterministic decision logic (not a model call):
      - nucleus or satellite content not found anywhere -> severed
        (content genuinely absent).
      - nucleus and satellite share a proposition index AND a
        connective also occurs at that shared index -> preserved
        immediately (all three co-located, trivially attached).
      - nucleus and satellite are in different propositions:
          - a connective occurs at the nucleus index OR the satellite
            index (checked symmetrically -- the marker may legitimately
            sit next to EITHER clause, e.g. marking the turn back to an
            already-stated satellite, not just introducing it, see the
            v1/v2 PROMPT ITERATION NOTE): run the narrow attachment
            mismatch check against that anchor. Preserved only if the
            mismatch check confirms a genuine match.
          - no connective occurs at either index: if no connective
            exists anywhere in the propositions, severed (marker
            genuinely dropped). If a connective exists but floats
            somewhere unconnected to either clause, severed, but
            flagged explicitly ("flagged_marker_floating": true) for
            manual review rather than silently trusted, since this
            branch was not covered by the validation set's known cases.

    Callers MUST route Condition/Concession relations to this function,
    Elaboration to llm_judge_paragraph_severance_elaboration_v2, and
    None to llm_judge_paragraph_severance (the original).
    """
    if relation.get("relation_type") not in ("Condition", "Concession"):
        raise ValueError(
            "FATAL: llm_judge_paragraph_severance_condition_concession_v3 is "
            f"Condition/Concession-only; got relation_type={relation.get('relation_type')!r}. "
            "Use llm_judge_paragraph_severance_elaboration_v2 for Elaboration or "
            "llm_judge_paragraph_severance (the original) for None."
        )
    model = model or DEFAULT_JUDGE_MODEL
    relation_type = relation.get("relation_type")

    locator_prompt = build_cc_locator_prompt(paragraph, relation, propositions)
    locator_response = generate_response(locator_prompt, model=model)
    if not locator_response or not hasattr(locator_response, "content"):
        return {
            "preserved": None, "nucleus_found": None, "satellite_found": None,
            "marker_found": None, "attachment_check_ran": False,
            "attachment_correct": None, "flagged_marker_floating": False,
            "reasoning": "LLM-judge call failed: no model response (locator call).",
        }
    locator_data = extract_json_from_response(locator_response.content)
    if not locator_data:
        return {
            "preserved": None, "nucleus_found": None, "satellite_found": None,
            "marker_found": None, "attachment_check_ran": False,
            "attachment_correct": None, "flagged_marker_floating": False,
            "reasoning": "LLM-judge call failed: unparseable JSON response (locator call).",
        }

    nucleus_indices = set(locator_data.get("nucleus_indices") or [])
    satellite_indices = set(locator_data.get("satellite_indices") or [])
    connective_occurrences = locator_data.get("connective_occurrences") or []
    connective_indices = {c.get("index") for c in connective_occurrences if isinstance(c, dict)}

    nucleus_found = bool(nucleus_indices)
    satellite_found = bool(satellite_indices)
    marker_found = bool(connective_indices)

    if not nucleus_found or not satellite_found:
        missing = []
        if not nucleus_found:
            missing.append("nucleus")
        if not satellite_found:
            missing.append("satellite")
        return {
            "preserved": False, "nucleus_found": nucleus_found,
            "satellite_found": satellite_found, "marker_found": marker_found,
            "attachment_check_ran": False, "attachment_correct": None,
            "flagged_marker_floating": False,
            "reasoning": f"Content genuinely absent: {' and '.join(missing)} not "
                         f"found in any proposition.",
        }

    shared_indices = nucleus_indices & satellite_indices

    # Decide whether an attachment check is needed, and against which
    # anchor, in three distinct structural cases:
    #
    #  (a) Co-located: nucleus and satellite share a proposition index,
    #      AND a connective also occurs at one of the shared indices.
    #      This does NOT auto-preserve -- a merged sentence can still
    #      have the connective fronted onto the WRONG clause (confirmed
    #      real case: pool 4117/arm_2, "Although [nucleus], [satellite]"
    #      instead of the source's "[nucleus], although [satellite]" --
    #      reverses which fact is conceded to which even though both
    #      facts and the connective are all present in one sentence). So
    #      co-located cases are always checked against the SATELLITE
    #      specifically: a genuinely correct merge has the connective's
    #      own clause matching the satellite (see pool 4117/arm_3:
    #      "Dutch was allowed..., although French remained...", where
    #      "although" directly precedes the satellite).
    #  (b) Split, connective anchored to the satellite index: same check
    #      as (a), against the satellite -- this is the classic
    #      "Although Q, [nucleus]" pattern, and Q must match the
    #      ground-truth satellite (this is what catches pool 3278/arm_4
    #      and pool 4200/arm_4's misattachment).
    #  (c) Split, connective anchored ONLY to the nucleus index (not the
    #      satellite index), with the satellite independently, correctly
    #      located in a separate, unmarked proposition elsewhere
    #      (confirmed real, legitimate case: pool 2272, "[satellite
    #      stated plainly]. However, [nucleus, marking the turn]." --
    #      RST does not require the satellite itself to carry a marker
    #      when it was already asserted). No further check is run here:
    #      the marker's own clause will always roughly restate the
    #      nucleus (that is tautological, since that is where nucleus
    #      was located), so asking a model to "verify" it against the
    #      nucleus produced spurious rejections in testing (see the
    #      PROMPT ITERATION NOTE). What actually matters here -- the
    #      satellite being real and separately present -- was already
    #      confirmed by the nucleus_found/satellite_found check above.
    if shared_indices and (shared_indices & connective_indices):
        anchor_idx = sorted(shared_indices & connective_indices)[0]
        anchor_label = "satellite"
        anchor_content = relation.get("satellite")
    elif connective_indices & satellite_indices:
        anchor_idx = sorted(connective_indices & satellite_indices)[0]
        anchor_label = "satellite"
        anchor_content = relation.get("satellite")
    elif connective_indices & nucleus_indices:
        anchor_idx = sorted(connective_indices & nucleus_indices)[0]
        return {
            "preserved": True, "nucleus_found": True, "satellite_found": True,
            "marker_found": True, "attachment_check_ran": False,
            "attachment_correct": None, "flagged_marker_floating": False,
            "reasoning": "Connective anchors to the nucleus (proposition "
                         f"{anchor_idx}), marking the turn back to the "
                         "satellite, which is independently and correctly "
                         "located in its own separate proposition -- a "
                         "legitimate pattern, no further check needed "
                         "(see pool 2272).",
        }
    else:
        anchor_idx = None

    if anchor_idx is None:
        if not marker_found:
            return {
                "preserved": False, "nucleus_found": True, "satellite_found": True,
                "marker_found": False, "attachment_check_ran": False,
                "attachment_correct": None, "flagged_marker_floating": False,
                "reasoning": "No connective/marker found anywhere in the "
                             "propositions -- the relationship's signal is "
                             "genuinely dropped.",
            }
        return {
            "preserved": False, "nucleus_found": True, "satellite_found": True,
            "marker_found": True, "attachment_check_ran": False,
            "attachment_correct": None, "flagged_marker_floating": True,
            "reasoning": "A connective was found, but not at the same "
                         "proposition index as either the nucleus or the "
                         "satellite -- flagged for manual review, not a "
                         "case class covered by validation.",
        }

    nearby_description = next(
        (c.get("nearby_content") for c in connective_occurrences
         if isinstance(c, dict) and c.get("index") == anchor_idx),
        "",
    )
    mismatch_prompt = build_cc_attachment_mismatch_prompt(
        relation_type, anchor_label, anchor_content, nearby_description
    )
    mismatch_response = generate_response(mismatch_prompt, model=model)
    if not mismatch_response or not hasattr(mismatch_response, "content"):
        return {
            "preserved": None, "nucleus_found": True, "satellite_found": True,
            "marker_found": True, "attachment_check_ran": True,
            "attachment_correct": None, "flagged_marker_floating": False,
            "reasoning": "LLM-judge call failed: no model response (attachment check call).",
        }
    mismatch_data = extract_json_from_response(mismatch_response.content)
    if not mismatch_data:
        return {
            "preserved": None, "nucleus_found": True, "satellite_found": True,
            "marker_found": True, "attachment_check_ran": True,
            "attachment_correct": None, "flagged_marker_floating": False,
            "reasoning": "LLM-judge call failed: unparseable JSON response (attachment check call).",
        }

    attached_correctly = bool(mismatch_data.get("attached_correctly"))
    return {
        "preserved": attached_correctly,
        "nucleus_found": True, "satellite_found": True, "marker_found": True,
        "attachment_check_ran": True, "attachment_correct": attached_correctly,
        "flagged_marker_floating": False,
        "reasoning": f"Marker anchored to {anchor_label} (proposition "
                     f"{anchor_idx}); mismatch check: "
                     f"{mismatch_data.get('reasoning', '')}",
    }


# --- Condition/Concession (deletion/replacement test): a fourth, --------
# independent ensemble member, added for the ensemble-disagreement
# reframe of Experiment 3's ground truth. NOT a paraphrase of what the
# deletion/replacement test is thought to imply -- it applies the test
# itself, quoted verbatim from the primary source:
#
#   Carlson, L. and Marcu, D. (2001). "Discourse Tagging Reference
#   Manual." ISI Technical Report ISI-TR-545, p. 31:
#     "Deletion test: When a satellite of a relation is deleted, the
#     segment that is left, i.e., the nucleus, can still perform the
#     same function in the text, although it may be somewhat weaker.
#     When the nucleus is deleted, the segment that is left is much
#     less coherent."
#     "Replacement test: Unlike the nucleus, a satellite can be
#     replaced with different information without altering the
#     function of the segment."
#   (verbatim from literature/carlson_2001_discourse/paper.pdf, lines
#   1546-1549 of its extracted text -- checked directly, not quoted
#   from memory.)
#
# One-sentence justification (grounding this member against (a)/(b)/v3,
# per the pre-registration requirement below): unlike (a) ("would a
# reader understand the relationship") and (b)/v3 (does the marker
# attach to the correct content), this member asks a structurally
# DIFFERENT question -- is the satellite's specific content doing real
# FUNCTIONAL work on the nucleus (removing it would leave the nucleus
# "somewhat weaker" but still functioning; swapping it for different
# content WOULD change how the nucleus reads), or has atomization
# flattened the satellite into a freely-detachable, freely-substitutable
# fact that could be swapped for any other true statement about the
# same topic without changing the nucleus's assertion at all -- which is
# this project's own definition of severance (the split output no
# longer conveys that the qualifying clause limits the main clause).
# Carlson & Marcu built these two tests to help a human ANNOTATOR decide
# nucleus/satellite ROLE at tagging time; applied here, the nucleus and
# satellite roles are already fixed (elicited earlier), so the tests are
# repurposed as an EVALUATION check -- does the atomized output still
# exhibit the functional asymmetry the tests describe, not re-derive
# which segment is which.
_CC_DELETION_REPLACEMENT_PROMPT_MARKER = "the deletion test and the replacement test"


def build_cc_deletion_replacement_prompt(paragraph, relation, propositions):
    """Condition/Concession-only judge prompt anchored strictly to
    Carlson & Marcu's deletion and replacement tests (quoted above),
    applied to already-atomized output rather than to segmenting raw
    text. Must only be used when relation["relation_type"] is
    "Condition" or "Concession".
    """
    props_block = "\n".join(f"- {p}" for p in propositions) or "(no propositions produced)"
    relation_type = relation.get("relation_type", "Concession")
    nucleus = relation.get("nucleus")
    satellite = relation.get("satellite")
    connective = relation.get("connective", "")
    return f"""
Original paragraph (context ONLY -- do not base your answer on this, only
on the atomized propositions below): "{paragraph}"

Discourse relation identified in the original paragraph: {relation_type}
Nucleus (the governed/asserted clause): {nucleus!r}
Satellite (the qualifying/conceding clause): {satellite!r}
Connective in the original text: {connective!r}

Atomized propositions (this is what a downstream reader would actually
see, with NO access to the original paragraph -- judge them TOGETHER, as
the full set a reader would have):
{props_block}

Apply {_CC_DELETION_REPLACEMENT_PROMPT_MARKER}, quoted here verbatim from
Carlson & Marcu's (2001) Discourse Tagging Reference Manual (the RST
annotation standard this project cites throughout), to the atomized
propositions above -- not to the original paragraph:

  Deletion test: "When a satellite of a relation is deleted, the segment
  that is left, i.e., the nucleus, can still perform the same function
  in the text, although it may be somewhat weaker. When the nucleus is
  deleted, the segment that is left is much less coherent."

  Replacement test: "Unlike the nucleus, a satellite can be replaced
  with different information without altering the function of the
  segment."

Apply these tests to what the atomized propositions actually show, not
to your own judgment of the original sentence:

Step 1 (deletion test): if you notionally remove, from the set of
propositions above, whichever ones state the satellite's specific
content, does what remains still state the nucleus's content performing
the SAME function it had in the original paragraph -- i.e. still
appropriately governed/qualified/conceded, even if only weakly signaled
-- or does the nucleus now read as an unconditional, ungoverned
statement it was not in the original? Set "nucleus_survives_deletion" to
true only if the nucleus's governed status is still evident without the
satellite propositions, even weakly.

Step 2 (replacement test, applied as a discriminator): is the
satellite's content in the atomized propositions doing real, specific
work on the nucleus -- would swapping it for a different, unrelated
true fact about the same topic change how the nucleus reads or what
qualifies it -- or does the satellite's content sit alongside the
nucleus as an independent, freely-detachable fact that could be
replaced by any other true statement without changing anything about
the nucleus's own assertion? Set "satellite_does_functional_work" to
true only if the satellite could NOT be freely swapped for unrelated
content without changing the nucleus's governed status (i.e. the
opposite of what the replacement test says is true of a REAL satellite
in its original role -- here you are checking whether the atomized
output still shows the satellite in that non-substitutable, governing
role, not whether it is technically substitutable in principle).

Answer "preserved": true only if BOTH "nucleus_survives_deletion" and
"satellite_does_functional_work" are true.

Output strict JSON with exactly these keys:
  "preserved": true or false
  "nucleus_survives_deletion": true or false
  "satellite_does_functional_work": true or false
  "reasoning": one or two sentences explaining your answer, referring
    back to the deletion and replacement tests by name

Return only valid JSON. Do not include Markdown code fences or additional
text.
"""


def llm_judge_paragraph_severance_deletion_replacement(paragraph, relation, propositions, model=None):
    """Condition/Concession-only severance judge built on Carlson &
    Marcu's deletion/replacement tests (see the block comment above for
    the primary-source quote and the grounding justification). Returns
    {"preserved": bool or None, "nucleus_survives_deletion": bool or
    None, "satellite_does_functional_work": bool or None, "reasoning":
    str}. `preserved` is None only on an outright call/parse failure --
    same contract as llm_judge_paragraph_severance.

    NOT validated at scale as of writing -- this is the member under
    validation in the ensemble-disagreement check, not an established
    production judge like (a) above.
    """
    if relation.get("relation_type") not in ("Condition", "Concession"):
        raise ValueError(
            "FATAL: llm_judge_paragraph_severance_deletion_replacement is "
            f"Condition/Concession-only; got relation_type={relation.get('relation_type')!r}."
        )
    model = model or DEFAULT_JUDGE_MODEL
    prompt = build_cc_deletion_replacement_prompt(paragraph, relation, propositions)
    response = generate_response(prompt, model=model)
    if not response or not hasattr(response, "content"):
        return {
            "preserved": None, "nucleus_survives_deletion": None,
            "satellite_does_functional_work": None,
            "reasoning": "LLM-judge call failed: no model response.",
        }
    data = extract_json_from_response(response.content)
    if not data:
        return {
            "preserved": None, "nucleus_survives_deletion": None,
            "satellite_does_functional_work": None,
            "reasoning": "LLM-judge call failed: unparseable JSON response.",
        }
    return {
        "preserved": bool(data.get("preserved")),
        "nucleus_survives_deletion": data.get("nucleus_survives_deletion"),
        "satellite_does_functional_work": data.get("satellite_does_functional_work"),
        "reasoning": data.get("reasoning", ""),
    }


def llm_judge_paragraph_severance_elaboration_v2(paragraph, relation, propositions, model=None):
    """Corrected Elaboration-only severance judge, paragraph-adapted.
    Returns {"preserved": bool or None, "nucleus_recoverable": bool or
    None, "reasoning": str}. `preserved` is None only on an outright
    call/parse failure -- same contract as llm_judge_paragraph_severance.
    `reasoning` is logged verbatim for every call so disagreements can be
    audited later.

    See ../severance_detection.py's llm_judge_severance_elaboration_v2
    docstring for the "PROMPT ITERATION NOTE" documenting why an earlier
    separate-evidence-quoting version of this prompt was tried and
    discarded (it over-corrected gpt-4o-mini into fabricating
    deficiencies on straightforward merged cases) -- this paragraph-level
    prompt is kept in lockstep with that one's final design.

    Callers MUST route Elaboration relations to this function and every
    other relation type to `llm_judge_paragraph_severance` (the
    original) -- this function does not itself branch on relation_type.
    """
    if relation.get("relation_type") != "Elaboration":
        raise ValueError(
            "FATAL: llm_judge_paragraph_severance_elaboration_v2 is "
            f"Elaboration-only; got relation_type={relation.get('relation_type')!r}. "
            "Use llm_judge_paragraph_severance (the original judge) for "
            "Condition/Concession/None."
        )
    model = model or DEFAULT_JUDGE_MODEL
    prompt = build_paragraph_judge_prompt_elaboration_v2(paragraph, relation, propositions)
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
