"""Meaning-level checks (live/nli.py). Skipped when the model can't be loaded (offline)."""

from __future__ import annotations

import pytest

from wittgenstein.core.enums import FlagKind
from wittgenstein.live import nli
from wittgenstein.live.corpus import LiveCorpus
from wittgenstein.live.external import ExternalCheckRequest, check_external
from wittgenstein.live.flags import FlagCollector
from wittgenstein.live.generate import ContextPassage
from wittgenstein.live.verify import verify_answer

pytestmark = pytest.mark.skipif(nli.model() is None, reason=f"NLI model unavailable: {nli.load_error()}")

POLICY = "Bereavement policy does not allow refunds for travel that has already happened."
CHATBOT = (
    "If you need to travel immediately or have already travelled and would like to submit your ticket for a "
    "reduced bereavement rate, kindly do so within 90 days of the date your ticket was issued by completing our "
    "Ticket Refund Application form. [1]"
)


def _verify(source: str, answer: str) -> tuple[list, FlagCollector]:
    corpus = LiveCorpus(f"nli-{abs(hash((source, answer)))}", {"d": source})
    units = corpus.units()
    out = FlagCollector("t")
    sents, _, _ = verify_answer(answer, [ContextPassage(1, units.units[0])], units, out)
    return sents, out


def test_variants_keep_the_subject_and_the_condition() -> None:
    vs = nli.variants("If you need to travel immediately or have already travelled, apply within 90 days.")
    assert "If you have already travelled, apply within 90 days." in vs
    assert all(v.startswith(("If you", "apply")) for v in vs)


def test_the_air_canada_contradiction_is_caught() -> None:
    """The case from research/case-studies: word matching said only 'no support'."""
    _, out = _verify(POLICY, CHATBOT)
    flags = [f for f in out.flags if f.kind == FlagKind.ANSWER_CONTRADICTS_SOURCE]
    assert flags and flags[0].severity.value == "warning"
    assert flags[0].measurement == "model_judgment"
    # the vaguer "couldn't be matched" flag is replaced, not duplicated
    assert not any(f.kind == FlagKind.ANSWER_SENTENCE_UNSUPPORTED for f in out.flags)


def test_a_faithful_paraphrase_is_supported_not_flagged() -> None:
    sents, out = _verify(
        "The recommended starting dosage is 500 mg orally once daily with the evening meal.",
        "Start at 500 mg once a day with the evening meal. [1]",
    )
    assert sents[0].support == "entailed_paraphrase"
    assert not any(
        f.kind in {FlagKind.ANSWER_SENTENCE_UNSUPPORTED, FlagKind.ANSWER_CONTRADICTS_SOURCE} for f in out.flags
    )


def test_a_different_patient_group_is_not_a_contradiction() -> None:
    _, out = _verify(
        "In adults, the recommended dose is 500 mg twice daily.",
        "In pediatric patients, the recommended dose is 250 mg twice daily. [1]",
    )
    assert not any(f.kind == FlagKind.ANSWER_CONTRADICTS_SOURCE for f in out.flags)


def test_paraphrased_conflict_between_passages_is_found() -> None:
    req = ExternalCheckRequest.model_validate(
        {
            "query": "Do landlords have to accept Section 8 housing vouchers?",
            "candidates": [
                {
                    "id": "a",
                    "text": "Landlords may not refuse tenants because they pay with Section 8 housing vouchers.",
                },
                {
                    "id": "b",
                    "text": "Landlords do not have to accept tenants who pay with Section 8 housing vouchers.",
                },
            ],
        }
    )
    r = check_external(req)
    conflicts = [f for f in r["flags"] if f["kind"] == FlagKind.CONTEXT_CONFLICT.value]
    assert conflicts
