"""own_baseline_track: extract+judge orchestration for THIS PROJECT'S OWN
minimal prompted baseline splitter (own_baseline_adapter.py, wrapping
../../atomization_conditions.py's `run_condition_a` / `run_condition_b`
UNMODIFIED -- see that adapter's module docstring for the full "why call
it unmodified, not reimplemented" argument and the required
INPUT-GRANULARITY DECISION). Measures whether this baseline's atomized
claims still convey a Condition/Concession relation identified in the SAME
272 governing (75 Condition + 197 Concession) + 206 Elaboration-control
FactoidWiki paragraphs ../run_experiment_1_2.py already built and scored
for Propositionizer (Condition A there) and the gpt-4o-mini relation-aware
atomizer (Condition B there) -- see ../logs/task7_experiment_govern_log.jsonl
/ task7_experiment_elaboration_log.jsonl (read-only source here; see
env_utils.py).

FRAMING (must be preserved wherever this baseline's numbers are cited --
see own_baseline_adapter.FRAMING_STATEMENT): "a minimal prompted baseline,
included as one additional tested system for the generality claim, not
itself a claimed contribution." This is the fourth of four chunkers in a
controlled comparison, nothing more -- never described as this project's
own showcased pipeline.

CONDITION B IS AVAILABLE FOR THIS CHUNKER (unlike AtomicRAG/NuggetIndex --
see those tracks' own adapters for why their external prompts have no
relation-hint input slot): ../../atomization_conditions.py defines
`run_condition_b` for exactly this purpose (relation-aware elicitation),
so this track runs BOTH conditions and reports the same capacity-vs-
elicitation ablation (Experiment 1) already run for the Propositionizer
track (`../run_experiment_1_2.py`'s `experiment_1` key, and the original
CFR-sentence track's `../../run_experiments.py`'s `experiment_1`).

VOCABULARY NOTE: this track's records use "claims" (condition_a_claims /
condition_b_claims), matching atomization_conditions.py's own return key
literally (`{"claims": [...]}`), NOT "propositions" the way
../run_experiment_1_2.py / ../atomicrag_track / ../nuggetindex_track name
their atomized units -- deliberate, since "call it the same way it's
invoked elsewhere in this project" (own_baseline_adapter.py's mandate)
extends to not silently renaming its own output vocabulary either.

REUSE, NOT REIMPLEMENTATION, OF THE SEVERANCE JUDGE: this script imports
`llm_judge_paragraph_severance` from ../severance_judge_paragraph.py and
`normalize_text` from ../candidate_prefilter.py directly -- the SAME
severance measurement (LLM-judge, paragraph-adapted from
../../severance_detection.py's design, plus the rule-based connective-
survival check) already used for the Propositionizer and AtomicRAG tracks,
rather than a third reimplementation. See
../atomicrag_track/run_atomicrag_experiment.py's own "REUSE, NOT
REIMPLEMENTATION, OF THE JUDGE" docstring section for the identical
precedent/justification for this cross-track-boundary import.

Every governing (Condition/Concession) paragraph gets: Condition A
atomize (1 call) + Condition B atomize (1 call) + severance-judge on A's
output (1 call) + severance-judge on B's output (1 call) = 4 real LLM
calls. Every Elaboration-control paragraph gets: Condition A atomize (1
call) + severance-judge on A's output (1 call) = 2 real LLM calls (no
Condition B on the control, matching ../run_experiment_1_2.py's own
Experiment 2 control-arm design). Full 272+206 sample: 272*4 + 206*2 =
1088 + 412 = 1500 real LLM calls.

Usage:
    venv/bin/python server/scripts/discourse_severance/factoidwiki_track/own_baseline_track/run_own_baseline_experiment.py --pilot 6
    venv/bin/python server/scripts/discourse_severance/factoidwiki_track/own_baseline_track/run_own_baseline_experiment.py
"""

import argparse
import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

OWN_BASELINE_TRACK_DIR = os.path.dirname(os.path.abspath(__file__))
FACTOIDWIKI_TRACK_DIR = os.path.dirname(OWN_BASELINE_TRACK_DIR)
# Insertion order matters: FACTOIDWIKI_TRACK_DIR first, then
# OWN_BASELINE_TRACK_DIR, so this track's OWN env_utils.py (with
# GOVERN_SOURCE_LOG / ELABORATION_SOURCE_LOG / load_jsonl -- names
# ../env_utils.py does not have) wins the name collision and is the one
# actually imported below, while FACTOIDWIKI_TRACK_DIR is still reachable
# afterward (lower priority) for severance_judge_paragraph/candidate_prefilter.
if FACTOIDWIKI_TRACK_DIR not in sys.path:
    sys.path.insert(0, FACTOIDWIKI_TRACK_DIR)
