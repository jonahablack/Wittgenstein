"""One-off repair pass for AtomicRAG Experiment 3: retry arm 2 (Disco-RAG)
for the cases that failed with RateLimitError during the first full run
(results/atomicrag_exp3_report.json, run_date 2026-08-15).

WHAT HAPPENED (see logs/atomicrag_exp3_full_run.log): with --max-workers 8,
all six arms' calls (arm 2's 3-stage Disco-RAG pipeline, arm 3/4's single
calls, arm 4/5's judge/failure-type/calibration calls) ran concurrently
against the SAME org-wide gpt-4o-mini TPM budget (200,000 tokens/min).
71/124 cases (57%) hit `RateLimitError: ... tokens per min (TPM) ...
Limit 200000` specifically in arm 2 -- arm 3/4/5 had only 0-3 failures
each because their calls go through server/api_call.py's
`generate_response`, which has its own manual retry-with-backoff loop
(3 attempts, exponential + jitter). Arm 2's `ChatOpenAIBackbone`
(disco_rag_paragraph_adapter.py) instead relies solely on the OpenAI
SDK's client-level `max_retries=3`, which was not enough backoff to
survive sustained, aggregate (all-arms) TPM exhaustion under 8-way
concurrency for a 3-real-LLM-call-per-case pipeline (RST parse -> plan ->
generate).

FIX, per the task brief's explicit instruction ("if you hit rate limits,
back off concurrency and retry rather than failing silently"): back off
(max_workers=3 here, well under the earlier 8, AND now running with no
other arm's calls in flight at all, since the main run already finished)
plus an explicit retry-with-backoff wrapper around `recover()` (5
attempts, linearly increasing backoff) around the SAME
`DiscoRagParagraphRecovery.recover` and `_score_recovered` used by the
main run -- imported from run_experiment_3_atomicrag.py, not
reimplemented. Reprocesses ONLY the 71 previously-failed cases; every
other case/arm's already-successful output is left untouched, and no
case is re-billed twice for the same output.

Usage:
    venv/bin/python server/scripts/discourse_severance/factoidwiki_track/atomicrag_track/retry_arm2_rate_limited_cases.py
"""

import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Lock

ATOMICRAG_TRACK_DIR = os.path.dirname(os.path.abspath(__file__))
if ATOMICRAG_TRACK_DIR not in sys.path:
    sys.path.insert(0, ATOMICRAG_TRACK_DIR)

import run_experiment_3_atomicrag as exp3  # noqa: E402

REPORT_PATH = exp3.REPORT_JSON
RETRY_MAX_WORKERS = 3
MAX_ATTEMPTS = 5
BACKOFF_BASE_SECONDS = 6.0

_PRINT_LOCK = Lock()


def recover_with_retry(disco_rag_recovery, paragraph, pool_index):
    last_exc = None
    for attempt in range(MAX_ATTEMPTS):
        try:
            return disco_rag_recovery.recover(paragraph), None
        except Exception as exc:  # noqa: BLE001 -- recorded loudly below, never swallowed
            last_exc = exc
            wait = BACKOFF_BASE_SECONDS * (attempt + 1)
            with _PRINT_LOCK:
                print(f"  pool_index {pool_index}: attempt {attempt + 1}/{MAX_ATTEMPTS} failed "
                      f"({type(exc).__name__}: {exc}); backing off {wait:.0f}s", flush=True)
            time.sleep(wait)
    return None, f"{type(last_exc).__name__}: {last_exc}"


def retry_one(record, disco_rag_recovery):
    paragraph = record["content"]
    relation = record["relation"]
    recovered, err = recover_with_retry(disco_rag_recovery, paragraph, record["pool_index"])
    arm2 = {"propositions": None, "error": err}
    if recovered is not None:
        exp3._count("disco_rag_recovery_attempts")
        arm2.update(recovered)
    arm2.update(exp3._score_recovered(paragraph, relation, arm2.get("propositions"),
                                      exp3.MODEL, run_calibration=True, counter_prefix="arm2"))
    with _PRINT_LOCK:
        status = "OK" if arm2.get("error") is None else f"STILL FAILING: {arm2['error']}"
        print(f"pool_index {record['pool_index']}: {status}", flush=True)
    return record["pool_index"], arm2


