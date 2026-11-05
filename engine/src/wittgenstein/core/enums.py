"""Canonical, single-source vocabulary for every classification axis in the registry.

Every module that needs to express epistemic status, evidence grade, transfer level,
pipeline stage, etc. imports from here. Do not define parallel ad hoc string literals
elsewhere for these concepts -- that is exactly the "two lists describing the same
categories, drifting out of sync" failure this project is designed to avoid.
"""

from __future__ import annotations

from enum import Enum


class EpistemicStatus(str, Enum):
    """How strongly a failure mechanism's real-world applicability is established.

    This is the single most important guardrail enum in the system: UI-facing code
    must never present a mechanism as more certain than this status allows.
    """

    EXTERNALLY_ESTABLISHED = "externally_established"
    MANIFEST_CONDITIONED_TRANSFER = "manifest_conditioned_transfer"
    TRACE_INTEGRITY_CONDITION = "trace_integrity_condition"
    RESEARCH_HYPOTHESIS = "research_hypothesis"
    LOCALLY_VALIDATED = "locally_validated"
    UNSUPPORTED_OR_RETIRED = "unsupported_or_retired"


class EvidenceGrade(str, Enum):
    """Grade of a single evidence record, independent of the mechanism's overall status."""

    A1_DIRECT_CAUSAL_PEER_REVIEWED = "A1_direct_causal_peer_reviewed"
    A2_STRONG_COMPARATIVE_PEER_REVIEWED = "A2_strong_comparative_peer_reviewed"
    B1_MECHANISTIC_TRANSFER_PEER_REVIEWED = "B1_mechanistic_transfer_peer_reviewed"
    B2_COMPONENT_EVIDENCE_PEER_REVIEWED = "B2_component_evidence_peer_reviewed"
    C_PREPRINT_EMPIRICAL = "C_preprint_empirical"
    D_LOCAL_EMPIRICAL = "D_local_empirical"
    E_HYPOTHESIS = "E_hypothesis"


#: Grades that may support an `EpistemicStatus.EXTERNALLY_ESTABLISHED` claim.
ESTABLISHED_GRADE_FLOOR = {
    EvidenceGrade.A1_DIRECT_CAUSAL_PEER_REVIEWED,
    EvidenceGrade.A2_STRONG_COMPARATIVE_PEER_REVIEWED,
}


class TransferLevel(str, Enum):
    """How closely a manifest/trace's configuration matches an evidence record's envelope."""

    DIRECTLY_MATCHED = "directly_matched"
    MECHANISTICALLY_MATCHED = "mechanistically_matched"
    PARTIALLY_MATCHED = "partially_matched"
    NOT_APPLICABLE = "not_applicable"
    INSUFFICIENT_MANIFEST_INFORMATION = "insufficient_manifest_information"


class PipelineStage(str, Enum):
    """Ordered RAG pipeline lineage. Order matters: index position is used for lineage checks.

    Do not collapse adjacent stages -- "retrieved" (RETRIEVAL_CANDIDATES) is not
    "available to the generator" (PACKED_CONTEXT_ITEMS) is not "used correctly by the
    generator" (ANSWER_TO_EVIDENCE_SUPPORT_EDGES).
    """

    CORPUS_AVAILABLE = "corpus_available"
    PARSED_REPRESENTATION = "parsed_representation"
    INDEX_UNITS = "index_units"
    RETRIEVAL_CANDIDATES = "retrieval_candidates"
    RERANKED_CANDIDATES = "reranked_candidates"
    SELECTED_CONTEXT_ITEMS = "selected_context_items"
    PACKED_CONTEXT_ITEMS = "packed_context_items"
    ACTUAL_PROMPT_TOKEN_SPANS = "actual_prompt_token_spans"
    ANSWER_CLAIMS = "answer_claims"
    ANSWER_TO_EVIDENCE_SUPPORT_EDGES = "answer_to_evidence_support_edges"
    REVIEWER_JUDGMENTS = "reviewer_judgments"


#: Canonical stage order, for lineage/precondition checks (e.g. "was X logged before Y").
PIPELINE_STAGE_ORDER: list[PipelineStage] = list(PipelineStage)


class ActivationPolicy(str, Enum):
    """Default posture for whether a mechanism may fire in production triage.

    `SHADOW` / `MANIFEST_CONDITIONED` / `TRIAGE_ENABLED` are a three-stage graduation
    path added for mechanisms whose evidence has cleared the registry's epistemic
    threshold (`externally_established`) but whose *deployment-trust* level has not yet
    been separately earned -- reaching `externally_established` is necessary but never
    sufficient for full activation (see docs/registry-governance.md, "Externally
    established is necessary but not sufficient"). `ENABLED_BY_DEFAULT` and
    `ENABLED_WITH_MANIFEST_GATES` are the original, still-valid values (e.g.
    `PACK_OMISSION_OR_TRUNCATION` uses the latter) and are unaffected by this addition.

    - `SHADOW`: evaluated and logged (appears in audit output) but never contributes a
      priority-bearing `RiskEvent` -- observability only.
    - `MANIFEST_CONDITIONED`: contributes a `RiskEvent` once its manifest and trace
      gates all pass, but its priority is capped below `PriorityTier.HIGH` -- displayed,
      not yet fully trusted for queue ordering.
    - `TRIAGE_ENABLED`: full priority weight, once a `LocalValidationRecord` has
      established `reviewer_yield` for this mechanism in a specific deployment -- see
      docs/registry-governance.md.
    """

    ENABLED_BY_DEFAULT = "enabled_by_default"
    ENABLED_WITH_MANIFEST_GATES = "enabled_with_manifest_gates"
    SHADOW = "shadow"
    MANIFEST_CONDITIONED = "manifest_conditioned"
    TRIAGE_ENABLED = "triage_enabled"
    DISABLED_BY_DEFAULT_OR_RESEARCH_MODE = "disabled_by_default_or_research_mode"
    RETIRED = "retired"


