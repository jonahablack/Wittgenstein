"""NuggetIndex Experiment 3 (repair-arm reliability), REDUCED 3-ARM SCOPE.

This is NOT the full 6-arm design ../../run_experiment_3.py runs for
FactoidWiki/Propositionizer. That scope reduction was decided by the
project owner up front, after being asked directly, and is restated here
so this report is self-documenting without cross-referencing anything
outside this file:

NuggetIndex's severed cases are subject-predicate-object TRIPLES, not
natural-language claims. The three GENERATIVE repair arms FactoidWiki
runs -- arm 2 (Disco-RAG), arm 3 (custom fallback rewriter), arm 4
(Contextual Retrieval context injection) -- are all natural-language
operations with no defined triple-native form. Naturalizing NuggetIndex's
triples into prose first, then running a natural-language repair arm on
that prose, would test the repair arms against synthesized text
NuggetIndex itself never produced -- an uncontrolled confound, not a
measurement of anything NuggetIndex did. Arms 2, 3, and 4 are therefore
NOT built or run anywhere in this file, and triples are not converted to
prose anywhere in this experiment except the one narrow, explicitly-
justified exception documented in arm6_flagged_deferral.py (render_triple
reused ONLY because risk_triage.flag_claim structurally requires a text
string as input).

THE THREE ARMS ACTUALLY RUN, against exp3_dataset.py's bundling-corrected
205-case eval set (60 Condition + 145 Concession; see that module's
docstring for exactly how the correction is derived and why it is not
simply "raw minus the audit's exclusion list"):

  1. No elicitation (baseline): NuggetIndex's own severed triples, as
     extracted, no repair attempted. Reused directly from
     ../logs/nuggetindex_govern_log.jsonl (+ the bundling-audit
     correction for pool_index 1840, 1936, 4920 -- see exp3_dataset.py).
     ZERO new LLM calls: by construction of the eval set (every case here
     IS a case NuggetIndex's own triple-aware judge scored severed), this
     arm's severance judge verdict is 100% severed, 0% correct, always --
     nothing to (re)compute.

  5. Parent-segment fallback: the full source PARAGRAPH in place of
     NuggetIndex's triples -- this arm does not operate ON NuggetIndex's
     atomic output at all, it REPLACES it, so it is chunker-agnostic and
     transfers unmodified from ../../run_experiment_3.py's design. Scored
     with severance_judge_paragraph.py's EXISTING natural-language
     severance judge (imported directly from ../../, unmodified) --
     correct, since this arm's OUTPUT is genuine natural-language
     paragraph text, not a rendering of anything triple-shaped. Real LLM
     calls: one severance-judge call per case always, plus one
     exp3_scoring_paragraph.classify_failure_type call per case the judge
     scores severed (mirroring ../../run_experiment_3.py's own arm 5
     exactly -- that arm also skips ONLY calibration, not failure-type
     classification; see that file's process_case). Both classifier
     modules operate on real natural-language paragraph text throughout
     -- no triple conversion of any kind occurs in this arm.

  6. Flagged deferral: server/components/risk_triage.py's `flag_claim`,
     imported UNMODIFIED, run against NuggetIndex's triples via
     arm6_flagged_deferral.py. Per the task brief: flag_claim structurally
     requires a text string, which a bare (subject, predicate, object)
     tuple has no surface form for -- so render_triple (an existing,
     deterministic, non-LLM, pre-built string template already used
     elsewhere in this project for NuggetIndex's own severance judge) is
     reused ONLY to satisfy that one input requirement. This is NOT new
     methodology and NOT a generative rewrite (render_triple calls no
     model); it is the ONE narrow, explicitly-authorized exception to
     "no conversion" in this entire experiment -- see
     arm6_flagged_deferral.py's module docstring for the full
     justification, restated there rather than only here so it survives
     independently of this file. Arm 6 does not change NuggetIndex's
     triples (flags are annotations layered on top), so its severance
     bucket is IDENTICAL to arm 1's BY CONSTRUCTION -- no second judge
     call is made for it; the verdict is reused from arm 1. ZERO LLM
     calls (flag_claim is pure rule-based / spaCy-parse, no model call).

WHAT "correct / dangerous-failure / detectable-failure" MEANS HERE, AND
WHERE IT DOES **NOT** APPLY (stated explicitly, not glossed over):

Arms 2-5 in ../../run_experiment_3.py get a SECOND classification pass
(exp3_scoring_paragraph.classify_failure_type) that splits "severed" into
dangerous_failure (fluent, confident, no visible sign anything is
missing) vs. detectable_failure (visibly incomplete/garbled/hedged) --
that classifier's prompt is built by joining natural-language proposition
strings (`"\\n".join(f"- {p}" for p in recovered_propositions)`).

Arm 5 here reuses that classifier UNMODIFIED and its input genuinely is
natural-language text (the parent paragraph) -- fully legitimate, no
triple conversion involved.

Arms 1 and 6 do NOT get this dangerous/detectable sub-classification.
Running it would require either (a) reusing render_triple a SECOND time,
beyond the one exception this task's brief explicitly authorized
(arm 6's flag_claim input only), to build a props_block out of rendered
triples, or (b) inventing a brand-new triple-native failure-type
classifier that is not among the things this task's "What to build"
section asked for (it asks only that arms 1 and 6 be scored with the
EXISTING triple-aware severance judge). Either path is exactly the kind
of scope creep / uncontrolled-confound risk this task's scope reduction
exists to avoid. So: for arms 1 and 6, every eval-set case's bucket is
reported simply as "severed" (correct_rate 0.0 by construction, no
dangerous/detectable split). "Flag coverage of dangerous failures for
arm 6" is therefore operationalized as: of every eval-set case (each one
is, by construction, a silently-wrong triple set with nothing in arm 1's
own output marking it as incomplete), what fraction does arm 6's
flag_claim fire >=1 flag on. This is the closest faithful analogue to
../../run_experiment_3.py's coverage_of_dangerous_failure figure that is
honestly computable without the disallowed conversion step -- see
summarize_arm6's docstring below.

Usage
-----
    venv/bin/python .../nuggetindex_track/exp3/run_nuggetindex_exp3.py
    venv/bin/python .../nuggetindex_track/exp3/run_nuggetindex_exp3.py --limit 5
    venv/bin/python .../nuggetindex_track/exp3/run_nuggetindex_exp3.py --raw   # uncorrected eval set, for comparison
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

from exp3_paths import RESULTS_DIR, ensure_dirs, load_server_env

load_server_env()

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
NUGGETINDEX_TRACK_DIR = os.path.dirname(SCRIPT_DIR)
FACTOIDWIKI_TRACK_DIR = os.path.dirname(NUGGETINDEX_TRACK_DIR)
DISCOURSE_SEVERANCE_DIR = os.path.dirname(FACTOIDWIKI_TRACK_DIR)
SCRIPTS_DIR = os.path.dirname(DISCOURSE_SEVERANCE_DIR)
SERVER_DIR = os.path.dirname(SCRIPTS_DIR)

# IMPORTANT ORDERING: import this directory's OWN modules (exp3_dataset,
# arm6_flagged_deferral) BEFORE adding FACTOIDWIKI_TRACK_DIR to sys.path.
# factoidwiki_track/ has its OWN exp3_dataset.py (a different module, for
# FactoidWiki's 109-case set) -- if FACTOIDWIKI_TRACK_DIR were inserted
# ahead of this script's own directory, `import exp3_dataset` would
# silently resolve to the WRONG module (confirmed by hitting exactly this
# collision while building this file: it raised
# "derive_eval_set() got an unexpected keyword argument 'bundling_corrected'"
# because FactoidWiki's exp3_dataset.derive_eval_set has no such
# parameter). Python already puts this script's own directory first in
# sys.path by default, so importing local modules before touching
# sys.path at all is sufficient and avoids the collision entirely.
import exp3_dataset  # noqa: E402  (THIS exp3/ directory's own dataset module -- see ordering note above)
import arm6_flagged_deferral  # noqa: E402  (this exp3/ directory's own arm-6 module)

# Only now extend sys.path, via append (never insert(0, ...)) so nothing
# already resolved above can be shadowed by a later entry.
if FACTOIDWIKI_TRACK_DIR not in sys.path:
    sys.path.append(FACTOIDWIKI_TRACK_DIR)
if SERVER_DIR not in sys.path:
    sys.path.append(SERVER_DIR)

# Deliberate, explicitly-justified exception to nuggetindex_track's usual
# no-sibling-script-import convention (see ../env_utils.py's docstring):
# the task instructs REUSE, unmodified, of factoidwiki_track's existing,
# validated natural-language severance judge and failure-type classifier
# for arm 5 specifically, whose OUTPUT is genuine natural-language
# paragraph text (not a triple-to-prose conversion of anything). Importing
# the validated original -- rather than hand-copying its prompt logic the
# way triple_severance_judge.py copies _RELATION_DESCRIPTIONS verbatim --
# is what "use it unmodified" requires: a copy could silently drift from
# the original over time; an import cannot.
import severance_judge_paragraph  # noqa: E402  (factoidwiki_track/, reused per explicit task instruction)
import exp3_scoring_paragraph  # noqa: E402  (factoidwiki_track/, reused per explicit task instruction; natural-language input only, never called on triples)

DEFAULT_MAX_WORKERS = 8
MODEL = "gpt-4o-mini"
TEMPERATURE = 0  # api_call.generate_response's own default
SEED = 13        # api_call.generate_response's own default

REPORT_JSON = os.path.join(RESULTS_DIR, "nuggetindex_exp3_report.json")

ARMS_NOT_RUN_NOTE = (
    "Arms 2 (Disco-RAG, adapted), 3 (custom fallback rewriter), and 4 (Contextual "
    "Retrieval context injection) are intentionally NOT present anywhere in this report. "
    "All three are natural-language generative repair operations with no defined "
    "triple-native form for NuggetIndex's (subject, predicate, object) atomic output; "
    "naturalizing the triples into prose first and then repairing the prose would test "
    "the repair arms against synthesized text NuggetIndex itself never produced -- an "
    "uncontrolled confound. This scope reduction (3 of 6 arms) was decided directly by "
    "the project owner, not inferred here. See this module's own docstring for the full "
    "reasoning, restated in this JSON so the report is self-documenting."
)

RENDER_TRIPLE_EXCEPTION_NOTE = (
    "The ONLY triple-to-text conversion anywhere in this experiment: arm 6's flag_claim "
    "(server/components/risk_triage.py, imported UNMODIFIED) structurally requires a text "
    "string as input -- a bare (subject, predicate, object) tuple has no surface form for "
    "its regex/spaCy-based detectors to run against. render_triple "
    "(nuggetindex_track/triple_severance_judge.py) is reused to satisfy that one "
    "requirement: it is a FIXED, DETERMINISTIC, PRE-EXISTING string template with no LLM "
    "call in it, already built and validated elsewhere in this project (the primary "
    "NuggetIndex severance judge's pseudo-sentence rendering). This is not new "
    "methodology and not a generative rewrite -- see arm6_flagged_deferral.py's module "
    "docstring for the full justification."
)

FAILURE_TYPE_SCOPE_NOTE = (
    "Arms 1 and 6 (triple-shaped output) do NOT get a dangerous-failure/detectable-failure "
    "sub-classification -- every case in this eval set is, by construction, 'severed' under "
    "NuggetIndex's own triple-aware judge (that is the eval-set selection criterion), so "
    "correct_rate is trivially 0.0 for both. Computing a dangerous/detectable split for "
    "triples would require either reusing render_triple a second time beyond its one "
    "authorized use (arm 6's flag_claim input) or inventing a new triple-native "
    "failure-type classifier that this task's 'What to build' section never asked for -- "
    "both risk the same naturalization confound the 3-arm scope reduction exists to avoid. "
    "Arm 5 (genuine natural-language paragraph output) DOES get this sub-classification, "
    "via exp3_scoring_paragraph.classify_failure_type, reused unmodified."
)

CALL_COUNTER = Counter()
_LOCK = Lock()


def _count(key, n=1):
    with _LOCK:
        CALL_COUNTER[key] += n


def _parallel_map(func, items, max_workers=DEFAULT_MAX_WORKERS, label=""):
    """Same ThreadPoolExecutor-with-as_completed pattern used throughout
    this project (../../run_two_stage_pipeline.py's _parallel_map, this
    track's own run_nuggetindex_experiment.py's _parallel_map) --
    duplicated locally, per this track's established self-contained-
    scripts convention.
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
            if done % 20 == 0 or done == len(items):
                print(f"  {label} {done}/{len(items)}", flush=True)
    return results


