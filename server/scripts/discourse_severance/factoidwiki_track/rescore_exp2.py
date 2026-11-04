"""PART 1b: re-score Experiment 2 (governing relations vs Elaboration
control) for Propositionizer, AtomicRAG, and own-baseline. NuggetIndex
deferred pending its own scoped triple-judge redesign (see the 1b
diagnostic: same bug structurally, ~20% empirical mislabel rate, but
the v2 pipeline does not transfer to triple-rendered text unmodified).

Governing side: re-scored with the validated v2 parser+NLI pipeline,
using each chunker's own Condition-A-equivalent output (the same field
already re-scored per relation type in rescore_exp1.py for
propositionizer/own_baseline; computed fresh here for AtomicRAG, which
is not part of the Exp1 ablation).

Elaboration control side: NOT re-scored again here -- already corrected
earlier in this project (llm_judge_severance_elaboration_v2), pulled
directly from the existing *_elaboration_corrected_log.jsonl files
(original_preserved / corrected_preserved already computed there).
"""

import json
import sys

sys.path.insert(0, ".")
from pipeline_part0d_v2 import evaluate_v2  # noqa: E402

GOVERNING = {
    "propositionizer": {"log": "logs/task7_experiment_govern_log.jsonl",
                         "prop_field": "condition_a_propositions", "old_field": "severance_a"},
    "own_baseline": {"log": "own_baseline_track/logs/own_baseline_govern_log.jsonl",
                      "prop_field": "condition_a_claims", "old_field": "severance_a"},
    "atomicrag": {"log": "atomicrag_track/logs/atomicrag_govern_log.jsonl",
                  "prop_field": "atomicrag_propositions", "old_field": "severance_atomicrag"},
}
ELABORATION = {
    "propositionizer": "logs/task7_elaboration_corrected_log.jsonl",
    "own_baseline": "own_baseline_track/logs/own_baseline_elaboration_corrected_log.jsonl",
    "atomicrag": "atomicrag_track/logs/atomicrag_elaboration_corrected_log.jsonl",
}


def rate(n, total):
    return round(100 * n / total, 1) if total else None


def score_governing(recs, prop_field, old_field):
    old_severed = new_severed = n = 0
    mismatches = []
    for r in recs:
        old_p = r[old_field]["preserved"]
        if old_p is None:
            continue
        props = r.get(prop_field) or []
        out = evaluate_v2(props, r["nucleus"], r["satellite"], r["connective"], r["relation_type"],
                           source_paragraph=r["content"])
        new_p = out["preserved"]
        n += 1
        if not old_p:
            old_severed += 1
        if not new_p:
            new_severed += 1
        if old_p != new_p:
            mismatches.append({"pool_index": r["pool_index"], "old_preserved": old_p,
                                "new_preserved": new_p, "reason": out["reason"]})
    return {"n": n, "old_severed": old_severed, "new_severed": new_severed,
            "old_rate_pct": rate(old_severed, n), "new_rate_pct": rate(new_severed, n),
            "n_mismatches": len(mismatches), "mismatches": mismatches}


def score_elaboration(path):
    recs = [json.loads(l) for l in open(path, encoding="utf-8")]
    n = len(recs)
    orig_severed = sum(1 for r in recs if r["original_preserved"] is False)
    corr_severed = sum(1 for r in recs if r["corrected_preserved"] is False)
    return {"n": n, "original_severed": orig_severed, "corrected_severed": corr_severed,
            "original_rate_pct": rate(orig_severed, n), "corrected_rate_pct": rate(corr_severed, n)}


def main():
    report = {}
    for chunker, cfg in GOVERNING.items():
        recs = [json.loads(l) for l in open(cfg["log"], encoding="utf-8")]
        print(f"\n=== {chunker} ===")
        gov = score_governing(recs, cfg["prop_field"], cfg["old_field"])
        elab = score_elaboration(ELABORATION[chunker])
        report[chunker] = {"governing": gov, "elaboration": elab}
        print(f"  Governing (Condition+Concession): n={gov['n']}  old={gov['old_rate_pct']}%  "
              f"new={gov['new_rate_pct']}%  delta={round(gov['new_rate_pct'] - gov['old_rate_pct'], 1)}  "
              f"({gov['n_mismatches']} label changes)")
        print(f"  Elaboration (already corrected earlier): n={elab['n']}  "
              f"original={elab['original_rate_pct']}%  corrected={elab['corrected_rate_pct']}%")

    json.dump(report, open("results/exp2_rescore_v2_report.json", "w"), indent=2)
    print("\nWritten to results/exp2_rescore_v2_report.json")


if __name__ == "__main__":
    main()
