"""Answer-claim extraction: the same programmatic-first, LLM-optional, typed-fallback
priority as every other extraction tier in this codebase
(docs/review-loop-implementation-plan.md §1, §3).

1. Programmatic: reuse `ingestion/parser.py::split_sentences` (Tier 0 sentence
   boundaries) followed by `proposition/candidates.py::split_candidates` (Tier 1,
   designed to run on "typically a sentence" per its own docstring) against a
   synthetic SourceSegment per sentence. Composing the two existing splitters, not
   writing a new one (CLAUDE.md) -- and not skipping sentence splitting, which matters
   here: an answer is not pre-segmented into sentence-level Tier-0 segments the way
   source documents are, so without this step a multi-sentence answer would only ever
   split on semicolons/conjunctions/condition markers, not sentence boundaries.
2. Optional provider-backed: an ambiguous candidate may be escalated through the
   existing Tier-3 chokepoint, `proposition/llm_extraction.py::extract_tier3`. This
   only marks provenance (`extraction_method="llm_extracted"`); it does not attempt to
   further decompose the claim, since a Tier-3 provider's parsed_output shape is
   prompt/provider-defined and standardizing it is out of this milestone's scope (see
   docs/review-loop-implementation-plan.md §8, "deferred").
3. Typed fallback: one AnswerClaim covering the whole answer text,
   extraction_method="fallback_whole_answer" -- used when the answer text is empty/
   whitespace-only, or if programmatic splitting itself raises (defensive; never let an
   extraction failure become a false claim about the answer).

Never converts an extraction failure into "the answer is false," "the answer is
faithful," or "the answer is hallucinated" -- this module produces AnswerClaims only;
support/conflict judgments are `review/claim_linking.py`'s job, and even those are
explicitly pre-review candidates (core/enums.py::ClaimSupportCandidateStatus).
"""

from __future__ import annotations

from wittgenstein.core.enums import ExtractionValidationStatus, SegmentType
from wittgenstein.ingestion.kv_cache import KVCache
from wittgenstein.ingestion.parser import split_sentences
from wittgenstein.proposition.candidates import split_candidates
from wittgenstein.proposition.llm_client import LLMClient
from wittgenstein.proposition.llm_extraction import extract_tier3
from wittgenstein.schemas.proposition import LLMExtractionResult, PropositionCandidate, SourceSegment
from wittgenstein.schemas.trace import AnswerClaim


def extract_answer_claims(
    answer_text: str,
    *,
    trace_id: str,
    llm_client: LLMClient | None = None,
    llm_cache: KVCache | None = None,
    model_id: str = "unconfigured",
) -> tuple[list[AnswerClaim], list[LLMExtractionResult]]:
    """Returns (claims, llm_extractions). `llm_extractions` is empty whenever
    `llm_client` is None -- imported-answer mode works with zero LLM calls by default.
    """

    if not answer_text or not answer_text.strip():
        return (
            [
                AnswerClaim(
                    claim_id=f"{trace_id}-claim1", text=answer_text, extraction_method="fallback_whole_answer"
                )
            ],
            [],
        )

    try:
        candidates: list[PropositionCandidate] = []
        sentences = split_sentences(answer_text) or [(answer_text, 0, len(answer_text))]
        for sent_idx, (sentence_text, _start, _end) in enumerate(sentences, start=1):
            segment = SourceSegment(
                segment_id=f"answer-sent{sent_idx}",
                source_document_id="answer",
                corpus_id="answer",
                segment_type=SegmentType.SENTENCE,
                location=f"Answer > Sentence {sent_idx}",
                text=sentence_text,
                char_start=0,
                char_end=len(sentence_text),
                parser_version="review-answer-claims-1",
            )
            candidates.extend(split_candidates(segment, id_prefix=f"{trace_id}-claim{sent_idx}"))
    except Exception:  # noqa: BLE001 -- a splitting failure must degrade, never crash the review pipeline
        return (
            [
                AnswerClaim(
                    claim_id=f"{trace_id}-claim1", text=answer_text, extraction_method="fallback_whole_answer"
                )
            ],
            [],
        )

    claims: list[AnswerClaim] = []
    llm_extractions: list[LLMExtractionResult] = []
    for candidate in candidates:
        extraction_method = "programmatic_rule_based"
        if candidate.is_ambiguous and llm_client is not None:
            result = extract_tier3(
                candidate.candidate_id,
                candidate.text,
                client=llm_client,
                cache=llm_cache,
                model_id=model_id,
            )
            llm_extractions.append(result)
            if result.validation_status == ExtractionValidationStatus.VALIDATED:
                extraction_method = "llm_extracted"
        claims.append(
            AnswerClaim(claim_id=candidate.candidate_id, text=candidate.text, extraction_method=extraction_method)
        )

    return claims, llm_extractions
