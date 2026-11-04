"""own_baseline_track Experiment 3 (repair reliability) -- the SAME
six recovery/deferral arms as ../run_experiment_3.py (Task 8, run for
Chen et al.'s Propositionizer), run here on THIS PROJECT'S OWN minimal
prompted baseline chunker's own fixed 107-case severed-case set (every
governing paragraph run_own_baseline_experiment.py already scored
severed=True under its OWN Condition A: 16/75 Condition + 91/197
Concession, from logs/own_baseline_govern_log.jsonl -- see
own_baseline_exp3_dataset.py).

FRAMING (must be preserved wherever this script's numbers are cited --
see own_baseline_adapter.FRAMING_STATEMENT, reproduced below): this
chunker is "a minimal prompted baseline, included as one additional
tested system for the generality claim, not itself a claimed
contribution." It is one of four data points in a controlled comparison
-- never described as this project's own showcased pipeline.

BUNDLING-AUDIT STATUS (must be surfaced wherever this script's numbers
are cited): this eval set is the RAW Condition-A-severed set. Unlike
AtomicRAG's severed-case pool (bundling-corrected via
../atomicrag_track/audit_nucleus_bundling.py), this baseline's pool has
NOT yet had an equivalent nucleus-bundling audit applied -- separate,
pending follow-up work. See own_baseline_exp3_dataset.BUNDLING_AUDIT_NOTE.

REUSE, NOT REIMPLEMENTATION: every repair-arm and judge module below is
imported UNMODIFIED from ../ (factoidwiki_track/, the parent track
directory) -- contextual_retrieval_context.py, custom_fallback_paragraph.py,
disco_rag_paragraph_adapter.py, exp3_scoring_paragraph.py, and
severance_judge_paragraph.py -- plus server/components/risk_triage.py's
flag_claim, exactly as ../run_experiment_3.py already calls them. These
modules are chunker-agnostic (they operate on a source paragraph +
already-atomized claims/propositions + an elicited relation record,
nothing Propositionizer-specific), so running them against this
baseline's own severed-case pool is a parameterization -- a different
eval-set source and a different report path -- not a reimplementation.
This is the SAME cross-track-boundary-import precedent already
established and justified in this track by own_baseline_adapter.py
(importing atomization_conditions.py) and run_own_baseline_experiment.py
(importing severance_judge_paragraph.py / candidate_prefilter.py); this
script extends it to the four remaining Experiment-3 arm modules plus
exp3_scoring_paragraph.py, for the identical reason: measuring the
EXISTING, ALREADY-VALIDATED repair-arm code exactly as written, not a
reinvented copy of it.

TWO genuine adaptations were needed (beyond the eval-set source and
output path), both documented at their point of use below:
  1. A vocabulary bridge, documented in own_baseline_exp3_dataset.py's
     VOCABULARY TRANSLATION section: this track's own Condition-A output
     field is named `condition_a_claims` (matching
     atomization_conditions.py's own return shape), but the reused arm
     code expects a `condition_a_propositions` key on each eval record.
     own_baseline_exp3_dataset.derive_eval_set bridges that naming
     difference when building eval records; no other code changes were
     needed in the arm/judge modules themselves.
  2. `_parallel_map`/`DEFAULT_MAX_WORKERS` are duplicated locally below
     rather than imported from ../run_two_stage_pipeline.py the way
     ../run_experiment_3.py does -- see the NOTE at the import site for
     why (a real env_utils.py name collision through that module's own
     transitive import of ../download_data.py). This is boilerplate
     ThreadPoolExecutor orchestration, not arm/judge logic, and mirrors
     the identical duplication run_own_baseline_experiment.py's own
     `_parallel_map` already made in this same directory.

Six arms, all scored on the same 107 cases (identical design to
../run_experiment_3.py, see that module's docstring for full arm
descriptions -- summarized here):
  1. No elicitation: this baseline's existing Condition-A output + saved
     judge verdict, reused directly (zero regeneration). By construction,
     all 107/107 are severed here -- the baseline.
  2. Disco-RAG adapted (disco_rag_paragraph_adapter.py): released code
     (vendor/Disco-RAG, commit 0755104), gpt-4o-mini backbone substituted,
     retrieval bypassed, paragraph input. EXTERNAL system's method,
     adapted as documented in that module.
  3. Custom fallback (custom_fallback_paragraph.py): auto-rewrites this
     baseline's Condition-A claims using the saved relation-elicitation
     record, no human review. NOT Disco-RAG, NOT HCA.
  4. Contextual Retrieval context injection (contextual_retrieval_context.py):
     Anthropic's published technique, adapted to single-proposition
     discourse-relation recovery.
  5. Parent-segment fallback: return the full source PARAGRAPH instead of
     Condition-A's split claims. Ceiling/reality-check comparison, not a
     competitive arm.
  6. Flagged deferral: server/components/risk_triage.py's detectors,
     imported UNMODIFIED, run per Condition-A claim with segment_text =
     the source paragraph. Surfaces cases for human review; incorporates
     nothing automatically.

Scoring: identical methodology to ../run_experiment_3.py -- arms 2-5
judged with severance_judge_paragraph.py, classified into
correct / dangerous_failure / detectable_failure
(exp3_scoring_paragraph.py), with independent hedging/confidence-
calibration classification for arms 2-4.

Usage
-----
    venv/bin/python server/scripts/discourse_severance/factoidwiki_track/own_baseline_track/run_own_baseline_experiment_3.py
    venv/bin/python server/scripts/discourse_severance/factoidwiki_track/own_baseline_track/run_own_baseline_experiment_3.py --limit 5
"""

