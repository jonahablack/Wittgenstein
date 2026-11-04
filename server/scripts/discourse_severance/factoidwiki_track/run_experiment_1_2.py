"""Task 2 + Task 3 (full-scale run): build the Experiment 1/2 sample from
every Stage-2-confirmed Condition/Concession paragraph (Task 2), then score
severance under both atomization conditions and run the Experiment-1-style
and Experiment-2-style analyses (Task 3), reusing
../severance_detection.py's `judge_prompt_full_nucleus` framing (adapted
for paragraph input -- see severance_judge_paragraph.py) and
../run_experiments.py's Experiment 1/2 statistical design (Fisher's exact
test on the pooled governing-relations-vs-Elaboration 2x2 table) as closely
as possible without importing outside this directory (env_utils.py's
established convention).

Design recap (see README.md and this file's own docstrings in
condition_b_atomizer.py / severance_judge_paragraph.py / confirmed_pool.py
for the full reasoning behind each piece):

  Condition A ("standard atomization"): Chen et al.'s ALREADY-RELEASED
    Propositionizer output -- the `targets` field of the SAME source record
    in data_cache/train.jsonl, matched back by pool_index. No LLM call; this
    project does not run the Propositionizer model.
  Condition B ("elicitation-then-atomize"): a NEW gpt-4o-mini call
    (condition_b_atomizer.run_condition_b) given the paragraph plus its
    already-elicited Stage-1/Stage-2 relation (type/nucleus/satellite/
    connective), instructed to preserve or flag that relation while
    atomizing.
  Elaboration control: Stage-1 raw Elaboration hits (no Stage-2 equivalent
    exists for Elaboration in this track, matching the parent CFR track's
    own design, where Elaboration was likewise Condition-A/Stage-1-only),
    filtered to those passing the free grounding prefilter
    (candidate_prefilter.prefilter_candidate) so the severance judge is
    never scored against a hallucinated nucleus/satellite, then a
    fixed-seed sample matched in size to the pooled Condition+Concession
    confirmed group (mirroring ../run_experiments.py's roughly-matched,
    not exactly-equal, 47-vs-45 governing/control sizing).

Every governing (Condition/Concession) paragraph gets: Condition A lookup,
Condition B atomization, and an LLM-judge severance call against EACH of
A's and B's output (2 judge calls + 1 atomize call = 3 LLM calls/paragraph).
Every Elaboration-control paragraph gets: Condition A lookup and ONE
LLM-judge severance call against A's output only (no Condition B is ever
run on the control, matching the parent track's Experiment 2 design, where
the control arm is Condition-A-only).

Usage:
    venv/bin/python server/scripts/discourse_severance/factoidwiki_track/run_experiment_1_2.py
"""

import json
import os
import random

from download_data import get_classifier_pool, shuffled_records
from env_utils import LOGS_DIR, RESULTS_DIR, ensure_dirs, load_server_env
from confirmed_pool import get_confirmed_condition, get_confirmed_concession, get_elaboration_pool
from condition_b_atomizer import run_condition_b, DEFAULT_CONDITION_B_MODEL
from severance_judge_paragraph import llm_judge_paragraph_severance
from run_two_stage_pipeline import _parallel_map, DEFAULT_MAX_WORKERS
from candidate_prefilter import normalize_text

load_server_env()

GOVERN_LOG = os.path.join(LOGS_DIR, "task7_experiment_govern_log.jsonl")
ELABORATION_LOG = os.path.join(LOGS_DIR, "task7_experiment_elaboration_log.jsonl")
REPORT_JSON = os.path.join(RESULTS_DIR, "task7_experiment_1_2_report.json")

ELABORATION_SAMPLE_SEED = 13  # matches download_data.SPLIT_SEED / spot_check_sample.SAMPLE_SEED convention
GOVERNING_RELATION_TYPES = ["Condition", "Concession"]


# --- Task 2: build the sample -------------------------------------------


def _build_pool_index_lookup():
    """pool_index -> full data_cache record (title/section/content/targets),
    built once from the SAME deterministic (fixed-seed) shuffled pool every
    other script in this track uses, so pool_index is a stable join key.
    """
    pool = get_classifier_pool(shuffled_records())
    return {i: rec for i, rec in enumerate(pool)}


