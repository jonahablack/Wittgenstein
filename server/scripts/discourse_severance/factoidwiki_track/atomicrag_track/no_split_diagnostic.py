"""Post-hoc "severed-with-no-split" (A2) diagnostic, ported to AtomicRAG.

Direct port of ../no_split_diagnostic.py's design (itself a port of
../../audit_severance.py's A2 audit) to AtomicRAG's own 272
governing-relation records in logs/atomicrag_govern_log.jsonl. AtomicRAG's
atomic unit is still natural-language text (a "knowledge fragment" --
see ../atomicrag_openie_adapter.py's docstring), so NO adaptation of the
check's core logic is needed here, unlike the NuggetIndex track (whose
atomic unit is a structured subject-predicate-object triple -- see
../nuggetindex_track/no_split_diagnostic.py for how that check had to be
redesigned for triples, and why). This script only adapts FIELD NAMES:
AtomicRAG has ONE atomization condition, not Condition A/B like the
Propositionizer track (see ../atomicrag_openie_adapter.py /
run_atomicrag_experiment.py's CONDITION_B_NOT_APPLICABLE_NOTE for why),
so this script reports a single condition block instead of two.

Motivated by the same category-error concern ../no_split_diagnostic.py's
docstring names: an atomizer that returns its input back (mostly)
unsplit cannot have "severed" a relation by omission -- a severed=True
verdict there is a judge/prompt artifact, not evidence the atomization
step failed to preserve the relation.

Normalization is identical to ../no_split_diagnostic.py's `_normalize`:
NFKC-normalize, lowercase, drop every non-alphanumeric character,
collapse whitespace away entirely. "No-split" = the propositions,
joined, are identical or near-identical (difflib SequenceMatcher ratio
>= 0.95) to the normalized source paragraph. "STRICT no-split"
additionally requires exactly ONE proposition.

Does NOT re-run or change any LLM call -- reads the already-written
logs/atomicrag_govern_log.jsonl and writes a NEW, additive results file
(results/atomicrag_no_split_diagnostic.json); it never touches
results/atomicrag_experiment_1_2_report.json.

Usage:
    venv/bin/python server/scripts/discourse_severance/factoidwiki_track/atomicrag_track/no_split_diagnostic.py
"""

import difflib
import json
import os
import re
import unicodedata

TRACK_DIR = os.path.dirname(os.path.abspath(__file__))
LOGS_DIR = os.path.join(TRACK_DIR, "logs")
RESULTS_DIR = os.path.join(TRACK_DIR, "results")

GOVERN_LOG = os.path.join(LOGS_DIR, "atomicrag_govern_log.jsonl")
OUTPUT_PATH = os.path.join(RESULTS_DIR, "atomicrag_no_split_diagnostic.json")
NO_SPLIT_RATIO_THRESHOLD = 0.95

EXPECTED_N = 272
EXPECTED_BY_RELATION = {"Condition": 75, "Concession": 197}


def _normalize(s):
    s = unicodedata.normalize("NFKC", s or "")
    s = s.lower()
    s = re.sub(r"[^a-z0-9]+", "", s)
    return s


def no_split_check(paragraph, propositions):
    joined = " ".join(propositions)
    norm_source = _normalize(paragraph)
    norm_joined = _normalize(joined)
    ratio = difflib.SequenceMatcher(None, norm_source, norm_joined).ratio()
    return {
        "ratio": ratio,
        "no_split": ratio >= NO_SPLIT_RATIO_THRESHOLD,
        "strict_no_split": ratio >= NO_SPLIT_RATIO_THRESHOLD and len(propositions) == 1,
    }


def load_records():
    with open(GOVERN_LOG, encoding="utf-8") as fh:
        recs = [json.loads(line) for line in fh]
    if len(recs) != EXPECTED_N:
        raise RuntimeError(
            f"Expected {EXPECTED_N} governing-relation records in {GOVERN_LOG}, "
            f"found {len(recs)} -- refusing to run the diagnostic against an "
            "unexpected sample."
        )
    counts = {}
    for r in recs:
        counts[r["relation_type"]] = counts.get(r["relation_type"], 0) + 1
    if counts != EXPECTED_BY_RELATION:
        raise RuntimeError(
            f"Expected relation-type counts {EXPECTED_BY_RELATION}, found "
            f"{counts} -- refusing to run the diagnostic against an unexpected sample."
        )
    return recs


