"""Confidence-calibration addendum for Experiment 3 (requested as an
addition AFTER the original 4-arm run and the two-new-arm extension --
see ../RESULTS.md's dated addendum section for the full writeup).

For every case an automated-recovery arm (Disco-RAG, custom fallback,
or Contextual Retrieval) is scored a FAILURE by exp3_scoring.py's
wrongness classifier -- dangerous (fluent_but_wrong) OR detectable
(visibly_incomplete_or_garbled), i.e. any case whose primary judge
verdict is preserved=False -- this module runs ONE more structured LLM
call: does the arm's own output, exactly what a downstream reader would
see and nothing else, contain hedging/uncertainty language a careful
reader COULD have used as an independent signal not to trust it?

This is a calibration question, not a correctness question: it does
not re-litigate whether the output is right or wrong (already decided),
only whether the output's own surface language was honest about its
uncertainty.

INDEPENDENCE from server/components/risk_triage.py's detect_hedges is
by construction, not just by name: risk_triage.detect_hedges is a fixed
keyword wordlist match ("may", "might", "could", "can", "possibly",
...) run over ENGLISH CLAIM text as part of a different pipeline
(condition_4_flags). This module is a separate structured LLM judgment
call over the SAME surface text a reader sees, with no import of and no
delegation to risk_triage.py -- its verdict (`hedged`) is recorded
alongside, and explicitly compared against, condition_4_flags in the
calibration summary, never merged into it. A case can be hedged=True
under this classifier while risk_triage fired no flag at all, or vice
versa; both outcomes are real, reportable findings, not reconciled away.

Reasoning is logged for every call, same discipline as
exp3_scoring.classify_wrongness and severance_detection's judges.
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

# Distinctive substring for any future self-test stubbing generate_response
# (parallels WRONGNESS_PROMPT_MARKER / LLM_JUDGE_PROMPT_MARKER elsewhere in
# this experiment).
HEDGING_PROMPT_MARKER = (
    "does this claim set, AS WRITTEN, contain any hedging"
)


def build_hedging_prompt(claims):
    claims_block = "\n".join(f"- {c}" for c in claims) or "(no claims produced)"
    return f"""
A downstream reader sees ONLY the claims below -- no access to the
original source sentence, no access to any judge's verdict on whether
they are correct, complete, or reliable.

Claims:
{claims_block}

Question: {HEDGING_PROMPT_MARKER} (for example: "may", "might",
"possibly", "typically", "it is unclear whether", "in some cases", or
an explicit caveat about incompleteness or doubt) that a careful reader
COULD use as a signal that these claims might not be fully reliable or
complete -- regardless of whether the claims are, in fact, correct or
incorrect? Judge the claims exactly as written; do not assume hedging
is present just because the topic is regulatory or conditional in
nature -- confident, unqualified phrasing ("must", "shall", "is
restricted to", stated as flat fact) is NOT hedging.

Output strict JSON with exactly these keys:
  "hedged": true or false
  "evidence_phrases": a list of the exact hedging phrase(s) quoted
    verbatim from the claims above (empty list if hedged is false)
  "reasoning": one sentence explaining the judgment

Return only valid JSON. Do not include Markdown code fences or
additional text.
"""


def classify_hedging(claims, model=None):
    """Returns {"hedged": bool or None, "evidence_phrases": list,
    "reasoning": str}. `hedged` is None only on an outright call/parse
    failure or an out-of-vocabulary (non-boolean) field, named in
    `reasoning` -- never a silent default to False.
    """
    prompt = build_hedging_prompt(claims)
    response = generate_response(prompt, model=model)
    if not response or not hasattr(response, "content"):
        return {"hedged": None, "evidence_phrases": [],
                "reasoning": "hedging-classifier call failed: no model response."}
    data = extract_json_from_response(response.content)
    if not data:
        return {"hedged": None, "evidence_phrases": [],
                "reasoning": "hedging-classifier call failed: unparseable JSON response."}
    hedged = data.get("hedged")
    if not isinstance(hedged, bool):
        return {"hedged": None, "evidence_phrases": [],
                "reasoning": f"hedging-classifier returned non-boolean hedged field {hedged!r}."}
    evidence = data.get("evidence_phrases", [])
    if not isinstance(evidence, list):
        evidence = []
    return {"hedged": hedged, "evidence_phrases": evidence,
            "reasoning": data.get("reasoning", "")}
