"""Full-scale run: AtomicRAG's OpenIE atomization (atomicrag_openie_adapter.py)
against the SAME 272 governing-relation (Condition/Concession) + 206
Elaboration-control FactoidWiki paragraphs already sampled and classified
for the Propositionizer track -- read directly from
../logs/task7_experiment_govern_log.jsonl and
../logs/task7_experiment_elaboration_log.jsonl's `content` field (NOT
resampled, NOT the Propositionizer's already-atomized claims -- the raw
source paragraph, so both chunkers are compared apples-to-apples on
identical source text), then scored with the SAME severance-detection
infrastructure ../run_experiment_1_2.py used for Condition A/B:
../severance_judge_paragraph.llm_judge_paragraph_severance (the LLM judge)
plus a rule-based connective-survival check
(../candidate_prefilter.normalize_text, mirroring
../run_experiment_1_2.py's summarize_structural_comparison).

REUSE, NOT REIMPLEMENTATION, OF THE JUDGE: this script imports
`llm_judge_paragraph_severance` and `_RELATION_DESCRIPTIONS` from
../severance_judge_paragraph.py and `normalize_text` from
../candidate_prefilter.py directly (a real import across the
atomicrag_track/factoidwiki_track boundary), rather than duplicating
either a third time. This deliberately departs from env_utils.py's
"factoidwiki_track/ does not import its siblings outside the directory"
convention, but that convention was about not reaching OUTSIDE
factoidwiki_track/ (into discourse_severance/'s CFR-track scripts);
atomicrag_track/ is nested INSIDE factoidwiki_track/, was built
specifically to extend this track's own already-validated severance
measurement to a second chunker, and severance_judge_paragraph.py's own
docstring already warns against introducing "a second, silently-
miscalibrated metric" -- copying the judge prompt a third time here would
be exactly that.

NO CONDITION B FOR ATOMICRAG: see atomicrag_openie_adapter.py's module
docstring ("CONDITION B / RELATION-AWARE ELICITATION IS NOT POSSIBLE FOR
THIS CHUNKER") for the full evidence (no relation-hint input slot in any
of AtomicRAG's OpenIE prompts). This script therefore reports only ONE
AtomicRAG atomization condition per paragraph -- there is no
capacity-vs-elicitation ablation for this chunker, unlike Experiment 1's
Condition A vs Condition B design for the Propositionizer.

Every governing paragraph gets: AtomicRAG atomization (2 real LLM calls,
via the SINGLE batched OpenIE call for the whole sample -- not one-by-one,
see below) + 1 severance-judge call against AtomicRAG's fragments. Every
Elaboration-control paragraph gets the same. Total real LLM calls for the
full 478-paragraph sample: 478 * 2 (AtomicRAG OpenIE: NER + unified
triple/fragment extraction) + 478 (severance judge) = 1434.

BATCHING: the 478-paragraph AtomicRAG atomization is ONE call to
`atomicrag_openie_adapter.run_atomicrag_atomization` (which itself calls
AtomicRAG's real `OpenIE.batch_unified_openie` once), not a Python-level
loop -- concurrency is AtomicRAG's own async semaphore
(`BaseConfig.max_concurrency`). The severance-judge calls (this project's
own `generate_response`, synchronous) are parallelized with a
ThreadPoolExecutor, same `_parallel_map` pattern duplicated across this
project's scripts (see ../run_two_stage_pipeline.py's docstring on why
this is duplicated rather than imported).

Usage:
    venv/bin/python server/scripts/discourse_severance/factoidwiki_track/atomicrag_track/run_atomicrag_experiment.py
"""

import json
import os
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed

ATOMICRAG_TRACK_DIR = os.path.dirname(os.path.abspath(__file__))
FACTOIDWIKI_TRACK_DIR = os.path.dirname(ATOMICRAG_TRACK_DIR)
if ATOMICRAG_TRACK_DIR not in sys.path:
    sys.path.insert(0, ATOMICRAG_TRACK_DIR)
if FACTOIDWIKI_TRACK_DIR not in sys.path:
    sys.path.insert(0, FACTOIDWIKI_TRACK_DIR)

from env_utils import load_server_env  # noqa: E402  (intra-track reuse, see module docstring)

load_server_env()

import atomicrag_openie_adapter as adapter  # noqa: E402
from severance_judge_paragraph import llm_judge_paragraph_severance  # noqa: E402
from candidate_prefilter import normalize_text  # noqa: E402

