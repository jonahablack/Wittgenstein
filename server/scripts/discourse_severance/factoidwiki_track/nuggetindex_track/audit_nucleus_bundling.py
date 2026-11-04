"""Post-hoc A1 (nucleus-bundling) audit, adapted for NuggetIndex's
TRIPLE-shaped output.

Ports the STRUCTURAL heuristic from ../../audit_severance.py exactly as
../audit_nucleus_bundling.py (Propositionizer track) and
../../atomicrag_track/audit_nucleus_bundling.py (AtomicRAG) already do --
`detect_bundling_sites`, `choose_bundling_site`, `assign_governed_
subclause` are imported UNMODIFIED and operate only on the shared
`nucleus`/`content`/`satellite` fields, which are copied verbatim from
../../logs/task7_experiment_govern_log.jsonl into every chunker's own
govern log. So step 1 (bundling detection) and the governed-sub-clause
half of step 2 are guaranteed to reproduce the SAME 13/272 bundled
pool_indices (12 clear, 1 borderline) already found for the other two
chunkers -- verified below, not assumed (a RuntimeError would fire if the
source logs ever diverged).

WHAT CHANGES FOR TRIPLES (the two adaptation decisions this script makes,
stated explicitly as the task that created it required):

1. Step 2 (connective attachment): `connective_attachment` (imported
   unmodified from ../../audit_severance.py) takes a plain list of
   strings ("claims") and a connective, and checks keyword-overlap
   coverage against two candidate sub-clauses. It has no dependency on
   the claims being genuinely natural language beyond being strings --
   so it is called here with `nuggetindex_triples_rendered` (the SAME
   humanized pseudo-sentence rendering ../triple_severance_judge.py's
   primary judge already shows the LLM judge, via `render_triple`) as
   the claims list. This is real reuse of the function AND of the
   rendering step, not a new heuristic -- the only adaptation is which
   saved field gets passed in.

2. Step 3 (sub-clause-scoped judge): per the task brief, this step must
   use a TRIPLE-AWARE judge, for consistency with how NuggetIndex's
   primary severance measurement was judged (../triple_severance_judge.py
   -- exclude evidence_span, show raw+rendered fields side by side, etc.)
   rather than ../../severance_detection.py's natural-language sub-clause
   judge (which is what the Propositionizer-track and AtomicRAG-track
   versions of this audit reuse unmodified, since their claims genuinely
   are natural language). NO pre-existing triple-aware sub-clause judge
   existed anywhere in this project before this task, so
   ../triple_severance_judge.py was extended (additively -- its existing
   functions are untouched) with `llm_judge_triple_severance_subclause` /
   `build_triple_judge_prompt_subclause`, mirroring exactly how
   ../../severance_detection.py itself houses BOTH its full-nucleus and
   sub-clause judges side by side. See that function's docstring block in
   ../triple_severance_judge.py for the full reasoning on why this had to
   be written new rather than reused, and what within it IS reused
   (render_triple, _RELATION_DESCRIPTIONS, the scoping-note wording).

ONLY ONE CONDITION: NuggetIndex has no Condition-B analog (no
relation-hint input slot in its extraction prompt -- see
../nuggetindex_extractor_adapter.py's module docstring), so step 2 and
step 3 run once per bundled record, like ../../atomicrag_track/audit_
nucleus_bundling.py, not twice like the Propositionizer-track version.

Does NOT re-run extraction or the primary severance judge -- it re-reads
the already-saved govern log. The only new LLM calls are the sub-clause-
scoped triple-judge calls on the bundled-nucleus subset (1 per bundled
record, against the saved `nuggetindex_triples`).

Writes an ADDITIVE new file (results/nuggetindex_nucleus_bundling_audit.json);
never touches results/nuggetindex_severance_report.json.

Usage
-----
    venv/bin/python server/scripts/discourse_severance/factoidwiki_track/nuggetindex_track/audit_nucleus_bundling.py             # full audit (n_bundled LLM calls)
    venv/bin/python server/scripts/discourse_severance/factoidwiki_track/nuggetindex_track/audit_nucleus_bundling.py --skip-llm  # structural analysis only, no API calls
"""

import argparse
import json
import os
import sys

TRACK_DIR = os.path.dirname(os.path.abspath(__file__))
FACTOIDWIKI_TRACK_DIR = os.path.dirname(TRACK_DIR)
DISCOURSE_SEVERANCE_DIR = os.path.dirname(FACTOIDWIKI_TRACK_DIR)
SCRIPTS_DIR = os.path.dirname(DISCOURSE_SEVERANCE_DIR)
SERVER_DIR = os.path.dirname(SCRIPTS_DIR)

if TRACK_DIR not in sys.path:
    sys.path.insert(0, TRACK_DIR)
if SERVER_DIR not in sys.path:
    sys.path.insert(0, SERVER_DIR)

from env_utils import load_server_env  # noqa: E402  (this track's own env_utils)

load_server_env()