class PeerReviewStatus(str, Enum):
    PEER_REVIEWED = "peer_reviewed"
    PREPRINT = "preprint"
    WORKSHOP = "workshop"
    TECHNICAL_REPORT = "technical_report"
    UNKNOWN = "unknown"


class StudyType(str, Enum):
    CAUSAL_INTERVENTION = "causal_intervention"
    CONTROLLED_COMPARISON = "controlled_comparison"
    OBSERVATIONAL_BENCHMARK = "observational_benchmark"
    ABLATION = "ablation"
    CASE_STUDY = "case_study"
    SURVEY_OR_META_ANALYSIS = "survey_or_meta_analysis"


class QuoteType(str, Enum):
    FINDING_STATEMENT = "finding_statement"
    METHOD_DESCRIPTION = "method_description"
    LIMITATION_STATEMENT = "limitation_statement"
    DEFINITION = "definition"
    RESULT_TABLE_CAPTION = "result_table_caption"


class VerificationStatus(str, Enum):
    """Whether the exact_quote and metadata on an EvidenceRecord have been checked
    against the primary source by a human reviewer.
    """

    VERIFIED = "verified"
    UNVERIFIED = "unverified"
    DISPUTED = "disputed"
    RETRACTED_SOURCE = "retracted_source"


class PipelineFailureObject(str, Enum):
    """What kind of thing the failure mechanism ultimately degrades."""

    RETRIEVAL_QUALITY = "retrieval_quality"
    CONTEXT_UTILIZATION = "context_utilization"
    CONTEXT_INTEGRITY = "context_integrity"
    ANSWER_CORRECTNESS = "answer_correctness"
    ANSWER_ATTRIBUTION = "answer_attribution"
    ANSWER_CONSISTENCY = "answer_consistency"


class GateResultStatus(str, Enum):
    """Outcome of evaluating a single manifest gate or trace observable predicate.

    Deliberately three-valued (not boolean): a predicate can be satisfied, violated,
    or unevaluable because the manifest/trace does not carry the field it needs. That
    third case must never be silently coerced into "satisfied" or "violated."
    """

    SATISFIED = "satisfied"
    VIOLATED = "violated"
    UNKNOWN_INSUFFICIENT_DATA = "unknown_insufficient_data"


class TraceStatus(str, Enum):
    COMPLETE = "complete"
    PARTIAL = "partial"
    MALFORMED = "malformed"