# --- per-case processing (3 arms) --------------------------------------------


def process_case(case, model=None):
    paragraph = case["content"]
    relation = case["relation"]
    result = {
        "pool_index": case["pool_index"],
        "relation_type": case["relation_type"],
        "title": case["title"],
        "section": case["section"],
        "content": paragraph,
        "relation": relation,
        "bundling_corrected_case": case["bundling_corrected_case"],
        "judge_variant": case["judge_variant"],
    }

    # Arm 1 -- no elicitation: NuggetIndex's own triples, as extracted,
    # zero regeneration; judge verdict reused (bundling-audit-corrected
    # where applicable -- see exp3_dataset.py). No new LLM call.
    result["arm_1_no_elicitation"] = {
        "triples": case["nuggetindex_triples"],
        "triples_rendered": case["nuggetindex_triples_rendered"],
        "n_triples": case["n_nuggetindex_triples"],
        "extraction_error": case["nuggetindex_extraction_error"],
        "judge": case["saved_severance_nuggetindex"],
        "bucket": "severed",
        "failure_type_subclassification": "not_computed",
        "note": ("reused from nuggetindex_govern_log.jsonl (+ bundling-audit correction "
                 "where applicable), zero regeneration, zero new LLM calls"),
    }

    # Arm 5 -- parent-segment fallback: full source paragraph in place of
    # NuggetIndex's triples; scored with severance_judge_paragraph.py's
    # existing natural-language judge, unmodified. Real LLM call (always).
    arm5_props = [paragraph]
    judge5 = severance_judge_paragraph.llm_judge_paragraph_severance(paragraph, relation, arm5_props, model=model)
    _count("arm5_judge_calls")
    arm5 = {"propositions": arm5_props, "judge": judge5, "bucket": "unscored", "failure_type": None}
    preserved = judge5.get("preserved")
    if preserved is True:
        arm5["bucket"] = "correct"
    elif preserved is False:
        failure_type = exp3_scoring_paragraph.classify_failure_type(
            paragraph, relation, arm5_props, judge5.get("reasoning", ""), model=model)
        _count("arm5_failure_type_calls")
        arm5["failure_type"] = failure_type
        category = failure_type.get("category")
        arm5["bucket"] = category if category in exp3_scoring_paragraph.FAILURE_TYPE_CATEGORIES \
            else "failure_type_unclassified"
    # preserved is None (judge call/parse failure) -> bucket stays "unscored"
    result["arm_5_parent_segment"] = arm5

    # Arm 6 -- flagged deferral: risk_triage.flag_claim, unmodified, run
    # against render_triple(triple) for each of NuggetIndex's own triples
    # (see arm6_flagged_deferral.py for the render_triple justification).
    # No new severance-judge call: arm 6 does not change the triples, so
    # its bucket is identical to arm 1's by construction.
    arm6 = arm6_flagged_deferral.flags_for_case(case)
    arm6["judge"] = case["saved_severance_nuggetindex"]
    arm6["bucket"] = "severed"
    arm6["failure_type_subclassification"] = "not_computed"
    result["arm_6_flagged_deferral"] = arm6

    return result


