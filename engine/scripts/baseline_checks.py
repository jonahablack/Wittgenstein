"""How often do the usual "is this answer grounded?" signals miss real errors?

The motivating experiment for the project. A RAG pipeline that wants a safety net usually
reaches for one of three signals. Each is computed here on the same answers the checker
is evaluated on:

1. **Has a citation**: the answer points at a passage. Many products treat this as
   the reassurance ("sources shown").
2. **Embedding similarity**: cosine similarity between the answer and the cited passage
   (the common "groundedness" or "context relevance" score). The threshold is set so
   5% of correct answers are flagged, then detection is read off at that threshold.
3. **NLI entailment judge**: a natural-language-inference model asks whether the passage
   entails the answer, and anything under 0.5 is flagged. This is the idea behind most
   automatic "faithfulness" metrics. Same model the checker uses as one signal among
   many (cross-encoder/nli-deberta-v3-xsmall).

On two sets:
- **Planted errors** on the held-out FDA labels (scripts/evaluate_checks.py), one known
  error per answer, 240 correct answers as controls.
- **A real model's answers**: the 40 held-out questions answered by Qwen2-1.5B in the
  red-team run, labelled correct / content error / no answer / wrong citation
  (research/red-team/2026-11-05_local-qwen/heldout_labels.json; Claude's labels).

Run (writes JSON next to the red-team results, which stay local):
  uv run python scripts/baseline_checks.py \\
    --real ../research/red-team/2026-11-05_local-qwen \\
    --out ../research/red-team/2026-11-05_baselines.json
"""

from __future__ import annotations

import argparse
import json
import re
import time
import zlib
from pathlib import Path
from typing import Any

import numpy as np

from evaluate_checks import EXPECTED, ROOT, TRANSFORMS, _clean, _flags, _restate
from wittgenstein.live import nli
from wittgenstein.live.corpus import LiveCorpus
from wittgenstein.live.embedding import get_embedder
from wittgenstein.live.generate import ContextPassage

_CITE = re.compile(r"\[\d+\]")
#: Stripped before judging, as the checker does: the premise never says "according to".
_ATTRIBUTION = re.compile(r"^According to the label,\s*", re.IGNORECASE)
_SENT = re.compile(r"(?<=[.!?])\s+(?=[A-Z])")
NLI_THRESHOLD = 0.5
TARGET_FALSE_ALARM = 0.05


def _entail(passage: str, answer: str) -> float:
    """Best entailment of the answer by the passage or any of its sentences."""
    answer = _ATTRIBUTION.sub("", _CITE.sub("", answer)).strip()
    if answer:
        answer = answer[0].upper() + answer[1:]
    if not answer:
        return 1.0  # nothing is claimed, so nothing is unentailed: the judge passes it
    premises = [passage] + [s for s in _SENT.split(passage) if len(s.split()) >= 4]
    v = nli.best_entailment(premises, answer)
    return v.entailment if v else float("nan")


def _sentences_entailed(passage: str, answer: str) -> float:
    """The weakest sentence's entailment (a faithfulness judge scores each claim)."""
    parts = [s for s in _SENT.split(_CITE.sub("", answer).strip()) if s.strip()]
    if not parts:
        return 1.0
    return min(_entail(passage, s) for s in parts)


def planted(limit: int) -> dict:
    folder = ROOT / "data" / "live_corpora" / "fda-labels-heldout"
    docs = {p.stem: p.read_text() for p in sorted(folder.glob("*.md"))}
    corpus = LiveCorpus("baseline-heldout", docs)
    units = corpus.units()
    emb = get_embedder()
    pool = []
    for u in units.units:
        for s, _, _ in u.sentences:
            s = _clean(s)
            if 8 <= len(s.split()) <= 60 and not s.lower().startswith(("see ", "[see", "table", "figure")):
                pool.append((u, s))
    pool.sort(key=lambda t: (zlib.crc32(t[1].encode()) % 997, t[1]))

    items: list[dict] = []  # {type, answer, passage, wittgenstein}
    for u, s in pool[: limit * 4]:
        a = _restate(s)
        items.append({"type": "correct", "answer": a, "passage": u.text, "unit": u})
    for name, fn in TRANSFORMS.items():
        n = 0
        for u, s in pool:
            if n >= limit:
                break
            bad = fn(s)
            if not bad or bad == s:
                continue
            items.append({"type": name, "answer": _restate(bad), "passage": u.text, "unit": u})
            n += 1
    other = {d: [u for u in units.units if u.document_id != d] for d in docs}
    for i, (u, s) in enumerate(pool[:limit]):
        wrong = other[u.document_id][(i * 37) % len(other[u.document_id])]
        items.append({"type": "wrong_citation", "answer": _restate(s), "passage": wrong.text, "unit": wrong})

    vecs_a = emb.embed([x["answer"] for x in items])
    vecs_p = emb.embed([x["passage"] for x in items])
    for x, va, vp in zip(items, vecs_a, vecs_p, strict=True):
        x["similarity"] = float(va @ vp)
        x["entailment"] = _entail(x["passage"], x["answer"])
        fl = _flags(x["answer"] + " [1]", [ContextPassage(1, x["unit"])], units)
        x["wittgenstein"] = bool(fl)
        x["wittgenstein_intended"] = x["type"] != "correct" and bool({f.kind for f in fl} & EXPECTED[x["type"]])

    correct = [x for x in items if x["type"] == "correct"]
    sim_t = float(np.quantile([x["similarity"] for x in correct], TARGET_FALSE_ALARM))
    nli_t = float(np.quantile([x["entailment"] for x in correct], TARGET_FALSE_ALARM))
    by_type: dict[str, dict] = {}
    for t in ["correct", *TRANSFORMS, "wrong_citation"]:
        xs = [x for x in items if x["type"] == t]
        by_type[t] = {
            "n": len(xs),
            "has_citation": 1.0,  # every answer cites its passage
            "similarity_flagged": _rate(xs, lambda x: x["similarity"] < sim_t),
            "nli_flagged": _rate(xs, lambda x: x["entailment"] < NLI_THRESHOLD),
            "nli_calibrated_flagged": _rate(xs, lambda x: x["entailment"] < nli_t),
            "wittgenstein_flagged": _rate(xs, lambda x: x["wittgenstein"]),
            "similarity_mean": round(float(np.mean([x["similarity"] for x in xs])), 3),
            "entailment_median": round(float(np.median([x["entailment"] for x in xs])), 3),
        }
    errors = [x for x in items if x["type"] != "correct"]
    return {
        "corpus": "fda-labels-heldout",
        "embedder": emb.info.model_identifier,
        "nli_model": nli.REPO,
        "similarity_threshold": round(sim_t, 3),
        "nli_calibrated_threshold": round(nli_t, 4),
        "by_type": by_type,
        "all_errors": {
            "n": len(errors),
            "similarity_flagged": _rate(errors, lambda x: x["similarity"] < sim_t),
            "nli_flagged": _rate(errors, lambda x: x["entailment"] < NLI_THRESHOLD),
            "nli_calibrated_flagged": _rate(errors, lambda x: x["entailment"] < nli_t),
            "wittgenstein_flagged": _rate(errors, lambda x: x["wittgenstein"]),
        },
        # For the distribution chart: (type, similarity, entailment) per answer.
        "points": [
            {"type": x["type"], "similarity": round(x["similarity"], 3), "entailment": round(x["entailment"], 3)}
            for x in items
        ],
    }


