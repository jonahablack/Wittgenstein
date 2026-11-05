"""Measure the answer checks with planted errors (detection rate and false alarms).

Method, deliberately simple and fully reproducible:
1. Take sentences from the FDA label sample (data/live_corpora/fda-labels) that contain
   something an error could change: a dose or other quantity, a patient group, a
   condition, a negation, or a hedge.
2. Make a correct answer from each: "According to the label, <sentence>." It is not a
   verbatim quote (so every check runs) but means exactly what the source says. Any
   flag on these is a false alarm.
3. Plant exactly one known error per answer, by type, and record which flags fire on it.

What this measures: how reliably each detector catches a *known kind* of planted
error, and how often it fires on correct answers. What it doesn't measure: how
often real LLM answers contain these errors, or errors of kinds not planted here.
Synthetic errors are cleaner than real ones, so read detection rates as upper bounds
for these error types, and false-alarm rates as computed on near-verbatim answers.

Run: uv run python scripts/evaluate_checks.py [--limit N] [--out PATH]
"""

from __future__ import annotations

import argparse
import json
import re
import time
import zlib
from collections import defaultdict
from pathlib import Path

from wittgenstein.core.enums import FlagDisposition, FlagKind
from wittgenstein.live import phrases as P
from wittgenstein.live.characterize import edit_sentence
from wittgenstein.live.corpus import LiveCorpus, Unit
from wittgenstein.live.flags import FlagCollector
from wittgenstein.live.generate import ContextPassage
from wittgenstein.live.quantities import checkable, quantities
from wittgenstein.live.text_artifacts import find_satellite
from wittgenstein.live.verify import verify_answer

ROOT = Path(__file__).resolve().parents[1]
LABELS = ROOT / "data" / "live_corpora" / "fda-labels"

ANSWER_KINDS = {
    FlagKind.ANSWER_SENTENCE_UNSUPPORTED,
    FlagKind.ANSWER_CONTRADICTS_SOURCE,
    FlagKind.QUANTITY_MISMATCH,
    FlagKind.POPULATION_QUALIFIER_DROPPED,
    FlagKind.CONDITION_SATELLITE,
    FlagKind.CONCESSION_SATELLITE,
    FlagKind.MODAL_STRENGTH_MISMATCH,
    FlagKind.RECOMMENDATION_STRENGTH_DROPPED,
}
#: Which flags count as catching each planted error.
EXPECTED = {
    "dose_changed": {FlagKind.QUANTITY_MISMATCH, FlagKind.ANSWER_CONTRADICTS_SOURCE},
    "unit_changed": {FlagKind.QUANTITY_MISMATCH},
    "population_dropped": {FlagKind.POPULATION_QUALIFIER_DROPPED},
    "condition_dropped": {FlagKind.CONDITION_SATELLITE},
    "negation_flipped": {FlagKind.ANSWER_CONTRADICTS_SOURCE, FlagKind.ANSWER_SENTENCE_UNSUPPORTED},
    "hedge_strengthened": {FlagKind.MODAL_STRENGTH_MISMATCH, FlagKind.ANSWER_CONTRADICTS_SOURCE},
    "wrong_citation": {FlagKind.ANSWER_SENTENCE_UNSUPPORTED, FlagKind.ANSWER_CONTRADICTS_SOURCE},
}
_UNIT_SWAP = {
    "mg": "mcg",
    "mcg": "mg",
    "g": "mg",
    "ml": "l",
    "l": "ml",
    "day": "week",
    "week": "day",
    "hour": "day",
}
_MODAL = re.compile(r"\b(may|might|could|can|should)\b")
_LEAD_POP = re.compile(r"^(?:In|For|Among)\b[^,]{3,90},\s*")
_INLINE_POP = re.compile(
    r"\s(?:in|for)\s+(?:pediatric|adult|elderly|geriatric|pregnant|older|premenopausal|postmenopausal|"
    r"patients\s+(?:with|aged|who))\b[^,;\[(]*?(?=[,;\[(]|\.\s|\.$|$)"
)


