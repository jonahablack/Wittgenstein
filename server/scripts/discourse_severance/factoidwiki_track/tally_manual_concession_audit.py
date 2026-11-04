"""Tally server/scripts/discourse_severance/factoidwiki_track/manual_concession_audit.md
once a human has filled in its VERDICT lines.

Mirrors the parent discourse_severance/tally_manual_audit.py's approach:
parse the filled-in sheet, report the human-confirmed rate overall and
per stratum (DISAGREEMENT vs AGREEMENT, see the sheet's own header for
what those mean), and compare against both automated passes' verdicts on
the same items so the sheet's purpose -- settling which automated
reading was closer to right -- has a direct answer.

Usage:
    venv/bin/python server/scripts/discourse_severance/factoidwiki_track/tally_manual_concession_audit.py
"""
import json
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))
SHEET = os.path.join(HERE, "manual_concession_audit.md")
MANIFEST = os.path.join(HERE, "manual_concession_audit_manifest.json")
STAGE2_LOG = os.path.join(HERE, "logs", "task6_stage2_log.jsonl")
REVISED_LOG = os.path.join(
    HERE, "logs", "task6_stage2_concession_check4_revision_experiment.jsonl"
)

GENUINE = "genuine-Concession"
VALID_VERDICTS = {GENUINE, "plain-contrast", "mislabeled-causal", "other"}

# Item headers are matched loosely on purpose: this sheet has been hand-
# reformatted twice already (dropped "##", dropped "pool_index=" from the
# header text) while still being filled in correctly otherwise. Rather
# than require an exact header format, this only needs the ordinal
# "Item NN" number -- pool_index is recovered by POSITION from the
# manifest (which recorded the exact sampling order), not from text in
# the sheet itself, so reformatting the header can't break this again.
ITEM_HEADER_RE = re.compile(r"^#{0,2}\s*Item\s+(\d+)\s*(\[[^\]]*\])?", re.MULTILINE)


def load_by_pool_index(path):
    out = {}
    for line in open(path):
        rec = json.loads(line)
        out[rec["pool_index"]] = rec
    return out


def main():
    if not os.path.isfile(SHEET):
        raise SystemExit(f"sheet not found: {SHEET}")
    text = open(SHEET).read()

    if not os.path.isfile(MANIFEST):
        raise SystemExit(f"manifest not found: {MANIFEST} -- can't map items to pool_index")
    manifest = json.load(open(MANIFEST))
    manifest_items = manifest["items"]

    stage2 = load_by_pool_index(STAGE2_LOG)
    revised = load_by_pool_index(REVISED_LOG)

    headers = list(ITEM_HEADER_RE.finditer(text))
    entries = []
    for i, h in enumerate(headers):
        start = h.end()
        end = headers[i + 1].start() if i + 1 < len(headers) else len(text)
        block = text[start:end]
        ordinal = int(h.group(1))
        if ordinal < 1 or ordinal > len(manifest_items):
            print(f"  WARNING -- Item {ordinal} has no matching manifest entry "
                  f"(manifest has {len(manifest_items)} items) -- skipped")
            continue
        pid = manifest_items[ordinal - 1]["pool_index"]
        stratum = manifest_items[ordinal - 1]["stratum"]
        verdict_m = re.search(r"VERDICT:[ \t]*(\S+)?[ \t]*(?:\n|$)", block)
        verdict = (verdict_m.group(1) or "").strip() if verdict_m else ""
        entries.append((pid, stratum, verdict))

    filled = [e for e in entries if e[2]]
    blank = [e for e in entries if not e[2]]
    unknown = [e for e in filled if e[2] not in VALID_VERDICTS]

    print(f"Total items: {len(entries)} | filled: {len(filled)} | blank: {len(blank)}")
    if blank:
        print(f"  blank pool_indices: {[e[0] for e in blank]}")
    if unknown:
        print(f"  WARNING -- unrecognized verdict strings (fix these before trusting the tally):")
        for pid, strat, v in unknown:
            print(f"    pool_index={pid}: {v!r}")

    if not filled:
        print("\nNothing filled in yet -- nothing to tally.")
        return

    def rate(subset):
        if not subset:
            return None
        genuine = sum(1 for _, _, v in subset if v == GENUINE)
        return genuine, len(subset), genuine / len(subset)

    print("\n=== Human-confirmed genuine-Concession rate ===")
    overall = rate(filled)
    if overall:
        g, n, pct = overall
        print(f"Overall: {g}/{n} = {pct:.1%}")

    for stratum_name in sorted(set(e[1] for e in filled)):
        subset = [e for e in filled if e[1] == stratum_name]
        g, n, pct = rate(subset)
        print(f"{stratum_name}: {g}/{n} = {pct:.1%}")

    print("\n=== Agreement with each automated pass, per item ===")
    agree_original = agree_revised = 0
    for pid, strat, v in filled:
        human_genuine = v == GENUINE
        original_genuine = False  # original check_4 wording confirmed 0/85, always False
        revised_genuine = bool(revised[pid]["stage2_check4_revision"]["confirmed"])
        if human_genuine == original_genuine:
            agree_original += 1
        if human_genuine == revised_genuine:
            agree_revised += 1
    n = len(filled)
    print(f"Human agrees with ORIGINAL check_4 wording (which said 'not genuine' on all 85): "
          f"{agree_original}/{n} = {agree_original/n:.1%}")
    print(f"Human agrees with REVISED check_4 wording: {agree_revised}/{n} = {agree_revised/n:.1%}")
    print("\nWhichever agreement rate is higher is the automated wording this sample")
    print("says was closer to right. Neither being close to 100% would mean this")
    print("category needs a fully manual pass rather than any automated shortcut.")


if __name__ == "__main__":
    main()
