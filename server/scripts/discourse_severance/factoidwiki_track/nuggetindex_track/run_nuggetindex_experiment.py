"""NuggetIndex track: extract+judge orchestration. Measures whether
NuggetIndex's `LLMExtractor`-produced fact triples still convey a
Condition/Concession relation identified in the SAME 272 governing
(75 Condition + 197 Concession) + 206 Elaboration-control FactoidWiki
paragraphs ../run_experiment_1_2.py already built and scored for
Propositionizer (Condition A) and the gpt-4o-mini relation-aware
atomizer (Condition B) -- see ../logs/task7_experiment_govern_log.jsonl
/ task7_experiment_elaboration_log.jsonl (read-only source here; see
env_utils.py).

ONLY ONE CONDITION IS RUN FOR NUGGETINDEX -- read this before looking at
the numbers below. ../condition_b_atomizer.py's "Condition B" design
(elicit-then-atomize: give the atomizer the already-elicited relation
and instruct it to preserve/flag that relation) has NO NuggetIndex
analogue. Confirmed by reading the real source, not assumed:
`nuggetindex.extractors.llm.LLMExtractor.aextract(text, *, context="",
source_id=None)` has no parameter for "relation to preserve", and
`extractors/prompts/extraction.md` (NuggetIndex's own extraction prompt,
read in full) contains zero mention of discourse relations, conditions,
concessions, or any construct like "preserve the following relation
while atomizing" -- its instructions are entirely about predicate
normalization, entity-type tagging, and one-fact-per-(subject,object)-pair
splitting. There is no built-in relation-aware extraction mode to turn
on, and hand-writing a NuggetIndex-branded "Condition B" by swapping in a
custom prompt file (`LLMExtractor(..., prompt_path=...)` does support
this) would not be testing NuggetIndex's own capability -- it would be
testing OUR OWN prompt engineering wearing NuggetIndex's name, which
this task's brief explicitly warns against. So: standard-extraction-only
is reported here, matching how this same limitation would be reported
for AtomicRAG if it turned out to have no relation-aware mode either
(that integration is separate and not assumed here). This means
NuggetIndex gets an Experiment-2-style analysis (governing pooled vs.
Elaboration control, single condition) but no Experiment-1-style A-vs-B
ablation.

CONTEXT-WINDOW CAVEAT: see ../nuggetindex_extractor_adapter.py's
docstring -- confirmed FALSE by reading the real NuggetIndex source
(no built-in sentence-window assembly anywhere in the extractor or
pipeline code). This script also runs
sentence_boundary_diagnostic.flag_boundary_spanning_severed_cases on
every severed governing case, per the task brief's explicit instruction
to flag any severed case where the connective's clause spans a sentence
boundary within the source paragraph -- a property of the DATA, not of
NuggetIndex specifically, reported regardless of the context-window
finding above.

Usage:
    venv/bin/python server/scripts/discourse_severance/factoidwiki_track/nuggetindex_track/run_nuggetindex_experiment.py --pilot 16
    venv/bin/python server/scripts/discourse_severance/factoidwiki_track/nuggetindex_track/run_nuggetindex_experiment.py
"""

import argparse
import json
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

from env_utils import (
    ELABORATION_SOURCE_LOG,
    GOVERN_SOURCE_LOG,
    LOGS_DIR,
    RESULTS_DIR,
    ensure_dirs,
    load_jsonl,
    load_server_env,
)

load_server_env()

from nuggetindex_extractor_adapter import DEFAULT_MODEL, extract_triples  # noqa: E402
from sentence_boundary_diagnostic import flag_boundary_spanning_severed_cases  # noqa: E402
from triple_severance_judge import llm_judge_triple_severance, render_triple  # noqa: E402

DEFAULT_MAX_WORKERS = 8
GOVERNING_RELATION_TYPES = ["Condition", "Concession"]