import argparse
import datetime
import json
import os
import sys
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Lock

OWN_BASELINE_TRACK_DIR = os.path.dirname(os.path.abspath(__file__))
FACTOIDWIKI_TRACK_DIR = os.path.dirname(OWN_BASELINE_TRACK_DIR)
DISCOURSE_SEVERANCE_DIR = os.path.dirname(FACTOIDWIKI_TRACK_DIR)
SERVER_DIR = os.path.dirname(os.path.dirname(DISCOURSE_SEVERANCE_DIR))

# Insertion order matters, same pattern (and same reason) as
# run_own_baseline_experiment.py's own sys.path setup: FACTOIDWIKI_TRACK_DIR
# first (so the reused arm/judge modules and their own self-locating
# imports resolve), then SERVER_DIR (for components.risk_triage), then
# OWN_BASELINE_TRACK_DIR re-inserted at index 0 last so THIS track's own
# env_utils.py / own_baseline_adapter.py / own_baseline_exp3_dataset.py win
# any name collision.
for _p in (FACTOIDWIKI_TRACK_DIR, SERVER_DIR):
    if _p not in sys.path:
        sys.path.insert(0, _p)
if OWN_BASELINE_TRACK_DIR in sys.path:
    sys.path.remove(OWN_BASELINE_TRACK_DIR)
sys.path.insert(0, OWN_BASELINE_TRACK_DIR)

from env_utils import RESULTS_DIR, ensure_dirs, load_server_env  # noqa: E402

load_server_env()

from components.risk_triage import flag_claim  # noqa: E402  (UNMODIFIED import, read-only)

import contextual_retrieval_context  # noqa: E402  (reused unmodified from ../)
import custom_fallback_paragraph  # noqa: E402  (reused unmodified from ../)
import disco_rag_paragraph_adapter  # noqa: E402  (reused unmodified from ../)
import exp3_scoring_paragraph  # noqa: E402  (reused unmodified from ../)
import severance_judge_paragraph  # noqa: E402  (reused unmodified from ../)

import own_baseline_exp3_dataset  # noqa: E402  (this track's own eval-set derivation)
from own_baseline_adapter import FRAMING_STATEMENT  # noqa: E402

# NOTE on _parallel_map/DEFAULT_MAX_WORKERS: ../run_experiment_3.py imports
# these from ../run_two_stage_pipeline.py. That module is NOT imported here
# -- it transitively imports ../download_data.py, which does
# `from env_utils import DATA_CACHE_DIR` expecting FACTOIDWIKI_TRACK_DIR's
# own env_utils.py. Because Python caches modules by bare name, and this
# script (like run_own_baseline_experiment.py before it) deliberately makes
# THIS track's own env_utils.py win the `import env_utils` name collision
# (see sys.path setup above -- own_baseline_track/env_utils.py lacks
# DATA_CACHE_DIR), importing run_two_stage_pipeline here would crash on
# that unrelated dependency. _parallel_map/DEFAULT_MAX_WORKERS are trivial
# orchestration boilerplate (a ThreadPoolExecutor-with-as_completed loop),
# not arm/judge logic -- duplicated locally below, exactly the same
# precedent already set by run_own_baseline_experiment.py's own local
# _parallel_map in this same directory ("duplicated locally per this
# track's self-contained-scripts convention").
DEFAULT_MAX_WORKERS = 8


