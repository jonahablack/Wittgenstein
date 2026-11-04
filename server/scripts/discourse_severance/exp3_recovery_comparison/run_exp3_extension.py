"""Experiment 3 extension: two new recovery arms + a confidence-
calibration retrofit, added on top of the ALREADY-COMPLETE 4-arm
comparison (run_exp3.py / exp3_report.json / RESULTS.md).

This script is strictly ADDITIVE. It:
  - loads the EXISTING exp3_report.json (does not regenerate conditions
    1-4; arms 2/3's original claims/judge/wrongness outputs are read
    as-is, never recomputed),
  - re-derives the fixed 38-case eval set from the ORIGINAL source
    files (../discourse_severance_report.json + ../audit_addendum.json)
    via run_exp3.derive_eval_set and asserts it is IDENTICAL to the
    case set already saved in exp3_report.json -- refuses to run on
    anything else,
  - adds two new per-case arms (condition_5, condition_6) and a new
    "calibration" field on three existing arms,
  - writes the augmented dict back to exp3_report.json (every existing
    key/value is preserved; only new keys are added), and
  - APPENDS (does not rewrite) a new, dated, top-level section to
    RESULTS.md, matching this project's own established addendum
    convention (see ../RESULTS.md's "# Audit addendum (2026-08-07)"
    and "# Exception reclassification addendum (2026-08-11)" sections).

Numbering (documented once here, used consistently in the appended
RESULTS.md section and in every report of these results): this project
uses the TASK-level arm numbering 1-6 as the prose numbering for ALL
six arms. That numbering maps onto this codebase's two PRE-EXISTING,
already-committed internal naming conventions as follows -- neither
pre-existing convention is renamed (extend, don't overwrite: the
original RESULTS.md sections already say "arm 1 (Disco-RAG, adapted)"
in prose, and that text is not touched):

  task #  description                              per-case JSON key                      pre-existing summary JSON key
  1       No elicitation (baseline)                 condition_1_no_elicitation              n/a (eval_set only)
  2       Disco-RAG, adapted                        condition_2_disco_rag                   arm_1_disco_rag        <- pre-existing "arm 1"
  3       Custom fallback                           condition_3_custom_fallback              arm_2_custom_fallback  <- pre-existing "arm 2"
  4       Flagged deferral                          condition_4_flags                        condition_4_flag_summary
  5 (NEW) Contextual Retrieval (Anthropic method)    condition_5_contextual_retrieval         arm_3_contextual_retrieval  (continues the pre-existing arm_N sequence: arm_1, arm_2, arm_3)
  6 (NEW) Parent-segment / sentence-window fallback  condition_6_parent_segment_fallback      condition_6_parent_segment_summary  (kept OUT of the arm_N family, like condition_4 -- ceiling check, not a competitive arm)

The pre-existing "arm_1"/"arm_2" JSON summary keys therefore correspond
to TASK arms 2 and 3, not task arms 1 and 2 -- this off-by-one predates
this extension (it was already in run_exp3.py) and is preserved as-is
rather than renamed. All PROSE in this script's docstrings, in the
appended RESULTS.md section, and in this run's final report uses the
unambiguous task numbering (1-6) throughout.

Confidence-calibration field scope (documented discrepancy in the task
spec, resolved here): the task spec's section header read "add the
confidence-calibration field to ALL FIVE non-baseline arms (2,3,5,6..."
-- four numbers, not five, and omitting 4 -- but its own body text
immediately scoped the field to EXACTLY THREE arms by name, with
reasons given for excluding the other two: "for every case scored
dangerous-failure or detectable-failure in the Disco-RAG, custom-
fallback, and Contextual-Retrieval arms (not the parent-segment arm,
which doesn't fail in the same sense, and not flagged-deferral, which
is a different kind of arm)". The reasoned, specific body text is
treated as authoritative over the header's inconsistent count/list;
this script implements calibration for EXACTLY those three arms
(condition_2, condition_3, condition_5) and excludes condition_4 and
condition_6. This resolution is repeated in the appended RESULTS.md
section so it is never silently assumed.

Usage
-----
    venv/bin/python server/scripts/discourse_severance/exp3_recovery_comparison/run_exp3_extension.py

No --self-test flag: this extension reuses run_exp3.py's already
self-tested judge/wrongness/cross-tab machinery directly (see inline
comments at each reuse site) rather than re-implementing it, so the
only genuinely NEW logic here -- section-context resolution
(contextual_retrieval_arm.py), context generation, and the hedging
classifier (calibration_scoring.py) -- was smoke-tested offline against
all 38 real sentences (section resolution) and read over for prompt-
construction correctness before being run against the live API; a
synthetic-fixture self-test in the style of self_test_exp3.py was not
built for this extension (scope decision, stated plainly rather than
left unstated).
"""

import argparse
import datetime
import json
import os
import sys
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed

EXP3_DIR = os.path.dirname(os.path.abspath(__file__))
SCRIPT_DIR = os.path.dirname(EXP3_DIR)          # .../discourse_severance
SERVER_DIR = os.path.dirname(os.path.dirname(SCRIPT_DIR))
if SERVER_DIR not in sys.path:
    sys.path.insert(0, SERVER_DIR)

from scripts.discourse_severance import severance_detection  # noqa: E402
from scripts.discourse_severance.exp3_recovery_comparison import (  # noqa: E402
    calibration_scoring,
    contextual_retrieval_arm,
    run_exp3,
)

# Importing run_exp3 already ran _load_server_env() at module import time
# (its own top-level call), so OPENAI_API_KEY is available here too.

JSON_REPORT = run_exp3.JSON_REPORT
MD_REPORT = run_exp3.MD_REPORT
MODEL = run_exp3.MODEL
TEMPERATURE = run_exp3.TEMPERATURE
SEED = run_exp3.SEED
MAX_WORKERS = run_exp3.MAX_WORKERS
EXPECTED_EVAL_N = run_exp3.EXPECTED_EVAL_N

