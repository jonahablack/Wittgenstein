"""Tally manual_exp2_condition_concession_audit.md once a human has filled
in its VERDICT lines. Reports the human-confirmed mislabel rate overall
and stratified by chunker and by relation type, and compares directly
against dangerous_failure_full_audit.json's 65.6% figure (the Experiment
3 audit that motivated this sheet), since the sheet exists specifically
to check whether that same over-rejection pattern generalizes to
Experiment 1/2's own raw severed-verdict material.

Usage:
    venv/bin/python server/scripts/discourse_severance/factoidwiki_track/tally_manual_exp2_condition_concession_audit.py
"""
import json
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))
SHEET = os.path.join(HERE, "manual_exp2_condition_concession_audit.md")
MANIFEST = os.path.join(HERE, "manual_exp2_condition_concession_manifest.json")
DANGEROUS_FAILURE_AUDIT = os.path.join(HERE, "results", "dangerous_failure_full_audit.json")

VALID = {"severed", "mislabeled_actually_correct", "ambiguous"}
ITEM_HEADER_RE = re.compile(r"^## Item (\d+) \[(\w+) / pool_index (\d+) / (\w+)\]", re.MULTILINE)
VERDICT_RE = re.compile(r"^VERDICT:\s*(\S+)?\s*$", re.MULTILINE)


def parse_sheet():
    src = open(SHEET, encoding="utf-8").read()
    headers = list(ITEM_HEADER_RE.finditer(src))
    items = []
    for i, h in enumerate(headers):
        start = h.end()
        end = headers[i + 1].start() if i + 1 < len(headers) else len(src)
        block = src[start:end]
        vm = VERDICT_RE.search(block)
        verdict = vm.group(1) if vm and vm.group(1) else None
        items.append({
            "num": int(h.group(1)), "chunker": h.group(2),
            "pool_index": int(h.group(3)), "relation": h.group(4),
            "verdict": verdict,
        })
    return items


def rate_block(items, label):
    scored = [it for it in items if it["verdict"] in ("severed", "mislabeled_actually_correct")]
    n = len(scored)
    if n == 0:
        print(f"  {label}: no scored items")
        return
    mislabeled = sum(1 for it in scored if it["verdict"] == "mislabeled_actually_correct")
    confirmed = n - mislabeled
    amb = sum(1 for it in items if it["verdict"] == "ambiguous")
    print(f"  {label}: n={n} | mislabeled_actually_correct={mislabeled} ({mislabeled/n:.1%}) "
          f"| confirmed severed={confirmed} ({confirmed/n:.1%})" + (f" | ambiguous={amb}" if amb else ""))


def main():
    items = parse_sheet()
    unfilled = [it for it in items if it["verdict"] not in VALID]
    if unfilled:
        print(f"WARNING: {len(unfilled)} item(s) still unfilled or invalid: "
              f"{[it['num'] for it in unfilled]}")

    print(f"Manual audit of Experiment 1/2's own raw severed-verdict material: {len(items)} items\n")

    print("=== Overall ===")
    rate_block(items, "All 36")

    print("\n=== By chunker ===")
    by_chunker = {}
    for it in items:
        by_chunker.setdefault(it["chunker"], []).append(it)
    for chunker in sorted(by_chunker):
        rate_block(by_chunker[chunker], chunker)

    print("\n=== By relation type ===")
    by_rel = {}
    for it in items:
        by_rel.setdefault(it["relation"], []).append(it)
    for rel in sorted(by_rel):
        rate_block(by_rel[rel], rel)

    print("\n=== Comparison to Experiment 3's dangerous_failure_full_audit.json ===")
    if os.path.exists(DANGEROUS_FAILURE_AUDIT):
        exp3 = json.load(open(DANGEROUS_FAILURE_AUDIT, encoding="utf-8"))
        exp3_counts = exp3["counts"]
        exp3_n = sum(exp3_counts.get(k, 0) for k in ("confirmed_dangerous_failure", "mislabeled_actually_correct"))
        exp3_mislabeled = exp3_counts.get("mislabeled_actually_correct", 0)
        print(f"  Experiment 3 (recovery-arm output, n={exp3_n}): "
              f"{exp3_mislabeled}/{exp3_n} ({exp3_mislabeled/exp3_n:.1%}) mislabeled_actually_correct")
    scored = [it for it in items if it["verdict"] in ("severed", "mislabeled_actually_correct")]
    n = len(scored)
    mislabeled = sum(1 for it in scored if it["verdict"] == "mislabeled_actually_correct")
    print(f"  Experiment 1/2 (original atomized-claim output, n={n}): "
          f"{mislabeled}/{n} ({mislabeled/n:.1%}) mislabeled_actually_correct")
    print("  -> Same judge (llm_judge_paragraph_severance), same failure direction (over-rejection), "
          "checked on two disjoint input distributions (Exp3's recovery-arm text vs. Exp1/2's original "
          "atomized-claim text). Close agreement between the two rates is evidence the over-rejection "
          "pattern is a property of the judge itself, not an artifact of either input distribution.")


if __name__ == "__main__":
    main()