def _parallel_map(func, items, max_workers=DEFAULT_MAX_WORKERS, label=""):
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
            if done % 10 == 0 or done == len(items):
                print(f"  {label} {done}/{len(items)}", flush=True)
    return results


REPORT_JSON = os.path.join(RESULTS_DIR, "own_baseline_exp3_report.json")

MODEL = "gpt-4o-mini"
TEMPERATURE = 0
SEED = 13

ARM_KEYS = {
    "arm_2_disco_rag": "arm 2 (Disco-RAG, adapted)",
    "arm_3_custom_fallback": "arm 3 (custom fallback)",
    "arm_4_contextual_retrieval": "arm 4 (Contextual Retrieval context injection)",
    "arm_5_parent_segment": "arm 5 (parent-segment fallback)",
}
# Confidence-calibration (hedging) classification runs for arms 2-4 only --
# arm 5 does not "fail" in the same sense (see ../run_experiment_3.py's
# module docstring / README, identical reasoning applies here).
CALIBRATION_ARM_KEYS = ["arm_2_disco_rag", "arm_3_custom_fallback", "arm_4_contextual_retrieval"]
FAILURE_BUCKETS = ("dangerous_failure", "detectable_failure")
ALL_BUCKETS = ("correct", "dangerous_failure", "detectable_failure",
               "failure_type_unclassified", "unscored")

HCA_STATEMENT = (
    "HCA (Fan et al. 2023) was not included as a comparison arm because "
    "neither its trained corpus nor model weights are released -- same "
    "reasoning as ../exp3_recovery_comparison/run_exp3.py's HCA_STATEMENT "
    "and ../run_experiment_3.py's HCA_STATEMENT."
)
FLAGGED_DEFERRAL_STATEMENT = (
    "Arm 6 runs server/components/risk_triage.py's detectors, imported "
    "UNMODIFIED, per Condition-A claim with segment_text = the source "
    "paragraph. It incorporates nothing automatically; it only surfaces "
    "cases for human review."
)
CHUNKER_FRAMING_STATEMENT = FRAMING_STATEMENT
BUNDLING_AUDIT_NOTE = own_baseline_exp3_dataset.BUNDLING_AUDIT_NOTE

CALL_COUNTER = Counter()
_COUNTER_LOCK = Lock()


def _count(key, n=1):
    with _COUNTER_LOCK:
        CALL_COUNTER[key] += n


# --- per-arm scoring (shared by arms 2, 3, 4, 5) -----------------------------
# Identical to ../run_experiment_3.py's _score_recovered -- see that
# module's docstring for the full rationale. Duplicated here (not
# imported) only because it is a thin orchestration function, not a
# reusable arm/judge module in its own right; every LLM-calling primitive
# it invokes (severance_judge_paragraph, exp3_scoring_paragraph) IS
# imported, not reimplemented.


