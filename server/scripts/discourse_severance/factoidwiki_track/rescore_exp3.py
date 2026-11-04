"""PART 1c: re-score Experiment 3 (repair-arm correct/dangerous_failure
labels) for Propositionizer, AtomicRAG, and own-baseline -- the three
chunkers whose repair arms were scored with build_paragraph_judge_prompt,
now replaced by the validated v2 pipeline. Arms 2/3/4 only (the three
that attempt a repair at all; arm_1/5/6 are not repair attempts, per
evaluation.tex's own established scope).
"""

import json
import sys

sys.path.insert(0, ".")
from pipeline_part0d_v2 import evaluate_v2  # noqa: E402

REPORTS = {
    "propositionizer": "results/task8_factoidwiki_exp3_report.json",
    "own_baseline": "own_baseline_track/results/own_baseline_exp3_report.json",
    "atomicrag": "atomicrag_track/results/atomicrag_exp3_report.json",
}
REPAIR_ARMS = ["arm_2_disco_rag", "arm_3_custom_fallback", "arm_4_contextual_retrieval"]


def main():
    report = {}
    for chunker, path in REPORTS.items():
        d = json.load(open(path, encoding="utf-8"))
        print(f"\n=== {chunker} ({len(d['records'])} records) ===")
        chunker_out = {}
        for arm in REPAIR_ARMS:
            old_correct = old_dangerous = new_correct = new_dangerous = 0
            mismatches = []
            for r in d["records"]:
                rel = r["relation"]
                arm_data = r[arm]
                props = arm_data.get("propositions") or []
                old_bucket = arm_data.get("bucket")
                if old_bucket not in ("correct", "dangerous_failure"):
                    continue  # detectable_failure or missing -- excluded, matches original scope
                out = evaluate_v2(props, rel["nucleus"], rel["satellite"], rel["connective"],
                                   rel["relation_type"], source_paragraph=r["content"])
                new_bucket = "correct" if out["preserved"] else "dangerous_failure"
                if old_bucket == "correct":
                    old_correct += 1
                else:
                    old_dangerous += 1
                if new_bucket == "correct":
                    new_correct += 1
                else:
                    new_dangerous += 1
                if old_bucket != new_bucket:
                    mismatches.append({"pool_index": r["pool_index"], "old_bucket": old_bucket,
                                        "new_bucket": new_bucket, "reason": out["reason"]})
            n = old_correct + old_dangerous
            old_rate = round(100 * old_dangerous / n, 1) if n else None
            new_rate = round(100 * new_dangerous / n, 1) if n else None
            chunker_out[arm] = {
                "n": n, "old_correct": old_correct, "old_dangerous_failure": old_dangerous,
                "new_correct": new_correct, "new_dangerous_failure": new_dangerous,
                "old_dangerous_rate_pct": old_rate, "new_dangerous_rate_pct": new_rate,
                "delta": round(new_rate - old_rate, 1) if (old_rate is not None and new_rate is not None) else None,
                "n_mismatches": len(mismatches), "mismatches": mismatches,
            }
            print(f"  {arm:25s} n={n:3d}  old_dangerous={old_rate}%  new_dangerous={new_rate}%  "
                  f"delta={chunker_out[arm]['delta']}  ({len(mismatches)} label changes)")
        report[chunker] = chunker_out

    json.dump(report, open("results/exp3_rescore_v2_report.json", "w"), indent=2)
    print("\nWritten to results/exp3_rescore_v2_report.json")


if __name__ == "__main__":
    main()
