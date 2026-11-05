"""Counterfactual context probe: does the model answer from the passages, or from memory?

Every text check compares the answer with the passages. None can tell whether the model
*read* them: a model that knows "metformin ER, maximum 2,000 mg" from training gives the
right number with a citation whether or not the passage says it -- and gives the same
number when the passage (a newer label, a local protocol) says something else. That
failure is invisible in any single run.

So the probe changes the evidence and asks again. For a value the answer takes from a
passage (a dose, a threshold, a duration), every mention of it in the passages is
replaced by a different, plausible value, and the pipeline's own generator is asked the
same question over the edited passages:

- the new answer gives the new value: the model follows its context (passed);
- it still gives the original value: the model is answering from memory (flagged);
- it gives neither: inconclusive, reported as such.

This is a measurement of the generator, not of one answer's truth, and it costs one
extra generation per probed value (MAX_PROBES). It needs a generator to call: an LLM
provider in the live pipeline, or the caller's own model through a callback
(docs/integration.md). Known limit: a model that follows context on numbers may still
lean on memory elsewhere; a pass is evidence, not proof.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from wittgenstein.core.enums import CheckOutcome, FlagDisposition, FlagKind, FlagOrigin, FlagSeverity
from wittgenstein.live.flags import FlagCollector
from wittgenstein.live.quantities import Quantity, checkable, quantities

MAX_PROBES = 2

#: (question, [(n, passage text)]) -> answer text
Generate = Callable[[str, list[tuple[int, str]]], str]


@dataclass
class ProbeResult:
    value: str
    unit: str | None
    original_text: str
    replacement_text: str
    outcome: str  # follows_context | ignores_context | unstable | inconclusive | error
    new_answer: str = ""
    detail: str = ""
    passages_edited: list[int] = field(default_factory=list)


def _replacement(q: Quantity) -> str:
    """A different value of the same shape and plausibility: x1.5, rounded the way the
    original is written (500 -> 750, 2,000 -> 3,000, 1.6 -> 2.4, 30 -> 45)."""
    v = float(q.value)
    new = v * 1.5
    if "." in q.value:
        places = len(q.value.split(".")[1])
        s = f"{new:.{places}f}"
    else:
        s = str(int(round(new)))
        if v >= 100 and int(s) % 50:
            s = str(int(round(new / 50.0)) * 50)
    if s == q.value:
        s = str(int(v) + 1) if "." not in q.value else f"{v + 0.1:.1f}"
    return s


def _fmt(raw_value: str, like: str) -> str:
    """Write `raw_value` with a thousands separator if the original used one."""
    if "," in like and "." not in raw_value and len(raw_value) > 3:
        return f"{int(raw_value):,}"
    return raw_value


def _replacer(new_value: str) -> Callable[[re.Match[str]], str]:
    def sub(m: re.Match[str]) -> str:
        return _fmt(new_value, m.group(0))

    return sub


def _value_pattern(q: Quantity) -> re.Pattern[str]:
    v = q.value
    digits = rf"{v[:-3]},?{v[-3:]}" if len(v) > 3 and "." not in v else re.escape(v)
    return re.compile(rf"(?<![\w.,]){digits}(?![\d])(?=\s*{re.escape(q.unit or '')})", re.IGNORECASE)


def _mentions(text: str, value: str, unit: str | None) -> bool:
    return any(q.value == value and (unit is None or q.unit == unit) for q in quantities(text))


def targets(answer: str, passages: list[tuple[int, str]], question: str = "") -> list[Quantity]:
    """Answer values (with units) that some passage states: the ones whose source a
    counterfactual edit can test. Values the question states ("children over 3 months")
    are left alone -- repeating them is right whatever the passages say (measured: the
    probe's one false positive on a real model)."""
    out: list[Quantity] = []
    seen = {(q.value, q.unit) for q in quantities(question)}
    for q in quantities(answer):
        if not checkable(q) or q.unit is None or q.range_with is not None:
            continue
        key = (q.value, q.unit)
        if key in seen:
            continue
        if any(_mentions(t, q.value, q.unit) for _, t in passages):
            seen.add(key)
            out.append(q)
    return out


def run_probes(
    question: str,
    passages: list[tuple[int, str]],
    answer: str,
    generate: Generate,
    max_probes: int = MAX_PROBES,
) -> list[ProbeResult]:
    results = []
    for q in targets(answer, passages, question)[:max_probes]:
        new_value = _replacement(q)
        pat = _value_pattern(q)
        edited: list[tuple[int, str]] = []
        touched: list[int] = []
        sample = ""
        for n, t in passages:
            m = pat.search(t)
            if m:
                sample = sample or m.group(0)
                touched.append(n)
                t = pat.sub(_replacer(new_value), t)
            edited.append((n, t))
        if not touched:
            continue
        unit = q.unit or ""
        r = ProbeResult(
            value=q.value,
            unit=q.unit,
            original_text=f"{sample} {unit}".strip(),
            replacement_text=f"{_fmt(new_value, sample)} {unit}".strip(),
            outcome="inconclusive",
            passages_edited=touched,
        )
        try:
            new_answer = generate(question, edited)
        except Exception as e:  # noqa: BLE001 -- a failed probe is reported, never counted as a pass
            r.outcome, r.detail = "error", f"{type(e).__name__}: {e}"[:300]
            results.append(r)
            continue
        r.new_answer = new_answer
        has_new = _mentions(new_answer, new_value, q.unit)
        has_old = _mentions(new_answer, q.value, q.unit)
        if has_new and not has_old:
            r.outcome = "follows_context"
        elif has_old and not has_new:
            r.outcome = "ignores_context"
        elif not has_new and not has_old and _other_value(new_answer, q, new_value):
            # Neither value: the model said something else entirely. A generator that
            # reads its context changes only what was edited; this one rewrote the answer.
            r.outcome = "unstable"
            r.detail = "a different value"
        else:
            r.outcome = "inconclusive"
            r.detail = "both values" if has_new else "neither value"
        results.append(r)
    return results


def _other_value(text: str, q: Quantity, new_value: str) -> bool:
    """`text` gives some other amount where the answer had `q`: a value with q's unit
    (or any dose unit, when q is a dose) that is neither the original nor the edit."""
    dose_units = {"mg", "mcg", "g", "mg/kg", "mcg/kg", "mg/kg/day", "mcg/kg/day"}
    for x in quantities(text):
        if x.value in {q.value, new_value}:
            continue
        if x.unit == q.unit or (q.unit in dose_units and x.unit in dose_units):
            return True
    return False


def report(results: list[ProbeResult], out: FlagCollector) -> list[dict[str, Any]]:
    flags = []
    for r in results:
        if r.outcome == "unstable":
            f = out.flag(
                FlagKind.ANSWER_UNSTABLE,
                origin=FlagOrigin.PIPELINE,
                stage="answer",
                severity=FlagSeverity.CAUTION,
                disposition=FlagDisposition.NEEDS_REVIEW,
                title="The answer changed in other ways when one value was edited",
                observation=f"With {r.original_text} changed to {r.replacement_text} in the passages, the model "
                f"answered “{r.new_answer[:200]}”.",
                why_it_matters="A model that reads its context changes only what was edited. One whose answer "
                "jumps to a different value is not reliably grounded, so this answer may not be either.",
                what_to_check="The value in the source, independently of the answer.",
                refs=[],
                metrics={
                    "value": r.value,
                    "unit": r.unit,
                    "replaced_with": r.replacement_text,
                    "new_answer": r.new_answer[:400],
                },
                measurement="measured",
            )
            flags.append(f)
            continue
        if r.outcome != "ignores_context":
            continue
        f = out.flag(
            FlagKind.CONTEXT_IGNORED,
            origin=FlagOrigin.PIPELINE,
            stage="answer",
            severity=FlagSeverity.WARNING,
            disposition=FlagDisposition.NEEDS_REVIEW,
            title="The model may be answering from memory, not from the passages",
            observation=f"When the passages were changed to say {r.replacement_text} instead of "
            f"{r.original_text}, the model still answered {r.original_text}.",
            why_it_matters="A model that answers from training gives the familiar value even where the document "
            "(a newer label, a local protocol) says otherwise; its citations then decorate an answer they "
            "didn't produce.",
            what_to_check="Whether the document's value is the one that applies, and whether the pipeline's "
            "model reliably uses its context.",
            refs=[],
            metrics={
                "value": r.value,
                "unit": r.unit,
                "replaced_with": r.replacement_text,
                "passages_edited": r.passages_edited,
                "new_answer": r.new_answer[:400],
            },
            measurement="measured",
        )
        flags.append(f)
    done = [r for r in results if r.outcome in {"follows_context", "ignores_context", "unstable"}]
    out.check(
        FlagKind.CONTEXT_IGNORED,
        "The model follows its passages (counterfactual probe)",
        CheckOutcome.FLAGGED if flags else CheckOutcome.PASSED if done else CheckOutcome.NOT_APPLICABLE,
        (
            f"{len(results)} values probed: "
            + ", ".join(
                f"{r.original_text} → {r.replacement_text}: {r.outcome.replace('_', ' ')}" for r in results
            )
        )
        if results
        else "No answer value came from a passage, so there was nothing to probe.",
        flags,
    )
    return [r.__dict__ for r in results]


__all__ = ["MAX_PROBES", "ProbeResult", "Generate", "run_probes", "report", "targets"]
