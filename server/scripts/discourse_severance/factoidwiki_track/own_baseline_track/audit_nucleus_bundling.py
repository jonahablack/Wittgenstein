"""Post-hoc A1 (nucleus-bundling) audit, ported to THIS PROJECT'S OWN
minimal prompted baseline (own_baseline_track).

Direct port of ../atomicrag_track/audit_nucleus_bundling.py's design
(itself ported from ../audit_nucleus_bundling.py / ../../audit_severance.py's
A1 audit) to this baseline's own 272 governing-relation records in
logs/own_baseline_govern_log.jsonl. This baseline's atomic unit ("claim")
is still natural-language text, so this is the fairly direct port the
task brief anticipated: the SAME sub-clause-scoped judge
(`severance_detection.llm_judge_severance_subclause`) ../audit_nucleus_
bundling.py and ../atomicrag_track/audit_nucleus_bundling.py already use
is reused unmodified here too.

TWO CONDITIONS, NOT ONE -- match the Propositionizer-track scoping, not
AtomicRAG's: unlike AtomicRAG (no Condition-B analog), this baseline has
a REAL Condition B (own_baseline_adapter.run_condition_b, a relation-aware
atomizer), independently judged (severance_b against condition_b_claims,
see run_own_baseline_experiment.py's `_process_govern_record`). So, per
the task brief ("2 real LLM calls per bundled case, same as before"),
step 2 (connective attachment) and step 3 (sub-clause judge) each run
TWICE per bundled record here (once per condition), exactly like
../audit_nucleus_bundling.py's Condition A/B design -- not once like
AtomicRAG's single-condition version.

FIELD-NAME LANDMINE, CHECKED AND AVOIDED (see no_split_diagnostic.py's
module docstring for the full diff-based confirmation): logs/own_baseline
_govern_log.jsonl carries `condition_a_propositions`/`condition_b_
propositions` keys that are STALE fields copied through from ../logs/
task7_experiment_govern_log.jsonl (Propositionizer's real output and the
Propositionizer-track's own gpt-4o-mini elicit-then-atomize Condition B)
-- NOT this baseline's own output. This script uses `condition_a_claims`/
`condition_b_claims` throughout (the fields `severance_a`/`severance_b`
were actually judged against), never `condition_a_propositions`/
`condition_b_propositions`.

WHY THE BUNDLED SET IS EXPECTED TO BE IDENTICAL TO EVERY OTHER CHUNKER'S:
bundling detection (`detect_bundling_sites`) and governed-sub-clause
assignment (`assign_governed_subclause`) operate ONLY on the
`nucleus`/`content`/`satellite` fields, which are copied verbatim from
../logs/task7_experiment_govern_log.jsonl into every chunker's own govern
log (see run_own_baseline_experiment.py: `{**rec, "condition_a_claims":
claims_a, ...}` -- `rec` is the untouched source record, so `nucleus`/
`content`/`satellite` are the same untouched source fields too). Since
those fields never change across chunkers, steps 1 (detection) and the
governed-sub-clause half of step 2 are guaranteed, not coincidentally, to
reproduce the SAME 13/272 bundled pool_indices (12 clear, 1 borderline)
already reported for Propositionizer, AtomicRAG, and NuggetIndex -- this
script re-runs the detection anyway (not assumed) so the result is
verified against this baseline's own log, and a mismatch is reported
rather than silently assumed.

Does NOT re-run atomization or the primary severance judge -- it re-reads
the already-saved govern log. The only new LLM calls are the sub-clause-
scoped judge calls on the bundled-nucleus subset (2 per bundled record:
one against the saved `condition_a_claims`, one against
`condition_b_claims`).

Writes an ADDITIVE new file (results/own_baseline_nucleus_bundling_audit.json);
never touches results/own_baseline_experiment_1_2_report.json.

Usage
-----
    venv/bin/python server/scripts/discourse_severance/factoidwiki_track/own_baseline_track/audit_nucleus_bundling.py             # full audit (2*n_bundled LLM calls)
    venv/bin/python server/scripts/discourse_severance/factoidwiki_track/own_baseline_track/audit_nucleus_bundling.py --skip-llm  # structural analysis only, no API calls
"""

import argparse
import json
import os
import sys

TRACK_DIR = os.path.dirname(os.path.abspath(__file__))
if TRACK_DIR not in sys.path:
    sys.path.insert(0, TRACK_DIR)

import env_utils  # noqa: E402  (this track's own env_utils.py)
from env_utils import LOGS_DIR, RESULTS_DIR, SERVER_DIR  # noqa: E402

if SERVER_DIR not in sys.path:
    sys.path.insert(0, SERVER_DIR)

env_utils.load_server_env()

