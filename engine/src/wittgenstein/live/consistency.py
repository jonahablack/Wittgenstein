"""Does the answer survive a change of context? A material-difference test.

Two answers to the same question, from the same model, over different passages (all
of them, and only the passages most relevant to each part of the question). If they
differ in substance, at least one is wrong, and a person should look. Only material
differences count, never wording:

- one answers and the other doesn't (empty, bare citation, "not stated");
- yes against no;
- a value (with its unit) in one that the other doesn't give, after unit conversion
  (500 mg / 0.5 g are the same).

No model judges either answer; the test is deterministic, and the flag shows both.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from wittgenstein.live.claims import abstains, yes_no
from wittgenstein.live.quantities import canonical, checkable, quantities

_CITE = re.compile(r"\[\d+(?:\s*,\s*\d+)*\]")


@dataclass
class Difference:
    kind: str  # answered | polarity | value
    detail: str


def _content(text: str) -> str:
    return _CITE.sub(" ", text).strip(" .\n")


def answered(text: str) -> bool:
    body = _content(text)
    return len(body.split()) >= 2 and not abstains(body)


def _values(text: str) -> dict[tuple[str, float], str]:
    """Values with units, keyed by (dimension, amount in the base unit), shown as written."""
    out: dict[tuple[str, float], str] = {}
    for q in quantities(_content(text)):
        if checkable(q) and q.unit:
            c = canonical(q.value, q.unit)
            key = (c[0], round(c[1], 6)) if c is not None else (q.unit, float(q.value))
            out.setdefault(key, q.text.strip())
    return out


def material_difference(a: str, b: str, question: str = "") -> Difference | None:
    """`question`: values it states (the patient's own, "over 3 months") are ignored."""
    aa, ab = answered(a), answered(b)
    if aa != ab:
        return Difference("answered", "one version answers the question and the other doesn't")
    if not aa:
        return None
    ya, yb = yes_no(_content(a)), yes_no(_content(b))
    if ya and yb and ya != yb:
        return Difference("polarity", f"one says {ya}, the other {yb}")
    asked = set(_values(question))
    va = {k: v for k, v in _values(a).items() if k not in asked}
    vb = {k: v for k, v in _values(b).items() if k not in asked}
    if va and vb and set(va) != set(vb):
        only_a = ", ".join(v for k, v in va.items() if k not in vb) or "nothing else"
        only_b = ", ".join(v for k, v in vb.items() if k not in va) or "nothing else"
        return Difference("value", f"the answer shown gives {only_a}; the other gives {only_b}")
    return None


# --------------------------------------------------------------------------- the probe
@dataclass
class ContextProbe:
    perturbation: str  # fewer | reordered
    passages: list[int]  # the passage numbers (in the original prompt) the model saw, in order
    answer: str
    difference: Difference | None


def reduced(passages: list[tuple[int, str]], part_terms: list[list[str]], cap: int) -> list[int]:
    """The passages most relevant to each part of the question: the first passage (in
    prompt order, i.e. the pipeline's ranking) covering each part, then the next best,
    up to `cap`."""
    keep: list[int] = []
    for terms in part_terms:
        if len(keep) >= cap:
            break
        n = next((n for n, t in passages if terms and all(w in t.lower() for w in terms) and n not in keep), None)
        if n is not None:
            keep.append(n)
    for n, _ in passages:
        if len(keep) >= cap:
            break
        if n not in keep:
            keep.append(n)
    return [n for n, _ in passages if n in keep]


def run_context_probe(
    question: str,
    passages: list[tuple[int, str]],
    answer: str,
    generate,  # noqa: ANN001 -- (question, [(n, text)]) -> answer, numbering as given
    part_terms: list[list[str]],
    cap: int,
) -> ContextProbe | None:
    """Ask again with fewer passages (or, when there are no more than `cap`, the same
    passages in reverse order) and compare in substance."""
    if not passages:
        return None
    if len(passages) > cap:
        order, kind = reduced(passages, part_terms, cap), "fewer"
    elif len(passages) > 1:
        order, kind = [n for n, _ in reversed(passages)], "reordered"
    else:
        return None
    by_n = dict(passages)
    alt = generate(question, [(i + 1, by_n[n]) for i, n in enumerate(order)])
    return ContextProbe(kind, order, alt, material_difference(answer, alt, question))


def report(probe: ContextProbe | None, answer: str, out, capacity_note: str = "") -> None:  # noqa: ANN001
    from wittgenstein.core.enums import CheckOutcome, FlagDisposition, FlagKind, FlagOrigin, FlagSeverity

    label = "The answer keeps its substance with fewer passages, or in another order"
    if probe is None:
        out.check(FlagKind.ANSWER_CONTEXT_SENSITIVE, label, CheckOutcome.NOT_APPLICABLE, "Nothing to vary.")
        return
    how = (
        f"with only passages {', '.join(f'[{n}]' for n in probe.passages)}"
        if probe.perturbation == "fewer"
        else "with the same passages in reverse order"
    )
    d = probe.difference
    common = {
        "perturbation": probe.perturbation,
        "passages": probe.passages,
        "other_answer": probe.answer[:600],
    }
    if d is None:
        out.check(FlagKind.ANSWER_CONTEXT_SENSITIVE, label, CheckOutcome.PASSED,
                  f"Asked again {how}: the same in substance.")  # fmt: skip
        return
    shown, other = answered(answer), answered(probe.answer)
    if shown and other:
        f = out.flag(
            FlagKind.ANSWER_CONTEXT_SENSITIVE,
            origin=FlagOrigin.PIPELINE,
            stage="answer",
            severity=FlagSeverity.WARNING,
            disposition=FlagDisposition.NEEDS_REVIEW,
            title="The answer changes when the model sees "
            + ("fewer passages" if probe.perturbation == "fewer" else "the passages in another order"),
            observation=f"Asked again {how}, the model answered “{_content(probe.answer)[:240]}”. "
            f"In substance: {d.detail}. At most one of the two can be right."
            + (f" {capacity_note}" if capacity_note else ""),
            why_it_matters="A model that reads its passages reliably gives the same answer when an unrelated "
            "passage is removed or moved. One whose answer changes is being steered by which passages "
            "surround the answer, the way look-alike passages mislead models.",
            what_to_check="The value or yes/no against the source passage, for both versions.",
            refs=[],
            metrics={**common, "difference": d.kind},
            measurement="measured",
        )
        out.check(
            FlagKind.ANSWER_CONTEXT_SENSITIVE, label, CheckOutcome.FLAGGED, f"Asked again {how}: {d.detail}.", [f]
        )
        return
    # Only one version answers: informative, but it doesn't show the answer shown is wrong.
    title = (
        "With fewer passages, the model gave no answer" if shown else "With fewer passages, the model does answer"
    )
    if probe.perturbation == "reordered":
        title = title.replace("With fewer passages", "With the passages reordered")
    f = out.flag(
        FlagKind.ANSWER_CONTEXT_SENSITIVE,
        origin=FlagOrigin.PIPELINE,
        stage="answer",
        severity=FlagSeverity.INFO,
        disposition=FlagDisposition.INFORMATIONAL,
        title=title,
        observation=f"Asked again {how}, the model answered "
        f"“{_content(probe.answer)[:240] or probe.answer[:60]}”.",
        why_it_matters="Whether the model answers at all depends on which passages it sees.",
        what_to_check=None,
        refs=[],
        metrics={**common, "difference": d.kind},
        measurement="measured",
    )
    out.check(
        FlagKind.ANSWER_CONTEXT_SENSITIVE, label, CheckOutcome.PASSED, f"Asked again {how}: {d.detail}.", [f]
    )


__all__ = [
    "ContextProbe",
    "Difference",
    "answered",
    "material_difference",
    "reduced",
    "report",
    "run_context_probe",
]