# New per-case keys, registered into run_exp3's existing arm-key ->
# display-label registry so its ALREADY-TESTED summarize_arm()/
# cross_tab() functions can be reused VERBATIM for the two new arms
# instead of re-implementing that logic (extend, don't rebuild -- the
# registry is exactly the extensibility point that machinery already
# exposes). This mutation is explicit, one-time, and documented here --
# never a hidden side effect.
CONDITION_5_KEY = "condition_5_contextual_retrieval"
CONDITION_6_KEY = "condition_6_parent_segment_fallback"
NEW_ARM_LABELS = {
    CONDITION_5_KEY: "arm 5 (Contextual Retrieval, Anthropic method)",
    CONDITION_6_KEY: "arm 6 (parent-segment/sentence-window fallback, ceiling check)",
}
run_exp3.ARM_KEYS.update(NEW_ARM_LABELS)

# Confidence-calibration field scope -- see module docstring for the
# spec-discrepancy resolution. Exactly these three arms.
CALIBRATION_ARM_KEYS = [
    "condition_2_disco_rag",
    "condition_3_custom_fallback",
    CONDITION_5_KEY,
]
CALIBRATION_EXCLUDED_ARM_KEYS = ["condition_4_flags", CONDITION_6_KEY]

PARENT_SEGMENT_STATEMENT = (
    "Arm 6 returns the ORIGINAL, un-atomized source sentence "
    "(condition_1_no_elicitation's own `sentence` field, i.e. exactly "
    "the same text saved per case throughout this experiment) as the "
    "sole 'claim'. Nothing was split, so the discourse relation was "
    "never severed in the first place -- this arm is a ceiling/reality-"
    "check on the judge and scoring pipeline, not a competitive "
    "recovery strategy, per the task specification. A less-than-100% "
    "correct-recovery rate here would indicate primary-judge strictness "
    "or noise in the judging pipeline itself, not a recovery failure, "
    "and is reported plainly either way."
)

CALIBRATION_SCOPE_STATEMENT = (
    "Computed for arms 2 (Disco-RAG), 3 (custom fallback), and 5 "
    "(Contextual Retrieval) only -- every case where that arm's primary "
    "judge (judge_full_nucleus) scored preserved=False, i.e. EITHER "
    "wrongness category (dangerous/fluent_but_wrong OR "
    "detectable/visibly_incomplete_or_garbled). NOT computed for arm 4 "
    "(flagged deferral -- a different kind of arm, produces flags, not "
    "a claim set of its own to hedge) or arm 6 (parent-segment "
    "fallback -- a ceiling/reality-check arm, not scored as a failure "
    "mode in the same sense). See this script's module docstring for "
    "the task-spec discrepancy this scope resolves."
)

CALL_COUNTER = Counter()
_COUNTER_LOCK = __import__("threading").Lock()


def _count(key, n=1):
    with _COUNTER_LOCK:
        CALL_COUNTER[key] += n


# --- load + validate (fail fast, never resample) ------------------------------


def load_existing_report():
    if not os.path.exists(JSON_REPORT):
        raise RuntimeError(
            f"FATAL: {JSON_REPORT} not found -- run run_exp3.py first; "
            "this extension only ever ADDS to an existing 4-arm report."
        )
    with open(JSON_REPORT, encoding="utf-8") as fh:
        return json.load(fh)


def preflight_api_check(model=None):
    """One minimal, non-retried API call before touching any of the 38
    cases -- fail in a couple of seconds, not after grinding through
    38 cases x several call sites x 3 retries each with exponential
    backoff, all doomed for the same account-level reason (repo
    convention: "Better to crash in 1 second than run for 10 hours
    with wrong behavior"). Raises RuntimeError with the raw API error
    on any failure; never silently proceeds to write a report full of
    null/failed calls.
    """
    import openai

    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError(
            "FATAL: OPENAI_API_KEY is not set -- cannot run the extension."
        )
    client = openai.OpenAI(api_key=api_key)
    try:
        client.chat.completions.create(
            model=model or MODEL,
            messages=[{"role": "user", "content": "reply with: ok"}],
            max_tokens=5,
        )
    except Exception as exc:
        raise RuntimeError(
            f"FATAL: preflight API check failed ({type(exc).__name__}: {exc}) "
            "-- refusing to start the 38-case run (would just grind through "
            "guaranteed-to-fail retries and append a null-filled report). "
            "Fix API access (e.g. add credits to the OpenAI account behind "
            "OPENAI_API_KEY) and re-run."
        ) from exc


def verify_fixed_eval_set(report):
    """Re-derives the eval set from the ORIGINAL source reports the
    exact way run_exp3.derive_eval_set does (which itself asserts the
    39/38/5/1 invariants), and asserts the result is IDENTICAL to the
    case set already saved in exp3_report.json. Fails loudly on any
    mismatch rather than silently extending a different set.
    """
    with open(run_exp3.SOURCE_REPORT, encoding="utf-8") as fh:
        source = json.load(fh)
    with open(run_exp3.AUDIT_ADDENDUM, encoding="utf-8") as fh:
        addendum = json.load(fh)
    fresh_records, derivation = run_exp3.derive_eval_set(source, addendum)

    fresh_ids = {r["id"] for r in fresh_records}
    saved_ids = {r["id"] for r in report["records"]}
    if fresh_ids != saved_ids:
        raise AssertionError(
            "FATAL: eval set mismatch between exp3_report.json and a fresh "
            f"re-derivation. Saved-only: {sorted(saved_ids - fresh_ids)}; "
            f"fresh-only: {sorted(fresh_ids - saved_ids)}. Refusing to "
            "extend a report that does not match the fixed 38-case set."
        )
    if len(saved_ids) != EXPECTED_EVAL_N:
        raise AssertionError(
            f"FATAL: expected {EXPECTED_EVAL_N} cases, found {len(saved_ids)}."
        )
    return derivation


# --- arm 5 / arm 6 per-case processing ----------------------------------------


