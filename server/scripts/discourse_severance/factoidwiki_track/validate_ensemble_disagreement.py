"""Step 2 of the ensemble-disagreement reframe for Experiment 3's ground
truth (see the task that authorized this: reframe Exp3's ground truth
from single-judge verdict to ensemble-disagreement, gated on validating
against data already in hand BEFORE applying it to anything new).

Ensemble (4 members, all real, already-built or newly-built-and-grounded
-- NOT 5; a 5th named member, a standalone "deletion/replacement-test"
judge PROMPT distinct from the one added here, did not exist anywhere in
this project's history and was not fabricated to fill the slot):

  (a) llm_judge_paragraph_severance -- the production judge ("would a
      reader understand"). CONSTANT on both validation sets below: every
      case in both the 36-item and 125-item sheets was selected BECAUSE
      this judge scored it severed, so its vote contributes zero
      variance here by construction -- included as the reference vote
      every other member's dissent is measured against, not as a live
      variable.
  (b) llm_judge_paragraph_severance_condition_concession_v2 -- the
      "explicit narration not required" framing. Real, already-built,
      but its own code comment says "NOT validated, DO NOT call in
      production" (33.6% agreement, 33% JSON-parse-failure rate, known
      design flaw). Included anyway: an ensemble member does not need to
      be individually strong to contribute a genuinely different,
      defensible standard.
  (v3) llm_judge_paragraph_severance_condition_concession_v3 -- the
      two-call locator + attachment-mismatch architecture that
      superseded (b). 44.5% agreement on its own prior validation run.
  (d) llm_judge_paragraph_severance_deletion_replacement -- NEW, built
      for this task, anchored strictly to Carlson & Marcu (2001)'s
      deletion and replacement tests quoted verbatim (see the block
      comment directly above it in severance_judge_paragraph.py).
      NOT validated before this run.
  (rule) severance_detection.rule_based_severance -- imported UNMODIFIED
      from the CFR/sentence-level track (its logic was never actually
      sentence-length-specific: plain substring/keyword checks over
      whatever text string is passed). Free (no LLM call). NOTE: this
      track's own module docstring previously declined to port this
      exact check, specifically because it was "never validated against
      Wikipedia prose" and "introducing it here un-validated would risk
      a second, silently-miscalibrated metric" -- this run IS that
      validation, not a reversal of that earlier caution.

PRE-REGISTERED HYPOTHESIS (written before this script is run, not after
seeing its output):

  H1: For each case, define DISSENT COUNT = the number of {b, v3, d}
  that vote preserved=True (i.e. disagree with (a)'s constant
  severed=False call). [rule-based is reported separately, not folded
  into DISSENT COUNT, since "None/not-applicable" is a common, valid
  outcome for it and would bias a simple count.]

  Cases hand-confirmed as mislabeled_actually_correct (the ORIGINAL
  judge (a) was WRONG -- the relation actually survives) should show
  HIGHER dissent counts than cases hand-confirmed as genuinely severed
  ((a) was RIGHT). This is checked via (1) mean dissent count in each
  hand-confirmed group, (2) a Mann-Whitney U test on the two
  distributions, and (3) point-biserial correlation between dissent
  count and hand-confirmed-mislabeled (1/0).

  DECISION RULE, fixed now: if the Mann-Whitney p-value is not < 0.05,
  or if the two groups' mean dissent counts differ by less than 0.3 (on
  a 0-3 scale), disagreement is treated as NOT discriminating anything
  useful on this data, and Step 3 (building Experiment 3's full material
  set on this basis) does not proceed -- the reframe gets reconsidered,
  not patched to force a positive result.

Data sources (both ALREADY hand-audited by a human, ground truth taken
directly from those completed sheets, not re-derived):
  - manual_exp2_condition_concession_audit.md (36 items, VERDICT filled
    2026-08-18): "severed" = hand-confirmed the original judge was
    right; "mislabeled_actually_correct" = hand-confirmed the original
    judge was wrong.
  - results/dangerous_failure_full_audit.json (125 items):
    "confirmed_dangerous_failure" = hand-confirmed right;
    "mislabeled_actually_correct" = hand-confirmed wrong; "ambiguous"
    (8 items) excluded from this analysis, same as every other script
    in this project that has used this file.

Usage:
    venv/bin/python server/scripts/discourse_severance/factoidwiki_track/validate_ensemble_disagreement.py
"""
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PARENT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, PARENT)

from severance_judge_paragraph import (  # noqa: E402
    llm_judge_paragraph_severance_condition_concession_v2,
    llm_judge_paragraph_severance_condition_concession_v3,
    llm_judge_paragraph_severance_deletion_replacement,
)
from severance_detection import rule_based_severance  # noqa: E402

SHEET_36 = os.path.join(HERE, "manual_exp2_condition_concession_audit.md")
AUDIT_125 = os.path.join(HERE, "results", "dangerous_failure_full_audit.json")
TASK8_REPORT = os.path.join(HERE, "results", "task8_factoidwiki_exp3_report.json")
OUT_PATH = os.path.join(HERE, "results", "ensemble_disagreement_validation.json")

