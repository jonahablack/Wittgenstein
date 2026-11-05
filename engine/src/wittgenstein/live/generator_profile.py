"""How much context the answer-writing model actually uses well, measured.

A model's context window says how much text it *accepts*, not how much it *uses*. Small
models in particular get worse as passages are added: a passage about "Class R" next to
the one about "Class S" is enough for a 1.5B model to answer from the wrong one (seen
on the Asteria manual: the self-aware pipeline gave the model 12 passages and the
answer took its second half from an irrelevant one; plain keyword search, with 5, was
right). So the pipeline's own generator is measured, not assumed:

- **Probe set.** Fictional facts (nothing a model can know from training), each asked
  about one entity among near-identical ones: the same sentence with another class,
  port or term and a different value. The decoys are the hard part, as in real
  documents.
- **Sizes.** Each question is asked with 1 passage (the answer alone), then 3, 6 and 12
  (the answer among decoys, at a varying position).
- **Two-part questions** too ("...and how often must a northern substation be
  inspected?"), each part with its own decoys: the shape of the Asteria failure.
- **Grading.** Deterministic, by value and citation; no model judges the model. Each
  answer is *correct* (every target value, no decoy value), *wrong passage* (a decoy's
  value, or only citations and none to a target passage), or *no answer*.
- **Result.** Per size: accuracy and the wrong-passage rate. The *reliable size* is the
  most passages at which neither has got worse than with the fewest passages by more
  than the tolerance (and no smaller size has either).
- **Audit.** Every prompt size, passage list, raw answer and grade is saved in the
  profile (~/.wittgenstein/models/<provider>__<model>.json), with the date and the
  exact rule used.

The runner then flags any run that gives this model more passages than its reliable
size, and the self-aware pipeline trims to that size (live/runner.py). Measuring costs
len(PROBES) x len(SIZES) generations, so it only runs when asked.
"""

from __future__ import annotations

import json
import re
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

SIZES = (2, 4, 8, 12)
TOLERANCE = 0.15
RULE = (
    "reliable size = the largest number of passages at which, and at every smaller size, accuracy is at most "
    f"{TOLERANCE:.0%} below and the wrong-passage rate at most {TOLERANCE:.0%} above their values at the "
    "smallest size"
)

#: (template, question template, unit, [(entity, value), ...]); the first `PER_FAMILY`
#: entities are asked about, every entity serves as a decoy for the others.
_FAMILIES: list[tuple[str, str, str, list[tuple[str, str]]]] = [
    (
        "A Class {e} survey drone shall maintain a minimum altitude of {v} metres when operating over "
        "populated areas.",
        "What minimum altitude must a Class {e} survey drone maintain over populated areas?",
        "metres",
        [("K", "140"), ("L", "95"), ("M", "210"), ("N", "65"), ("P", "180"), ("Q", "120"), ("T", "75"),
         ("V", "160"), ("W", "230"), ("X", "55"), ("Y", "190"), ("Z", "110")],
    ),
    (
        "Under the Verlan Harbour Code, vessels in berthing category {e} pay a mooring fee of {v} credits per "
        "day.",
        "Under the Verlan Harbour Code, what daily mooring fee do vessels in berthing category {e} pay?",
        "credits",
        [("Amber", "340"), ("Basalt", "215"), ("Cobalt", "480"), ("Dune", "125"), ("Ember", "390"),
         ("Fjord", "265"), ("Garnet", "150"), ("Heron", "520"), ("Indigo", "305"), ("Jasper", "175"),
         ("Kestrel", "445"), ("Larch", "235")],
    ),
    (
        "In the Orsk grid regulations, each {e} substation must be inspected at least every {v} days.",
        "Under the Orsk grid regulations, how often must each {e} substation be inspected?",
        "days",
        [("northern", "45"), ("southern", "30"), ("coastal", "21"), ("alpine", "60"), ("urban", "14"),
         ("rural", "90"), ("offshore", "7"), ("desert", "40"), ("river", "35"), ("valley", "50"),
         ("island", "28"), ("border", "75")],
    ),
]  # fmt: skip
PER_FAMILY = 3


@dataclass
class ProbeRecord:
    probe: str
    size: int
    target_position: int
    passages: list[str]
    question: str
    expected: str
    answer: str
    outcome: str  # correct | wrong_passage | no_answer
    detail: str = ""