def real(folder: Path) -> dict:
    labels = {r["q"]: r for r in json.loads((folder / "heldout_labels.json").read_text())["rows"]}
    emb = get_embedder()
    rows = []
    for line in (folder / "heldout_v3.jsonl").read_text().splitlines():
        r = json.loads(line)
        lab = labels.get(r["q"])
        if lab is None:
            continue
        by_n = {c["n"]: c["text"] for c in r["context"]}
        cited = [int(n) for n in re.findall(r"\[(\d+)\]", r["answer"])]
        passage = " ".join(by_n[n] for n in cited if n in by_n) or " ".join(by_n.values())
        rows.append(
            {
                "id": lab["id"],
                "label": lab["label"],
                "answer": r["answer"],
                "has_citation": bool(cited),
                "text": _CITE.sub("", r["answer"]).strip(),
                "passage": passage,
                "wittgenstein": lab["flagged_content"] or (lab["label"] in {"Z", "X"} and lab["flagged"]),
                "wittgenstein_any": lab["flagged"],
            }
        )
    texts = [x["text"] or "(empty)" for x in rows]
    va = emb.embed(texts)
    vp = emb.embed([x["passage"] for x in rows])
    for x, a, p in zip(rows, va, vp, strict=True):
        x["similarity"] = float(a @ p) if x["text"] else 1.0  # an empty answer has nothing to be dissimilar
        x["entailment"] = _sentences_entailed(x["passage"], x["answer"])
    # Same similarity threshold rule as the planted set, on this set's correct answers.
    correct = [x for x in rows if x["label"] == "C"]
    sim_t = float(np.quantile([x["similarity"] for x in correct], TARGET_FALSE_ALARM))
    groups = {"correct": ["C"], "content_error": ["E"], "no_answer": ["Z"], "wrong_citation": ["X"]}
    out = {}
    for g, labs in groups.items():
        xs = [x for x in rows if x["label"] in labs]
        out[g] = {
            "n": len(xs),
            "has_citation": _rate(xs, lambda x: x["has_citation"]),
            "similarity_flagged": _rate(xs, lambda x: x["similarity"] < sim_t),
            "nli_flagged": _rate(xs, lambda x: x["entailment"] < NLI_THRESHOLD),
            "wittgenstein_flagged": _rate(xs, lambda x: x["wittgenstein"]),
        }
    bad = [x for x in rows if x["label"] != "C"]
    return {
        "model": "Qwen/Qwen2-1.5B-Instruct",
        "labeler": "Claude (model), against the label text; not clinician-reviewed",
        "similarity_threshold": round(sim_t, 3),
        "groups": out,
        "problem_answers": {
            "n": len(bad),
            "share_of_all": round(len(bad) / len(rows), 3),
            "with_a_citation": _rate(bad, lambda x: x["has_citation"]),
        },
        "rows": [
            {k: (round(v, 3) if isinstance(v, float) else v) for k, v in x.items() if k not in {"passage", "text"}}
            for x in rows
        ],
        "note": "Wittgenstein column is the code as it ran on these answers (before H29 was fixed).",
    }


def _rate(xs: list[dict], pred) -> dict:  # noqa: ANN001
    k = sum(1 for x in xs if pred(x))
    return {"k": k, "rate": round(k / len(xs), 3) if xs else None}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=60)
    ap.add_argument("--real", type=Path, required=True, help="folder with heldout_v3.jsonl + heldout_labels.json")
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()
    t0 = time.time()
    result: dict[str, Any] = {"planted": planted(args.limit), "real_model": real(args.real)}
    result["seconds"] = round(time.time() - t0, 1)
    show = {
        "planted": {k: v for k, v in result["planted"].items() if k != "points"},
        "real_model": {k: v for k, v in result["real_model"].items() if k != "rows"},
    }
    print(json.dumps(show, indent=2))
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2))
    print(f"wrote {args.out}")


if __name__ == "__main__":
    main()
