"""Speed (and accuracy) of Wittgenstein's checks vs a frontier-LLM judge on the same answers.

Items: the planted-error evaluation's construction (scripts/evaluate_checks.py): a correct
restatement of an FDA label sentence, or one with exactly one planted error. Wittgenstein
is timed in-process after warm-up (as a running server would be); the judge is one
Messages API call per answer at the model's default settings (it may think first;
max_tokens leaves room for that so every call returns a verdict).

Run: WITTGENSTEIN_NLI=jev uv run --with anthropic python scripts/benchmark_vs_llm_judge.py OUT.json
(needs ANTHROPIC_API_KEY, and TYPESAFE_API_KEY for Jev; JUDGE_MODEL overrides the judge)."""

import json
import os
import re
import statistics
import sys
import time
import zlib
from pathlib import Path

sys.path.insert(0, ".")
import anthropic

from scripts.evaluate_checks import ROOT, TRANSFORMS, _clean, _flags, _restate
from wittgenstein.live.corpus import LiveCorpus
from wittgenstein.live.generate import ContextPassage

N_OK, PER_KIND = 20, 3
folder = ROOT / "data" / "fixtures" / "fda_labels" / "fda-labels"
docs = {p.stem: p.read_text() for p in sorted(folder.glob("*.md"))}
units = LiveCorpus("bench", docs).units()
pool = []
for u in units.units:
    for s, _, _ in u.sentences:
        s = _clean(s)
        if 8 <= len(s.split()) <= 60 and not s.lower().startswith(("see ", "[see", "table", "figure")):
            pool.append((u, s))
pool.sort(key=lambda t: (zlib.crc32(t[1].encode()) % 997, t[1]))
items = [(u, _restate(s), False) for u, s in pool[:N_OK]]
for fn in TRANSFORMS.values():
    k = 0
    for u, s in pool[N_OK:]:
        if k >= PER_KIND:
            break
        bad = fn(s)
        if bad and bad != s:
            items.append((u, _restate(bad), True))
            k += 1
n_bad = sum(1 for i in items if i[2])
print(f"{len(items)} items ({len(items) - n_bad} correct, {n_bad} with one planted error)")

# Wittgenstein (warm up: load spaCy etc. once, as a running server would have)
_flags(items[0][1] + " [1]", [ContextPassage(1, items[0][0])], units)
w_t, w_flag = [], []
for u, ans, _ in items:
    t = time.perf_counter()
    fl = _flags(ans + " [1]", [ContextPassage(1, u)], units)
    w_t.append(time.perf_counter() - t)
    w_flag.append(bool(fl))

# Frontier LLM judge
client = anthropic.Anthropic()
MODEL = os.environ.get("JUDGE_MODEL", "claude-opus-5-5")
c_t, c_flag, c_in, c_out, c_noverdict = [], [], 0, 0, 0
for u, ans, _ in items:
    prompt = (
        f"Source passage [1]:\n{u.text}\n\nAnswer:\n{ans} [1]\n\n"
        "Check the answer against the source passage. Does every claim in it faithfully state what the "
        "passage says (no changed numbers, units, negations, certainty, conditions, or patient groups)? "
        'Reply with JSON only: {"faithful": true|false, "problem": "<short reason or empty>"}'
    )
    t = time.perf_counter()
    r = client.messages.create(model=MODEL, max_tokens=1024, messages=[{"role": "user", "content": prompt}])
    c_t.append(time.perf_counter() - t)
    text = "".join(b.text for b in r.content if b.type == "text")
    m = re.search(r'"faithful"\s*:\s*(true|false)', text)
    c_flag.append(m is not None and m.group(1) == "false")
    c_noverdict += m is None
    c_in += r.usage.input_tokens
    c_out += r.usage.output_tokens


def acc(flags):
    fa = sum(f for f, (_, _, bad) in zip(flags, items, strict=True) if not bad)
    n_ok = sum(1 for i in items if not i[2])
    hit = sum(f for f, (_, _, bad) in zip(flags, items, strict=True) if bad)
    n_bad = len(items) - n_ok
    return {"false_alarms": f"{fa}/{n_ok}", "errors_caught": f"{hit}/{n_bad}"}


out = {
    "items": len(items),
    "judge_model": MODEL,
    "wittgenstein": {
        "median_s": statistics.median(w_t),
        "mean_s": statistics.mean(w_t),
        "total_s": sum(w_t),
        **acc(w_flag),
    },
    "frontier_judge": {
        "median_s": statistics.median(c_t),
        "mean_s": statistics.mean(c_t),
        "total_s": sum(c_t),
        "input_tokens": c_in,
        "output_tokens": c_out,
        "no_verdict": c_noverdict,
        **acc(c_flag),
    },
}
out["speedup_median"] = out["frontier_judge"]["median_s"] / out["wittgenstein"]["median_s"]
out["speedup_total"] = out["frontier_judge"]["total_s"] / out["wittgenstein"]["total_s"]
print(json.dumps(out, indent=2))
Path(sys.argv[1]).write_text(json.dumps(out, indent=2))
