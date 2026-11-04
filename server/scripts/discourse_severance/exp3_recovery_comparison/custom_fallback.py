"""Arm-2 automated recovery: this project's OWN custom fallback rewriter.

ATTRIBUTION (must accompany every arm-2 number): this arm is a
representative instance of the automated-correction design pattern --
take the already-elicited relation record (relation type, nucleus,
satellite, connective, saved per case by Experiment 1's
relation_elicitation.py) and auto-rewrite the Condition-A atomized
claims to incorporate that relation, with no human review. It is NOT a
reproduction of Disco-RAG (whose released code runs, adapted, in arm 1
-- see disco_rag_adapter.py) and NOT a reproduction of HCA (Fan et al.
2023), whose corpus and weights are unreleased.

Design decision (documented, not hidden): the rewriter is given ONLY
the Condition-A claims and the saved relation-elicitation fields, NOT
the original source sentence. This keeps the arm a pure downstream
corrector operating on the pipeline's saved artifacts -- exactly the
resources an automated post-hoc correction step would have if it ran
inside the production pipeline after atomization. (The nucleus/satellite
fields are verbatim substrings of the source, so the relation record
itself carries the relation-bearing material.)
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

# Distinctive substring used by self_test_exp3.py to recognize this prompt
# when stubbing generate_response.
CUSTOM_FALLBACK_PROMPT_MARKER = (
    "rewriting an already-atomized claim set to restore a discourse relation"
)

CUSTOM_FALLBACK_STATEMENT = (
    "The custom fallback (arm 2) is this project's own automated rewriter: "
    "a representative instance of the automated-correction design pattern "
    "(auto-rewrite atomized claims using the saved relation-elicitation "
    "record, no human review). It is not a reproduction of Disco-RAG or "
    "HCA."
)


def build_fallback_rewrite_prompt(claims, relation):
    claims_block = "\n".join(f"- {c}" for c in claims) or "(no claims produced)"
    relation_type = relation.get("relation_type", "None")
    nucleus = relation.get("nucleus")
    satellite = relation.get("satellite")
    connective = relation.get("connective")
    return f"""
You are {CUSTOM_FALLBACK_PROMPT_MARKER} that atomization severed.

An upstream step decomposed one source sentence into the atomized
claims below. A separate elicitation step had already identified, in
the source sentence, a {relation_type} discourse relation with these
fields (verbatim substrings of the source sentence):

Relation type: {relation_type}
Nucleus (the governed/asserted clause): {nucleus!r}
Satellite (the governing/qualifying clause): {satellite!r}
Connective: {connective!r}

Atomized claims (the current, possibly-severed decomposition):
{claims_block}

Rewrite the claim set so the {relation_type} relation is restored:
  1. Identify the claim(s) whose content corresponds to the nucleus.
  2. Rewrite those claim(s) so the satellite's qualification, joined by
     the connective, is explicitly attached to the nucleus content in
     the SAME claim -- the nucleus must not read as asserted
     unconditionally/unexceptionally on its own.
  3. Leave claims that are genuinely independent of this relation
     unchanged.
  4. If no claim corresponds to the nucleus, add ONE claim stating the
     nucleus-plus-connective-plus-satellite relation intact.
  5. Use only material from the claims and the relation fields above.
     Do not invent new content, and do not drop assertions that were
     present in the claims.

Output strict JSON with exactly these keys: "claims" (a list of
strings, the full rewritten claim set).
Return only valid JSON. Do not include Markdown code fences or
additional text.
"""


def run_fallback_rewrite(claims, relation, model=None):
    """One LLM call: rewrite `claims` to incorporate `relation`.

    Returns (rewritten_claims_list, error). On any call/parse failure the
    list is None and `error` names the failure -- callers must record it
    loudly, never substitute the input claims silently.
    """
    prompt = build_fallback_rewrite_prompt(claims, relation)
    response = generate_response(prompt, model=model)
    if not response or not hasattr(response, "content"):
        return None, "no_response"
    data = extract_json_from_response(response.content)
    if not data:
        return None, "unparseable_json"
    rewritten = data.get("claims")
    if not isinstance(rewritten, list) or not all(isinstance(c, str) for c in rewritten):
        return None, "invalid_claims_shape"
    return rewritten, None
