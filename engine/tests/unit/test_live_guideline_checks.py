"""Conflicting evidence among passages used, and recommendation strength."""

from __future__ import annotations

from wittgenstein.core.enums import FlagKind, RetrievalChannel
from wittgenstein.live.corpus import LiveCorpus
from wittgenstein.live.embedding import CachingEmbedder, HashingEmbedder
from wittgenstein.live.external import ExternalCheckRequest, check_external
from wittgenstein.live.flags import FlagCollector
from wittgenstein.live.generate import ContextPassage
from wittgenstein.live.pipelines import PipelineSpec
from wittgenstein.live.runner import run_query
from wittgenstein.live.strength import find_strength, summarize
from wittgenstein.live.verify import verify_answer

# --- recommendation strength parsing -------------------------------------------------


def _levels(text: str) -> list[tuple[str, str]]:
    return [(s.system, s.level) for s in find_strength(text)]


def test_acc_aha_classes_and_levels() -> None:
    assert ("ACC/AHA", "weak") in _levels("Statin therapy may be reasonable (Class IIb; LOE B-R).")
    assert ("ACC/AHA", "strong") in _levels("High-intensity statin therapy is recommended (Class I, LOE A).")
    assert ("ACC/AHA", "against") in _levels(
        "Routine aspirin is not recommended (Class III: No Benefit; LOE B-R)."
    )


def test_device_and_unit_classes_are_not_recommendation_classes() -> None:
    assert find_strength("A Class R inspection unit shall pass the assessment.") == []
    assert find_strength("This is a Class II medical device.") == []


def test_grade_and_uspstf() -> None:
    assert ("GRADE", "weak") in _levels("We suggest X (conditional recommendation, low-certainty evidence).")
    assert ("GRADE", "evidence_only") in _levels(
        "We suggest X (conditional recommendation, low-certainty evidence)."
    )
    assert ("GRADE", "weak") in _levels("Treatment is suggested (Grade 2B).")
    assert ("USPSTF", "against") in _levels("The USPSTF recommends against screening (D recommendation).")
    assert summarize(find_strength("may be reasonable (Class IIb; LOE B-R)")) == (
        "Class IIb; LOE B-R (weak or conditional recommendation)"
    )


def _guideline_unit(text: str) -> ContextPassage:
    corpus = LiveCorpus(f"g-{abs(hash(text))}", {"guideline": text})
    return ContextPassage(1, corpus.units().units[0]), corpus.units()


def test_weak_recommendation_stated_as_a_rule_is_flagged() -> None:
    src = (
        "In adults with diabetes aged 40 to 75 years, initiating statin therapy may be reasonable "
        "(Class IIb; LOE B-R)."
    )
    passage, units = _guideline_unit(src)
    out = FlagCollector("t")
    sents, _, _ = verify_answer(
        "In adults with diabetes aged 40 to 75 years, initiating statin therapy is required. [1]",
        [passage],
        units,
        out,
    )
    assert sents[0].strength and "Class IIb" in sents[0].strength
    assert any(f.kind == FlagKind.RECOMMENDATION_STRENGTH_DROPPED for f in out.flags)


def test_hedged_answer_keeps_a_weak_recommendation() -> None:
    src = (
        "In adults with diabetes aged 40 to 75 years, initiating statin therapy may be reasonable "
        "(Class IIb; LOE B-R)."
    )
    passage, units = _guideline_unit(src)
    out = FlagCollector("t")
    verify_answer(
        "In adults with diabetes aged 40 to 75 years, initiating statin therapy may be reasonable. [1]",
        [passage],
        units,
        out,
    )
    assert not any(f.kind == FlagKind.RECOMMENDATION_STRENGTH_DROPPED for f in out.flags)


def test_recommendation_against_answered_as_a_recommendation_is_caught() -> None:
    src = (
        "Routine aspirin use for primary prevention is not recommended in adults over 70 "
        "(Class III: Harm; LOE B-R)."
    )
    passage, units = _guideline_unit(src)
    out = FlagCollector("t")
    verify_answer("Adults over 70 should use routine aspirin for primary prevention. [1]", [passage], units, out)
    against = [f for f in out.flags if f.kind == FlagKind.RECOMMENDATION_STRENGTH_DROPPED]
    assert against and against[0].title == "The source recommends against this"
    assert "Class III: Harm; LOE B-R" in against[0].observation


# --- conflicting evidence -------------------------------------------------------------

OLD = "The recommended starting dosage of exampledrug is 500 mg orally once daily with the evening meal."
NEW = "The recommended starting dosage of exampledrug is 1000 mg orally once daily with the evening meal."
ADULT = "In adults, the recommended dose of exampledrug is 500 mg twice daily."
CHILD = "In pediatric patients, the recommended dose of exampledrug is 250 mg twice daily."


def _ext(texts: list[str]) -> dict:
    req = ExternalCheckRequest.model_validate(
        {
            "query": "What is the starting dosage of exampledrug?",
            "candidates": [{"id": f"c{i}", "text": t} for i, t in enumerate(texts)],
        }
    )
    return check_external(req)


def test_two_passages_with_different_values_are_reported_side_by_side() -> None:
    r = _ext([OLD, NEW])
    conflicts = [f for f in r["flags"] if f["kind"] == FlagKind.CONTEXT_CONFLICT.value]
    assert len(conflicts) == 1
    assert {x["quote"] for x in conflicts[0]["refs"]} == {OLD, NEW}
    assert conflicts[0]["registry"]["mechanism_id"] == "GEN_CONTEXT_CONFLICT_UNRESOLVED"


def test_opposite_polarity_is_a_conflict() -> None:
    r = _ext(
        [
            "Exampledrug is contraindicated in patients with an eGFR below 30 mL/min/1.73 m2.",
            "Exampledrug is not contraindicated in patients with an eGFR below 30 mL/min/1.73 m2.",
        ]
    )
    conflicts = [f for f in r["flags"] if f["kind"] == FlagKind.CONTEXT_CONFLICT.value]
    assert conflicts and conflicts[0]["metrics"]["dimension"] == "polarity"


def test_a_difference_by_patient_group_is_not_a_conflict() -> None:
    r = _ext([ADULT, CHILD])
    assert not [f for f in r["flags"] if f["kind"] == FlagKind.CONTEXT_CONFLICT.value]


def test_conflicts_are_recorded_in_the_query_trace() -> None:
    corpus = LiveCorpus("conflict-trace", {"edition-2024": OLD, "edition-2026": NEW})
    spec = PipelineSpec(
        pipeline_id="t", label="t", description="t", channels=[RetrievalChannel.LEXICAL], k=2, k_min=1
    )
    import wittgenstein.live.embedding as E

    E._REGISTRY.setdefault("hashing-test", CachingEmbedder(HashingEmbedder()))
    result = run_query(corpus, "What is the starting dosage of exampledrug?", ["t"], specs={"t": spec})
    trace = result.outcomes["t"].trace
    assert trace["context_conflicts"], "the conflict should be recorded on the trace"
    assert set(trace["context_conflicts"][0]["context_item_ids"]) == {u.unit_id for u in corpus.units().units}