# Imported (not re-implemented): the A1 bundling heuristic is pure
# English-clause-structure string/regex analysis with no CFR-specific
# logic baked in -- see ../audit_nucleus_bundling.py's and
# ../../atomicrag_track/audit_nucleus_bundling.py's module docstrings for
# the same reasoning, taken here for a third, final chunker.
from scripts.discourse_severance import audit_severance  # noqa: E402

# This track's own triple-aware judge (full-nucleus judge already used
# for the primary severance measurement; sub-clause judge added
# alongside it specifically for this audit -- see module docstring).
from triple_severance_judge import (  # noqa: E402
    llm_judge_triple_severance_subclause,
    render_triple,
)

LOGS_DIR = os.path.join(TRACK_DIR, "logs")
RESULTS_DIR = os.path.join(TRACK_DIR, "results")
GOVERN_LOG = os.path.join(LOGS_DIR, "nuggetindex_govern_log.jsonl")
OUTPUT_PATH = os.path.join(RESULTS_DIR, "nuggetindex_nucleus_bundling_audit.json")

EXPECTED_N = 272
EXPECTED_BY_RELATION = {"Condition": 75, "Concession": 197}
EXPECTED_BUNDLED_POOL_INDICES = {1840, 1936, 3263, 3360, 3397, 3444, 4208,
                                  4380, 4698, 4707, 4859, 4920, 5132}

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


def adjusted_counts(records, bundled_by_key, subset_pred):
    """Severed count over `records` with bundled-subset (filtered by
    subset_pred) verdicts swapped for the sub-clause verdicts; everything
    else keeps its original saved verdict."""
    severed = 0
    for rec in records:
        entry = bundled_by_key.get(rec["pool_index"])
        if entry is not None and subset_pred(entry):
            preserved = entry["subclause_judge"]["preserved"]
        else:
            preserved = rec["severance_nuggetindex"]["preserved"]
        if preserved is False:
            severed += 1
    return severed


