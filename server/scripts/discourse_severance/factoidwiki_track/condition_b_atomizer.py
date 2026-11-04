"""Task 2 (full-scale run): "Condition B" atomization for FactoidWiki
paragraphs -- elicitation-then-atomize, mirroring
../atomization_conditions.py's Condition B design CONCEPTUALLY (same
core idea: give the atomizer the already-elicited relation and instruct
it to preserve/flag that relation rather than silently dropping it) but
NOT imported from there, per this track's established self-contained-
scripts convention (see env_utils.py's docstring). A fresh implementation
is needed anyway because the input shape differs in a way that is not a
cosmetic change: ../atomization_conditions.py's Condition B decomposes a
single CFR SENTENCE; this decomposes a whole multi-sentence Wikipedia
PARAGRAPH (the same `content` field relation_classifier.classify_paragraph
was given in Stage 1), so the prompt's decomposition guidance, examples,
and framing are paragraph-appropriate (e.g. "self-contained" here must
call out pronoun/reference resolution ACROSS sentences within the
paragraph, which a single-sentence prompt never needs to mention).

"Condition A" for this track is NOT generated here at all -- it is Chen et
al.'s own already-released Propositionizer output, the `targets` field
already sitting in data_cache/train.jsonl (see download_data.py and
README.md's dataset-verification note). Condition A requires no LLM call
and no code in this module; see confirmed_pool.py / run_experiment_1_2.py
for where it's looked up.

MODEL CHOICE: gpt-4o-mini (generate_response's own default, same as
../atomization_conditions.py's run_condition_b and this track's own Stage
1 classifier) -- per the task brief's explicit instruction ("prompt
gpt-4o-mini to atomize"), not a stronger/differently-configured model.
This means Condition A (Propositionizer, a small fine-tuned FLAN-T5-large
checkpoint) and Condition B (gpt-4o-mini, zero-shot prompted) differ by
MODEL as well as by elicitation-awareness -- a real confound the task
brief explicitly anticipates and asks to be reported qualitatively
alongside the severance numbers, not resolved by trying to reproduce a
"relation-aware Propositionizer" (out of scope; Chen et al.'s checkpoint
is used read-only, per the task brief).

INPUT SHAPE DECISION: Condition B is given the BARE paragraph `content`
string only -- the same view of the text Stage 1/2's relation elicitation
saw (relation_classifier.classify_paragraph(record["content"], ...)), NOT
the full "Title: X. Section: Y. Content: Z." string the real Propositionizer
was trained on and given for Condition A. This is a second, separate
confound from the model-choice one above (Condition A saw title+section
context; Condition B does not) -- deliberately chosen so that, WITHIN
Condition B, the relation was elicited from and atomized from the
identical text, rather than introducing a third variable (elicited from
bare content, atomized from content-plus-metadata) inside a single
condition. Both confounds are surfaced explicitly in this track's
results write-up rather than papered over.
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

DEFAULT_CONDITION_B_MODEL = "gpt-4o-mini"

# Distinctive substring, parallel to atomization_conditions.CONDITION_B_PROMPT_MARKER,
# in case a future self-test wants to stub/recognize this prompt.
CONDITION_B_PROMPT_MARKER = (
    "this paragraph has already been identified as containing a"
)


def build_condition_b_prompt(paragraph, relation):
    relation_type = relation.get("relation_type", "None")
    nucleus = relation.get("nucleus")
    satellite = relation.get("satellite")
    connective = relation.get("connective")
    return f"""
You are decomposing a PARAGRAPH of source text (it may contain several
sentences, not just one) into atomic, self-contained propositions -- the
same task as standard propositional/atomic decomposition (as used to
build FactoidWiki-style proposition corpora) -- EXCEPT that
{CONDITION_B_PROMPT_MARKER} {relation_type} discourse relation, and you
must explicitly preserve that relation rather than silently dropping it
during decomposition.

Relation type: {relation_type}
Nucleus (the governed/asserted clause): {nucleus!r}
Satellite (the governing/qualifying clause): {satellite!r}
Connective: {connective!r}

Decompose the paragraph using the same base criteria as standard atomic
decomposition:
  1. ATOMIC: each proposition expresses exactly one assertion.
  2. SELF-CONTAINED: resolve pronouns/references (e.g. "it", "he", "the
     company", "the album") using only antecedents present elsewhere IN
     THIS PARAGRAPH; never invent one and never leave an unresolved
     pronoun dangling in a proposition that is split away from its
     antecedent sentence.
  3. VERBATIM WHERE POSSIBLE: keep the source's own wording, deviating
     only as far as (1) and (2) require.

BUT, in addition, you must not let atomization sever the {relation_type}
relation identified above:
  - Do NOT split the nucleus and satellite into separate propositions such
    that the nucleus ends up asserted unconditionally/unexceptionally when
    read on its own, with no trace of the {relation_type} left anywhere.
    Either:
      (a) keep the nucleus and satellite together in ONE proposition that
          retains the connective, so the {relation_type} relation is
          explicit in that single proposition's own text (e.g. keep "Y,
          although X" together rather than splitting into a bare "Y"
          proposition and a separate "X" proposition), OR
      (b) if you produce separate propositions, make sure at least one
          proposition states the full nucleus-plus-connective-plus-
          satellite relation intact, not a bare nucleus proposition with
          the condition/concession dropped.
  - Any OTHER assertions in the paragraph that are genuinely independent
    of this relation should still be split into separate atomic
    propositions as usual -- do not under-split the rest of the paragraph
    just because one relation needs careful handling; a paragraph may
    easily need 3-10+ propositions total, of which only the ones
    involving the nucleus/satellite need the special handling above.
  - If relation_type is "None", just do standard atomic decomposition;
    there is no relation to preserve.

Paragraph: "{paragraph}"

Output strict JSON with exactly these keys: "propositions" (a list of
strings, possibly empty).
Return only valid JSON. Do not include Markdown code fences or additional
text.
"""


def run_condition_b(paragraph, relation, model=None):
    """Condition B: relation-aware paragraph atomization. Returns a list of
    proposition strings (never raises on a call/parse failure -- returns an
    empty list, matching ../atomization_conditions.py's run_condition_b
    fail-safe behavior, since a severance judge scoring an empty list is
    itself informative -- a real "nothing usable was produced" outcome --
    rather than a value that should stop the batch).
    """
    model = model or DEFAULT_CONDITION_B_MODEL
    prompt = build_condition_b_prompt(paragraph, relation)
    response = generate_response(prompt, model=model)
    if not response or not hasattr(response, "content"):
        return {"propositions": [], "_error": "no_response"}
    data = extract_json_from_response(response.content)
    if not data:
        return {"propositions": [], "_error": "unparseable_json"}
    propositions = data.get("propositions", [])
    if not isinstance(propositions, list):
        return {"propositions": [], "_error": f"non_list_propositions:{type(propositions).__name__}"}
    return {"propositions": [str(p) for p in propositions], "_error": None}
