"""Pilot of the two-part Concession pattern (CONCESSION_PATTERN_PART_A/B
in build_source_grounded_qa.py) that replaced the confirmed-degenerate
"prevent" pattern (flat 92.9%/94.1% correct across old-severed/old-
preserved buckets -- no discriminative power, because "does S prevent
N?" is theoretically "No" for every genuine Concession relation).

Self-contained rather than routed through process_items/score_case,
since those were built around a single question per case and the old
pattern's groundedness/polarity checks; this pilot needs its own
two-question flow before any of that machinery gets adapted for it.

Preserved = BOTH parts answered correctly from claims (matching the
source-grounded answer for that part). Not ANDed at the answer-string
level -- each part is independently answered from claims, independently
answered from source, independently scored for a match, and only THEN
ANDed into a final preserved/severed call.

Usage:
    venv/bin/python server/scripts/discourse_severance/factoidwiki_track/pilot_concession_two_part.py
"""
import json
import os
import random
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PARENT = os.path.dirname(HERE)
SERVER_DIR = os.path.dirname(os.path.dirname(PARENT))
sys.path.insert(0, HERE)
sys.path.insert(0, SERVER_DIR)

from build_source_grounded_qa import construct_concession_two_part_questions  # noqa: E402
from score_source_grounded_answers import build_answer_from_source_prompt, _call  # noqa: E402

CLEAN_SET_PATH = os.path.join(HERE, "results", "qa_questions_clean.json")
OUT_PATH = os.path.join(HERE, "results", "concession_two_part_pilot.json")
FULL_OUT_PATH = os.path.join(HERE, "results", "concession_two_part_full.json")

# Vague-satellite exclusions, round after item 5 (exp3-4998, "Despite
# great challenges") was confirmed non-singleton by a full-pool spot
# check: 3 more distinct relations share the same generic-stock-phrase
# problem (no specific referent at all, independent of question-
# construction quality) -- see the check that authorized this list.
# Matched by pool_index (exp3 cases share relation fields across arms).
VAGUE_SATELLITE_POOL_INDICES = {
    4998,  # "Despite great challenges" -- the original finding
    4242,  # "Even so" -- zero content words
    3454,  # "Although it had supporters" -- no specifics
    4580,  # "Though often oppressive" -- generic descriptor, no referent
}


def is_vague_satellite_excluded(item):
    if item.get("source_set") != "exp3_125":
        return False
    pool_index = int(item["case_id"].split("-")[1])
    return pool_index in VAGUE_SATELLITE_POOL_INDICES


# Dedicated, UNBIASED claims-answering prompt for the two-part pattern --
# does NOT reuse score_source_grounded_answers.build_answer_from_claims_
# prompt, whose "default to No absent clear evidence" branch is keyed to
# PREVENT/CONTRADICT/RULE OUT/STOP language and was found (this pilot's
# first run) to fire inappropriately on Part A's "presented as...
# contrasts with" phrasing -- it answered "No" even on a claim
# containing an explicit "however" marker. Part B's phrasing never
# touched that keyword space and worked correctly on the same claims,
# confirming this is prompt contamination, not a problem with the
# two-part design itself. This version has no default-to-No bias in
# either direction -- plain "answer from what's stated" only.
def build_two_part_answer_from_claims_prompt(question, propositions):
    props_block = "\n".join(f"- {p}" for p in propositions) or "(no propositions produced)"
    return f"""
You have ONLY the following list of claims. You do NOT have access to any
original source text, and must not use outside knowledge.

Claims:
{props_block}

Question: {question}

Answer using ONLY what these claims state, drawing ordinary, direct
inferences a careful reader would make -- including recognizing an
explicit contrastive/concessive marker (e.g. "however," "but," "despite,"
"although") if one is present in the claims themselves. Do not invent
facts, names, dates, or details the claims never state in any form. Do
not default to "no" or "not stated" out of caution -- answer what the
claims actually support, whether that is yes or no.

Output strict JSON with exactly these keys:
  "answer": your short answer (a word/phrase, or "not stated" only if
    the claims never establish the relevant content at all)
  "reasoning": one sentence citing which claim(s) support the answer

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
score on factual agreement, not phrasing.

Output strict JSON with exactly these keys:
  "correct": true or false
  "reasoning": one sentence explaining the comparison

Return only valid JSON. Do not include Markdown code fences or additional
text.
"""


def pick_stratified_sample(items, n_per_bucket=10, seed=11):
    concession = [it for it in items if it["relation_type"] == "Concession"]
    severed = [it for it in concession if it["hand_verdict"] == "severed"]
    preserved = [it for it in concession if it["hand_verdict"] == "mislabeled_actually_correct"]
    rnd = random.Random(seed)
    sample = rnd.sample(severed, min(n_per_bucket, len(severed))) + \
        rnd.sample(preserved, min(n_per_bucket, len(preserved)))
    rnd.shuffle(sample)
    return sample


def score_part(question, propositions, paragraph):
    claims_data, claims_err = _call(build_two_part_answer_from_claims_prompt(question, propositions))
    source_data, source_err = _call(build_answer_from_source_prompt(question, paragraph))
    if claims_err or source_err:
        return {"answer_from_claims": None, "answer_from_source": None, "correct": None,
                "match_reasoning": f"call failed: claims_err={claims_err}, source_err={source_err}"}
    claims_ans = claims_data.get("answer")
    source_ans = source_data.get("answer")
    match_data, match_err = _call(build_match_scoring_prompt(question, source_ans, claims_ans))
    if match_err:
        return {"answer_from_claims": claims_ans, "answer_from_source": source_ans,
                "correct": None, "match_reasoning": match_err}
    return {
        "answer_from_claims": claims_ans, "answer_from_source": source_ans,
        "correct": bool(match_data.get("correct")), "match_reasoning": match_data.get("reasoning"),
    }


