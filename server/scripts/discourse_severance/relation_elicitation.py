"""Zero-shot LLM discourse-relation elicitation.

Given one sentence, asks the model whether it contains a Condition,
Exception, Concession, or Elaboration relation (or none of those), and
if so, to return the nucleus clause, satellite clause, and connective
word/phrase as structured JSON.

DESIGN-PHILOSOPHY NOTE (read before reusing this pattern elsewhere):
this classifier is deliberately narrow and single-purpose -- five
categories, one LLM call, no tree structure -- because it exists ONLY to
support the research measurement in run_experiments.py (can the model
identify these relations at all, as opposed to whether it preserves them
when atomizing). This is NOT a general RST parser and should not be
extended into one.

This is also, deliberately, a DIFFERENT design philosophy from
server/components/risk_triage.py, which is rule-based (regex/wordlist)
BY DESIGN because it ships inside the production formalization pipeline:
deterministic, auditable without an API call, no per-call latency/cost,
no model-drift risk between runs. An LLM-based classifier would be the
wrong choice for risk_triage.py's job. It is the right choice here
because the question this module exists to answer -- "can an LLM
identify this discourse relation when explicitly asked" -- is itself
about LLM behavior, so probing it with an LLM is the correct instrument,
not a shortcut. A future reader should not read this module's approach
as an implicit critique of risk_triage.py's approach, or vice versa;
they are solving different problems.
"""

import os
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SERVER_DIR = os.path.dirname(os.path.dirname(SCRIPT_DIR))
if SERVER_DIR not in sys.path:
    sys.path.insert(0, SERVER_DIR)

from api_call import generate_response  # noqa: E402
from components.response_parsing import extract_json_from_response  # noqa: E402

RELATION_TYPES = ["Condition", "Exception", "Concession", "Elaboration", "None"]

# Distinctive substring used by self_test.py to recognize this prompt when
# stubbing generate_response -- kept as a named constant so the prompt
# text and the self-test dispatcher can't silently drift apart.
PROMPT_MARKER = "You are a discourse-relation annotator."


def build_relation_elicitation_prompt(sentence):
    return f"""{PROMPT_MARKER} Read ONE sentence from a regulatory
document and decide whether it contains one of the following relations
between two of its clauses. These are narrow, RST-derived categories --
use exactly these definitions, not a broader relation inventory:

- Condition: one clause (the satellite) states a circumstance under
  which the other clause (the nucleus) holds ("if X, then Y"; "when X,
  Y"; "in the event that X, Y").
- Exception: one clause (the satellite) carves out a case where the
  nucleus does NOT hold, or is exempted from applying ("Y, unless X";
  "Y, except when X"; "Y, except that X"; "Y, provided that X" when
  "provided that" is functioning as an exemption/exception condition).
- Concession: the satellite is acknowledged as true, or as apparently in
  tension with the nucleus, but the nucleus holds anyway ("although X,
  Y"; "even though X, Y"; "despite X, Y").
- Elaboration: the satellite adds independently-true supporting detail,
  example, restatement, or list-expansion about the nucleus, WITHOUT
  governing whether the nucleus holds -- the nucleus would still be true
  even if the satellite were removed or turned out false.
- None: the sentence does not clearly instantiate any of the above (a
  single unconditioned assertion, a bare list, a definition with no
  clause-governing structure, purely mechanical/citation text).

If more than one relation could arguably apply, pick the SINGLE relation
that most governs the sentence's overall truth conditions.

Sentence: "{sentence}"

Output strict JSON with exactly these keys:
  "relation_type": one of "Condition", "Exception", "Concession",
    "Elaboration", "None"
  "nucleus": the governed/asserted clause, as a VERBATIM substring of
    the sentence, or null if relation_type is "None"
  "satellite": the governing/qualifying clause, as a VERBATIM substring
    of the sentence, or null if relation_type is "None"
  "connective": the connective word or phrase that signals the relation,
    VERBATIM (e.g. "unless", "provided that", "although"), or null if
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
    }
    if error:
        result["_error"] = error
    return result


def elicit_relation(sentence, model=None):
    """One LLM call: classify `sentence` into one of RELATION_TYPES and
    extract nucleus/satellite/connective. Returns a dict; on any failure
    (no response, unparseable JSON, invalid relation_type) returns
    _empty_relation() with an "_error" key set, rather than raising --
    callers doing a large batch need to keep going past occasional
    failures, same as response_parsing.py's _empty_result() pattern.
    """
    prompt = build_relation_elicitation_prompt(sentence)
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
    }