# Imported (not re-implemented), same deliberate exception
# ../audit_nucleus_bundling.py / ../atomicrag_track/audit_nucleus_bundling.py
# already document and take: the A1 bundling heuristic is pure
# English-clause-structure string/regex analysis with no CFR-specific
# logic baked into its control flow, and the sub-clause judge is a prompt
# already iterated on and validated (CFR track, then reused unmodified
# for the Propositionizer and AtomicRAG tracks). Copying either a fourth
# time risks drift.
from scripts.discourse_severance import audit_severance  # noqa: E402
from scripts.discourse_severance import severance_detection  # noqa: E402

GOVERN_LOG = os.path.join(LOGS_DIR, "own_baseline_govern_log.jsonl")
OUTPUT_PATH = os.path.join(RESULTS_DIR, "own_baseline_nucleus_bundling_audit.json")

EXPECTED_N = 272
EXPECTED_BY_RELATION = {"Condition": 75, "Concession": 197}

AUDIT_DATE = "2026-08-15"

EXPECTED_BUNDLED_POOL_INDICES = {1840, 1936, 3263, 3360, 3397, 3444, 4208, 4380, 4698,
                                  4707, 4859, 4920, 5132}


def load_records():
    with open(GOVERN_LOG, encoding="utf-8") as fh:
        recs = [json.loads(line) for line in fh]
    if len(recs) != EXPECTED_N:
        raise RuntimeError(
            f"Expected {EXPECTED_N} governing-relation records in "
            f"{GOVERN_LOG}, found {len(recs)} -- refusing to run the "
            "audit against an unexpected sample."
        )
    counts = {}
    for r in recs:
        counts[r["relation_type"]] = counts.get(r["relation_type"], 0) + 1
    if counts != EXPECTED_BY_RELATION:
        raise RuntimeError(
            f"Expected relation-type counts {EXPECTED_BY_RELATION}, found "
            f"{counts} -- refusing to run the audit against an unexpected sample."
        )
    return recs


def adjusted_counts(records, cond, bundled_by_key, subset_pred):
    """Severed count over `records` with bundled-subset (filtered by
    subset_pred) verdicts swapped for the sub-clause verdicts; everything
    else keeps its original saved verdict. Mirrors ../audit_nucleus_
    bundling.py's `adjusted_counts` closure."""
    severed = 0
    for rec in records:
        entry = bundled_by_key.get(rec["pool_index"])
        if entry is not None and subset_pred(entry):
            preserved = entry[f"subclause_judge_{cond}"]["preserved"]
        else:
            preserved = rec[f"severance_{cond}"]["preserved"]
        if preserved is False:
            severed += 1
    return severed