def _score_recovered(paragraph, relation, propositions, model, run_calibration, counter_prefix):
    """Judge one arm's recovered propositions exactly the way Condition-A's
    claims were judged in this track's Experiment 1/2 (same
    severance_judge_paragraph.py methodology), then (only if severed)
    classify dangerous vs. detectable failure, then (only if
    run_calibration and severed) run the independent hedging/confidence-
    calibration classifier. Returns a dict with judge/bucket/failure_type/
    calibration fields, uniform across arms 2/3/4/5.

    `propositions is None` (the arm's own generation step failed) short-
    circuits straight to bucket="unscored" -- no judge call is made
    against a nonexistent output, and no failure is fabricated in place
    of a genuine generation error.
    """
    out = {"judge": None, "bucket": "unscored", "failure_type": None, "calibration": None}
    if propositions is None:
        return out

    judge = severance_judge_paragraph.llm_judge_paragraph_severance(
        paragraph, relation, propositions, model=model)
    _count(f"{counter_prefix}_judge_calls")
    out["judge"] = judge

    preserved = judge.get("preserved")
    if preserved is True:
        out["bucket"] = "correct"
        return out
    if preserved is not False:
        out["bucket"] = "unscored"  # judge call itself failed (preserved is None)
        return out

    # preserved is False -> classify dangerous vs. detectable failure.
    failure_type = exp3_scoring_paragraph.classify_failure_type(
        paragraph, relation, propositions, judge.get("reasoning", ""), model=model)
    _count(f"{counter_prefix}_failure_type_calls")
    out["failure_type"] = failure_type
    category = failure_type.get("category")
    out["bucket"] = category if category in exp3_scoring_paragraph.FAILURE_TYPE_CATEGORIES \
        else "failure_type_unclassified"

    if run_calibration:
        calibration = exp3_scoring_paragraph.classify_hedging_calibration(propositions, model=model)
        _count(f"{counter_prefix}_calibration_calls")
        out["calibration"] = calibration

    return out


# --- arm 6: flagged deferral (no LLM calls) ----------------------------------


def flags_for_case(case):
    """Arm 6: the EXISTING risk-triage detectors, unmodified, run per
    Condition-A claim with segment_text = the original source paragraph.
    No formalization exists in this experiment, so formal=proposition
    (self-identical), which makes detect_modal_mismatch a structural
    no-op; the arm's signal is the english-side per-claim detectors plus
    the two segment-level detectors. Mirrors ../run_experiment_3.py's
    flags_for_case exactly.
    """
    per_proposition = []
    for prop in case["condition_a_propositions"]:
        flags = flag_claim(prop, prop, formal_mode="english", segment_text=case["content"])
        per_proposition.append({"proposition": prop, "flags": flags})
    all_types = sorted({f["type"] for pp in per_proposition for f in pp["flags"]})
    segment_types = [t for t in all_types
                     if t in ("segment_nested_conditional", "segment_negation_scope")]
    claim_level_types = [t for t in all_types if t not in segment_types]
    return {
        "per_proposition_flags": per_proposition,
        "flag_types_fired": all_types,
        "segment_flag_fired": bool(segment_types),
        "segment_flag_types": segment_types,
        "claim_level_flag_fired": bool(claim_level_types),
        "claim_level_flag_types": claim_level_types,
        "any_flag_fired": bool(all_types),
    }


# --- per-case processing (all six arms) --------------------------------------


def process_case(case, disco_rag_recovery, model=None):
    """All six arms + scoring for one case. Arm errors are recorded loudly
    per case (error field), never swallowed into empty-but-plausible
    output -- same discipline as ../run_experiment_3.py's process_case.
    """
    paragraph = case["content"]
    relation = case["relation"]
    result = {
        "pool_index": case["pool_index"],
        "relation_type": case["relation_type"],
        "title": case["title"],
        "section": case["section"],
        "content": paragraph,
        "relation": relation,
    }

    # Arm 1 -- no elicitation: this baseline's saved Condition-A output +
    # saved verdict, reused directly (zero regeneration). By construction
    # of the eval set, every case is severed here.
    result["arm_1_no_elicitation"] = {
        "propositions": case["condition_a_propositions"],
        "judge": {
            "preserved": case["saved_severance_a"]["preserved"],
            "reasoning": case["saved_severance_a"]["reasoning"],
        },
        "note": "reused from logs/own_baseline_govern_log.jsonl, zero regeneration",
    }

    # Arm 2 -- Disco-RAG (adapted external system).
    arm2 = {"propositions": None, "error": None}
    try:
        recovered = disco_rag_recovery.recover(paragraph)
        _count("disco_rag_recovery_attempts")
        arm2.update(recovered)
    except Exception as exc:  # recorded loudly, run continues past one case
        arm2["error"] = f"{type(exc).__name__}: {exc}"
    arm2.update(_score_recovered(paragraph, relation, arm2.get("propositions"),
                                 model, run_calibration=True, counter_prefix="arm2"))
    result["arm_2_disco_rag"] = arm2

    # Arm 3 -- custom fallback (this project's own).
    rewritten, err = custom_fallback_paragraph.run_fallback_rewrite(
        case["condition_a_propositions"], relation, model=model)
    _count("custom_fallback_attempts")
    arm3 = {"propositions": rewritten, "error": err}
    arm3.update(_score_recovered(paragraph, relation, rewritten,
                                 model, run_calibration=True, counter_prefix="arm3"))
    result["arm_3_custom_fallback"] = arm3

    # Arm 4 -- Contextual Retrieval context injection.
    ctx = contextual_retrieval_context.run_contextual_retrieval(
        paragraph, relation, case["condition_a_propositions"], model=model)
    _count("contextual_retrieval_attempts")
    arm4 = dict(ctx)
    arm4["propositions"] = ctx.get("contextualized_propositions")
    arm4.update(_score_recovered(paragraph, relation, arm4["propositions"],
                                 model, run_calibration=True, counter_prefix="arm4"))
    result["arm_4_contextual_retrieval"] = arm4

    # Arm 5 -- parent-segment fallback: the full source paragraph in place
    # of Condition-A's split claims. Ceiling/reality-check arm, no
    # calibration (see module docstring).
    arm5 = {"propositions": [paragraph], "error": None}
    arm5.update(_score_recovered(paragraph, relation, arm5["propositions"],
                                 model, run_calibration=False, counter_prefix="arm5"))
    result["arm_5_parent_segment"] = arm5

    # Arm 6 -- flagged deferral (existing detectors, no LLM).
    result["arm_6_flagged_deferral"] = flags_for_case(case)

    return result


