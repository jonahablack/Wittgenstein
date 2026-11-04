"""PART 0e: human calibration sample.

Draws 24 NEW Condition/Concession cases from the general Experiment 1/2
pool (BOTH severed and preserved verdicts this time, not severed-only),
stratified across all four chunkers, excluding every case already used
as a hard/validation case elsewhere in this project (the pool 2004,
2272, 3278, 4200, 4117 hard cases, and all 36 pool_indices already used
in manual_exp2_condition_concession_audit.md) to avoid circularity.

This is a sanity CALIBRATION sample, not a ground-truth source: the
parser+NLI pipeline's own output remains the definition of ground truth
per the user's explicit framing. Verdicts are left blank for a human
reviewer; pipeline output is not shown.
"""

import json
import os
import random

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
OUT_MD = os.path.join(SCRIPT_DIR, "manual_part0e_calibration_audit.md")
OUT_MANIFEST = os.path.join(SCRIPT_DIR, "manual_part0e_calibration_manifest.json")

SEED = 43  # different seed from the earlier 36-item sheet, deliberately
TARGET_N = 24

EXCLUDE_POOL_INDICES = {2004, 2272, 3278, 4200, 4117}

CHUNKERS = {
    "propositionizer": {"log": os.path.join(SCRIPT_DIR, "logs/task7_experiment_govern_log.jsonl"),
                         "severance_field": "severance_a", "prop_field": "condition_a_propositions",
                         "label": "atomized propositions"},
    "own_baseline": {"log": os.path.join(SCRIPT_DIR, "own_baseline_track/logs/own_baseline_govern_log.jsonl"),
                      "severance_field": "severance_a", "prop_field": "condition_a_claims",
                      "label": "atomized claims"},
    "nuggetindex": {"log": os.path.join(SCRIPT_DIR, "nuggetindex_track/logs/nuggetindex_govern_log.jsonl"),
                     "severance_field": "severance_nuggetindex", "prop_field": "nuggetindex_triples_rendered",
                     "label": "rendered (subject, predicate, object) triples"},
    "atomicrag": {"log": os.path.join(SCRIPT_DIR, "atomicrag_track/logs/atomicrag_govern_log.jsonl"),
                  "severance_field": "severance_atomicrag", "prop_field": "atomicrag_propositions",
                  "label": "atomized propositions"},
}


def main():
    random.seed(SEED)

    already_used = set(EXCLUDE_POOL_INDICES)
    prior_manifest_path = os.path.join(SCRIPT_DIR, "manual_exp2_condition_concession_manifest.json")
    if os.path.exists(prior_manifest_path):
        prior = json.load(open(prior_manifest_path, encoding="utf-8"))
        already_used |= {m["pool_index"] for m in prior}
    print(f"Excluding {len(already_used)} already-used pool_indices")

    pools = {}
    for name, cfg in CHUNKERS.items():
        recs = [json.loads(l) for l in open(cfg["log"], encoding="utf-8")]
        cc = [r for r in recs if r["relation_type"] in ("Condition", "Concession")
              and r["pool_index"] not in already_used]
        pools[name] = cc

    per_chunker = TARGET_N // len(CHUNKERS)
    items = []
    for name, cfg in CHUNKERS.items():
        sample = random.sample(pools[name], min(per_chunker, len(pools[name])))
        for r in sample:
            items.append({
                "chunker": name, "pool_index": r["pool_index"], "relation_type": r["relation_type"],
                "title": r["title"], "content": r["content"], "nucleus": r["nucleus"],
                "satellite": r["satellite"], "connective": r["connective"],
                "propositions": r.get(cfg["prop_field"]) or [], "prop_label": cfg["label"],
            })
    random.shuffle(items)

    lines = [
        "# Manual calibration sample: Part 0e (parser+NLI pipeline sanity check)\n",
        "**This sheet is for a HUMAN reviewer. Verdicts are deliberately blank. No pipeline or judge output is shown.**\n",
        "## Why this sheet exists\n",
        "This is a sanity CALIBRATION sample for the new parser+NLI ground-truth "
        "pipeline (Part 0), not a ground-truth source itself -- the pipeline's own "
        "output remains the definition of ground truth regardless of this "
        "result, per the explicit scoping decision. If agreement here is very "
        "low, that signals the pipeline needs revision before being trusted at "
        "scale. Drawn from the general Experiment 1/2 pool (both severed AND "
        "preserved verdicts, not severed-only), stratified across all four "
        "chunkers, excluding every pool_index already used as a hard case or "
        "in the earlier 36-item audit, to avoid circularity.\n",
        "## Task\n",
        "Each item is a Condition or Concession relation and the chunker's "
        "actual atomized output. Judge, independent of any prior verdict "
        "(none shown): is the relationship recoverable from the atomized "
        "output taken as a whole?\n",
        "Write ONE of: `preserved` / `severed` / `ambiguous` on the VERDICT line.\n",
        "---\n",
    ]
    manifest = []
    for i, it in enumerate(items, start=1):
        lines.append(f"## Item {i} [{it['chunker']} / pool_index {it['pool_index']} / {it['relation_type']}]\n")
        lines.append(f"**Title:** {it['title']}\n")
        lines.append(f"**Source paragraph:** {it['content']}\n")
        lines.append(f"**Nucleus:** {it['nucleus']!r}\n")
        lines.append(f"**Satellite:** {it['satellite']!r}\n")
        lines.append(f"**Connective:** {it['connective']!r}\n")
        lines.append(f"**{it['prop_label'].capitalize()} actually produced:**")
        for p in it["propositions"]:
            lines.append(f"  - {p}")
        lines.append("")
        lines.append("VERDICT: ")
        lines.append("NOTES: ")
        lines.append("")
        manifest.append({"item": i, "chunker": it["chunker"], "pool_index": it["pool_index"],
                          "relation_type": it["relation_type"]})

    with open(OUT_MD, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    json.dump(manifest, open(OUT_MANIFEST, "w", encoding="utf-8"), indent=2)
    print(f"Wrote {len(items)} items to {OUT_MD}")


if __name__ == "__main__":
    main()
