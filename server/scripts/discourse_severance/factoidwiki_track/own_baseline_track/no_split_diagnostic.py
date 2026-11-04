"""Post-hoc "severed-with-no-split" (A2) diagnostic, ported to THIS
PROJECT'S OWN minimal prompted baseline (own_baseline_track).

Direct port of ../atomicrag_track/no_split_diagnostic.py's design (itself
a port of ../no_split_diagnostic.py's design, itself a port of
../../audit_severance.py's A2 audit) to this baseline's own 272
governing-relation records in logs/own_baseline_govern_log.jsonl. This
baseline's atomized output ("claims" -- see own_baseline_adapter.py's /
run_own_baseline_experiment.py's VOCABULARY NOTE for why it is called
"claims" here, not "propositions") is natural-language text, exactly like
Propositionizer's and AtomicRAG's, so NO adaptation of the check's core
LOGIC is needed here, unlike the NuggetIndex track (structured triples).

TWO CONDITIONS, NOT ONE -- match the Propositionizer-track scoping, not
AtomicRAG's: unlike AtomicRAG (no Condition-B analog), this baseline has a
REAL Condition B (own_baseline_adapter.run_condition_b, a relation-aware
atomizer -- see that module's docstring), and both conditions were scored
by their own severance judge call (severance_a against condition_a_claims,
severance_b against condition_b_claims -- see run_own_baseline_experiment.
py's `_process_govern_record`). So, per the task brief's instruction to
"check how the Propositionizer/AtomicRAG version scoped this and match
it," this script reports TWO condition blocks (mirroring
../no_split_diagnostic.py's condition_a/condition_b split), not
AtomicRAG's single-condition block.

FIELD-NAME LANDMINE, CHECKED AND AVOIDED: logs/own_baseline_govern_log.jsonl
carries `condition_a_propositions` / `condition_b_propositions` /
`verification_prompt_version` / `condition_b_error` keys that are STALE,
COPIED-THROUGH fields from the ORIGINAL source log this track reads from
(../logs/task7_experiment_govern_log.jsonl) -- i.e. Chen et al.'s real
Propositionizer output and the gpt-4o-mini elicit-then-atomize Condition
B from the Propositionizer track, NOT this baseline's own output.
Confirmed by diffing: pool_index 1809's `condition_a_propositions` in
this track's own govern log is byte-for-byte identical to the SOURCE
log's `condition_a_propositions` (11 Propositionizer propositions),
while this baseline's actual own Condition-A output for the same record
lives in a DIFFERENT key, `condition_a_claims` (10 claims, different
wording) -- see run_own_baseline_experiment.py's `_process_govern_record`:
`{**rec, "condition_a_claims": claims_a, ..., "severance_a": severance_a,
...}` spreads the untouched source record first, so `condition_a_
propositions` survives unshadowed while `severance_a`/`severance_b` DO
get overwritten with this baseline's own judge verdicts -- verdicts
computed against `claims_a`/`claims_b` (see that function: `severance_a =
llm_judge_paragraph_severance(content, relation, claims_a)`), never
against `condition_a_propositions`/`condition_b_propositions`. This
script therefore uses `condition_a_claims`/`condition_b_claims`
throughout -- the ONLY fields `severance_a`/`severance_b` were actually
judged against.

Normalization is identical to ../no_split_diagnostic.py's `_normalize`:
NFKC-normalize, lowercase, drop every non-alphanumeric character,
collapse whitespace away entirely. "No-split" = the claims, joined, are
identical or near-identical (difflib SequenceMatcher ratio >= 0.95) to
the normalized source paragraph. "STRICT no-split" additionally requires
exactly ONE claim.

Does NOT re-run or change any LLM call -- reads the already-written
logs/own_baseline_govern_log.jsonl and writes a NEW, additive results
file (results/own_baseline_no_split_diagnostic.json); it never touches
results/own_baseline_experiment_1_2_report.json.

Usage:
    venv/bin/python server/scripts/discourse_severance/factoidwiki_track/own_baseline_track/no_split_diagnostic.py
"""

import difflib
import json
import os
import re
import unicodedata

TRACK_DIR = os.path.dirname(os.path.abspath(__file__))
LOGS_DIR = os.path.join(TRACK_DIR, "logs")
RESULTS_DIR = os.path.join(TRACK_DIR, "results")

GOVERN_LOG = os.path.join(LOGS_DIR, "own_baseline_govern_log.jsonl")
OUTPUT_PATH = os.path.join(RESULTS_DIR, "own_baseline_no_split_diagnostic.json")
NO_SPLIT_RATIO_THRESHOLD = 0.95

EXPECTED_N = 272
EXPECTED_BY_RELATION = {"Condition": 75, "Concession": 197}

AUDIT_DATE = "2026-08-15"


def _normalize(s):
    s = unicodedata.normalize("NFKC", s or "")
    s = s.lower()
    s = re.sub(r"[^a-z0-9]+", "", s)
    return s