CONDITION_B_ABLATION_NOTE = (
    "NOT RUN: NuggetIndex's own extraction prompt (extractors/prompts/extraction.md, read in "
    "full) has no built-in notion of discourse-relation-aware extraction -- no parameter or "
    "prompt hook exists for 'preserve this Condition/Concession relation while extracting', "
    "unlike ../condition_b_atomizer.py's elicit-then-atomize design for the gpt-4o-mini "
    "atomizer. Writing a custom relation-aware prompt and swapping it in via LLMExtractor's "
    "prompt_path override was considered and rejected -- that would test our own prompt "
    "engineering, not NuggetIndex's own capability, misrepresenting what this integration is "
    "measuring. Only the standard-extraction condition is reported below."
)

CONTEXT_WINDOW_CAVEAT_NOTE = (
    "CONFIRMED FALSE by reading the real NuggetIndex source (extractors/llm.py, "
    "extractors/base.py, pipeline/constructor.py, extractors/prompts/extraction.md): "
    "NuggetIndex has NO built-in sentence-window context assembly. LLMExtractor.aextract "
    "accepts an optional `context` kwarg but nothing in NuggetIndex's own pipeline code "
    "populates it automatically, and this track's adapter (nuggetindex_extractor_adapter.py) "
    "calls aextract(text=paragraph) with context left at its default empty string -- so "
    "NuggetIndex sees exactly the same single-paragraph unit of text every other chunker in "
    "this comparison sees, no cross-chunker context-richness asymmetry. Sentence-boundary "
    "flagging is still computed and reported below per the task brief's instruction, as a "
    "property of the source data, independent of this (non-)confound finding."
)


def _pool_lookup(source_log):
    return {r["pool_index"]: r for r in load_jsonl(source_log)}


def select_pilot_sample(govern_records, elaboration_records, n_per_governing_type=6, n_elaboration=4):
    """Deterministic (pool_index order, no randomness) small pilot slice:
    up to `n_per_governing_type` of each Condition/Concession (first by
    pool_index) plus `n_elaboration` Elaboration records -- a stratified
    mix so the hand-inspection in this task's pilot step actually covers
    all three relation types, not just whichever type happens to sort
    first in the log.
    """
    govern_sorted = sorted(govern_records, key=lambda r: r["pool_index"])
    condition = [r for r in govern_sorted if r["relation_type"] == "Condition"][:n_per_governing_type]
    concession = [r for r in govern_sorted if r["relation_type"] == "Concession"][:n_per_governing_type]
    govern_pilot = sorted(condition + concession, key=lambda r: r["pool_index"])
    elaboration_pilot = sorted(elaboration_records, key=lambda r: r["pool_index"])[:n_elaboration]
    return govern_pilot, elaboration_pilot


def _relation_dict(rec):
    return {
        "relation_type": rec["relation_type"],
        "nucleus": rec["nucleus"],
        "satellite": rec["satellite"],
        "connective": rec["connective"],
    }


def _process_record(rec):
    """One governing OR Elaboration-control record: extract triples, then
    judge severance against them. Sequential within a record (judge needs
    the extraction result); records are processed in parallel across
    threads by `_parallel_map` below.
    """
    content = rec["content"]
    relation = _relation_dict(rec)

    t0 = time.time()
    extraction = extract_triples(content, model=DEFAULT_MODEL)
    extract_seconds = time.time() - t0

    triples = extraction["triples"]
    t0 = time.time()
    severance = llm_judge_triple_severance(content, relation, triples)
    judge_seconds = time.time() - t0

    return {
        **rec,
        "nuggetindex_triples": triples,
        "nuggetindex_triples_rendered": [render_triple(t) for t in triples],
        "n_nuggetindex_triples": len(triples),
        "nuggetindex_extraction_error": extraction["_error"],
        "severance_nuggetindex": severance,
        "_extract_seconds": extract_seconds,
        "_judge_seconds": judge_seconds,
    }


