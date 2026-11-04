"""Task 6 orchestration: classify-then-verify two-stage pipeline.

Two rounds of single-stage prompt tuning (Task 5 -> Task 5b, see
README.md) failed to make relation_classifier.py reliably precise
(Condition ~24.5-34.0%, Concession ~46.5-53.5% by spot-check -- see
results/task5b_revised_precision_report.json). This script wires that
same Stage-1 classifier into a three-stage pipeline instead of tuning its
prompt a third time:

  Stage 1  (candidate generation, cheap):   relation_classifier.classify_paragraph,
             REUSED AS-IS, unmodified -- see that file. Every paragraph in
             the batch gets one gpt-4o-mini call; Condition/Concession
             hits become "candidates" for the next stage (Elaboration/None
             are logged for rate-tracking but go no further).
  Stage 1.5 (free, deterministic pre-filter, no LLM call): candidate_prefilter.py.
             Rejects a candidate immediately if its own reported
             "connective" and/or "satellite" text does not actually appear
             (verbatim/near-verbatim) in the source paragraph -- catches
             the hallucinated-span half of the 5th failure mode Task 5b's
             spot-check found, at zero additional cost.
  Stage 2   (strict verification, one LLM call per Stage-1.5 survivor):
             verification_classifier.py. An adversarial/skeptical
             checklist call, structurally different from Stage 1's
             classify-from-scratch prompt, on gpt-4o (see that module's
             docstring for the model-choice rationale). Only confirms a
             candidate if none of five named failure modes can be found to
             apply. As of the full-scale run (2026-08), this stage uses
             verify_candidate()'s DEFAULT prompt_builder, which is now
             build_verification_prompt_check4_revision (promoted from the
             original build_verification_prompt after a human audit --
             manual_concession_audit.md -- found the revised check_4
             wording agrees with human judgment 84.6% of the time vs. 46.2%
             for the original; see verification_classifier.py's docstring
             for the full writeup). This script never passes prompt_builder
             explicitly, so it always tracks whatever verify_candidate()'s
             current default is. Every Stage-2 log record carries a
             "verification_prompt_version" field so a log spanning both
             eras (pool_index 1803-2802 = original wording, >= 2803 =
             revised wording) stays self-documenting.

Each stage's full history is an independent, append-only, pool_index-keyed
JSONL log (same resumable-by-offset-bump pattern as
run_relation_screening.py), so re-running with a bumped --offset/--n
extends the total screened sample without re-processing or duplicating
any paragraph, at any stage. The funnel/report is always recomputed over
the FULL accumulated logs, not just the latest batch.

Usage:
    venv/bin/python server/scripts/discourse_severance/factoidwiki_track/run_two_stage_pipeline.py \\
        --offset 1803 --n 1000

    # extend an existing run with more paragraphs:
    venv/bin/python server/scripts/discourse_severance/factoidwiki_track/run_two_stage_pipeline.py \\
        --offset 2803 --n 500

    # re-run only Stage 1.5 / Stage 2 over an existing Stage-1 log (e.g.
    # after fixing a Stage-2 bug, without re-spending Stage-1 calls):
    venv/bin/python server/scripts/discourse_severance/factoidwiki_track/run_two_stage_pipeline.py \\
        --skip-stage1
"""

import argparse
import json
import os
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed

from download_data import get_classifier_pool, shuffled_records
from env_utils import LOGS_DIR, RESULTS_DIR, ensure_dirs, load_server_env
from relation_classifier import classify_paragraph
from candidate_prefilter import prefilter_candidate
from verification_classifier import verify_candidate, DEFAULT_STAGE2_MODEL

load_server_env()

STAGE1_LOG = os.path.join(LOGS_DIR, "task6_stage1_log.jsonl")
STAGE1_5_LOG = os.path.join(LOGS_DIR, "task6_stage1_5_log.jsonl")
STAGE2_LOG = os.path.join(LOGS_DIR, "task6_stage2_log.jsonl")
REPORT_JSON = os.path.join(RESULTS_DIR, "task6_two_stage_pipeline_report.json")

