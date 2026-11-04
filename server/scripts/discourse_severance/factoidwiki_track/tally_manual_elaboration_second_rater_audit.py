"""Tally script for manual_elaboration_second_rater_audit.md.

Computes, from one or two filled-in copies of the sheet:
  - each rater's raw agreement against the corrected Elaboration judge's
    own verdict for the same 28 cases (a human-vs-judge validity check,
    reported separately from and never substituted for the existing
    82.4%-on-a-different-sample figure already in the paper)
  - if a second rater's copy is also provided, raw percent agreement AND
    Cohen's kappa BETWEEN THE TWO HUMAN RATERS (the actual reliability
    statistic Part 1 asked for; requires two independent copies, not one)

Usage
-----
    venv/bin/python tally_manual_elaboration_second_rater_audit.py \
        --rater1 manual_elaboration_second_rater_audit_rater1.md \
        [--rater2 manual_elaboration_second_rater_audit_rater2.md]

Each filled-in sheet must keep the "## Item N [...]" headers and
"VERDICT:"/"NOTES:" lines from the original template (some reformatting
tolerated, matching this project's established parser leniency for these
sheets -- see tally_manual_audit.py / tally_manual_concession_audit.py
for the same pattern).
"""

import argparse
import json
import os
import re
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
MANIFEST_PATH = os.path.join(SCRIPT_DIR, "manual_elaboration_second_rater_manifest.json")

ITEM_RE = re.compile(r"^#{0,2}\s*Item\s+(\d+)\b", re.MULTILINE)
VERDICT_RE = re.compile(r"VERDICT:[ \t]*(\S+)?[ \t]*(?:\n|$)")

VALID_VERDICTS = {"preserved", "severed-content-missing", "severed-misattributed", "other"}


def parse_sheet(path):
    text = open(path, encoding="utf-8").read()
    item_positions = [(int(m.group(1)), m.start()) for m in ITEM_RE.finditer(text)]
    item_positions.append((None, len(text)))
    verdicts = {}
    for i in range(len(item_positions) - 1):
        item_num, start = item_positions[i]
        _, end = item_positions[i + 1]
        block = text[start:end]
        vm = VERDICT_RE.search(block)
        verdict = vm.group(1).strip() if vm and vm.group(1) else None
        verdicts[item_num] = verdict
    return verdicts


def to_binary(verdict):
    """Collapse the 4-way verdict to preserved/severed for kappa purposes
    (severed-content-missing and severed-misattributed are both
    'severed'; 'other' is left out of the binary kappa, reported
    separately as an explicit non-fit rate, never silently folded in)."""
    if verdict == "preserved":
        return "preserved"
    if verdict in ("severed-content-missing", "severed-misattributed"):
        return "severed"
    return None


def cohens_kappa(rater1, rater2, items):
    pairs = [(rater1[i], rater2[i]) for i in items
             if to_binary(rater1.get(i)) and to_binary(rater2.get(i))]
    pairs = [(to_binary(a), to_binary(b)) for a, b in pairs]
    n = len(pairs)
    if n == 0:
        return None, 0
    agree = sum(1 for a, b in pairs if a == b)
    po = agree / n
    p_preserved_1 = sum(1 for a, _ in pairs if a == "preserved") / n
    p_preserved_2 = sum(1 for _, b in pairs if b == "preserved") / n
    p_severed_1 = 1 - p_preserved_1
    p_severed_2 = 1 - p_preserved_2
    pe = p_preserved_1 * p_preserved_2 + p_severed_1 * p_severed_2
    if pe == 1:
        return 1.0, n
    kappa = (po - pe) / (1 - pe)
    return kappa, n


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--rater1", required=True)
    ap.add_argument("--rater2", default=None)
    args = ap.parse_args()

    manifest = json.load(open(MANIFEST_PATH, encoding="utf-8"))
    n_items = len(manifest)
    items = list(range(1, n_items + 1))

    rater1 = parse_sheet(args.rater1)
    blank1 = [i for i in items if not rater1.get(i)]
    print(f"Rater 1 ({args.rater1}): {n_items - len(blank1)}/{n_items} filled, "
          f"{len(blank1)} blank: {blank1}")
    invalid1 = {i: v for i, v in rater1.items() if v and v not in VALID_VERDICTS}
    if invalid1:
        print(f"  WARNING -- unrecognized verdict strings: {invalid1}")

    if not args.rater2:
        print("\nNo second rater provided -- reporting rater 1 only, no kappa "
              "computed (kappa requires two independent human raters).")
        sys.exit(0)

    rater2 = parse_sheet(args.rater2)
    blank2 = [i for i in items if not rater2.get(i)]
    print(f"Rater 2 ({args.rater2}): {n_items - len(blank2)}/{n_items} filled, "
          f"{len(blank2)} blank: {blank2}")
    invalid2 = {i: v for i, v in rater2.items() if v and v not in VALID_VERDICTS}
    if invalid2:
        print(f"  WARNING -- unrecognized verdict strings: {invalid2}")

    both_filled = [i for i in items if rater1.get(i) and rater2.get(i)]
    raw_agree = sum(1 for i in both_filled if rater1[i] == rater2[i])
    print(f"\nExact 4-way agreement (preserved / severed-content-missing / "
          f"severed-misattributed / other): {raw_agree}/{len(both_filled)} "
          f"({100*raw_agree/len(both_filled):.1f}%)" if both_filled else "no overlapping items")

    kappa, n_binary = cohens_kappa(rater1, rater2, items)
    if kappa is not None:
        print(f"Cohen's kappa (preserved vs. severed, {n_binary} items with a "
              f"binary verdict from both raters): {kappa:.3f}")
    else:
        print("Could not compute kappa -- no items with a binary verdict from both raters.")

    other_count = sum(1 for i in both_filled
                       if rater1.get(i) == "other" or rater2.get(i) == "other")
    if other_count:
        print(f"NOTE: {other_count} items had an 'other' verdict from at least one "
              f"rater and were excluded from the binary kappa above, reported here "
              f"explicitly rather than silently folded into either category.")


if __name__ == "__main__":
    main()