GOVERN_LOG_SRC = os.path.join(FACTOIDWIKI_TRACK_DIR, "logs", "task7_experiment_govern_log.jsonl")
ELABORATION_LOG_SRC = os.path.join(FACTOIDWIKI_TRACK_DIR, "logs", "task7_experiment_elaboration_log.jsonl")

CACHE_DIR = os.path.join(ATOMICRAG_TRACK_DIR, "atomicrag_llm_cache")
LOGS_DIR = os.path.join(ATOMICRAG_TRACK_DIR, "logs")
RESULTS_DIR = os.path.join(ATOMICRAG_TRACK_DIR, "results")
GOVERN_LOG_OUT = os.path.join(LOGS_DIR, "atomicrag_govern_log.jsonl")
ELABORATION_LOG_OUT = os.path.join(LOGS_DIR, "atomicrag_elaboration_log.jsonl")
REPORT_JSON = os.path.join(RESULTS_DIR, "atomicrag_experiment_1_2_report.json")

GOVERNING_RELATION_TYPES = ["Condition", "Concession"]
ATOMICRAG_MAX_CONCURRENCY = 5  # lowered from an initial 20 after the first full run hit 132/478 RateLimitErrors
# (all in the "unified extraction" stage -- see logs/atomicrag_govern_log.jsonl /
# atomicrag_elaboration_log.jsonl's now-stale first-run atomicrag_error values, and
# atomicrag_llm_cache/llm_cache/*.sqlite, which already holds the 346 successful
# chunks' real responses from that run, keyed by hash(messages, model, seed,
# temperature) via CacheOpenAI's own on-disk cache -- so re-running at this lower
# concurrency is cheap: only the previously-failed chunks make fresh API calls,
# everything that already succeeded is served from cache, not silently re-billed).
JUDGE_MAX_WORKERS = 8  # matches this project's established DEFAULT_MAX_WORKERS convention

CONDITION_B_NOT_APPLICABLE_NOTE = (
    "AtomicRAG's OpenIE prompts (NER, unified triple+knowledge-fragment "
    "extraction) have no relation-hint input slot -- verified by reading "
    "every prompt template's parameter list (only {passage}, "
    "{candidate_entities}/{named_entity_json}) and every OpenIE public "
    "method signature. There is therefore no AtomicRAG analog of this "
    "track's Condition B (relation-aware elicit-then-atomize) or of "
    "Experiment 1's capacity-vs-elicitation ablation for this chunker. "
    "See atomicrag_openie_adapter.py's module docstring for the full "
    "evidence. This is reported as a stated limitation, not forced."
)


def _load_jsonl(path):
    records = []
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    return records