class PriorityTier(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFORMATIONAL = "informational"


class ConfidenceTier(str, Enum):
    """Deterministic, rule-derived confidence in an ApplicabilityAssessment.

    Never a fitted/opaque probability -- computed from the ratio of known to unknown
    envelope dimensions and the gate results, per `matching/transferability.py`. This
    is confidence in *how well the manifest/trace matches the evidence envelope*, not
    a "probability of hallucination."
    """

    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INSUFFICIENT_DATA = "insufficient_data"


class RiskEventStatus(str, Enum):
    OPEN = "open"
    UNDER_REVIEW = "under_review"
    CONFIRMED_ISSUE = "confirmed_issue"
    REVIEWED_NOT_AN_ISSUE = "reviewed_not_an_issue"
    DISMISSED = "dismissed"


class EvidenceSynthesis(str, Enum):
    """How a mechanism's linked evidence records, taken together, agree or disagree.

    Set on `FailureMechanism`, computed by a human reviewer from the set of linked
    `EvidenceRecord.direction` values -- never averaged into a single confidence number.
    See docs/registry-governance.md ("Conflicting studies").
    """

    CONVERGENT = "convergent"
    MIXED = "mixed"
    LIMITED = "limited"
    UNRESOLVED = "unresolved"


class EvidenceDirection(str, Enum):
    """Whether one EvidenceRecord supports, refutes, or is mixed/non-committal on its
    mechanism's causal claim. `NULL` is an explicit value (a record that speaks to the
    mechanism's setting without taking a clear position), distinct from omitting the
    field entirely -- this field is always required, never left unset.
    """

    SUPPORTS = "supports"
    REFUTES = "refutes"
    MIXED = "mixed"
    NULL = "null"


class LocalValidationStatus(str, Enum):
    """Lifecycle status of a LocalValidationRecord, independent of the mechanism's
    global epistemic_status -- see docs/registry-governance.md ("Local validation").
    """

    PROPOSED = "proposed"
    IN_PROGRESS = "in_progress"
    COMPLETED_SUPPORTS = "completed_supports"
    COMPLETED_DOES_NOT_SUPPORT = "completed_does_not_support"
    INCONCLUSIVE = "inconclusive"


class AdjudicationOutcome(str, Enum):
    """A per-case factual/evidence adjudication label, used only where a defensible
    adjudication target exists (docs/local-validation-protocol.md). Deliberately not a
    binary correct/incorrect: this project's intended domains contain changing,
    versioned, contested, and context-dependent information, so "the reviewer disagreed
    with the tool" and "the reviewer found the claim factually wrong" are not the same
    event, and must not be collapsed into one.
    """

    SUPPORTED = "supported"
    PARTIALLY_SUPPORTED = "partially_supported"
    UNSUPPORTED = "unsupported"
    CONTRADICTED = "contradicted"
    QUALIFICATION_OMITTED = "qualification_omitted"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"
    SOURCE_CONFLICT = "source_conflict"
    VERSION_DEPENDENT = "version_dependent"
    JURISDICTION_DEPENDENT = "jurisdiction_dependent"
    REQUIRES_CLARIFICATION = "requires_clarification"
    REQUIRES_EXPERT_ESCALATION = "requires_expert_escalation"
    UNRESOLVED = "unresolved"


class ReviewerAction(str, Enum):
    """The bounded set of actions a reviewer may take on a risk event or trace in a
    local-validation study (docs/local-validation-protocol.md). Never a forced
    binary correct/incorrect judgment.
    """

    APPROVE_SUFFICIENTLY_SUPPORTED = "approve_sufficiently_supported"
    APPROVE_WITH_QUALIFICATION = "approve_with_qualification"
    REQUEST_ADDITIONAL_CONTEXT = "request_additional_context"
    INSPECT_REFERENCED_SECTION = "inspect_referenced_section"
    COMPARE_COMPETING_SOURCES = "compare_competing_sources"
    CHECK_DATE_VERSION_JURISDICTION = "check_date_version_jurisdiction"
    ASK_CLARIFYING_QUESTION = "ask_clarifying_question"
    ESCALATE_TO_DOMAIN_EXPERT = "escalate_to_domain_expert"
    REJECT_AS_UNSUPPORTED = "reject_as_unsupported"
    MARK_UNRESOLVED = "mark_unresolved"
    DISMISS_AS_LOW_PRIORITY = "dismiss_as_low_priority"
    OVERRIDE_RISK_PRIORITY = "override_risk_priority"


class IntentSource(str, Enum):
    """Where a claimed query constraint (jurisdiction, population, date, comparator,
    scope, ...) actually came from. System-inferred intent is never treated as ground
    truth -- docs/local-validation-protocol.md, "User-intent responsiveness".
    """

    USER_STATED = "user_stated"
    SYSTEM_INFERRED = "system_inferred"
    REVIEWER_CONFIRMED = "reviewer_confirmed"
    UNRESOLVED = "unresolved"


class SegmentType(str, Enum):
    """Structural type of a Tier-0 SourceSegment, per
    docs/efficiency-and-processing-architecture.md -- created programmatically from
    existing document structure, never by an LLM.
    """

    HEADING = "heading"
    PARAGRAPH = "paragraph"
    SENTENCE = "sentence"
    LIST_ITEM = "list_item"
    TABLE_ROW = "table_row"
    TABLE_CELL = "table_cell"
    CAPTION = "caption"
    FOOTNOTE = "footnote"


class AnnotationCueType(str, Enum):
    """Tier-2 lightweight annotation cue types (schemas/proposition.py::PropositionAnnotation).
    Candidate cues only -- never a guaranteed semantic interpretation. See "RISK
    ANALYSIS" in docs/efficiency-and-processing-architecture.md: these back
    `research_hypothesis`/`experimental_review_cue` labels only, never a proof of error.
    """

    NEGATION = "negation"
    MODALITY_HEDGE = "modality_hedge"
    CONDITION = "condition"
    EXCEPTION = "exception"
    ATTRIBUTION = "attribution"
    TEMPORAL = "temporal"
    NUMERIC_UNIT = "numeric_unit"
    CROSS_REFERENCE = "cross_reference"


class ExtractionValidationStatus(str, Enum):
    """Outcome of a Tier-3 LLM extraction attempt
    (schemas/proposition.py::LLMExtractionResult). Fallback behavior
    (docs/efficiency-and-processing-architecture.md §7) always yields one of the
    non-`validated` values here rather than raising or guessing.
    """

    NOT_ATTEMPTED = "not_attempted"
    VALIDATED = "validated"
    VALIDATION_FAILED = "validation_failed"
    LLM_UNAVAILABLE = "llm_unavailable"


class CueEpistemicLabel(str, Enum):
    """How a programmatic risk cue (Tier 2) is allowed to be labeled -- never as proof
    of model error. See "RISK ANALYSIS",
    docs/efficiency-and-processing-architecture.md.
    """

    RESEARCH_HYPOTHESIS = "research_hypothesis"
    EXPERIMENTAL_REVIEW_CUE = "experimental_review_cue"


class ClaimSupportCandidateStatus(str, Enum):
    """A programmatic, pre-review classification linking one AnswerClaim to packed
    evidence (schemas/trace.py::AnswerSupportEdge.candidate_support_status) --
    deliberately not a final correctness verdict and never rendered as "the answer is
    false/faithful/hallucinated" (docs/review-loop-implementation-plan.md, "Answer
    claim extraction"). Kept as a field separate from the existing, reviewer-facing
    `AnswerSupportEdge.support_status` so a programmatic linking pass can never masquerade
    as a reviewer's judgment.
    """

    SUPPORTED_CANDIDATE = "supported_candidate"
    PARTIAL_SUPPORT_CANDIDATE = "partial_support_candidate"
    NO_SUPPORT_EDGE_FOUND = "no_support_edge_found"
    CONFLICT_CANDIDATE = "conflict_candidate"
    UNRESOLVED = "unresolved"
    # Added by docs/claim-linking-improvement-plan.md's field-comparison engine.
    # SUPPORTED_CANDIDATE (above) is kept for backward compatibility with the earlier
    # pure-lexical-overlap linker but is no longer produced by that engine --
    # DIRECT_SUPPORT_CANDIDATE is its replacement, since it now requires established
    # entity/predicate alignment and no critical mismatch, not just high token overlap.
    # NO_SUPPORT_EDGE_FOUND already covers the task brief's "no_support_found" --
    # kept as one name for one concept rather than adding a synonym.
    DIRECT_SUPPORT_CANDIDATE = "direct_support_candidate"
    QUALIFICATION_REQUIRED = "qualification_required"
    CONTRADICTION_CANDIDATE = "contradiction_candidate"
    # Added by docs/multi-passage-evidence-plan.md's evidence-set layer -- always the
    # relationship_status of an EvidenceSet (schemas/evidence_set.py), never written
    # back onto AnswerSupportEdge.candidate_support_status (which stays single-passage
    # only; see that doc's §5/§schema for why they are kept separate).
    COMPOSITE_SUPPORT_CANDIDATE = "composite_support_candidate"
    COMPOSITE_PARTIAL_SUPPORT_CANDIDATE = "composite_partial_support_candidate"
    COMPOSITE_QUALIFICATION_REQUIRED = "composite_qualification_required"
    COMPOSITE_CONFLICT_CANDIDATE = "composite_conflict_candidate"
    COMPOSITE_UNRESOLVED = "composite_unresolved"


class ReviewCondition(str, Enum):
    """Which of the three review conditions described in
    docs/local-validation-protocol.md ("Review conditions") a given `ReviewEvent` was
    collected under. Full retrieved evidence is available in every condition -- what
    varies is only whether/what risk-event tooling was shown, never the underlying
    evidence content.
    """

    UNDIFFERENTIATED = "undifferentiated"
    QUERY_SCOPED = "query_scoped"
    MANIFEST_CONDITIONED = "manifest_conditioned"


class ProvenanceStatus(str, Enum):
    """How a real-trace smoke-test case's source document(s) were obtained -- gates
    whether the document text itself may ever be committed to this repository
    (docs/real-trace-smoke-test-plan.md §2, "Provenance and licensing requirements").
    Only `SYNTHETIC_FICTIONAL` content (e.g. the existing widget-certification corpus)
    is safe to redistribute in `cases.example.json`; every other status implies the
    document text lives only at a git-excluded local path.
    """

    SYNTHETIC_FICTIONAL = "synthetic_fictional"
    USER_PROVIDED_LICENSE_CONFIRMED = "user_provided_license_confirmed"
    USER_PROVIDED_LICENSE_UNKNOWN = "user_provided_license_unknown"
    PUBLIC_DOMAIN_OR_OPEN_LICENSE = "public_domain_or_open_license"
    PENDING_PROVENANCE_REVIEW = "pending_provenance_review"


class PilotCoverageLabel(str, Enum):
    """Which pilot-variation category(ies) a real-trace smoke-test case is designed to
    exercise (docs/real-trace-smoke-test-plan.md's required pilot-variation list) -- a
    case may carry more than one. This is a case-authoring/coverage-tracking label, not
    a post-hoc diagnostic outcome -- contrast with `RetrievalDiagnosticLabel` etc. below.
    """

    STRUCTURED_DOCUMENT = "structured_document"
    NARRATIVE_DOCUMENT = "narrative_document"
    SHORT_DOCUMENT = "short_document"
    LONG_DOCUMENT = "long_document"
    MULTIPLE_SECTIONS = "multiple_sections"
    CONDITIONS_AND_EXCEPTIONS = "conditions_and_exceptions"
    CROSS_REFERENCES = "cross_references"
    TEMPORAL_OR_VERSION_INFORMATION = "temporal_or_version_information"
    MULTI_CLAIM_ANSWER = "multi_claim_answer"
    MULTI_PASSAGE_EVIDENCE = "multi_passage_evidence"
    SUPPORTED_ANSWER = "supported_answer"
    PARTIALLY_SUPPORTED_ANSWER = "partially_supported_answer"
    UNSUPPORTED_ANSWER = "unsupported_answer"
    CONFLICT_OR_UNRESOLVED = "conflict_or_unresolved"


class RetrievalDiagnosticLabel(str, Enum):
    """Manual labels a researcher applies to one retrieval candidate while inspecting a
    real-trace smoke-test case (docs/real-trace-smoke-test-plan.md §8). Never computed
    automatically -- the smoke-test runner only produces the inspection report these
    labels are applied to. Diagnostic labels about this pipeline's retrieval behavior --
    never factual-truth labels about the underlying document's content.
    """

    EVIDENCE_CANDIDATE_FOUND = "evidence_candidate_found"
    EVIDENCE_CANDIDATE_MISSED = "evidence_candidate_missed"
    CANDIDATE_TOO_BROAD = "candidate_too_broad"
    CANDIDATE_TOO_NARROW = "candidate_too_narrow"
    CANDIDATE_QUERY_RELATED_NON_SUPPORTING = "candidate_query_related_non_supporting"
    EVIDENCE_SOURCE_VERSION_MISMATCH = "evidence_source_version_mismatch"
    UNRESOLVED = "unresolved"


class ClaimLinkingDiagnosticLabel(str, Enum):
    """Manual labels a researcher applies to one claim/evidence link while inspecting a
    real-trace smoke-test case (docs/real-trace-smoke-test-plan.md §7). Never computed
    automatically -- `candidate_support_status` (core/enums.py::ClaimSupportCandidateStatus)
    is the programmatic signal these labels are assessing the quality of. Diagnostic
    labels about this pipeline's linking behavior -- never factual-truth labels about
    the underlying document's content.
    """

    USEFUL_SUPPORT_LINK = "useful_support_link"
    SPURIOUS_SUPPORT_LINK = "spurious_support_link"
    MISSED_SUPPORT_LINK = "missed_support_link"
    CLAIM_SPLIT_PROBLEM = "claim_split_problem"
    CLAIM_TOO_BROAD = "claim_too_broad"
    CLAIM_TOO_NARROW = "claim_too_narrow"
    UNRESOLVED = "unresolved"


class PropositionProvenanceDiagnosticLabel(str, Enum):
    """Manual labels for assessing Tier 0-2 source-span and annotation quality on a
    real-trace smoke-test case (docs/real-trace-smoke-test-plan.md §9). These are
    diagnostic labels about this pipeline's extraction/dependency behavior -- never
    factual-truth labels about the underlying document's content.
    """

    SOURCE_SPAN_VALID = "source_span_valid"
    SOURCE_SPAN_INVALID = "source_span_invalid"
    PROPOSITION_INDEPENDENTLY_INTERPRETABLE = "proposition_independently_interpretable"
    PROPOSITION_REQUIRES_DEPENDENCY = "proposition_requires_dependency"
    DEPENDENCY_AVAILABLE = "dependency_available"
    DEPENDENCY_MISSING = "dependency_missing"
    EXTRACTION_UNCERTAIN = "extraction_uncertain"


class ReviewInterfaceDiagnosticLabel(str, Enum):
    """Manual labels for assessing the review interface's (frontend/public/review.html)
    usability while working through a real-trace smoke-test case
    (docs/real-trace-smoke-test-plan.md §10). Diagnostic labels about this pipeline's
    review interface -- never factual-truth labels about the underlying document.
    """

    EVIDENCE_EASY_TO_LOCATE = "evidence_easy_to_locate"
    RISK_EXPLANATION_UNDERSTANDABLE = "risk_explanation_understandable"
    FULL_CONTEXT_SUFFICIENT = "full_context_sufficient"
    OMITTED_COMPETING_EVIDENCE_VISIBLE = "omitted_competing_evidence_visible"
    REVIEWER_ACTION_CLEAR = "reviewer_action_clear"
    UNNECESSARY_ALERT = "unnecessary_alert"
    MISSING_USEFUL_WARNING = "missing_useful_warning"
    UNRESOLVED = "unresolved"


class ComparisonFieldName(str, Enum):
    """The 17 structured field types `review/field_extraction.py` attempts to extract
    from a claim or candidate passage, per
    docs/claim-linking-improvement-plan.md §2. Not every field fires on every text --
    a field this extractor finds no signal for is `ABSENT` (ComparisonOutcome), not a
    failure.
    """

    ENTITY = "entity"
    PREDICATE = "predicate"
    OBJECT_VALUE = "object_value"
    POLARITY = "polarity"
    MODALITY = "modality"
    QUANTIFICATION = "quantification"
    POPULATION_SCOPE = "population_scope"
    CONDITION = "condition"
    EXCEPTION = "exception"
    TEMPORAL = "temporal"
    VERSION = "version"
    FREQUENCY_DURATION = "frequency_duration"
    NUMERIC_VALUE = "numeric_value"
    COMPARATOR = "comparator"
    UNIT = "unit"
    JURISDICTION = "jurisdiction"
    CROSS_REFERENCE = "cross_reference"


class ExtractionStatus(str, Enum):
    """Outcome of attempting to extract one ComparisonFieldName from one text.
    Distinct from ComparisonOutcome (which compares two sides) -- this describes one
    side's extraction attempt only.
    """

    EXTRACTED = "extracted"
    ABSENT = "absent"
    EXTRACTION_FAILED = "extraction_failed"
    EXTRACTION_CONFLICT = "extraction_conflict"


class ComparisonOutcome(str, Enum):
    """The four-state field-comparison lattice
    (docs/claim-linking-improvement-plan.md §3). ABSENT and UNKNOWN are deliberately
    distinct: ABSENT means the field is not expressed on at least one side (nothing to
    compare); UNKNOWN means it may be expressed on both sides but cannot be compared
    with sufficient confidence (extraction/normalization/scope uncertainty).
    """

    MATCH = "match"
    MISMATCH = "mismatch"
    ABSENT = "absent"
    UNKNOWN = "unknown"


class MismatchType(str, Enum):
    """Classification of a MISMATCH-outcome FieldComparison
    (docs/claim-linking-improvement-plan.md §4). A mismatch is never automatically a
    contradiction -- that inference is relationship classification's job, under
    stricter conditions (see ClaimSupportCandidateStatus.CONTRADICTION_CANDIDATE).
    """

    FREQUENCY_MISMATCH = "frequency_mismatch"
    DURATION_MISMATCH = "duration_mismatch"
    NUMERIC_MISMATCH = "numeric_mismatch"
    UNIT_MISMATCH = "unit_mismatch"
    COMPARATOR_MISMATCH = "comparator_mismatch"
    POLARITY_MISMATCH = "polarity_mismatch"
    MODALITY_ESCALATION = "modality_escalation"
    MODALITY_WEAKENING = "modality_weakening"
    SCOPE_BROADENING = "scope_broadening"
    SCOPE_NARROWING = "scope_narrowing"
    CONDITION_OMISSION = "condition_omission"
    EXCEPTION_OMISSION = "exception_omission"
    TEMPORAL_MISMATCH = "temporal_mismatch"
    VERSION_MISMATCH = "version_mismatch"
    JURISDICTION_MISMATCH = "jurisdiction_mismatch"
    ENTITY_BINDING_MISMATCH = "entity_binding_mismatch"
    PREDICATE_MISMATCH = "predicate_mismatch"
    VALUE_MISMATCH = "value_mismatch"


class SemanticComparisonOutcome(str, Enum):
    """Outcome of an optional semantic/NLI provider comparing one (claim, passage) pair
    (docs/claim-linking-improvement-plan.md §7). Never itself a factual judgment --
    `entailment_like`/`contradiction_like` raise support/contradiction *priority* in
    relationship classification, they do not assert truth.
    """

    ENTAILMENT_LIKE = "entailment_like"
    CONTRADICTION_LIKE = "contradiction_like"
    NEUTRAL = "neutral"
    UNCERTAIN = "uncertain"
    PROVIDER_ERROR = "provider_error"


class ComponentRequiredness(str, Enum):
    """Whether a `ClaimComponent` (schemas/evidence_set.py) is load-bearing for the
    claim -- docs/multi-passage-evidence-plan.md §4. CRITICAL components must be
    covered by some member of a candidate evidence set for composite support to be
    considered valid; INFORMATIONAL components (currently just cross-references) are
    never themselves treated as blocking.
    """

    CRITICAL = "critical"
    NON_CRITICAL = "non_critical"
    INFORMATIONAL = "informational"


class EvidenceSetConstructionMethod(str, Enum):
    """How an EvidenceSet was assembled -- docs/multi-passage-evidence-plan.md §9.
    Always deterministic/programmatic in this pass; the enum exists so a future
    semantic-assisted method (§"OPTIONAL SEMANTIC LAYER") has a place to be recorded
    without a schema change.
    """

    BOUNDED_GREEDY_SET_COVER = "bounded_greedy_set_cover"


class ExtractionQualityDiagnosticLabel(str, Enum):
    """Manual labels a researcher applies to one extracted field while reading a
    real-corpus evidence-set diagnostic report
    (docs/evidence-set-real-corpus-diagnostics-plan.md §6, category A). Never computed
    automatically. Diagnostic labels about this pipeline's extraction behavior -- never
    factual-truth labels about the underlying document's content.
    """

    EXTRACTION_CORRECT = "extraction_correct"
    EXTRACTION_PARTIALLY_CORRECT = "extraction_partially_correct"
    EXTRACTION_ARTIFACT = "extraction_artifact"
    SOURCE_SPAN_INVALID = "source_span_invalid"
    SOURCE_SPAN_INCOMPLETE = "source_span_incomplete"
    NORMALIZATION_CORRECT = "normalization_correct"
    NORMALIZATION_UNCERTAIN = "normalization_uncertain"
    PARSER_DISAGREEMENT = "parser_disagreement"
    UNSUPPORTED_INFERENCE = "unsupported_inference"
    UNRESOLVED = "unresolved"


class ConflictQualityDiagnosticLabel(str, Enum):
    """Manual labels a researcher applies to one `composite_conflict_candidate` (or
    single-passage `contradiction_candidate`/`conflict_candidate`) while reading a
    real-corpus evidence-set diagnostic report
    (docs/evidence-set-real-corpus-diagnostics-plan.md §6-7, category B). Never
    computed automatically -- the system never downgrades a conflict on its own on the
    basis of the extraction-confidence exposure these labels are judging. Diagnostic
    labels about this pipeline's conflict-detection behavior -- never factual-truth
    labels about the underlying document's content.
    """

    GENUINE_SOURCE_CONFLICT = "genuine_source_conflict"
    CLAIM_SOURCE_CONTRADICTION_CANDIDATE_JUSTIFIED = "claim_source_contradiction_candidate_justified"
    EVIDENCE_SET_MEMBER_CONFLICT_JUSTIFIED = "evidence_set_member_conflict_justified"
    APPARENT_CONFLICT_CAUSED_BY_EXTRACTION_ARTIFACT = "apparent_conflict_caused_by_extraction_artifact"
    APPARENT_CONFLICT_CAUSED_BY_VERSION_TIME_MISMATCH = "apparent_conflict_caused_by_version_time_mismatch"
    APPARENT_CONFLICT_CAUSED_BY_SCOPE_POPULATION_MISMATCH = "apparent_conflict_caused_by_scope_population_mismatch"
    CONFLICT_UNRESOLVED = "conflict_unresolved"
    NO_CONFLICT = "no_conflict"


class CrossReferenceClosureDiagnosticLabel(str, Enum):
    """Manual labels a researcher applies to one detected cross-reference marker while
    reading a real-corpus evidence-set diagnostic report
    (docs/evidence-set-real-corpus-diagnostics-plan.md §6/§8, category C;
    `docs/cross-reference-diagnostic-spec.md`). Never computed automatically beyond the
    system's own `CrossReferenceTargetState` (a distinct, automatic signal these labels
    add human judgment on top of -- e.g. whether the target was actually *needed*,
    which the system cannot determine). Diagnostic labels about this pipeline's
    cross-reference handling -- never factual-truth labels about the underlying
    document's content.
    """

    EXPLICIT_CROSS_REFERENCE_PRESENT = "explicit_cross_reference_present"
    CROSS_REFERENCE_TARGET_AVAILABLE_IN_CORPUS = "cross_reference_target_available_in_corpus"
    TARGET_RETRIEVED = "target_retrieved"
    TARGET_SELECTED = "target_selected"
    TARGET_PACKED = "target_packed"
    TARGET_OMITTED_BY_BUDGET = "target_omitted_by_budget"
    TARGET_NEEDED_TO_INTERPRET_CLAIM = "target_needed_to_interpret_claim"
    TARGET_ONLY_CLARIFIES_CLAIM = "target_only_clarifies_claim"
    DEPENDENCY_CLOSURE_COMPLETE = "dependency_closure_complete"
    DEPENDENCY_CLOSURE_INCOMPLETE = "dependency_closure_incomplete"
    CLOSURE_UNRESOLVED = "closure_unresolved"


class EvidenceSetSizingDiagnosticLabel(str, Enum):
    """Manual labels a researcher applies to one (claim, evidence-set-construction-attempt)
    pair while reading a real-corpus evidence-set diagnostic report
    (docs/evidence-set-real-corpus-diagnostics-plan.md §6/§9, category D). Never
    computed automatically -- the system reports uncovered components and a closed-form
    combination count (§"EVIDENCE-SET-SIZE DIAGNOSTIC"), never a judgment of whether a
    third item was actually required. Diagnostic labels about this pipeline's
    evidence-set-size behavior -- never factual-truth labels about the underlying
    document's content.
    """

    ONE_ITEM_SUFFICIENT = "one_item_sufficient"
    TWO_ITEMS_SUFFICIENT = "two_items_sufficient"
    THREE_ITEMS_PLAUSIBLY_REQUIRED = "three_items_plausibly_required"
    MORE_THAN_THREE_ITEMS_PLAUSIBLY_REQUIRED = "more_than_three_items_plausibly_required"
    MISSING_EVIDENCE_OUTSIDE_CANDIDATE_POOL = "missing_evidence_outside_candidate_pool"
    SET_SIZE_BOUND_PREVENTED_ADEQUATE_COMPOSITION = "set_size_bound_prevented_adequate_composition"
    CANDIDATE_SET_REDUNDANT = "candidate_set_redundant"
    COMPOSITION_UNRESOLVED = "composition_unresolved"


class ReviewerWorkflowDiagnosticLabel(str, Enum):
    """Manual labels a researcher applies at the case level while reading a real-corpus
    evidence-set diagnostic report
    (docs/evidence-set-real-corpus-diagnostics-plan.md §6, category E). Never computed
    automatically. Diagnostic labels about this pipeline's reviewer/workflow value --
    never factual-truth labels about the underlying document's content.
    """

    EVIDENCE_SET_EXPLANATION_USEFUL = "evidence_set_explanation_useful"
    CONFLICT_EXPLANATION_USEFUL = "conflict_explanation_useful"
    CROSS_REFERENCE_WARNING_USEFUL = "cross_reference_warning_useful"
    EXTRACTION_UNCERTAINTY_VISIBLE = "extraction_uncertainty_visible"
    LIKELY_FALSE_REASSURANCE = "likely_false_reassurance"
    LIKELY_UNNECESSARY_ESCALATION = "likely_unnecessary_escalation"
    REVIEWER_REQUESTED_FULL_CONTEXT = "reviewer_requested_full_context"
    REVIEWER_REQUESTED_SOURCE_EXPANSION = "reviewer_requested_source_expansion"
    REVIEWER_MARKED_UNRESOLVED = "reviewer_marked_unresolved"


class CrossReferenceTargetState(str, Enum):
    """Where (if anywhere) a detected cross-reference marker's target landed in the
    retrieval/packing pipeline -- computed automatically by
    `review/cross_reference_diagnostics.py` (docs/cross-reference-diagnostic-spec.md).
    A trace-observable fact, never a claim about whether the target was actually
    *needed* (that is `CrossReferenceClosureDiagnosticLabel`, a human judgment). Exactly
    the six states the milestone brief names: `IN_CORPUS` means a segment's location
    matched the marker text but that segment was never retrieved; `UNKNOWN` covers both
    "no segment matched at all" and "the trace isn't instrumented enough to check" --
    the brief's vocabulary does not distinguish these, and a marker whose target
    cannot be found is exactly the case human review is recommended for either way.
    """

    IN_CORPUS = "in_corpus"
    RETRIEVED = "retrieved"
    SELECTED = "selected"
    PACKED = "packed"
    OMITTED = "omitted"
    UNKNOWN = "unknown"


class CrossReferenceResolutionGranularity(str, Enum):
    """The finest granularity a cited cross-reference target's structure could actually
    be resolved at, capped at whatever the citation itself asked for -- computed by
    `review/cross_reference_diagnostics.py` alongside (never instead of)
    `CrossReferenceTargetState`. See docs/cross-reference-granularity-resolution-plan.md
    §5. `DOCUMENT`, `SUBPARAGRAPH`, and `TABLE` are part of the required vocabulary but
    are not produced by the current deterministic parser extension -- see that plan's
    §8, "What remains unresolved."
    """

    DOCUMENT = "document"
    ARTICLE = "article"
    PARAGRAPH = "paragraph"
    POINT = "point"
    SUBPARAGRAPH = "subparagraph"
    ANNEX = "annex"
    TABLE = "table"
    UNKNOWN = "unknown"


class ExactTargetAvailability(str, Enum):
    """Whether the *specific* cited paragraph/point -- when one was cited -- is what
    was actually found among a cross-reference target's matched segments, relative to
    `CrossReferenceResolutionGranularity`. A trace-observable structural fact, never a
    claim that the target is legally necessary, controlling, or that it resolves the
    answer claim. See docs/cross-reference-granularity-resolution-plan.md §5.
    """

    EXACT_TARGET_PRESENT = "exact_target_present"
    PARENT_ONLY_PRESENT = "parent_only_present"
    SIBLING_ONLY_PRESENT = "sibling_only_present"
    BROADER_CONTEXT_PRESENT = "broader_context_present"
    TARGET_MISSING = "target_missing"
    TARGET_UNKNOWN = "target_unknown"


# --- Live self-aware pipeline (docs/live-pipeline-plan.md) ---------------------------


class EmbedderFamily(str, Enum):
    """How an embedding backend turns text into a vector -- recorded in every live
    manifest because the awareness probes' interpretation depends on it (e.g. a static
    model has no input-length truncation but dilutes long passages; a contextual model
    with a fixed input window silently drops text past that window).
    """

    STATIC = "static"
    CONTEXTUAL = "contextual"
    HASHING_TEST_ONLY = "hashing_test_only"
    EXTERNAL = "external"
    """A caller's own model, reached through a callback; nothing about it is assumed."""


class RetrievalChannel(str, Enum):
    """How a candidate entered the pool. A candidate found by more than one channel
    carries every channel that found it -- never collapsed to one."""

    LEXICAL = "lexical"
    DENSE = "dense"
    FACET = "facet"
    REMEDIATION = "remediation"


class KPolicy(str, Enum):
    FIXED = "fixed"
    ADAPTIVE = "adaptive"


class CandidateFate(str, Enum):
    """Exactly one fate per pool candidate, recorded with a reason. `NOT_REACHED`
    means selection stopped before evaluating it -- distinct from being judged below
    the cutoff (`BELOW_ELBOW`)."""

    SELECTED = "selected"
    PULLED_IN = "pulled_in"
    SKIPPED_REDUNDANT = "skipped_redundant"
    BELOW_ELBOW = "below_elbow"
    OMITTED_BUDGET = "omitted_budget"
    NOT_REACHED = "not_reached"


class PullInReason(str, Enum):
    SEVERED_NEIGHBOR = "severed_neighbor"
    CROSS_REFERENCE_TARGET = "cross_reference_target"
    DEFINITION = "definition"


class QuestionType(str, Enum):
    FACTOID = "factoid"
    ENUMERATION = "enumeration"
    COMPARISON = "comparison"
    EXPLANATION = "explanation"
    UNKNOWN = "unknown"


class ConstraintKind(str, Enum):
    """A hard constraint in the query that similarity search may not respect."""

    NEGATION = "negation"
    NUMBER = "number"
    DATE = "date"
    IDENTIFIER = "identifier"
    COMPARATOR = "comparator"
    QUOTED = "quoted"
    MODALITY = "modality"


class FlagOrigin(str, Enum):
    """Whether a flag is about the source text itself or about what the pipeline did
    with it. A flag can be both (e.g. a passage that opens with an anaphor -- text --
    whose antecedent the chunker separated from it -- pipeline)."""

    TEXT = "text"
    PIPELINE = "pipeline"
    TEXT_AND_PIPELINE = "text_and_pipeline"


class FlagKind(str, Enum):
    """Every awareness check's flag type. Embedding probes (D*) and gap signals (G*)
    are measured observations of one run; text-artifact kinds map onto registry
    mechanisms where one exists (see live/flags.py::REGISTRY_LINKS)."""

    # Embedding probes
    FACET_DOMINANCE = "facet_dominance"
    CONSTRAINT_INSENSITIVE = "constraint_insensitive"
    EMBEDDER_TRUNCATION = "embedder_truncation"
    DILUTION = "dilution"
    RETRIEVER_DISAGREEMENT = "retriever_disagreement"
    NEAR_MISS = "near_miss"
    WEAK_BEST_MATCH = "weak_best_match"
    AMBIGUOUS_CUTOFF = "ambiguous_cutoff"
    FLAT_TOP = "flat_top"
    # Evidence gaps
    FACET_UNCOVERED = "facet_uncovered"
    CROSS_REFERENCE_NOT_FOLLOWED = "cross_reference_not_followed"
    SEVERED_CONTEXT = "severed_context"
    BUDGET_OMISSION = "budget_omission"
    ENUMERATION_INCOMPLETE = "enumeration_incomplete"
    DEFINITION_NOT_IN_CONTEXT = "definition_not_in_context"
    REDUNDANCY = "redundancy"
    # Text artifacts (ported risk-triage detectors)
    CONDITION_SATELLITE = "condition_satellite"
    CONCESSION_SATELLITE = "concession_satellite"
    NEGATION_SCOPE = "negation_scope"
    BACKWARD_REFERENCE = "backward_reference"
    UNRESOLVED_REFERENCE = "unresolved_reference"
    # Answer verification
    MODAL_STRENGTH_MISMATCH = "modal_strength_mismatch"
    ANSWER_SENTENCE_UNSUPPORTED = "answer_sentence_unsupported"
    QUANTITY_MISMATCH = "quantity_mismatch"
    POPULATION_QUALIFIER_DROPPED = "population_qualifier_dropped"
    RECOMMENDATION_STRENGTH_DROPPED = "recommendation_strength_dropped"
    # Evidence consistency
    CONTEXT_CONFLICT = "context_conflict"


class FlagDisposition(str, Enum):
    """What the user should do with a flag. `HANDLED` means the pipeline already acted
    on the observation (and says what it did); it must never be rendered as a warning."""

    NEEDS_REVIEW = "needs_review"
    HANDLED = "handled"
    INFORMATIONAL = "informational"


class FlagSeverity(str, Enum):
    INFO = "info"
    CAUTION = "caution"
    WARNING = "warning"


class CheckOutcome(str, Enum):
    """Result of running one awareness check on one run. `NOT_APPLICABLE` (e.g. the
    negation probe on a query with no negation) is distinct from `PASSED`."""

    PASSED = "passed"
    FLAGGED = "flagged"
    NOT_APPLICABLE = "not_applicable"


class LiveEventType(str, Enum):
    """Event types on the live pipeline's stream (live/events.py). The frontend's
    TypeScript types are generated from these models, so the two cannot drift."""

    RUN_STARTED = "run.started"
    QUERY_ANALYZED = "query.analyzed"
    MODEL_PROFILE = "model.profile"
    STAGE = "stage"
    FIELD = "field"
    CANDIDATES = "candidates"
    CHECK = "check"
    FLAG = "flag"
    FLAG_UPDATED = "flag.updated"
    DECISION = "decision"
    CONTEXT_PACKED = "context.packed"
    ANSWER_DELTA = "answer.delta"
    ANSWER_SENTENCE = "answer.sentence"
    PIPELINE_COMPLETED = "pipeline.completed"
    RUN_COMPLETED = "run.completed"
    ERROR = "error"
