"""Task 5: zero-shot LLM relation classifier for Condition/Concession/
Elaboration/None on a SOURCE PARAGRAPH (not an already-atomized
proposition).

Adapted from ../relation_elicitation.py's pattern (read first, per this
pilot's task spec) with two deliberate differences:

1. Operates on a whole source paragraph (Wikipedia prose, the `content`
   field from the propositionizer-wiki-data records), not a single
   sentence from a regulatory document. Paragraphs can contain several
   sentences/clauses, so the prompt asks for the SINGLE relation that
   most organizes the paragraph if more than one could apply.

2. Does NOT offer "Exception" as a separate category. Per this project's
   corrected RST understanding (a parallel task is reclassifying
   regulatory-text "Exception" sentences into Condition right now),
   restrictive/exceptive conditions ("except when X", "unless X") are
   Condition under RST's own definition, not a separate relation. The
   Condition bullet below says so explicitly so the model doesn't invent
   an Exception bucket on its own.

The Condition and Concession definitions below are used VERBATIM, per
task instructions, from the verified definitions supplied for this
pilot -- not paraphrased from memory:

    CONDITION: satellite presents a hypothetical, future, or otherwise
    unrealized situation; the nucleus's realization depends on the
    satellite's realization.

    CONCESSION: nucleus and satellite present an apparent-but-not-actual
    incompatibility; the writer's positive regard for the nucleus
    increases once the reader recognizes they're actually compatible.

Elaboration and None reuse ../relation_elicitation.py's existing working
definitions verbatim (that pilot's task spec only flagged the
Condition/Concession grounding and the Exception-as-separate-category
issue as needing correction; Elaboration/None were not flagged).

TASK 5b REVISION (2026-08): a manual spot-check of the Task 5 raw output
above (39 hits reviewed; see README.md's Task 5 section and
results/task5_relation_screening_report.json) found only ~35-45%
precision against these same verbatim definitions, with four specific,
recurring failure modes:

  1. Causal "because"/"since" explanations mislabeled as Concession (a
     plain causal reason is not an apparent-but-resolved
     INCOMPATIBILITY).
  2. Purpose/goal clauses ("to avoid X", "in order to X", "to maximize
     Y") mislabeled as Condition (a goal is not a hypothetical/future/
     unrealized precondition the nucleus depends on).
  3. Past-tense narrative "when" clauses mislabeled as Condition (an
     already-happened, narrated event is not "unrealized" merely
     because the word "when" introduces it).
  4. Plain narrative contrast ("X, but Y") mislabeled as Concession,
     absent the writer-regard-for-the-nucleus-survives-an-apparent-
     incompatibility dynamic Concession actually requires.

build_paragraph_relation_prompt() below is the REVISED prompt used from
Task 5b onward. The Condition and Concession bullets keep the exact
verbatim definitions above, character-for-character, UNCHANGED; each
bullet gains an appended "Do NOT classify as X when..." block giving a
short negative example for each of the two failure modes it is prone to
(quoted from the four above), plus a checklist question the model must
satisfy before assigning that label. The output JSON schema also gained
one new first key, "rationale" (a one-sentence, criterion-referencing
justification that must be written BEFORE "relation_type" in generation
order), as a lightweight forcing function for the model to check its
own answer against the negative examples rather than pattern-match on a
surface connective. The four-way output space
(Condition/Concession/Elaboration/None) and the existing "except
when/unless X is Condition, not a separate category" instruction are
both unchanged. Elaboration/None's own definitions are also unchanged
(not flagged by the spot-check).

This revised prompt was piloted on a FRESH, disjoint batch of paragraphs
(pool_index 903+, vs. the original 903 at pool_index 0-902 -- see
run_relation_screening.py's --log-file/--report-file flags and
results/task5b_revised_precision_report.json), not by re-scoring the
original batch. So the before/after comparison in README.md's Task 5b
section is old-prompt-on-batch-1 vs. new-prompt-on-batch-2, not a
same-batch before/after -- batch-to-batch sampling variance is a real,
if probably small, confound that comparison flags explicitly rather
than hiding.
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

RELATION_TYPES = ["Condition", "Concession", "Elaboration", "None"]

PROMPT_MARKER = "You are a discourse-relation annotator."


def build_paragraph_relation_prompt(paragraph):
    return f"""{PROMPT_MARKER} Read ONE paragraph of Wikipedia prose and \
