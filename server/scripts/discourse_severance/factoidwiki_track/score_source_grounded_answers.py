"""Step 2 of the task-grounded correctness reframe: for each of Step 1's
127 clean questions, generate an answer from the atomized/repaired
claims ALONE (no source access), generate a separate ground-truth answer
from the ORIGINAL SOURCE SENTENCE alone, then score whether the two
answers match.

EXPLICIT FLAG, per the task that required it: all three steps below
(claims-answer, source-answer, match-scoring) are LLM calls. This is
disclosed prominently because it matters methodologically -- the
reframe's theoretical appeal is that "is this specific factual answer
correct" is a narrower, more constrained judgment than "is this
relationship preserved," but chaining FOUR LLM calls per case (question
construction in Step 1, two answer generations, one match score) means
four independent places for interpretive drift to enter, not one. This
step does NOT by itself demonstrate the reframe is more stable -- it
only builds the material Step 3's human inter-rater check evaluates.
Treat everything this script outputs as provisional, system-side
material pending that check, not as validated ground truth.

Usage:
    venv/bin/python server/scripts/discourse_severance/factoidwiki_track/score_source_grounded_answers.py --sample
    venv/bin/python server/scripts/discourse_severance/factoidwiki_track/score_source_grounded_answers.py --full
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PARENT = os.path.dirname(HERE)
SERVER_DIR = os.path.dirname(os.path.dirname(PARENT))
sys.path.insert(0, HERE)
sys.path.insert(0, SERVER_DIR)

from api_call import generate_response  # noqa: E402
from components.response_parsing import extract_json_from_response  # noqa: E402

DEFAULT_MODEL = None  # gpt-4o-mini default, matching every other call in this project

CLEAN_SET_PATH = os.path.join(HERE, "results", "qa_questions_clean.json")
OUT_PATH = os.path.join(HERE, "results", "qa_answers_scored.json")


def build_answer_from_claims_prompt(question, propositions):
    """Round-2 revision: the v1 wording ("if the claims do not provide
    enough information to answer confidently, say so explicitly rather
    than guessing") was tested against a 10-case, two-rater blind human
    comparison and found miscalibrated -- both human raters, reading the
    IDENTICAL claims with no other instruction than "answer naturally,"
    matched the source-grounded ground truth on 9/10; the v1 prompt's
    claims-answerer matched on 1/10, defaulting to "not stated" on cases
    the humans confidently and correctly resolved.

    Correction (per direct instruction, sharper than my first-pass
    "ordinary inference" framing): for a "Does S prevent N?" question,
    "No" is the correct DEFAULT answer whenever the claims don't
    obviously support inferring that S actually did block/stop/
    invalidate N -- this isn't a positive inference the reader has to
    construct from two co-present facts, it's a burden-of-proof
    asymmetry built into the question itself (a genuine Concession
    relation's satellite essentially never defeats the nucleus, so
    absence of evidence THAT it did is itself sufficient grounds for
    "No"). "Not stated" is reserved for cases where the claims don't
    even establish what the question's terms refer to at all, not for
    "the claims don't explicitly rule out prevention" -- those simply
    default to No.
    """
    props_block = "\n".join(f"- {p}" for p in propositions) or "(no propositions produced)"
    return f"""
You have ONLY the following list of claims. You do NOT have access to any
original source text, and must not use outside knowledge.

Claims:
{props_block}

Question: {question}

If this question asks whether one circumstance PREVENTS/CONTRADICTS/
RULES OUT/STOPS another: "No" is the correct DEFAULT answer whenever the
claims do not clearly show that the first circumstance actually blocked,
stopped, or invalidated the second. You do not need a claim that
explicitly states "X did not prevent Y" -- if the claims establish both
circumstances as true/asserted without any indication that one defeated
the other, that IS sufficient grounds for "No." Only answer "not stated"
if the claims don't even establish what the question is asking about at
all (the relevant people, events, or circumstances are simply absent) --
not merely because no claim explicitly addresses the prevention
relationship itself.

For any other kind of question, answer using ONLY what these claims
state, drawing ordinary, direct inferences a careful reader would make.
Do not invent facts, names, dates, or details the claims never state in
any form.

Output strict JSON with exactly these keys:
  "answer": your short answer (a word/phrase, or "not stated" only if
    the claims never establish the relevant people/events/circumstances
    at all)
  "reasoning": one sentence citing which claim(s) support the answer

Return only valid JSON. Do not include Markdown code fences or additional
text.
"""


def build_answer_from_source_prompt(question, source_sentence):
    return f"""
You have ONLY the following original source sentence. Answer the
question using ONLY what this sentence states -- do not use outside
knowledge.

Source sentence: "{source_sentence}"

Question: {question}

Output strict JSON with exactly these keys:
  "answer": your short answer (a word/phrase)
  "reasoning": one sentence citing the specific part of the source that
    supports the answer

Return only valid JSON. Do not include Markdown code fences or additional
text.
"""


def build_match_scoring_prompt(question, source_answer, claims_answer):
    return f"""
Question: {question}

Ground-truth answer (derived from the ORIGINAL source text): {source_answer!r}

Candidate answer (derived ONLY from atomized/repaired claims, with no
access to the original source): {claims_answer!r}

Does the candidate answer convey the SAME factual content as the
ground-truth answer, for this specific question? Wording may differ;
score on factual agreement, not phrasing. If the candidate answer is
"not stated" / "insufficient information" while the ground truth gives a
definite answer, that counts as INCORRECT (the claims failed to convey
what the source actually states).

Output strict JSON with exactly these keys:
  "correct": true or false
  "reasoning": one sentence explaining the comparison

Return only valid JSON. Do not include Markdown code fences or additional
text.
"""


def _call(prompt, model=None):
    model = model or DEFAULT_MODEL
    response = generate_response(prompt, model=model)
    if not response or not hasattr(response, "content"):
        return None, "call failed: no response"
    data = extract_json_from_response(response.content)
    if not data:
        return None, "call failed: unparseable JSON"
    return data, None


def score_case(item, model=None):
    question = item["question_construction"]["question"]
    claims_data, claims_err = _call(build_answer_from_claims_prompt(question, item["propositions"]), model)
    source_data, source_err = _call(build_answer_from_source_prompt(question, item["paragraph"]), model)

    result = {
        "case_id": item["case_id"],
        "relation_type": item["relation_type"],
        "hand_verdict": item["hand_verdict"],  # the OLD relation-preservation verdict -- kept for comparison only
        "question": question,
        "answer_from_claims": claims_data.get("answer") if claims_data else None,
        "answer_from_claims_reasoning": claims_data.get("reasoning") if claims_data else None,
        "answer_from_claims_error": claims_err,
        "answer_from_source": source_data.get("answer") if source_data else None,
        "answer_from_source_reasoning": source_data.get("reasoning") if source_data else None,
        "answer_from_source_error": source_err,
    }

    if claims_err or source_err:
        result["correct"] = None
        result["match_reasoning"] = "skipped: one or both answer-generation calls failed"
        return result

    match_data, match_err = _call(
        build_match_scoring_prompt(question, result["answer_from_source"], result["answer_from_claims"]), model
    )
    if match_err:
        result["correct"] = None
        result["match_reasoning"] = match_err
    else:
        result["correct"] = bool(match_data.get("correct"))
        result["match_reasoning"] = match_data.get("reasoning")
    return result


def main():
    items = json.load(open(CLEAN_SET_PATH, encoding="utf-8"))
    mode = sys.argv[1] if len(sys.argv) > 1 else "--sample"

    if mode == "--sample":
        import random
        random.seed(7)
        sample = random.sample(items, 10)
        for i, item in enumerate(sample, 1):
            r = score_case(item)
            print(f"[{i}/{len(sample)}] {r['case_id']} | {r['relation_type']} | old verdict={r['hand_verdict']}")
            print(f"  Q: {r['question']}")
            print(f"  answer from SOURCE:  {r['answer_from_source']!r}  ({r['answer_from_source_reasoning']})")
            print(f"  answer from CLAIMS:  {r['answer_from_claims']!r}  ({r['answer_from_claims_reasoning']})")
            print(f"  CORRECT: {r['correct']}  -- {r['match_reasoning']}")
            print()
    elif mode == "--full":
        results = []
        for i, item in enumerate(items, 1):
            r = score_case(item)
            results.append(r)
            sys.stderr.write(f"[{i}/{len(items)}] {r['case_id']} correct={r['correct']}\n")
            sys.stderr.flush()
        json.dump(results, open(OUT_PATH, "w", encoding="utf-8"), indent=2)
        n_scored = sum(1 for r in results if r["correct"] is not None)
        n_correct = sum(1 for r in results if r["correct"] is True)
        print(f"\n{n_correct}/{n_scored} scored correct ({n_scored}/{len(results)} scored, "
              f"{len(results) - n_scored} call failures)")
        print(f"Saved to {OUT_PATH}")
    else:
        print(f"Unknown mode {mode!r}")


if __name__ == "__main__":
    main()