# OWN_BASELINE_TRACK_DIR is auto-inserted by the interpreter at sys.path[0]
# when this script is run directly, but the FACTOIDWIKI_TRACK_DIR insert
# above pushes it back to index 1 -- unconditionally re-insert at index 0
# (remove-then-insert, not an "if not in sys.path" guard, which would
# wrongly no-op here since it's already present just at the wrong index).
if OWN_BASELINE_TRACK_DIR in sys.path:
    sys.path.remove(OWN_BASELINE_TRACK_DIR)
sys.path.insert(0, OWN_BASELINE_TRACK_DIR)

from env_utils import (  # noqa: E402
    ELABORATION_SOURCE_LOG,
    GOVERN_SOURCE_LOG,
    LOGS_DIR,
    RESULTS_DIR,
    ensure_dirs,
    load_jsonl,
    load_server_env,
)

load_server_env()

import own_baseline_adapter as adapter  # noqa: E402
from severance_judge_paragraph import llm_judge_paragraph_severance  # noqa: E402
from candidate_prefilter import normalize_text  # noqa: E402

DEFAULT_MAX_WORKERS = 8
GOVERNING_RELATION_TYPES = ["Condition", "Concession"]

INPUT_GRANULARITY_DECISION_NOTE = (
    "Both Condition A and Condition B are run on the bare FactoidWiki "
    "paragraph `content` string AS-IS, passed unmodified into "
    "atomization_conditions.run_condition_a/run_condition_b as the "
    "`sentence` argument, even though that function's prompt assumes "
    "single-sentence input ('This segment is exactly one sentence'). This "
    "is a deliberate choice, not an oversight: it is what a real "
    "deployment of this project's shipped baseline would do if pointed at "
    "Wikipedia paragraphs without adapting it first, and reimplementing a "
    "paragraph-flavored prompt (the way ../condition_b_atomizer.py did for "
    "the Propositionizer track's own from-scratch Condition B) would make "
    "this a reinvented variant rather than 'our baseline, run unmodified'. "
    "Full reasoning, including the empirical pilot check that the model "
    "does not collapse on multi-sentence input despite the prompt's false "
    "framing: own_baseline_adapter.py's module docstring, "
    "'INPUT-GRANULARITY DECISION' section."
)


def _relation_dict(rec):
    return {
        "relation_type": rec["relation_type"],
        "nucleus": rec["nucleus"],
        "satellite": rec["satellite"],
        "connective": rec["connective"],
    }


def _process_govern_record(rec):
    """Governing (Condition/Concession) record: Condition A + Condition B
    atomize, then severance-judge each independently against the SAME
    paragraph/relation. Sequential within a record (judge needs the
    atomization result); records are processed in parallel across threads
    by `_parallel_map` below.
    """
    content = rec["content"]
    relation = _relation_dict(rec)

    claims_a = adapter.run_condition_a(content)
    claims_b = adapter.run_condition_b(content, relation)

    severance_a = llm_judge_paragraph_severance(content, relation, claims_a)
    severance_b = llm_judge_paragraph_severance(content, relation, claims_b)

    return {
        **rec,
        "condition_a_claims": claims_a,
        "n_condition_a_claims": len(claims_a),
        "condition_b_claims": claims_b,
        "n_condition_b_claims": len(claims_b),
        "severance_a": severance_a,
        "severance_b": severance_b,
    }


def _process_elaboration_record(rec):
    """Elaboration-control record: Condition A only, matching
    ../run_experiment_1_2.py's Experiment 2 control-arm design (the
    control never gets Condition B in any sibling track).
    """
    content = rec["content"]
    relation = _relation_dict(rec)

    claims_a = adapter.run_condition_a(content)
    severance_a = llm_judge_paragraph_severance(content, relation, claims_a)

    return {
        **rec,
        "condition_a_claims": claims_a,
        "n_condition_a_claims": len(claims_a),
        "severance_a": severance_a,
    }


