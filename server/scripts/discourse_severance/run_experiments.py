"""Orchestrates the two discourse-severance experiments described in this
task:

Experiment 1 (capacity-vs-elicitation ablation): for each Condition/
Exception/Concession sentence found in the corpus sample, run Condition A
(standard atomization) and Condition B (relation-aware atomization),
score both with the LLM-judge and rule-based severance checks, and
report severance rate under A vs B, agreement between the two metrics,
and whether "correctly elicited but still severed under B" occurs.

Experiment 2 (relation-type stratified severance test): across the same
Condition/Exception/Concession sample PLUS a separate Elaboration-control
sample, run Condition A only, score both severance checks, and report
severance rate per relation type, testing whether Condition/Exception/
Concession show higher severance than the Elaboration control.

Background note (context only, per task instructions -- NOT this
project's finding): atomic/propositional chunking can silently sever a
discourse relation where a satellite clause governs a nucleus clause.
This general phenomenon is documented prior art (Carlson & Marcu 2001's
discourse-tagging criteria; Fan et al. 2023's HCA-AMR2.0 finding that
decomposition "cannot preserve the original semantics" when discourse
connectives are dropped; Liu et al. 2026's Disco-RAG reporting 58.6
relation-F1 for a zero-shot LLM RST parser against a 60.0 supervised
baseline on RST-DT). This script tests whether the specific project
pipeline (server/components/response_parsing.py's propositional
extraction) exhibits this failure, and whether it is a capacity limit or
an elicitation gap.

Usage
-----
    venv/bin/python server/scripts/discourse_severance/run_experiments.py
    venv/bin/python server/scripts/discourse_severance/run_experiments.py --self-test
"""

import argparse
import datetime
import json
import os
import random
import sys
import time
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SERVER_DIR = os.path.dirname(os.path.dirname(SCRIPT_DIR))
if SERVER_DIR not in sys.path:
    sys.path.insert(0, SERVER_DIR)