# --- summaries ----------------------------------------------------------------
# Identical to ../run_experiment_3.py's summary functions.


def summarize_arm(results, arm_key):
    bucket_counts = Counter(r[arm_key]["bucket"] for r in results)
    n = len(results)
    n_scored = sum(1 for r in results
                   if r[arm_key]["judge"] is not None and r[arm_key]["judge"].get("preserved") is not None)
    n_generation_failed = sum(1 for r in results if r[arm_key].get("propositions") is None)

    def _rate(bucket):
        return bucket_counts.get(bucket, 0) / n_scored if n_scored else None

    return {
        "n": n,
        "n_scored": n_scored,
        "n_generation_failed": n_generation_failed,
        "n_arm_errors": sum(1 for r in results if r[arm_key].get("error")),
        "bucket_counts": {b: bucket_counts.get(b, 0) for b in ALL_BUCKETS},
        "correct_rate": _rate("correct"),
        "dangerous_failure_rate": _rate("dangerous_failure"),
        "detectable_failure_rate": _rate("detectable_failure"),
        "failure_type_unclassified_rate": _rate("failure_type_unclassified"),
    }


def summarize_calibration(results, arm_key):
    failing = [r for r in results if r[arm_key]["bucket"] in FAILURE_BUCKETS]
    n = len(failing)

    def _hedge_count(subset, value):
        return sum(1 for r in subset if (r[arm_key].get("calibration") or {}).get("hedged") is value)

    by_bucket = {}
    for bucket in FAILURE_BUCKETS:
        subset = [r for r in failing if r[arm_key]["bucket"] == bucket]
        by_bucket[bucket] = {
            "n": len(subset),
            "n_hedged": _hedge_count(subset, True),
            "n_unhedged": _hedge_count(subset, False),
        }

    return {
        "n_failures_checked": n,
        "n_hedged": _hedge_count(failing, True),
        "n_unhedged": _hedge_count(failing, False),
        "n_calibration_call_failed": _hedge_count(failing, None),
        "hedged_rate_of_failures": _hedge_count(failing, True) / n if n else None,
        "by_bucket": by_bucket,
    }


def flag_summary(results):
    n = len(results)
    n_any = sum(1 for r in results if r["arm_6_flagged_deferral"]["any_flag_fired"])
    n_seg = sum(1 for r in results if r["arm_6_flagged_deferral"]["segment_flag_fired"])
    type_counts = Counter(
        t for r in results for t in r["arm_6_flagged_deferral"]["flag_types_fired"])
    return {
        "n_cases": n,
        "n_cases_any_flag": n_any,
        "n_cases_segment_flag": n_seg,
        "flag_type_case_counts": dict(sorted(type_counts.items())),
    }