# --- summaries ----------------------------------------------------------------


def summarize_arm1(results):
    n = len(results)
    n_extraction_errors = sum(1 for r in results if r["arm_1_no_elicitation"]["extraction_error"])
    n_zero_triples = sum(1 for r in results if r["arm_1_no_elicitation"]["n_triples"] == 0)
    return {
        "n": n,
        "n_scored": n,
        "bucket_counts": {"correct": 0, "severed": n},
        "correct_rate": 0.0,
        "severed_rate": 1.0,
        "n_extraction_errors": n_extraction_errors,
        "n_zero_triple_cases": n_zero_triples,
        "note": FAILURE_TYPE_SCOPE_NOTE,
    }


ARM5_BUCKETS = ("correct", "dangerous_failure", "detectable_failure", "failure_type_unclassified", "unscored")


def summarize_arm5(results):
    bucket_counts = Counter(r["arm_5_parent_segment"]["bucket"] for r in results)
    n = len(results)
    n_scored = sum(1 for r in results if r["arm_5_parent_segment"]["judge"].get("preserved") is not None)

    def _rate(bucket):
        return bucket_counts.get(bucket, 0) / n_scored if n_scored else None

    return {
        "n": n,
        "n_scored": n_scored,
        "bucket_counts": {b: bucket_counts.get(b, 0) for b in ARM5_BUCKETS},
        "correct_rate": _rate("correct"),
        "dangerous_failure_rate": _rate("dangerous_failure"),
        "detectable_failure_rate": _rate("detectable_failure"),
        "failure_type_unclassified_rate": _rate("failure_type_unclassified"),
    }