ITEM_HEADER_RE = re.compile(r"^## Item (\d+) \[(\w+) / pool_index (\d+) / (\w+)\]", re.MULTILINE)
FIELD_RE = {
    "title": re.compile(r"\*\*Title:\*\* (.+)"),
    "source": re.compile(r"\*\*Source paragraph:\*\* (.+?)\n\n\*\*Nucleus", re.S),
    "nucleus": re.compile(r"\*\*Nucleus:\*\* (.+)"),
    "satellite": re.compile(r"\*\*Satellite:\*\* (.+)"),
    "connective": re.compile(r"\*\*Connective:\*\* (.+)"),
}
OUT_RE = re.compile(
    r"\*\*(Atomized (?:claims|propositions) actually produced|"
    r"Rendered \(subject, predicate, object\) triples actually produced):\*\*\n(.+?)\n\nVERDICT",
    re.S,
)
VERDICT_RE = re.compile(r"^VERDICT:\s*(\S+)?\s*$", re.MULTILINE)


def _clean_quoted(s):
    return s.strip().strip("'\"")


def load_36():
    src = open(SHEET_36, encoding="utf-8").read()
    headers = list(ITEM_HEADER_RE.finditer(src))
    items = []
    for i, h in enumerate(headers):
        start, end = h.end(), (headers[i + 1].start() if i + 1 < len(headers) else len(src))
        block = src[start:end]
        vm = VERDICT_RE.search(block)
        verdict = vm.group(1) if vm and vm.group(1) else None
        om = OUT_RE.search(block)
        out_items = [l.strip("- ").strip() for l in om.group(2).strip().split("\n") if l.strip()] if om else []
        items.append({
            "case_id": f"exp2-item{h.group(1)}",
            "source_set": "exp2_36",
            "relation_type": h.group(4),
            "hand_verdict": verdict,
            "paragraph": FIELD_RE["source"].search(block).group(1).strip(),
            "relation": {
                "relation_type": h.group(4),
                "nucleus": _clean_quoted(FIELD_RE["nucleus"].search(block).group(1)),
                "satellite": _clean_quoted(FIELD_RE["satellite"].search(block).group(1)),
                "connective": _clean_quoted(FIELD_RE["connective"].search(block).group(1)),
            },
            "propositions": out_items,
        })
    return items


def load_125():
    audit = json.load(open(AUDIT_125, encoding="utf-8"))
    report = json.load(open(TASK8_REPORT, encoding="utf-8"))
    records_by_pool = {r["pool_index"]: r for r in report["records"]}
    items = []
    for c in audit["cases"]:
        cls = c["audit_classification"]
        if cls not in ("confirmed_dangerous_failure", "mislabeled_actually_correct"):
            continue  # exclude "ambiguous", same convention as every prior script
        rec = records_by_pool.get(c["pool_index"])
        if rec is None:
            continue
        hand_verdict = "severed" if cls == "confirmed_dangerous_failure" else "mislabeled_actually_correct"
        items.append({
            "case_id": f"exp3-{c['pool_index']}-{c['arm']}",
            "source_set": "exp3_125",
            "relation_type": c["relation_type"],
            "hand_verdict": hand_verdict,
            "paragraph": rec["content"],
            "relation": c["relation"],
            "propositions": c["propositions"],
        })
    return items


def run_ensemble(item, i, total):
    r = item["relation"]
    p = item["paragraph"]
    props = item["propositions"]
    sys.stderr.write(f"[{i}/{total}] {item['case_id']} ({item['relation_type']}) ... ")
    sys.stderr.flush()

    v2 = llm_judge_paragraph_severance_condition_concession_v2(p, r, props)
    v3 = llm_judge_paragraph_severance_condition_concession_v3(p, r, props)
    dr = llm_judge_paragraph_severance_deletion_replacement(p, r, props)
    rb = rule_based_severance(p, r, props)

    sys.stderr.write(f"b={v2['preserved']} v3={v3['preserved']} d={dr['preserved']} "
                      f"rule={rb['rule_based_preserved']}\n")
    return {
        "b_v2_preserved": v2["preserved"], "b_v2_reasoning": v2["reasoning"],
        "v3_preserved": v3["preserved"], "v3_reasoning": v3["reasoning"],
        "d_deletion_replacement_preserved": dr["preserved"], "d_reasoning": dr["reasoning"],
        "rule_based_preserved": rb["rule_based_preserved"], "rule_based_detail": rb["rule_based_detail"],
    }


def main():
    items = load_36() + load_125()
    print(f"Loaded {len(items)} cases ({sum(1 for i in items if i['source_set']=='exp2_36')} from the "
          f"36-item sheet, {sum(1 for i in items if i['source_set']=='exp3_125')} from the 125-item audit, "
          f"ambiguous cases already excluded).")
    unfilled = [i for i in items if i["hand_verdict"] not in ("severed", "mislabeled_actually_correct")]
    if unfilled:
        print(f"WARNING: {len(unfilled)} case(s) with missing/invalid hand verdict, dropping: "
              f"{[i['case_id'] for i in unfilled]}")
        items = [i for i in items if i not in unfilled]

    total = len(items)
    for i, item in enumerate(items, 1):
        item["ensemble"] = run_ensemble(item, i, total)

    json.dump(items, open(OUT_PATH, "w", encoding="utf-8"), indent=2)
    print(f"\nRaw results written to {OUT_PATH}")


if __name__ == "__main__":
    main()