# pool_index 0-902 was Task 5's batch, 903-1802 was Task 5b's -- see
# README.md and logs/task5_screening_log.jsonl / task5b_screening_log.jsonl.
# Enforced here (rather than just documented) so a mistyped --offset can't
# silently re-screen and dilute an already-screened range.
MIN_FRESH_POOL_INDEX = 1803

CANDIDATE_RELATION_TYPES = ["Condition", "Concession"]
TARGET_PER_CATEGORY = 50
DEFAULT_N = 1000
DEFAULT_MAX_WORKERS = 8


def _parallel_map(func, items, max_workers=DEFAULT_MAX_WORKERS, label=""):
    """Same ThreadPoolExecutor-with-as_completed pattern as
    run_relation_screening.py's _parallel_map, duplicated locally per this
    track's self-contained-scripts convention (see env_utils.py).
    """
    results = [None] * len(items)
    if not items:
        return results
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_idx = {executor.submit(func, item): i for i, item in enumerate(items)}
        done = 0
        for future in as_completed(future_to_idx):
            i = future_to_idx[future]
            results[i] = future.result()
            done += 1
            if done % 25 == 0 or done == len(items):
                print(f"  {label} {done}/{len(items)}", flush=True)
    return results


def _load_jsonl(path):
    if not os.path.exists(path):
        return []
    records = []
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    return records


def _load_by_pool_index(path):
    """De-dup by pool_index, keeping the LAST write for a given index --
    same convention as run_relation_screening.py's load_full_log.
    """
    records = _load_jsonl(path)
    by_index = {r["pool_index"]: r for r in records}
    return {k: by_index[k] for k in sorted(by_index)}


def _append_jsonl(path, records):
    if not records:
        return
    with open(path, "a", encoding="utf-8") as fh:
        for rec in records:
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")


def run_stage1(offset, n, model, max_workers, log_file):
    ensure_dirs()
    if offset < MIN_FRESH_POOL_INDEX:
        raise ValueError(
            f"FATAL: offset ({offset}) is below MIN_FRESH_POOL_INDEX "
            f"({MIN_FRESH_POOL_INDEX}). pool_index 0-902 was screened by Task 5 and "
            "903-1802 by Task 5b (see logs/task5_screening_log.jsonl and "
            "logs/task5b_screening_log.jsonl) -- re-screening that range would not be "
            "a fresh batch. Pass --offset >= 1803."
        )
    pool = get_classifier_pool(shuffled_records())
    if offset + n > len(pool):
        raise ValueError(f"FATAL: offset+n ({offset + n}) exceeds classifier pool size ({len(pool)})")
    batch = pool[offset:offset + n]

    already = _load_by_pool_index(log_file)
    todo = [(idx, rec) for idx, rec in enumerate(batch, start=offset) if idx not in already]
    print(f"Stage 1: pool[{offset}:{offset + n}] ({len(batch)} paragraphs) -- "
          f"{len(batch) - len(todo)} already in {log_file}, {len(todo)} new "
          f"(model={model or 'gpt-4o-mini (default)'}, max_workers={max_workers}).", flush=True)

    def _do(item):
        idx, record = item
        t0 = time.time()
        relation = classify_paragraph(record["content"], model=model)
        elapsed = time.time() - t0
        return {
            "pool_index": idx,
            "title": record["title"],
            "section": record["section"],
            "content": record["content"],
            "stage1_model": model or "gpt-4o-mini",
            "elapsed_seconds": elapsed,
            **relation,
        }

    t0 = time.time()
    new_results = _parallel_map(_do, todo, max_workers=max_workers, label="stage1")
    elapsed_total = time.time() - t0
    _append_jsonl(log_file, new_results)
    if new_results:
        n_errors = sum(1 for r in new_results if r.get("_error"))
        print(f"Stage 1 done: {len(new_results)} new paragraphs classified in "
              f"{elapsed_total:.1f}s, {n_errors} errors.", flush=True)
    return elapsed_total