def _clean(sentence: str) -> str:
    s = re.sub(r"\s+", " ", sentence).strip().lstrip("•o ").strip()
    return s if s.endswith(".") else s + "."


def _restate(sentence: str) -> str:
    return "According to the label, " + sentence[0].lower() + sentence[1:]


def dose_changed(s: str) -> str | None:
    for q in quantities(s):
        if q.unit and checkable(q):
            v = q.value
            new = str(int(float(v)) * 2 + 50) if "." not in v else f"{float(v) * 2 + 0.5:g}"
            i = s.find(v, q.start)
            return s[:i] + new + s[i + len(v) :] if i >= 0 else None
    return None


def unit_changed(s: str) -> str | None:
    for q in quantities(s):
        if q.unit in _UNIT_SWAP:
            m = re.search(rf"(?<=\d)\s*{re.escape(q.text.split()[-1])}\b", s[q.start : q.end + 1])
            if not m:
                continue
            a, b = q.start + m.start(), q.start + m.end()
            return s[:a] + " " + _UNIT_SWAP[q.unit] + s[b:]
    return None


def _names_group(span: str) -> bool:
    return any(P.contains_word_prefix(P.lower(span), c) for c in P.POPULATION_CUES)


def population_dropped(s: str) -> str | None:
    """Remove the phrase naming who the statement applies to -- only when the removed
    words really name a patient group (not "In clinical trials of 29 weeks, ...")."""
    m = _LEAD_POP.match(s)
    out = s[m.end() :] if m and _names_group(m.group(0)) else None
    if out is None:
        m2 = _INLINE_POP.search(s)
        out = s[: m2.start()] + s[m2.end() :] if m2 and _names_group(m2.group(0)) else None
    if not out or len(out.split()) < 5:
        return None
    if any(P.contains_word_prefix(P.lower(out), c) for c in P.POPULATION_CUES) or not _well_formed(out):
        return None  # still names a group, or no longer a readable sentence
    return out[0].upper() + out[1:]


_BROKEN = re.compile(r"(?:^|\s)\.\d|\w\(|\(\s*$")


def _well_formed(out: str) -> bool:
    """A planted error must still be a readable sentence (no "… .73 m 2", "modified(3")."""
    return not _BROKEN.search(out)


def condition_dropped(s: str) -> str | None:
    low = P.lower(s)
    found = find_satellite(low, P.CONDITION_CONNECTIVES)
    if not found:
        return None
    conn, clause, start = found
    end = low.find(clause, start) + len(clause)
    out = (s[:start] + s[end:]).strip()
    out = re.sub(r"^[,;\s]+|\s+,", lambda m: "" if m.start() == 0 else ",", out)
    out = re.sub(r"\s{2,}", " ", out).strip(" ,")
    if len(out.split()) < 5 or not _well_formed(out):
        return None
    if find_satellite(P.lower(out), P.CONDITION_CONNECTIVES):
        return None  # another condition remains ("If A, or if B, ..."): not a clean drop
    return out[0].upper() + out[1:]


def negation_flipped(s: str) -> str | None:
    return edit_sentence(s, "negation")


def hedge_strengthened(s: str) -> str | None:
    m = _MODAL.search(s)
    return s[: m.start()] + "must" + s[m.end() :] if m else None


TRANSFORMS = {
    "dose_changed": dose_changed,
    "unit_changed": unit_changed,
    "population_dropped": population_dropped,
    "condition_dropped": condition_dropped,
    "negation_flipped": negation_flipped,
    "hedge_strengthened": hedge_strengthened,
}