def cross_tab(results, arm_key):
    """The key deferral question, per automated/context/parent-segment
    arm: of the cases this arm got dangerously wrong, how many would
    flagged deferral have surfaced? Plus the false-alarm side: flags
    fired where the arm was correct. Mirrors
    ../run_experiment_3.py's cross_tab exactly.
    """
    buckets = {b: [] for b in ALL_BUCKETS}
    for r in results:
        buckets[r[arm_key]["bucket"]].append(r)

    def _row(cases):
        return {
            "n": len(cases),
            "n_any_flag": sum(1 for r in cases if r["arm_6_flagged_deferral"]["any_flag_fired"]),
            "n_segment_flag": sum(1 for r in cases if r["arm_6_flagged_deferral"]["segment_flag_fired"]),
            "pool_indices": [r["pool_index"] for r in cases],
        }

    table = {k: _row(v) for k, v in buckets.items()}
    df = table["dangerous_failure"]
    table["coverage_of_dangerous_failure"] = {
        "any_flag": (f"{df['n_any_flag']}/{df['n']}", df["n_any_flag"] / df["n"] if df["n"] else None),
        "segment_flag": (f"{df['n_segment_flag']}/{df['n']}",
                         df["n_segment_flag"] / df["n"] if df["n"] else None),
    }
    corr = table["correct"]
    table["false_alarms_on_correct"] = {
        "any_flag": (f"{corr['n_any_flag']}/{corr['n']}",
                     corr["n_any_flag"] / corr["n"] if corr["n"] else None),
        "segment_flag": (f"{corr['n_segment_flag']}/{corr['n']}",
                         corr["n_segment_flag"] / corr["n"] if corr["n"] else None),
    }
    return table


def dangerous_failure_docs(results):
    """Full documentation for every dangerous-failure case, arms 2-5 --
    same style as ../run_experiment_3.py's dangerous_failure_docs."""
    docs = []
    for r in results:
        for arm_key in ARM_KEYS:
            arm = r[arm_key]
            if arm["bucket"] != "dangerous_failure":
                continue
            docs.append({
                "pool_index": r["pool_index"],
                "arm": ARM_KEYS[arm_key],
                "relation_type": r["relation_type"],
                "title": r["title"],
                "content": r["content"],
                "nucleus": r["relation"]["nucleus"],
                "satellite": r["relation"]["satellite"],
                "connective": r["relation"]["connective"],
                "arm_output_propositions": arm.get("propositions"),
                "why_severed_judge": (arm.get("judge") or {}).get("reasoning"),
                "why_dangerous_classifier": (arm.get("failure_type") or {}).get("reasoning"),
                "calibration_hedged": (arm.get("calibration") or {}).get("hedged")
                                      if arm_key in CALIBRATION_ARM_KEYS else "n/a (arm 5, not checked)",
                "flag_fired": r["arm_6_flagged_deferral"]["any_flag_fired"],
                "flag_types": r["arm_6_flagged_deferral"]["flag_types_fired"],
            })
    return docs


def build_summary(results, derivation):
    summary = {"eval_set": derivation, "n_cases": len(results)}
    for arm_key, label in ARM_KEYS.items():
        arm_summary = summarize_arm(results, arm_key)
        arm_summary["label"] = label
        if arm_key in CALIBRATION_ARM_KEYS:
            arm_summary["calibration"] = summarize_calibration(results, arm_key)
        summary[arm_key] = arm_summary
    summary["flag_summary"] = flag_summary(results)
    summary["cross_tabs"] = {arm_key: cross_tab(results, arm_key) for arm_key in ARM_KEYS}
    summary["dangerous_failure_documentation"] = dangerous_failure_docs(results)
    summary["llm_call_counts"] = dict(CALL_COUNTER)
    return summary


# --- reporting ----------------------------------------------------------------