def run_stage1_5(stage1_log, stage1_5_log):
    stage1_records = _load_by_pool_index(stage1_log)
    already = _load_by_pool_index(stage1_5_log)
    candidates = [
        r for idx, r in stage1_records.items()
        if idx not in already
        and not r.get("_error")
        and r.get("relation_type") in CANDIDATE_RELATION_TYPES
    ]
    print(f"Stage 1.5: {len(candidates)} new Condition/Concession candidates to "
          f"free-prefilter (of {len(stage1_records)} total Stage-1 records so far).", flush=True)

    results = [{**rec, "stage1_5": prefilter_candidate(rec)} for rec in candidates]
    _append_jsonl(stage1_5_log, results)
    if results:
        n_pass = sum(1 for r in results if r["stage1_5"]["passes_stage1_5"])
        print(f"Stage 1.5 done: {len(results)} checked, {n_pass} passed, "
              f"{len(results) - n_pass} rejected for a hallucinated connective/satellite "
              "(zero LLM calls).", flush=True)
    return results


def _verify_and_wrap(rec, model):
    t0 = time.time()
    verdict = verify_candidate(
        rec["content"], rec["relation_type"], rec["nucleus"], rec["satellite"],
        rec["connective"], model=model,
    )
    elapsed = time.time() - t0
    return {**rec, "stage2": verdict, "stage2_elapsed_seconds": elapsed}


def run_stage2(stage1_5_log, stage2_log, model, max_workers):
    stage1_5_records = _load_by_pool_index(stage1_5_log)
    already = _load_by_pool_index(stage2_log)
    survivors = [
        r for idx, r in stage1_5_records.items()
        if idx not in already and r.get("stage1_5", {}).get("passes_stage1_5")
    ]
    print(f"Stage 2: {len(survivors)} new Stage-1.5 survivors to verify "
          f"(model={model}, max_workers={max_workers}).", flush=True)

    t0 = time.time()
    new_results = _parallel_map(
        lambda rec: _verify_and_wrap(rec, model), survivors, max_workers=max_workers, label="stage2"
    )
    elapsed_total = time.time() - t0
    _append_jsonl(stage2_log, new_results)
    if new_results:
        n_confirmed = sum(1 for r in new_results if r["stage2"].get("confirmed"))
        print(f"Stage 2 done: {len(new_results)} new verifications in {elapsed_total:.1f}s, "
              f"{n_confirmed} confirmed, {len(new_results) - n_confirmed} rejected.", flush=True)
    return elapsed_total


def retry_stage2_errors(stage2_log, model, max_workers):
    """A Stage-2 log entry with "_error" (e.g. "no_response") means the
    candidate was NEVER actually verified -- generate_response's own
    internal retry/backoff (api_call.py, 3 attempts) was exhausted, almost
    always because of sustained per-minute rate-limiting when running many
    gpt-4o calls at high parallelism back-to-back. run_stage2()'s own
    dedup treats ANY existing log entry (including an errored one) as
    "already done" so re-running the main pipeline will never retry these
    on its own -- silently counting a never-verified candidate as
    "rejected" would violate this project's explicit no-silent-failures
    principle, so this is a dedicated, explicit retry path instead.

    Re-verifies ONLY the errored pool_indices, using the SAME candidate
    record already stored in the Stage-2 log (which already carries every
    Stage-1/Stage-1.5 field needed), and appends fresh results -- the
    existing last-write-wins dedup (_load_by_pool_index) means a
    successful retry transparently supersedes the old error entry the
    next time the log is read, with both attempts preserved in the raw
    file for audit.
    """
    stage2_by_idx = _load_by_pool_index(stage2_log)
    errored = [r for r in stage2_by_idx.values() if r["stage2"].get("_error")]
    print(f"Retrying {len(errored)} Stage-2 candidates that previously errored "
          f"(model={model}, max_workers={max_workers}).", flush=True)
    if not errored:
        return []

    new_results = _parallel_map(
        lambda rec: _verify_and_wrap(rec, model), errored, max_workers=max_workers, label="stage2-retry"
    )
    _append_jsonl(stage2_log, new_results)
    n_confirmed = sum(1 for r in new_results if r["stage2"].get("confirmed"))
    n_still_errored = sum(1 for r in new_results if r["stage2"].get("_error"))
    print(f"Retry done: {len(new_results)} re-verified, {n_confirmed} confirmed, "
          f"{n_still_errored} still errored.", flush=True)
    return new_results


