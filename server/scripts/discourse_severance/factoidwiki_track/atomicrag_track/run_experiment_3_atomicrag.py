"""AtomicRAG-track analog of ../run_experiment_3.py: the SAME six
repair/deferral arms, run on AtomicRAG's own fixed 124-case severed-case
pool (every governing paragraph run_atomicrag_experiment.py already
scored severed=True under AtomicRAG's standard OpenIE atomization: 29/75
Condition + 95/197 Concession, from logs/atomicrag_govern_log.jsonl --
see exp3_dataset_atomicrag.py) instead of the Propositionizer's 109-case
pool. This is a PARAMETERIZATION of ../run_experiment_3.py, not a
reimplementation: arms 2-6's actual repair/scoring/flagging logic is
IMPORTED UNMODIFIED from the same five chunker-agnostic modules
../run_experiment_3.py already calls
(disco_rag_paragraph_adapter.py, custom_fallback_paragraph.py,
contextual_retrieval_context.py, severance_judge_paragraph.py,
exp3_scoring_paragraph.py, and server/components/risk_triage.flag_claim)
-- every one of those operates on a source paragraph + a set of atomized
propositions, with no assumption baked in about which chunker produced
them. The only real differences from ../run_experiment_3.py are (1) the
eval-set source (exp3_dataset_atomicrag.py, this track's own
logs/atomicrag_govern_log.jsonl) and (2) arm 1's baseline field names
(`atomicrag_propositions` / `severance_atomicrag` in place of
`condition_a_propositions` / `severance_a`) -- see exp3_dataset_atomicrag.py's
module docstring for why no Condition-B analog exists for this chunker.

CHUNKER-SPECIFIC ADAPTATION CHECK (per the task brief -- documented,
none found needed beyond field renaming): AtomicRAG's own knowledge
fragments are coarser than the Propositionizer's (avg. 3.48
propositions/paragraph across this eval set's 124 severed cases, vs.
Propositionizer's 9.06 avg. over its whole sample; range here is 1-7,
i.e. some cases hand arm 3/4/6 only ONE proposition to work with). Read
every reused module's logic before running the full sample specifically
for a hidden assumption of "many" propositions:
  - custom_fallback_paragraph.run_fallback_rewrite: takes a propositions
    list of any length; the rewrite prompt lists them with a bulleted
    "- {p}" block that renders correctly for length 1 (single bullet).
    No hidden assumption found.
  - contextual_retrieval_context.select_target_proposition: with exactly
    one proposition, `target_idx=0` trivially (only candidate). No
    special-casing needed; already handled by the existing "falls back to
    index 0" logic (see that function's own docstring).
  - severance_judge_paragraph / exp3_scoring_paragraph: build a
    `props_block` the same "- {p}" way regardless of count.
  - flags_for_case (arm 6, below): iterates `for prop in propositions`,
    count-agnostic.
  - disco_rag_paragraph_adapter / arm 5 (parent-segment fallback): both
    operate on the raw source PARAGRAPH, never on the chunker's
    propositions at all, so AtomicRAG's granularity is structurally
    irrelevant to these two arms.
No module required a code change; a --limit 6 pilot (see
results/atomicrag_exp3_pilot_report.json) additionally confirmed no
degenerate output (empty proposition lists, judge/parse failures, or
truncated rewrites) before the full 124-case run.

Six arms, all scored on the same 124 cases (bucket vocabulary, scoring
methodology, and cross-tab design all IDENTICAL to
../run_experiment_3.py -- see that module's docstring for the full
per-arm description; only arm 1 and arm 2's provenance differ here):
  1. No elicitation: AtomicRAG's existing standard-atomization output +
     saved judge verdict from run_atomicrag_experiment.py, reused
     directly (zero regeneration). By construction, all 124/124 are
     severed here -- the baseline.
  2. Disco-RAG adapted (disco_rag_paragraph_adapter.py): released code
     (vendor/Disco-RAG, commit 0755104), gpt-4o-mini backbone
     substituted, retrieval bypassed, operates on the source PARAGRAPH
     directly (never on AtomicRAG's propositions) -- EXTERNAL system's
     method, adapted as documented, IDENTICAL invocation to the
     Propositionizer-track run.
  3. Custom fallback (custom_fallback_paragraph.py): auto-rewrites
     AtomicRAG's knowledge fragments using the saved relation-elicitation
     record, no human review. NOT Disco-RAG, NOT HCA.
  4. Contextual Retrieval context injection (contextual_retrieval_context.py):
     Anthropic's published technique, adapted to single-proposition
     discourse-relation recovery.
  5. Parent-segment fallback: return the full source PARAGRAPH instead of
     AtomicRAG's fragments. Ceiling/reality-check comparison, not a
     competitive arm.
  6. Flagged deferral: server/components/risk_triage.py's detectors,
     imported UNMODIFIED, run per AtomicRAG proposition with
     segment_text = the source paragraph. Surfaces cases for human
     review; incorporates nothing automatically.

Usage
-----
    venv/bin/python server/scripts/discourse_severance/factoidwiki_track/atomicrag_track/run_experiment_3_atomicrag.py
    venv/bin/python server/scripts/discourse_severance/factoidwiki_track/atomicrag_track/run_experiment_3_atomicrag.py --limit 6
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

ATOMICRAG_TRACK_DIR = os.path.dirname(os.path.abspath(__file__))
FACTOIDWIKI_TRACK_DIR = os.path.dirname(ATOMICRAG_TRACK_DIR)
DISCOURSE_SEVERANCE_DIR = os.path.dirname(FACTOIDWIKI_TRACK_DIR)
SERVER_DIR = os.path.dirname(os.path.dirname(DISCOURSE_SEVERANCE_DIR))

for _p in (ATOMICRAG_TRACK_DIR, FACTOIDWIKI_TRACK_DIR, SERVER_DIR):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from env_utils import load_server_env  # noqa: E402  (parent track's env loader, reused -- see run_atomicrag_experiment.py's precedent)

load_server_env()

from components.risk_triage import flag_claim  # noqa: E402  (UNMODIFIED import, read-only)

import atomicrag_openie_adapter  # noqa: E402
import contextual_retrieval_context  # noqa: E402
import custom_fallback_paragraph  # noqa: E402
import disco_rag_paragraph_adapter  # noqa: E402
import exp3_dataset_atomicrag  # noqa: E402
import exp3_scoring_paragraph  # noqa: E402
import severance_judge_paragraph  # noqa: E402

LOGS_DIR = os.path.join(ATOMICRAG_TRACK_DIR, "logs")
RESULTS_DIR = os.path.join(ATOMICRAG_TRACK_DIR, "results")
REPORT_JSON = os.path.join(RESULTS_DIR, "atomicrag_exp3_report.json")

MODEL = "gpt-4o-mini"
TEMPERATURE = 0
SEED = 13
DEFAULT_MAX_WORKERS = 8  # matches this project's established convention (see ../run_two_stage_pipeline.py / run_atomicrag_experiment.py's JUDGE_MAX_WORKERS)

ARM_KEYS = {
    "arm_2_disco_rag": "arm 2 (Disco-RAG, adapted)",
    "arm_3_custom_fallback": "arm 3 (custom fallback)",
    "arm_4_contextual_retrieval": "arm 4 (Contextual Retrieval context injection)",
    "arm_5_parent_segment": "arm 5 (parent-segment fallback)",
}
# Confidence-calibration (hedging) classification runs for arms 2-4 only --
# arm 5 does not "fail" in the same sense (see ../run_experiment_3.py's docstring).
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
    "UNMODIFIED, per AtomicRAG proposition with segment_text = the "
    "source paragraph. It incorporates nothing automatically; it only "
    "surfaces cases for human review."
)

CALL_COUNTER = Counter()
_COUNTER_LOCK = Lock()


def _count(key, n=1):
    with _COUNTER_LOCK:
        CALL_COUNTER[key] += n


def _parallel_map(func, items, max_workers=DEFAULT_MAX_WORKERS, label=""):
    """Same ThreadPoolExecutor-with-as_completed pattern duplicated across
    this project's scripts (see ../run_two_stage_pipeline.py /
    run_atomicrag_experiment.py) -- duplicated locally here too rather
    than importing run_two_stage_pipeline just for this helper, matching
    run_atomicrag_experiment.py's own precedent for this track.
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