def _load_server_env():
    """This project's dev/prod entry points (start.sh) load server/.env
    via `source ... ; set -a`, which is not in effect for a standalone
    script invocation. Load it here (without overriding any var already
    set in the real environment) so OPENAI_API_KEY is available the same
    way it is for the Flask app.
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

from scripts.discourse_severance import atomization_conditions  # noqa: E402
from scripts.discourse_severance import corpus  # noqa: E402
from scripts.discourse_severance import relation_elicitation  # noqa: E402
from scripts.discourse_severance import severance_detection  # noqa: E402
from scripts.discourse_severance.self_test import run_self_test  # noqa: E402

RELATION_BEARING_TYPES = ["Condition", "Exception", "Concession"]
CONTROL_TYPE = "Elaboration"

# Sampling / budget defaults -- kept in the 30-50-per-category range per
# task instructions, not scaled up further without reason.
DEFAULT_SEED = 13
DEFAULT_BATCH_SIZE = 150
DEFAULT_MAX_ELICITATION_TOTAL = 900
PER_RELATION_CAP = 17  # so 3 * 17 = 51, inside the 30-50 target band
ELABORATION_CAP = 45
MAX_WORKERS = 8

OUTPUT_DIR = SCRIPT_DIR
JSON_REPORT = os.path.join(OUTPUT_DIR, "discourse_severance_report.json")
MD_REPORT = os.path.join(OUTPUT_DIR, "RESULTS.md")
ELICITATION_CACHE = os.path.join(OUTPUT_DIR, "corpus_cache", "elicitation_log.jsonl")


def _parallel_map(func, items, max_workers=MAX_WORKERS, desc=""):
    """Run func(item) for each item, in parallel, preserving input order
    in the returned list. Same ThreadPoolExecutor-with-as_completed
    pattern as response_parsing.py's extract_claims, reused here because
    it is the project's existing convention for batches of independent
    LLM calls.
    """
    results = [None] * len(items)
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_idx = {executor.submit(func, item): i for i, item in enumerate(items)}
        done = 0
        for future in as_completed(future_to_idx):
            i = future_to_idx[future]
            results[i] = future.result()
            done += 1
            if desc and done % 25 == 0:
                print(f"  {desc}: {done}/{len(items)} done")
    return results


# --- Stage 1: corpus + relation elicitation sampling -------------------------


def build_corpus():
    """Loads both CFR parts, returning a dict per part with sentences and
    stats. Any fetch failure propagates (RuntimeError) -- no silent
    fallback to a smaller/synthetic corpus.
    """
    parts = {}
    for spec in corpus.CFR_PARTS:
        sentences, stats = corpus.load_cfr_part_sentences(**spec)
        parts[spec["label"]] = {"sentences": sentences, "stats": stats}
        print(f"Loaded {spec['label']}: {stats['prose_filtered_sentence_count']} "
              f"prose sentences (of {stats['raw_sentence_count']} raw) -- "
              f"{stats['source_note']}")
    return parts


def sample_and_elicit(parts, seed=DEFAULT_SEED, batch_size=DEFAULT_BATCH_SIZE,
                       max_total=DEFAULT_MAX_ELICITATION_TOTAL, model=None):
    """Randomly samples sentences (without replacement, split evenly
    across parts, fixed seed for reproducibility) in batches, running the
    relation-elicitation classifier on each in parallel, until either
    every relation-bearing category and the Elaboration control have
    reached their sample cap, or `max_total` elicitation calls have been
    spent, or both parts' sentence pools are exhausted -- whichever comes
    first. Returns (elicited_records, per_part_yield_stats).
    """
    rng = random.Random(seed)
    pools = {}
    for label, data in parts.items():
        pool = list(data["sentences"])
        rng.shuffle(pool)
        pools[label] = pool

    part_labels = list(pools.keys())
    cursor = {label: 0 for label in part_labels}

    elicited = []
    per_part_counts = {label: Counter() for label in part_labels}
    total_calls = 0

    def relation_target_met():
        by_type = Counter(r["relation_type"] for r in elicited if not r.get("_error"))
        rel_bearing_ok = all(by_type[t] >= PER_RELATION_CAP for t in RELATION_BEARING_TYPES)
        control_ok = by_type[CONTROL_TYPE] >= ELABORATION_CAP
        return rel_bearing_ok and control_ok

    with open(ELICITATION_CACHE, "w", encoding="utf-8") as log_fh:
        while total_calls < max_total and not relation_target_met():
            batch = []
            per_part_batch = batch_size // len(part_labels)
            for label in part_labels:
                start = cursor[label]
                chunk = pools[label][start:start + per_part_batch]
                cursor[label] += len(chunk)
                for idx, sentence in chunk:
                    batch.append((label, idx, sentence))
            if not batch:
                print("Corpus pools exhausted before elicitation targets were met.")
                break

            def _do(item):
                label, idx, sentence = item
                relation = relation_elicitation.elicit_relation(sentence, model=model)
                return {"part_label": label, "sentence_index": idx, "sentence": sentence, **relation}

            batch_results = _parallel_map(_do, batch, desc="elicitation")
            total_calls += len(batch)
            for rec in batch_results:
                elicited.append(rec)
                if not rec.get("_error"):
                    per_part_counts[rec["part_label"]][rec["relation_type"]] += 1
                log_fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
            log_fh.flush()

            by_type_running = Counter(r["relation_type"] for r in elicited if not r.get("_error"))
            print(f"Elicitation progress: {total_calls} sentences classified so far -- "
                  f"{dict(by_type_running)}")

    return elicited, per_part_counts, total_calls


def select_samples(elicited):
    """From all elicited records, select the capped relation-bearing
    sample (Condition/Exception/Concession, up to PER_RELATION_CAP each)
    and the Elaboration-control sample (up to ELABORATION_CAP), requiring
    a non-empty nucleus AND satellite (severance detection needs both).
    Selection order follows elicitation order (i.e. the order sentences
    were drawn from the shuffled corpus pool), so this is not
    re-randomized or cherry-picked after the fact.
    """
    by_type = defaultdict(list)
    excluded_incomplete = Counter()
    for rec in elicited:
        if rec.get("_error"):
            continue
        rt = rec["relation_type"]
        if rt not in RELATION_BEARING_TYPES + [CONTROL_TYPE]:
            continue
        if not rec.get("nucleus") or not rec.get("satellite"):
            excluded_incomplete[rt] += 1
            continue
        by_type[rt].append(rec)

    relation_bearing_sample = []
    for rt in RELATION_BEARING_TYPES:
        relation_bearing_sample.extend(by_type[rt][:PER_RELATION_CAP])
    elaboration_sample = by_type[CONTROL_TYPE][:ELABORATION_CAP]

    return relation_bearing_sample, elaboration_sample, excluded_incomplete, by_type


# --- Stage 2: Experiment 1 ---------------------------------------------------


def run_experiment_1(relation_bearing_sample, model=None):
    """For each Condition/Exception/Concession sentence: run Condition A,
    Condition B, and both severance checks on each condition's output.
    """
    def _process(rec):
        sentence = rec["sentence"]
        relation = {
            "relation_type": rec["relation_type"],
            "nucleus": rec["nucleus"],
            "satellite": rec["satellite"],
            "connective": rec["connective"],
        }
        claims_a = atomization_conditions.run_condition_a(sentence)
        claims_b = atomization_conditions.run_condition_b(sentence, relation, model=model)
        severance_a = severance_detection.run_severance_checks(sentence, relation, claims_a, model=model)
        severance_b = severance_detection.run_severance_checks(sentence, relation, claims_b, model=model)
        return {
            **rec,
            "condition_a_claims": claims_a,
            "condition_b_claims": claims_b,
            "severance_a": severance_a,
            "severance_b": severance_b,
        }

    print(f"Running Experiment 1 on {len(relation_bearing_sample)} relation-bearing sentences "
          "(Condition A + Condition B + both severance checks each)...")
    results = _parallel_map(_process, relation_bearing_sample, desc="experiment-1")
    return results


def summarize_experiment_1(results):
    n = len(results)
    if n == 0:
        return {"n": 0}

    def rate(preds):
        vals = [p for p in preds if p is not None]
        severed = sum(1 for p in vals if p is False)
        return {"n_scored": len(vals), "n_severed": severed,
                "severed_rate": severed / len(vals) if vals else None}

    llm_a = rate([r["severance_a"]["llm_judge_preserved"] for r in results])
    llm_b = rate([r["severance_b"]["llm_judge_preserved"] for r in results])
    rb_a = rate([r["severance_a"]["rule_based_preserved"] for r in results])
    rb_b = rate([r["severance_b"]["rule_based_preserved"] for r in results])

    def agreement(cond_key):
        agree, total = 0, 0
        for r in results:
            llm_p = r[cond_key]["llm_judge_preserved"]
            rb_p = r[cond_key]["rule_based_preserved"]
            if llm_p is None or rb_p is None:
                continue
            total += 1
            if llm_p == rb_p:
                agree += 1
        return {"n_compared": total, "n_agree": agree,
                "agreement_rate": agree / total if total else None}

    agreement_a = agreement("severance_a")
    agreement_b = agreement("severance_b")

    # The failure mode the task spec anticipates: elicitation succeeded
    # (nucleus/satellite/connective were extracted -- true for every
    # record in this sample by construction of select_samples) but
    # Condition B's LLM-judge STILL says the relation was severed.
    still_severed_under_b = [
        r for r in results if r["severance_b"]["llm_judge_preserved"] is False
    ]

    by_relation_type = {}
    for rt in RELATION_BEARING_TYPES:
        subset = [r for r in results if r["relation_type"] == rt]
        by_relation_type[rt] = {
            "n": len(subset),
            "llm_judge_severed_rate_a": rate(
                [r["severance_a"]["llm_judge_preserved"] for r in subset]
            ),
            "llm_judge_severed_rate_b": rate(
                [r["severance_b"]["llm_judge_preserved"] for r in subset]
            ),
        }

    return {
        "n": n,
        "condition_a": {"llm_judge": llm_a, "rule_based": rb_a, "agreement": agreement_a},
        "condition_b": {"llm_judge": llm_b, "rule_based": rb_b, "agreement": agreement_b},
        "by_relation_type": by_relation_type,
        "n_still_severed_under_b_llm_judge": len(still_severed_under_b),
        "still_severed_under_b_rate": len(still_severed_under_b) / n if n else None,
    }


# --- Stage 3: Experiment 2 ---------------------------------------------------


def run_experiment_2(experiment_1_results, elaboration_sample, model=None):
    """Reuses Experiment 1's Condition-A results for the Condition/
    Exception/Concession sentences (same sentence, same Condition-A
    output -- re-running would just spend API credits to get the same
    thing given temperature=0/fixed seed in generate_response) and runs
    Condition A fresh on the separate Elaboration-control sample.
    """
    reused = [
        {
            **{k: r[k] for k in ("part_label", "sentence_index", "sentence", "relation_type",
                                  "nucleus", "satellite", "connective")},
            "condition_a_claims": r["condition_a_claims"],
            "severance": r["severance_a"],
        }
        for r in experiment_1_results
    ]

    def _process(rec):
        sentence = rec["sentence"]
        relation = {
            "relation_type": rec["relation_type"],
            "nucleus": rec["nucleus"],
            "satellite": rec["satellite"],
            "connective": rec["connective"],
        }
        claims_a = atomization_conditions.run_condition_a(sentence)
        severance = severance_detection.run_severance_checks(sentence, relation, claims_a, model=model)
        return {**rec, "condition_a_claims": claims_a, "severance": severance}

    print(f"Running Experiment 2 control arm on {len(elaboration_sample)} Elaboration sentences "
          "(Condition A + both severance checks)...")
    fresh = _parallel_map(_process, elaboration_sample, desc="experiment-2-elaboration")

    return reused + fresh


def summarize_experiment_2(records):
    by_type = defaultdict(list)
    for r in records:
        by_type[r["relation_type"]].append(r)

    def rate(preds):
        vals = [p for p in preds if p is not None]
        severed = sum(1 for p in vals if p is False)
        return {"n_scored": len(vals), "n_severed": severed,
                "severed_rate": severed / len(vals) if vals else None}

    per_type = {}
    for rt, recs in by_type.items():
        per_type[rt] = {
            "n": len(recs),
            "llm_judge": rate([r["severance"]["llm_judge_preserved"] for r in recs]),
            "rule_based": rate([r["severance"]["rule_based_preserved"] for r in recs]),
        }

    stats_test = compare_relation_bearing_vs_control(by_type)

    return {"per_relation_type": per_type, "statistical_test": stats_test}


def compare_relation_bearing_vs_control(by_type):
    """2x2 contingency table (severed vs preserved) comparing the pooled
    Condition+Exception+Concession group against the Elaboration control,
    on the LLM-judge metric (the less coarse of the two). Uses scipy if
    available; otherwise reports raw counts only, per task instructions
    not to overstate significance if a stats library isn't available or
    if N is small.
    """
    rel_bearing = [r for rt in RELATION_BEARING_TYPES for r in by_type.get(rt, [])]
    control = by_type.get(CONTROL_TYPE, [])

    def severed_counts(recs):
        vals = [r["severance"]["llm_judge_preserved"] for r in recs]
        vals = [v for v in vals if v is not None]
        severed = sum(1 for v in vals if v is False)
        preserved = len(vals) - severed
        return severed, preserved

    rb_severed, rb_preserved = severed_counts(rel_bearing)
    ctrl_severed, ctrl_preserved = severed_counts(control)

    result = {
        "relation_bearing_n": rb_severed + rb_preserved,
        "relation_bearing_severed": rb_severed,
        "relation_bearing_severed_rate": (
            rb_severed / (rb_severed + rb_preserved) if (rb_severed + rb_preserved) else None
        ),
        "control_n": ctrl_severed + ctrl_preserved,
        "control_severed": ctrl_severed,
        "control_severed_rate": (
            ctrl_severed / (ctrl_severed + ctrl_preserved) if (ctrl_severed + ctrl_preserved) else None
        ),
    }

    try:
        from scipy.stats import fisher_exact, chi2_contingency
        table = [[rb_severed, rb_preserved], [ctrl_severed, ctrl_preserved]]
        odds_ratio, fisher_p = fisher_exact(table)
        result["fisher_exact_p_value"] = fisher_p
        result["fisher_odds_ratio"] = odds_ratio
        if all(sum(row) > 0 for row in table) and all(sum(col) > 0 for col in zip(*table)):
            chi2, chi2_p, dof, _ = chi2_contingency(table)
            result["chi2_p_value"] = chi2_p
        result["test_note"] = (
            "Fisher's exact test on the 2x2 severed/preserved table, "
            "Condition+Exception+Concession (pooled) vs Elaboration control. "
            "Small-N caveat applies -- see RESULTS.md for the actual counts "
            "before treating the p-value as conclusive."
        )
    except ImportError:
        result["test_note"] = (
            "scipy not available in this environment -- reporting raw "
            "counts/rates only, no significance test computed."
        )

    return result


# --- reporting ----------------------------------------------------------


def pick_failure_examples(results, n=4):
    """Examples where Condition A severed the relation (per LLM-judge),
    for inclusion in RESULTS.md, preferring a spread across relation
    types and including at least one "still severed under B" case if one
    exists.
    """
    severed_a = [r for r in results if r["severance_a"]["llm_judge_preserved"] is False]
    still_severed_b = [r for r in results if r["severance_b"]["llm_judge_preserved"] is False]
    examples = []
    seen_types = set()
    for r in severed_a:
        if r["relation_type"] not in seen_types:
            examples.append(r)
            seen_types.add(r["relation_type"])
        if len(examples) >= n:
            break
    for r in still_severed_b:
        if r not in examples and len(examples) < n + 2:
            examples.append(r)
    return examples


def write_json_report(corpus_stats, elicitation_meta, exp1_results, exp1_summary,
                       exp2_records, exp2_summary, path=JSON_REPORT):
    report = {
        "run_date": datetime.date.today().isoformat(),
        "corpus": corpus_stats,
        "elicitation": elicitation_meta,
        "experiment_1": {
            "summary": exp1_summary,
            "records": exp1_results,
        },
        "experiment_2": {
            "summary": exp2_summary,
            "records": exp2_records,
        },
    }
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(report, fh, indent=2, ensure_ascii=False)
    return path


def _fmt_rate(rate_dict):
    if rate_dict is None or rate_dict.get("severed_rate") is None:
        return "n/a"
    return f"{rate_dict['n_severed']}/{rate_dict['n_scored']} ({100*rate_dict['severed_rate']:.1f}%)"


def write_markdown_report(corpus_stats, elicitation_meta, exp1_summary, exp1_examples,
                           exp2_summary, path=MD_REPORT):
    lines = [
        "# Discourse severance under LLM-prompted atomization: results",
        "",
        f"Run date: {datetime.date.today().isoformat()}. Generated by "
        "`server/scripts/discourse_severance/run_experiments.py`.",
        "",
        "## Prior art (context only -- not this project's finding)",
        "",
        "The motivating background for these two experiments -- that "
        "atomic/propositional chunking can silently sever a discourse "
        "relation where a satellite clause (Condition/Exception/"
        "Concession) governs a nucleus clause -- is established prior "
        "art, cited here for context, not claimed as a finding of this "
        "project:",
        "",
        "- Carlson & Marcu (2001), discourse-tagging criteria for "
        "RST-style relation annotation.",
        "- Fan et al. (2023), HCA-AMR2.0: decomposition \"cannot preserve "
        "the original semantics\" when discourse connectives are dropped.",
        "- Liu et al. (2026), Disco-RAG: a zero-shot LLM RST parser "
        "(Llama-3.3-70B) reaches 58.6 relation-F1 vs. a supervised "
        "parser's 60.0 on RST-DT.",
        "",
        "What IS this project's contribution: whether this specific "
        "pipeline's atomization (server/components/response_parsing.py) "
        "loses this structure because of a model capacity limit or an "
        "elicitation gap (Experiment 1), and whether Condition/Exception/"
        "Concession relations are severed at a higher rate than an "
        "Elaboration control (Experiment 2).",
        "",
        "## Corpus",
        "",
    ]
    for label, stats in corpus_stats.items():
        lines.append(
            f"- **{label}**: {stats['source_note']} "
            f"(eCFR versioner API, date `{stats['date']}`); "
            f"{stats['raw_sentence_count']} raw sentences -> "
            f"{stats['prose_filtered_sentence_count']} after prose "
            "filtering (drops `[Reserved]` placeholders, bare citation/"
            "list lines, and exact-duplicate boilerplate -- see "
            "`corpus.py:segment_and_filter`)."
        )
    lines += [
        "",
        f"- Source: eCFR versioner API "
        "(`https://www.ecfr.gov/api/versioner/v1/full/{date}/title-{title}.xml?part={part}`). "
        "govinfo.gov bulk data was NOT needed -- eCFR was reachable "
        "(after retrying past a transient 503/queue-full response).",
        "",
        "## Relation elicitation yield",
        "",
        f"- Total sentences classified by the relation-elicitation LLM "
        f"call: **{elicitation_meta['total_calls']}** (random sample, "
        f"seed={elicitation_meta['seed']}, drawn evenly from both parts' "
        "prose-filtered sentence pools).",
        "",
        "| Part | Condition | Exception | Concession | Elaboration | None/error |",
        "|---|---|---|---|---|---|",
    ]
    for label, counts in elicitation_meta["per_part_yield"].items():
        lines.append(
            f"| {label} | {counts.get('Condition', 0)} | "
            f"{counts.get('Exception', 0)} | {counts.get('Concession', 0)} | "
            f"{counts.get('Elaboration', 0)} | {counts.get('None', 0)} |"
        )
    lines += [
        "",
        f"- Sentences excluded from the samples below despite a "
        "relation-bearing/Elaboration classification because nucleus "
        f"and/or satellite came back empty: "
        f"{dict(elicitation_meta['excluded_incomplete'])}",
        "",
        "## Sample sizes used",
        "",
        f"- Experiment 1 (Condition/Exception/Concession, combined): "
        f"**{exp1_summary['n']}** sentences "
        f"(target band: 30-50 combined, capped at {PER_RELATION_CAP} per "
        "relation type).",
        f"- Experiment 2 control (Elaboration): "
        f"**{exp2_summary['per_relation_type'].get('Elaboration', {}).get('n', 0)}** sentences.",
        "",
        "## Experiment 1: capacity-vs-elicitation ablation",
        "",
        "| Condition | Metric | Severed | Rate |",
        "|---|---|---|---|",
        f"| A (standard atomization) | LLM-judge | "
        f"{exp1_summary['condition_a']['llm_judge']['n_severed']} | "
        f"{_fmt_rate(exp1_summary['condition_a']['llm_judge'])} |",
        f"| A (standard atomization) | rule-based | "
        f"{exp1_summary['condition_a']['rule_based']['n_severed']} | "
        f"{_fmt_rate(exp1_summary['condition_a']['rule_based'])} |",
        f"| B (relation-aware atomization) | LLM-judge | "
        f"{exp1_summary['condition_b']['llm_judge']['n_severed']} | "
        f"{_fmt_rate(exp1_summary['condition_b']['llm_judge'])} |",
        f"| B (relation-aware atomization) | rule-based | "
        f"{exp1_summary['condition_b']['rule_based']['n_severed']} | "
        f"{_fmt_rate(exp1_summary['condition_b']['rule_based'])} |",
        "",
        f"- Agreement between LLM-judge and rule-based check, Condition A: "
        f"{exp1_summary['condition_a']['agreement']['n_agree']}/"
        f"{exp1_summary['condition_a']['agreement']['n_compared']} "
        f"({100*exp1_summary['condition_a']['agreement']['agreement_rate']:.1f}%)"
        if exp1_summary['condition_a']['agreement']['agreement_rate'] is not None else
        "- Agreement (Condition A): n/a (no comparable pairs)",
        f"- Agreement between LLM-judge and rule-based check, Condition B: "
        f"{exp1_summary['condition_b']['agreement']['n_agree']}/"
        f"{exp1_summary['condition_b']['agreement']['n_compared']} "
        f"({100*exp1_summary['condition_b']['agreement']['agreement_rate']:.1f}%)"
        if exp1_summary['condition_b']['agreement']['agreement_rate'] is not None else
        "- Agreement (Condition B): n/a (no comparable pairs)",
        "",
        "### Per-relation-type breakdown (Experiment 1, LLM-judge)",
        "",
        "| Relation | N | Severed under A | Severed under B |",
        "|---|---|---|---|",
    ]
    for rt, d in exp1_summary["by_relation_type"].items():
        lines.append(
            f"| {rt} | {d['n']} | {_fmt_rate(d['llm_judge_severed_rate_a'])} | "
            f"{_fmt_rate(d['llm_judge_severed_rate_b'])} |"
        )
    lines += [
        "",
        "### The \"correctly elicited but still severed\" failure mode",
        "",
        f"Sentences where the model was explicitly told the relation type, "
        "nucleus, satellite, and connective (Condition B), and STILL "
        "produced an atomized claim set the LLM-judge scored as severed: "
        f"**{exp1_summary['n_still_severed_under_b_llm_judge']}** of "
        f"{exp1_summary['n']} "
        f"({100*exp1_summary['still_severed_under_b_rate']:.1f}%)."
        if exp1_summary['n'] else "n/a (empty sample).",
        "",
        "## Experiment 2: relation-type stratified severance",
        "",
        "| Relation type | N | LLM-judge severed | Rule-based severed |",
        "|---|---|---|---|",
    ]
    for rt, d in exp2_summary["per_relation_type"].items():
        lines.append(
            f"| {rt} | {d['n']} | {_fmt_rate(d['llm_judge'])} | "
            f"{_fmt_rate(d['rule_based'])} |"
        )
    st = exp2_summary["statistical_test"]
    lines += [
        "",
        f"- Condition+Exception+Concession (pooled) severed: "
        f"{st['relation_bearing_severed']}/{st['relation_bearing_n']} "
        f"({100*st['relation_bearing_severed_rate']:.1f}%)" if st.get('relation_bearing_severed_rate') is not None else "- Condition+Exception+Concession (pooled): n/a",
        f"- Elaboration control severed: "
        f"{st['control_severed']}/{st['control_n']} "
        f"({100*st['control_severed_rate']:.1f}%)" if st.get('control_severed_rate') is not None else "- Elaboration control: n/a",
        f"- {st['test_note']}",
    ]
    if "fisher_exact_p_value" in st:
        lines.append(f"- Fisher's exact test p-value: {st['fisher_exact_p_value']:.4f}")
    if "chi2_p_value" in st:
        lines.append(f"- Chi-square test p-value: {st['chi2_p_value']:.4f}")
    lines += [
        "",
        "## Example failures",
        "",
    ]
    for r in exp1_examples:
        lines.append(f"**[{r['relation_type']}]** \"{r['sentence']}\"")
        lines.append(f"- Nucleus: {r['nucleus']!r}; Satellite: {r['satellite']!r}; "
                      f"Connective: {r['connective']!r}")
        lines.append(f"- Condition A claims: {r['condition_a_claims']}")
        lines.append(f"  - LLM-judge preserved={r['severance_a']['llm_judge_preserved']}: "
                      f"{r['severance_a']['llm_judge_reasoning']}")
        lines.append(f"  - rule-based preserved={r['severance_a']['rule_based_preserved']}: "
                      f"{r['severance_a']['rule_based_detail']}")
        lines.append(f"- Condition B claims: {r['condition_b_claims']}")
        lines.append(f"  - LLM-judge preserved={r['severance_b']['llm_judge_preserved']}: "
                      f"{r['severance_b']['llm_judge_reasoning']}")
        lines.append(f"  - rule-based preserved={r['severance_b']['rule_based_preserved']}: "
                      f"{r['severance_b']['rule_based_detail']}")
        lines.append("")
    lines += [
        "## Self-test",
        "",
        "`--self-test` runs the full plumbing (elicitation -> Condition A/B "
        "atomization -> both severance checks) on a small SYNTHETIC hand-"
        "written sentence set with every LLM call site stubbed -- no "
        "network access, no API cost. See "
        "`server/scripts/discourse_severance/self_test.py`.",
        "",
        "Full machine-readable results: "
        "`server/scripts/discourse_severance/discourse_severance_report.json`.",
        "",
    ]
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines))
    return path


# --- entry point --------------------------------------------------------


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--self-test", action="store_true",
                         help="run on a tiny SYNTHETIC inline sample (no network, "
                              "no report files) to verify plumbing only")
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument("--batch-size", type=int, default=DEFAULT_BATCH_SIZE)
    parser.add_argument("--max-elicitation-total", type=int, default=DEFAULT_MAX_ELICITATION_TOTAL)
    parser.add_argument("--model", type=str, default=None)
    args = parser.parse_args(argv)

    if args.self_test:
        run_self_test()
        return 0

    start = time.time()
    parts = build_corpus()
    corpus_stats = {label: data["stats"] for label, data in parts.items()}

    elicited, per_part_counts, total_calls = sample_and_elicit(
        parts, seed=args.seed, batch_size=args.batch_size,
        max_total=args.max_elicitation_total, model=args.model,
    )
    relation_bearing_sample, elaboration_sample, excluded_incomplete, by_type = \
        select_samples(elicited)

    elicitation_meta = {
        "seed": args.seed,
        "total_calls": total_calls,
        "per_part_yield": {
            label: dict(counts) for label, counts in per_part_counts.items()
        },
        "excluded_incomplete": dict(excluded_incomplete),
        "relation_bearing_sample_size": len(relation_bearing_sample),
        "elaboration_sample_size": len(elaboration_sample),
    }
    print(f"\nSelected {len(relation_bearing_sample)} relation-bearing sentences "
          f"(Condition/Exception/Concession) and {len(elaboration_sample)} "
          "Elaboration-control sentences.")

    exp1_results = run_experiment_1(relation_bearing_sample, model=args.model)
    exp1_summary = summarize_experiment_1(exp1_results)

    exp2_records = run_experiment_2(exp1_results, elaboration_sample, model=args.model)
    exp2_summary = summarize_experiment_2(exp2_records)

    exp1_examples = pick_failure_examples(exp1_results)

    json_path = write_json_report(corpus_stats, elicitation_meta, exp1_results,
                                   exp1_summary, exp2_records, exp2_summary)
    md_path = write_markdown_report(corpus_stats, elicitation_meta, exp1_summary,
                                     exp1_examples, exp2_summary)

    elapsed = time.time() - start
    print(f"\nDone in {elapsed:.0f}s. Wrote {json_path}\nWrote {md_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
