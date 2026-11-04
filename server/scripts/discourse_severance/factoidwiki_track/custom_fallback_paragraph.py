"""Task 8 (Experiment 3), arm 3: this project's OWN custom fallback
rewriter, retargeted to paragraph-level propositions. Mirrors
../exp3_recovery_comparison/custom_fallback.py's design exactly (same
prompt structure, same design decisions), re-implemented self-contained
in this track per env_utils.py's established convention, renamed from
"claims" to "propositions" to match this track's/dataset's own vocabulary
(train.jsonl's `targets` field, this track's Propositionizer/
condition_b_atomizer.py nomenclature).

ATTRIBUTION (must accompany every arm-3 number): this arm is a
representative instance of the automated-correction design pattern --
take the already-elicited relation record (relation type, nucleus,
satellite, connective, saved by Task 6/7's relation-elicitation pipeline)
and auto-rewrite the Condition-A atomized propositions (Chen et al.'s real
Propositionizer output) to incorporate that relation, with no human
review. It is NOT a reproduction of Disco-RAG (whose released code runs,
adapted, in arm 2 -- see disco_rag_paragraph_adapter.py) and NOT a
reproduction of HCA (Fan et al. 2023), whose corpus and weights are
unreleased.

Design decision (documented, not hidden), identical in spirit to the
CFR-track arm: the rewriter is given ONLY the Condition-A propositions and
the saved relation-elicitation fields, NOT the original source paragraph.
This keeps the arm a pure downstream corrector operating on the
pipeline's saved artifacts -- exactly the resources an automated post-hoc
correction step would have if it ran inside the production pipeline after
atomization. (The nucleus/satellite fields are verbatim substrings of the
source paragraph, so the relation record itself carries the
relation-bearing material.)
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

DEFAULT_FALLBACK_MODEL = "gpt-4o-mini"

# Distinctive substring, parallel to
# ../exp3_recovery_comparison/custom_fallback.CUSTOM_FALLBACK_PROMPT_MARKER,
# in case a future self-test wants to stub/recognize this prompt.
CUSTOM_FALLBACK_PROMPT_MARKER = (
    "rewriting an already-atomized proposition set to restore a discourse relation"
)

CUSTOM_FALLBACK_STATEMENT = (
    "The custom fallback (arm 3) is this project's own automated rewriter: "
    "a representative instance of the automated-correction design pattern "
    "(auto-rewrite Condition-A's atomized propositions using the saved "
    "relation-elicitation record, no human review). It is not a "
    "reproduction of Disco-RAG or HCA."
)


def build_fallback_rewrite_prompt(propositions, relation):
    props_block = "\n".join(f"- {p}" for p in propositions) or "(no propositions produced)"
    relation_type = relation.get("relation_type", "None")
    nucleus = relation.get("nucleus")
    satellite = relation.get("satellite")
    connective = relation.get("connective")
    return f"""
You are {CUSTOM_FALLBACK_PROMPT_MARKER} that atomization severed.

An upstream step (Chen et al.'s trained Propositionizer) decomposed one
source paragraph into the atomized propositions below. A separate
elicitation step had already identified, in the source paragraph, a
{relation_type} discourse relation with these fields (verbatim substrings
of the source paragraph):

Relation type: {relation_type}
Nucleus (the governed/asserted clause): {nucleus!r}
Satellite (the governing/qualifying clause): {satellite!r}
Connective: {connective!r}

Atomized propositions (the current, possibly-severed decomposition):
{props_block}

Rewrite the proposition set so the {relation_type} relation is restored:
  1. Identify the proposition(s) whose content corresponds to the nucleus.
  2. Rewrite those proposition(s) so the satellite's qualification, joined
     by the connective, is explicitly attached to the nucleus content in
     the SAME proposition -- the nucleus must not read as asserted
     unconditionally/unexceptionally on its own.
  3. Leave propositions that are genuinely independent of this relation
     unchanged.
  4. If no proposition corresponds to the nucleus, add ONE proposition
     stating the nucleus-plus-connective-plus-satellite relation intact.
  5. Use only material from the propositions and the relation fields
     above. Do not invent new content, and do not drop assertions that
     were present in the propositions.

Output strict JSON with exactly these keys: "propositions" (a list of
strings, the full rewritten proposition set).
Return only valid JSON. Do not include Markdown code fences or
additional text.
"""


def run_fallback_rewrite(propositions, relation, model=None):
    """One LLM call: rewrite `propositions` to incorporate `relation`.

    Returns (rewritten_propositions_list, error). On any call/parse
    failure the list is None and `error` names the failure -- callers must
    record it loudly, never substitute the input propositions silently.
    """
    model = model or DEFAULT_FALLBACK_MODEL
    prompt = build_fallback_rewrite_prompt(propositions, relation)
    response = generate_response(prompt, model=model)
    if not response or not hasattr(response, "content"):
        return None, "no_response"
    data = extract_json_from_response(response.content)
    if not data:
        return None, "unparseable_json"
    rewritten = data.get("propositions")
    if not isinstance(rewritten, list) or not all(isinstance(p, str) for p in rewritten):
        return None, "invalid_propositions_shape"
    return rewritten, None