def _parallel_map(func, items, max_workers=DEFAULT_MAX_WORKERS, label=""):
    """Same ThreadPoolExecutor-with-as_completed pattern used throughout
    this project (../run_two_stage_pipeline.py's _parallel_map,
    ../run_experiment_1_2.py's import of it) -- duplicated locally per
    this track's self-contained-scripts convention.
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


# --- summaries --------------------------------------------------------------


def _rate(preds):
    vals = [p for p in preds if p is not None]
    severed = sum(1 for p in vals if p is False)
    return {"n_scored": len(vals), "n_severed": severed,
            "severed_rate": severed / len(vals) if vals else None}


def summarize(govern_results, elaboration_results):
    """Experiment-2-style analysis (governing pooled vs. Elaboration
    control), the only experiment shape available for NuggetIndex --
    see CONDITION_B_ABLATION_NOTE for why there is no Experiment-1-style
    A-vs-B ablation here.
    """
    by_relation_type = {}
    for rt in GOVERNING_RELATION_TYPES:
        subset = [r for r in govern_results if r["relation_type"] == rt]
        by_relation_type[rt] = _rate([r["severance_nuggetindex"]["preserved"] for r in subset])
    by_relation_type["Elaboration"] = _rate(
        [r["severance_nuggetindex"]["preserved"] for r in elaboration_results]
    )

    govern_preds = [r["severance_nuggetindex"]["preserved"] for r in govern_results]
    control_preds = [r["severance_nuggetindex"]["preserved"] for r in elaboration_results]

    def counts(preds):
        vals = [p for p in preds if p is not None]
        severed = sum(1 for p in vals if p is False)
        return severed, len(vals) - severed

    gov_severed, gov_preserved = counts(govern_preds)
    ctrl_severed, ctrl_preserved = counts(control_preds)

    result = {
        "per_relation_type": by_relation_type,
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
        from scipy.stats import chi2_contingency, fisher_exact
        table = [[gov_severed, gov_preserved], [ctrl_severed, ctrl_preserved]]
        odds_ratio, fisher_p = fisher_exact(table)
        result["fisher_exact_p_value"] = fisher_p
        result["fisher_odds_ratio"] = odds_ratio
        if all(sum(row) > 0 for row in table) and all(sum(col) > 0 for col in zip(*table)):
            chi2, chi2_p, dof, _ = chi2_contingency(table)
            result["chi2_p_value"] = chi2_p
        result["test_note"] = (
            "Fisher's exact test on the 2x2 severed/preserved table, Condition+Concession "
            "(pooled) vs Elaboration control, NuggetIndex triple output. Mirrors "
            "../run_experiment_1_2.py's summarize_experiment_2 design."
        )
    except ImportError:
        result["test_note"] = "scipy not available in this environment -- reporting raw counts/rates only."

    return result


def summarize_structural(govern_results):
    """Free (no new LLM calls) qualitative stats: triples/paragraph, and
    whether the elicited connective survives verbatim in >=1 triple's
    RENDERED pseudo-sentence (subject+predicate+object -- never the
    evidence_span, matching ../triple_severance_judge.py's exclusion of
    evidence_span from what counts as 'the atomized output'). Mirrors
    ../run_experiment_1_2.py's summarize_structural_comparison.
    """
    def connective_survives(connective, rendered_triples):
        conn = (connective or "").strip().lower()
        if not conn:
            return None
        return any(conn in rt.lower() for rt in rendered_triples)

    rows = []
    for r in govern_results:
        rows.append({
            "relation_type": r["relation_type"],
            "n_triples": r["n_nuggetindex_triples"],
            "conn_survives": connective_survives(r["connective"], r["nuggetindex_triples_rendered"]),
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
            "avg_triples_per_paragraph": avg([row["n_triples"] for row in subset]),
            "connective_survival": survival([row["conn_survives"] for row in subset]),
        }

    overall = block(rows)
    by_relation_type = {rt: block([row for row in rows if row["relation_type"] == rt])
                         for rt in GOVERNING_RELATION_TYPES}
    return {"overall": overall, "by_relation_type": by_relation_type}


def run(govern_sample, elaboration_sample, govern_log_path, elaboration_log_path, report_path, label):
    print(f"[{label}] Extracting NuggetIndex triples + judging severance for "
          f"{len(govern_sample)} governing paragraphs...")
    t0 = time.time()
    govern_results = _parallel_map(_process_record, govern_sample, label=f"{label}-govern")
    with open(govern_log_path, "w", encoding="utf-8") as fh:
        for rec in govern_results:
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")

    print(f"[{label}] Extracting NuggetIndex triples + judging severance for "
          f"{len(elaboration_sample)} Elaboration-control paragraphs...")
    elaboration_results = _parallel_map(_process_record, elaboration_sample, label=f"{label}-elab")
    with open(elaboration_log_path, "w", encoding="utf-8") as fh:
        for rec in elaboration_results:
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
    elapsed = time.time() - t0

    n_extraction_errors = sum(
        1 for r in (govern_results + elaboration_results) if r.get("nuggetindex_extraction_error")
    )
    n_judge_errors = sum(
        1 for r in (govern_results + elaboration_results)
        if r["severance_nuggetindex"]["preserved"] is None
    )
    n_calls = 2 * (len(govern_results) + len(elaboration_results))  # 1 extract + 1 judge, each record

    severed_govern = [
        {**r, "severed": True}
        for r in govern_results if r["severance_nuggetindex"]["preserved"] is False
    ]
    flagged, boundary_summary = flag_boundary_spanning_severed_cases(severed_govern, severed_key="severed")

    report = {
        "label": label,
        "model": DEFAULT_MODEL,
        "condition_b_style_ablation": CONDITION_B_ABLATION_NOTE,
        "context_window_caveat": CONTEXT_WINDOW_CAVEAT_NOTE,
        "n_governing": len(govern_results),
        "n_elaboration_control": len(elaboration_results),
        "n_real_llm_calls": n_calls,
        "n_extraction_errors": n_extraction_errors,
        "n_judge_errors": n_judge_errors,
        "wall_clock_seconds": elapsed,
        "severance_summary": summarize(govern_results, elaboration_results),
        "structural_summary": summarize_structural(govern_results),
        "sentence_boundary_diagnostic": boundary_summary,
        "sentence_boundary_flagged_cases": flagged,
        "govern_log": govern_log_path,
        "elaboration_log": elaboration_log_path,
    }
    with open(report_path, "w", encoding="utf-8") as fh:
        json.dump(report, fh, indent=2, ensure_ascii=False)

    print(f"\n[{label}] {n_calls} real LLM calls, {n_extraction_errors} extraction errors, "
          f"{n_judge_errors} judge errors, {elapsed:.1f}s wall-clock.")
    print(json.dumps(report["severance_summary"], indent=2))
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
        govern_log = os.path.join(LOGS_DIR, "nuggetindex_pilot_govern_log.jsonl")
        elaboration_log = os.path.join(LOGS_DIR, "nuggetindex_pilot_elaboration_log.jsonl")
        report_path = os.path.join(RESULTS_DIR, "nuggetindex_pilot_report.json")
        run(govern_sample, elaboration_sample, govern_log, elaboration_log, report_path, label="pilot")
    else:
        govern_log = os.path.join(LOGS_DIR, "nuggetindex_govern_log.jsonl")
        elaboration_log = os.path.join(LOGS_DIR, "nuggetindex_elaboration_log.jsonl")
        report_path = os.path.join(RESULTS_DIR, "nuggetindex_severance_report.json")
        run(govern_records, elaboration_records, govern_log, elaboration_log, report_path, label="full")


if __name__ == "__main__":
    main()