def _parallel_map(func, items, max_workers, label=""):
    """Same ThreadPoolExecutor-with-as_completed pattern duplicated across
    this project's scripts (see ../run_two_stage_pipeline.py).
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
            if done % 50 == 0 or done == len(items):
                print(f"  {label} {done}/{len(items)}", flush=True)
    return results


def _relation_dict(rec):
    return {
        "relation_type": rec["relation_type"],
        "nucleus": rec["nucleus"],
        "satellite": rec["satellite"],
        "connective": rec["connective"],
    }


def _score_severance(rec):
    relation = _relation_dict(rec)
    severance = llm_judge_paragraph_severance(rec["content"], relation, rec["atomicrag_propositions"])
    return {**rec, "severance_atomicrag": severance}


def _rate(preds):
    vals = [p for p in preds if p is not None]
    severed = sum(1 for p in vals if p is False)
    return {"n_scored": len(vals), "n_severed": severed,
            "severed_rate": severed / len(vals) if vals else None}


def summarize_experiment_1(govern_results):
    by_type = {}
    for rt in GOVERNING_RELATION_TYPES:
        subset = [r for r in govern_results if r["relation_type"] == rt]
        by_type[rt] = {"n": len(subset), "severed_atomicrag": _rate([r["severance_atomicrag"]["preserved"] for r in subset])}
    overall = _rate([r["severance_atomicrag"]["preserved"] for r in govern_results])
    n_errors = sum(1 for r in govern_results if r.get("atomicrag_error"))
    return {
        "n": len(govern_results),
        "atomicrag_overall": overall,
        "by_relation_type": by_type,
        "n_atomicrag_atomization_errors": n_errors,
    }


def summarize_experiment_2(govern_results, elaboration_results):
    def severed_counts(preds):
        vals = [p for p in preds if p is not None]
        severed = sum(1 for p in vals if p is False)
        return severed, len(vals) - severed

    govern_preds = [r["severance_atomicrag"]["preserved"] for r in govern_results]
    control_preds = [r["severance_atomicrag"]["preserved"] for r in elaboration_results]
    gov_severed, gov_preserved = severed_counts(govern_preds)
    ctrl_severed, ctrl_preserved = severed_counts(control_preds)

    per_relation_type = {}
    for rt in GOVERNING_RELATION_TYPES + ["Elaboration"]:
        subset = ([r["severance_atomicrag"]["preserved"] for r in govern_results if r["relation_type"] == rt]
                   if rt in GOVERNING_RELATION_TYPES else control_preds)
        per_relation_type[rt] = _rate(subset)

    result = {
        "per_relation_type_atomicrag": per_relation_type,
        "governing_pooled_n": gov_severed + gov_preserved,
        "governing_pooled_severed": gov_severed,
        "governing_pooled_severed_rate": gov_severed / (gov_severed + gov_preserved) if (gov_severed + gov_preserved) else None,
        "elaboration_control_n": ctrl_severed + ctrl_preserved,
        "elaboration_control_severed": ctrl_severed,
        "elaboration_control_severed_rate": ctrl_severed / (ctrl_severed + ctrl_preserved) if (ctrl_severed + ctrl_preserved) else None,
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
        result["test_note"] = ("Fisher's exact test on the 2x2 severed/preserved table, Condition+Concession "
                                "(pooled, AtomicRAG output) vs Elaboration control (AtomicRAG output). Mirrors "
                                "../run_experiment_1_2.py's summarize_experiment_2 design.")
    except ImportError:
        result["test_note"] = "scipy not available in this environment -- reporting raw counts/rates only."
    return result


def summarize_structural_comparison(govern_results):
    """Propositionizer (Condition A, already in the reused log records)
    vs AtomicRAG -- same free, lexical connective-survival signal
    ../run_experiment_1_2.py's summarize_structural_comparison computes
    for Condition A vs Condition B, computed here for Condition A vs
    AtomicRAG instead. Same caveat carries: presence somewhere in the
    output set is not the same as still governing the right clause.
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
            "n_condition_a": r["n_condition_a_propositions"],
            "n_atomicrag": r["n_atomicrag_propositions"],
            "conn_survives_condition_a": connective_survives(r["connective"], r["condition_a_propositions"]),
            "conn_survives_atomicrag": connective_survives(r["connective"], r["atomicrag_propositions"]),
        })

    def avg(vals):
        return sum(vals) / len(vals) if vals else None

    def survival(vals):
        scored = [v for v in vals if v is not None]
        return {"n_scored": len(scored), "n_survives": sum(1 for v in scored if v),
                "survival_rate": sum(1 for v in scored if v) / len(scored) if scored else None}

    def block(subset):
        return {
            "n": len(subset),
            "avg_propositions_condition_a": avg([row["n_condition_a"] for row in subset]),
            "avg_propositions_atomicrag": avg([row["n_atomicrag"] for row in subset]),
            "connective_survival_condition_a": survival([row["conn_survives_condition_a"] for row in subset]),
            "connective_survival_atomicrag": survival([row["conn_survives_atomicrag"] for row in subset]),
        }

    overall = block(rows)
    by_relation_type = {rt: block([row for row in rows if row["relation_type"] == rt]) for rt in GOVERNING_RELATION_TYPES}
    return {"overall": overall, "by_relation_type": by_relation_type}


