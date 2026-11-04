"""Validation harness for build_paragraph_judge_prompt_condition_concession_v2.

Ground truth, combined per the user's explicit validation spec:
  - All 82 "mislabeled_actually_correct" cases from
    results/dangerous_failure_full_audit.json -- expected preserved=True
    under v2 (these are the confirmed-wrong-verbatim/paraphrase-preserved
    cases the fix must flip).
  - All 35 "confirmed_dangerous_failure" cases from the same audit --
    expected preserved=False under v2 (genuine failures must stay caught).
  - Two explicit misattachment negative controls, pool 3278/arm_4 and
    pool 4200/arm_4 (labeled "ambiguous" in the audit but asserted by the
    user as genuine misattachment failures for this specific test) --
    expected preserved=False under v2. These are the critical check that
    dropping the narration requirement did not also drop attachment.

Paragraph text is pulled from results/task8_factoidwiki_exp3_report.json
by pool_index (the audit file itself does not carry the paragraph).
"""

import json
import os
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
RESULTS_DIR = os.path.join(SCRIPT_DIR, "results")
sys.path.insert(0, SCRIPT_DIR)

from severance_judge_paragraph import (  # noqa: E402
    llm_judge_paragraph_severance_condition_concession_v2,
)

AUDIT_PATH = os.path.join(RESULTS_DIR, "dangerous_failure_full_audit.json")
REPORT_PATH = os.path.join(RESULTS_DIR, "task8_factoidwiki_exp3_report.json")
OUT_PATH = os.path.join(RESULTS_DIR, "condition_concession_v2_validation_report.json")

NEGATIVE_CONTROLS = {(3278, "arm_4_contextual_retrieval"), (4200, "arm_4_contextual_retrieval")}


def main():
    audit = json.load(open(AUDIT_PATH, encoding="utf-8"))
    report = json.load(open(REPORT_PATH, encoding="utf-8"))
    records_by_pool = {r["pool_index"]: r for r in report["records"]}

    items = []
    for c in audit["cases"]:
        cls = c["audit_classification"]
        if cls == "mislabeled_actually_correct":
            expected = True
        elif cls == "confirmed_dangerous_failure":
            expected = False
        else:
            continue
        items.append((c, expected, "audit"))

    # Explicit misattachment negative controls (audit called these
    # "ambiguous"; user's spec overrides that for this specific test).
    for c in audit["cases"]:
        key = (c["pool_index"], c["arm"])
        if key in NEGATIVE_CONTROLS and c["audit_classification"] == "ambiguous":
            items.append((c, False, "negative_control"))

    print(f"Validation set: {len(items)} cases "
          f"({sum(1 for _, e, _ in items if e)} expected preserved, "
          f"{sum(1 for _, e, _ in items if not e)} expected severed)")

    results = []
    n_correct = 0
    n_failed_call = 0
    for i, (c, expected, source) in enumerate(items):
        pool_index = c["pool_index"]
        arm = c["arm"]
        rec = records_by_pool.get(pool_index)
        if rec is None:
            print(f"  WARNING: pool_index {pool_index} not found in task8 report, skipping")
            continue
        paragraph = rec["content"]
        relation = rec["relation"]
        propositions = c["propositions"]

        verdict = llm_judge_paragraph_severance_condition_concession_v2(
            paragraph, relation, propositions
        )
        actual = verdict["preserved"]
        if actual is None:
            n_failed_call += 1
        correct = actual == expected
        n_correct += int(correct)

        results.append({
            "pool_index": pool_index,
            "arm": arm,
            "relation_type": c["relation_type"],
            "source": source,
            "audit_classification": c["audit_classification"],
            "expected_preserved": expected,
            "v2_preserved": actual,
            "correct": correct,
            "v2_nucleus_recoverable": verdict.get("nucleus_recoverable"),
            "v2_marker_attached": verdict.get("marker_attached_to_correct_satellite"),
            "v2_quoted_nucleus_evidence": verdict.get("quoted_nucleus_evidence"),
            "v2_quoted_marker_clauses": verdict.get("quoted_marker_clauses"),
            "v2_reasoning": verdict.get("reasoning"),
        })
        tag = "OK" if correct else "MISMATCH"
        print(f"  [{i+1}/{len(items)}] pool {pool_index} {arm} expected={expected} "
              f"actual={actual} {tag}")

    n_scored = len([r for r in results if r["v2_preserved"] is not None])
    agreement = n_correct / len(results) if results else 0.0

    mismatches = [r for r in results if not r["correct"]]
    negative_control_results = [r for r in results if r["source"] == "negative_control"]

    summary = {
        "n_total": len(results),
        "n_call_failed": n_failed_call,
        "n_correct": n_correct,
        "agreement": agreement,
        "n_mismatches": len(mismatches),
        "negative_controls_passed": all(r["correct"] for r in negative_control_results),
        "negative_control_detail": negative_control_results,
    }
    print()
    print(json.dumps(summary if False else {
        "n_total": summary["n_total"],
        "n_call_failed": summary["n_call_failed"],
        "n_correct": summary["n_correct"],
        "agreement": round(agreement, 4),
        "n_mismatches": summary["n_mismatches"],
        "negative_controls_passed": summary["negative_controls_passed"],
    }, indent=2))

    out = {
        "validation_set_size": len(items),
        "agreement": agreement,
        "n_correct": n_correct,
        "n_mismatches": len(mismatches),
        "negative_controls_passed": summary["negative_controls_passed"],
        "mismatches": mismatches,
        "results": results,
    }
    json.dump(out, open(OUT_PATH, "w", encoding="utf-8"), indent=2)
    print(f"\nFull report written to {OUT_PATH}")


if __name__ == "__main__":
    main()