def run_batch(sample, out_path, verbose=True):
    results = []
    for i, item in enumerate(sample, 1):
        qs = construct_concession_two_part_questions(item)
        if qs["error"] or not qs["question_a"] or not qs["question_b"]:
            msg = f"[{i}/{len(sample)}] {item['case_id']}: question construction failed -- {qs['error']}"
            (print if verbose else sys.stderr.write)(msg + ("\n" if not verbose else ""))
            results.append({**item, "question_construction": qs, "part_a": None, "part_b": None, "preserved": None})
            continue

        part_a = score_part(qs["question_a"], item["propositions"], item["paragraph"])
        part_b = score_part(qs["question_b"], item["propositions"], item["paragraph"])
        preserved = (part_a["correct"] is True) and (part_b["correct"] is True)
        both_scored = part_a["correct"] is not None and part_b["correct"] is not None

        rec = {**item, "question_construction": qs, "part_a": part_a, "part_b": part_b,
               "preserved": preserved if both_scored else None}
        results.append(rec)

        if verbose:
            print(f"[{i}/{len(sample)}] {item['case_id']} | old_verdict={item['hand_verdict']} | "
                  f"new_preserved={rec['preserved']}")
            print(f"  Part A: {qs['question_a']}")
            print(f"    claims={part_a['answer_from_claims']!r} source={part_a['answer_from_source']!r} "
                  f"correct={part_a['correct']}")
            print(f"    reasoning: {part_a['match_reasoning']}")
            print(f"  Part B: {qs['question_b']}")
            print(f"    claims={part_b['answer_from_claims']!r} source={part_b['answer_from_source']!r} "
                  f"correct={part_b['correct']}")
            print(f"    reasoning: {part_b['match_reasoning']}")
            print()
        else:
            sys.stderr.write(f"[{i}/{len(sample)}] {item['case_id']} preserved={rec['preserved']}\n")
            sys.stderr.flush()

    json.dump(results, open(out_path, "w", encoding="utf-8"), indent=2)
    return results


def report_summary(results, out_path):
    scored = [r for r in results if r["preserved"] is not None]
    print("=" * 70)
    print(f"Scored: {len(scored)}/{len(results)}")
    for bucket in ("severed", "mislabeled_actually_correct"):
        sub = [r for r in scored if r["hand_verdict"] == bucket]
        n_preserved = sum(1 for r in sub if r["preserved"])
        print(f"  old={bucket:28} n={len(sub):2} | new-preserved={n_preserved} "
              f"({n_preserved/len(sub):.1%} if n>0)" if sub else f"  old={bucket}: n=0")
    print(f"\nSaved to {out_path}")


def main():
    items = json.load(open(CLEAN_SET_PATH, encoding="utf-8"))
    mode = sys.argv[1] if len(sys.argv) > 1 else "--sample"

    if mode == "--sample":
        sample = pick_stratified_sample(items, n_per_bucket=10)
        print(f"Pilot sample: {len(sample)} Concession cases "
              f"({sum(1 for it in sample if it['hand_verdict']=='severed')} old-severed, "
              f"{sum(1 for it in sample if it['hand_verdict']=='mislabeled_actually_correct')} old-preserved)\n")
        results = run_batch(sample, OUT_PATH, verbose=True)
        report_summary(results, OUT_PATH)

    elif mode == "--full":
        piloted = json.load(open(OUT_PATH, encoding="utf-8"))
        piloted_ids = {r["case_id"] for r in piloted if r["case_id"] != "exp3-4998-arm_4_contextual_retrieval"}
        # item 5 (exp3-4998) is excluded per the vague-satellite finding,
        # so it is NOT carried forward into the full result set.

        concession = [it for it in items if it["relation_type"] == "Concession"]
        vague_excluded = [it for it in concession if is_vague_satellite_excluded(it)]
        remaining = [it for it in concession
                     if it["case_id"] not in piloted_ids
                     and it["case_id"] not in {r["case_id"] for r in piloted}
                     and not is_vague_satellite_excluded(it)]

        print(f"Concession clean pool: {len(concession)}")
        print(f"Already piloted (kept, 19 scored + item 5 excluded): {len(piloted)}")
        print(f"Vague-satellite exclusions (new): {len(vague_excluded)} -- "
              f"{sorted(set(int(it['case_id'].split('-')[1]) for it in vague_excluded))}")
        print(f"Remaining to score: {len(remaining)}\n")

        new_results = run_batch(remaining, FULL_OUT_PATH + ".partial", verbose=False)
        # combine: piloted (minus excluded item 5) + newly scored remainder
        combined = [r for r in piloted if r["case_id"] != "exp3-4998-arm_4_contextual_retrieval"] + new_results
        json.dump(combined, open(FULL_OUT_PATH, "w", encoding="utf-8"), indent=2)
        report_summary(combined, FULL_OUT_PATH)
    else:
        print(f"Unknown mode {mode!r}")


if __name__ == "__main__":
    main()