def _flags(answer: str, passages: list[ContextPassage], units) -> list:  # noqa: ANN001
    out = FlagCollector("eval")
    verify_answer(answer, passages, units, out)
    return [f for f in out.flags if f.kind in ANSWER_KINDS and f.disposition == FlagDisposition.NEEDS_REVIEW]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=60, help="source sentences per error type (max)")
    ap.add_argument("--out", type=Path, default=None)
    ap.add_argument("--corpus", default="fda-labels", help="folder under data/live_corpora/")
    args = ap.parse_args()
    folder = ROOT / "data" / "live_corpora" / args.corpus
    docs = {p.stem: p.read_text() for p in sorted(folder.glob("*.md"))}
    if not docs:
        raise SystemExit("Fetch the sample first: uv run python scripts/fetch_sample_corpora.py")
    corpus = LiveCorpus(f"eval-{args.corpus}", docs)
    units = corpus.units()
    pool: list[tuple[Unit, str]] = []
    for u in units.units:
        for s, _, _ in u.sentences:
            s = _clean(s)
            if 8 <= len(s.split()) <= 60 and not s.lower().startswith(("see ", "[see", "table", "figure")):
                pool.append((u, s))
    # Deterministic, document-balanced order.
    pool.sort(key=lambda t: (zlib.crc32(t[1].encode()) % 997, t[1]))  # stable across runs

    t0 = time.time()
    counts: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    examples: dict[str, list[dict]] = defaultdict(list)
    false_alarm_kinds: dict[str, int] = defaultdict(int)
    n_base = 0
    base_flagged = 0
    for u, s in pool[: args.limit * 4]:
        base = _restate(s)
        fl = _flags(base + " [1]", [ContextPassage(1, u)], units)
        n_base += 1
        if fl:
            base_flagged += 1
            for f in fl:
                false_alarm_kinds[f.kind.value] += 1
            if len(examples["false_alarm"]) < 8:
                examples["false_alarm"].append({"source": s, "answer": base, "flags": [f.title for f in fl]})
    for name, fn in TRANSFORMS.items():
        for u, s in pool:
            if counts[name]["n"] >= args.limit:
                break
            bad = fn(s)
            if not bad or bad == s:
                continue
            fl = _flags(_restate(bad) + " [1]", [ContextPassage(1, u)], units)
            hit = bool({f.kind for f in fl} & EXPECTED[name])
            counts[name]["n"] += 1
            counts[name]["caught"] += hit
            counts[name]["flagged_any"] += bool(fl)
            if not hit and len(examples[f"missed_{name}"]) < 5:
                examples[f"missed_{name}"].append({"source": s, "planted": bad, "flags": [f.title for f in fl]})
    # Wrong citation: the sentence is cited to a passage from a *different* document.
    other = {d: [u for u in units.units if u.document_id != d] for d in docs}
    for i, (u, s) in enumerate(pool[: args.limit]):
        wrong = other[u.document_id][(i * 37) % len(other[u.document_id])]
        fl = _flags(_restate(s) + " [1]", [ContextPassage(1, wrong)], units)
        hit = bool({f.kind for f in fl} & EXPECTED["wrong_citation"])
        counts["wrong_citation"]["n"] += 1
        counts["wrong_citation"]["caught"] += hit
        counts["wrong_citation"]["flagged_any"] += bool(fl)
        if not hit and len(examples["missed_wrong_citation"]) < 5:
            examples["missed_wrong_citation"].append({"source": s, "cited": wrong.text[:160]})

    result = {
        "corpus": args.corpus,
        "correct_answers": n_base,
        "correct_answers_flagged": base_flagged,
        "false_alarm_rate": round(base_flagged / n_base, 3) if n_base else None,
        "false_alarms_by_kind": dict(false_alarm_kinds),
        "detection": {
            k: {
                "n": v["n"],
                "caught_by_intended_check": v["caught"],
                "rate": round(v["caught"] / v["n"], 3) if v["n"] else None,
                "flagged_by_any_check": v["flagged_any"],
                "any_rate": round(v["flagged_any"] / v["n"], 3) if v["n"] else None,
            }
            for k, v in counts.items()
        },
        "examples": dict(examples),
        "seconds": round(time.time() - t0, 1),
    }
    print(json.dumps({k: v for k, v in result.items() if k != "examples"}, indent=2))
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(result, indent=2))
        print(f"wrote {args.out}")


if __name__ == "__main__":
    main()