def process_new_arms(rec, model=None):
    """Adds condition_5 (Contextual Retrieval) and condition_6
    (parent-segment fallback) to one existing per-case record IN
    PLACE. Scoring reuses run_exp3._judge_arm VERBATIM -- the exact
    same judge (severance_detection.llm_judge_severance /
    llm_judge_severance_subclause) + wrongness pipeline
    (exp3_scoring.classify_wrongness) as arms 2/3, per the task's
    instruction to reuse exp3_scoring.py's existing judge logic rather
    than build a new one.
    """
    claims_in = rec["condition_1_no_elicitation"]["claims"]  # == condition_a_claims

    # --- Arm 5: Contextual Retrieval context injection ----------------
    arm5 = {
        "claims": None, "generated_context": None,
        "document_context_citation": None, "document_context_char_len": None,
        "context_only_judge": None, "error": None,
    }
    try:
        section = contextual_retrieval_arm.resolve_section_context(
            rec["part_label"], rec["sentence"])
        arm5["document_context_citation"] = section["citation"]
        arm5["document_context_char_len"] = section["char_len"]
        context_text, err = contextual_retrieval_arm.generate_context(
            section["section_text"], claims_in, model=model)
        _count("contextual_retrieval_context_gen")
        if err:
            arm5["error"] = f"context_generation_failed:{err}"
        else:
            arm5["generated_context"] = context_text
            arm5["claims"] = [context_text] + list(claims_in)
            # Diagnostic (task spec): does the generated context ALONE
            # state the missing relation? Reuses severance_detection's
            # judge UNCHANGED, applied to [context_text] as the sole
            # text a reader would see -- not a new judge.
            arm5["context_only_judge"] = severance_detection.llm_judge_severance(
                rec["sentence"], rec["relation"], [context_text], model=model)
            _count("contextual_retrieval_context_only_judge")
    except Exception as exc:  # recorded loudly, run continues past one case
        arm5["error"] = f"{type(exc).__name__}: {exc}"
    arm5.update(run_exp3._judge_arm(rec, arm5.get("claims"), model=model))
    rec[CONDITION_5_KEY] = arm5

    # --- Arm 6: parent-segment / sentence-window fallback -------------
    arm6 = {"claims": [rec["sentence"]], "error": None}
    arm6.update(run_exp3._judge_arm(rec, arm6["claims"], model=model))
    rec[CONDITION_6_KEY] = arm6

    return rec


# --- confidence-calibration retrofit -------------------------------------------


def add_calibration(rec, model=None):
    """Retrofits a 'calibration' field onto CALIBRATION_ARM_KEYS for
    every case where that arm's own judge_full_nucleus.preserved is
    False. condition_2/3's claims are the ALREADY-SAVED outputs from
    the original run (read, never regenerated); condition_5's claims
    were just computed by process_new_arms above. Cases the arm scored
    correct get calibration=None (explicit not-applicable, never a
    silently-skipped key).
    """
    for arm_key in CALIBRATION_ARM_KEYS:
        arm = rec[arm_key]
        judge = arm.get("judge_full_nucleus")
        is_failure = judge is not None and judge.get("preserved") is False
        if not is_failure:
            arm["calibration"] = None
            continue
        claims = arm.get("claims")
        result = calibration_scoring.classify_hedging(claims, model=model)
        _count(f"hedging_classifier__{arm_key}")
        wrongness_category = (arm.get("wrongness") or {}).get("category")
        arm["calibration"] = {
            "applicable": True,
            "wrongness_category": wrongness_category,
            **result,
        }
    return rec


# --- summaries (new arms) ------------------------------------------------------


def subclause_side_by_side_new_arms(records):
    """Same style as run_exp3.subclause_side_by_side, parameterized for
    the two new arms (kept as a separate table -- the original
    subclause_side_by_side_bundled_cases key, arms 1/2 only, is left
    untouched)."""
    rows = []
    for r in records:
        if not r["bundled_nucleus"]:
            continue
        row = {"id": r["id"], "relation_type": r["relation"]["relation_type"]}
        for arm_key, short in ((CONDITION_5_KEY, "arm5"), (CONDITION_6_KEY, "arm6")):
            arm = r[arm_key]
            fn = arm.get("judge_full_nucleus")
            sc = arm.get("judge_subclause")
            row[f"{short}_full_nucleus"] = None if fn is None else fn["preserved"]
            row[f"{short}_subclause"] = None if sc is None else sc["preserved"]
        rows.append(row)
    return rows


def confidently_wrong_docs_new_arms(records):
    """Same documentation shape as run_exp3.confidently_wrong_docs, for
    the two NEW arms only -- a separate list; the existing
    confidently_wrong_documentation key (arms 2/3) is left untouched."""
    docs = []
    for r in records:
        for arm_key in (CONDITION_5_KEY, CONDITION_6_KEY):
            arm = r[arm_key]
            judge = arm.get("judge_full_nucleus")
            if judge is None or judge.get("preserved") is not False:
                continue
            if (arm.get("wrongness") or {}).get("category") != "fluent_but_wrong":
                continue
            docs.append({
                "id": r["id"],
                "arm": run_exp3.ARM_KEYS[arm_key],
                "a2_flagged": r["a2_flagged"],
                "relation_type": r["relation"]["relation_type"],
                "sentence": r["sentence"],
                "nucleus": r["relation"]["nucleus"],
                "satellite": r["relation"]["satellite"],
                "connective": r["relation"]["connective"],
                "arm_output_claims": arm.get("claims"),
                "why_wrong_judge": judge["reasoning"],
                "why_confidently_wrong": arm["wrongness"]["reasoning"],
                "flag_fired": r["condition_4_flags"]["any_flag_fired"],
                "flag_types": r["condition_4_flags"]["flag_types_fired"],
                "subclause_verdict": (
                    None if arm.get("judge_subclause") is None
                    else arm["judge_subclause"]["preserved"]),
            })
    return docs


