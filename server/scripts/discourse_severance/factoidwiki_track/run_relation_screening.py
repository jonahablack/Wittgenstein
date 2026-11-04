"""Task 5 orchestration: screen real Wikipedia-prose paragraphs for
Condition/Concession/Elaboration/None using relation_classifier.py's
zero-shot GPT-4o-mini classifier, and report hit rates + extrapolation
to a 50-instance target per category.

Design supports incremental screening: each invocation screens
pool[offset : offset+n] (from download_data.get_classifier_pool(), which
is already disjoint from the paragraphs used in Tasks 3/4) and APPENDS
results to a jsonl log keyed by pool index, so re-running with a fresh
--offset/--n extends the total screened sample without re-classifying or
duplicating any paragraph. The report is always computed over the FULL
accumulated log, not just the latest batch, so "screen more if it's
cheap/fast" is just another invocation with a bumped --offset.

Usage:
    venv/bin/python server/scripts/discourse_severance/factoidwiki_track/run_relation_screening.py --n 400
    venv/bin/python server/scripts/discourse_severance/factoidwiki_track/run_relation_screening.py --offset 400 --n 200   # extend

    # Task 5b (revised prompt, fresh disjoint batch): point at independent
    # log/report files with --log-file/--report-file so a differently-
    # prompted pilot never mixes into the original 903-paragraph log/report:
    venv/bin/python server/scripts/discourse_severance/factoidwiki_track/run_relation_screening.py \\
        --offset 903 --n 900 \\
        --log-file server/scripts/discourse_severance/factoidwiki_track/logs/task5b_screening_log.jsonl \\
        --report-file server/scripts/discourse_severance/factoidwiki_track/results/task5b_revised_precision_report.json
"""

import argparse
import json
import os
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed

from download_data import get_classifier_pool, shuffled_records
from env_utils import LOGS_DIR, RESULTS_DIR, ensure_dirs, load_server_env
from relation_classifier import RELATION_TYPES, classify_paragraph

load_server_env()

SCREENING_LOG = os.path.join(LOGS_DIR, "task5_screening_log.jsonl")
REPORT_JSON = os.path.join(RESULTS_DIR, "task5_relation_screening_report.json")

DEFAULT_N = 400
DEFAULT_MAX_WORKERS = 8
TARGET_PER_CATEGORY = 50


def _parallel_map(func, items, max_workers=DEFAULT_MAX_WORKERS):
    """Same ThreadPoolExecutor-with-as_completed pattern as
    ../run_experiments.py's _parallel_map, duplicated locally rather than
    imported -- see env_utils.py's docstring for why this track keeps
    itself self-contained instead of importing siblings.
    """
    results = [None] * len(items)
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_idx = {executor.submit(func, item): i for i, item in enumerate(items)}
        done = 0
        for future in as_completed(future_to_idx):
            i = future_to_idx[future]
            results[i] = future.result()
            done += 1
            if done % 50 == 0:
                print(f"  screened {done}/{len(items)}", flush=True)
    return results


def screen_batch(offset, n, model=None, max_workers=DEFAULT_MAX_WORKERS, log_file=None):
    ensure_dirs()
    log_file = log_file or SCREENING_LOG
    pool = get_classifier_pool(shuffled_records())
    if offset + n > len(pool):
        raise ValueError(
            f"FATAL: offset+n ({offset + n}) exceeds classifier pool size ({len(pool)})"
        )
    batch = pool[offset:offset + n]
    print(f"Screening paragraphs [{offset}:{offset + n}] ({len(batch)} paragraphs), "
          f"model={model or 'gpt-4o-mini (default)'}, max_workers={max_workers}, "
          f"log_file={log_file} ...",
          flush=True)

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
            "elapsed_seconds": elapsed,
            **relation,
        }

    items = list(enumerate(batch, start=offset))
    t0 = time.time()
    results = _parallel_map(_do, items, max_workers=max_workers)
    elapsed_total = time.time() - t0

    with open(log_file, "a", encoding="utf-8") as fh:
        for rec in results:
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")

    n_errors = sum(1 for r in results if r.get("_error"))
    print(f"Batch done: {len(results)} paragraphs in {elapsed_total:.1f}s "
          f"({elapsed_total / len(results):.2f}s/call avg wall-clock, {max_workers}-way "
          f"parallel), {n_errors} errors.", flush=True)
    return results, elapsed_total