def main():
    with open(REPORT_PATH, encoding="utf-8") as fh:
        report = json.load(fh)

    records = report["records"]
    by_pool_index = {r["pool_index"]: r for r in records}
    failed = [r for r in records if r["arm_2_disco_rag"].get("error")]
    print(f"Found {len(failed)} cases with arm_2_disco_rag errors to retry "
          f"(max_workers={RETRY_MAX_WORKERS}, up to {MAX_ATTEMPTS} attempts each).")
    if not failed:
        print("Nothing to do.")
        return 0

    disco_rag_recovery = exp3.disco_rag_paragraph_adapter.DiscoRagParagraphRecovery(
        backbone=exp3.disco_rag_paragraph_adapter.ChatOpenAIBackbone(model_name=exp3.MODEL))

    patched = {}
    with ThreadPoolExecutor(max_workers=RETRY_MAX_WORKERS) as executor:
        futures = {executor.submit(retry_one, r, disco_rag_recovery): r for r in failed}
        for future in as_completed(futures):
            pool_index, arm2 = future.result()
            patched[pool_index] = arm2

    still_failed = [pi for pi, arm2 in patched.items() if arm2.get("error")]
    print(f"\nRetry pass done. Recovered: {len(patched) - len(still_failed)}/{len(patched)}. "
          f"Still failing: {still_failed}")

    for pool_index, arm2 in patched.items():
        by_pool_index[pool_index]["arm_2_disco_rag"] = arm2

    # Recompute summary from the patched records (bucket counts, cross-tabs,
    # dangerous-failure docs, etc. all depend on arm_2_disco_rag, so must be
    # regenerated, not hand-patched).
    derivation = report["eval_set_derivation"]
    summary = exp3.build_summary(records, derivation)

    # Merge call counts: the retry pass's CALL_COUNTER (fresh at import,
    # only incremented by THIS script's calls) is ADDED to the original
    # run's counts -- these are genuinely new, real calls made against
    # cases that had ZERO arm2 judge/failure-type/calibration calls
    # counted the first time (an errored recover() short-circuits
    # _score_recovered before any counter increments), so nothing is
    # double-counted.
    original_counts = report["summary"]["llm_call_counts"]
    retry_counts = dict(exp3.CALL_COUNTER)
    merged_counts = dict(original_counts)
    for k, v in retry_counts.items():
        merged_counts[k] = merged_counts.get(k, 0) + v
    summary["llm_call_counts"] = merged_counts

    report["summary"] = summary
    report["records"] = records
    report["reproducibility"]["llm_call_counts"] = merged_counts
    report["repair_note"] = (
        f"2026-08-15 repair pass (retry_arm2_rate_limited_cases.py): the initial "
        f"full run (--max-workers 8) hit RateLimitError (org-wide gpt-4o-mini TPM "
        f"cap, 200000 tokens/min) on {len(failed)}/124 arm-2 (Disco-RAG) cases -- "
        "see logs/atomicrag_exp3_full_run.log. Retried at --max-workers "
        f"{RETRY_MAX_WORKERS} with an explicit retry-with-backoff wrapper (up to "
        f"{MAX_ATTEMPTS} attempts each), run separately after the main pass "
        "finished (no other arm's calls in flight). "
        f"{len(patched) - len(still_failed)}/{len(failed)} recovered; "
        f"{len(still_failed)} still failing after retries: {still_failed}. "
        "No other arm or case was re-run or re-billed; only arm_2_disco_rag for "
        "these specific pool_indices was replaced."
    )

    with open(REPORT_PATH, "w", encoding="utf-8") as fh:
        json.dump(report, fh, indent=2, ensure_ascii=False)

    print(f"\nWrote patched report to {REPORT_PATH}")
    print(f"arm_2_disco_rag now: n_scored={summary['arm_2_disco_rag']['n_scored']}, "
          f"n_arm_errors={summary['arm_2_disco_rag']['n_arm_errors']}, "
          f"bucket_counts={summary['arm_2_disco_rag']['bucket_counts']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
