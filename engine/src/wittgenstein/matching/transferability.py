"""Transparent transferability assessment: compare a manifest/trace-derived envelope
against a mechanism's linked evidence record envelopes, field by field.

Never produces a single opaque similarity score -- always a triple of
matching/mismatching/unknown dimension lists a reviewer can read directly.
"""

from __future__ import annotations

from dataclasses import dataclass

from wittgenstein.core.enums import ConfidenceTier, TransferLevel
from wittgenstein.schemas.evidence import EvidenceRecord, ExperimentalEnvelope

#: Fields compared for transfer purposes. Excludes bookkeeping-only fields.
_COMPARABLE_FIELDS = [name for name in ExperimentalEnvelope.model_fields if name != "rag_presence"]


@dataclass
class EnvelopeComparison:
    matching_dimensions: list[str]
    mismatching_dimensions: list[str]
    unknown_dimensions: list[str]


def compare_envelopes(
    manifest_env: ExperimentalEnvelope, evidence_env: ExperimentalEnvelope
) -> EnvelopeComparison:
    matching: list[str] = []
    mismatching: list[str] = []
    unknown: list[str] = []
    for field in _COMPARABLE_FIELDS:
        evidence_value = getattr(evidence_env, field)
        if evidence_value is None:
            continue  # the study itself didn't specify this dimension; not comparable
        manifest_value = getattr(manifest_env, field)
        if manifest_value is None:
            unknown.append(field)
        elif manifest_value == evidence_value:
            matching.append(field)
        else:
            mismatching.append(field)
    return EnvelopeComparison(matching, mismatching, unknown)


def transfer_level_for_evidence(
    manifest_env: ExperimentalEnvelope, evidence: EvidenceRecord
) -> tuple[TransferLevel, EnvelopeComparison]:
    comparison = compare_envelopes(manifest_env, evidence.experimental_envelope)

    if comparison.mismatching_dimensions:
        return TransferLevel.PARTIALLY_MATCHED, comparison

    known_count = len(comparison.matching_dimensions) + len(comparison.unknown_dimensions)
    if known_count == 0:
        return TransferLevel.INSUFFICIENT_MANIFEST_INFORMATION, comparison

    evidence_rag_presence = evidence.experimental_envelope.rag_presence
    if evidence_rag_presence is False:
        # Direct evidence from a non-RAG setting (e.g. plain long-context LLM study)
        # can never be directly_matched to a RAG manifest -- it always requires the
        # manifest-conditioning step.
        if not comparison.unknown_dimensions:
            return TransferLevel.MECHANISTICALLY_MATCHED, comparison
        return TransferLevel.PARTIALLY_MATCHED, comparison

    if comparison.unknown_dimensions:
        if len(comparison.unknown_dimensions) <= len(comparison.matching_dimensions):
            return TransferLevel.MECHANISTICALLY_MATCHED, comparison
        return TransferLevel.PARTIALLY_MATCHED, comparison

    return TransferLevel.DIRECTLY_MATCHED, comparison


#: Ranks levels so "best across linked evidence records" can be picked deterministically.
_LEVEL_RANK = {
    TransferLevel.NOT_APPLICABLE: 0,
    TransferLevel.INSUFFICIENT_MANIFEST_INFORMATION: 1,
    TransferLevel.PARTIALLY_MATCHED: 2,
    TransferLevel.MECHANISTICALLY_MATCHED: 3,
    TransferLevel.DIRECTLY_MATCHED: 4,
}


def best_transfer_across_evidence(
    manifest_env: ExperimentalEnvelope, evidence_records: list[EvidenceRecord]
) -> tuple[TransferLevel, EnvelopeComparison, EvidenceRecord | None]:
    if not evidence_records:
        return (
            TransferLevel.INSUFFICIENT_MANIFEST_INFORMATION,
            EnvelopeComparison([], [], []),
            None,
        )
    best_level = TransferLevel.NOT_APPLICABLE
    best_comparison = EnvelopeComparison([], [], [])
    best_evidence: EvidenceRecord | None = None
    for evidence in evidence_records:
        level, comparison = transfer_level_for_evidence(manifest_env, evidence)
        if _LEVEL_RANK[level] > _LEVEL_RANK[best_level]:
            best_level, best_comparison, best_evidence = level, comparison, evidence
    return best_level, best_comparison, best_evidence


def confidence_for(comparison: EnvelopeComparison) -> ConfidenceTier:
    known = len(comparison.matching_dimensions) + len(comparison.mismatching_dimensions)
    total = known + len(comparison.unknown_dimensions)
    if total == 0:
        return ConfidenceTier.INSUFFICIENT_DATA
    if comparison.mismatching_dimensions:
        return ConfidenceTier.LOW
    if not comparison.unknown_dimensions:
        return ConfidenceTier.HIGH
    if len(comparison.unknown_dimensions) <= len(comparison.matching_dimensions):
        return ConfidenceTier.MEDIUM
    return ConfidenceTier.LOW
