"""Stratified sampler for a human hand-audit of Experiment 1/2's
Condition/Concession "severed" verdicts, across all four chunkers,
proportional to each chunker's reported severed-case count.

This is a DIFFERENT, independent ground-truth check from
dangerous_failure_full_audit.json (which audited Experiment 3's repair
pool and was produced by a single dispatched agent, spot-checked by
Claude on only 6/125 cases -- not a human, not a second independent
rater). This sheet asks a human to classify Experiment 1/2's *original*
severed verdicts directly, before any repair arm touches them, since
llm_judge_paragraph_severance is the same function that gates BOTH
experiments (see the pipeline explanation already given).

Severed-CC counts (from the four govern logs, relation_type in
Condition/Concession, chunker-specific severance field preserved=False):
  propositionizer: 109/272   own_baseline: 107/272
  nuggetindex: 206/272       atomicrag: 124/272
  total: 546 -> proportional sample of 36 at seed=42.
"""

import json
import os
import random

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
OUT_MD = os.path.join(SCRIPT_DIR, "manual_exp2_condition_concession_audit.md")
OUT_MANIFEST = os.path.join(SCRIPT_DIR, "manual_exp2_condition_concession_manifest.json")

SEED = 42
TARGET_N = 36

CHUNKERS = {
    "propositionizer": {
        "log": os.path.join(SCRIPT_DIR, "logs/task7_experiment_govern_log.jsonl"),
        "severance_field": "severance_a",
        "prop_field": "condition_a_propositions",
        "label": "atomized propositions",
    },
    "own_baseline": {
        "log": os.path.join(SCRIPT_DIR, "own_baseline_track/logs/own_baseline_govern_log.jsonl"),
        "severance_field": "severance_a",
        "prop_field": "condition_a_claims",
        "label": "atomized claims",
    },
    "nuggetindex": {
        "log": os.path.join(SCRIPT_DIR, "nuggetindex_track/logs/nuggetindex_govern_log.jsonl"),
        "severance_field": "severance_nuggetindex",
        "prop_field": "nuggetindex_triples_rendered",
        "label": "rendered (subject, predicate, object) triples",
    },
    "atomicrag": {
        "log": os.path.join(SCRIPT_DIR, "atomicrag_track/logs/atomicrag_govern_log.jsonl"),
        "severance_field": "severance_atomicrag",
        "prop_field": "atomicrag_propositions",
        "label": "atomized propositions",
    },
}


def main():
    random.seed(SEED)
    severed_by_chunker = {}
    for name, cfg in CHUNKERS.items():
        recs = [json.loads(l) for l in open(cfg["log"], encoding="utf-8")]
        cc = [r for r in recs if r["relation_type"] in ("Condition", "Concession")]
        severed = [r for r in cc if (r.get(cfg["severance_field"]) or {}).get("preserved") is False]
        severed_by_chunker[name] = severed

    total_severed = sum(len(v) for v in severed_by_chunker.values())
    quotas = {}
    running = 0
    names = list(CHUNKERS.keys())
    for i, name in enumerate(names):
        if i == len(names) - 1:
            quotas[name] = TARGET_N - running
        else:
            q = round(len(severed_by_chunker[name]) / total_severed * TARGET_N)
            quotas[name] = q
            running += q

    print("Quotas:", quotas, "sum:", sum(quotas.values()))

    items = []
    for name, cfg in CHUNKERS.items():
        pool = severed_by_chunker[name]
        k = min(quotas[name], len(pool))
        sample = random.sample(pool, k)
        for r in sample:
            items.append({
                "chunker": name,
                "pool_index": r["pool_index"],
                "relation_type": r["relation_type"],
                "title": r["title"],
                "content": r["content"],
                "nucleus": r["nucleus"],
                "satellite": r["satellite"],
                "connective": r["connective"],
                "propositions": r.get(cfg["prop_field"]) or [],
                "prop_label": cfg["label"],
            })
    random.shuffle(items)

    lines = []
    lines.append("# Manual audit: Experiment 1/2 Condition/Concession \"severed\" verdicts, all four chunkers\n")
    lines.append("**This sheet is for a HUMAN reviewer. Verdicts are deliberately blank: do not fill them in with a model.**\n")
    lines.append("## Why this sheet exists\n")
    lines.append(
        "Experiment 3's dangerous_failure ground truth (already hand-audited "
        "separately, in dangerous_failure_full_audit.json) turned out to be "
        "65.6% mislabeled by the same judge function used here, "
        "`llm_judge_paragraph_severance`. That same function is also what "
        "produces Experiment 1/2's headline severed-verdict counts -- the "
        "paper's central RST claim (\"governing relations severed far more "
        "than descriptive ones\"). This sheet independently checks a "
        "stratified sample of THAT claim's own raw material, across all "
        "four chunkers, before any repair arm touches it. It is NOT the "
        "same audit as dangerous_failure_full_audit.json -- that one covered "
        "Propositionizer's Experiment 3 repair pool only, and was produced "
        "by a dispatched agent, not a human.\n"
    )
    lines.append("## Task\n")
    lines.append(
        "Each item below is a case where an automated chunker split a source "
        "paragraph into atomic units (propositions, claims, or, for "
        "NuggetIndex, subject-predicate-object triples), for a Condition or "
        "Concession relation: the NUCLEUS is asserted to hold only under/"
        "despite the SATELLITE. The chunker's own severance judge scored "
        "this case SEVERED (relationship lost). Read the source content, "
        "the nucleus, the satellite, the connective, and the full list of "
        "atomized units actually produced. Then judge, independent of the "
        "judge's verdict (not shown here): is the Condition/Concession "
        "relationship -- the specific governing/conceding link between "
        "these two specific pieces of content -- still recoverable from the "
        "atomized output, taken as a whole, in any wording, connective "
        "present or not as long as the logical relationship is evident?\n"
    )
    lines.append("Write ONE of the following on the `VERDICT:` line:\n")
    lines.append("- `severed` -- the relationship is genuinely lost: content missing, "
                  "presented as unconnected parallel facts, or actively misattached "
                  "(the marker, if any, governs different content than the real satellite).")
    lines.append("- `mislabeled_actually_correct` -- the relationship IS recoverable "
                  "from the atomized output as a whole; the judge's severed verdict was wrong.")
    lines.append("- `ambiguous` -- a genuine close call either way.\n")
    lines.append("---\n")

    manifest = []
    for i, it in enumerate(items, start=1):
        n = i
        lines.append(f"## Item {n} [{it['chunker']} / pool_index {it['pool_index']} / {it['relation_type']}]\n")
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
        manifest.append({"item": n, "chunker": it["chunker"], "pool_index": it["pool_index"],
                          "relation_type": it["relation_type"]})

    with open(OUT_MD, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    json.dump(manifest, open(OUT_MANIFEST, "w", encoding="utf-8"), indent=2)
    print(f"\nWrote {len(items)} items to {OUT_MD}")
    print(f"Manifest written to {OUT_MANIFEST}")


if __name__ == "__main__":
    main()