def write_json_report(summary, results, derivation, execution_note, path=REPORT_JSON):
    report = {
        "run_date": datetime.date.today().isoformat(),
        "experiment": "own_baseline_factoidwiki_exp3_repair_reliability",
        "chunker": "own_minimal_prompted_baseline",
        "chunker_framing_statement": CHUNKER_FRAMING_STATEMENT,
        "bundling_audit_note": BUNDLING_AUDIT_NOTE,
        "execution_note": execution_note,
        "attribution": {
            "disco_rag": disco_rag_paragraph_adapter.BACKBONE_SUBSTITUTION_STATEMENT,
            "disco_rag_commit": disco_rag_paragraph_adapter.DISCO_RAG_COMMIT,
            "disco_rag_bypasses": disco_rag_paragraph_adapter.BYPASS_NOTES,
            "custom_fallback": custom_fallback_paragraph.CUSTOM_FALLBACK_STATEMENT,
            "contextual_retrieval": contextual_retrieval_context.CONTEXTUAL_RETRIEVAL_STATEMENT,
            "flagged_deferral": FLAGGED_DEFERRAL_STATEMENT,
            "hca": HCA_STATEMENT,
            "chunker_framing": CHUNKER_FRAMING_STATEMENT,
        },
        "reproducibility": {
            "model": MODEL,
            "temperature": TEMPERATURE,
            "seed": SEED,
            "severance_judge": "severance_judge_paragraph.llm_judge_paragraph_severance "
                               "(reused unmodified from ../, same methodology as "
                               "this track's Experiment 1/2)",
            "recovery_query_disco_rag": disco_rag_paragraph_adapter.RECOVERY_QUERY,
            "llm_call_counts": dict(CALL_COUNTER),
        },
        "eval_set_derivation": derivation,
        "summary": summary,
        "records": results,
    }
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(report, fh, indent=2, ensure_ascii=False)
    return path


# --- entry point --------------------------------------------------------------


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--limit", type=int, default=None,
                        help="process only the first N cases (smoke-testing only; "
                             "the full experiment is always all 107)")
    parser.add_argument("--model", type=str, default=MODEL)
    parser.add_argument("--max-workers", type=int, default=DEFAULT_MAX_WORKERS)
    parser.add_argument("--report-file", type=str, default=REPORT_JSON)
    args = parser.parse_args(argv)

    ensure_dirs()
    start = time.time()

    eval_records, derivation = own_baseline_exp3_dataset.derive_eval_set()
    print(f"Eval set derived: {len(eval_records)} cases "
          f"({derivation['n_condition_severed']} Condition + "
          f"{derivation['n_concession_severed']} Concession, both severed under "
          "this baseline's OWN Condition A in Experiment 1/2). "
          f"NOTE: {CHUNKER_FRAMING_STATEMENT}")
    print(f"Bundling-audit status: {BUNDLING_AUDIT_NOTE}")

    if args.limit is not None:
        eval_records = eval_records[:args.limit]
        print(f"--limit given: processing only the first {len(eval_records)} cases "
              "(smoke-test mode, NOT the full experiment).")

    disco_rag_recovery = disco_rag_paragraph_adapter.DiscoRagParagraphRecovery(
        backbone=disco_rag_paragraph_adapter.ChatOpenAIBackbone(model_name=args.model))

    print(f"Processing {len(eval_records)} cases x 6 arms "
          f"(model={args.model}, temperature={TEMPERATURE}, seed={SEED})...")
    results = _parallel_map(
        lambda case: process_case(case, disco_rag_recovery, model=args.model),
        eval_records, max_workers=args.max_workers, label="own-baseline-exp3")

    summary = build_summary(results, derivation)

    fully_blocked = all(summary[arm_key]["n_scored"] == 0 for arm_key in ARM_KEYS)
    execution_note = (
        "completed" if not fully_blocked else
        "BLOCKED: every LLM-dependent arm (2-5) returned zero successfully-"
        "judged cases despite attempting generation -- consistent with an "
        "account-level API blocker (e.g. OPENAI_API_KEY quota/credits "
        "exhausted), not a per-case content issue. Arm 1 (reused from "
        "Experiment 1/2) and arm 6 (rule-based, no LLM calls) are "
        "unaffected and reflect real results. Re-run this exact script "
        "once the blocker is resolved."
    )

    json_path = write_json_report(summary, results, derivation, execution_note,
                                  path=args.report_file)

    elapsed = time.time() - start
    print(f"\nDone in {elapsed:.0f}s. LLM calls attempted: {dict(CALL_COUNTER)}")
    print(f"Execution note: {execution_note}")
    print(f"Wrote {json_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
