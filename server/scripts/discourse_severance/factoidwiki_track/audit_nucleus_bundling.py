"""Post-hoc A1 (nucleus-bundling) audit, ported to the FactoidWiki track.

This mirrors ../audit_severance.py's A1 audit design as closely as
possible for paragraph-level input, over the 272 governing-relation
records in logs/task7_experiment_govern_log.jsonl (75 Condition + 197
Concession). It does NOT re-run screening, relation elicitation, or
atomization -- it re-reads the already-saved govern log. The only new
LLM calls are the sub-clause-scoped judge calls on the bundled-nucleus
subset (2 per bundled record: one against the saved
`condition_a_propositions`, one against `condition_b_propositions`).

A2 (severed-with-no-split) is explicitly OUT OF SCOPE here -- it was
already ported as `no_split_diagnostic.py` and its output already lives
in `results/task7_experiment_1_2_report.json`'s `no_split_diagnostic`
key. This script only ports A1, and writes an ADDITIVE new file
(`results/task7_nucleus_bundling_audit.json`); it never touches
`task7_experiment_1_2_report.json`.

DELIBERATE DEVIATION FROM THIS TRACK'S "NO SIBLING IMPORTS" CONVENTION
-----------------------------------------------------------------------
`env_utils.py` documents (and every other script in this directory
follows) a rule that factoidwiki_track/ must not import from its
siblings outside this directory, precisely so the track stays
self-contained and safely deletable/movable as a unit. This script is a
deliberate, narrow exception, made because the specific task that
created it instructed reuse-by-import rather than re-implementation:
the A1 bundling heuristic (`detect_bundling_sites` /
`choose_bundling_site` / `assign_governed_subclause` /
`connective_attachment`, all in ../audit_severance.py) is pure
English-clause-structure string/regex analysis with no CFR-specific
logic baked into its control flow, and the sub-clause-scoped judge
(`llm_judge_severance_subclause` in ../severance_detection.py) is a
prompt that was already iterated on and validated once (see
../RESULTS.md's audit addendum -- the first prompt draft was discarded
as claims-blind and the fix is now baked into that function). Copying
~250 lines of that heuristic and a validated prompt into this directory
would either (a) drift from the original as either side gets edited
later, or (b) require re-validating a second copy of the same judge
prompt against nothing. Importing it is copy-avoidance for logic that
was already audited once, not new coupling between the two tracks'
experiment pipelines (screening, elicitation, atomization,
`severance_judge_paragraph.py`'s primary judge, etc. all remain exactly
as self-contained as before -- only this bonus audit script reaches
across the boundary).

ADAPTATION NOTE: is the CFR-tuned heuristic actually reusable here?
---------------------------------------------------------------------
Yes, and NO wordlist/rule changes were made. `detect_bundling_sites` was
run unmodified against all 272 elicited FactoidWiki nuclei during
development of this script. It flagged 13/272 (4.8%) as bundled (12
clear, 1 borderline) -- lower than the CFR track's 8/47 (17.0%), which
is expected: Wikipedia narrative prose has less of the CFR corpus's
list-heavy, multiply-coordinated regulatory sentence structure. Every
one of the 13 catches came from the heuristic's two REGISTER-NEUTRAL
rules -- (a) "a_second_full_predicate" (a modal/auxiliary reappears
after the conjunction: X and IS/WAS/HAS ... ) and (d)
"d_participial_second_predication" (a comma-attached past-participle
second predication) -- rules that test for generic English clause
structure, not vocabulary. Rules (b) and (c), which key off
CFR-register-specific curated verb lists (FINITE_S_VERBS/BASE_VERBS --
e.g. "identifies", "shall follow"/"shall precede"), matched ZERO
FactoidWiki nuclei; this is an honest, expected finding (that
vocabulary is CFR's regulatory register, not Wikipedia's), not a defect
to fix. `assign_governed_subclause`'s difflib span-matching also worked
unmodified: it takes an arbitrary "sentence" string to search for
fragment spans in, and a whole Wikipedia paragraph (`content`, which is
typically several sentences) works exactly like a CFR sentence would --
all 13 bundled cases resolved to a governed sub-clause with no
RuntimeError (which would have fired had the satellite/sub-clauses not
been locatable in `content`). Given a clean, complete, self-consistent
result set with no crashes or degenerate matches, tuning the curated
verb lists for Wikipedia's much broader vocabulary was deliberately NOT
attempted -- doing so without a held-out validation set (the same
concern `severance_judge_paragraph.py`'s docstring raises about
reusing the CFR rule-based check un-validated) risks introducing
false positives/negatives calibrated to nothing. The heuristic is used
exactly as validated on the CFR corpus.

One additional field-name adaptation, not a logic change: CFR records
call the source text "sentence" and the atomized output "claims";
FactoidWiki records call them "content" (a paragraph) and
"propositions". The imported functions take positional/generic
arguments (a source-text string, a list-of-strings claims arg), so no
change to the imported code was needed -- only which saved field is
passed to which parameter.

Usage
-----
    venv/bin/python server/scripts/discourse_severance/factoidwiki_track/audit_nucleus_bundling.py             # full audit (2*n_bundled LLM calls)
    venv/bin/python server/scripts/discourse_severance/factoidwiki_track/audit_nucleus_bundling.py --skip-llm  # structural analysis only, no API calls
"""

