"""Third Concession question-pattern attempt: single open-ended synthesis
question, scored by the UNMODIFIED score_source_grounded_answers.
score_case() pipeline (same claims-answer/source-answer/match-scoring
prompts already validated for Condition) -- no new scoring architecture,
no AND-gate.

Two patterns already failed to discriminate at scale:
  1. "does S prevent N?" -- flat 92.9%/94.1% at n=127 (theoretically
     always "No" for a genuine Concession relation -- construct flaw).
  2. Two-part A/B contrast-legibility -- looked clean at n=20 (60%/80%,
     kappa=0.565 human agreement) but collapsed to 58.8%/63.8% at
     n=103, Fisher p=0.67 -- NOT significant.

Given that history, this script does NOT stop at a clean-looking n=20
pilot. If the pilot shows a real gap, it immediately runs a second,
larger, non-overlapping confirmation sample (n=20-25/bucket) with its
own significance test before recommending full-scale authorization.

Usage:
    venv/bin/python server/scripts/discourse_severance/factoidwiki_track/pilot_concession_synthesis.py --pilot
    venv/bin/python server/scripts/discourse_severance/factoidwiki_track/pilot_concession_synthesis.py --confirm
"""
import json
import os
import random
import sys

from scipy.stats import fisher_exact

HERE = os.path.dirname(os.path.abspath(__file__))
PARENT = os.path.dirname(HERE)
SERVER_DIR = os.path.dirname(os.path.dirname(PARENT))
sys.path.insert(0, HERE)
sys.path.insert(0, SERVER_DIR)

from build_source_grounded_qa import construct_concession_synthesis_question  # noqa: E402
from score_source_grounded_answers import (  # noqa: E402
    build_answer_from_source_prompt, build_match_scoring_prompt, _call,
)
from pilot_concession_two_part import is_vague_satellite_excluded, build_two_part_answer_from_claims_prompt  # noqa: E402

# NOTE, deviation from the original instruction to reuse
# score_source_grounded_answers.score_case() unmodified: that function's
# claims-answering prompt has a "PREVENTS/CONTRADICTS -> default to No"
# branch that was found (this pilot's first run) to misfire on 7/20
# (35%) of these open-ended synthesis questions -- the model answered a
# non-yes/no "what is stated..." question with a bare "No"/"not stated",
# a category error, not a genuine content judgment. Reusing
# build_two_part_answer_from_claims_prompt instead -- NOT a new prompt
# written for this pattern, it's the already-built, already-validated
# (89.5%/94.7% human agreement in Step 3) unbiased answerer from the
# two-part pilot, which was written for exactly this problem the first
# time it appeared. answer-from-source and match-scoring are still the
# original, unmodified, Condition-validated prompts -- only the one
# component with a demonstrated incompatibility was swapped.


def score_case_generic(item):
    question = item["question_construction"]["question"]
    claims_data, claims_err = _call(build_two_part_answer_from_claims_prompt(question, item["propositions"]))
    source_data, source_err = _call(build_answer_from_source_prompt(question, item["paragraph"]))
    result = {**item, "question": question,
              "answer_from_claims": claims_data.get("answer") if claims_data else None,
              "answer_from_claims_reasoning": claims_data.get("reasoning") if claims_data else None,
              "answer_from_source": source_data.get("answer") if source_data else None,
              "answer_from_source_reasoning": source_data.get("reasoning") if source_data else None}
    if claims_err or source_err:
        result["correct"] = None
        result["match_reasoning"] = f"call failed: claims_err={claims_err}, source_err={source_err}"
        return result
    match_data, match_err = _call(build_match_scoring_prompt(
        question, result["answer_from_source"], result["answer_from_claims"]))
    if match_err:
        result["correct"] = None
        result["match_reasoning"] = match_err
    else:
        result["correct"] = bool(match_data.get("correct"))
        result["match_reasoning"] = match_data.get("reasoning")
    return result

CLEAN_SET_PATH = os.path.join(HERE, "results", "qa_questions_clean.json")
PILOT_OUT_PATH = os.path.join(HERE, "results", "concession_synthesis_pilot.json")
CONFIRM_OUT_PATH = os.path.join(HERE, "results", "concession_synthesis_confirm.json")


def eligible_concession(items):
    return [it for it in items if it["relation_type"] == "Concession" and not is_vague_satellite_excluded(it)]


