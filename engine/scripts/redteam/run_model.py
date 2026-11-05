"""Run real model answers through the live pipelines and record what the checks say.

Every question in questions.json is asked over all six FDA labels at once (a realistic
multi-document knowledge base, where answers can mix up drugs), through one or more
pipelines, with a real language model (the `local` provider by default: an open-weights
model behind an OpenAI-compatible server; see live/providers/local_provider.py).

Output: one JSON record per (question, pipeline) with the packed context, the answer,
per-sentence support and every flag -- the input for annotation (annotate.md) and for
scoring (score.py). Outputs hold document text and belong outside the repo.

Run:
  WITTGENSTEIN_LOCAL_LLM_URL=http://127.0.0.1:8200/v1 \\
    uv run python scripts/redteam/run_model.py --out ../research/red-team/<date>/answers.jsonl
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

from wittgenstein.live.corpus import LiveCorpus
from wittgenstein.live.runner import run_query

ROOT = Path(__file__).resolve().parents[2]
CORPORA = ["fda-labels", "fda-labels-heldout"]


def load_corpus() -> LiveCorpus:
    docs: dict[str, str] = {}
    for c in CORPORA:
        for p in sorted((ROOT / "data" / "live_corpora" / c).glob("*.md")):
            docs[p.stem] = p.read_text()
    if len(docs) < 6:
        raise SystemExit("Fetch the labels first: uv run python scripts/fetch_sample_corpora.py")
    return LiveCorpus("fda-six", docs)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--provider", default="local")
    ap.add_argument("--pipelines", default="aware,semantic-top5")
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--questions", type=Path, default=Path(__file__).with_name("questions.json"))
    args = ap.parse_args()
    qs = json.loads(args.questions.read_text())["questions"][: args.limit]
    corpus = load_corpus()
    units = corpus.units()
    args.out.parent.mkdir(parents=True, exist_ok=True)
    done = set()
    if args.out.exists():  # resume
        for line in args.out.read_text().splitlines():
            r = json.loads(line)
            done.add((r["q"], r["pipeline"]))
    with args.out.open("a") as fh:
        for i, item in enumerate(qs):
            pipes = [p for p in args.pipelines.split(",") if (item["q"], p) not in done]
            if not pipes:
                continue
            t0 = time.time()
            res = run_query(corpus, item["q"], pipes, provider=args.provider)
            for pid, o in res.outcomes.items():
                packed = o.trace.get("packed_context_items") or []
                rec = {
                    "q": item["q"],
                    "kind": item["kind"],
                    "pipeline": pid,
                    "provider": o.provider,
                    "answer": o.answer,
                    "context": [
                        {
                            "n": j + 1,
                            "unit_id": it["item_id"],
                            "document": it.get("source_document_id"),
                            "text": units.by_id[it["item_id"]].text if it["item_id"] in units.by_id else "",
                        }
                        for j, it in enumerate(packed)
                    ],
                    "sentences": o.sentences,
                    "flags": [
                        {
                            k: f.get(k)
                            for k in ("flag_id", "kind", "title", "disposition", "severity", "stage", "metrics")
                        }
                        for f in o.flags
                    ],
                }
                fh.write(json.dumps(rec, default=str) + "\n")
            fh.flush()
            print(f"[{i + 1}/{len(qs)}] {time.time() - t0:5.1f}s  {item['q'][:70]}", flush=True)


if __name__ == "__main__":
    main()
