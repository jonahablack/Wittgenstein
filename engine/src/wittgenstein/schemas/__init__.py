"""Typed Pydantic v2 schemas for every registry, manifest, trace, and assessment entity.

Import surface is intentionally flat re-exports from here so callers write
`from wittgenstein.schemas import FailureMechanism` rather than reaching into
individual submodules.
"""

from __future__ import annotations

from wittgenstein.schemas.applicability import (
    ApplicabilityAssessment,
    EligibilityGateResult,
)
from wittgenstein.schemas.claim_comparison import (
    ClaimEvidenceComparison,
    ExtractedField,
    FieldComparison,
    SemanticComparisonResult,
)
from wittgenstein.schemas.corpus_profile import CorpusProfile
from wittgenstein.schemas.evidence import EvidenceRecord, ExperimentalEnvelope
from wittgenstein.schemas.evidence_set import ClaimComponent, EvidenceSet, EvidenceSetConflict, EvidenceSetMember
from wittgenstein.schemas.failure_mode import (
    FailureMechanism,
    ManifestGate,
    ManifestPredicate,
    TraceObservableRequirement,
    TraceTrigger,
)
from wittgenstein.schemas.manifest import (
    CorpusManifest,
    EvaluationManifest,
    GenerationManifest,
    IngestionManifest,
    PackingManifest,
    PipelineManifest,
    RepresentationManifest,
    RerankingManifest,
    RetrievalManifest,
    SelectionManifest,
)
from wittgenstein.schemas.proposition import (
    LLMExtractionResult,
    PropositionAnnotation,
    PropositionCandidate,
    SourceDocument,
    SourceSegment,
)
from wittgenstein.schemas.review import LocalValidationRecord, ReviewAction, RiskEvent
from wittgenstein.schemas.review_event import ReviewEvent
from wittgenstein.schemas.smoke_test import CorpusReference, SmokeTestCase, SmokeTestCaseFile
from wittgenstein.schemas.trace import (
    AnswerClaim,
    AnswerSupportEdge,
    ContextConflict,
    ContextItem,
    QueryTrace,
    SupportRequirement,
)

__all__ = [
    "ApplicabilityAssessment",
    "EligibilityGateResult",
    "CorpusProfile",
    "EvidenceRecord",
    "ExperimentalEnvelope",
    "FailureMechanism",
    "ManifestGate",
    "ManifestPredicate",
    "TraceObservableRequirement",
    "TraceTrigger",
    "CorpusManifest",
    "EvaluationManifest",
    "GenerationManifest",
    "IngestionManifest",
    "PackingManifest",
    "PipelineManifest",
    "RepresentationManifest",
    "RerankingManifest",
    "RetrievalManifest",
    "SelectionManifest",
    "LocalValidationRecord",
    "ReviewAction",
    "RiskEvent",
    "ReviewEvent",
    "CorpusReference",
    "SmokeTestCase",
    "SmokeTestCaseFile",
    "ClaimEvidenceComparison",
    "ExtractedField",
    "FieldComparison",
    "SemanticComparisonResult",
    "ClaimComponent",
    "EvidenceSet",
    "EvidenceSetConflict",
    "EvidenceSetMember",
    "AnswerClaim",
    "AnswerSupportEdge",
    "ContextConflict",
    "ContextItem",
    "QueryTrace",
    "SupportRequirement",
    "LLMExtractionResult",
    "PropositionAnnotation",
    "PropositionCandidate",
    "SourceDocument",
    "SourceSegment",
]
