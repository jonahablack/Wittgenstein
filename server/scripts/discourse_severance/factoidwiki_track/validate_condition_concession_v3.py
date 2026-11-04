"""Validation harness for llm_judge_paragraph_severance_condition_concession_v3
(the two-call locator + narrow mismatch-detection architecture).

Ground truth, combined per the user's validation spec:
  - All 82 "mislabeled_actually_correct" cases from
    results/dangerous_failure_full_audit.json -- expected preserved=True,
    EXCEPT pool 4117/arm_2_disco_rag, independently re-checked and moved
    to the negative-control set below (nucleus/satellite roles are
    reversed by the atomized proposition's clause order: the original
    satellite string is "although French remained the only official
    language in Belgium" -- "although" precedes the SATELLITE in the
    source text -- but arm_2's proposition reads "Although Dutch was
    allowed ..., French remained the only official language", which
    fronts "although" onto the NUCLEUS instead, reversing which fact is
    being conceded to which. arm_3 and arm_4 for the same pool_index
    keep the original nucleus-first order and remain expected=True.
  - All 35 "confirmed_dangerous_failure" cases -- expected preserved=False.
  - Three misattachment negative controls, expected preserved=False:
    pool 3278/arm_4, pool 4200/arm_4 (both "ambiguous" in the audit,
    asserted by the user as genuine misattachment), and pool
    4117/arm_2_disco_rag (see above).

Paragraph text is pulled from results/task8_factoidwiki_exp3_report.json
by pool_index.
"""

import json
import os
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
RESULTS_DIR = os.path.join(SCRIPT_DIR, "results")
sys.path.insert(0, SCRIPT_DIR)

from severance_judge_paragraph import (  # noqa: E402
    llm_judge_paragraph_severance_condition_concession_v3,
)

AUDIT_PATH = os.path.join(RESULTS_DIR, "dangerous_failure_full_audit.json")
REPORT_PATH = os.path.join(RESULTS_DIR, "task8_factoidwiki_exp3_report.json")
OUT_PATH = os.path.join(RESULTS_DIR, "condition_concession_v3_validation_report.json")

NEGATIVE_CONTROLS = {(3278, "arm_4_contextual_retrieval"), (4200, "arm_4_contextual_retrieval")}
REVERSAL_OVERRIDE = (4117, "arm_2_disco_rag")  # audit said True; independently re-checked -> False

KEY_CASES = [
    (2004, "arm_2_disco_rag"),
    (2272, "arm_2_disco_rag"),
    (3278, "arm_4_contextual_retrieval"),
    (4200, "arm_4_contextual_retrieval"),
    (4117, "arm_2_disco_rag"),
]


def main():
    audit = json.load(open(AUDIT_PATH, encoding="utf-8"))
    report = json.load(open(REPORT_PATH, encoding="utf-8"))
    records_by_pool = {r["pool_index"]: r for r in report["records"]}

    items = []
    for c in audit["cases"]:
        cls = c["audit_classification"]
        key = (c["pool_index"], c["arm"])
        if key == REVERSAL_OVERRIDE:
            items.append((c, False, "reversal_override"))
            continue
        if cls == "mislabeled_actually_correct":
            items.append((c, True, "audit"))
        elif cls == "confirmed_dangerous_failure":
            items.append((c, False, "audit"))
        elif key in NEGATIVE_CONTROLS:
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

        verdict = llm_judge_paragraph_severance_condition_concession_v3(
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
            "v3_preserved": actual,
            "correct": correct,
            "v3_nucleus_found": verdict.get("nucleus_found"),
            "v3_satellite_found": verdict.get("satellite_found"),
            "v3_marker_found": verdict.get("marker_found"),
            "v3_attachment_check_ran": verdict.get("attachment_check_ran"),
            "v3_flagged_marker_floating": verdict.get("flagged_marker_floating"),
            "v3_reasoning": verdict.get("reasoning"),
        })
        tag = "OK" if correct else "MISMATCH"
        sys.stderr.write(f"  [{i+1}/{len(items)}] pool {pool_index} {arm} expected={expected} "
                          f"actual={actual} {tag}\n")
        sys.stderr.flush()

    agreement = n_correct / len(results) if results else 0.0
    mismatches = [r for r in results if not r["correct"]]
    key_case_results = {(r["pool_index"], r["arm"]): r for r in results
                         if (r["pool_index"], r["arm"]) in KEY_CASES}

    print()
    print(json.dumps({
        "n_total": len(results),
        "n_call_failed": n_failed_call,
        "n_correct": n_correct,
        "agreement": round(agreement, 4),
        "n_mismatches": len(mismatches),
    }, indent=2))

    print("\nKey cases:")
    for key in KEY_CASES:
        r = key_case_results.get(key)
        if r:
            print(f"  pool {key[0]}/{key[1]}: expected={r['expected_preserved']} "
                  f"actual={r['v3_preserved']} {'OK' if r['correct'] else 'MISMATCH'}")
        else:
            print(f"  pool {key[0]}/{key[1]}: NOT IN VALIDATION SET")

    n_flagged = sum(1 for r in results if r["v3_flagged_marker_floating"])
    if n_flagged:
        print(f"\n{n_flagged} case(s) hit the flagged_marker_floating branch (uncovered by "
              f"validation, treated as severed but flagged for manual review):")
        for r in results:
            if r["v3_flagged_marker_floating"]:
                print(f"  pool {r['pool_index']}/{r['arm']}: expected={r['expected_preserved']} "
                      f"actual={r['v3_preserved']} {'OK' if r['correct'] else 'MISMATCH'}")

    out = {
        "validation_set_size": len(items),
        "agreement": agreement,
        "n_correct": n_correct,
        "n_mismatches": len(mismatches),
        "mismatches": mismatches,
        "results": results,
    }
    json.dump(out, open(OUT_PATH, "w", encoding="utf-8"), indent=2)
    print(f"\nFull report written to {OUT_PATH}")


if __name__ == "__main__":
    main()