import argparse
import json
import os
import sys

import env_utils
from env_utils import LOGS_DIR, RESULTS_DIR

if env_utils.SERVER_DIR not in sys.path:
    sys.path.insert(0, env_utils.SERVER_DIR)

env_utils.load_server_env()

# Imported (not re-implemented) per the deviation documented above.
from scripts.discourse_severance import audit_severance  # noqa: E402
from scripts.discourse_severance import severance_detection  # noqa: E402

GOVERN_LOG = os.path.join(LOGS_DIR, "task7_experiment_govern_log.jsonl")
OUTPUT_PATH = os.path.join(RESULTS_DIR, "task7_nucleus_bundling_audit.json")

EXPECTED_N = 272
EXPECTED_BY_RELATION = {"Condition": 75, "Concession": 197}

AUDIT_DATE = "2026-08-14"


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
    else keeps its original saved verdict. Mirrors
    ../audit_severance.py's `adjusted_counts` closure."""
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
          "imported unmodified from ../audit_severance.py) ===")
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

    # ---------------- step 2: connective attachment (read-only) ------------
    print("\n=== Step 2: connective attachment in saved atomized outputs "
          "(read-only, imported unmodified from ../audit_severance.py) ===")
    by_pool_index = {r["pool_index"]: r for r in recs}
    for entry in bundled:
        rec = by_pool_index[entry["pool_index"]]
        site = entry["chosen_site"]
        for cond, props_key in [("a", "condition_a_propositions"), ("b", "condition_b_propositions")]:
            att = audit_severance.connective_attachment(
                rec[props_key], rec["connective"],
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
            for cond, props_key in [("a", "condition_a_propositions"), ("b", "condition_b_propositions")]:
                verdict = severance_detection.llm_judge_severance_subclause(
                    rec["content"], relation, rec[props_key], entry["governed_subclause"])
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
            "Sub-clause-scoped ALTERNATIVE reading: bundled-subset records "
            "use the judge_prompt_subclause verdict (severance_detection."
            "llm_judge_severance_subclause), all other records keep their "
            "original saved judge_prompt_full_nucleus verdict "
            "(severance_a/severance_b.preserved from the govern log). NOT a "
            "replacement of the headline task7_experiment_1_2_report.json "
            "figures.")}
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

        # ---------------- step 5: exclusion list (parity with CFR audit) ---
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
            "note": ("Records scored severed=True under Condition A by the "
                     "ORIGINAL full-nucleus judge that FLIP to preserved "
                     "under the sub-clause judge. These define exclusions "
                     "from a future experiment's evaluation set."),
            "pool_indices": [x["pool_index"] for x in exclusions],
            "records": exclusions,
        }
        print(f"  Exclusion list (A severed -> sub-clause preserved): "
              f"{summary['future_eval_exclusion_list']['pool_indices']}")

    # ---------------- write output -------------------------------------------
    output = {
        "audit_date": AUDIT_DATE,
        "source_log": os.path.basename(GOVERN_LOG),
        "note": ("Post-hoc audit of SAVED results (A1 nucleus-bundling audit, "
                 "ported from ../audit_severance.py). Does not touch "
                 "task7_experiment_1_2_report.json; the original headline "
                 "numbers there are untouched. Figures here are a "
                 "sub-clause-scoped alternative reading reported alongside "
                 "them, not a replacement. A2 (no-split) is out of scope for "
                 "this script -- see no_split_diagnostic.py, already done."),
        "adaptation_note": (
            "The CFR-tuned bundling heuristic (detect_bundling_sites / "
            "choose_bundling_site / assign_governed_subclause / "
            "connective_attachment, imported unmodified from "
            "../audit_severance.py) was run as-is against all 272 elicited "
            "FactoidWiki nuclei -- NO wordlist or rule changes were made. It "
            "flagged 13/272 (4.8%) as bundled, all via the two "
            "register-neutral rules (a, second-full-predicate/auxiliary; d, "
            "participial second-predication); rules b/c (CFR-curated "
            "regulatory verb lists) matched zero cases here, as expected for "
            "Wikipedia prose. See this file's module docstring for the full "
            "reasoning."),
        "summary": summary,
        "records": [e for e in entries if e["bundled"]],
        "llm_calls_made": 0 if args.skip_llm else 2 * len(bundled),
    }
    with open(OUTPUT_PATH, "w", encoding="utf-8") as fh:
        json.dump(output, fh, indent=2, ensure_ascii=False)
    print(f"\nWrote {OUTPUT_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