def _condition_a_lookup(pool_index, expected_content, pool_lookup):
    """Returns the `targets` list (Condition A / real Propositionizer
    output) for `pool_index`, after asserting the freshly-looked-up
    record's `content` matches what Stage 1/2 actually logged for this
    index -- a silent mismatch here would mean scoring severance against
    the WRONG paragraph's real output, exactly the kind of silent
    corruption this repo's fail-fast philosophy exists to catch.
    """
    record = pool_lookup.get(pool_index)
    if record is None:
        raise AssertionError(f"FATAL: pool_index {pool_index} not found in the classifier pool lookup.")
    if record["content"] != expected_content:
        raise AssertionError(
            f"FATAL: content mismatch at pool_index {pool_index} -- data_cache lookup does not match "
            "the content logged in the Stage-1/Stage-2 record. Refusing to score severance against "
            "a potentially wrong paragraph's Propositionizer output."
        )
    return record["targets"]


def build_govern_sample(pool_lookup):
    """Every Stage-2-confirmed Condition + Concession paragraph, sorted by
    pool_index (deterministic order, not re-shuffled) -- per the task
    brief, ALL of them are used, not a capped/sampled subset.
    """
    condition = get_confirmed_condition()
    concession = get_confirmed_concession()
    records = []
    for relation_type, by_idx in (("Condition", condition), ("Concession", concession)):
        for pool_index, rec in by_idx.items():
            records.append({
                "pool_index": pool_index,
                "relation_type": relation_type,
                "title": rec["title"],
                "section": rec["section"],
                "content": rec["content"],
                "nucleus": rec["nucleus"],
                "satellite": rec["satellite"],
                "connective": rec["connective"],
                "condition_a_propositions": _condition_a_lookup(pool_index, rec["content"], pool_lookup),
                "verification_prompt_version": rec["stage2"].get("verification_prompt_version"),
            })
    records.sort(key=lambda r: r["pool_index"])
    return records


def build_elaboration_sample(pool_lookup, target_size, seed=ELABORATION_SAMPLE_SEED):
    """Stage-1 Elaboration hits, filtered to grounded, then a fixed-seed
    sample of size min(target_size, available). Returns (sample, meta)
    where meta records how many were excluded for ungroundedness and
    whether the target size was actually reached.

    GROUNDING BAR IS DELIBERATELY NOT THE SAME AS CONDITION/CONCESSION'S
    STAGE 1.5: candidate_prefilter.prefilter_candidate's "passes_stage1_5"
    requires BOTH connective_grounded AND satellite_grounded, which is
    correct for Condition/Concession (relation_classifier.py's prompt
    schema always gives those two types a real connective). Checking the
    actual data here found this is the WRONG bar for Elaboration: 139 of
    177 raw Elaboration hits have connective=None -- not hallucination, but
    the expected, normal case, since RST Elaboration frequently has NO
    lexical marker at all (unlike "although"/"if"/etc.) -- and
    is_grounded(None, ...) correctly returns False for a None input by
    design (see candidate_prefilter.py's docstring: fails safe, never
    passes-by-default). Applying "passes_stage1_5" here would have
    discarded 141/177 (79.7%) of otherwise-good Elaboration hits for
    legitimately having no connective, not for being ungrounded --
    confirmed by inspection: satellite_grounded alone is true for 176/177
    raw hits (only 1 genuine satellite-grounding failure), so the real
    signal is in satellite/nucleus groundedness, not connective presence.
    severance_judge_paragraph's Elaboration description also never asks the
    judge to evaluate a connective, only whether the satellite still reads
    as detail about the nucleus -- so this filter requires satellite_grounded
    AND the (diagnostic-only for Condition/Concession, but load-bearing
    here) nucleus_grounded_diagnostic_only, and explicitly does NOT require
    connective_grounded.
    """
    pool = get_elaboration_pool()
    grounded = {
        idx: rec for idx, rec in pool.items()
        if rec["stage1_5_diagnostic"]["satellite_grounded"]
        and rec["stage1_5_diagnostic"]["nucleus_grounded_diagnostic_only"]
    }
    n_excluded_ungrounded = len(pool) - len(grounded)

    ordered = sorted(grounded.values(), key=lambda r: r["pool_index"])
    if target_size >= len(ordered):
        sampled = ordered
    else:
        rng = random.Random(seed)
        sampled = sorted(rng.sample(ordered, target_size), key=lambda r: r["pool_index"])

    records = []
    for rec in sampled:
        pool_index = rec["pool_index"]
        records.append({
            "pool_index": pool_index,
            "relation_type": "Elaboration",
            "title": rec["title"],
            "section": rec["section"],
            "content": rec["content"],
            "nucleus": rec["nucleus"],
            "satellite": rec["satellite"],
            "connective": rec["connective"],
            "condition_a_propositions": _condition_a_lookup(pool_index, rec["content"], pool_lookup),
        })
    meta = {
        "seed": seed,
        "n_available_raw_elaboration_hits": len(pool),
        "n_excluded_ungrounded": n_excluded_ungrounded,
        "n_available_after_grounding_filter": len(ordered),
        "target_size": target_size,
        "n_sampled": len(records),
        "sampling_method": "all available (target size not reached)" if target_size >= len(ordered)
                           else f"random sample, seed={seed}",
    }
    return records, meta