def pick_stratified(items, n_per_bucket, seed, exclude_ids=frozenset()):
    concession = [it for it in eligible_concession(items) if it["case_id"] not in exclude_ids]
    severed = [it for it in concession if it["hand_verdict"] == "severed"]
    preserved = [it for it in concession if it["hand_verdict"] == "mislabeled_actually_correct"]
    rnd = random.Random(seed)
    sample = rnd.sample(severed, min(n_per_bucket, len(severed))) + \
        rnd.sample(preserved, min(n_per_bucket, len(preserved)))
    rnd.shuffle(sample)
    return sample


def run_batch(sample, out_path, verbose=True):
    results = []
    for i, item in enumerate(sample, 1):
        qc = construct_concession_synthesis_question(item)
        item_with_q = {**item, "question_construction": qc}
        if qc["error"] or not qc["question"]:
            msg = f"[{i}/{len(sample)}] {item['case_id']}: question construction failed -- {qc['error']}"
            (print(msg) if verbose else sys.stderr.write(msg + "\n"))
            results.append({**item_with_q, "correct": None})
            continue

        scored = score_case_generic(item_with_q)
        results.append(scored)

        if verbose:
            print(f"[{i}/{len(sample)}] {scored['case_id']} | old_verdict={scored['hand_verdict']} | "
                  f"correct={scored['correct']}")
            print(f"  Q: {scored['question']}")
            print(f"  claims={scored['answer_from_claims']!r} source={scored['answer_from_source']!r}")
            print(f"  reasoning: {scored['match_reasoning']}")
            print()
        else:
            sys.stderr.write(f"[{i}/{len(sample)}] {scored['case_id']} correct={scored['correct']}\n")
            sys.stderr.flush()

    json.dump(results, open(out_path, "w", encoding="utf-8"), indent=2)
    return results


def report(results, label):
    scored = [r for r in results if r["correct"] is not None]
    print("=" * 70)
    print(f"{label}: scored {len(scored)}/{len(results)}")
    sev = [r for r in scored if r["hand_verdict"] == "severed"]
    pre = [r for r in scored if r["hand_verdict"] == "mislabeled_actually_correct"]
    sev_c = sum(1 for r in sev if r["correct"])
    pre_c = sum(1 for r in pre if r["correct"])
    print(f"  old=severed                      n={len(sev):3} | correct={sev_c:3} ({sev_c/len(sev):.1%})" if sev else "  old=severed: n=0")
    print(f"  old=mislabeled_actually_correct  n={len(pre):3} | correct={pre_c:3} ({pre_c/len(pre):.1%})" if pre else "  old=mislabeled_actually_correct: n=0")
    if sev and pre:
        table = [[sev_c, len(sev) - sev_c], [pre_c, len(pre) - pre_c]]
        odds, p = fisher_exact(table)
        print(f"  Fisher's exact test: p={p:.4g}, odds ratio={odds:.3g}")
        return p
    return None


def main():
    items = json.load(open(CLEAN_SET_PATH, encoding="utf-8"))
    mode = sys.argv[1] if len(sys.argv) > 1 else "--pilot"

    if mode == "--pilot":
        sample = pick_stratified(items, n_per_bucket=10, seed=11)  # same seed as the two-part pilot
        print(f"PILOT sample: {len(sample)} ({sum(1 for it in sample if it['hand_verdict']=='severed')} severed, "
              f"{sum(1 for it in sample if it['hand_verdict']=='mislabeled_actually_correct')} preserved)\n")
        results = run_batch(sample, PILOT_OUT_PATH, verbose=True)
        report(results, "PILOT (n=20)")

    elif mode == "--confirm":
        pilot_results = json.load(open(PILOT_OUT_PATH, encoding="utf-8"))
        pilot_ids = {r["case_id"] for r in pilot_results}
        sample = pick_stratified(items, n_per_bucket=20, seed=97, exclude_ids=pilot_ids)
        print(f"CONFIRMATION sample: {len(sample)} ({sum(1 for it in sample if it['hand_verdict']=='severed')} severed, "
              f"{sum(1 for it in sample if it['hand_verdict']=='mislabeled_actually_correct')} preserved), "
              f"non-overlapping with the {len(pilot_ids)}-item pilot\n")
        results = run_batch(sample, CONFIRM_OUT_PATH, verbose=False)
        report(pilot_results, "PILOT (n=20, for reference)")
        report(results, "CONFIRMATION (fresh sample)")
    else:
        print(f"Unknown mode {mode!r}")


if __name__ == "__main__":
    main()