def _parallel_map(func, items, max_workers=DEFAULT_MAX_WORKERS, label=""):
    """Same ThreadPoolExecutor-with-as_completed pattern used throughout
    this project (../run_two_stage_pipeline.py's _parallel_map,
    ../nuggetindex_track/run_nuggetindex_experiment.py's own copy) --
    duplicated locally per this track's self-contained-scripts convention.
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
            if done % 10 == 0 or done == len(items):
                print(f"  {label} {done}/{len(items)}", flush=True)
    return results


# --- pilot sampling -----------------------------------------------------


def select_pilot_sample(govern_records, elaboration_records, n_per_governing_type=6, n_elaboration=4):
    """Deterministic (pool_index order, no randomness) small pilot slice --
    same design as ../nuggetindex_track's select_pilot_sample: up to
    `n_per_governing_type` of each Condition/Concession (first by
    pool_index) plus `n_elaboration` Elaboration records, so the pilot's
    hand-inspection covers all three relation types.
    """
    govern_sorted = sorted(govern_records, key=lambda r: r["pool_index"])
    condition = [r for r in govern_sorted if r["relation_type"] == "Condition"][:n_per_governing_type]
    concession = [r for r in govern_sorted if r["relation_type"] == "Concession"][:n_per_governing_type]
    govern_pilot = sorted(condition + concession, key=lambda r: r["pool_index"])
    elaboration_pilot = sorted(elaboration_records, key=lambda r: r["pool_index"])[:n_elaboration]
    return govern_pilot, elaboration_pilot


# --- summaries ------------------------------------------------------------


def _rate(preds):
    vals = [p for p in preds if p is not None]
    severed = sum(1 for p in vals if p is False)
    return {"n_scored": len(vals), "n_severed": severed,
            "severed_rate": severed / len(vals) if vals else None}


def summarize_experiment_1(govern_results):
    """Capacity-vs-elicitation ablation: Condition A (standard atomization)
    vs Condition B (relation-aware atomization), on the SAME governing
    sample. Mirrors ../run_experiment_1_2.py's summarize_experiment_1
    exactly (field names included), so this track's experiment_1 is
    directly comparable in shape to the Propositionizer track's.
    """
    by_type = {}
    for rt in GOVERNING_RELATION_TYPES:
        subset = [r for r in govern_results if r["relation_type"] == rt]
        by_type[rt] = {
            "n": len(subset),
            "severed_a": _rate([r["severance_a"]["preserved"] for r in subset]),
            "severed_b": _rate([r["severance_b"]["preserved"] for r in subset]),
        }

    overall_a = _rate([r["severance_a"]["preserved"] for r in govern_results])
    overall_b = _rate([r["severance_b"]["preserved"] for r in govern_results])

    still_severed_under_b = [r for r in govern_results if r["severance_b"]["preserved"] is False]
    n_scored_b = sum(1 for r in govern_results if r["severance_b"]["preserved"] is not None)

    n_condition_a_empty = sum(1 for r in govern_results if r["n_condition_a_claims"] == 0)
    n_condition_b_empty = sum(1 for r in govern_results if r["n_condition_b_claims"] == 0)

    return {
        "n": len(govern_results),
        "condition_a_overall": overall_a,
        "condition_b_overall": overall_b,
        "by_relation_type": by_type,
        "n_condition_a_empty_claims": n_condition_a_empty,
        "n_condition_b_empty_claims": n_condition_b_empty,
        "empty_claims_note": (
            "Mechanical count of paragraphs where the returned claim list "
            "was empty. NOT the same as a confirmed call/parse failure -- "
            "atomization_conditions.run_condition_a/run_condition_b (run "
            "unmodified, per own_baseline_adapter.py) do not distinguish a "
            "genuine zero-claim decomposition from a swallowed failure. "
            "See own_baseline_adapter.py's module docstring."
        ),
        "n_still_severed_under_b": len(still_severed_under_b),
        "still_severed_under_b_rate_of_scored": (
            len(still_severed_under_b) / n_scored_b if n_scored_b else None
        ),
        "still_severed_under_b_pool_indices": sorted(r["pool_index"] for r in still_severed_under_b),
    }


def summarize_experiment_2(govern_results, elaboration_results):
    """Relation-type stratified severance test: governing (pooled
    Condition+Concession) vs Elaboration control, Condition A output only
    (the control never gets Condition B). Mirrors
    ../run_experiment_1_2.py's summarize_experiment_2 exactly.
    """
    def severed_counts(preds):
        vals = [p for p in preds if p is not None]
        severed = sum(1 for p in vals if p is False)
        return severed, len(vals) - severed

    govern_preds = [r["severance_a"]["preserved"] for r in govern_results]
    control_preds = [r["severance_a"]["preserved"] for r in elaboration_results]

    gov_severed, gov_preserved = severed_counts(govern_preds)
    ctrl_severed, ctrl_preserved = severed_counts(control_preds)

    per_relation_type = {}
    for rt in GOVERNING_RELATION_TYPES + ["Elaboration"]:
        subset = (
            [r["severance_a"]["preserved"] for r in govern_results if r["relation_type"] == rt]
            if rt in GOVERNING_RELATION_TYPES
            else control_preds
        )
        per_relation_type[rt] = _rate(subset)

    result = {
        "per_relation_type_condition_a": per_relation_type,
        "governing_pooled_n": gov_severed + gov_preserved,
        "governing_pooled_severed": gov_severed,
        "governing_pooled_severed_rate": (
            gov_severed / (gov_severed + gov_preserved) if (gov_severed + gov_preserved) else None
        ),
        "elaboration_control_n": ctrl_severed + ctrl_preserved,
        "elaboration_control_severed": ctrl_severed,
        "elaboration_control_severed_rate": (
            ctrl_severed / (ctrl_severed + ctrl_preserved) if (ctrl_severed + ctrl_preserved) else None
        ),
    }

    try:
        from scipy.stats import fisher_exact, chi2_contingency
        table = [[gov_severed, gov_preserved], [ctrl_severed, ctrl_preserved]]
        odds_ratio, fisher_p = fisher_exact(table)
        result["fisher_exact_p_value"] = fisher_p
        result["fisher_odds_ratio"] = odds_ratio
        if all(sum(row) > 0 for row in table) and all(sum(col) > 0 for col in zip(*table)):
            chi2, chi2_p, dof, _ = chi2_contingency(table)
            result["chi2_p_value"] = chi2_p
        result["test_note"] = (
            "Fisher's exact test on the 2x2 severed/preserved table, Condition+Concession "
            "(pooled, own-baseline Condition-A output) vs Elaboration control (own-baseline "
            "Condition-A output). Mirrors ../run_experiment_1_2.py's summarize_experiment_2 "
            "and ../../run_experiments.py's compare_relation_bearing_vs_control design."
        )
    except ImportError:
        result["test_note"] = "scipy not available in this environment -- reporting raw counts/rates only."

    return result


def summarize_structural_comparison(govern_results):
    """Free (no new LLM calls) qualitative Condition-A-vs-B comparison:
    claims/paragraph, and whether the elicited connective survives
    verbatim (after normalize_text) in >=1 output claim under A vs under
    B. Mirrors ../run_experiment_1_2.py's summarize_structural_comparison
    exactly (adapted field names for "claims" vocabulary).
    """
    def connective_survives(connective, claims):
        norm_conn = normalize_text(connective)
        if not norm_conn:
            return None
        return any(norm_conn in normalize_text(c) for c in claims)

    rows = []
    for r in govern_results:
        rows.append({
            "relation_type": r["relation_type"],
            "n_a": r["n_condition_a_claims"],
            "n_b": r["n_condition_b_claims"],
            "conn_survives_a": connective_survives(r["connective"], r["condition_a_claims"]),
            "conn_survives_b": connective_survives(r["connective"], r["condition_b_claims"]),
        })

    def avg(vals):
        return sum(vals) / len(vals) if vals else None

    def survival(vals):
        scored = [v for v in vals if v is not None]
        return {
            "n_scored": len(scored),
            "n_survives": sum(1 for v in scored if v),
            "survival_rate": sum(1 for v in scored if v) / len(scored) if scored else None,
        }

    def block(subset):
        return {
            "n": len(subset),
            "avg_claims_condition_a": avg([row["n_a"] for row in subset]),
            "avg_claims_condition_b": avg([row["n_b"] for row in subset]),
            "connective_survival_condition_a": survival([row["conn_survives_a"] for row in subset]),
            "connective_survival_condition_b": survival([row["conn_survives_b"] for row in subset]),
        }

    overall = block(rows)
    by_relation_type = {rt: block([row for row in rows if row["relation_type"] == rt])
                         for rt in GOVERNING_RELATION_TYPES}

    return {"overall": overall, "by_relation_type": by_relation_type}


# --- run ------------------------------------------------------------------


def run(govern_sample, elaboration_sample, govern_log_path, elaboration_log_path, report_path, label):
    print(f"[{label}] Running own-baseline (Condition A + Condition B) + severance-judge for "
          f"{len(govern_sample)} governing paragraphs...")
    t0 = time.time()
    govern_results = _parallel_map(_process_govern_record, govern_sample, label=f"{label}-govern")
    with open(govern_log_path, "w", encoding="utf-8") as fh:
        for rec in govern_results:
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")

    print(f"[{label}] Running own-baseline (Condition A only) + severance-judge for "
          f"{len(elaboration_sample)} Elaboration-control paragraphs...")
    elaboration_results = _parallel_map(_process_elaboration_record, elaboration_sample, label=f"{label}-elab")
    with open(elaboration_log_path, "w", encoding="utf-8") as fh:
        for rec in elaboration_results:
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
    elapsed = time.time() - t0

    n_judge_errors = sum(
        1 for r in govern_results if r["severance_a"]["preserved"] is None or r["severance_b"]["preserved"] is None
    ) + sum(1 for r in elaboration_results if r["severance_a"]["preserved"] is None)

    n_condition_a_calls = len(govern_results) + len(elaboration_results)
    n_condition_b_calls = len(govern_results)
    n_severance_judge_calls = 2 * len(govern_results) + len(elaboration_results)
    n_real_llm_calls = n_condition_a_calls + n_condition_b_calls + n_severance_judge_calls

    exp1_summary = summarize_experiment_1(govern_results)
    exp2_summary = summarize_experiment_2(govern_results, elaboration_results)
    structural_summary = summarize_structural_comparison(govern_results)

    report = {
        "label": label,
        "baseline_framing_statement": adapter.FRAMING_STATEMENT,
        "input_granularity_decision_note": INPUT_GRANULARITY_DECISION_NOTE,
        "govern_sample_size": len(govern_sample),
        "elaboration_sample_size": len(elaboration_sample),
        "govern_log_source": GOVERN_SOURCE_LOG,
        "elaboration_log_source": ELABORATION_SOURCE_LOG,
        "govern_log": govern_log_path,
        "elaboration_log": elaboration_log_path,
        "experiment_1": exp1_summary,
        "experiment_2": exp2_summary,
        "structural_comparison_condition_a_vs_b": structural_summary,
        "llm_call_accounting": {
            "n_condition_a_calls": n_condition_a_calls,
            "n_condition_b_calls": n_condition_b_calls,
            "n_severance_judge_calls": n_severance_judge_calls,
            "total_real_llm_calls": n_real_llm_calls,
            "n_judge_call_or_parse_failures": n_judge_errors,
        },
        "wall_clock_seconds": elapsed,
    }
    with open(report_path, "w", encoding="utf-8") as fh:
        json.dump(report, fh, indent=2, ensure_ascii=False)

    print(f"\n[{label}] {n_real_llm_calls} real LLM calls "
          f"({n_condition_a_calls} Condition-A atomize + {n_condition_b_calls} Condition-B atomize + "
          f"{n_severance_judge_calls} severance-judge), {n_judge_errors} judge call/parse failures, "
          f"{elapsed:.1f}s wall-clock.")
    print(json.dumps({"experiment_1": exp1_summary, "experiment_2": exp2_summary}, indent=2))
    print(f"\nWrote {report_path}")
    return report


def main():
    ensure_dirs()
    parser = argparse.ArgumentParser()
    parser.add_argument("--pilot", type=int, default=None,
                         help="If set, run a small stratified pilot (N Condition + N Concession + "
                              "~N*0.67 Elaboration, deterministic pool_index order) instead of the "
                              "full 272+206 sample. E.g. --pilot 6 -> 6 Condition + 6 Concession + "
                              "4 Elaboration = 16 paragraphs.")
    args = parser.parse_args()

    govern_records = load_jsonl(GOVERN_SOURCE_LOG)
    elaboration_records = load_jsonl(ELABORATION_SOURCE_LOG)
    print(f"Loaded {len(govern_records)} governing + {len(elaboration_records)} Elaboration-control "
          f"source records from ../logs/ (factoidwiki_track's Task 7 output).")

    if args.pilot is not None:
        n_elab = max(1, round(args.pilot * 2 / 3))
        govern_sample, elaboration_sample = select_pilot_sample(
            govern_records, elaboration_records, n_per_governing_type=args.pilot, n_elaboration=n_elab
        )
        govern_log = os.path.join(LOGS_DIR, "own_baseline_pilot_govern_log.jsonl")
        elaboration_log = os.path.join(LOGS_DIR, "own_baseline_pilot_elaboration_log.jsonl")
        report_path = os.path.join(RESULTS_DIR, "own_baseline_pilot_report.json")
        run(govern_sample, elaboration_sample, govern_log, elaboration_log, report_path, label="pilot")
    else:
        govern_log = os.path.join(LOGS_DIR, "own_baseline_govern_log.jsonl")
        elaboration_log = os.path.join(LOGS_DIR, "own_baseline_elaboration_log.jsonl")
        report_path = os.path.join(RESULTS_DIR, "own_baseline_experiment_1_2_report.json")
        run(govern_records, elaboration_records, govern_log, elaboration_log, report_path, label="full")


if __name__ == "__main__":
    main()