def no_split_check(paragraph, claims):
    joined = " ".join(claims)
    norm_source = _normalize(paragraph)
    norm_joined = _normalize(joined)
    ratio = difflib.SequenceMatcher(None, norm_source, norm_joined).ratio()
    return {
        "ratio": ratio,
        "no_split": ratio >= NO_SPLIT_RATIO_THRESHOLD,
        "strict_no_split": ratio >= NO_SPLIT_RATIO_THRESHOLD and len(claims) == 1,
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


def analyze(condition_label, claims_key, severance_key, records):
    rows = []
    for r in records:
        chk = no_split_check(r["content"], r[claims_key])
        rows.append({
            "pool_index": r["pool_index"],
            "relation_type": r["relation_type"],
            **chk,
            "n_claims": len(r[claims_key]),
            "severed": r[severance_key]["preserved"] is False,
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
            "n_strict_no_split_single_claim": sum(1 for row in subset if row["strict_no_split"]),
        }

    return {
        "condition": condition_label,
        "n_total": len(rows),
        "n_no_split_ratio_ge_0_95": n_no_split,
        "n_strict_no_split_single_claim": n_strict,
        "n_strict_no_split_yet_scored_severed": len(strict_yet_severed),
        "strict_no_split_yet_severed_pool_indices": sorted(row["pool_index"] for row in strict_yet_severed),
        "n_any_no_split_yet_scored_severed": len(any_no_split_yet_severed),
        "any_no_split_yet_severed_pool_indices": sorted(row["pool_index"] for row in any_no_split_yet_severed),
        "by_relation_type": by_relation,
        "rows_no_split_only": [row for row in rows if row["no_split"]],
    }


def main():
    records = load_records()

    result_a = analyze("Condition A (own_baseline_adapter.run_condition_a)",
                        "condition_a_claims", "severance_a", records)
    result_b = analyze("Condition B (own_baseline_adapter.run_condition_b, relation-aware)",
                        "condition_b_claims", "severance_b", records)

    diagnostic = {
        "audit_date": AUDIT_DATE,
        "source_log": os.path.basename(GOVERN_LOG),
        "note": (
            "Direct port of ../atomicrag_track/no_split_diagnostic.py's design (itself "
            "ported from ../no_split_diagnostic.py / ../../audit_severance.py's A2 "
            "'severed-with-no-split' audit) to this project's own minimal prompted "
            "baseline. No adaptation of the check's LOGIC was needed -- this baseline's "
            "atomic unit ('claim') is still natural-language text. Reports TWO condition "
            "blocks (Condition A and Condition B), matching ../no_split_diagnostic.py's "
            "scoping rather than AtomicRAG's single-condition scoping, because this "
            "baseline (unlike AtomicRAG) has a real Condition-B analog that was actually "
            "run and independently judged (severance_b against condition_b_claims). A "
            "STRICT no-split case (single claim, near-identical to source) scored "
            "severed=True is a judge/prompt category error, not an atomization failure -- "
            "nothing was actually split apart. Reported as a caveat on the headline "
            "severed rates in results/own_baseline_experiment_1_2_report.json, not a "
            "replacement for them."
        ),
        "field_name_landmine_note": (
            "logs/own_baseline_govern_log.jsonl also carries condition_a_propositions/ "
            "condition_b_propositions/verification_prompt_version/condition_b_error keys "
            "that are STALE fields copied through from ../logs/task7_experiment_govern_log"
            ".jsonl (Propositionizer's real output and the Propositionizer-track's own "
            "gpt-4o-mini elicit-then-atomize Condition B) -- NOT this baseline's own "
            "output. This script deliberately uses condition_a_claims/condition_b_claims "
            "(the fields severance_a/severance_b were actually judged against per "
            "run_own_baseline_experiment.py's _process_govern_record), never "
            "condition_a_propositions/condition_b_propositions. See this module's "
            "docstring for the full diff-based confirmation."
        ),
        "normalization": (
            "NFKC-normalize, lowercase, drop every non-alphanumeric character, collapse "
            "whitespace away entirely (identical to ../no_split_diagnostic.py's "
            "_normalize). Near-identical = difflib.SequenceMatcher ratio >= "
            f"{NO_SPLIT_RATIO_THRESHOLD} on the normalized strings."
        ),
        "condition_a": result_a,
        "condition_b": result_b,
    }

    print(json.dumps({k: v for k, v in diagnostic.items()
                       if k not in ("condition_a", "condition_b")}, indent=2))
    for key in ("condition_a", "condition_b"):
        print(json.dumps({k: v for k, v in diagnostic[key].items() if k != "rows_no_split_only"},
                          indent=2))

    os.makedirs(RESULTS_DIR, exist_ok=True)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as fh:
        json.dump(diagnostic, fh, indent=2, ensure_ascii=False)
    print(f"\nWrote {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