def summarize_arm6(results):
    """Arm 6 shares arm 1's triples and judge verdict by construction (see
    process_case), so its own bucket_counts are identical to arm 1's --
    reported for completeness, not as new information. The genuinely new
    information this arm adds is flag coverage, computed here.

    "Flag coverage of dangerous failures": since arms 1/6 have no
    dangerous/detectable sub-split (see FAILURE_TYPE_SCOPE_NOTE), the
    honestly-computable analogue is coverage over the WHOLE eval set --
    every case here is, by construction, a silently-wrong (unflagged by
    arm 1 itself) severed-relation case, so this is the full "would
    flagging have surfaced this?" question for this experiment's
    baseline arm.
    """
    n = len(results)
    n_any = sum(1 for r in results if r["arm_6_flagged_deferral"]["any_flag_fired"])
    n_seg = sum(1 for r in results if r["arm_6_flagged_deferral"]["segment_flag_fired"])
    type_counts = Counter(t for r in results for t in r["arm_6_flagged_deferral"]["flag_types_fired"])
    n_zero_triples = sum(1 for r in results if r["arm_6_flagged_deferral"]["n_triples_checked"] == 0)
    return {
        "n": n,
        "bucket_counts": {"correct": 0, "severed": n},
        "correct_rate": 0.0,
        "severed_rate": 1.0,
        "n_cases_any_flag": n_any,
        "n_cases_segment_flag": n_seg,
        "flag_coverage_rate_any": n_any / n if n else None,
        "flag_coverage_rate_segment": n_seg / n if n else None,
        "flag_type_case_counts": dict(sorted(type_counts.items())),
        "n_cases_zero_triples_no_flag_possible": n_zero_triples,
        "note": (
            "Arm 6 uses the SAME triples and the SAME judge verdict as arm 1 (flag_claim "
            "only adds flags, it does not change the triples). 'Flag coverage of dangerous "
            "failures' is operationalized here as: of all N eval-set cases (each one is, by "
            "construction, a silent/unflagged severed-relation failure under arm 1's "
            "no-elicitation baseline), what fraction got >=1 risk_triage flag. See "
            "FAILURE_TYPE_SCOPE_NOTE for why there is no dangerous-vs-detectable split to "
            f"condition coverage on instead. n_cases_zero_triples_no_flag_possible={n_zero_triples}: "
            "cases where NuggetIndex's extractor produced zero triples (extraction error) -- "
            "flag_claim has nothing to iterate over for these, so they can never be flagged "
            "regardless of how wrong the (empty) output is. This is a real, reportable "
            "structural blind spot of claim-level flagging applied to a triple extractor, "
            "not a bug in this experiment's code."
        ),
    }