@dataclass
class GeneratorProfile:
    provider: str
    model: str
    measured_at: str
    sizes: list[int]
    accuracy: dict[str, float]  # str(size) -> share correct
    wrong_passage: dict[str, float]  # str(size) -> share that answered from a decoy
    no_answer: dict[str, float]
    n_probes: int
    reliable_passages: int
    rule: str = RULE
    note: str = ""
    seconds: float = 0.0
    records: list[ProbeRecord] = field(default_factory=list)

    def summary(self) -> str:
        acc = ", ".join(f"{round(self.accuracy[str(s)] * 100)}% with {s}" for s in self.sizes)
        wrong = ", ".join(f"{round(self.wrong_passage[str(s)] * 100)}%" for s in self.sizes)
        return (
            f"correct {acc}; answered from the wrong passage {wrong} "
            f"({self.n_probes} probes per size; measured {self.measured_at[:10]})"
        )


Generate = Callable[[str, list[str]], str]


@dataclass(frozen=True)
class _Part:
    family: int
    target: int  # entity index


def probes() -> list[tuple[str, list[_Part]]]:
    """(name, parts): single questions, then two-part questions across families."""
    single = [
        (f"f{f + 1}-{_FAMILIES[f][3][i][0]}", [_Part(f, i)])
        for f in range(len(_FAMILIES))
        for i in range(PER_FAMILY)
    ]
    pairs = [
        ("pair-1", [_Part(0, 3), _Part(2, 3)]),
        ("pair-2", [_Part(1, 3), _Part(0, 4)]),
        ("pair-3", [_Part(2, 4), _Part(1, 4)]),
        ("pair-4", [_Part(0, 5), _Part(1, 5)]),
        ("pair-5", [_Part(1, 6), _Part(2, 5)]),
        ("pair-6", [_Part(2, 6), _Part(0, 6)]),
    ]
    return single + pairs


def _has_value(answer: str, value: str) -> bool:
    return re.search(rf"(?<![\d.,]){re.escape(value)}(?![\d])", answer.replace(",", "")) is not None


def _question(parts: list[_Part]) -> str:
    qs = [_FAMILIES[p.family][1].format(e=_FAMILIES[p.family][3][p.target][0]) for p in parts]
    if len(qs) == 1:
        return qs[0]
    second = qs[1][0].lower() + qs[1][1:]
    return qs[0].rstrip("?") + ", and " + second


def build(parts: list[_Part], n: int, seed: int) -> tuple[list[str], list[int], list[str], list[str]]:
    """n passages: the targets plus decoys from the same families, interleaved; the
    targets' positions vary with `seed`. Returns (texts, target positions (1-based),
    target values, decoy values)."""
    targets = [
        (_FAMILIES[p.family][0].format(e=e, v=v), v) for p in parts for e, v in [_FAMILIES[p.family][3][p.target]]
    ]
    pools = [[(j, e, v) for j, (e, v) in enumerate(_FAMILIES[p.family][3]) if j != p.target] for p in parts]
    decoys: list[tuple[str, str]] = []
    i = 0
    while len(decoys) < max(0, n - len(parts)):
        pool = pools[i % len(pools)]
        k = i // len(pools)
        if k < len(pool):
            _, e, v = pool[k]
            decoys.append((_FAMILIES[parts[i % len(pools)].family][0].format(e=e, v=v), v))
        i += 1
        if i > 100:
            break
    texts = [t for t, _ in decoys]
    positions: list[int] = []
    for ti, (t, _) in enumerate(targets):
        pos = (seed * 7 + ti * 3 + n) % (len(texts) + 1)
        texts.insert(pos, t)
        positions = [p + 1 if p >= pos else p for p in positions]
        positions.append(pos)
    return texts, [p + 1 for p in positions], [v for _, v in targets], [v for _, v in decoys]


def grade(answer: str, positions: list[int], values: list[str], decoy_values: list[str]) -> tuple[str, str]:
    decoy = next((v for v in decoy_values if _has_value(answer, v)), None)
    if decoy is not None:
        return "wrong_passage", f"gave {decoy}, a decoy's value"
    if all(_has_value(answer, v) for v in values):
        return "correct", ""
    cited = {int(c) for c in re.findall(r"\[(\d{1,2})\]", answer)}
    if cited and not (cited & set(positions)) and not any(_has_value(answer, v) for v in values):
        return "wrong_passage", f"cited {sorted(cited)}; the answer is in {positions}"
    return "no_answer", "no value given" if not any(
        _has_value(answer, v) for v in values
    ) else "only part answered"