# --- per-arm scoring (shared by arms 2, 3, 4, 5) -----------------------------
# IDENTICAL to ../run_experiment_3.py's _score_recovered -- reused
# verbatim (not just "same design"): takes paragraph/relation/propositions
# generically, no chunker-specific assumption.


def _score_recovered(paragraph, relation, propositions, model, run_calibration, counter_prefix):
    """Judge one arm's recovered propositions exactly the way arm 1's
    propositions were judged by run_atomicrag_experiment.py (same
    severance-judge methodology, severance_judge_paragraph.py), then
    (only if severed) classify dangerous vs. detectable failure, then
    (only if run_calibration and severed) run the independent
    hedging/confidence-calibration classifier. Returns a dict with
    judge/bucket/failure_type/calibration fields, uniform across arms
    2/3/4/5 so summaries can treat them identically.

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
    AtomicRAG proposition with segment_text = the original source
    paragraph. No formalization exists in this experiment, so
    formal=proposition (self-identical), which makes detect_modal_mismatch
    a structural no-op; the arm's signal is the english-side per-
    proposition detectors plus the two segment-level detectors. Mirrors
    ../run_experiment_3.py's flags_for_case exactly, with
    `condition_a_propositions` renamed to `atomicrag_propositions`.
    """
    per_proposition = []
    for prop in case["atomicrag_propositions"]:
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

    # Arm 1 -- no elicitation: saved AtomicRAG output + saved verdict,
    # reused directly (zero regeneration). By construction of the eval
    # set, every case is severed here.
    result["arm_1_no_elicitation"] = {
        "propositions": case["atomicrag_propositions"],
        "judge": {
            "preserved": case["saved_severance_atomicrag"]["preserved"],
            "reasoning": case["saved_severance_atomicrag"]["reasoning"],
        },
        "note": "reused from logs/atomicrag_govern_log.jsonl, zero regeneration",
    }

    # Arm 2 -- Disco-RAG (adapted external system). Operates on the raw
    # source paragraph only -- never sees AtomicRAG's propositions, so
    # this call is byte-for-byte identical in shape to the
    # Propositionizer-track invocation.
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

    # Arm 3 -- custom fallback (this project's own), operating on
    # AtomicRAG's knowledge fragments.
    rewritten, err = custom_fallback_paragraph.run_fallback_rewrite(
        case["atomicrag_propositions"], relation, model=model)
    _count("custom_fallback_attempts")
    arm3 = {"propositions": rewritten, "error": err}
    arm3.update(_score_recovered(paragraph, relation, rewritten,
                                 model, run_calibration=True, counter_prefix="arm3"))
    result["arm_3_custom_fallback"] = arm3

    # Arm 4 -- Contextual Retrieval context injection, targeting one of
    # AtomicRAG's knowledge fragments.
    ctx = contextual_retrieval_context.run_contextual_retrieval(
        paragraph, relation, case["atomicrag_propositions"], model=model)
    _count("contextual_retrieval_attempts")
    arm4 = dict(ctx)
    arm4["propositions"] = ctx.get("contextualized_propositions")
    arm4.update(_score_recovered(paragraph, relation, arm4["propositions"],
                                 model, run_calibration=True, counter_prefix="arm4"))
    result["arm_4_contextual_retrieval"] = arm4

    # Arm 5 -- parent-segment fallback: the full source paragraph in place
    # of AtomicRAG's fragments. Ceiling/reality-check arm, no calibration.
    arm5 = {"propositions": [paragraph], "error": None}
    arm5.update(_score_recovered(paragraph, relation, arm5["propositions"],
                                 model, run_calibration=False, counter_prefix="arm5"))
    result["arm_5_parent_segment"] = arm5

    # Arm 6 -- flagged deferral (existing detectors, no LLM).
    result["arm_6_flagged_deferral"] = flags_for_case(case)

    return result