def extrapolate_to_target(confirmed_count, n_scored, target=TARGET_PER_CATEGORY):
    if not n_scored:
        return None
    if confirmed_count == 0:
        upper_rate = 3.0 / n_scored
        return {
            "observed_confirmed_rate": 0.0,
            "n_needed_point_estimate": None,
            "note": (
                f"0 Stage-2-confirmed hits in {n_scored} paragraphs scored -- rule-of-three "
                f"95% upper confidence bound on the true rate is ~{upper_rate:.4%}, implying "
                f"screening would need to exceed roughly {target / upper_rate:,.0f} paragraphs "
                f"to plausibly reach {target}+ EVEN AT THAT OPTIMISTIC UPPER BOUND."
            ),
        }
    rate = confirmed_count / n_scored
    return {
        "observed_confirmed_rate": rate,
        "n_needed_point_estimate": target / rate,
        "note": f"At the observed Stage-2-CONFIRMED rate ({confirmed_count}/{n_scored} = "
                f"{rate:.2%} of paragraphs scored through the full pipeline), reaching "
                f"{target}+ confirmed instances needs ~{target / rate:,.0f} paragraphs "
                "screened (point estimate; noisy at these counts, same caveat as every "
                "other extrapolation in this track).",
    }


def compute_funnel(stage1_log, stage1_5_log, stage2_log):
    stage1_by_idx = _load_by_pool_index(stage1_log)
    stage1_5_by_idx = _load_by_pool_index(stage1_5_log)
    stage2_by_idx = _load_by_pool_index(stage2_log)

    n_screened = len(stage1_by_idx)
    n_stage1_errors = sum(1 for r in stage1_by_idx.values() if r.get("_error"))
    n_scored = n_screened - n_stage1_errors
    stage1_counts = Counter(r["relation_type"] for r in stage1_by_idx.values() if not r.get("_error"))

    per_relation = {}
    for rel in CANDIDATE_RELATION_TYPES:
        raw_idx = [idx for idx, r in stage1_by_idx.items()
                   if not r.get("_error") and r.get("relation_type") == rel]
        n_raw = len(raw_idx)

        survivors_idx = [idx for idx in raw_idx
                          if idx in stage1_5_by_idx and stage1_5_by_idx[idx]["stage1_5"]["passes_stage1_5"]]
        rejected_1_5_idx = [idx for idx in raw_idx
                             if idx in stage1_5_by_idx and not stage1_5_by_idx[idx]["stage1_5"]["passes_stage1_5"]]
        not_yet_1_5 = [idx for idx in raw_idx if idx not in stage1_5_by_idx]

        reject_reason_tally = Counter()
        for idx in rejected_1_5_idx:
            v = stage1_5_by_idx[idx]["stage1_5"]
            if not v["connective_grounded"]:
                reject_reason_tally["connective_not_grounded"] += 1
            if not v["satellite_grounded"]:
                reject_reason_tally["satellite_not_grounded"] += 1

        stage2_done_idx = [idx for idx in survivors_idx if idx in stage2_by_idx]
        not_yet_2 = [idx for idx in survivors_idx if idx not in stage2_by_idx]
        confirmed_idx = [idx for idx in stage2_done_idx if stage2_by_idx[idx]["stage2"].get("confirmed")]
        rejected_2_idx = [idx for idx in stage2_done_idx if idx not in confirmed_idx]
        stage2_error_idx = [idx for idx in stage2_done_idx if stage2_by_idx[idx]["stage2"].get("_error")]
        n_self_agg_disagreements = sum(
            1 for idx in stage2_done_idx
            if stage2_by_idx[idx]["stage2"].get("verdict_agrees_with_model") is False
        )

        check_trigger_tally = Counter()
        for idx in stage2_done_idx:
            checks = stage2_by_idx[idx]["stage2"].get("checks") or {}
            for check_key, check_val in checks.items():
                if check_val and check_val.get("applies"):
                    check_trigger_tally[check_key] += 1

        # Which check_4 wording produced each verdict -- matters because a
        # single log can now span both eras (see verification_classifier.py's
        # docstring on the 2026-08 promotion of the revised wording to
        # default). Tallied per relation so a report reader never has to
        # guess whether a given confirmed/rejected count is comparable
        # across pool_index ranges.
        prompt_version_tally = Counter(
            stage2_by_idx[idx]["stage2"].get("verification_prompt_version") or "unknown"
            for idx in stage2_done_idx
        )

        per_relation[rel] = {
            "stage1_raw_hits": n_raw,
            "stage1_5_not_yet_processed": len(not_yet_1_5),
            "stage1_5_survivors": len(survivors_idx),
            "stage1_5_rejected": len(rejected_1_5_idx),
            "stage1_5_rejection_rate_of_raw": (len(rejected_1_5_idx) / n_raw) if n_raw else None,
            "stage1_5_reject_reason_tally": dict(reject_reason_tally),
            "stage2_not_yet_processed": len(not_yet_2),
            "stage2_verified_total": len(stage2_done_idx),
            "stage2_confirmed": len(confirmed_idx),
            "stage2_rejected": len(rejected_2_idx),
            "stage2_errors_among_verified": len(stage2_error_idx),
            "stage2_confirmation_rate_of_survivors": (
                len(confirmed_idx) / len(stage2_done_idx) if stage2_done_idx else None
            ),
            "stage2_check_trigger_tally_among_all_verified": dict(check_trigger_tally),
            "stage2_verification_prompt_version_tally": dict(prompt_version_tally),
            "stage2_model_self_aggregation_disagreements": n_self_agg_disagreements,
            "overall_confirmed_rate_of_paragraphs_scored": (
                len(confirmed_idx) / n_scored if n_scored else None
            ),
            "overall_confirmed_rate_of_raw_hits": (len(confirmed_idx) / n_raw) if n_raw else None,
            "confirmed_pool_indices": confirmed_idx,
            "rejected_pool_indices": rejected_2_idx,
        }

    return {
        "n_paragraphs_screened_stage1": n_screened,
        "n_stage1_errors": n_stage1_errors,
        "n_scored_stage1": n_scored,
        "stage1_relation_type_counts": dict(stage1_counts),
        "per_relation": per_relation,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--offset", type=int, default=MIN_FRESH_POOL_INDEX,
                         help="start index into the classifier pool (must be >= 1803)")
    parser.add_argument("--n", type=int, default=DEFAULT_N)
    parser.add_argument("--stage1-model", type=str, default=None,
                         help="defaults to relation_classifier's own default (gpt-4o-mini)")
    parser.add_argument("--stage2-model", type=str, default=DEFAULT_STAGE2_MODEL)
    parser.add_argument("--max-workers", type=int, default=DEFAULT_MAX_WORKERS)
    parser.add_argument("--stage2-max-workers", type=int, default=DEFAULT_MAX_WORKERS)
    parser.add_argument("--stage1-log", type=str, default=STAGE1_LOG)
    parser.add_argument("--stage1-5-log", type=str, default=STAGE1_5_LOG)
    parser.add_argument("--stage2-log", type=str, default=STAGE2_LOG)
    parser.add_argument("--report-file", type=str, default=REPORT_JSON)
    parser.add_argument("--skip-stage1", action="store_true",
                         help="skip Stage 1 entirely and just (re-)run Stage 1.5 / Stage 2 "
                              "over whatever is already in --stage1-log")
    parser.add_argument("--retry-stage2-errors", action="store_true",
                         help="instead of the normal Stage 1/1.5/2 flow, re-verify ONLY the "
                              "existing --stage2-log entries that previously errored (e.g. "
                              "exhausted rate-limit retries) -- see retry_stage2_errors()")
    parser.add_argument("--retry-max-workers", type=int, default=3,
                         help="lower default parallelism for --retry-stage2-errors, since "
                              "errors are usually caused by rate-limiting in the first place")
    args = parser.parse_args()

    ensure_dirs()

    if args.retry_stage2_errors:
        retry_stage2_errors(args.stage2_log, args.stage2_model, args.retry_max_workers)
        funnel = compute_funnel(args.stage1_log, args.stage1_5_log, args.stage2_log)
        print("\n" + "#" * 90)
        print("FUNNEL AFTER STAGE-2 ERROR RETRY")
        print("#" * 90)
        print(json.dumps(funnel, indent=2))
        return

    stage1_elapsed = 0.0
    if not args.skip_stage1:
        stage1_elapsed = run_stage1(args.offset, args.n, args.stage1_model, args.max_workers, args.stage1_log)
    else:
        print("Skipping Stage 1 (--skip-stage1 passed).", flush=True)

    run_stage1_5(args.stage1_log, args.stage1_5_log)
    stage2_elapsed = run_stage2(args.stage1_5_log, args.stage2_log, args.stage2_model, args.stage2_max_workers)

    funnel = compute_funnel(args.stage1_log, args.stage1_5_log, args.stage2_log)

    print("\n" + "#" * 90)
    print("TWO-STAGE PIPELINE CUMULATIVE FUNNEL (over ALL paragraphs processed so far in these logs)")
    print("#" * 90)
    print(json.dumps(funnel, indent=2))

    report = {
        "stage1_log": args.stage1_log,
        "stage1_5_log": args.stage1_5_log,
        "stage2_log": args.stage2_log,
        "last_batch_offset": args.offset,
        "last_batch_n": args.n,
        "last_batch_stage1_elapsed_seconds": stage1_elapsed,
        "last_batch_stage2_elapsed_seconds": stage2_elapsed,
        "stage1_model": args.stage1_model or "gpt-4o-mini",
        "stage2_model": args.stage2_model,
        "funnel": funnel,
        "extrapolation_to_50_confirmed": {
            rel: extrapolate_to_target(
                funnel["per_relation"][rel]["stage2_confirmed"], funnel["n_scored_stage1"]
            )
            for rel in CANDIDATE_RELATION_TYPES
        },
    }

    # Preserve a previously-written "spot_check" section (added by a separate
    # human/AI-judgment pass over this same report file, same two-step
    # pattern as results/task5b_revised_precision_report.json) rather than
    # clobbering it if this script is re-run later to extend the batch.
    if os.path.exists(args.report_file):
        try:
            with open(args.report_file, encoding="utf-8") as fh:
                prior = json.load(fh)
            if "spot_check" in prior:
                report["spot_check"] = prior["spot_check"]
        except (json.JSONDecodeError, OSError):
            pass

    with open(args.report_file, "w", encoding="utf-8") as fh:
        json.dump(report, fh, indent=2, ensure_ascii=False)
    print(f"\nWrote {args.report_file}")
    print(f"Stage 1 log:   {args.stage1_log}")
    print(f"Stage 1.5 log: {args.stage1_5_log}")
    print(f"Stage 2 log:   {args.stage2_log}")


if __name__ == "__main__":
    main()
