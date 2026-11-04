"""PART 1a: re-score Experiment 1 (Condition A vs Condition B ablation)
for Propositionizer and own-baseline, the two chunkers that support it,
using the validated v2 parser+NLI pipeline. Reports original (old LLM
judge) and corrected (v2 pipeline) severance rates side by side, per
relation type, per condition -- never one replacing the other silently.
"""

import json
import sys

sys.path.insert(0, ".")
from pipeline_part0d_v2 import evaluate_v2  # noqa: E402

CHUNKERS = {
    "propositionizer": {"log": "logs/task7_experiment_govern_log.jsonl",
                         "prop_field_a": "condition_a_propositions", "prop_field_b": "condition_b_propositions"},
    "own_baseline": {"log": "own_baseline_track/logs/own_baseline_govern_log.jsonl",
                      "prop_field_a": "condition_a_claims", "prop_field_b": "condition_b_propositions"},
}


def rate(n_severed, n_total):
    return round(100 * n_severed / n_total, 1) if n_total else None


def score_condition(recs, prop_field):
    """Returns {relation_type: {"old_severed": n, "new_severed": n, "n": n, "cases": [...]}}"""
    out = {"Condition": {"old_severed": 0, "new_severed": 0, "n": 0, "mismatches": []},
           "Concession": {"old_severed": 0, "new_severed": 0, "n": 0, "mismatches": []}}
    old_field = "severance_a" if prop_field.startswith("condition_a") else "severance_b"
    for r in recs:
        rt = r["relation_type"]
        props = r.get(prop_field) or []
        old_preserved = r[old_field]["preserved"]
        if old_preserved is None:
            continue  # call failure in the original run, excluded same as original analysis
        out_v2 = evaluate_v2(props, r["nucleus"], r["satellite"], r["connective"], rt,
                              source_paragraph=r["content"])
        new_preserved = out_v2["preserved"]
        out[rt]["n"] += 1
        if not old_preserved:
            out[rt]["old_severed"] += 1
        if not new_preserved:
            out[rt]["new_severed"] += 1
        if old_preserved != new_preserved:
            out[rt]["mismatches"].append({
                "pool_index": r["pool_index"], "old_preserved": old_preserved,
                "new_preserved": new_preserved, "reason": out_v2["reason"],
            })
    return out


def main():
    report = {}
    for chunker, cfg in CHUNKERS.items():
        recs = [json.loads(l) for l in open(cfg["log"], encoding="utf-8")]
        print(f"\n=== {chunker} ({len(recs)} records) ===")
        cond_a = score_condition(recs, cfg["prop_field_a"])
        cond_b = score_condition(recs, cfg["prop_field_b"])
        report[chunker] = {"condition_a": cond_a, "condition_b": cond_b}
        for cond_name, cond in (("Condition A (standard)", cond_a), ("Condition B (relation-aware elicitation)", cond_b)):
            print(f"  -- {cond_name} --")
            for rt in ("Condition", "Concession"):
                d = cond[rt]
                old_r, new_r = rate(d["old_severed"], d["n"]), rate(d["new_severed"], d["n"])
                print(f"    {rt:10s} n={d['n']:3d}  old_severed={old_r}%  new_severed={new_r}%  "
                      f"delta={round(new_r - old_r, 1) if old_r is not None else None}  "
                      f"({len(d['mismatches'])} label changes)")

    json.dump(report, open("results/exp1_rescore_v2_report.json", "w"), indent=2)
    print("\nWritten to results/exp1_rescore_v2_report.json")


if __name__ == "__main__":
    main()
