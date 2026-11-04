"""Answer-claim extraction: programmatic-first, LLM-optional, typed fallback
(docs/review-loop-implementation-plan.md §1, §3). Test categories 1, 6.
"""

from __future__ import annotations

from wittgenstein.proposition.llm_client import FakeLLMClient
from wittgenstein.review.answer_claims import extract_answer_claims


def test_no_llm_client_produces_zero_llm_calls() -> None:
    claims, llm_extractions = extract_answer_claims(
        "A Class I widget must pass the Load Stress Test at a 95% threshold. It is exempt from inspection.",
        trace_id="t1",
    )
    assert llm_extractions == []
    assert len(claims) >= 1
    assert all(c.extraction_method == "programmatic_rule_based" for c in claims)


def test_multi_sentence_answer_splits_into_multiple_claims() -> None:
    claims, _ = extract_answer_claims(
        "A Class I widget must pass the Load Stress Test at a 95% threshold. It is exempt from inspection.",
        trace_id="t1",
    )
    assert len(claims) == 2


def test_original_answer_text_is_preserved_across_claims() -> None:
    answer = "A Class I widget must pass the Load Stress Test at a 95% threshold. It is exempt from inspection."
    claims, _ = extract_answer_claims(answer, trace_id="t1")
    reconstructed = " ".join(c.text for c in claims)
    # Every word of the original answer appears somewhere in the claims -- extraction
    # never silently drops or rewrites the answer text.
    for word in answer.split():
        assert word.strip(".,") in reconstructed


def test_empty_answer_falls_back_to_one_whole_answer_claim() -> None:
    claims, llm_extractions = extract_answer_claims("   ", trace_id="t1")
    assert len(claims) == 1
    assert claims[0].extraction_method == "fallback_whole_answer"
    assert claims[0].text == "   "
    assert llm_extractions == []


def test_ambiguous_candidate_escalates_to_llm_when_client_given() -> None:
    answer = "The widget passes, and it is also exempt from inspection, which is unusual."
    fake_client = FakeLLMClient(responses={})
    _, llm_extractions = extract_answer_claims(answer, trace_id="t1", llm_client=fake_client)
    assert len(llm_extractions) >= 1


def test_llm_unavailable_client_falls_back_without_crashing() -> None:
    from wittgenstein.proposition.llm_client import NullLLMClient

    answer = "The widget passes, and it is also exempt from inspection, which is unusual."
    claims, llm_extractions = extract_answer_claims(answer, trace_id="t1", llm_client=NullLLMClient())
    assert len(claims) >= 1
    assert all(c.extraction_method in ("programmatic_rule_based", "llm_extracted") for c in claims)
    assert all(e.validation_status.value == "llm_unavailable" for e in llm_extractions)
