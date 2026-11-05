"""Two per-answer signals for misleading context, instead of trimming it:
- live/answer_source.py: a question part answered from a look-alike passage;
- live/consistency.py: the answer's substance changes with fewer passages or another order."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from wittgenstein.core.enums import CheckOutcome, FlagDisposition, FlagKind
from wittgenstein.live import consistency as C
from wittgenstein.live.answer_source import answers, check_answer_sources, parts
from wittgenstein.live.flags import FlagCollector

Q = "What clearance margin applies to Class S units, and who counts as a registered operator?"
ASTERIA = [
    "A Class R inspection unit shall pass the Structural Load Assessment at a minimum clearance margin of 12 "
    "centimetres before deployment.",
    "A Class S inspection unit shall pass the Structural Load Assessment at a minimum clearance margin of 8 "
    "centimetres before deployment.",
    "A registered operator is subject to the renewal obligation under this Article only if the operator's "
    "inspection unit operates in a restricted-access industrial zone.",
    "A registered operator is a natural or legal person who has completed registration under Article 5.",
]


def _passages(texts: list[str]) -> list:
    return [SimpleNamespace(n=i + 1, unit=SimpleNamespace(sentences=[], text=t)) for i, t in enumerate(texts)]


def test_parts_and_their_forms() -> None:
    ps = parts(Q)
    assert [(p.kind, p.ids, p.term) for p in ps] == [
        ("amount", ("class s",), None),
        ("definition", (), "registered operator"),
    ]
    assert [p.kind for p in parts("What is the usual starting dose of metformin?")] == ["amount"]
    assert [p.kind for p in parts("How often should INR be monitored?")] == ["frequency"]
    assert parts("Is warfarin safe in pregnancy?") == []


def test_answering_sentences() -> None:
    amount, definition = parts(Q)
    assert [answers(amount, s) for s in ASTERIA] == [False, True, False, False]  # Class R is not Class S
    assert [answers(definition, s) for s in ASTERIA] == [False, False, False, True]


@pytest.mark.parametrize(
    ("answer", "flagged"),
    [
        (
            "The clearance margin for Class S units is 8 centimetres, and a registered operator is subject to the "
            "renewal obligation under Article 2 only if the operator's inspection unit operates in a "
            "restricted-access industrial zone.",
            True,
        ),
        (
            "The clearance margin for Class S units is 8 centimetres, and a registered operator is a natural or "
            "legal person who has completed registration under Article 5.",
            False,
        ),
    ],
)
def test_answer_from_a_neighbouring_passage(answer: str, flagged: bool) -> None:
    out = FlagCollector("t")
    check_answer_sources(Q, answer, _passages(ASTERIA), out)
    got = [f for f in out.flags if f.kind == FlagKind.ANSWER_FROM_NEIGHBOR]
    assert bool(got) == flagged
    if flagged:
        assert "[3]" in got[0].observation and "[4]" in got[0].observation  # names both passages


@pytest.mark.parametrize(
    ("a", "b", "question", "kind"),
    [
        ("The adult dose is 25 mg/kg/day.", "The adult dose is 500 mg every 12 hours.", "", "value"),
        ("Max 2,000 mg.", "Max 2 g.", "", None),  # the same amount
        ("Yes, it is.", "No, it is not.", "", "polarity"),
        ("Every 8 hours for children over 3 months.", "Every 8 hours.", "...children over 3 months?", None),
        ("[1]", "The dose is 80 mg.", "", "answered"),
        ("Start at 500 mg once daily [1].", "The starting dose is 500 mg daily [2].", "", None),  # wording only
    ],
)
def test_material_difference(a: str, b: str, question: str, kind: str | None) -> None:
    d = C.material_difference(a, b, question)
    assert (d.kind if d else None) == kind


def test_reduced_keeps_a_passage_for_each_part() -> None:
    ps = [(1, "about alpha"), (2, "about beta"), (3, "about gamma"), (4, "about delta and omega")]
    assert C.reduced(ps, [["omega"], ["beta"]], 2) == [2, 4]


def _probe(shown: str, other: str, n: int = 6) -> FlagCollector:
    out = FlagCollector("t")
    ps = [(i + 1, f"passage {i + 1}") for i in range(n)]
    C.report(C.run_context_probe("What is the dose?", ps, shown, lambda q, p: other, [], 3), shown, out)
    return out


def test_probe_flags_a_changed_value_for_review() -> None:
    out = _probe("The dose is 2,000 mg [1].", "The dose is 80 mg [2].")
    f = out.flags[0]
    assert f.kind == FlagKind.ANSWER_CONTEXT_SENSITIVE and f.disposition == FlagDisposition.NEEDS_REVIEW
    assert "80 mg" in f.observation and f.metrics["perturbation"] == "fewer"


def test_probe_notes_but_does_not_alarm_when_one_version_is_empty() -> None:
    out = _probe("The dose is 80 mg [1].", "[2]")
    assert out.flags[0].disposition == FlagDisposition.INFORMATIONAL


def test_probe_passes_on_the_same_substance_and_reorders_small_contexts() -> None:
    out = _probe("The dose is 80 mg [1].", "It is 80 mg [3].", n=3)
    assert not out.flags and out.checks[-1].outcome == CheckOutcome.PASSED
    assert "reverse order" in out.checks[-1].detail