# --- summaries ----------------------------------------------------------------
# IDENTICAL to ../run_experiment_3.py's summarize_arm / summarize_calibration /
# flag_summary / cross_tab / dangerous_failure_docs / build_summary -- the
# bucket vocabulary, cross-tab design, and documentation shape are all
# chunker-agnostic, so these are reused verbatim (copied, not imported,
# per this track's established precedent of duplicating small orchestration
# helpers rather than reaching back into ../run_experiment_3.py, which is
# itself an entry-point script, not a library module).


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
    fired where the arm was correct. Mirrors ../run_experiment_3.py's
    cross_tab exactly.
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
        "experiment": "atomicrag_exp3_repair_reliability",
        "execution_note": execution_note,
        "attribution": {
            "atomicrag_chunker": atomicrag_openie_adapter.ATTRIBUTION_STATEMENT,
            "disco_rag": disco_rag_paragraph_adapter.BACKBONE_SUBSTITUTION_STATEMENT,
            "disco_rag_commit": disco_rag_paragraph_adapter.DISCO_RAG_COMMIT,
            "disco_rag_bypasses": disco_rag_paragraph_adapter.BYPASS_NOTES,
            "custom_fallback": custom_fallback_paragraph.CUSTOM_FALLBACK_STATEMENT,
            "contextual_retrieval": contextual_retrieval_context.CONTEXTUAL_RETRIEVAL_STATEMENT,
            "flagged_deferral": FLAGGED_DEFERRAL_STATEMENT,
            "hca": HCA_STATEMENT,
        },
        "reproducibility": {
            "model": MODEL,
            "temperature": TEMPERATURE,
            "seed": SEED,
            "severance_judge": "severance_judge_paragraph.llm_judge_paragraph_severance "
                               "(same methodology as ../run_experiment_3.py / Experiment 1/2)",
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
                             "the full experiment is always all 124)")
    parser.add_argument("--model", type=str, default=MODEL)
    parser.add_argument("--max-workers", type=int, default=DEFAULT_MAX_WORKERS)
    parser.add_argument("--report-file", type=str, default=REPORT_JSON)
    args = parser.parse_args(argv)

    os.makedirs(RESULTS_DIR, exist_ok=True)
    start = time.time()

    eval_records, derivation = exp3_dataset_atomicrag.derive_eval_set()
    print(f"Eval set derived: {len(eval_records)} cases "
          f"({derivation['n_condition_severed']} Condition + "
          f"{derivation['n_concession_severed']} Concession, both severed under "
          "AtomicRAG's standard atomization).")

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
        eval_records, max_workers=args.max_workers, label="atomicrag-exp3")

    summary = build_summary(results, derivation)

    fully_blocked = all(summary[arm_key]["n_scored"] == 0 for arm_key in ARM_KEYS)
    execution_note = (
        "completed" if not fully_blocked else
        "BLOCKED: every LLM-dependent arm (2-5) returned zero successfully-"
        "judged cases despite attempting generation -- consistent with an "
        "account-level API blocker (e.g. OPENAI_API_KEY quota/credits "
        "exhausted), not a per-case content issue. Arm 1 (reused from "
        "run_atomicrag_experiment.py) and arm 6 (rule-based, no LLM calls) "
        "are unaffected and reflect real results. Re-run this exact script "
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
