"""Scoring for Experiment 3's two automated-recovery arms.

Correctness is judged with the SAME LLM-judge methodology as the
original severance experiment (../severance_detection.py) -- the
recovered claim set is judged exactly the way atomized claim sets were
judged, so arm-1/arm-2 numbers are commensurable with the Experiment 1
numbers:

  - Primary reading: `judge_prompt_full_nucleus`
    (severance_detection.llm_judge_severance).
  - Alternative reading, bundled-nucleus subset only:
    `judge_prompt_subclause`
    (severance_detection.llm_judge_severance_subclause), with the
    governed sub-clause taken from ../audit_addendum.json's A1 records
    -- reported side by side, mirroring how the audit reported them.
  No third judge prompt is introduced.

This module adds ONE new structured judge call: the wrongness
classifier. For a case the primary judge scored preserved=False, it
separates "incorrect" into:

  - "fluent_but_wrong": the recovered output reads as a complete,
    fluent, authoritative claim set -- no hedging, no flag, no visible
    gap -- while substantively misrepresenting the source relation
    (e.g. asserting the nucleus unconditionally, attaching the
    condition to the wrong sub-clause, inverting exception scope).
    This is the confidently-wrong category.
  - "visibly_incomplete_or_garbled": the failure is visible on the
    surface -- output is empty, truncated, garbled, self-contradictory,
    hedged, or explicitly flags its own uncertainty/incompleteness --
    so a reader is warned that something is off.

Reasoning is logged for every call so verdicts can be audited by a
human later (same discipline as severance_detection.py).
"""

import os
import sys

EXP3_DIR = os.path.dirname(os.path.abspath(__file__))
SCRIPT_DIR = os.path.dirname(EXP3_DIR)
SERVER_DIR = os.path.dirname(os.path.dirname(SCRIPT_DIR))
if SERVER_DIR not in sys.path:
    sys.path.insert(0, SERVER_DIR)

from api_call import generate_response  # noqa: E402
from components.response_parsing import extract_json_from_response  # noqa: E402

WRONGNESS_CATEGORIES = ["fluent_but_wrong", "visibly_incomplete_or_garbled"]

# Distinctive substring used by self_test_exp3.py to recognize this prompt
# when stubbing generate_response.
WRONGNESS_PROMPT_MARKER = (
    "classify HOW the recovered output is wrong"
)


def build_wrongness_prompt(sentence, relation, recovered_claims, judge_reasoning):
    claims_block = "\n".join(f"- {c}" for c in recovered_claims) or "(no claims produced)"
    relation_type = relation.get("relation_type", "None")
    nucleus = relation.get("nucleus")
    satellite = relation.get("satellite")
    connective = relation.get("connective")
    return f"""
An automated system tried to re-express the sentence below as atomic
claims while preserving its {relation_type} discourse relation. An
independent judge has ALREADY determined that the output does NOT
preserve the relation -- do not re-litigate that verdict. Your task is
to {WRONGNESS_PROMPT_MARKER}, from the point of view of a downstream
reader who sees ONLY the recovered claims.

Original sentence: "{sentence}"
Relation type: {relation_type}
Nucleus (the governed/asserted clause): {nucleus!r}
Satellite (the governing/qualifying clause): {satellite!r}
Connective: {connective!r}
Judge's reasoning for why the relation is not preserved: {judge_reasoning!r}

Recovered claims (all the downstream reader sees):
{claims_block}

Classify the failure into exactly one category:

- "fluent_but_wrong": the recovered claims read as a complete, fluent,
  authoritative claim set -- no hedging, no caveat or flag, no visibly
  missing or garbled fragment -- while substantively misrepresenting
  the source relation (for example: asserting the nucleus
  unconditionally, attaching the condition/exception to the wrong
  sub-clause, or inverting the exception's scope). A reader would
  accept these claims at face value with no cue that anything is
  missing.

- "visibly_incomplete_or_garbled": the failure is visible on the
  surface -- the output is empty, truncated, garbled, ungrammatical,
  self-contradictory, hedged ("may", "unclear", "possibly" used AS a
  warning about the output itself), or explicitly flags uncertainty or
  incompleteness -- so a reader is warned that the claim set cannot be
  taken at face value.

Output strict JSON with exactly these keys:
  "category": "fluent_but_wrong" or "visibly_incomplete_or_garbled"
  "reasoning": one or two sentences explaining the classification,
    naming the specific surface evidence (or lack of it)

Return only valid JSON. Do not include Markdown code fences or
additional text.
"""


def classify_wrongness(sentence, relation, recovered_claims, judge_reasoning,
                       model=None):
    """Returns {"category": str or None, "reasoning": str}. `category` is
    None only on an outright call/parse failure or an out-of-vocabulary
    label (named in `reasoning`), never a silent default.
    """
    prompt = build_wrongness_prompt(sentence, relation, recovered_claims,
                                    judge_reasoning)
    response = generate_response(prompt, model=model)
    if not response or not hasattr(response, "content"):
        return {"category": None,
                "reasoning": "wrongness-classifier call failed: no model response."}
    data = extract_json_from_response(response.content)
    if not data:
        return {"category": None,
                "reasoning": "wrongness-classifier call failed: unparseable JSON response."}
    category = data.get("category")
    if category not in WRONGNESS_CATEGORIES:
        return {"category": None,
                "reasoning": f"wrongness-classifier returned out-of-vocabulary category {category!r}."}
    return {"category": category, "reasoning": data.get("reasoning", "")}