# --- Task 3: score severance ---------------------------------------------


def _relation_dict(rec):
    return {
        "relation_type": rec["relation_type"],
        "nucleus": rec["nucleus"],
        "satellite": rec["satellite"],
        "connective": rec["connective"],
    }


def _score_govern_record(rec):
    relation = _relation_dict(rec)
    content = rec["content"]

    condition_b_result = run_condition_b(content, relation, model=DEFAULT_CONDITION_B_MODEL)
    condition_b_propositions = condition_b_result["propositions"]

    severance_a = llm_judge_paragraph_severance(content, relation, rec["condition_a_propositions"])
    severance_b = llm_judge_paragraph_severance(content, relation, condition_b_propositions)

    return {
        **rec,
        "n_condition_a_propositions": len(rec["condition_a_propositions"]),
        "condition_b_propositions": condition_b_propositions,
        "condition_b_error": condition_b_result["_error"],
        "n_condition_b_propositions": len(condition_b_propositions),
        "severance_a": severance_a,
        "severance_b": severance_b,
    }


def _score_elaboration_record(rec):
    relation = _relation_dict(rec)
    severance_a = llm_judge_paragraph_severance(rec["content"], relation, rec["condition_a_propositions"])
    return {
        **rec,
        "n_condition_a_propositions": len(rec["condition_a_propositions"]),
        "severance_a": severance_a,
    }


# --- summaries -------------------------------------------------------------


def _rate(preds):
    vals = [p for p in preds if p is not None]
    severed = sum(1 for p in vals if p is False)
    return {"n_scored": len(vals), "n_severed": severed,
            "severed_rate": severed / len(vals) if vals else None}


def summarize_experiment_1(govern_results):
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
    n_condition_b_errors = sum(1 for r in govern_results if r.get("condition_b_error"))

    return {
        "n": len(govern_results),
        "condition_a_overall": overall_a,
        "condition_b_overall": overall_b,
        "by_relation_type": by_type,
        "n_condition_b_atomization_errors": n_condition_b_errors,
        "n_still_severed_under_b": len(still_severed_under_b),
        "still_severed_under_b_rate_of_scored": (
            len(still_severed_under_b) / n_scored_b if n_scored_b else None
        ),
        "still_severed_under_b_pool_indices": sorted(r["pool_index"] for r in still_severed_under_b),
    }


def summarize_experiment_2(govern_results, elaboration_results):
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
            "(pooled, Condition-A output) vs Elaboration control (Condition-A output). Mirrors "
            "../run_experiments.py's compare_relation_bearing_vs_control design."
        )
    except ImportError:
        result["test_note"] = "scipy not available in this environment -- reporting raw counts/rates only."

    return result