def context_diagnostic_summary(records):
    """Arm-5-specific diagnostic (task spec): how often does the
    generated context sentence ALONE state the missing relation, and
    how does that line up with whether the combined (context+claims)
    output was actually scored correct?"""
    rows = []
    n_scored = 0
    n_context_states_relation = 0
    n_context_states_and_combined_correct = 0
    n_context_states_but_combined_wrong = 0
    n_context_silent_but_combined_correct = 0
    for r in records:
        arm5 = r[CONDITION_5_KEY]
        cj = arm5.get("context_only_judge")
        if cj is None or cj.get("preserved") is None:
            continue
        n_scored += 1
        states_relation = bool(cj["preserved"])
        combined_judge = arm5.get("judge_full_nucleus")
        combined_correct = (
            None if combined_judge is None else combined_judge.get("preserved"))
        if states_relation:
            n_context_states_relation += 1
            if combined_correct is True:
                n_context_states_and_combined_correct += 1
            elif combined_correct is False:
                n_context_states_but_combined_wrong += 1
        elif combined_correct is True:
            n_context_silent_but_combined_correct += 1
        rows.append({
            "id": r["id"],
            "context_alone_states_relation": states_relation,
            "combined_output_scored_correct": combined_correct,
            "generated_context": arm5.get("generated_context"),
        })
    return {
        "n_scored": n_scored,
        "n_context_alone_states_relation": n_context_states_relation,
        "rate_context_alone_states_relation": (
            n_context_states_relation / n_scored if n_scored else None),
        "n_context_states_relation_and_combined_correct": n_context_states_and_combined_correct,
        "n_context_states_relation_but_combined_still_wrong": n_context_states_but_combined_wrong,
        "n_context_silent_but_combined_correct_anyway": n_context_silent_but_combined_correct,
        "per_case": rows,
    }


def calibration_summary(records):
    """Hedged-vs-unhedged rate among each in-scope arm's failures, plus
    a breakdown by wrongness category and a 2x2 against
    condition_4_flags' any_flag_fired -- the explicit, reportable
    comparison against risk_triage.py's INDEPENDENT flag signal (never
    merged with it)."""
    out = {}
    for arm_key in CALIBRATION_ARM_KEYS:
        n_failures = 0
        n_hedged = 0
        n_unhedged = 0
        n_unclassified = 0
        by_category = {}
        two_by_two = {"hedged_and_flagged": 0, "hedged_not_flagged": 0,
                      "unhedged_and_flagged": 0, "unhedged_not_flagged": 0}
        cases = []
        for r in records:
            cal = r[arm_key].get("calibration")
            if cal is None or not cal.get("applicable"):
                continue
            n_failures += 1
            cat = cal.get("wrongness_category") or "unclassified"
            by_category.setdefault(cat, {"n": 0, "hedged": 0})
            by_category[cat]["n"] += 1
            hedged = cal.get("hedged")
            flagged = r["condition_4_flags"]["any_flag_fired"]
            if hedged is True:
                n_hedged += 1
                by_category[cat]["hedged"] += 1
                two_by_two["hedged_and_flagged" if flagged else "hedged_not_flagged"] += 1
            elif hedged is False:
                n_unhedged += 1
                two_by_two["unhedged_and_flagged" if flagged else "unhedged_not_flagged"] += 1
            else:
                n_unclassified += 1
            cases.append({
                "id": r["id"], "wrongness_category": cat, "hedged": hedged,
                "evidence_phrases": cal.get("evidence_phrases", []),
                "risk_triage_flag_fired": flagged,
            })
        out[arm_key] = {
            "label": run_exp3.ARM_KEYS[arm_key],
            "n_failures_all_38": n_failures,
            "n_hedged": n_hedged,
            "n_unhedged": n_unhedged,
            "n_calibration_call_unclassified": n_unclassified,
            "hedged_rate_among_failures": (n_hedged / n_failures) if n_failures else None,
            "by_wrongness_category": by_category,
            "hedged_vs_risk_triage_flag_2x2": two_by_two,
            "cases": cases,
        }
    return out


NUMBERING_KEY = {
    "description": (
        "Task-level arm numbering (1-6), the prose numbering used "
        "throughout this extension's writeup, mapped to this JSON's "
        "actual field names. Fields for arms 1-4 and their arm_1_/"
        "arm_2_-prefixed summary keys are UNCHANGED from the original "
        "run_exp3.py output, INCLUDING the pre-existing off-by-one "
        "between 'condition_N' per-case keys (which follow 1-6 "
        "cleanly) and 'arm_N' summary keys (which only count the "
        "automated-recovery arms, so arm_1==condition_2, "
        "arm_2==condition_3) -- that convention predates this "
        "extension and is preserved as-is rather than renamed."
    ),
    "1_no_elicitation": {
        "per_case_key": "condition_1_no_elicitation", "summary_key": None,
        "note": "baseline; reused verbatim from ../discourse_severance_report.json",
    },
    "2_disco_rag_adapted": {
        "per_case_key": "condition_2_disco_rag", "summary_key": "arm_1_disco_rag",
    },
    "3_custom_fallback": {
        "per_case_key": "condition_3_custom_fallback",
        "summary_key": "arm_2_custom_fallback",
    },
    "4_flagged_deferral": {
        "per_case_key": "condition_4_flags",
        "summary_key": "condition_4_flag_summary",
    },
    "5_contextual_retrieval_NEW": {
        "per_case_key": CONDITION_5_KEY,
        "summary_key": "arm_3_contextual_retrieval",
        "note": "NEW in this extension.",
    },
    "6_parent_segment_fallback_NEW": {
        "per_case_key": CONDITION_6_KEY,
        "summary_key": "condition_6_parent_segment_summary",
        "note": (
            "NEW in this extension. Ceiling/reality-check arm, not a "
            "competitive recovery arm -- kept out of the arm_N family "
            "for the same reason condition_4 is."
        ),
    },
    "calibration_field_scope": {
        "arms_with_calibration": CALIBRATION_ARM_KEYS,
        "arms_excluded": CALIBRATION_EXCLUDED_ARM_KEYS,
        "spec_discrepancy_note": (
            "The task spec's section header said 'ALL FIVE non-baseline "
            "arms (2,3,5,6)' (four numbers, not five, and omitting 4), "
            "but its own body text immediately scoped the calibration "
            "field to EXACTLY three arms by name -- Disco-RAG, custom "
            "fallback, Contextual Retrieval -- explicitly excluding "
            "flagged-deferral ('a different kind of arm') and "
            "parent-segment ('doesn't fail in the same sense'). The "
            "reasoned body text is treated as authoritative here; this "
            "resolution is stated explicitly rather than silently "
            "assumed."
        ),
    },
}