def load_full_log(log_file=None):
    log_file = log_file or SCREENING_LOG
    if not os.path.exists(log_file):
        return []
    records = []
    with open(log_file, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    # De-dup by pool_index (keeps the LAST write for a given index) in
    # case a re-run ever overlapped a previous batch's range.
    by_index = {r["pool_index"]: r for r in records}
    return [by_index[k] for k in sorted(by_index)]


def rule_of_three_upper_bound(n):
    """For 0 observed events in n trials, the ~95% upper confidence bound
    on the true rate is approximately 3/n ("rule of three"). Used only to
    give a defensible statement for a zero-hit category instead of a
    divide-by-zero or an unsupported-sounding guess.
    """
    return 3.0 / n if n else None


def extrapolate_to_target(hit_count, n_screened, target=TARGET_PER_CATEGORY):
    if n_screened == 0:
        return None
    rate = hit_count / n_screened
    if hit_count == 0:
        upper_rate = rule_of_three_upper_bound(n_screened)
        return {
            "observed_rate": 0.0,
            "n_needed_point_estimate": None,
            "note": (
                f"0 hits in {n_screened} screened -- the point-estimate rate is 0, so a "
                "point extrapolation is undefined. Rule-of-three 95% upper confidence "
                f"bound on the true rate is ~{upper_rate:.4%}, implying screening would "
                f"need to exceed roughly {target / upper_rate:,.0f} paragraphs to "
                f"plausibly reach {target}+ hits EVEN AT THAT OPTIMISTIC UPPER BOUND; "
                "the true number could be far higher if the real rate is lower still."
            ),
        }
    return {
        "observed_rate": rate,
        "n_needed_point_estimate": target / rate,
        "note": f"At the observed rate ({hit_count}/{n_screened} = {rate:.2%}), reaching "
                f"{target}+ hits needs ~{target / rate:,.0f} paragraphs screened "
                "(point estimate; real-world variance will make this noisy at low counts).",
    }


def summarize(records, target=TARGET_PER_CATEGORY):
    n = len(records)
    counts = Counter(r["relation_type"] for r in records if not r.get("_error"))
    n_errors = sum(1 for r in records if r.get("_error"))
    n_scored = n - n_errors

    per_type = {}
    for rt in RELATION_TYPES:
        c = counts.get(rt, 0)
        per_type[rt] = {
            "count": c,
            "pct_of_scored": (c / n_scored) if n_scored else None,
            "extrapolation_to_target": extrapolate_to_target(c, n_scored, target=target),
        }

    return {
        "n_screened": n,
        "n_scored": n_scored,
        "n_errors": n_errors,
        "counts": dict(counts),
        "per_type": per_type,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--offset", type=int, default=0,
                         help="start index into the classifier pool (use to extend a prior batch)")
    parser.add_argument("--n", type=int, default=DEFAULT_N)
    parser.add_argument("--model", type=str, default=None)
    parser.add_argument("--max-workers", type=int, default=DEFAULT_MAX_WORKERS)
    parser.add_argument("--log-file", type=str, default=SCREENING_LOG,
                         help="jsonl log path to append to / accumulate over. Override "
                              "(together with --report-file) to run an independent batch -- "
                              "e.g. a revised-prompt pilot -- without mixing its results into "
                              "the original log/report.")
    parser.add_argument("--report-file", type=str, default=REPORT_JSON,
                         help="report json path to write, paired with --log-file")
    args = parser.parse_args()

    _, batch_elapsed = screen_batch(
        args.offset, args.n, model=args.model, max_workers=args.max_workers,
        log_file=args.log_file,
    )

    all_records = load_full_log(args.log_file)
    summary = summarize(all_records)

    print("\n" + "#" * 90)
    print(f"CUMULATIVE SUMMARY (over all {summary['n_screened']} paragraphs screened so far "
          f"in {args.log_file}, across this run + any prior batches in that log)")
    print("#" * 90)
    print(json.dumps(summary, indent=2))

    with open(args.report_file, "w", encoding="utf-8") as fh:
        json.dump({
            "log_file": args.log_file,
            "last_batch_offset": args.offset,
            "last_batch_n": args.n,
            "last_batch_elapsed_seconds": batch_elapsed,
            "summary": summary,
        }, fh, indent=2, ensure_ascii=False)
    print(f"\nWrote {args.report_file}")
    print(f"Full per-paragraph log: {args.log_file}")


if __name__ == "__main__":
    main()
