"""Tallies the HUMAN-filled manual_condition_audit.md review sheet.

Run AFTER a human has filled in the VERDICT lines (see the sheet's own
instructions). Reports the verdict distribution and the mislabel rate
(mislabeled-* verdicts / filled random items). Items marked
[NON-RANDOM CHECK CASE] are tallied separately and excluded from the
random-sample mislabel-rate estimate.

Usage
-----
    venv/bin/python server/scripts/discourse_severance/tally_manual_audit.py
"""

import os
import re
import sys
from collections import Counter

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SHEET_PATH = os.path.join(SCRIPT_DIR, "manual_condition_audit.md")

ALLOWED_VERDICTS = {
    "genuine-Condition",
    "mislabeled-Purpose",
    "mislabeled-Result",
    "mislabeled-Elaboration",
    "other",
}
MISLABEL_VERDICTS = {"mislabeled-Purpose", "mislabeled-Result",
                     "mislabeled-Elaboration"}

ITEM_RE = re.compile(r"^#{0,2}\s*(Item \d+)\s+(\[[^\]]+\])\s*(.*)$")
VERDICT_RE = re.compile(r"^-?\s*VERDICT:\s*(.*)$")


def parse_sheet(path):
    if not os.path.exists(path):
        raise SystemExit(f"Sheet not found: {path} -- run audit_severance.py first.")
    items = []
    current = None
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            m = ITEM_RE.match(line)
            if m:
                current = {"item": m.group(1), "tag": m.group(2),
                           "meta": m.group(3).strip(), "verdict": None}
                items.append(current)
                continue
            m = VERDICT_RE.match(line)
            if m and current is not None:
                current["verdict"] = m.group(1).strip() or None
    return items


def main():
    items = parse_sheet(SHEET_PATH)
    if not items:
        raise SystemExit("No items found in the sheet -- is the file intact?")

    bad = [i for i in items
           if i["verdict"] is not None and i["verdict"] not in ALLOWED_VERDICTS]
    if bad:
        for i in bad:
            print(f"UNRECOGNIZED verdict on {i['item']}: {i['verdict']!r}", file=sys.stderr)
        raise SystemExit(f"{len(bad)} unrecognized verdict label(s) -- allowed: "
                         f"{sorted(ALLOWED_VERDICTS)}")

    random_items = [i for i in items if i["tag"] == "[RANDOM]"]
    check_items = [i for i in items if i["tag"] != "[RANDOM]"]
    unfilled = [i for i in random_items if i["verdict"] is None]
    filled = [i for i in random_items if i["verdict"] is not None]

    print(f"Sheet: {SHEET_PATH}")
    print(f"Random items: {len(random_items)} ({len(filled)} filled, "
          f"{len(unfilled)} still blank)")
    if unfilled:
        print("  Blank: " + ", ".join(i["item"] for i in unfilled))

    if filled:
        counts = Counter(i["verdict"] for i in filled)
        print("\nVerdict distribution (random items):")
        for verdict, n in sorted(counts.items()):
            print(f"  {verdict}: {n}")
        mislabeled = sum(n for v, n in counts.items() if v in MISLABEL_VERDICTS)
        non_genuine = sum(n for v, n in counts.items() if v != "genuine-Condition")
        print(f"\nNarrow mislabel rate (named categories only -- mislabeled-Purpose/"
              f"-Result/-Elaboration): {mislabeled}/{len(filled)} "
              f"({100 * mislabeled / len(filled):.1f}%)")
        print(f"Non-genuine rate (everything NOT verdict=genuine-Condition, "
              f"including 'other'): {non_genuine}/{len(filled)} "
              f"({100 * non_genuine / len(filled):.1f}%)")
        other_n = counts.get("other", 0)
        if other_n:
            print(f"  NOTE: {other_n} item(s) were marked 'other' -- the narrow rate "
                  "above assumes these are NOT mislabels (a category miss, not a "
                  "content error). Read each 'other' NOTES line yourself: if the "
                  "reasoning says the relation genuinely isn't Condition (just not one "
                  "of the three named failure modes), it belongs in the non-genuine "
                  "rate instead, not the narrow one.")
        if unfilled:
            print("NOTE: rate computed over FILLED items only -- finish the "
                  "sheet for the final estimate.")
    else:
        print("\nNo random items filled in yet -- nothing to tally.")

    for i in check_items:
        print(f"\n{i['tag']} {i['item']} ({i['meta']}): "
              f"verdict={i['verdict'] or '(blank)'} -- excluded from the "
              "random mislabel-rate estimate.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
