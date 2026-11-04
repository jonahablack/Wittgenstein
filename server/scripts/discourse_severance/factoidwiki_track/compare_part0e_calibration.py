"""PART 0e: compare the human calibration verdicts against the CURRENT
(pre-fix) parser+NLI pipeline's output on the same 24 cases. Per
explicit instruction, this runs the pipeline as it stands right now --
neither of the two proposed fixes (aggregated multi-proposition content
check, anaphora pre-check) has been implemented yet.
"""

import json
import sys

sys.path.insert(0, ".")
from pipeline_part0d import evaluate  # noqa: E402

MANIFEST_PATH = "manual_part0e_calibration_manifest.json"

CHUNKERS = {
    "propositionizer": {"log": "logs/task7_experiment_govern_log.jsonl", "prop_field": "condition_a_propositions"},
    "own_baseline": {"log": "own_baseline_track/logs/own_baseline_govern_log.jsonl", "prop_field": "condition_a_claims"},
    "nuggetindex": {"log": "nuggetindex_track/logs/nuggetindex_govern_log.jsonl", "prop_field": "nuggetindex_triples_rendered"},
    "atomicrag": {"log": "atomicrag_track/logs/atomicrag_govern_log.jsonl", "prop_field": "atomicrag_propositions"},
}

# Human verdicts, in item order (1-24), as returned.
HUMAN_VERDICTS = [
    "preserved", "preserved", "preserved", "ambiguous", "severed", "severed", "severed",
    "preserved", "preserved", "preserved", "preserved", "ambiguous", "preserved", "ambiguous",
    "preserved", "preserved", "preserved", "preserved", "preserved", "preserved", "preserved",
    "preserved", "preserved", "severed",
]


def main():
    manifest = json.load(open(MANIFEST_PATH, encoding="utf-8"))
    recs_by_chunker = {}
    for name, cfg in CHUNKERS.items():
        recs_by_chunker[name] = {json.loads(l)["pool_index"]: json.loads(l) for l in open(cfg["log"], encoding="utf-8")}

    results = []
    for m, human in zip(manifest, HUMAN_VERDICTS):
        chunker, pool_index = m["chunker"], m["pool_index"]
        rec = recs_by_chunker[chunker][pool_index]
        propositions = rec.get(CHUNKERS[chunker]["prop_field"]) or []
        r = rec["relation_type"], rec["nucleus"], rec["satellite"], rec["connective"]
        out = evaluate(propositions, rec["nucleus"], rec["satellite"], rec["connective"], rec["relation_type"])
        pipeline_verdict = "preserved" if out["preserved"] else "severed"
        if human == "ambiguous":
            agree = None
        else:
            agree = (human == pipeline_verdict)
        results.append({
            "item": m["item"], "chunker": chunker, "pool_index": pool_index,
            "relation_type": rec["relation_type"], "human": human, "pipeline": pipeline_verdict,
            "agree": agree, "reason": out["reason"],
        })
        tag = "N/A(ambig)" if agree is None else ("AGREE" if agree else "DISAGREE")
        print(f"[{m['item']:2d}] {chunker:15s} pool={pool_index:5d} human={human:10s} "
              f"pipeline={pipeline_verdict:10s} {tag}  ({out['reason']})")

    scored = [r for r in results if r["agree"] is not None]
    n_agree = sum(r["agree"] for r in scored)
    n_ambig = sum(1 for r in results if r["agree"] is None)
    print(f"\n{n_agree}/{len(scored)} agree on non-ambiguous items "
          f"({n_ambig} human-ambiguous items excluded from that ratio)")
    disagreements = [r for r in scored if not r["agree"]]
    print(f"\nDisagreements ({len(disagreements)}):")
    for r in disagreements:
        print(f"  item {r['item']} ({r['chunker']} pool {r['pool_index']}, {r['relation_type']}): "
              f"human={r['human']} pipeline={r['pipeline']} reason={r['reason']}")

    json.dump(results, open("results/part0e_calibration_comparison_report.json", "w"), indent=2)


if __name__ == "__main__":
    main()