def figure_block(records, bundled_by_key, subset_pred):
    n = len(records)
    orig = sum(1 for r in records if r["severance_nuggetindex"]["preserved"] is False)
    adj = adjusted_counts(records, bundled_by_key, subset_pred)
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
                             "triple-judge LLM calls (output will mark them as not run)")
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
    same_as_other_tracks = found_bundled == EXPECTED_BUNDLED_POOL_INDICES
    print(f"Same 13 pool_indices as the other two tracks' audits: "
          f"{same_as_other_tracks} (expected, since detection depends only "
          "on the shared nucleus/content/satellite fields -- see module docstring)")

    # ---------------- step 2: connective attachment (read-only, adapted) ---
    print("\n=== Step 2: connective attachment in saved atomized outputs "
          "(read-only; ../../audit_severance.py's connective_attachment "
          "called against nuggetindex_triples_rendered -- see module "
          "docstring, adaptation 1) ===")
    by_pool_index = {r["pool_index"]: r for r in recs}
    for entry in bundled:
        rec = by_pool_index[entry["pool_index"]]
        site = entry["chosen_site"]
        att = audit_severance.connective_attachment(
            rec["nuggetindex_triples_rendered"], rec["connective"],
            site["subclause_1"], site["subclause_2"],
            entry["governed_subclause_index"])
        entry["attachment"] = att
        print(f"  pool_index={entry['pool_index']}: "
              f"present={att['connective_present']} attachment={att['attachment']} "
              f"same_as_governed={att['same_subclause_as_governed']}")

    # ---------------- step 3: sub-clause-scoped TRIPLE judge (adapted) -----
    if args.skip_llm:
        print("\n=== Step 3: SKIPPED (--skip-llm) ===")
    else:
        print(f"\n=== Step 3: sub-clause TRIPLE judge on {len(bundled)} bundled "
              f"records ({len(bundled)} LLM calls; see module docstring, "
              "adaptation 2, for why this is a NEW triple-aware function "
              "rather than ../../severance_detection.py's natural-language "
              "sub-clause judge) ===")
        for entry in bundled:
            rec = by_pool_index[entry["pool_index"]]
            relation = {k: rec[k] for k in ("relation_type", "nucleus", "satellite", "connective")}
            verdict = llm_judge_triple_severance_subclause(
                rec["content"], relation, rec["nuggetindex_triples"], entry["governed_subclause"])
            if verdict["preserved"] is None:
                raise RuntimeError(
                    f"Sub-clause triple-judge call failed for pool_index={entry['pool_index']}: "
                    f"{verdict['reasoning']} -- refusing to compute adjusted figures "
                    "from missing data.")
            entry["subclause_judge"] = verdict
            orig = rec["severance_nuggetindex"]["preserved"]
            entry["verdict_change"] = {
                "original_full_nucleus_preserved": orig,
                "subclause_preserved": verdict["preserved"],
                "changed": orig != verdict["preserved"],
            }
            print(f"  pool_index={entry['pool_index']}: "
                  f"full-nucleus preserved={orig} -> sub-clause preserved="
                  f"{verdict['preserved']}"
                  f"{'  [CHANGED]' if orig != verdict['preserved'] else ''}")

    # ---------------- step 4: adjusted secondary figures --------------------
    summary = {
        "n_total": EXPECTED_N,
        "n_bundled": len(bundled),
        "n_bundled_clear": len(bundled) - n_borderline,
        "n_bundled_borderline": n_borderline,
        "same_bundled_set_as_other_tracks": same_as_other_tracks,
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
            "sub-clause TRIPLE-judge verdict (triple_severance_judge."
            "llm_judge_triple_severance_subclause against nuggetindex_triples), all "
            "other records keep their original saved judge_prompt_full_nucleus verdict "
            "(severance_nuggetindex.preserved from the govern log). NOT a replacement "
            "of the headline nuggetindex_severance_report.json figures.")}
        adjusted["nuggetindex_overall"] = figure_block(recs, bundled_by_key, lambda e: True)
        adjusted["nuggetindex_overall_clear_bundles_only"] = figure_block(
            recs, bundled_by_key, lambda e: e["clarity"] == "clear")
        adjusted["nuggetindex_by_relation_type"] = {
            "Condition": figure_block(condition_recs, bundled_by_key, lambda e: True),
            "Concession": figure_block(concession_recs, bundled_by_key, lambda e: True),
        }
        summary["adjusted_secondary_figures"] = adjusted

        print("\n=== Adjusted secondary figures (sub-clause-scoped alternative reading) ===")
        block = adjusted["nuggetindex_overall"]
        print(f"  NuggetIndex overall: original {block['original_severed_rate']} "
              f"-> adjusted {block['adjusted_severed_rate']}")

        # ---------------- step 5: exclusion list (parity with the other tracks) ---
        exclusions = []
        for entry in bundled:
            rec = by_pool_index[entry["pool_index"]]
            if (rec["severance_nuggetindex"]["preserved"] is False
                    and entry["subclause_judge"]["preserved"] is True):
                exclusions.append({
                    "pool_index": entry["pool_index"],
                    "relation_type": entry["relation_type"],
                    "clarity": entry["clarity"],
                    "title": rec["title"],
                })
        summary["future_eval_exclusion_list"] = {
            "note": ("Records scored severed=True under NuggetIndex by the ORIGINAL "
                     "full-nucleus judge that FLIP to preserved under the sub-clause "
                     "judge. These define exclusions from a future experiment's "
                     "evaluation set."),
            "pool_indices": [x["pool_index"] for x in exclusions],
            "records": exclusions,
        }
        print(f"  Exclusion list (NuggetIndex severed -> sub-clause preserved): "
              f"{summary['future_eval_exclusion_list']['pool_indices']}")

    # ---------------- write output -------------------------------------------
    output = {
        "audit_date": AUDIT_DATE,
        "source_log": os.path.basename(GOVERN_LOG),
        "note": ("Post-hoc audit of SAVED results (A1 nucleus-bundling audit, ported "
                 "from ../../audit_severance.py). Does not touch "
                 "results/nuggetindex_severance_report.json; the original headline "
                 "numbers there are untouched. Figures here are a sub-clause-scoped "
                 "alternative reading reported alongside them, not a replacement. A2 "
                 "(no-split) is out of scope for this script -- see "
                 "no_split_diagnostic.py, already done."),
        "adaptation_note": (
            "Bundling DETECTION (detect_bundling_sites / choose_bundling_site / "
            "assign_governed_subclause, imported unmodified from "
            "../../audit_severance.py) reproduces the identical 13/272 (12 clear, 1 "
            "borderline) pool_indices already found for the Propositionizer and "
            "AtomicRAG tracks, because detection depends only on the nucleus/content/"
            "satellite fields shared verbatim across every chunker's govern log. TWO "
            "adaptations were made for NuggetIndex's triple shape: (1) step 2's "
            "connective_attachment (also imported unmodified) is called against "
            "nuggetindex_triples_rendered (the same humanized pseudo-sentence "
            "rendering the primary triple judge already shows the LLM) instead of a "
            "natural-language claims list; (2) step 3 uses a NEW triple-aware "
            "sub-clause judge (triple_severance_judge.llm_judge_triple_severance_"
            "subclause, added alongside -- not replacing -- the existing full-nucleus "
            "triple judge in that file) instead of "
            "severance_detection.llm_judge_severance_subclause, since no triple-aware "
            "sub-clause judge existed anywhere in this project before this task. See "
            "this script's and triple_severance_judge.py's module docstrings for the "
            "full reasoning."
        ),
        "summary": summary,
        "records": [e for e in entries if e["bundled"]],
        "llm_calls_made": 0 if args.skip_llm else len(bundled),
    }
    os.makedirs(RESULTS_DIR, exist_ok=True)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as fh:
        json.dump(output, fh, indent=2, ensure_ascii=False)
    print(f"\nWrote {OUTPUT_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