def build_extension_summary(records):
    return {
        "arm_3_contextual_retrieval": run_exp3.summarize_arm(records, CONDITION_5_KEY),
        "condition_6_parent_segment_summary": run_exp3.summarize_arm(records, CONDITION_6_KEY),
        "cross_tab_arm_3_vs_flags": run_exp3.cross_tab(records, CONDITION_5_KEY),
        "cross_tab_condition_6_parent_segment_vs_flags": run_exp3.cross_tab(records, CONDITION_6_KEY),
        "subclause_side_by_side_new_arms": subclause_side_by_side_new_arms(records),
        "confidently_wrong_documentation_new_arms": confidently_wrong_docs_new_arms(records),
        "context_states_missing_relation_diagnostic": context_diagnostic_summary(records),
        "calibration_summary": calibration_summary(records),
        "calibration_scope_statement": CALIBRATION_SCOPE_STATEMENT,
        "numbering_key": NUMBERING_KEY,
    }


# --- parallel map (reuse run_exp3's pattern) -----------------------------------


def _parallel_map(func, items, max_workers=MAX_WORKERS, desc=""):
    results = [None] * len(items)
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_idx = {executor.submit(func, item): i for i, item in enumerate(items)}
        done = 0
        for future in as_completed(future_to_idx):
            i = future_to_idx[future]
            results[i] = future.result()
            done += 1
            if desc:
                print(f"  {desc}: {done}/{len(items)} done ({items[i]['id']})")
    return results


# --- writers (additive) --------------------------------------------------------


def write_extended_json_report(report, extension_summary, records, path=JSON_REPORT):
    report["records"] = records
    report["summary"].update(extension_summary)
    report["extension"] = {
        "run_date": datetime.date.today().isoformat(),
        "description": (
            "Adds two new recovery arms (5: Contextual Retrieval context "
            "injection, Anthropic's published method; 6: parent-segment/"
            "sentence-window fallback, a ceiling/reality-check) on the "
            "SAME fixed 38-case set as the original run, plus a "
            "confidence-calibration (hedging) field retrofitted onto "
            "arms 2, 3, and 5. Original run_date/attribution/"
            "reproducibility fields, and the original summary/records "
            "keys, are UNCHANGED except for additive new keys within "
            "them -- nothing from the original 4-arm run was "
            "recomputed, deleted, or overwritten."
        ),
        "numbering_key": NUMBERING_KEY,
        "new_arm_attribution": {
            "contextual_retrieval": contextual_retrieval_arm.CONTEXTUAL_RETRIEVAL_STATEMENT,
            "contextual_retrieval_document_context_method": contextual_retrieval_arm.SECTION_RESOLUTION_STATEMENT,
            "parent_segment_fallback": PARENT_SEGMENT_STATEMENT,
            "calibration_scope": CALIBRATION_SCOPE_STATEMENT,
        },
        "new_reproducibility": {
            "model": MODEL, "temperature": TEMPERATURE, "seed": SEED,
            "contextual_retrieval_prompt_template": contextual_retrieval_arm.CONTEXT_PROMPT_TEMPLATE_DISPLAY,
            "contextual_retrieval_source": contextual_retrieval_arm.CONTEXTUAL_RETRIEVAL_SOURCE_URL,
            "hedging_classifier_prompt_marker": calibration_scoring.HEDGING_PROMPT_MARKER,
        },
        "llm_call_counts_extension": {**dict(CALL_COUNTER), **dict(run_exp3.CALL_COUNTER)},
    }
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(report, fh, indent=2, ensure_ascii=False)
    return path


def _fmt(n, d):
    return run_exp3._fmt(n, d)


def _pres(v):
    return run_exp3._pres(v)


def _pct(n, d):
    if not d:
        return "n/a"
    return f"{n}/{d} ({100 * n / d:.1f}%)"


