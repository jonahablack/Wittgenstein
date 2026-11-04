"""Task 6 bonus/exploratory diagnostic -- NOT part of the official
validation numbers.

The primary Task 6 run (run_two_stage_pipeline.py, results/
task6_two_stage_pipeline_report.json) found Stage 2 confirming 0 of 85
Concession survivors. A spot-check of a random sample of those 85
rejections (see the report's "concession_rejected_false_negative_spot_check"
key) found roughly 40% looked like genuine Concessions rejected via
check_4 ("plain contrast, not concession") alone, on reasoning that
mostly just restated "this is a contrast" without engaging whether the
contrast created real doubt about the nucleus that the sentence then
resolves -- see verification_classifier.build_verification_prompt_check4_revision's
docstring for the full diagnosis.

This script re-verifies the SAME 85 Concession candidates (already
extracted; no new Stage 1 calls, no new paragraphs) using ONLY a revised
check_4 wording (everything else about the checklist, model, and
programmatic confirm/reject logic is unchanged), logs to a clearly
separate file, and reports a before/after comparison -- to check whether
the 0%-confirmed result is a real ceiling or a fixable prompt-calibration
bug, before recommending a Concession screening target off the primary
run's number. Explicitly exploratory: this is a single follow-up test of
one diagnosed issue, not another open-ended prompt-tuning round.

Usage:
    venv/bin/python server/scripts/discourse_severance/factoidwiki_track/run_check4_revision_experiment.py
"""

import json
import os
import time

from env_utils import LOGS_DIR, RESULTS_DIR, ensure_dirs, load_server_env
from run_two_stage_pipeline import STAGE1_5_LOG, _load_by_pool_index, _parallel_map, DEFAULT_MAX_WORKERS
from verification_classifier import verify_candidate, build_verification_prompt_check4_revision, DEFAULT_STAGE2_MODEL

load_server_env()

EXPERIMENT_LOG = os.path.join(LOGS_DIR, "task6_stage2_concession_check4_revision_experiment.jsonl")
EXPERIMENT_REPORT = os.path.join(RESULTS_DIR, "task6_check4_revision_experiment_report.json")


def main():
    ensure_dirs()
    stage1_5_by_idx = _load_by_pool_index(STAGE1_5_LOG)
    concession_survivors = [
        r for r in stage1_5_by_idx.values()
        if r["relation_type"] == "Concession" and r.get("stage1_5", {}).get("passes_stage1_5")
    ]
    print(f"Re-verifying {len(concession_survivors)} Concession Stage-1.5 survivors with the "
          f"REVISED check_4 wording (model={DEFAULT_STAGE2_MODEL}).", flush=True)

    def _do(rec):
        t0 = time.time()
        verdict = verify_candidate(
            rec["content"], rec["relation_type"], rec["nucleus"], rec["satellite"], rec["connective"],
            model=DEFAULT_STAGE2_MODEL, prompt_builder=build_verification_prompt_check4_revision,
        )
        elapsed = time.time() - t0
        return {**rec, "stage2_check4_revision": verdict, "stage2_elapsed_seconds": elapsed}

    results = _parallel_map(_do, concession_survivors, max_workers=DEFAULT_MAX_WORKERS, label="check4-revision")

    # Same rate-limit reality as the primary run (see retry_stage2_errors in
    # run_two_stage_pipeline.py) -- retry any "_error" entries once, at lower
    # concurrency, before reporting a final summary, rather than letting
    # transient rate-limit exhaustion masquerade as a "rejected" verdict.
    errored_positions = [i for i, r in enumerate(results) if r["stage2_check4_revision"].get("_error")]
    if errored_positions:
        print(f"Retrying {len(errored_positions)} candidates that errored (max_workers=3)...", flush=True)
        retried = _parallel_map(_do, [results[i] for i in errored_positions], max_workers=3, label="check4-retry")
        for pos, new_rec in zip(errored_positions, retried):
            results[pos] = new_rec

    with open(EXPERIMENT_LOG, "w", encoding="utf-8") as fh:
        for rec in results:
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")

    n_confirmed = sum(1 for r in results if r["stage2_check4_revision"].get("confirmed"))
    n_errors = sum(1 for r in results if r["stage2_check4_revision"].get("_error"))
    check4_trigger_count = sum(
        1 for r in results
        if ((r["stage2_check4_revision"].get("checks") or {}).get("check_4_plain_contrast") or {}).get("applies")
    )

    summary = {
        "n_reverified": len(results),
        "model": DEFAULT_STAGE2_MODEL,
        "n_confirmed_with_revised_check4": n_confirmed,
        "n_rejected_with_revised_check4": len(results) - n_confirmed - n_errors,
        "n_errors": n_errors,
        "check_4_trigger_count_revised": check4_trigger_count,
        "confirmation_rate": (n_confirmed / len(results)) if results else None,
        "comparison_to_original_check4": {
            "original_confirmed": 0,
            "original_verified_total": 85,
            "original_check_4_trigger_count": 79,
            "note": "Original (task-brief-specified) check_4 wording confirmed 0/85 Concession "
                    "survivors, triggering on 79/85. This experiment changes ONLY check_4's "
                    "wording (see build_verification_prompt_check4_revision's docstring) and "
                    "re-verifies the same 85 candidates.",
        },
    }

    print("\n" + "#" * 90)
    print("CHECK-4 REVISION EXPERIMENT SUMMARY")
    print("#" * 90)
    print(json.dumps(summary, indent=2))

    with open(EXPERIMENT_REPORT, "w", encoding="utf-8") as fh:
        json.dump(summary, fh, indent=2, ensure_ascii=False)
    print(f"\nWrote {EXPERIMENT_REPORT}")
    print(f"Full per-candidate log: {EXPERIMENT_LOG}")


if __name__ == "__main__":
    main()