def measure(generate: Generate, provider: str, model: str, sizes: tuple[int, ...] = SIZES) -> GeneratorProfile:
    t0 = time.time()
    records: list[ProbeRecord] = []
    plist = probes()
    for pi, (name, parts) in enumerate(plist):
        question = _question(parts)
        for n in sizes:
            n = max(n, len(parts))
            texts, positions, values, decoy_values = build(parts, n, pi)
            try:
                answer = generate(question, texts)
            except Exception as e:  # noqa: BLE001 -- a failed generation counts as no answer, and is recorded
                answer = f"[error: {type(e).__name__}: {e}]"
            outcome, detail = grade(answer, positions, values, decoy_values)
            records.append(
                ProbeRecord(
                    name, n, positions[0], texts, question, " and ".join(values), answer[:600], outcome, detail
                )
            )

    def share(n: int, outcome: str) -> float:
        rs = [r for r in records if r.size == n]
        return round(sum(r.outcome == outcome for r in rs) / len(rs), 3) if rs else 0.0

    accuracy = {str(n): share(n, "correct") for n in sizes}
    wrong = {str(n): share(n, "wrong_passage") for n in sizes}
    none = {str(n): share(n, "no_answer") for n in sizes}
    base_acc, base_wrong = accuracy[str(sizes[0])], wrong[str(sizes[0])]
    reliable = sizes[0]
    for n in sizes:
        if accuracy[str(n)] >= base_acc - TOLERANCE - 1e-9 and wrong[str(n)] <= base_wrong + TOLERANCE + 1e-9:
            reliable = n
        else:
            break
    note = ""
    if base_acc < 0.5:
        note = (
            f"Even with {sizes[0]} passages this model answered only {base_acc:.0%} of probes correctly "
            f"({none[str(sizes[0])]:.0%} gave no answer); its reliable size is a lower bound."
        )
    return GeneratorProfile(
        provider=provider,
        model=model,
        measured_at=datetime.now(UTC).isoformat(timespec="seconds"),
        sizes=list(sizes),
        accuracy=accuracy,
        wrong_passage=wrong,
        no_answer=none,
        n_probes=len(plist),
        reliable_passages=reliable,
        note=note,
        seconds=round(time.time() - t0, 1),
        records=records,
    )


def with_provider(provider: Any) -> Generate:
    """A Generate that asks a live provider exactly as the pipeline does (same system
    prompt, same numbered-passage format), so the measurement is of the real setup."""
    from wittgenstein.live.corpus import Unit
    from wittgenstein.live.generate import ContextPassage

    def gen(question: str, texts: list[str]) -> str:
        units = [
            Unit(f"probe-{i}", i, "probe", t, 0, len(t), "", None, [], len(t.split()), 0.0)
            for i, t in enumerate(texts)
        ]
        return "".join(provider.stream(question, [ContextPassage(i + 1, u) for i, u in enumerate(units)]))

    return gen


# --------------------------------------------------------------------------- storage
def _dir() -> Path:
    from wittgenstein.service import home

    d = home() / "models"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _slug(provider: str, model: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "_", f"{provider}__{model}").strip("_")[:180]


def save(profile: GeneratorProfile) -> Path:
    p = _dir() / f"{_slug(profile.provider, profile.model)}.json"
    p.write_text(json.dumps(asdict(profile), indent=2))
    return p


def load(provider: str, model: str | None) -> GeneratorProfile | None:
    if not model:
        return None
    p = _dir() / f"{_slug(provider, model)}.json"
    if not p.exists():
        return None
    try:
        d: dict[str, Any] = json.loads(p.read_text())
        d["records"] = [ProbeRecord(**r) for r in d.get("records", [])]
        return GeneratorProfile(**d)
    except (json.JSONDecodeError, TypeError):
        return None


def path_for(provider: str, model: str) -> Path:
    return _dir() / f"{_slug(provider, model)}.json"


__all__ = [
    "with_provider",
    "GeneratorProfile",
    "ProbeRecord",
    "SIZES",
    "RULE",
    "measure",
    "save",
    "load",
    "path_for",
    "probes",
]