def flag_summary(results):
    """Top-level flag summary, same shape as ../../run_experiment_3.py's
    flag_summary."""
    n = len(results)
    n_any = sum(1 for r in results if r["arm_6_flagged_deferral"]["any_flag_fired"])
    n_seg = sum(1 for r in results if r["arm_6_flagged_deferral"]["segment_flag_fired"])
    type_counts = Counter(t for r in results for t in r["arm_6_flagged_deferral"]["flag_types_fired"])
    return {
        "n_cases": n,
        "n_cases_any_flag": n_any,
        "n_cases_segment_flag": n_seg,
        "flag_type_case_counts": dict(sorted(type_counts.items())),
    }


def cross_tab_arm5(results):
    """Of arm 5's own bucket (correct / dangerous_failure / ...), how many
    would arm 6's flags (computed from arm 1's ORIGINAL NuggetIndex
    triples, NOT from arm 5's paragraph output -- flags are never
    recomputed per-arm) have surfaced? Plus the false-alarm side: flags
    fired where arm 5 was correct. Mirrors ../../run_experiment_3.py's
    cross_tab exactly, reduced to the one arm (5) that actually has a
    dangerous_failure bucket in this reduced experiment.
    """
    buckets = {b: [] for b in ARM5_BUCKETS}
    for r in results:
        buckets[r["arm_5_parent_segment"]["bucket"]].append(r)

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
    """Full documentation for every dangerous-failure case. Only arm 5 can
    land here (see FAILURE_TYPE_SCOPE_NOTE re: arms 1/6)."""
    docs = []
    for r in results:
        arm = r["arm_5_parent_segment"]
        if arm["bucket"] != "dangerous_failure":
            continue
        docs.append({
            "pool_index": r["pool_index"],
            "arm": "arm 5 (parent-segment fallback)",
            "relation_type": r["relation_type"],
            "title": r["title"],
            "content": r["content"],
            "nucleus": r["relation"]["nucleus"],
            "satellite": r["relation"]["satellite"],
            "connective": r["relation"]["connective"],
            "why_severed_judge": (arm.get("judge") or {}).get("reasoning"),
            "why_dangerous_classifier": (arm.get("failure_type") or {}).get("reasoning"),
            "flag_fired": r["arm_6_flagged_deferral"]["any_flag_fired"],
            "flag_types": r["arm_6_flagged_deferral"]["flag_types_fired"],
        })
    return docs