def summarize_structural_comparison(govern_results):
    """Qualitative Propositionizer-vs-gpt-4o-mini comparison the task brief
    asks for -- computed for FREE from data already collected above (no new
    LLM calls): propositions-per-paragraph under each condition, and
    whether the Stage-1/2-elicited connective string survives verbatim
    (after the same cheap normalize_text() used by candidate_prefilter.py's
    grounding check) in at least one output proposition under A vs under B.
    This is a coarse, purely lexical/structural signal (same caveat
    ../severance_detection.py's own rule_based_severance carries: presence
    somewhere in the output set is not the same as still governing the
    right clause) -- reported alongside, not instead of, the LLM-judge
    severance numbers above.
    """
    def connective_survives(connective, propositions):
        norm_conn = normalize_text(connective)
        if not norm_conn:
            return None
        return any(norm_conn in normalize_text(p) for p in propositions)

    rows = []
    for r in govern_results:
        rows.append({
            "relation_type": r["relation_type"],
            "n_a": r["n_condition_a_propositions"],
            "n_b": r["n_condition_b_propositions"],
            "conn_survives_a": connective_survives(r["connective"], r["condition_a_propositions"]),
            "conn_survives_b": connective_survives(r["connective"], r["condition_b_propositions"]),
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
            "avg_propositions_condition_a": avg([row["n_a"] for row in subset]),
            "avg_propositions_condition_b": avg([row["n_b"] for row in subset]),
            "connective_survival_condition_a": survival([row["conn_survives_a"] for row in subset]),
            "connective_survival_condition_b": survival([row["conn_survives_b"] for row in subset]),
        }

    overall = block(rows)
    by_relation_type = {rt: block([row for row in rows if row["relation_type"] == rt])
                         for rt in GOVERNING_RELATION_TYPES}

    return {"overall": overall, "by_relation_type": by_relation_type}


# --- entry point -----------------------------------------------------------


def main():
    ensure_dirs()
    pool_lookup = _build_pool_index_lookup()

    govern_sample = build_govern_sample(pool_lookup)
    print(f"Governing (Condition+Concession) confirmed sample: {len(govern_sample)} paragraphs "
          f"({sum(1 for r in govern_sample if r['relation_type']=='Condition')} Condition, "
          f"{sum(1 for r in govern_sample if r['relation_type']=='Concession')} Concession).")

    elaboration_sample, elaboration_meta = build_elaboration_sample(pool_lookup, target_size=len(govern_sample))
    print(f"Elaboration control sample: {len(elaboration_sample)} paragraphs "
          f"({elaboration_meta['sampling_method']}, "
          f"{elaboration_meta['n_excluded_ungrounded']} excluded as ungrounded of "
          f"{elaboration_meta['n_available_raw_elaboration_hits']} available raw hits).")

    print(f"Scoring {len(govern_sample)} governing paragraphs "
          "(Condition-B atomize + severance-judge on A + severance-judge on B each)...")
    govern_results = _parallel_map(_score_govern_record, govern_sample, max_workers=DEFAULT_MAX_WORKERS,
                                    label="govern-scoring")
    with open(GOVERN_LOG, "w", encoding="utf-8") as fh:
        for rec in govern_results:
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")

    print(f"Scoring {len(elaboration_sample)} Elaboration-control paragraphs "
          "(severance-judge on Condition-A output only)...")
    elaboration_results = _parallel_map(_score_elaboration_record, elaboration_sample,
                                         max_workers=DEFAULT_MAX_WORKERS, label="elaboration-scoring")
    with open(ELABORATION_LOG, "w", encoding="utf-8") as fh:
        for rec in elaboration_results:
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")

    exp1_summary = summarize_experiment_1(govern_results)
    exp2_summary = summarize_experiment_2(govern_results, elaboration_results)
    structural_summary = summarize_structural_comparison(govern_results)

    report = {
        "govern_sample_size": len(govern_sample),
        "elaboration_sample_meta": elaboration_meta,
        "govern_log": GOVERN_LOG,
        "elaboration_log": ELABORATION_LOG,
        "experiment_1": exp1_summary,
        "experiment_2": exp2_summary,
        "structural_comparison_condition_a_vs_b": structural_summary,
    }
    with open(REPORT_JSON, "w", encoding="utf-8") as fh:
        json.dump(report, fh, indent=2, ensure_ascii=False)

    print("\n" + "#" * 90)
    print("EXPERIMENT 1/2 SUMMARY")
    print("#" * 90)
    print(json.dumps({
        "experiment_1": exp1_summary,
        "experiment_2": exp2_summary,
        "structural_comparison_condition_a_vs_b": structural_summary,
    }, indent=2))
    print(f"\nWrote {REPORT_JSON}")
    print(f"Govern log: {GOVERN_LOG}")
    print(f"Elaboration log: {ELABORATION_LOG}")


if __name__ == "__main__":
    main()
