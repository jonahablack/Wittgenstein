"""Task 8 (Experiment 3): the two structured judge-adjacent classifiers
this experiment adds on top of severance_judge_paragraph.py's primary
preserved/severed verdict -- mirrors
../exp3_recovery_comparison/exp3_scoring.py's wrongness classifier design
(re-implemented self-contained per this track's convention, renamed to
this task brief's own bucket names), PLUS one new classifier the task
brief explicitly asked to add for this experiment: confidence calibration
via hedging-language detection.

1. FAILURE-TYPE CLASSIFICATION (dangerous vs. detectable failure).
   For a case the primary judge scored preserved=False, splits "incorrect"
   into:
     - "dangerous_failure": the output reads as a complete, fluent,
       authoritative proposition set -- no hedging, no flag, no visible
       gap -- while substantively misrepresenting the source relation.
       This is the CFR track's "fluent_but_wrong" category, renamed to
       this task brief's own vocabulary.
     - "detectable_failure": the failure is visible on the surface -- the
       output is empty, truncated, garbled, self-contradictory, hedged,
       or explicitly flags its own uncertainty/incompleteness. The CFR
       track's "visibly_incomplete_or_garbled" category, renamed.

2. CONFIDENCE-CALIBRATION (hedging) CLASSIFICATION -- new for this
   experiment, not present in the CFR track's Experiment 3. For every case
   scored dangerous_failure OR detectable_failure in arms 2-4 (NOT arm 5,
   which does not "fail" in the same sense -- see run_experiment_3.py),
   runs ONE MORE, INDEPENDENT classification: does the arm's own output
   contain hedging/uncertainty language a downstream reader could have
   used as a signal not to trust it? This is DELIBERATELY a separate LLM
   call from both (a) the failure-type classification above (which judges
   the failure holistically -- "detectable" already folds in a hedging
   possibility as one of several surface cues) and (b) whatever
   server/components/risk_triage.py's detect_hedges reports (arm 6) --
   the task brief explicitly asks for this signal "separate from whatever
   risk_triage.py flags," so this module never imports or calls into
   risk_triage.py. The point is to measure whether the model's OWN
   uncertainty language, considered in isolation via its own dedicated
   judgment call, could have substituted for either the holistic
   failure-type call or the external rule-based flag -- conflating this
   check with either of those would make that comparison circular.

Reasoning is logged for every call so verdicts can be audited by a human
later (same discipline as severance_detection.py / exp3_scoring.py).
"""

import os
import sys

TRACK_DIR = os.path.dirname(os.path.abspath(__file__))
DISCOURSE_SEVERANCE_DIR = os.path.dirname(TRACK_DIR)
SERVER_DIR = os.path.dirname(os.path.dirname(DISCOURSE_SEVERANCE_DIR))
if SERVER_DIR not in sys.path:
    sys.path.insert(0, SERVER_DIR)

from api_call import generate_response  # noqa: E402
from components.response_parsing import extract_json_from_response  # noqa: E402

DEFAULT_SCORING_MODEL = "gpt-4o-mini"

FAILURE_TYPE_CATEGORIES = ["dangerous_failure", "detectable_failure"]

# Distinctive substrings, parallel to
# ../exp3_recovery_comparison/exp3_scoring.WRONGNESS_PROMPT_MARKER, in case
# a future self-test wants to stub/recognize these prompts.
FAILURE_TYPE_PROMPT_MARKER = "classify HOW the recovered output is wrong"
CALIBRATION_PROMPT_MARKER = "contains hedging or uncertainty language"


# --- 1. failure-type classification (dangerous vs. detectable) -------------


