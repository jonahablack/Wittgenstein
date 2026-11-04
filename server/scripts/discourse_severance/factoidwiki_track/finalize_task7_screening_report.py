"""Task 1 (full-scale run) report writer: assembles
results/task7_full_scale_screening_report.json from the already-accumulated
logs (this does NOT run any new LLM calls -- run_two_stage_pipeline.py is
what actually screens paragraphs; this just summarizes what's in the logs
once screening has stopped).

Reports both:
  - the TWO-STAGE PIPELINE's cumulative totals (task6_stage1_log.jsonl
    onward, i.e. pool_index 1803+ -- the validation batch PLUS this task's
    fresh screening, since both used the same Stage 1->1.5->2 pipeline)
  - the FRESH-ONLY subset this task actually screened (pool_index >= 2803),
    isolated so it's clear how much THIS run contributed on top of the
    already-completed validation batch
  - the AUTHORITATIVE combined-confirmed counts from confirmed_pool.py
    (which correctly folds in the Concession check4-revision-experiment
    log for the validation batch -- see that module's docstring), since
    those combined counts are what Task 2's Experiment 1/2 sample is
    actually built from, not the raw per-batch numbers alone.

Usage:
    venv/bin/python server/scripts/discourse_severance/factoidwiki_track/finalize_task7_screening_report.py
"""

import json
import os

from env_utils import RESULTS_DIR, ensure_dirs
from confirmed_pool import (
    STAGE1_LOG, STAGE2_LOG, load_jsonl_by_pool_index,
    get_confirmed_condition, get_confirmed_concession, get_elaboration_pool,
    summarize as confirmed_summarize,
)

REPORT_JSON = os.path.join(RESULTS_DIR, "task7_full_scale_screening_report.json")
FRESH_START = 2803
CANDIDATE_RELATION_TYPES = ["Condition", "Concession"]
TARGET = 50
COMFORTABLE_TARGET_BAND = (60, 70)


def _fresh_only(records_by_idx, start=FRESH_START):
    return {idx: r for idx, r in records_by_idx.items() if idx >= start}


def build_report():
    stage1_all = load_jsonl_by_pool_index(STAGE1_LOG)
    stage2_all = load_jsonl_by_pool_index(STAGE2_LOG)

    stage1_fresh = _fresh_only(stage1_all)
    stage2_fresh = _fresh_only(stage2_all)

    n_scored_cum = sum(1 for r in stage1_all.values() if not r.get("_error"))
    n_scored_fresh = sum(1 for r in stage1_fresh.values() if not r.get("_error"))

    fresh_relation_counts = {}
    for rt in ["Condition", "Concession", "Elaboration", "None"]:
        fresh_relation_counts[rt] = sum(
            1 for r in stage1_fresh.values() if not r.get("_error") and r.get("relation_type") == rt
        )

    fresh_per_relation = {}
    for rt in CANDIDATE_RELATION_TYPES:
        raw_idx_fresh = [idx for idx, r in stage1_fresh.items()
                          if not r.get("_error") and r.get("relation_type") == rt]
        confirmed_idx_fresh = [
            idx for idx in raw_idx_fresh
            if idx in stage2_fresh and stage2_fresh[idx]["stage2"].get("confirmed")
        ]
        fresh_per_relation[rt] = {
            "raw_hits": len(raw_idx_fresh),
            "stage2_confirmed": len(confirmed_idx_fresh),
            "confirmed_rate_of_fresh_scored": (
                len(confirmed_idx_fresh) / n_scored_fresh if n_scored_fresh else None
            ),
        }

    condition_confirmed = get_confirmed_condition()
    concession_confirmed = get_confirmed_concession()
    elaboration_pool = get_elaboration_pool()

    report = {
        "task": "Task 1 (full-scale run): full-scale screening, pool_index >= 2803",
        "fresh_pool_index_start": FRESH_START,
        "two_stage_pipeline_cumulative": {
            "note": "Covers the ENTIRE two-stage pipeline history (task6_stage1_log.jsonl), i.e. "
                    "pool_index 1803-2802 (Task 6 validation batch) PLUS pool_index >= 2803 (this "
                    "task's fresh screening) -- both used the identical Stage1->1.5->2 pipeline.",
            "n_paragraphs_screened": len(stage1_all),
            "n_scored": n_scored_cum,
        },
        "fresh_screening_this_task": {
            "note": f"Only pool_index >= {FRESH_START}, i.e. what THIS task actually screened, on "
                    "top of the already-completed validation batch.",
            "n_paragraphs_screened": len(stage1_fresh),
            "n_scored": n_scored_fresh,
            "stage1_relation_type_counts": fresh_relation_counts,
            "per_relation": fresh_per_relation,
        },
        "authoritative_combined_confirmed_counts": {
            "note": "From confirmed_pool.py -- Condition: main stage2_log, any wording. Concession: "
                    "UNION of main stage2_log (revised wording, pool_index >= 2803) and the Concession "
                    "check4-revision-experiment log (revised wording, pool_index 1803-2802) -- see "
                    "confirmed_pool.get_confirmed_concession's docstring for why this union is the "
                    "authoritative Concession count, not the main log alone.",
            "condition_confirmed_n": len(condition_confirmed),
            "condition_confirmed_pool_indices": sorted(condition_confirmed),
            "concession_confirmed_n": len(concession_confirmed),
            "concession_confirmed_pool_indices": sorted(concession_confirmed),
            "elaboration_available_raw_hits_n": len(elaboration_pool),
        },
        "targets": {
            "target_per_category": TARGET,
            "comfortable_target_band": list(COMFORTABLE_TARGET_BAND),
            "condition_meets_target": len(condition_confirmed) >= TARGET,
            "condition_meets_comfortable_band": len(condition_confirmed) >= COMFORTABLE_TARGET_BAND[0],
            "concession_meets_target": len(concession_confirmed) >= TARGET,
            "concession_meets_comfortable_band": len(concession_confirmed) >= COMFORTABLE_TARGET_BAND[0],
        },
    }
    return report


def main():
    ensure_dirs()
    report = build_report()
    with open(REPORT_JSON, "w", encoding="utf-8") as fh:
        json.dump(report, fh, indent=2, ensure_ascii=False)
    print(json.dumps(report, indent=2))
    print(f"\nWrote {REPORT_JSON}")


if __name__ == "__main__":
    main()