decide whether it contains one of the following relations between two \
of its clauses/sentences. These are narrow, RST-derived categories --
use exactly these definitions, not a broader relation inventory:

- Condition: satellite presents a hypothetical, future, or otherwise
  unrealized situation; the nucleus's realization depends on the
  satellite's realization ("if X, then Y"; "when X, Y"; "in the event
  that X, Y"). This INCLUDES restrictive/exceptive framing such as
  "except when X", "unless X", "except that X", "provided that X" --
  under RST's own definition these are Condition, NOT a separate
  category. Do not invent an "Exception" label; classify these as
  Condition.

  Do NOT classify as Condition when the satellite is actually one of
  these two commonly-confused patterns:
  * A PURPOSE/GOAL clause ("to avoid X", "in order to X", "to maximize
    Y", "so that X", "aimed at X") stating WHY the nucleus's action was
    taken. A goal is not a hypothetical/future/unrealized situation the
    nucleus depends on -- it is the nucleus's motivation, not its
    precondition. NOT Condition example: "The shield is angled to
    maximize capture of forward-scattered radiation." -- "to maximize
    capture..." is the PURPOSE of angling the shield, not an unrealized
    precondition the angling depends on; this is Elaboration or None,
    never Condition.
  * A PAST-tense "when" clause narrating a specific, completed,
    one-time historical event ("When the IAFE was transformed into a
    state-run agency in 1937, its mandate expanded"). Condition's
    "when" must be hypothetical, generic/habitual, or future; an
    already-happened narrated event is not "unrealized" just because
    the word "when" introduces it -- it functions like "while" / "at
    the time that". NOT Condition example: "When the bridge reopened in
    1998, traffic patterns shifted." -- a narrated past event, not a
    hypothetical/unrealized precondition; this is Elaboration or None,
    never Condition.
  Before assigning Condition, check: is the satellite genuinely
  hypothetical/future/unrealized (not narrated as something that
  definitely already happened), AND does the nucleus's realization
  actually depend on the satellite (rather than the satellite merely
  explaining the nucleus's motive/purpose)?

- Concession: nucleus and satellite present an apparent-but-not-actual
  incompatibility; the writer's positive regard for the nucleus
  increases once the reader recognizes they're actually compatible
  ("although X, Y"; "even though X, Y"; "despite X, Y"; "X, but Y is
  still true").

  Do NOT classify as Concession when:
  * The connective is a CAUSAL reason-giver -- "because", "since", "due
    to", "as a result of" -- rather than a concessive one. A causal
    clause explains WHY the nucleus is true; it presents no apparent
    incompatibility to resolve. NOT Concession example: "The bridge
    collapsed because of corrosion." -- "because" gives a plain causal
    reason; there is no apparent clash between nucleus and satellite
    that resolves into compatibility. This is Elaboration or None,
    never Concession.
  * It is plain narrative contrast -- two facts that merely differ or
    sit in tension ("X, but Y"; "X. However, Y.") without the writer
    signaling that an apparent incompatibility resolves in the
    nucleus's favor. NOT Concession example: "The team traveled to the
    capital, but the meeting was cancelled." -- a plain sequential/
    contrastive fact, not a resolved apparent-incompatibility with
    sustained positive regard for the nucleus. This is Elaboration or
    None, never Concession.
  Before assigning Concession, check: is there a genuine APPARENT
  incompatibility that gets surfaced and then resolved/recognized as
  compatible (not just a cause-effect explanation or a bare factual
  contrast), and does the writer's regard for the nucleus survive or
  increase because of that resolution?

- Elaboration: the satellite adds independently-true supporting detail,
  example, restatement, or list-expansion about the nucleus, WITHOUT
  governing whether the nucleus holds -- the nucleus would still be true
  even if the satellite were removed or turned out false.
- None: the paragraph does not clearly instantiate any of the above (a
  bare list/sequence of independent facts, a definition, or purely
  descriptive/factual assertions with no conditional or concessive
  clause-governing structure).

If more than one relation could arguably apply somewhere in the
paragraph, pick the SINGLE relation that most governs/organizes the
paragraph's overall structure. A paragraph may be long and contain many
independent facts; that alone does not make it Elaboration -- only mark
Elaboration if the satellite/supporting-detail relationship is actually
the dominant structure. If nothing in the paragraph clearly instantiates
Condition or Concession, and it is not dominantly an
elaboration/supporting-detail structure either, use None.

Paragraph: "{paragraph}"

Output strict JSON with exactly these keys, IN THIS ORDER:
  "rationale": ONE short sentence, written BEFORE you decide
    relation_type, that checks the paragraph against the "Do NOT
    classify as..." criteria above. For a candidate Condition, confirm
    the satellite is genuinely hypothetical/future/unrealized and is
    not really a purpose clause or a completed past narrated event.
    For a candidate Concession, confirm there is a genuine apparent
    incompatibility being resolved and it is not really a causal
    "because"/"since" explanation or a plain contrast. For a candidate
    Elaboration or None, briefly state why none of the above apply.
    Let this check determine your relation_type answer below, rather
    than writing a rationale to match a relation_type you already
    picked.
  "relation_type": one of "Condition", "Concession", "Elaboration",
    "None"
  "nucleus": the governed/asserted clause or sentence, as a VERBATIM
    substring of the paragraph, or null if relation_type is "None"
  "satellite": the governing/qualifying clause or sentence, as a
    VERBATIM substring of the paragraph, or null if relation_type is
    "None"
  "connective": the connective word or phrase that signals the relation,
    VERBATIM (e.g. "unless", "although", "despite"), or null if
    relation_type is "None"

Return only valid JSON. Do not include Markdown code fences or
additional text.
"""


def _empty_relation(error=None):
    result = {
        "relation_type": "None",
        "nucleus": None,
        "satellite": None,
        "connective": None,
        "rationale": None,
    }
    if error:
        result["_error"] = error
    return result


def classify_paragraph(paragraph, model=None):
    """One LLM call: classify `paragraph` into one of RELATION_TYPES and
    extract nucleus/satellite/connective/rationale. Returns a dict; on
    any failure (no response, unparseable JSON, invalid relation_type)
    returns _empty_relation() with an "_error" key set, rather than
    raising -- a large screening batch needs to keep going past
    occasional failures, same pattern as relation_elicitation.py.

    "rationale" (added in the Task 5b prompt revision -- see this
    module's docstring) is carried through verbatim from the model's
    output, unvalidated, purely so a downstream spot-check can see the
    model's own stated justification alongside its label; nothing here
    parses or enforces it.
    """
    prompt = build_paragraph_relation_prompt(paragraph)
    response = generate_response(prompt, model=model)
    if not response or not hasattr(response, "content"):
        return _empty_relation(error="no_response")

    data = extract_json_from_response(response.content)
    if not data:
        return _empty_relation(error="unparseable_json")

    relation_type = data.get("relation_type")
    if relation_type not in RELATION_TYPES:
        return _empty_relation(error=f"invalid_relation_type:{relation_type!r}")

    return {
        "relation_type": relation_type,
        "nucleus": data.get("nucleus"),
        "satellite": data.get("satellite"),
        "connective": data.get("connective"),
        "rationale": data.get("rationale"),
    }