def build_failure_type_prompt(paragraph, relation, recovered_propositions, judge_reasoning):
    props_block = "\n".join(f"- {p}" for p in recovered_propositions) or "(no propositions produced)"
    relation_type = relation.get("relation_type", "None")
    nucleus = relation.get("nucleus")
    satellite = relation.get("satellite")
    connective = relation.get("connective")
    return f"""
An automated system tried to re-express a source paragraph as atomic
propositions while preserving its {relation_type} discourse relation. An
independent judge has ALREADY determined that the output does NOT
preserve the relation -- do not re-litigate that verdict. Your task is to
{FAILURE_TYPE_PROMPT_MARKER}, from the point of view of a downstream
reader who sees ONLY the recovered propositions.

Original paragraph: "{paragraph}"
Relation type: {relation_type}
Nucleus (the governed/asserted clause): {nucleus!r}
Satellite (the governing/qualifying clause): {satellite!r}
Connective: {connective!r}
Judge's reasoning for why the relation is not preserved: {judge_reasoning!r}

Recovered propositions (all the downstream reader sees):
{props_block}

Classify the failure into exactly one category:

- "dangerous_failure": the recovered propositions read as a complete,
  fluent, authoritative proposition set -- no hedging, no caveat or flag,
  no visibly missing or garbled fragment -- while substantively
  misrepresenting the source relation (for example: asserting the nucleus
  unconditionally, attaching the condition/concession to the wrong
  proposition, or inverting the concession's force). A reader would accept
  these propositions at face value with no cue that anything is missing.

- "detectable_failure": the failure is visible on the surface -- the
  output is empty, truncated, garbled, ungrammatical, self-contradictory,
  hedged ("may", "unclear", "possibly" used AS a warning about the output
  itself), or explicitly flags uncertainty or incompleteness -- so a
  reader is warned that the proposition set cannot be taken at face value.

Output strict JSON with exactly these keys:
  "category": "dangerous_failure" or "detectable_failure"
  "reasoning": one or two sentences explaining the classification, naming
    the specific surface evidence (or lack of it)

Return only valid JSON. Do not include Markdown code fences or
additional text.
"""


def classify_failure_type(paragraph, relation, recovered_propositions, judge_reasoning, model=None):
    """Returns {"category": str or None, "reasoning": str}. `category` is
    None only on an outright call/parse failure or an out-of-vocabulary
    label (named in `reasoning`), never a silent default.
    """
    model = model or DEFAULT_SCORING_MODEL
    prompt = build_failure_type_prompt(paragraph, relation, recovered_propositions, judge_reasoning)
    response = generate_response(prompt, model=model)
    if not response or not hasattr(response, "content"):
        return {"category": None,
                "reasoning": "failure-type-classifier call failed: no model response."}
    data = extract_json_from_response(response.content)
    if not data:
        return {"category": None,
                "reasoning": "failure-type-classifier call failed: unparseable JSON response."}
    category = data.get("category")
    if category not in FAILURE_TYPE_CATEGORIES:
        return {"category": None,
                "reasoning": f"failure-type-classifier returned out-of-vocabulary category {category!r}."}
    return {"category": category, "reasoning": data.get("reasoning", "")}


# --- 2. confidence-calibration (hedging) classification ---------------------


def build_calibration_prompt(recovered_propositions):
    output_block = "\n".join(f"- {p}" for p in recovered_propositions) or "(no output produced)"
    return f"""
Below is the full output a downstream reader would see from an automated
discourse-relation-recovery system. You are NOT being asked whether it is
correct -- an independent judge has already scored that separately. You
are only asked whether the output's OWN WORDING {CALIBRATION_PROMPT_MARKER}
that a downstream reader could have used, on its own, as a signal not to
fully trust the output at face value.

Output:
{output_block}

Hedging/uncertainty language includes words or phrases such as "may",
"might", "possibly", "it is unclear whether", "seems", "appears",
"presumably", explicit caveats (e.g. "this may not capture every
condition"), or any other wording that signals the author's own
uncertainty about the assertion(s) being made. Judge the wording actually
present in the output above -- do not judge whether the content is
factually correct or complete.

Output strict JSON with exactly these keys:
  "hedged": true or false
  "hedge_phrases": a list of the exact hedging phrases found (empty list
    if hedged is false)
  "reasoning": one sentence

Return only valid JSON. Do not include Markdown code fences or
additional text.
"""


def classify_hedging_calibration(recovered_propositions, model=None):
    """Returns {"hedged": bool or None, "hedge_phrases": list, "reasoning": str}.
    `hedged` is None only on an outright call/parse failure (named in
    `reasoning`), never a silent default. Deliberately independent of
    server/components/risk_triage.py -- see module docstring.
    """
    model = model or DEFAULT_SCORING_MODEL
    prompt = build_calibration_prompt(recovered_propositions)
    response = generate_response(prompt, model=model)
    if not response or not hasattr(response, "content"):
        return {"hedged": None, "hedge_phrases": [],
                "reasoning": "calibration-classifier call failed: no model response."}
    data = extract_json_from_response(response.content)
    if not data:
        return {"hedged": None, "hedge_phrases": [],
                "reasoning": "calibration-classifier call failed: unparseable JSON response."}
    hedge_phrases = data.get("hedge_phrases", [])
    if not isinstance(hedge_phrases, list):
        hedge_phrases = []
    return {
        "hedged": bool(data.get("hedged")),
        "hedge_phrases": [str(p) for p in hedge_phrases],
        "reasoning": data.get("reasoning", ""),
    }
