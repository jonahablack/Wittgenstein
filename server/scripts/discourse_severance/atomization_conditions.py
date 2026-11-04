"""Condition A / Condition B atomization for the discourse-severance
experiments.

Condition A ("standard atomization"): calls the EXISTING production
propositional-extraction logic in server/components/response_parsing.py
as-is (process_single_segment, the single-segment path used by both the
parallel and sequential extractors). Nothing in response_parsing.py is
duplicated or modified here -- this is literally today's production
default, run unchanged.

Condition B ("explicit relation identification before atomizing"): a NEW
prompt, defined in this file only, that gives the model the sentence
PLUS its already-elicited relation type/nucleus/satellite/connective
(from relation_elicitation.py) and instructs it to atomize while
explicitly preserving or flagging that relation. Its output shape
({"claims": [...]}) is compatible with what severance_detection.py
expects, and with Condition A's claim list, so both conditions can be
scored identically.
"""

import os
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SERVER_DIR = os.path.dirname(os.path.dirname(SCRIPT_DIR))
if SERVER_DIR not in sys.path:
    sys.path.insert(0, SERVER_DIR)

from api_call import generate_response  # noqa: E402
from components.response_parsing import (  # noqa: E402
    extract_json_from_response,
    process_single_segment,
)

# Distinctive substring used by self_test.py to recognize this prompt when
# stubbing generate_response.
CONDITION_B_PROMPT_MARKER = (
    "this sentence has already been identified as containing a"
)


def run_condition_a(sentence, seg_idx=0):
    """Condition A: today's production propositional-extraction path,
    unmodified. `seg_idx` only matters if a caller wants a non-zero
    segment_index in the result; it is not otherwise used here.
    """
    result = process_single_segment((seg_idx, sentence))
    return result.get("claims", [])


def build_condition_b_prompt(sentence, relation):
    relation_type = relation.get("relation_type", "None")
    nucleus = relation.get("nucleus")
    satellite = relation.get("satellite")
    connective = relation.get("connective")
    return f"""
You are decomposing a single sentence of source text into atomic,
self-contained claims, for downstream formalization into logic -- the
same task as standard atomic/propositional decomposition -- EXCEPT that
{CONDITION_B_PROMPT_MARKER} {relation_type} discourse relation, and you
must explicitly preserve that relation rather than silently dropping it
during decomposition.

Relation type: {relation_type}
Nucleus (the governed/asserted clause): {nucleus!r}
Satellite (the governing/qualifying clause): {satellite!r}
Connective: {connective!r}

Decompose the sentence using the same base criteria as standard atomic
decomposition:
  1. ATOMIC: each claim expresses exactly one assertion.
  2. SELF-CONTAINED: resolve pronouns/references using only antecedents
     present in this sentence; never invent one.
  3. VERBATIM WHERE POSSIBLE: keep the source's own wording, deviating
     only as far as (1) and (2) require.

BUT, in addition, you must not let atomization sever the {relation_type}
relation identified above:
  - Do NOT split the nucleus and satellite into separate claims such
    that the nucleus ends up asserted unconditionally/unexceptionally
    when read on its own. Either:
      (a) keep the nucleus and satellite together in ONE claim that
          retains the connective, so the {relation_type} relation is
          explicit in that single claim's own text (e.g. keep "Y,
          unless X" together rather than splitting into a bare "Y"
          claim and a separate "X" claim), OR
      (b) if you produce separate claims, make sure at least one claim
          states the full nucleus-plus-connective-plus-satellite
          relation intact, not a bare nucleus claim with the condition/
          exception/concession dropped.
  - Any other assertions in the sentence that are genuinely independent
    of this relation may still be split into separate atomic claims as
    usual.
  - If relation_type is "None", just do standard atomic decomposition;
    there is no relation to preserve.

Sentence: "{sentence}"

Output strict JSON with exactly these keys: "claims" (a list of
strings, possibly empty).
Return only valid JSON. Do not include Markdown code fences or
additional text.
"""


def run_condition_b(sentence, relation, model=None):
    """Condition B: relation-aware atomization. Returns a list of claim
    strings (same shape as run_condition_a), or an empty list if the
    model call/parse failed.
    """
    prompt = build_condition_b_prompt(sentence, relation)
    response = generate_response(prompt, model=model)
    if not response or not hasattr(response, "content"):
        return []
    data = extract_json_from_response(response.content)
    if not data:
        return []
    claims = data.get("claims", [])
    return claims if isinstance(claims, list) else []
