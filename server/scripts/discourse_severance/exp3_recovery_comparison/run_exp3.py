"""Experiment 3: reliability comparison of recovery strategies on the
sentences whose Condition/Exception/Concession relation Condition-A
atomization severed.

Four conditions, all evaluated on the SAME fixed 38-case set (the 39
Condition-A severed=True cases from Experiment 1 minus the one A1-audit
exclusion cfr21p201:467; the set is derived programmatically from
../discourse_severance_report.json + ../audit_addendum.json, never
resampled):

  1. No elicitation: the saved Condition-A output + saved judge verdict,
     reused directly (zero regeneration). By construction of the eval
     set, every case is severed here -- this is the baseline.
  2. Automated recovery, arm 1: the released Disco-RAG pipeline code
     (vendor/Disco-RAG, commit 0755104beb39f877282808fee0dfe7905478adbb)
     with a substituted gpt-4o-mini backbone and the retrieval stage
     bypassed -- see disco_rag_adapter.py for the full adaptation
     statement. An EXTERNAL system's method, adapted as documented.
  3. Automated recovery, arm 2: this project's own custom fallback
     rewriter (custom_fallback.py) -- auto-rewrites the Condition-A
     claims using the saved relation-elicitation record, no human
     review. NOT Disco-RAG, NOT HCA.
  4. Flagged deferral: the EXISTING risk-triage detectors
     (server/components/risk_triage.py, imported UNMODIFIED) run
     against the Condition-A claims with segment_text = the source
     sentence. Surfaces the issue for human review; incorporates
     nothing automatically.

Scoring: both automated arms are judged with the SAME judge prompts as
Experiment 1 (severance_detection.judge_prompt_full_nucleus primary;
judge_prompt_subclause side-by-side on the A1 bundled-nucleus subset).
Incorrect recoveries are further classified fluent-but-wrong (the
confidently-wrong category) vs visibly-incomplete-or-garbled by
exp3_scoring.classify_wrongness.

Usage
-----
    venv/bin/python server/scripts/discourse_severance/exp3_recovery_comparison/run_exp3.py
    venv/bin/python server/scripts/discourse_severance/exp3_recovery_comparison/run_exp3.py --self-test
"""

import argparse
import datetime
import json
import os
import re
import sys
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed

EXP3_DIR = os.path.dirname(os.path.abspath(__file__))
SCRIPT_DIR = os.path.dirname(EXP3_DIR)          # .../discourse_severance
SERVER_DIR = os.path.dirname(os.path.dirname(SCRIPT_DIR))
if SERVER_DIR not in sys.path:
    sys.path.insert(0, SERVER_DIR)