def analyze(records):
    rows = []
    for r in records:
        chk = no_split_check(r["content"], r["atomicrag_propositions"])
        rows.append({
            "pool_index": r["pool_index"],
            "relation_type": r["relation_type"],
            **chk,
            "n_propositions": r["n_atomicrag_propositions"],
            "severed": r["severance_atomicrag"]["preserved"] is False,
        })

    n_no_split = sum(1 for row in rows if row["no_split"])
    n_strict = sum(1 for row in rows if row["strict_no_split"])
    strict_yet_severed = [row for row in rows if row["strict_no_split"] and row["severed"]]
    any_no_split_yet_severed = [row for row in rows if row["no_split"] and row["severed"]]

    by_relation = {}
    for rt in EXPECTED_BY_RELATION:
        subset = [row for row in rows if row["relation_type"] == rt]
        by_relation[rt] = {
            "n_total": len(subset),
            "n_no_split_ratio_ge_0_95": sum(1 for row in subset if row["no_split"]),
            "n_strict_no_split_single_proposition": sum(1 for row in subset if row["strict_no_split"]),
        }

    return {
        "condition": "AtomicRAG (single condition -- no Condition-B analog, see module docstring)",
        "n_total": len(rows),
        "n_no_split_ratio_ge_0_95": n_no_split,
        "n_strict_no_split_single_proposition": n_strict,
        "n_strict_no_split_yet_scored_severed": len(strict_yet_severed),
        "strict_no_split_yet_severed_pool_indices": sorted(row["pool_index"] for row in strict_yet_severed),
        "n_any_no_split_yet_scored_severed": len(any_no_split_yet_severed),
        "any_no_split_yet_severed_pool_indices": sorted(row["pool_index"] for row in any_no_split_yet_severed),
        "by_relation_type": by_relation,
        "rows_no_split_only": [row for row in rows if row["no_split"]],
    }


def main():
    records = load_records()
    result = analyze(records)

    diagnostic = {
        "audit_date": "2026-08-14",
        "source_log": os.path.basename(GOVERN_LOG),
        "note": (
            "Direct port of ../no_split_diagnostic.py's design (itself ported from "
            "../../audit_severance.py's A2 'severed-with-no-split' audit) to AtomicRAG's "
            "own single-condition output. No adaptation of the check's LOGIC was needed -- "
            "AtomicRAG's atomic unit ('knowledge fragment') is still natural-language text, "
            "unlike NuggetIndex's structured triples (see "
            "../nuggetindex_track/no_split_diagnostic.py for that adaptation). A STRICT "
            "no-split case (single proposition, near-identical to source) scored "
            "severed=True is a judge/prompt category error, not an atomization failure -- "
            "nothing was actually split apart. Reported as a caveat on the headline severed "
            "rates in results/atomicrag_experiment_1_2_report.json, not a replacement for them."
        ),
        "normalization": (
            "NFKC-normalize, lowercase, drop every non-alphanumeric character, collapse "
            "whitespace away entirely (identical to ../no_split_diagnostic.py's "
            "_normalize). Near-identical = difflib.SequenceMatcher ratio >= "
            f"{NO_SPLIT_RATIO_THRESHOLD} on the normalized strings."
        ),
        "atomicrag": result,
    }

    print(json.dumps({k: v for k, v in diagnostic.items() if k != "atomicrag"}, indent=2))
    print(json.dumps({k: v for k, v in result.items() if k != "rows_no_split_only"}, indent=2))

    os.makedirs(RESULTS_DIR, exist_ok=True)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as fh:
        json.dump(diagnostic, fh, indent=2, ensure_ascii=False)
    print(f"\nWrote {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