def build_markdown_section(report, extension_summary, records, derivation):
    s5 = extension_summary["arm_3_contextual_retrieval"]
    s6 = extension_summary["condition_6_parent_segment_summary"]
    ct5 = extension_summary["cross_tab_arm_3_vs_flags"]
    ct6 = extension_summary["cross_tab_condition_6_parent_segment_vs_flags"]
    diag = extension_summary["context_states_missing_relation_diagnostic"]
    cal = extension_summary["calibration_summary"]
    today = datetime.date.today().isoformat()

    lines = [
        "",
        f"# Experiment 3 extension ({today}): Contextual Retrieval + "
        "parent-segment arms, confidence-calibration addendum",
        "",
        "Run date: " + today + ". Generated by "
        "`server/scripts/discourse_severance/exp3_recovery_comparison/"
        "run_exp3_extension.py`, appended to (never overwriting) the "
        "4-arm comparison above. Same fixed 38-case set as every "
        "section above -- re-derived from "
        "`../discourse_severance_report.json` + `../audit_addendum.json` "
        "via the ORIGINAL `run_exp3.derive_eval_set` and asserted "
        f"identical to the 38 cases already in `exp3_report.json` "
        "before anything else ran (see module docstring). Arms 2/3's "
        "original claims/judge/wrongness outputs are read as-is from "
        "the existing report and never regenerated.",
        "",
        "## Numbering (read first)",
        "",
        "This section uses the TASK-level arm numbering 1-6 in all "
        "prose. Arms 1-4 are exactly the four arms described earlier in "
        "this file; arms 5 and 6 are new. Internally, "
        "`exp3_report.json`'s per-case keys follow this numbering "
        "cleanly (`condition_1_..` .. `condition_6_..`), but its "
        "PRE-EXISTING aggregate summary keys (`arm_1_disco_rag`, "
        "`arm_2_custom_fallback`) only count automated-recovery arms and "
        "so are off by one from the task numbering (`arm_1` == task arm "
        "2, `arm_2` == task arm 3) -- that convention predates this "
        "extension and is kept as-is rather than renamed. New summary "
        "keys continue that same pre-existing convention: task arm 5 -> "
        "`arm_3_contextual_retrieval`; task arm 6 -> "
        "`condition_6_parent_segment_summary` (kept out of the `arm_N` "
        "family, like `condition_4`, since the task spec calls it a "
        "ceiling check, not a competitive arm). Full table:",
        "",
        "| Task arm # | Description | Per-case JSON key | Summary JSON key |",
        "|---|---|---|---|",
        "| 1 | No elicitation (baseline) | `condition_1_no_elicitation` | n/a |",
        "| 2 | Disco-RAG, adapted | `condition_2_disco_rag` | `arm_1_disco_rag` |",
        "| 3 | Custom fallback | `condition_3_custom_fallback` | `arm_2_custom_fallback` |",
        "| 4 | Flagged deferral | `condition_4_flags` | `condition_4_flag_summary` |",
        "| 5 (NEW) | Contextual Retrieval | `condition_5_contextual_retrieval` | `arm_3_contextual_retrieval` |",
        "| 6 (NEW) | Parent-segment fallback | `condition_6_parent_segment_fallback` | `condition_6_parent_segment_summary` |",
        "",
        "## Confidence-calibration field scope (spec discrepancy, resolved)",
        "",
        CALIBRATION_SCOPE_STATEMENT,
        "",
        "The task spec's own section header read \"ALL FIVE non-baseline "
        "arms (2,3,5,6)\" -- four numbers, not five, omitting 4 -- "
        "immediately followed by body text naming exactly three arms "
        "(Disco-RAG, custom fallback, Contextual Retrieval) with "
        "explicit reasons to exclude the other two. The specific, "
        "reasoned body text is treated as authoritative here.",
        "",
        "## Arm 5: Contextual Retrieval context injection (Anthropic's published method)",
        "",
        contextual_retrieval_arm.CONTEXTUAL_RETRIEVAL_STATEMENT,
        "",
        "Published prompt template (quoted verbatim, "
        f"{contextual_retrieval_arm.CONTEXTUAL_RETRIEVAL_SOURCE_URL}):",
        "",
        "```",
        contextual_retrieval_arm.CONTEXT_PROMPT_TEMPLATE_DISPLAY,
        "```",
        "",
        "`{{CHUNK_CONTENT}}` = the case's atomized (Condition-A) claims, "
        "bullet-listed. `{{WHOLE_DOCUMENT}}` = the enclosing CFR SECTION "
        "text (not the whole CFR part -- see below). The generated "
        "context sentence is PREPENDED to the atomized claims; that "
        "combined [context] + [claims] list is what gets judged, "
        "exactly like every other arm's claim list.",
        "",
        contextual_retrieval_arm.SECTION_RESOLUTION_STATEMENT,
        "",
        "## Arm 6: parent-segment / sentence-window fallback",
        "",
        PARENT_SEGMENT_STATEMENT,
        "",
        "## Scoring",
        "",
        "Both new arms are judged with the EXACT SAME three-way scheme "
        "as arms 2-4: `severance_detection.llm_judge_severance` "
        "(primary; `judge_prompt_subclause` side by side on the "
        "bundled-nucleus subset) plus `exp3_scoring.classify_wrongness` "
        "for cases scored `preserved=False`, via "
        "`run_exp3._judge_arm` reused verbatim -- no new judge was "
        "built. correct = `preserved=True`; **dangerous** = "
        "`fluent_but_wrong`; **detectable** = "
        "`visibly_incomplete_or_garbled`.",
        "",
        "## Per-arm results (all 38 cases)",
        "",
        "| Arm | Reading | Correct recovery | Dangerous (confidently wrong) | Detectable (visibly garbled) |",
        "|---|---|---|---|---|",
    ]

    for label, summ in ((NEW_ARM_LABELS[CONDITION_5_KEY], s5),
                        (NEW_ARM_LABELS[CONDITION_6_KEY], s6)):
        p = summ["all_38"]["full_nucleus_primary"]
        alt = summ["all_38"]["subclause_alternative_reading"]
        lines.append(
            f"| {label} | full-nucleus (primary) | "
            f"{_fmt(p['n_correct'], p['n_scored'])} | "
            f"{_fmt(p['n_confidently_wrong'], p['n_scored'])} | "
            f"{_fmt(p['n_visibly_incomplete_or_garbled'], p['n_scored'])} |")
        lines.append(
            f"| {label} | sub-clause alternative (bundled cases re-read) | "
            f"{_fmt(alt['n_correct'], alt['n_scored'])} | "
            "(classified under primary reading) | |")

    lines += [
        "",
        "### Excluding the 5 `a2_flagged` cases (n=33)",
        "",
        "| Arm | Reading | Correct recovery | Dangerous (confidently wrong) |",
        "|---|---|---|---|",
    ]
    for label, summ in ((NEW_ARM_LABELS[CONDITION_5_KEY], s5),
                        (NEW_ARM_LABELS[CONDITION_6_KEY], s6)):
        p = summ["excluding_a2_flagged"]["full_nucleus_primary"]
        alt = summ["excluding_a2_flagged"]["subclause_alternative_reading"]
        lines.append(
            f"| {label} | full-nucleus (primary) | "
            f"{_fmt(p['n_correct'], p['n_scored'])} | "
            f"{_fmt(p['n_confidently_wrong'], p['n_scored'])} |")
        lines.append(
            f"| {label} | sub-clause alternative | "
            f"{_fmt(alt['n_correct'], alt['n_scored'])} | |")

    if s5["n_arm_errors"] or s6["n_arm_errors"]:
        lines += [
            "",
            f"Arm errors (call failures, recorded per case, not scored): "
            f"arm 5: {s5['n_arm_errors']}, arm 6: {s6['n_arm_errors']}.",
        ]

    lines += [
        "",
        "**Read this plainly, not optimistically**: arm 6 replays the "
        "original, unsplit sentence, so a correct-recovery rate below "
        "100% here is a property of the judge/scoring pipeline (or of "
        "the underlying relation elicitation itself), not a recovery "
        "failure -- reported as observed, not adjusted.",
        "",
        "### Bundled-nucleus cases: both judge readings side by side (arms 5 and 6)",
        "",
        "| ID | Relation | Arm 5 full-nucleus | Arm 5 sub-clause | "
        "Arm 6 full-nucleus | Arm 6 sub-clause |",
        "|---|---|---|---|---|---|",
    ]
    for row in extension_summary["subclause_side_by_side_new_arms"]:
        lines.append(
            f"| {row['id']} | {row['relation_type']} | "
            f"{_pres(row['arm5_full_nucleus'])} | {_pres(row['arm5_subclause'])} | "
            f"{_pres(row['arm6_full_nucleus'])} | {_pres(row['arm6_subclause'])} |")

    lines += [
        "",
        "## Arm-5 diagnostic: does the generated context sentence ALONE "
        "state the missing relation?",
        "",
        "Separate from the combined [context]+[claims] scoring above: "
        "`severance_detection.llm_judge_severance` applied to "
        "`[generated_context]` alone (not a new judge -- the existing "
        "judge, reused, given only the context sentence as \"what a "
        "reader would see\").",
        "",
        f"- Context sentence alone states the missing relation: "
        f"{_pct(diag['n_context_alone_states_relation'], diag['n_scored'])}",
        f"- ...and the combined context+claims output was ALSO scored "
        f"correct: {diag['n_context_states_relation_and_combined_correct']} "
        f"of those cases",
        f"- ...but the combined output was STILL scored wrong anyway: "
        f"{diag['n_context_states_relation_but_combined_still_wrong']} of "
        "those cases",
        f"- Context alone did NOT state the relation, yet the combined "
        f"output was scored correct anyway (claims alone must have "
        f"carried it): "
        f"{diag['n_context_silent_but_combined_correct_anyway']} cases",
        "",
        "## Updated flag-coverage cross-tab (now covering all four "
        "automated/ceiling arms)",
        "",
        "Same question as the original cross-tab, extended to arms 5 "
        "and 6: of the cases an arm got confidently wrong, how many "
        "would flagged deferral (arm 4) have surfaced?",
        "",
    ]

    for label, ct in ((NEW_ARM_LABELS[CONDITION_5_KEY], ct5),
                      (NEW_ARM_LABELS[CONDITION_6_KEY], ct6)):
        lines += [
            f"### {label}",
            "",
            "| Arm outcome (primary reading) | N | Any flag fired | Segment-level flag fired |",
            "|---|---|---|---|",
        ]
        for bucket in ("correct", "fluent_but_wrong",
                       "visibly_incomplete_or_garbled",
                       "wrongness_unclassified", "unscored"):
            row = ct[bucket]
            if row["n"] == 0 and bucket in ("wrongness_unclassified", "unscored"):
                continue
            lines.append(
                f"| {bucket} | {row['n']} | {row['n_any_flag']} | "
                f"{row['n_segment_flag']} |")
        cov = ct["coverage_of_confidently_wrong"]
        fa = ct["false_alarms_on_correct"]
        lines += [
            "",
            f"- **Flag coverage of confidently-wrong cases**: any flag "
            f"{cov['any_flag'][0]}; segment-level flag {cov['segment_flag'][0]}.",
            f"- **False-alarm side** (flags fired where this arm was "
            f"correct): any flag {fa['any_flag'][0]}; segment-level flag "
            f"{fa['segment_flag'][0]}.",
            "",
        ]

    lines += [
        "## Confidence-calibration (hedging) results",
        "",
        CALIBRATION_SCOPE_STATEMENT,
        "",
        "For every in-scope failure case, an independent LLM "
        "classification (`calibration_scoring.classify_hedging`, "
        "no import of or delegation to `risk_triage.py`) asked whether "
        "the arm's own output -- exactly what a downstream reader would "
        "see -- contains hedging/uncertainty language. Hedged-vs-"
        "unhedged rate among each arm's failures:",
        "",
        "| Arm | Failures (of 38) | Hedged | Unhedged | Hedged rate |",
        "|---|---|---|---|---|",
    ]
    for arm_key in CALIBRATION_ARM_KEYS:
        c = cal[arm_key]
        rate = ("n/a" if c["hedged_rate_among_failures"] is None
                else f"{100 * c['hedged_rate_among_failures']:.1f}%")
        lines.append(
            f"| {c['label']} | {c['n_failures_all_38']} | {c['n_hedged']} | "
            f"{c['n_unhedged']} | {rate} |")

    lines += [
        "",
        "### Breakdown by wrongness category",
        "",
        "| Arm | Category | N | Hedged |",
        "|---|---|---|---|",
    ]
    for arm_key in CALIBRATION_ARM_KEYS:
        c = cal[arm_key]
        for cat, stats in sorted(c["by_wrongness_category"].items()):
            lines.append(f"| {c['label']} | {cat} | {stats['n']} | {stats['hedged']} |")

    lines += [
        "",
        "### Hedging vs. risk_triage.py's (independent) flag signal",
        "",
        "2x2 of this run's hedging classifier against "
        "`condition_4_flags.any_flag_fired`, computed on the SAME "
        "failure cases -- these are two independently-derived signals "
        "that are compared here, never merged:",
        "",
        "| Arm | Hedged & flagged | Hedged, not flagged | Unhedged & flagged | Unhedged, not flagged |",
        "|---|---|---|---|---|",
    ]
    for arm_key in CALIBRATION_ARM_KEYS:
        c = cal[arm_key]
        t = c["hedged_vs_risk_triage_flag_2x2"]
        lines.append(
            f"| {c['label']} | {t['hedged_and_flagged']} | "
            f"{t['hedged_not_flagged']} | {t['unhedged_and_flagged']} | "
            f"{t['unhedged_not_flagged']} |")

    n_fbw_hedged_any = sum(
        stats["hedged"]
        for arm_key in CALIBRATION_ARM_KEYS
        for cat, stats in cal[arm_key]["by_wrongness_category"].items()
        if cat == "fluent_but_wrong")
    n_fbw_total = sum(
        stats["n"]
        for arm_key in CALIBRATION_ARM_KEYS
        for cat, stats in cal[arm_key]["by_wrongness_category"].items()
        if cat == "fluent_but_wrong")
    lines += [
        "",
        "**Why this is worth checking even though `fluent_but_wrong` is "
        "*defined* as unhedged**: `exp3_scoring.classify_wrongness` "
        "(the ORIGINAL wrongness classifier, arms 2/3's data unchanged "
        "since the first run) defines its `fluent_but_wrong` category "
        "as, in part, \"no hedging, no caveat or flag\" -- so by that "
        "classifier's own construction, every `fluent_but_wrong` case "
        "should already be unhedged. Running a SEPARATE, independent "
        "hedging classification over the exact same output text is a "
        "genuine check on whether that original judgment holds up, not "
        "a redundant re-ask. Result on the "
        f"`fluent_but_wrong`-labeled cases across arms 2/3/5: "
        f"{n_fbw_hedged_any}/{n_fbw_total} were nonetheless flagged "
        "hedged by the independent classifier "
        f"({_pct(n_fbw_hedged_any, n_fbw_total)}). Any disagreement here "
        "is reported as a real inter-classifier finding, not smoothed "
        "over -- consistent with how this project already reports "
        "rule-based-vs-LLM-judge disagreement elsewhere "
        "(`severance_detection.py`).",
        "",
    ]

    docs = extension_summary["confidently_wrong_documentation_new_arms"]
    lines += [
        f"## Confidently-wrong case documentation, new arms ({len(docs)} "
        "arm-case instances)",
        "",
    ]
    if not docs:
        lines.append(
            "None -- no case in arms 5 or 6 was scored both "
            "`preserved=False` and `fluent_but_wrong`.")
    for doc in docs:
        a2_tag = " [a2_flagged]" if doc["a2_flagged"] else ""
        lines += [
            "",
            f"**[{doc['relation_type']}] {doc['id']}{a2_tag} -- {doc['arm']}** "
            f"\"{doc['sentence']}\"",
            f"- Nucleus: {doc['nucleus']!r}; Satellite: {doc['satellite']!r}; "
            f"Connective: {doc['connective']!r}",
            f"- Arm output: {doc['arm_output_claims']}",
            f"- Why wrong (judge): {doc['why_wrong_judge']}",
            f"- Why confidently wrong (classifier): {doc['why_confidently_wrong']}",
            f"- Deferral flag fired: {doc['flag_fired']} "
            f"({', '.join(doc['flag_types']) or 'none'})",
        ]
        if doc["subclause_verdict"] is not None:
            lines.append(
                f"- Sub-clause judge reading (bundled nucleus): "
                f"{_pres(doc['subclause_verdict'])}")

    lines += [
        "",
        "## Reproducibility (extension)",
        "",
        f"- All new LLM calls (context generation, context-only judge, "
        f"arm 5/6 primary+subclause judges, wrongness classifier, "
        f"hedging classifier): model `{MODEL}`, temperature={TEMPERATURE}, "
        f"seed={SEED} -- same settings as the original run.",
        "- Contextual Retrieval prompt template (verbatim, "
        f"{contextual_retrieval_arm.CONTEXTUAL_RETRIEVAL_SOURCE_URL}):",
        "  ```",
        *[f"  {ln}" for ln in contextual_retrieval_arm.CONTEXT_PROMPT_TEMPLATE_DISPLAY.split("\n")],
        "  ```",
        f"- Hedging-classifier distinctive prompt marker (for any future "
        f"self-test stub): {calibration_scoring.HEDGING_PROMPT_MARKER!r}",
        f"- Eval-set re-verification: {derivation['n_eval']} cases, "
        "re-derived from the ORIGINAL source files via the ORIGINAL "
        "`run_exp3.derive_eval_set` and asserted identical (by id set) "
        "to the 38 cases already in `exp3_report.json` -- see "
        "`verify_fixed_eval_set` in `run_exp3_extension.py`.",
        f"- LLM call counts, this extension run: "
        f"{ {**dict(CALL_COUNTER), **dict(run_exp3.CALL_COUNTER)} }",
        "- Scope decision, stated plainly: no synthetic-fixture "
        "self-test (in the style of `self_test_exp3.py`) was built for "
        "this extension; the two genuinely new pieces (section-context "
        "resolution, the hedging classifier) were smoke-tested "
        "offline -- section resolution was verified to resolve uniquely "
        "for all 38 real cases, including two structural edge cases "
        "(documented in `contextual_retrieval_arm.py`'s module "
        "docstring), before this script was run against the live API.",
        "",
        "Full machine-readable results (extension fields listed under "
        "`extension`, plus additive `condition_5_*`/`condition_6_*`/"
        "`calibration` keys on the existing per-case records, plus "
        "additive keys in `summary`): "
        "`server/scripts/discourse_severance/exp3_recovery_comparison/"
        "exp3_report.json`.",
        "",
    ]
    return lines