def _load_server_env():
    """Same pattern as ../run_experiments.py: load server/.env into the
    process environment (without overriding already-set vars) so
    OPENAI_API_KEY is available the way it is for the Flask app.
    """
    env_path = os.path.join(SERVER_DIR, ".env")
    if not os.path.exists(env_path):
        return
    with open(env_path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key, value = key.strip(), value.strip()
            if key and value and key not in os.environ:
                os.environ[key] = value


_load_server_env()

from components.risk_triage import flag_claim  # noqa: E402  (UNMODIFIED import)
from scripts.discourse_severance import severance_detection  # noqa: E402
from scripts.discourse_severance.exp3_recovery_comparison import (  # noqa: E402
    custom_fallback,
    disco_rag_adapter,
    exp3_scoring,
)

SOURCE_REPORT = os.path.join(SCRIPT_DIR, "discourse_severance_report.json")
AUDIT_ADDENDUM = os.path.join(SCRIPT_DIR, "audit_addendum.json")
JSON_REPORT = os.path.join(EXP3_DIR, "exp3_report.json")
MD_REPORT = os.path.join(EXP3_DIR, "RESULTS.md")

MODEL = "gpt-4o-mini"
TEMPERATURE = 0
SEED = 13
MAX_WORKERS = 6

EXPECTED_SEVERED_A = 39
EXPECTED_EVAL_N = 38
EXPECTED_EXCLUSIONS = {"cfr21p201:467"}
EXPECTED_A2_FLAGGED = {
    "cfr21p201:1716", "cfr21p201:899", "cfr29p1910:14335",
    "cfr29p1910:32446", "cfr29p1910:23521",
}

HCA_STATEMENT = (
    "HCA (Fan et al. 2023) was not included as a comparison arm because "
    "neither its trained corpus nor model weights are released; "
    "reimplementing its full BiLSTM+PLM clause-segmentation and "
    "clause-parsing pipeline from the paper's description alone was "
    "judged out of scope for this experiment."
)

_PART_RE = re.compile(r"(\d+)\s+CFR\s+Part\s+(\d+)")


def case_id(part_label, sentence_index):
    """Same ID scheme as ../audit_addendum.json: cfr<title>p<part>:<idx>."""
    m = _PART_RE.search(part_label)
    if not m:
        raise ValueError(f"FATAL: cannot derive case id from part label {part_label!r}")
    return f"cfr{m.group(1)}p{m.group(2)}:{sentence_index}"


# --- eval-set derivation ------------------------------------------------------


def derive_eval_set(report, addendum):
    """Fixed evaluation set, derived programmatically (never resampled):
    Experiment 1 records with Condition-A LLM-judge severed=True (39),
    minus the A1-audit exclusion list (cfr21p201:467) -> 38. The five A2
    strict no-split category-error cases are KEPT and tagged
    a2_flagged=True so their contribution is separable in analysis.
    Every expectation is asserted -- fail fast, no silent drift.
    """
    records = report["experiment_1"]["records"]
    severed = [r for r in records
               if r["severance_a"]["llm_judge_preserved"] is False]
    if len(severed) != EXPECTED_SEVERED_A:
        raise AssertionError(
            f"FATAL: expected {EXPECTED_SEVERED_A} Condition-A severed records, "
            f"found {len(severed)} -- source report changed?")

    exclusions = set(
        addendum["a1_nucleus_bundling"]["summary"]["future_eval_exclusion_list"]["ids"]
    )
    if exclusions != EXPECTED_EXCLUSIONS:
        raise AssertionError(
            f"FATAL: audit exclusion list changed: {sorted(exclusions)}")

    a2_flagged_ids = set(
        addendum["a2_no_split"]["summary"]["condition_a"][
            "no_split_single_claim_strict_scored_severed_ids"]
    )
    if a2_flagged_ids != EXPECTED_A2_FLAGGED:
        raise AssertionError(
            f"FATAL: A2 strict category-error id list changed: {sorted(a2_flagged_ids)}")

    bundled = {r["id"]: r for r in addendum["a1_nucleus_bundling"]["records"]}

    eval_records = []
    for r in severed:
        cid = case_id(r["part_label"], r["sentence_index"])
        if cid in exclusions:
            continue
        bundle_rec = bundled.get(cid)
        eval_records.append({
            "id": cid,
            "part_label": r["part_label"],
            "sentence_index": r["sentence_index"],
            "sentence": r["sentence"],
            "relation": {
                "relation_type": r["relation_type"],
                "nucleus": r["nucleus"],
                "satellite": r["satellite"],
                "connective": r["connective"],
            },
            "a2_flagged": cid in a2_flagged_ids,
            "bundled_nucleus": bundle_rec is not None,
            "governed_subclause": (
                bundle_rec["governed_subclause"] if bundle_rec else None
            ),
            "condition_a_claims": r["condition_a_claims"],
            "saved_severance_a": r["severance_a"],
        })

    if len(eval_records) != EXPECTED_EVAL_N:
        raise AssertionError(
            f"FATAL: eval set has {len(eval_records)} cases, expected {EXPECTED_EVAL_N}")
    missing_a2 = a2_flagged_ids - {r["id"] for r in eval_records}
    if missing_a2:
        raise AssertionError(
            f"FATAL: A2-flagged ids missing from eval set: {sorted(missing_a2)}")

    derivation = {
        "n_condition_a_severed_llm_judge": len(severed),
        "exclusions_applied": sorted(exclusions),
        "exclusion_rationale": (
            "cfr21p201:467 is the one Condition-A severed=True case whose "
            "verdict flips to preserved under judge_prompt_subclause (A1 "
            "audit future_eval_exclusion_list)."
        ),
        "n_eval": len(eval_records),
        "a2_flagged_ids_kept_and_tagged": sorted(a2_flagged_ids),
        "a2_note": (
            "Five strict no-split category-error cases flagged by the A2 "
            "audit (possible elicitation mislabels, pending human audit) "
            "are KEPT per spec and tagged a2_flagged=True so their "
            "contribution is separable."
        ),
        "bundled_nucleus_ids_in_eval_set": sorted(
            r["id"] for r in eval_records if r["bundled_nucleus"]
        ),
    }
    return eval_records, derivation


# --- per-case processing ------------------------------------------------------

CALL_COUNTER = Counter()
_COUNTER_LOCK = __import__("threading").Lock()


def _count(key, n=1):
    with _COUNTER_LOCK:
        CALL_COUNTER[key] += n


def _judge_arm(rec, claims, model=None):
    """Judge one arm's recovered claims exactly the way atomized claims
    were judged in Experiment 1 (same prompts, no third judge). Returns
    the arm-result fields (judge_full_nucleus, judge_subclause,
    wrongness).
    """
    out = {"judge_full_nucleus": None, "judge_subclause": None, "wrongness": None}
    if claims is None:
        return out
    out["judge_full_nucleus"] = severance_detection.llm_judge_severance(
        rec["sentence"], rec["relation"], claims, model=model)
    _count("judge_full_nucleus")
    if rec["bundled_nucleus"]:
        out["judge_subclause"] = severance_detection.llm_judge_severance_subclause(
            rec["sentence"], rec["relation"], claims,
            rec["governed_subclause"], model=model)
        _count("judge_subclause")
    if out["judge_full_nucleus"]["preserved"] is False:
        out["wrongness"] = exp3_scoring.classify_wrongness(
            rec["sentence"], rec["relation"], claims,
            out["judge_full_nucleus"]["reasoning"], model=model)
        _count("wrongness_classifier")
    return out


def flags_for_case(rec):
    """Condition 4: the EXISTING risk-triage detectors, unmodified, run
    per Condition-A claim with segment_text = the original source
    sentence. No formalization exists in this experiment, so
    formal=claim (self-identical), which makes detect_modal_mismatch a
    structural no-op; the arm's signal is the english-side claim-level
    detectors plus the two segment-level detectors.
    """
    per_claim = []
    for claim in rec["condition_a_claims"]:
        flags = flag_claim(claim, claim, formal_mode="english",
                           segment_text=rec["sentence"])
        per_claim.append({"claim": claim, "flags": flags})
    all_types = sorted({f["type"] for pc in per_claim for f in pc["flags"]})
    segment_types = [t for t in all_types
                     if t in ("segment_nested_conditional", "segment_negation_scope")]
    claim_level_types = [t for t in all_types if t not in segment_types]
    return {
        "per_claim_flags": per_claim,
        "flag_types_fired": all_types,
        "segment_flag_fired": bool(segment_types),
        "segment_flag_types": segment_types,
        "claim_level_flag_fired": bool(claim_level_types),
        "claim_level_flag_types": claim_level_types,
        "any_flag_fired": bool(all_types),
    }


def process_case(rec, recovery, model=None):
    """All four conditions + scoring for one case. Arm errors are
    recorded loudly per case (error field), never swallowed into
    empty-but-plausible output.
    """
    result = {
        "id": rec["id"],
        "part_label": rec["part_label"],
        "sentence_index": rec["sentence_index"],
        "sentence": rec["sentence"],
        "relation": rec["relation"],
        "a2_flagged": rec["a2_flagged"],
        "bundled_nucleus": rec["bundled_nucleus"],
        "governed_subclause": rec["governed_subclause"],
    }

    # Condition 1 -- no elicitation: saved output + saved verdict, reused.
    result["condition_1_no_elicitation"] = {
        "claims": rec["condition_a_claims"],
        "judge_full_nucleus": {
            "preserved": rec["saved_severance_a"]["llm_judge_preserved"],
            "reasoning": rec["saved_severance_a"]["llm_judge_reasoning"],
        },
        "rule_based_preserved": rec["saved_severance_a"]["rule_based_preserved"],
        "rule_based_detail": rec["saved_severance_a"]["rule_based_detail"],
        "note": "reused from ../discourse_severance_report.json, zero regeneration",
    }

    # Condition 2 -- Disco-RAG (adapted external system).
    arm1 = {"claims": None, "error": None}
    try:
        recovered = recovery.recover(rec["sentence"])
        _count("disco_rag_stage_calls", 3)  # RST + plan + generate
        arm1.update(recovered)
        arm1["error"] = None
    except Exception as exc:  # recorded loudly, run continues past one case
        arm1["error"] = f"{type(exc).__name__}: {exc}"
    arm1.update(_judge_arm(rec, arm1.get("claims"), model=model))
    result["condition_2_disco_rag"] = arm1

    # Condition 3 -- custom fallback (this project's own).
    rewritten, err = custom_fallback.run_fallback_rewrite(
        rec["condition_a_claims"], rec["relation"], model=model)
    _count("fallback_rewrite")
    arm2 = {"claims": rewritten, "error": err}
    arm2.update(_judge_arm(rec, rewritten, model=model))
    result["condition_3_custom_fallback"] = arm2

    # Condition 4 -- flagged deferral (existing detectors, no LLM).
    result["condition_4_flags"] = flags_for_case(rec)

    return result


def _parallel_map(func, items, max_workers=MAX_WORKERS, desc=""):
    """Same ThreadPoolExecutor pattern as ../run_experiments.py."""
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


# --- summaries ----------------------------------------------------------------

ARM_KEYS = {
    "condition_2_disco_rag": "arm 1 (Disco-RAG, adapted)",
    "condition_3_custom_fallback": "arm 2 (custom fallback)",
}


def _arm_verdicts(results, arm_key, use_subclause_for_bundled=False):
    """Per-case preserved verdicts for one arm. With
    use_subclause_for_bundled, bundled-nucleus cases take the
    judge_prompt_subclause verdict (the A1 audit's alternative reading);
    everything else keeps the full-nucleus verdict.
    """
    verdicts = {}
    for r in results:
        arm = r[arm_key]
        judge = arm["judge_full_nucleus"]
        if (use_subclause_for_bundled and r["bundled_nucleus"]
                and arm["judge_subclause"] is not None):
            judge = arm["judge_subclause"]
        verdicts[r["id"]] = None if judge is None else judge["preserved"]
    return verdicts


def summarize_arm(results, arm_key):
    def _rates(subset):
        verdicts_primary = _arm_verdicts(subset, arm_key, False)
        verdicts_alt = _arm_verdicts(subset, arm_key, True)

        def _tally(verdicts):
            vals = [v for v in verdicts.values() if v is not None]
            correct = sum(1 for v in vals if v is True)
            return {
                "n": len(subset),
                "n_scored": len(vals),
                "n_correct": correct,
                "n_incorrect": len(vals) - correct,
                "correct_recovery_rate": correct / len(vals) if vals else None,
            }

        primary = _tally(verdicts_primary)

        wrongness = Counter()
        confidently_wrong_ids = []
        for r in subset:
            arm = r[arm_key]
            if verdicts_primary[r["id"]] is False:
                w = arm["wrongness"] or {"category": None}
                cat = w["category"] or "unclassified"
                wrongness[cat] += 1
                if cat == "fluent_but_wrong":
                    confidently_wrong_ids.append(r["id"])
        n_scored = primary["n_scored"]
        primary["n_confidently_wrong"] = wrongness.get("fluent_but_wrong", 0)
        primary["confidently_wrong_rate"] = (
            wrongness.get("fluent_but_wrong", 0) / n_scored if n_scored else None)
        primary["n_visibly_incomplete_or_garbled"] = wrongness.get(
            "visibly_incomplete_or_garbled", 0)
        primary["n_wrongness_unclassified"] = wrongness.get("unclassified", 0)
        primary["confidently_wrong_ids"] = confidently_wrong_ids

        alt = _tally(verdicts_alt)
        return {"full_nucleus_primary": primary,
                "subclause_alternative_reading": alt}

    n_errors = sum(1 for r in results if r[arm_key]["error"])
    out = {
        "label": ARM_KEYS[arm_key],
        "n_arm_errors": n_errors,
        "all_38": _rates(results),
        "excluding_a2_flagged": _rates([r for r in results if not r["a2_flagged"]]),
    }
    return out


def subclause_side_by_side(results):
    """Bundled-nucleus cases: full-nucleus vs sub-clause verdicts per arm,
    side by side, mirroring the A1 audit's reporting style."""
    rows = []
    for r in results:
        if not r["bundled_nucleus"]:
            continue
        row = {"id": r["id"], "relation_type": r["relation"]["relation_type"]}
        for arm_key, short in (("condition_2_disco_rag", "arm1"),
                               ("condition_3_custom_fallback", "arm2")):
            arm = r[arm_key]
            fn = arm["judge_full_nucleus"]
            sc = arm["judge_subclause"]
            row[f"{short}_full_nucleus"] = None if fn is None else fn["preserved"]
            row[f"{short}_subclause"] = None if sc is None else sc["preserved"]
        rows.append(row)
    return rows


def flag_summary(results):
    n_any = sum(1 for r in results if r["condition_4_flags"]["any_flag_fired"])
    n_seg = sum(1 for r in results if r["condition_4_flags"]["segment_flag_fired"])
    type_counts = Counter(
        t for r in results for t in r["condition_4_flags"]["flag_types_fired"])
    return {
        "n_cases": len(results),
        "n_cases_any_flag": n_any,
        "n_cases_segment_flag": n_seg,
        "flag_type_case_counts": dict(sorted(type_counts.items())),
    }


def cross_tab(results, arm_key):
    """The key deferral question, per automated arm: of the cases this
    arm got confidently wrong, how many would flagged deferral have
    surfaced? Plus the false-alarm side: flags fired where the arm was
    correct."""
    buckets = {"correct": [], "fluent_but_wrong": [],
               "visibly_incomplete_or_garbled": [],
               "wrongness_unclassified": [], "unscored": []}
    for r in results:
        arm = r[arm_key]
        judge = arm["judge_full_nucleus"]
        preserved = None if judge is None else judge["preserved"]
        if preserved is True:
            buckets["correct"].append(r)
        elif preserved is False:
            cat = (arm["wrongness"] or {}).get("category")
            buckets[cat if cat in ("fluent_but_wrong",
                                   "visibly_incomplete_or_garbled")
                    else "wrongness_unclassified"].append(r)
        else:
            buckets["unscored"].append(r)

    def _row(cases):
        return {
            "n": len(cases),
            "n_any_flag": sum(1 for r in cases
                              if r["condition_4_flags"]["any_flag_fired"]),
            "n_segment_flag": sum(1 for r in cases
                                  if r["condition_4_flags"]["segment_flag_fired"]),
            "ids": [r["id"] for r in cases],
        }

    table = {k: _row(v) for k, v in buckets.items()}
    cw = table["fluent_but_wrong"]
    table["coverage_of_confidently_wrong"] = {
        "any_flag": (f"{cw['n_any_flag']}/{cw['n']}",
                     cw["n_any_flag"] / cw["n"] if cw["n"] else None),
        "segment_flag": (f"{cw['n_segment_flag']}/{cw['n']}",
                         cw["n_segment_flag"] / cw["n"] if cw["n"] else None),
    }
    corr = table["correct"]
    table["false_alarms_on_correct"] = {
        "any_flag": (f"{corr['n_any_flag']}/{corr['n']}",
                     corr["n_any_flag"] / corr["n"] if corr["n"] else None),
        "segment_flag": (f"{corr['n_segment_flag']}/{corr['n']}",
                         corr["n_segment_flag"] / corr["n"] if corr["n"] else None),
    }
    return table


def confidently_wrong_docs(results):
    """Full documentation for every confidently-wrong case, both arms --
    same style as the existing report's failure examples."""
    docs = []
    for r in results:
        for arm_key in ARM_KEYS:
            arm = r[arm_key]
            judge = arm["judge_full_nucleus"]
            if judge is None or judge["preserved"] is not False:
                continue
            if (arm["wrongness"] or {}).get("category") != "fluent_but_wrong":
                continue
            docs.append({
                "id": r["id"],
                "arm": ARM_KEYS[arm_key],
                "a2_flagged": r["a2_flagged"],
                "relation_type": r["relation"]["relation_type"],
                "sentence": r["sentence"],
                "nucleus": r["relation"]["nucleus"],
                "satellite": r["relation"]["satellite"],
                "connective": r["relation"]["connective"],
                "arm_output_claims": arm["claims"],
                "why_wrong_judge": judge["reasoning"],
                "why_confidently_wrong": arm["wrongness"]["reasoning"],
                "flag_fired": r["condition_4_flags"]["any_flag_fired"],
                "flag_types": r["condition_4_flags"]["flag_types_fired"],
                "subclause_verdict": (
                    None if arm["judge_subclause"] is None
                    else arm["judge_subclause"]["preserved"]),
            })
    return docs


# --- reporting ----------------------------------------------------------------


def _langchain_core_version():
    import langchain_core
    return langchain_core.__version__


def build_summary(results, derivation):
    return {
        "eval_set": derivation,
        "arm_1_disco_rag": summarize_arm(results, "condition_2_disco_rag"),
        "arm_2_custom_fallback": summarize_arm(results, "condition_3_custom_fallback"),
        "subclause_side_by_side_bundled_cases": subclause_side_by_side(results),
        "condition_4_flag_summary": flag_summary(results),
        "cross_tab_arm_1_vs_flags": cross_tab(results, "condition_2_disco_rag"),
        "cross_tab_arm_2_vs_flags": cross_tab(results, "condition_3_custom_fallback"),
        "confidently_wrong_documentation": confidently_wrong_docs(results),
        "llm_call_counts": dict(CALL_COUNTER),
    }


def write_json_report(summary, results, path=JSON_REPORT):
    report = {
        "run_date": datetime.date.today().isoformat(),
        "experiment": "exp3_recovery_comparison",
        "attribution": {
            "disco_rag": disco_rag_adapter.BACKBONE_SUBSTITUTION_STATEMENT,
            "disco_rag_commit": disco_rag_adapter.DISCO_RAG_COMMIT,
            "disco_rag_bypasses": disco_rag_adapter.BYPASS_NOTES,
            "custom_fallback": custom_fallback.CUSTOM_FALLBACK_STATEMENT,
            "hca": HCA_STATEMENT,
        },
        "reproducibility": {
            "model": MODEL,
            "temperature": TEMPERATURE,
            "seed": SEED,
            "judge_prompts": [
                "judge_prompt_full_nucleus (primary; ../severance_detection.py)",
                "judge_prompt_subclause (bundled-nucleus subset only; "
                "../severance_detection.py)",
            ],
            "langchain_core_version": _langchain_core_version(),
            "recovery_query": disco_rag_adapter.RECOVERY_QUERY,
        },
        "summary": summary,
        "records": results,
    }
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(report, fh, indent=2, ensure_ascii=False)
    return path


def _fmt(n, d):
    if d in (0, None):
        return "n/a"
    return f"{n}/{d} ({100 * n / d:.1f}%)"


def _pres(v):
    return {True: "preserved", False: "severed", None: "unscored"}[v]


def _arm_rate_rows(arm_summary, scope_key):
    p = arm_summary[scope_key]["full_nucleus_primary"]
    a = arm_summary[scope_key]["subclause_alternative_reading"]
    return p, a


def write_markdown_report(summary, results, path=MD_REPORT):
    d = summary["eval_set"]
    a1 = summary["arm_1_disco_rag"]
    a2 = summary["arm_2_custom_fallback"]
    lines = [
        "# Experiment 3: recovery-strategy reliability comparison",
        "",
        f"Run date: {datetime.date.today().isoformat()}. Generated by "
        "`server/scripts/discourse_severance/exp3_recovery_comparison/run_exp3.py`.",
        "",
        "## Attribution (read before quoting any number)",
        "",
        f"- **Arm 1 is an external system's method, adapted:** "
        f"{disco_rag_adapter.BACKBONE_SUBSTITUTION_STATEMENT}",
        f"  Vendored at `exp3_recovery_comparison/vendor/Disco-RAG`, commit "
        f"`{disco_rag_adapter.DISCO_RAG_COMMIT}` (2026-07-12). Its outputs are "
        "Disco-RAG's (as adapted), never presented as this project's own method.",
        f"- **Arm 2 is this project's own:** {custom_fallback.CUSTOM_FALLBACK_STATEMENT}",
        f"- {HCA_STATEMENT}",
        "",
        "## Evaluation set (fixed, derived, never resampled)",
        "",
        f"- Start: the **{d['n_condition_a_severed_llm_judge']}** Experiment-1 "
        "sentences scored severed=True by the LLM-judge "
        "(`judge_prompt_full_nucleus`) under Condition A (of 47).",
        f"- Minus the A1-audit exclusion {d['exclusions_applied']}: "
        f"{d['exclusion_rationale']}",
        f"- = **{d['n_eval']} cases**, derived programmatically from "
        "`../discourse_severance_report.json` + `../audit_addendum.json`.",
        f"- Five A2-audit strict no-split category-error cases are KEPT and "
        f"tagged `a2_flagged` (possible elicitation mislabels, pending human "
        f"audit): {', '.join('`%s`' % i for i in d['a2_flagged_ids_kept_and_tagged'])}. "
        "All rates below are reported both with and without them.",
        f"- Bundled-nucleus cases in the set (A1 audit) -- judged under BOTH "
        f"judge prompts, side by side: "
        f"{', '.join('`%s`' % i for i in d['bundled_nucleus_ids_in_eval_set'])}.",
        "",
        "## Conditions",
        "",
        "1. **No elicitation**: saved Condition-A atomization + saved judge "
        "verdict, reused directly (zero regeneration). By construction of "
        "the eval set, all 38/38 are severed here -- the baseline.",
        "2. **Automated recovery, arm 1 (Disco-RAG, adapted)**: the released "
        "code's real zero-shot RST-tree construction, discourse-aware "
        "planning, and plan-conditioned generation over the source "
        "sentence. Bypassed stages, documented in `disco_rag_adapter.py`: "
        "retrieval/embedding (no corpus to query; the single chunk is "
        "constructed directly) and the inter-chunk rhetorical graph (empty "
        "by construction with one chunk; the released "
        "`PipelineModules(use_graph=False)`/`graph=None` code path is used). "
        "The saved Condition-A claims are NOT fed to it -- the released "
        "design has no input slot for a prior decomposition.",
        "3. **Automated recovery, arm 2 (custom fallback)**: auto-rewrites "
        "the Condition-A claims using the saved relation-elicitation "
        "record (relation type, nucleus, satellite, connective), no human "
        "review, no access to the source sentence (see "
        "`custom_fallback.py`).",
        "4. **Flagged deferral**: `server/components/risk_triage.py` "
        "detectors, imported UNMODIFIED, run per Condition-A claim with "
        "`segment_text` = the source sentence. Surfaces cases for human "
        "review; incorporates nothing automatically.",
        "",
        "## Scoring",
        "",
        "Both automated arms are judged with the SAME two judge prompts as "
        "the Experiment-1/audit pipeline (`../severance_detection.py`): "
        "`judge_prompt_full_nucleus` (primary, all cases) and "
        "`judge_prompt_subclause` (bundled-nucleus cases, side by side). No "
        "third judge prompt was introduced. Incorrect recoveries are "
        "further classified by a structured wrongness call "
        "(`exp3_scoring.py`) into **fluent-but-wrong** (the "
        "confidently-wrong category: reads complete, fluent, authoritative "
        "-- no hedge, no flag, no visible gap -- while misrepresenting the "
        "relation) vs **visibly-incomplete-or-garbled**; reasoning is "
        "logged per case.",
        "",
        "## Per-arm results (all 38 cases)",
        "",
        "| Arm | Reading | Correct recovery | Confidently wrong | Visibly incomplete/garbled |",
        "|---|---|---|---|---|",
    ]
    for arm in (a1, a2):
        p, alt = _arm_rate_rows(arm, "all_38")
        lines.append(
            f"| {arm['label']} | full-nucleus (primary) | "
            f"{_fmt(p['n_correct'], p['n_scored'])} | "
            f"{_fmt(p['n_confidently_wrong'], p['n_scored'])} | "
            f"{_fmt(p['n_visibly_incomplete_or_garbled'], p['n_scored'])} |")
        lines.append(
            f"| {arm['label']} | sub-clause alternative (bundled cases "
            f"re-read) | {_fmt(alt['n_correct'], alt['n_scored'])} | "
            "(classified under primary reading) | |")
    lines += [
        "",
        "The sub-clause alternative reading swaps in the "
        "`judge_prompt_subclause` verdict for the bundled-nucleus cases "
        "only (all other cases keep the primary verdict), mirroring the A1 "
        "audit's adjusted-figures convention. Wrongness classification is "
        "keyed to the primary reading.",
        "",
        "### Excluding the 5 `a2_flagged` cases (n=33)",
        "",
        "| Arm | Reading | Correct recovery | Confidently wrong |",
        "|---|---|---|---|",
    ]
    for arm in (a1, a2):
        p, alt = _arm_rate_rows(arm, "excluding_a2_flagged")
        lines.append(
            f"| {arm['label']} | full-nucleus (primary) | "
            f"{_fmt(p['n_correct'], p['n_scored'])} | "
            f"{_fmt(p['n_confidently_wrong'], p['n_scored'])} |")
        lines.append(
            f"| {arm['label']} | sub-clause alternative | "
            f"{_fmt(alt['n_correct'], alt['n_scored'])} | |")
    if a1["n_arm_errors"] or a2["n_arm_errors"]:
        lines += [
            "",
            f"Arm errors (call failures, recorded per case, not scored): "
            f"arm 1: {a1['n_arm_errors']}, arm 2: {a2['n_arm_errors']}.",
        ]
    lines += [
        "",
        "### Bundled-nucleus cases: both judge readings side by side",
        "",
        "| ID | Relation | Arm 1 full-nucleus | Arm 1 sub-clause | "
        "Arm 2 full-nucleus | Arm 2 sub-clause |",
        "|---|---|---|---|---|---|",
    ]
    for row in summary["subclause_side_by_side_bundled_cases"]:
        lines.append(
            f"| {row['id']} | {row['relation_type']} | "
            f"{_pres(row['arm1_full_nucleus'])} | {_pres(row['arm1_subclause'])} | "
            f"{_pres(row['arm2_full_nucleus'])} | {_pres(row['arm2_subclause'])} |")

    fs = summary["condition_4_flag_summary"]
    lines += [
        "",
        "## Condition 4: flagged deferral",
        "",
        f"- Cases with ANY risk-triage flag fired: "
        f"{_fmt(fs['n_cases_any_flag'], fs['n_cases'])}",
        f"- Cases with a SEGMENT-level flag (segment_nested_conditional / "
        f"segment_negation_scope): {_fmt(fs['n_cases_segment_flag'], fs['n_cases'])}",
        f"- Flag-type case counts: {fs['flag_type_case_counts']}",
        "",
        "## Cross-tab: would flagged deferral have caught what automated "
        "recovery got wrong?",
        "",
    ]
    for arm_key, ct_key in (("arm_1_disco_rag", "cross_tab_arm_1_vs_flags"),
                            ("arm_2_custom_fallback", "cross_tab_arm_2_vs_flags")):
        ct = summary[ct_key]
        label = summary[arm_key]["label"]
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
            f"- **False-alarm side** (flags fired where this arm was correct): "
            f"any flag {fa['any_flag'][0]}; segment-level flag "
            f"{fa['segment_flag'][0]}.",
            "",
        ]

    docs = summary["confidently_wrong_documentation"]
    lines += [
        f"## Confidently-wrong case documentation ({len(docs)} arm-case "
        "instances)",
        "",
        "Every confidently-wrong case, both arms -- original sentence, the "
        "arm's output, and why it is wrong (same documentation style as the "
        "existing report's failure examples).",
        "",
    ]
    for doc in docs:
        a2_tag = " [a2_flagged]" if doc["a2_flagged"] else ""
        lines += [
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
        lines.append("")

    lines += [
        "## Reproducibility",
        "",
        f"- Disco-RAG vendored at commit "
        f"`{disco_rag_adapter.DISCO_RAG_COMMIT}`; "
        f"{disco_rag_adapter.BACKBONE_SUBSTITUTION_STATEMENT}",
        "- Documented bypasses:",
    ]
    lines += [f"  - {n}" for n in disco_rag_adapter.BYPASS_NOTES]
    lines += [
        f"- All LLM calls (both arms' recovery, both judges, wrongness "
        f"classifier): model `{MODEL}`, temperature={TEMPERATURE}, "
        f"seed={SEED} -- the same settings as `server/api_call.py` and "
        "Experiment 1.",
        f"- `langchain-core` {_langchain_core_version()} was installed into "
        "the project venv (`venv/bin/python -m pip install "
        "'langchain-core>=0.3,<0.4'`) solely so the unmodified vendor "
        "chains (`prompt | llm | StrOutputParser()`) can run; no vendor "
        "file was modified or patched.",
        f"- Fixed recovery query given to Disco-RAG for every case: "
        f"{disco_rag_adapter.RECOVERY_QUERY!r}",
        f"- LLM call counts this run: {dict(CALL_COUNTER)}",
        "",
        "## Self-test",
        "",
        "`--self-test` exercises all plumbing (eval-set derivation from the "
        "saved reports, both recovery arms through the REAL vendor parser/"
        "planner/generator code, both judge prompts, the wrongness "
        "classifier, the flag arm, summaries, and the cross-tab) on "
        "synthetic sentences with every LLM call site stubbed -- zero "
        "network, zero API cost. See `self_test_exp3.py`.",
        "",
        "Full machine-readable results: "
        "`server/scripts/discourse_severance/exp3_recovery_comparison/"
        "exp3_report.json`.",
        "",
    ]
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines))
    return path