def build_summary(results, derivation):
    summary = {"eval_set": derivation, "n_cases": len(results)}
    summary["arm_1_no_elicitation"] = {
        **summarize_arm1(results), "label": "arm 1 (no elicitation / NuggetIndex baseline)"}
    summary["arm_5_parent_segment"] = {
        **summarize_arm5(results), "label": "arm 5 (parent-segment fallback)"}
    summary["arm_6_flagged_deferral"] = {
        **summarize_arm6(results), "label": "arm 6 (flagged deferral)"}
    summary["flag_summary"] = flag_summary(results)
    summary["cross_tabs"] = {"arm_5_parent_segment": cross_tab_arm5(results)}
    summary["dangerous_failure_documentation"] = dangerous_failure_docs(results)
    summary["llm_call_counts"] = dict(CALL_COUNTER)
    return summary


# --- entry point --------------------------------------------------------------


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--limit", type=int, default=None,
                        help="process only the first N cases (smoke-testing only; "
                             "the full run is all 205 bundling-corrected cases)")
    parser.add_argument("--raw", action="store_true",
                        help="use the RAW (bundling-uncorrected) 206-case eval set instead "
                             "of the default bundling-corrected 205-case set")
    parser.add_argument("--model", type=str, default=MODEL)
    parser.add_argument("--max-workers", type=int, default=DEFAULT_MAX_WORKERS)
    parser.add_argument("--report-file", type=str, default=REPORT_JSON)
    args = parser.parse_args(argv)

    ensure_dirs()

    if not os.environ.get("OPENAI_API_KEY"):
        raise RuntimeError(
            "FATAL: OPENAI_API_KEY not set after load_server_env() (checked server/.env). "
            "Arm 5's severance judge makes real LLM calls and cannot silently proceed "
            "without it -- fix the environment rather than let this run produce partial "
            "or fabricated results."
        )

    start = time.time()
    bundling_corrected = not args.raw
    eval_records, derivation = exp3_dataset.derive_eval_set(bundling_corrected=bundling_corrected)
    print(f"Eval set derived: {len(eval_records)} cases "
          f"(variant={'bundling_corrected' if bundling_corrected else 'raw'}) -- "
          f"{derivation['n_condition']} Condition + {derivation['n_concession']} Concession.")

    if args.limit is not None:
        eval_records = eval_records[:args.limit]
        print(f"--limit given: processing only the first {len(eval_records)} cases "
              "(smoke-test mode, NOT the full experiment).")

    print(f"Processing {len(eval_records)} cases x 3 arms (arm 1: reused, 0 LLM calls; "
          f"arm 5: real LLM calls, model={args.model}; arm 6: rule-based, 0 LLM calls)...")
    results = _parallel_map(
        lambda case: process_case(case, model=args.model),
        eval_records, max_workers=args.max_workers, label="nuggetindex-exp3")

    summary = build_summary(results, derivation)

    report = {
        "run_date": datetime.date.today().isoformat(),
        "experiment": "nuggetindex_exp3_repair_reliability_reduced_3arm",
        "note": (
            "Reduced-scope Experiment 3 for NuggetIndex: 3 of the 6 arms "
            "../../run_experiment_3.py runs for FactoidWiki (arm 1 no-elicitation, arm 5 "
            "parent-segment fallback, arm 6 flagged deferral). Arms 2/3/4 (Disco-RAG, "
            "custom fallback, Contextual Retrieval) are NOT run -- see arms_not_run_note. "
            "See this report's top-of-file module docstring (run_nuggetindex_exp3.py) for "
            "the full reasoning."
        ),
        "arms_not_run_note": ARMS_NOT_RUN_NOTE,
        "render_triple_exception_note": RENDER_TRIPLE_EXCEPTION_NOTE,
        "failure_type_scope_note": FAILURE_TYPE_SCOPE_NOTE,
        "attribution": {
            "flagged_deferral": (
                "Arm 6 runs server/components/risk_triage.py's flag_claim, imported "
                "UNMODIFIED, per NuggetIndex triple (rendered via render_triple -- see "
                "render_triple_exception_note) with segment_text = the source paragraph. "
                "It incorporates nothing automatically; it only surfaces cases for human "
                "review. Judge verdict reused from arm 1 (flags do not change the triples)."
            ),
            "parent_segment_fallback": (
                "Arm 5 reuses severance_judge_paragraph.py and exp3_scoring_paragraph.py "
                "from ../../ (factoidwiki_track/) UNMODIFIED, per explicit task "
                "instruction -- this arm's output is genuine natural-language paragraph "
                "text, not a triple conversion, so reusing the existing natural-language "
                "judge/classifier is a correct fit, not a naturalization confound."
            ),
        },
        "reproducibility": {
            "model": args.model,
            "temperature": TEMPERATURE,
            "seed": SEED,
            "arm5_severance_judge": "severance_judge_paragraph.llm_judge_paragraph_severance "
                                    "(factoidwiki_track/, imported unmodified)",
            "arm5_failure_type_classifier": "exp3_scoring_paragraph.classify_failure_type "
                                            "(factoidwiki_track/, imported unmodified; run only "
                                            "on arm-5 cases the judge scores severed)",
            "arm1_arm6_severance_judge": (
                "triple_severance_judge.llm_judge_triple_severance / "
                "llm_judge_triple_severance_subclause (nuggetindex_track/) -- verdicts "
                "REUSED from ../logs/nuggetindex_govern_log.jsonl and "
                "../results/nuggetindex_nucleus_bundling_audit.json; ZERO new calls made "
                "by this script for arms 1 or 6."
            ),
            "arm6_flag_source": "server/components/risk_triage.py flag_claim, imported UNMODIFIED, 0 LLM calls",
            "llm_call_counts": dict(CALL_COUNTER),
        },
        "eval_set_derivation": derivation,
        "summary": summary,
        "records": results,
    }

    with open(args.report_file, "w", encoding="utf-8") as fh:
        json.dump(report, fh, indent=2, ensure_ascii=False)

    elapsed = time.time() - start
    print(f"\nDone in {elapsed:.0f}s. Real LLM calls: {dict(CALL_COUNTER)}")
    print(f"Wrote {args.report_file}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
