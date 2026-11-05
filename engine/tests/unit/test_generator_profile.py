"""How much context the answering model uses reliably (live/generator_profile.py), and
what the pipeline does with that measurement (runner.fit_to_generator)."""

from __future__ import annotations

import re
from types import SimpleNamespace

import pytest

from wittgenstein.core.enums import CandidateFate, CheckOutcome, FlagDisposition, FlagKind
from wittgenstein.live import generator_profile as gp
from wittgenstein.live.flags import FlagCollector
from wittgenstein.live.runner import fit_to_generator
from wittgenstein.live.select import LedgerEntry, SelectionResult, fit_to_capacity


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


def test_fit_to_capacity_keeps_every_part_of_the_question() -> None:
    sel = _selection(8)
    removed = fit_to_capacity(sel, 3, "capacity")
    assert len(sel.selected) == 3 and "u5" in sel.selected  # the only passage for part f2
    assert all(sel.ledger[u].fate == CandidateFate.OMITTED_CAPACITY for u in removed)


def _run(n: int, trim: bool, measured: bool = True, model: str = "small") -> tuple[FlagCollector, SelectionResult]:
    if measured:
        gp.save(gp.measure(small_model(4), "local", model))
    out = FlagCollector("t")
    sel = _selection(n)
    info = SimpleNamespace(uses_llm=True, provider_id="local", model_identifier=model)
    fit_to_generator(SimpleNamespace(fit_to_generator=False), sel, info, out, trim=trim)  # type: ignore[arg-type]
    return out, sel


def test_over_capacity_is_flagged_with_its_evidence() -> None:
    out, sel = _run(8, trim=False)
    f = next(f for f in out.flags if f.kind == FlagKind.CONTEXT_OVER_CAPACITY)
    assert f.disposition == FlagDisposition.NEEDS_REVIEW and len(sel.selected) == 8
    assert f.metrics["reliable_passages"] == 4 and "measured" in f.observation.lower()
    assert out.checks[-1].outcome == CheckOutcome.FLAGGED


def test_fit_context_trims_and_records_it() -> None:
    out, sel = _run(8, trim=True)
    assert len(sel.selected) == 4
    f = next(f for f in out.flags if f.kind == FlagKind.CONTEXT_OVER_CAPACITY)
    assert f.disposition == FlagDisposition.HANDLED and len(f.metrics["left_out"]) == 4


def test_within_capacity_passes_and_unmeasured_says_so() -> None:
    out, _ = _run(3, trim=False)
    assert out.checks[-1].outcome == CheckOutcome.PASSED and not out.flags
    out, _ = _run(8, trim=False, measured=False, model="never-measured")
    assert out.checks[-1].outcome == CheckOutcome.NOT_APPLICABLE and "measure-model" in out.checks[-1].detail
