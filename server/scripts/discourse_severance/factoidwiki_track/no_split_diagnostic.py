"""Task 3 bonus diagnostic (post-hoc, does not change any severance number
above it): "severed-with-no-split" check, mirroring
../audit_severance.py's A2 audit design as closely as possible for
paragraph-level input. Motivated by a concrete example surfaced while
reading through logs/task7_experiment_govern_log.jsonl for illustrative
quotes: pool_index 2965 (Survivin, Condition) -- Condition B's output
includes the ENTIRE original sentence back, verbatim, as one of its three
propositions (fully intact, connective included), yet the LLM-judge still
scored it severed=False (preserved=False). That is the exact category
error ../audit_severance.py's A2 section named and quantified for the CFR
track: an atomizer that did not actually split the governing clause away
from its connective cannot have "severed" anything by omission, so a
severed=True verdict there is a judge/prompt artifact, not evidence the
atomization step failed.

Normalization mirrors ../audit_severance.py's A2 description: lowercase,
all non-alphanumeric characters dropped, whitespace collapsed away
entirely (stricter than candidate_prefilter.normalize_text, which keeps
single spaces -- here we want ONLY letters/digits so wording is compared
independent of any punctuation/whitespace choices the atomizer made).
"No-split" = the propositions, joined, are identical or near-identical
(difflib SequenceMatcher ratio >= 0.95) to the normalized source paragraph.
"STRICT no-split" additionally requires exactly ONE proposition.

Does NOT re-run or change any LLM call -- reads the already-written
logs/task7_experiment_govern_log.jsonl and appends a new
"no_split_diagnostic" key to results/task7_experiment_1_2_report.json,
preserving everything else already in that file (same
preserve-on-rerun pattern run_two_stage_pipeline.py uses for its
"spot_check" key).

Usage:
    venv/bin/python server/scripts/discourse_severance/factoidwiki_track/no_split_diagnostic.py
"""

import difflib
import json
import os
import re
import unicodedata

from env_utils import LOGS_DIR, RESULTS_DIR

GOVERN_LOG = os.path.join(LOGS_DIR, "task7_experiment_govern_log.jsonl")
REPORT_JSON = os.path.join(RESULTS_DIR, "task7_experiment_1_2_report.json")
NO_SPLIT_RATIO_THRESHOLD = 0.95


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


def analyze(condition_label, propositions_key, severance_key, records):
    rows = []
    for r in records:
        chk = no_split_check(r["content"], r[propositions_key])
        rows.append({
            "pool_index": r["pool_index"],
            "relation_type": r["relation_type"],
            **chk,
            "severed": r[severance_key]["preserved"] is False,
        })

    n_no_split = sum(1 for row in rows if row["no_split"])
    n_strict = sum(1 for row in rows if row["strict_no_split"])
    strict_yet_severed = [row for row in rows if row["strict_no_split"] and row["severed"]]
    any_no_split_yet_severed = [row for row in rows if row["no_split"] and row["severed"]]

    return {
        "condition": condition_label,
        "n_total": len(rows),
        "n_no_split_ratio_ge_0_95": n_no_split,
        "n_strict_no_split_single_proposition": n_strict,
        "n_strict_no_split_yet_scored_severed": len(strict_yet_severed),
        "strict_no_split_yet_severed_pool_indices": sorted(row["pool_index"] for row in strict_yet_severed),
        "n_any_no_split_yet_scored_severed": len(any_no_split_yet_severed),
    }


def main():
    records = [json.loads(l) for l in open(GOVERN_LOG, encoding="utf-8")]

    result_a = analyze("Condition A (Propositionizer)", "condition_a_propositions", "severance_a", records)
    result_b = analyze("Condition B (elicit-then-atomize)", "condition_b_propositions", "severance_b", records)

    diagnostic = {
        "note": (
            "Mirrors ../audit_severance.py's A2 'severed-with-no-split' audit. A STRICT no-split "
            "case (single proposition, near-identical to source) scored severed=True is a judge/"
            "prompt category error, not an atomization failure -- nothing was actually split apart. "
            "Reported as a caveat on the headline severed rates above, not a replacement for them."
        ),
        "condition_a": result_a,
        "condition_b": result_b,
    }

    print(json.dumps(diagnostic, indent=2))

    with open(REPORT_JSON, encoding="utf-8") as fh:
        report = json.load(fh)
    report["no_split_diagnostic"] = diagnostic
    with open(REPORT_JSON, "w", encoding="utf-8") as fh:
        json.dump(report, fh, indent=2, ensure_ascii=False)
    print(f"\nAppended 'no_split_diagnostic' to {REPORT_JSON}")


if __name__ == "__main__":
    main()