def append_markdown_section(lines, path=MD_REPORT):
    with open(path, encoding="utf-8") as fh:
        existing = fh.read()
    new_section = "\n".join(lines)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(existing.rstrip("\n") + "\n\n" + new_section.lstrip("\n") + "\n")
    return path


# --- entry point ----------------------------------------------------------------


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--model", type=str, default=MODEL)
    args = parser.parse_args(argv)

    start = time.time()
    print("Preflight API check (one minimal call, no retries)...")
    preflight_api_check(model=args.model)
    print("Preflight OK.")

    report = load_existing_report()
    derivation = verify_fixed_eval_set(report)
    records = report["records"]
    print(f"Loaded existing exp3_report.json: {len(records)} cases confirmed "
          f"identical to the fixed eval set (re-derived and checked).")

    print("Pre-warming CFR part XML section index (local parse, no network)...")
    contextual_retrieval_arm.prewarm_part_indexes()

    print(f"Processing {len(records)} cases x 2 new arms "
          f"(model={args.model}, temperature={TEMPERATURE}, seed={SEED})...")
    records = _parallel_map(
        lambda rec: process_new_arms(rec, model=args.model),
        records, desc="new-arms")

    print(f"Retrofitting confidence-calibration onto "
          f"{CALIBRATION_ARM_KEYS} failure cases...")
    records = _parallel_map(
        lambda rec: add_calibration(rec, model=args.model),
        records, desc="calibration")

    extension_summary = build_extension_summary(records)
    json_path = write_extended_json_report(report, extension_summary, records)
    md_lines = build_markdown_section(report, extension_summary, records, derivation)
    md_path = append_markdown_section(md_lines)

    elapsed = time.time() - start
    combined_counts = {**dict(CALL_COUNTER), **dict(run_exp3.CALL_COUNTER)}
    print(f"\nDone in {elapsed:.0f}s. LLM calls: {combined_counts}")
    print(f"Updated {json_path}\nAppended to {md_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