# --- entry point --------------------------------------------------------------


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--self-test", action="store_true",
                        help="run all plumbing on synthetic sentences with "
                             "stubbed LLM calls -- zero network, no reports "
                             "written")
    parser.add_argument("--model", type=str, default=MODEL)
    args = parser.parse_args(argv)

    if args.self_test:
        from scripts.discourse_severance.exp3_recovery_comparison.self_test_exp3 import (
            run_self_test,
        )
        run_self_test()
        return 0

    start = time.time()
    with open(SOURCE_REPORT, encoding="utf-8") as fh:
        report = json.load(fh)
    with open(AUDIT_ADDENDUM, encoding="utf-8") as fh:
        addendum = json.load(fh)

    eval_records, derivation = derive_eval_set(report, addendum)
    print(f"Eval set derived: {len(eval_records)} cases "
          f"({derivation['n_condition_a_severed_llm_judge']} severed under A "
          f"minus {len(derivation['exclusions_applied'])} exclusion); "
          f"{len(derivation['a2_flagged_ids_kept_and_tagged'])} a2-flagged, "
          f"{len(derivation['bundled_nucleus_ids_in_eval_set'])} bundled-nucleus.")

    recovery = disco_rag_adapter.DiscoRagSingleSentenceRecovery(
        backbone=disco_rag_adapter.ChatOpenAIBackbone(model_name=args.model))

    print(f"Processing {len(eval_records)} cases x 4 conditions "
          f"(model={args.model}, temperature={TEMPERATURE}, seed={SEED})...")
    results = _parallel_map(
        lambda rec: process_case(rec, recovery, model=args.model),
        eval_records, desc="exp3")

    summary = build_summary(results, derivation)
    json_path = write_json_report(summary, results)
    md_path = write_markdown_report(summary, results)

    elapsed = time.time() - start
    print(f"\nDone in {elapsed:.0f}s. LLM calls: {dict(CALL_COUNTER)}")
    print(f"Wrote {json_path}\nWrote {md_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
