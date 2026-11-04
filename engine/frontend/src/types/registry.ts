// Stub types mirroring src/wittgenstein/schemas/*.py closely enough to type-check
// against API responses. Not codegen'd -- see ../../README.md. Keep in sync by hand
// with schemas/generated/*.schema.json when the backend schemas change.

export type EpistemicStatus =
  | "externally_established"
  | "manifest_conditioned_transfer"
  | "trace_integrity_condition"
  | "research_hypothesis"
  | "locally_validated"
  | "unsupported_or_retired";

export type TransferLevel =
  | "directly_matched"
  | "mechanistically_matched"
  | "partially_matched"
  | "not_applicable"
  | "insufficient_manifest_information";

export type PriorityTier = "high" | "medium" | "low" | "informational";

export interface EligibilityGateResult {
  gate_id: string;
  gate_kind: "required_manifest" | "disqualifying" | "strengthening" | "trace_observable";
  status: "satisfied" | "violated" | "unknown_insufficient_data";
  reason: string;
}

export interface ApplicabilityAssessment {
  assessment_id: string;
  failure_mechanism_id: string;
  evidence_record_ids: string[];
  manifest_id: string;
  trace_id_optional: string | null;
  eligibility_gate_results: EligibilityGateResult[];
  transfer_level: TransferLevel;
  matching_dimensions: string[];
  mismatching_dimensions: string[];
  unknown_dimensions: string[];
  explanation: string;
  allowed_claim_language: string;
  recommended_review_action_ids: string[];
  confidence: "high" | "medium" | "low" | "insufficient_data";
  created_at: string;
}

export interface RiskEvent {
  risk_event_id: string;
  trace_id: string;
  mechanism_id: string;
  trace_trigger_id: string | null;
  observed_evidence: string;
  transfer_level: TransferLevel;
  epistemic_status: EpistemicStatus;
  priority_tier: PriorityTier;
  causal_claim_allowed: boolean;
  reviewer_explanation: string;
  reviewer_action: string;
  source_evidence_links: string[];
  status: string;
}

// Added for the review-loop milestone -- docs/review-loop-implementation-plan.md.

export type ClaimSupportCandidateStatus =
  | "supported_candidate"
  | "partial_support_candidate"
  | "no_support_edge_found"
  | "conflict_candidate"
  | "unresolved";

export interface ContextItem {
  item_id: string;
  source_document_id: string | null;
  segment_id: string | null;
  excerpt: string | null;
  rank: number | null;
  relevance_score: number | null;
  is_query_related: boolean | null;
  is_answer_supporting: boolean | null;
  token_count: number | null;
  omission_reason: string | null;
}

export interface AnswerClaim {
  claim_id: string;
  text: string;
  extraction_method: "programmatic_rule_based" | "llm_extracted" | "fallback_whole_answer" | null;
}

export interface AnswerSupportEdge {
  claim_id: string;
  context_item_ids: string[];
  support_status: "supported" | "unsupported" | "contradicted" | "unknown";
  judged_by: "reviewer" | "unreviewed" | null;
  candidate_support_status: ClaimSupportCandidateStatus | null;
}

export type ReviewCondition = "undifferentiated" | "query_scoped" | "manifest_conditioned";

export type ReviewerAction =
  | "approve_sufficiently_supported"
  | "approve_with_qualification"
  | "request_additional_context"
  | "inspect_referenced_section"
  | "compare_competing_sources"
  | "check_date_version_jurisdiction"
  | "ask_clarifying_question"
  | "escalate_to_domain_expert"
  | "reject_as_unsupported"
  | "mark_unresolved"
  | "dismiss_as_low_priority"
  | "override_risk_priority";

export interface ReviewEvent {
  review_event_id: string;
  trace_id: string;
  reviewer_id: string;
  session_id: string | null;
  review_condition: ReviewCondition;
  displayed_risk_event_ids: string[];
  opened_evidence_item_ids: string[];
  reviewer_action: ReviewerAction;
  target_risk_event_id: string | null;
  target_claim_id: string | null;
  confidence: number | null;
  uncertainty: string | null;
  notes: string | null;
  timestamp: string;
  experience_measures: Record<string, number>;
}

// The response shape of POST /review/import-answer (api/routes/review.py). Left as a
// loosely-typed wrapper around the full QueryTrace/PipelineManifest/CorpusProfile/
// RiskEvent[] response rather than a fully-typed QueryTrace interface, which does not
// exist in this stub yet -- see ../../README.md.
export interface ImportAnswerResponse {
  trace: Record<string, unknown> & { answer_claims: AnswerClaim[]; answer_support_edges: AnswerSupportEdge[] };
  manifest: Record<string, unknown>;
  corpus_profile: Record<string, unknown> | null;
  risk_events: RiskEvent[];
  audited_non_applicable_assessments: ApplicabilityAssessment[];
  candidates: Record<string, unknown>[];
  annotations: Record<string, unknown>[];
  context_item_provenance: Record<string, string>;
}
