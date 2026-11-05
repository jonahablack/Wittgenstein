"""How much context the answering model uses reliably (live/generator_profile.py), and
what the pipeline does with that measurement (runner.note_generator_capacity): a note for
the reviewer, never a change to the context."""

from __future__ import annotations

import re
from types import SimpleNamespace

import pytest

from wittgenstein.core.enums import CandidateFate, CheckOutcome, FlagDisposition, FlagKind
from wittgenstein.live import generator_profile as gp
from wittgenstein.live.flags import FlagCollector
from wittgenstein.live.runner import note_generator_capacity
from wittgenstein.live.select import LedgerEntry, SelectionResult


@pytest.fixture(autouse=True)
def _home(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:  # noqa: ANN001
    monkeypatch.setenv("WITTGENSTEIN_HOME", str(tmp_path))


def small_model(limit: int):  # noqa: ANN201
    """Right with up to `limit` passages; beyond that, answers from passage 1 (a decoy
    unless the target happens to be first)."""

    def gen(question: str, texts: list[str]) -> str:
        if len(texts) > limit:
            return re.search(r"\d+", texts[0]).group(0) + " [1]"  # type: ignore[union-attr]
        found = []
        for tmpl, q, _unit, ents in gp._FAMILIES:
            for e, v in ents:
                asked = q.format(e=e).rstrip("?")
                if asked in question or (asked[0].lower() + asked[1:]) in question:
                    i = texts.index(tmpl.format(e=e, v=v))
                    found.append(f"{v} [{i + 1}]")
        return " and ".join(found)

    return gen


def test_build_places_targets_among_same_family_decoys() -> None:
    name, parts = gp.probes()[-1]
    texts, positions, values, decoys = gp.build(parts, 8, 5)
    assert len(texts) == 8 and len(positions) == 2
    for pos, v in zip(positions, values, strict=True):
        assert v in texts[pos - 1]
    assert not set(values) & set(decoys)


@pytest.mark.parametrize(
    ("answer", "outcome"),
    [
        ("It is 65 metres [3].", "correct"),
        ("It is 140 metres [1].", "wrong_passage"),  # a decoy's value
        ("[2]", "wrong_passage"),  # only a citation, to a decoy
        ("[3]", "no_answer"),  # cites the right passage but says nothing
        ("I don't know.", "no_answer"),
    ],
)
def test_grade(answer: str, outcome: str) -> None:
    assert gp.grade(answer, [3], ["65"], ["140", "95"])[0] == outcome


def test_measure_finds_where_a_small_model_breaks() -> None:
    prof = gp.measure(small_model(4), "fake", "small")
    assert prof.reliable_passages == 4
    assert prof.wrong_passage["12"] > prof.wrong_passage["2"]
    assert len(prof.records) == prof.n_probes * len(gp.SIZES)
    gp.save(prof)
    again = gp.load("fake", "small")
    assert again is not None and again.reliable_passages == 4 and len(again.records) == len(prof.records)


def _selection(n: int) -> SelectionResult:
    ledger = {
        f"u{i}": LedgerEntry(f"u{i}", CandidateFate.SELECTED, "", [], 1.0, i, ["f2"] if i == 5 else ["f1"], 10, i)
        for i in range(n)
    }
    return SelectionResult([f"u{i}" for i in range(n)], ledger, 2000, 10 * n, None, ["f1", "f2"], [], "k")


def _run(n: int, measured: bool = True, model: str = "small") -> tuple[FlagCollector, SelectionResult]:
    if measured:
        gp.save(gp.measure(small_model(4), "local", model))
    out = FlagCollector("t")
    sel = _selection(n)
    info = SimpleNamespace(uses_llm=True, provider_id="local", model_identifier=model)
    note_generator_capacity(sel, info, out)
    return out, sel


def test_over_capacity_is_flagged_with_its_evidence() -> None:
    out, sel = _run(8)
    f = next(f for f in out.flags if f.kind == FlagKind.CONTEXT_OVER_CAPACITY)
    # Informational: count alone is a weak predictor (held-out: flagged 38 of 40 runs), so no alarm.
    assert f.disposition == FlagDisposition.INFORMATIONAL
    assert len(sel.selected) == 8  # noted for the reviewer; the context is never changed
    assert f.metrics["reliable_passages"] == 4 and "measured" in f.observation.lower()
    assert out.checks[-1].outcome == CheckOutcome.FLAGGED


def test_within_capacity_passes_and_unmeasured_says_so() -> None:
    out, _ = _run(3)
    assert out.checks[-1].outcome == CheckOutcome.PASSED and not out.flags
    out, _ = _run(8, measured=False, model="never-measured")
    assert out.checks[-1].outcome == CheckOutcome.NOT_APPLICABLE and "measure-model" in out.checks[-1].detail