def figure_block(records, cond, bundled_by_key, subset_pred):
    n = len(records)
    orig = sum(1 for r in records if r[f"severance_{cond}"]["preserved"] is False)
    adj = adjusted_counts(records, cond, bundled_by_key, subset_pred)
    return {
        "n": n,
        "original_severed": orig,
        "original_severed_rate": f"{orig}/{n} ({100 * orig / n:.1f}%)",
        "adjusted_severed": adj,
        "adjusted_severed_rate": f"{adj}/{n} ({100 * adj / n:.1f}%)",
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--skip-llm", action="store_true",
                        help="structural analysis only; skip the sub-clause "
                             "judge LLM calls (output will mark them as not run)")
    args = parser.parse_args(argv)

    recs = load_records()

    # ---------------- step 1: bundled-nucleus detection --------------------
    print("=== Step 1: bundled-nucleus detection (structural heuristic, "
          "imported unmodified from ../../audit_severance.py) ===")
    entries = []
    for rec in recs:
        sites = audit_severance.detect_bundling_sites(rec["nucleus"])
        entry = {
            "pool_index": rec["pool_index"],
            "relation_type": rec["relation_type"],
            "title": rec["title"],
            "bundled": bool(sites),
            "sites": sites,
        }
        if sites:
            site = audit_severance.choose_bundling_site(sites)
            entry["chosen_site"] = site
            entry["clarity"] = ("clear" if any(s["clarity"] == "clear" for s in sites)
                                else "borderline")
            governed = audit_severance.assign_governed_subclause(
                rec["content"], rec["satellite"],
                site["subclause_1"], site["subclause_2"])
            entry.update(governed)
            print(f"  BUNDLED [{entry['clarity']:10s}] pool_index={rec['pool_index']} "
                  f"({rec['relation_type']}) rule={site['rule']}")
            print(f"    sub-clause 1: {site['subclause_1'][:90]}")
            print(f"    sub-clause 2: {site['subclause_2'][:90]}")
            print(f"    satellite governs sub-clause {governed['governed_subclause_index']} "
                  f"({governed['assignment_note']})")
        entries.append(entry)

    bundled = [e for e in entries if e["bundled"]]
    n_borderline = sum(1 for e in bundled if e["clarity"] == "borderline")
    print(f"\nBundled nuclei: {len(bundled)}/{EXPECTED_N} "
          f"({len(bundled) - n_borderline} clear, {n_borderline} borderline)")
    found_bundled = {e["pool_index"] for e in bundled}
    same_as_other_chunkers = found_bundled == EXPECTED_BUNDLED_POOL_INDICES
    print(f"Same 13 pool_indices as ../audit_nucleus_bundling.py's / "
          f"../atomicrag_track/audit_nucleus_bundling.py's / ../nuggetindex_track/"
          f"audit_nucleus_bundling.py's runs: {same_as_other_chunkers} (expected, "
          "since detection depends only on the shared nucleus/content/satellite "
          "fields -- see module docstring)")

    # ---------------- step 2: connective attachment (read-only) ------------
    print("\n=== Step 2: connective attachment in saved atomized outputs "
          "(read-only, imported unmodified from ../../audit_severance.py) ===")
    by_pool_index = {r["pool_index"]: r for r in recs}
    for entry in bundled:
        rec = by_pool_index[entry["pool_index"]]
        site = entry["chosen_site"]
        for cond, claims_key in [("a", "condition_a_claims"), ("b", "condition_b_claims")]:
            att = audit_severance.connective_attachment(
                rec[claims_key], rec["connective"],
                site["subclause_1"], site["subclause_2"],
                entry["governed_subclause_index"])
            entry[f"attachment_{cond}"] = att
            print(f"  pool_index={entry['pool_index']} cond {cond.upper()}: "
                  f"present={att['connective_present']} attachment={att['attachment']} "
                  f"same_as_governed={att['same_subclause_as_governed']}")

    # ---------------- step 3: sub-clause-scoped judge -----------------------
    if args.skip_llm:
        print("\n=== Step 3: SKIPPED (--skip-llm) ===")
    else:
        print(f"\n=== Step 3: sub-clause judge on {len(bundled)} bundled "
              f"records x 2 conditions ({2 * len(bundled)} LLM calls) ===")
        for entry in bundled:
            rec = by_pool_index[entry["pool_index"]]
            relation = {k: rec[k] for k in ("relation_type", "nucleus", "satellite", "connective")}
            for cond, claims_key in [("a", "condition_a_claims"), ("b", "condition_b_claims")]:
                verdict = severance_detection.llm_judge_severance_subclause(
                    rec["content"], relation, rec[claims_key], entry["governed_subclause"])
                if verdict["preserved"] is None:
                    raise RuntimeError(
                        f"Sub-clause judge call failed for pool_index={entry['pool_index']} "
                        f"condition {cond.upper()}: {verdict['reasoning']} -- refusing to "
                        "compute adjusted figures from missing data.")
                entry[f"subclause_judge_{cond}"] = verdict
                orig = rec[f"severance_{cond}"]["preserved"]
                entry[f"verdict_change_{cond}"] = {
                    "original_full_nucleus_preserved": orig,
                    "subclause_preserved": verdict["preserved"],
                    "changed": orig != verdict["preserved"],
                }
                print(f"  pool_index={entry['pool_index']} cond {cond.upper()}: "
                      f"full-nucleus preserved={orig} -> sub-clause preserved="
                      f"{verdict['preserved']}"
                      f"{'  [CHANGED]' if orig != verdict['preserved'] else ''}")

    # ---------------- step 4: adjusted secondary figures --------------------
    summary = {
        "n_total": EXPECTED_N,
        "n_bundled": len(bundled),
        "n_bundled_clear": len(bundled) - n_borderline,
        "n_bundled_borderline": n_borderline,
        "same_bundled_set_as_other_chunkers": same_as_other_chunkers,
        "bundled_pool_indices": [e["pool_index"] for e in bundled],
        "bundled_clear_pool_indices": [e["pool_index"] for e in bundled if e["clarity"] == "clear"],
        "bundled_borderline_pool_indices": [e["pool_index"] for e in bundled if e["clarity"] == "borderline"],
        "non_bundled_pool_indices": [e["pool_index"] for e in entries if not e["bundled"]],
    }

    if not args.skip_llm:
        bundled_by_key = {e["pool_index"]: e for e in bundled}
        condition_recs = [r for r in recs if r["relation_type"] == "Condition"]
        concession_recs = [r for r in recs if r["relation_type"] == "Concession"]

        adjusted = {"note": (
            "Sub-clause-scoped ALTERNATIVE reading: bundled-subset records use the "
            "sub-clause judge verdict (severance_detection.llm_judge_severance_subclause "
            "against condition_a_claims/condition_b_claims), all other records keep their "
            "original saved judge_prompt_full_nucleus verdict (severance_a/severance_b."
            "preserved from the govern log). NOT a replacement of the headline "
            "own_baseline_experiment_1_2_report.json figures.")}
        for cond in ("a", "b"):
            adjusted[f"condition_{cond}_overall"] = figure_block(
                recs, cond, bundled_by_key, lambda e: True)
            adjusted[f"condition_{cond}_overall_clear_bundles_only"] = figure_block(
                recs, cond, bundled_by_key, lambda e: e["clarity"] == "clear")
            adjusted[f"condition_{cond}_by_relation_type"] = {
                "Condition": figure_block(condition_recs, cond, bundled_by_key, lambda e: True),
                "Concession": figure_block(concession_recs, cond, bundled_by_key, lambda e: True),
            }
        summary["adjusted_secondary_figures"] = adjusted

        print("\n=== Adjusted secondary figures (sub-clause-scoped alternative reading) ===")
        for cond in ("a", "b"):
            block = adjusted[f"condition_{cond}_overall"]
            print(f"  Condition {cond.upper()} overall: original {block['original_severed_rate']} "
                  f"-> adjusted {block['adjusted_severed_rate']}")

        # ---------------- step 5: exclusion list (parity with other tracks) ---
        exclusions = []
        for entry in bundled:
            rec = by_pool_index[entry["pool_index"]]
            if (rec["severance_a"]["preserved"] is False
                    and entry["subclause_judge_a"]["preserved"] is True):
                exclusions.append({
                    "pool_index": entry["pool_index"],
                    "relation_type": entry["relation_type"],
                    "clarity": entry["clarity"],
                    "title": rec["title"],
                })
        summary["future_eval_exclusion_list"] = {
            "note": ("Records scored severed=True under Condition A by the ORIGINAL "
                     "full-nucleus judge that FLIP to preserved under the sub-clause "
                     "judge. These define exclusions from a future experiment's "
                     "evaluation set."),
            "pool_indices": [x["pool_index"] for x in exclusions],
            "records": exclusions,
        }
        print(f"  Exclusion list (Condition A severed -> sub-clause preserved): "
              f"{summary['future_eval_exclusion_list']['pool_indices']}")

    # ---------------- write output -------------------------------------------
    output = {
        "audit_date": AUDIT_DATE,
        "source_log": os.path.basename(GOVERN_LOG),
        "note": ("Post-hoc audit of SAVED results (A1 nucleus-bundling audit, ported "
                 "from ../../audit_severance.py via ../audit_nucleus_bundling.py's and "
                 "../atomicrag_track/audit_nucleus_bundling.py's already-validated "
                 "ports). Does not touch results/own_baseline_experiment_1_2_report.json; "
                 "the original headline numbers there are untouched. Figures here are a "
                 "sub-clause-scoped alternative reading reported alongside them, not a "
                 "replacement. A2 (no-split) is out of scope for this script -- see "
                 "no_split_diagnostic.py, already done."),
        "adaptation_note": (
            "Fairly direct port, as expected: this baseline's atomic unit ('claim') is "
            "still natural-language text, so the SAME bundling heuristic "
            "(detect_bundling_sites / choose_bundling_site / assign_governed_subclause / "
            "connective_attachment, imported unmodified from ../../audit_severance.py) "
            "and the SAME sub-clause-scoped judge "
            "(severance_detection.llm_judge_severance_subclause) used for the "
            "Propositionizer and AtomicRAG tracks were reused without modification -- "
            "only the field names changed (condition_a_claims/condition_b_claims/"
            "severance_a/severance_b in place of condition_a_propositions+condition_b_"
            "propositions/severance_a+severance_b -- see module docstring's "
            "FIELD-NAME LANDMINE note for why condition_a_propositions/condition_b_"
            "propositions were deliberately NOT used), and BOTH conditions are scored "
            "per bundled record (this baseline, unlike AtomicRAG, has a real Condition-B "
            "analog). Bundling DETECTION reproduces the identical 13/272 (12 clear, 1 "
            "borderline) pool_indices already found for every other chunker in this "
            "comparison, because detection depends only on the nucleus/content/satellite "
            "fields shared verbatim across every chunker's govern log -- see module "
            "docstring."
        ),
        "summary": summary,
        "records": [e for e in entries if e["bundled"]],
        "llm_calls_made": 0 if args.skip_llm else 2 * len(bundled),
    }
    os.makedirs(RESULTS_DIR, exist_ok=True)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as fh:
        json.dump(output, fh, indent=2, ensure_ascii=False)
    print(f"\nWrote {OUTPUT_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
