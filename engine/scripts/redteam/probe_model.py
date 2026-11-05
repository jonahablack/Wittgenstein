"""Counterfactual probe over recorded model answers: for each answer that takes a value
from its passages, change that value in the passages and ask the same model again
(live/counterfactual.py). Measures how often the generator follows its context.

Input: a JSONL written by run_model.py. Needs the same model server it was made with.

Run:
  WITTGENSTEIN_LOCAL_LLM_URL=http://127.0.0.1:8200/v1 \\
    uv run python scripts/redteam/probe_model.py --answers ../research/red-team/<date>/dev_v3.jsonl \\
    --out ../research/red-team/<date>/probes.json
"""

from __future__ import annotations

import argparse
import collections
import dataclasses
import json
from pathlib import Path

from run_model import load_corpus

from wittgenstein.live import counterfactual
from wittgenstein.live.generate import ContextPassage
from wittgenstein.live.providers.local_provider import LocalProvider


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--answers", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()
    units = load_corpus().units()
    provider = LocalProvider()
    rows = []
    counts: collections.Counter[str] = collections.Counter()
    for line in args.answers.read_text().splitlines():
        r = json.loads(line)
        by_n = {c["n"]: units.by_id[c["unit_id"]] for c in r["context"] if c["unit_id"] in units.by_id}
        passages = [(n, u.text) for n, u in sorted(by_n.items())]

        def regenerate(question: str, edited: list[tuple[int, str]], by_n=by_n) -> str:  # noqa: ANN001
            ps = [ContextPassage(n, dataclasses.replace(by_n[n], text=t)) for n, t in edited]
            return "".join(provider.stream(question, ps))

        results = counterfactual.run_probes(r["q"], passages, r["answer"], regenerate)
        for x in results:
            counts[x.outcome] += 1
            rows.append(
                {
                    "q": r["q"],
                    "answer": r["answer"],
                    "value": x.original_text,
                    "replaced_with": x.replacement_text,
                    "outcome": x.outcome,
                    "new_answer": x.new_answer,
                    "detail": x.detail,
                }
            )
        if results:
            print(f"{r['q'][:60]:60s} {[x.outcome for x in results]}", flush=True)
    summary = {"probes": sum(counts.values()), "outcomes": dict(counts)}
    print(json.dumps(summary, indent=2))
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps({"summary": summary, "probes": rows}, indent=2))


if __name__ == "__main__":
    main()