def main():
    os.makedirs(LOGS_DIR, exist_ok=True)
    os.makedirs(RESULTS_DIR, exist_ok=True)
    os.makedirs(CACHE_DIR, exist_ok=True)

    govern_sample = _load_jsonl(GOVERN_LOG_SRC)
    elaboration_sample = _load_jsonl(ELABORATION_LOG_SRC)
    print(f"Reusing existing sample (no resampling): {len(govern_sample)} governing "
          f"({sum(1 for r in govern_sample if r['relation_type']=='Condition')} Condition, "
          f"{sum(1 for r in govern_sample if r['relation_type']=='Concession')} Concession) + "
          f"{len(elaboration_sample)} Elaboration-control paragraphs, from {GOVERN_LOG_SRC} / {ELABORATION_LOG_SRC}.")

    id_to_content = {}
    for rec in govern_sample:
        id_to_content[f"govern-{rec['pool_index']}"] = rec["content"]
    for rec in elaboration_sample:
        id_to_content[f"elab-{rec['pool_index']}"] = rec["content"]

    print(f"Calling AtomicRAG OpenIE (single batched batch_unified_openie call) on "
          f"{len(id_to_content)} paragraphs -- {2 * len(id_to_content)} real LLM calls "
          f"(NER + unified extraction per paragraph), max_concurrency={ATOMICRAG_MAX_CONCURRENCY}...")
    atomization = adapter.run_atomicrag_atomization(id_to_content, save_dir=CACHE_DIR,
                                                      max_concurrency=ATOMICRAG_MAX_CONCURRENCY)

    total_prompt_tokens = sum(v["atomicrag_prompt_tokens"] for v in atomization.values())
    total_completion_tokens = sum(v["atomicrag_completion_tokens"] for v in atomization.values())
    n_atomicrag_errors = sum(1 for v in atomization.values() if v["atomicrag_error"])
    print(f"AtomicRAG atomization done: {total_prompt_tokens} prompt + {total_completion_tokens} completion "
          f"tokens, {n_atomicrag_errors} per-chunk errors.")

    govern_with_atoms = [{**rec, **atomization[f"govern-{rec['pool_index']}"]} for rec in govern_sample]
    elaboration_with_atoms = [{**rec, **atomization[f"elab-{rec['pool_index']}"]} for rec in elaboration_sample]

    print(f"Scoring severance for {len(govern_with_atoms)} governing paragraphs (1 judge call each)...")
    govern_results = _parallel_map(_score_severance, govern_with_atoms, max_workers=JUDGE_MAX_WORKERS, label="govern-judge")
    with open(GOVERN_LOG_OUT, "w", encoding="utf-8") as fh:
        for rec in govern_results:
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")

    print(f"Scoring severance for {len(elaboration_with_atoms)} Elaboration-control paragraphs (1 judge call each)...")
    elaboration_results = _parallel_map(_score_severance, elaboration_with_atoms, max_workers=JUDGE_MAX_WORKERS, label="elab-judge")
    with open(ELABORATION_LOG_OUT, "w", encoding="utf-8") as fh:
        for rec in elaboration_results:
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")

    exp1_summary = summarize_experiment_1(govern_results)
    exp2_summary = summarize_experiment_2(govern_results, elaboration_results)
    structural_summary = summarize_structural_comparison(govern_results)

    n_severance_judge_calls = len(govern_results) + len(elaboration_results)
    n_atomicrag_calls = 2 * len(id_to_content)
    report = {
        "attribution_statement": adapter.ATTRIBUTION_STATEMENT,
        "condition_b_note": CONDITION_B_NOT_APPLICABLE_NOTE,
        "govern_sample_size": len(govern_sample),
        "elaboration_sample_size": len(elaboration_sample),
        "govern_log_source": GOVERN_LOG_SRC,
        "elaboration_log_source": ELABORATION_LOG_SRC,
        "govern_log": GOVERN_LOG_OUT,
        "elaboration_log": ELABORATION_LOG_OUT,
        "experiment_1": exp1_summary,
        "experiment_2": exp2_summary,
        "structural_comparison_condition_a_vs_atomicrag": structural_summary,
        "llm_call_accounting": {
            "n_atomicrag_openie_calls": n_atomicrag_calls,
            "n_severance_judge_calls": n_severance_judge_calls,
            "n_condition_b_calls": 0,
            "total_real_llm_calls": n_atomicrag_calls + n_severance_judge_calls,
            "atomicrag_prompt_tokens": total_prompt_tokens,
            "atomicrag_completion_tokens": total_completion_tokens,
            "n_atomicrag_atomization_errors": n_atomicrag_errors,
        },
    }
    with open(REPORT_JSON, "w", encoding="utf-8") as fh:
        json.dump(report, fh, indent=2, ensure_ascii=False)

    print("\n" + "#" * 90)
    print("ATOMICRAG EXPERIMENT 1/2 SUMMARY")
    print("#" * 90)
    print(json.dumps({
        "experiment_1": exp1_summary,
        "experiment_2": exp2_summary,
        "structural_comparison_condition_a_vs_atomicrag": structural_summary,
        "llm_call_accounting": report["llm_call_accounting"],
    }, indent=2))
    print(f"\nWrote {REPORT_JSON}")
    print(f"Govern log: {GOVERN_LOG_OUT}")
    print(f"Elaboration log: {ELABORATION_LOG_OUT}")
    print(f"\n{adapter.ATTRIBUTION_STATEMENT}")


if __name__ == "__main__":
    main()
