"""One-off refresh: recompute condition_4_flags against the CURRENT
server/components/risk_triage.py.

Why this exists: exp3_report.json's condition_4_flags (and every summary
field derived from it) was computed on 2026-08-07, before this session's
RST-grounded detector rebuild (retired detect_hedges/nested_conditional,
added detect_condition_satellite/detect_concession_satellite). Confirmed
by inspection: the saved flags still contain "hedge" and
"segment_nested_conditional" (both retired) and never contain
"condition_satellite"/"concession_satellite" (both new). That made the
saved data stale relative to the shipped classifier it is documented
(here and in study_harness/README.md) to reflect verbatim -- and it had
already propagated into a written paper number (experiments.tex's
"58.1% of the Disco-RAG arm's wrong repairs").

flags_for_case() is a pure, deterministic, LLM-free function of a case's
claims + source sentence (server/components/risk_triage.flag_claim,
imported UNMODIFIED, same as run_exp3.py). This script:
  1. Recomputes condition_4_flags for all 38 records via
     run_exp3.flags_for_case, reusing that function verbatim (never
     reimplemented here).
  2. Re-derives every summary field that reads condition_4_flags
     (condition_4_flag_summary, both original cross-tabs, both
     extension cross-tabs, both confidently-wrong documentation lists,
     and the calibration cross-tab) via run_exp3's and
     run_exp3_extension's own already-tested functions -- never
     reimplemented here either.
  3. Leaves every other field (arm_1/2/3 recovery results, calibration
     hedging classifications, condition_6 summary, context diagnostic,
     attribution, reproducibility, extension metadata) byte-identical:
     none of that depends on risk_triage.py.
  4. Records an explicit provenance note (condition_4_flags_refresh) so
     the recompute is visible in the file itself, not just this
     docstring.

Usage
-----
    venv/bin/python server/scripts/discourse_severance/exp3_recovery_comparison/refresh_condition_4_flags.py
"""

import datetime
import json
import os
import sys

EXP3_DIR = os.path.dirname(os.path.abspath(__file__))
SCRIPT_DIR = os.path.dirname(EXP3_DIR)
SERVER_DIR = os.path.dirname(os.path.dirname(SCRIPT_DIR))
if SERVER_DIR not in sys.path:
    sys.path.insert(0, SERVER_DIR)

from scripts.discourse_severance.exp3_recovery_comparison import (  # noqa: E402
    run_exp3,
    run_exp3_extension as ext,
)

JSON_REPORT = run_exp3.JSON_REPORT
MD_REPORT = run_exp3.MD_REPORT


def main():
    with open(JSON_REPORT, encoding="utf-8") as fh:
        report = json.load(fh)
    records = report["records"]
    assert len(records) == 38, f"expected 38 records, found {len(records)}"

    old_flag_summary = report["summary"]["condition_4_flag_summary"]

    for r in records:
        shim = {
            "condition_a_claims": r["condition_1_no_elicitation"]["claims"],
            "sentence": r["sentence"],
        }
        r["condition_4_flags"] = run_exp3.flags_for_case(shim)

    new_flag_summary = run_exp3.flag_summary(records)
    report["summary"]["condition_4_flag_summary"] = new_flag_summary
    report["summary"]["cross_tab_arm_1_vs_flags"] = run_exp3.cross_tab(
        records, "condition_2_disco_rag")
    report["summary"]["cross_tab_arm_2_vs_flags"] = run_exp3.cross_tab(
        records, "condition_3_custom_fallback")
    report["summary"]["confidently_wrong_documentation"] = (
        run_exp3.confidently_wrong_docs(records))

    report["summary"]["cross_tab_arm_3_vs_flags"] = run_exp3.cross_tab(
        records, ext.CONDITION_5_KEY)
    report["summary"]["cross_tab_condition_6_parent_segment_vs_flags"] = (
        run_exp3.cross_tab(records, ext.CONDITION_6_KEY))
    report["summary"]["confidently_wrong_documentation_new_arms"] = (
        ext.confidently_wrong_docs_new_arms(records))
    report["summary"]["calibration_summary"] = ext.calibration_summary(records)

    report["condition_4_flags_refresh"] = {
        "refreshed_on": datetime.date.today().isoformat(),
        "reason": (
            "condition_4_flags was originally computed on 2026-08-07, "
            "before the same-session RST-grounded risk_triage.py rebuild "
            "(detect_hedges/detect_nested_conditional retired; "
            "detect_condition_satellite/detect_concession_satellite "
            "added). This recompute reruns the same flags_for_case() "
            "logic against the current classifier so condition_4_flags "
            "and every summary field derived from it (flag_summary, "
            "cross_tab_arm_1/2/3_vs_flags, "
            "cross_tab_condition_6_parent_segment_vs_flags, both "
            "confidently_wrong_documentation lists, calibration_summary's "
            "flagged/not-flagged cross-tab) reflect the classifier as "
            "actually shipped. No arm's recovered claims, judge "
            "verdicts, wrongness classifications, or calibration "
            "(hedging) classifications were touched -- none of those "
            "depend on risk_triage.py."
        ),
        "old_condition_4_flag_summary": old_flag_summary,
        "new_condition_4_flag_summary": new_flag_summary,
    }

    with open(JSON_REPORT, "w", encoding="utf-8") as fh:
        json.dump(report, fh, indent=2, ensure_ascii=False)

    print("old:", json.dumps(old_flag_summary, indent=2))
    print("new:", json.dumps(new_flag_summary, indent=2))
    print(f"\nwrote {JSON_REPORT}")


if __name__ == "__main__":
    main()
