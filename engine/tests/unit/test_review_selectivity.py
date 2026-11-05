"""What reaches "worth a look": passage-level flags stay review items only when they bear
on the answer (flags.gate_to_answer); different named items never count as conflicting
(conflicts.different_referents)."""

from __future__ import annotations

from wittgenstein.core.enums import FlagDisposition, FlagKind, FlagOrigin, FlagSeverity
from wittgenstein.live.conflicts import different_referents
from wittgenstein.live.flags import FlagCollector, SourceRef, gate_to_answer


def _flag(out: FlagCollector, kind: FlagKind, unit: str, sentences: list[str] | None = None):  # noqa: ANN202
    return out.flag(
        kind,
        origin=FlagOrigin.TEXT,
        stage="retrieval",
        severity=FlagSeverity.WARNING,
        disposition=FlagDisposition.NEEDS_REVIEW,
        title="t",
        observation="o",
        why_it_matters="w",
        what_to_check="c",
        refs=[SourceRef(unit_id=unit, document_id="d", char_start=0, char_end=1, quote="q")],
        metrics={"sentences": sentences or []},
        measurement="pattern_match",
    )


def test_look_alike_passage_is_a_review_item_only_if_the_answer_used_it() -> None:
    out = FlagCollector("t")
    used, unused = _flag(out, FlagKind.NEAR_MISS, "p1"), _flag(out, FlagKind.NEAR_MISS, "p6")
    changed = gate_to_answer(out.flags, {"p1", "p2"}, "anything")
    assert changed == [unused]
    assert used.disposition == FlagDisposition.NEEDS_REVIEW
    assert unused.disposition == FlagDisposition.INFORMATIONAL and unused.action_taken


def test_conflict_is_a_review_item_only_if_the_answer_states_the_disputed_point() -> None:
    sents = ["Do not exceed atorvastatin 20 mg once daily with clarithromycin.",
             "Do not exceed atorvastatin 40 mg once daily with clarithromycin."]  # fmt: skip
    out = FlagCollector("t")
    took_a_side = _flag(out, FlagKind.CONTEXT_CONFLICT, "p1", sents)
    gate_to_answer(out.flags, set(), "Do not exceed 40 mg once daily with clarithromycin. [2]")
    assert took_a_side.disposition == FlagDisposition.NEEDS_REVIEW
    out = FlagCollector("t")
    elsewhere = _flag(out, FlagKind.CONTEXT_CONFLICT, "p1", sents)
    gate_to_answer(out.flags, set(), "Children are given amoxicillin every 8 to 12 hours. [1]")
    assert elsewhere.disposition == FlagDisposition.INFORMATIONAL


def test_answer_flags_are_never_gated() -> None:
    out = FlagCollector("t")
    f = _flag(out, FlagKind.QUANTITY_MISMATCH, "p9")
    assert gate_to_answer(out.flags, set(), "") == [] and f.disposition == FlagDisposition.NEEDS_REVIEW


def test_different_named_items_are_not_a_conflict() -> None:
    assert different_referents("A Class R unit needs 12 centimetres.", "A Class S unit needs 8 centimetres.")
    assert different_referents("Immediate-release maximum is 2,550 mg.", "Extended-release maximum is 2,000 mg.")
    assert not different_referents("Do not exceed 20 mg with clarithromycin.", "Do not exceed 40 mg with it.")
