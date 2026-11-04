# Implementation Plan

Status: initial build complete (registry, matching engine, CLI/API, tests); binding
governance decisions applied 2026-09-09 (see §8); two literature-review passes
completed 2026-09-09 (`docs/literature-review-results.md`,
`docs/literature-review-second-review-results.md`); REP_SEGMENTATION_GRANULARITY_MISMATCH
activation-policy decision applied 2026-09-09 (see §9); the multidimensional
local-validation protocol was designed 2026-09-09 (see §10) -- no mechanism has been
promoted to `TRIAGE_ENABLED`; no human-subjects study interface has been built. This
document is written before code, per project instructions, and updated if the plan
materially changes during implementation.

## 0. Repository status at start

No prior project files existed at this path. This is a fresh, standalone, open-source
repository (`wittgenstein-rag-reliability`), nested inside a parent research workspace
but with its own git history and its own conventions — it is a software product/registry,
not a "research track" of the parent repo, so it does not follow the parent's
track-based `docs/repo_usage.md` conventions.

A sibling artifact in the parent workspace (`risk_triage_edge_cases.txt`) documents
edge cases from an unrelated proof-of-concept classifier (formalization-drift risk
triage, not RAG). Per the user, it "may or may not be useful." Several of its
generalizable engineering lessons are applicable here and are adopted as design
constraints, cited inline where relevant:

- Avoid boolean collapse of distinct outcomes (e.g. "dropped" vs "severed" vs
  "present") — informs `TransferLevel` and eligibility-gate results being multi-valued,
  not boolean.
- Avoid two lists/tables that are supposed to describe "the same categories" on two
  sides of a comparison and can drift out of sync — informs keeping a single canonical
  enum/table for each classification axis (epistemic status, evidence grade, transfer
  level, pipeline stage) referenced everywhere, never duplicated.
- Distinguish "a trigger condition is present" from "a trigger condition is present
  AND well-formed enough to support the claim being made" — informs manifest gates
  being explicit boolean predicates over structured fields, never inferred from loose
  pattern matching.
- Prefer deterministic, inspectable rules over ML/embedding heuristics for primary
  eligibility decisions — matches the task's explicit requirement.
- When retiring/rejecting something, remove/mark it explicitly rather than leaving a
  silently inert entry — informs `unsupported_or_retired` as a first-class status
  rather than deletion, and informs disabled-by-default research-hypothesis records
  carrying an explicit `default_activation_policy`.

## 1. Scope of this milestone

Build the registry-first backend and schema layer described in the task: a versioned,
evidence-graded registry of RAG failure mechanisms, plus schemas/tooling to match a
pipeline manifest + query trace to only the mechanisms whose experimental
prerequisites are actually present. No chat-with-documents product. No opaque
hallucination score. Frontend is a documented stub only.

## 2. Stack

Python 3.11+, `uv`, FastAPI, Pydantic v2, SQLModel (SQLAlchemy 2.x) + SQLite for dev,
Alembic, pytest, Ruff, mypy, Typer, JSON Schema export via Pydantic's built-in
`model_json_schema()`. Frontend: React/TS stub only, no build effort spent.

## 3. Core conceptual model (see `docs/architecture.md` for full detail)

Eight entities, kept structurally and conceptually separate (separate Pydantic models,
separate DB tables, never merged into a single "finding" blob):

`FailureMechanism`, `EvidenceRecord`, `ExperimentalEnvelope` (embedded in evidence
records, reused for manifest/trace comparison), `ManifestGate` (registry-side rule
attached to a mechanism), `TransferabilityAssessment`/`ApplicabilityAssessment`,
`TraceTrigger` (registry-side rule), `ReviewAction`, `LocalValidationRecord`.

Pipeline lineage is modeled as an explicit ordered stage enum (`PipelineStage`) used
consistently across `PipelineManifest`, `QueryTrace`, and `FailureMechanism.pipeline_stage`
so "retrieved" vs "available to generator" vs "used correctly" are never collapsed:

```
corpus_available -> parsed_representation -> index_units -> retrieval_candidates ->
reranked_candidates -> selected_context_items -> packed_context_items ->
actual_prompt_token_spans -> answer_claims -> answer_to_evidence_support_edges ->
reviewer_judgments
```

## 4. Epistemic guardrails enforced in code, not just docs

- `EpistemicStatus` enum is the only vocabulary for status; `unsupported_or_retired`
  is a real status, not a deleted row.
- A **validator** (`registry/validator.py`) rejects, at load time, any seed/production
  record where `epistemic_status="externally_established"` unless at least one linked
  `EvidenceRecord` has `peer_review_status="peer_reviewed"` and
  `evidence_grade in {A1_direct_causal_peer_reviewed, A2_strong_comparative_peer_reviewed}`.
- A separate check rejects activation (non-`disabled_by_default_or_research_mode`
  `default_activation_policy`) for any evidence record whose `verification_status`
  is not `verified` or which contains a literal `TODO` sentinel in a quote/citation
  field.
- `research_hypothesis` records cannot be assigned `A1`/`A2` grades — enforced by a
  Pydantic model validator on `FailureMechanism`, not just convention.
- `matching/eligibility.py` returns `insufficient_manifest_information` (a real
  `TransferLevel` value) whenever a manifest gate depends on a field whose manifest
  value is the literal `unknown`/`None` sentinel — it never defaults to "assume
  absent" or "assume present."

## 5. Deterministic matching engine

`matching/eligibility.py` evaluates, per mechanism, in order: required manifest
predicates -> disqualifying predicates -> (if query-level) required trace observables
-> strengthening predicates. Pure functions over typed dataclasses extracted from the
manifest/trace; no LLM or embedding call anywhere in this path. `matching/transferability.py`
computes `TransferLevel` by comparing the manifest/trace-derived envelope fields against
each linked evidence record's `ExperimentalEnvelope`, field by field, producing
matching/mismatching/unknown dimension lists (never a single opaque similarity score).
`matching/explanation.py` renders the reviewer-facing text and enforces allowed-vs-
prohibited claim language per epistemic status (e.g. a `trace_integrity_condition`
mechanism's explanation can never contain causal language unless a causal evidence
link or local causal validation is attached).

## 6. Build order (mirrors task's IMPLEMENTATION ORDER)

1. Scaffolding, `pyproject.toml`, tool config, doc stubs (this step).
2. `core/enums.py` (all enums), `core/identifiers.py`, `core/provenance.py`,
   `core/versioning.py`.
3. `schemas/*.py` Pydantic v2 models + `exports/json_schema.py` to dump JSON Schema
   files under a `schemas/generated/` (gitignored except a committed snapshot).
4. `data/registry/*.seed.yaml` + `registry/loader.py` + `registry/validator.py`
   (raises `RegistrySeedIntegrityError` on any epistemic violation).
5. `matching/eligibility.py`, `matching/transferability.py`, `matching/explanation.py`
   + unit tests for hard gating.
6. `trace/validator.py`, `trace/lineage.py`, `trace/packing.py`.
7. `db/models/*` (SQLModel), `db/session.py`, Alembic env + first migration.
8. `cli/main.py` (Typer) wiring registry/manifest/trace/applicability/schemas/examples
   commands, and `registry/dossier.py` for the Markdown dossier generator.
9. `api/app.py` + `api/routes/*` (FastAPI), `services/*` as the layer between routes
   and registry/matching/trace modules (routes stay thin).
10. Five synthetic manifest/trace pairs under `data/examples/` covering the scenarios
    listed in the task (single-passage, multi-passage+rerank+budget, parent-child with
    omitted cross-reference, compression-enabled, query-rewriting multi-hop).
11. Tests (unit + integration) written alongside each feature above, not deferred to
    the end; `tests/conftest.py` provides the loaded seed registry as a fixture.
12. `ruff format`, `ruff check`, `mypy`, `pytest`, `scripts/export_json_schemas.py`,
    `scripts/validate_seed_registry.py`.
13. Docs: `architecture.md`, `research-protocol.md`, `evidence-grading.md`,
    `manifest-spec.md`, `trace-spec.md`, `registry-spec.md`,
    `literature-review-protocol.md`, `registry-governance.md`, ADRs, dossier README,
    top-level `README.md`, `CONTRIBUTING.md`, `CODE_OF_CONDUCT.md`, `CITATION.cff`.
14. Frontend stub (`frontend/README.md` + typed stub files, no build).
15. Final summary: files created, commands run, results, limitations, next milestone.

## 7. Explicit non-goals for this milestone

No web scraping/automated literature ingestion. No LLM- or embedding-based primary
eligibility scoring. No polished frontend. No claim that the seed registry (7 active +
11 research-hypothesis mechanisms) is exhaustive — it is explicitly a bootstrap
registry, documented as such in `data/registry/README.md` and the top-level README.
No fabricated quotes, effect sizes, or venues: every seed `EvidenceRecord` sourced from
a real candidate paper in the task is left with `verification_status: unverified` and
literal `TODO` markers on unconfirmed fields (quote, quote_location, effect_size_text)
unless/until a primary-source PDF pass is done in a later milestone. This is enforced,
not just stated: the registry validator refuses production activation for any such
record.

## 8. Binding governance decisions applied (2026-09-09)

A second pass, driven by explicit binding project decisions rather than open design
choices, before any application logic (retriever, frontend, linguistic classifiers)
was implemented. Repository placement was confirmed unchanged (this skeleton remains
canonical; no second repository was created). Changes:

- **Schema**: added `FailureMechanism.evidence_synthesis` (`EvidenceSynthesis`:
  `convergent`/`mixed`/`limited`/`unresolved`, required, constrained to `unresolved`
  for `research_hypothesis`) and `EvidenceRecord.direction` (`EvidenceDirection`:
  `supports`/`refutes`/`mixed`/`null`, required). Expanded `LocalValidationRecord` with
  `external_evidence_status`, `local_validation_status`, `deployment_priority`, and the
  preregistration/precision/recall/reviewer-yield/uncertainty/replication fields needed
  for `meets_promotion_bar()`. Added `CorpusProfile.evidence_dispersion_metrics`.
- **Validator**: rewrote `_check_established_status_requires_a_grade_evidence` to the
  two-path evidence-threshold rule (one A1, or >=2 independent A1/A2, all RAG-native
  and `direction=supports`) — see `docs/evidence-grading.md`, "Evidence thresholds".
- **Seed data corrected accordingly**: `RET_HARD_DISTRACTOR`,
  `RET_MULTIHOP_SUPPORT_INCOMPLETE`, and `GEN_UNSUPPORTED_DESPITE_CONTEXT` reclassified
  `externally_established` -> `manifest_conditioned_transfer` (each had exactly one
  A2-grade record, which the new rule no longer treats as sufficient alone). All 18
  mechanisms now carry `evidence_synthesis`; all 9 evidence records now carry
  `direction`. Registry version bumped 0.1.0 -> 0.2.0 (a `MAJOR`-class change per
  `docs/registry-spec.md`'s bump discipline, since existing mechanisms' `epistemic_status`
  changed) for every record, for internal consistency across the batch.
- **Vocabulary decision, deliberately not implemented as new enums**: the
  "directly_rag_established / manifest_conditioned_transfer / untransferred" framing is
  documented as a mapping onto the *existing* `EpistemicStatus`/`TransferLevel` model
  (`docs/evidence-grading.md`) rather than added as parallel enum values — adding a
  second vocabulary for the same distinction is exactly the failure class this project
  guards against (see §0 above). The RAG-native requirement this framing implies *is*
  enforced, in the validator rule above.
- **Docs**: added `CLAUDE.md`; updated `registry-spec.md` (entities table, direction/
  synthesis fields), `evidence-grading.md` (thresholds, transfer-vocabulary mapping),
  `registry-governance.md` (mechanism/subtype rule, corpus-properties rule, local-
  validation promotion requirements), `manifest-spec.md` (CorpusManifest vs.
  CorpusProfile), `trace-spec.md` (explicit lineage list), `research-protocol.md`
  (schema-field cross-references), `literature-review-protocol.md` (require explicit
  `rag_presence`/`direction` at extraction time), `architecture.md`,
  `data/registry/README.md`.
- **Tests**: updated the three test-fixture builder helpers
  (`tests/unit/test_registry_validation.py`, `test_explanations.py`,
  `test_transferability.py`) for the two new required fields; added 6 new tests
  covering the two-path threshold rule, the RAG-native requirement, and
  direction-gating in `test_registry_validation.py`; added
  `TestLocalValidationRecordSelfValidation` (4 tests) for `meets_promotion_bar()`;
  fixed one integration test (`test_seed_registry_api.py::test_get_mechanism`) whose
  hardcoded `externally_established` assertion was invalidated by the seed
  reclassification.

## 9. `REP_SEGMENTATION_GRANULARITY_MISMATCH` activation-policy decision (2026-09-09)

Following the two literature-review passes (§8's successor work, in
`docs/literature-review-results.md` and `docs/literature-review-second-review-results.md`),
`REP_SEGMENTATION_GRANULARITY_MISMATCH` became the first mechanism to reach
`externally_established` with fully `verified` evidence. This section records the
registry-governance decision on what that does and does not unlock — full detail in
`docs/registry-governance.md`, "Activation policy: a three-stage graduation path."

- **Schema**: `ActivationPolicy` (`core/enums.py`) gained three additive values —
  `SHADOW`, `MANIFEST_CONDITIONED`, `TRIAGE_ENABLED` — forming an explicit graduation
  path for mechanisms whose evidence has cleared `externally_established` but whose
  deployment-trust level has not yet been separately earned. `ENABLED_BY_DEFAULT` and
  `ENABLED_WITH_MANIFEST_GATES` are unchanged (`PACK_OMISSION_OR_TRUNCATION` still uses
  the latter, unaffected).
- **Service layer**: `services/applicability_service.py::derive_risk_events` now
  distinguishes never-priority-bearing (`SHADOW`) from priority-capped
  (`MANIFEST_CONDITIONED`, capped below `PriorityTier.HIGH` via the new
  `_capped_priority_tier` helper) from fully-trusted (`TRIAGE_ENABLED`,
  `ENABLED_BY_DEFAULT`, `ENABLED_WITH_MANIFEST_GATES`) activation. No change to
  `matching/eligibility.py` was needed — its existing
  `_eval_rep_segmentation_granularity_mismatch` evaluator already implemented all five
  of this mechanism's activation-gate conditions (independently-segmented units known
  and non-whole-document; chunking/retrieval-unit known; a trace-observed
  boundary-crossing dependency; unknown manifest data yields insufficient information,
  never an assumed pass).
- **Bounded reviewer language**: `matching/explanation.py` gained a small, additive
  per-mechanism override map (`_MECHANISM_BOUNDED_CLAIM_LANGUAGE`) so this mechanism's
  risk events use one pre-approved sentence rather than the generic
  `externally_established` text, without touching that generic text for any other
  (future) mechanism reaching the same status.
- **Data**: `REP_SEGMENTATION_GRANULARITY_MISMATCH.default_activation_policy` ->
  `manifest_conditioned` (from `disabled_by_default_or_research_mode`); its
  `registry_version` bumped 0.2.0 -> 0.3.0 (only this mechanism's own per-record
  version field; no other mechanism changed). No evidence record, validator threshold,
  or other mechanism was touched.
- **Tests**: new `tests/integration/test_rep_segmentation_activation_policy.py` (11
  tests) covering all five gate conditions' activate/non-activate behavior, full risk
  event field/bounded-language/no-causal-claim coverage, priority capping (and its
  absence for `TRIAGE_ENABLED`/`ENABLED_WITH_MANIFEST_GATES`, confirming backward
  compatibility), and that no other mechanism's activation policy changed. Three
  pre-existing tests were updated because their assumptions were the direct target of
  this decision (`test_default_output_excludes_disabled_mechanisms`,
  `test_all_evidence_backed_activation_is_currently_disabled_pending_verification`, and
  the second-review pass's own
  `test_rep_segmentation_externally_established_still_disabled_by_default`, renamed to
  `test_rep_segmentation_activation_policy_is_manifest_conditioned_not_triage_enabled`).

## 10. Multidimensional local-validation protocol design (2026-09-09)

Designs, but does not run, the study that would be needed before any mechanism could be
considered for `ActivationPolicy.TRIAGE_ENABLED` (§9). No mechanism was promoted; no
human-subjects study interface was built.

- **Core principle**: this project is not evaluated solely by recovery of a fixed
  factual ground truth. The intended domains contain changing, versioned, contested,
  and context-dependent information. Factual/evidence adjudication remains part of the
  evaluation wherever a defensible target exists, but it is one of six independent
  outcome layers, never the sole endpoint and never collapsed into one score.
- **Schema**: `core/enums.py` gained three vocabulary enums (`AdjudicationOutcome`, 12
  values including `unresolved`/`version_dependent`/`jurisdiction_dependent`;
  `ReviewerAction`, 11 bounded actions; `IntentSource`, 4 values). `schemas/review.py`
  gained six evidence-layer sub-models (`AdjudicatedTraceEvidence`,
  `ContextualJudgmentEvidence`, `BehavioralWorkflowEvidence`,
  `AutonomyAndTrustEvidence`, `AlertFatigueEvidence`, `FalseReassuranceAnalysis`) and
  extended `LocalValidationRecord` with `reviewer_population`, `corpus_slices`,
  `study_design`, `outcome_definitions`, `uncertainty_or_intervals`,
  `unresolved_limitations`, and the six evidence-layer fields, plus a new
  `meets_triage_promotion_bar()` method -- deliberately separate from the existing
  `meets_promotion_bar()`, which governs the different `locally_validated` epistemic-
  status axis. No `QueryTrace`/`RiskEvent` schema change was made -- `IntentSource` and
  `AdjudicationOutcome` are reviewer-study-time vocabulary, not trace-time fields, per
  `docs/trace-spec.md`.
- **Docs**: new `docs/local-validation-protocol.md` (the general protocol: core
  principle, six outcome layers, review conditions 1-3, user-intent responsiveness,
  reviewer actions, factual-adjudication design, alert-fatigue/false-reassurance/
  unnecessary-escalation definitions, promotion summary), `docs/segmentation-local-validation.md`
  (the same protocol applied concretely to `REP_SEGMENTATION_GRANULARITY_MISMATCH`),
  `docs/reviewer-measures.md` (the measurement dictionary: every measure name, its
  field, primary/secondary outcome classification, example survey items, open-ended
  questions). Updated `docs/research-protocol.md`, `docs/registry-governance.md`
  (ten-point `TRIAGE_ENABLED` checklist), `docs/evidence-grading.md` (adjudication vs.
  evidence-grade distinction), `docs/trace-spec.md` (vocabulary/schema boundary), and
  `CLAUDE.md`.
- **Fixtures**: `data/examples/local_validation/` -- 3 manifests, 11 trace scenarios,
  a `scenarios.json` catalog, and a `README.md`. Six scenarios activate
  `REP_SEGMENTATION_GRANULARITY_MISMATCH`, five do not, deliberately including cases
  where the mechanism fires but rejection is not the right reviewer action, one
  false-reassurance probe, one unnecessary-escalation probe, and two non-segmentation
  scenarios (underspecified intent, unaddressed source conflict) for the protocol's
  other outcome layers. All content is fictional (a "widget certification program").
- **Tests**: `tests/unit/test_registry_validation.py` gained 16 schema-level tests
  covering all 13 applicable numbered test requirements from this milestone's brief
  (adjudication optionality, layer independence, the outcome vocabulary, evidence-grade
  isolation, `meets_triage_promotion_bar()` behavior including its two blocking
  conditions, deployment-priority independence, usefulness-without-falseness,
  negative-result preservation, alert-fatigue/autonomy measurability, and intent-source
  distinctness). New `tests/unit/test_local_validation_protocol_examples.py` loads and
  cross-validates all 11 fixtures against the real registry and eligibility engine
  (requirement 14: every activating scenario's `RiskEvent` carries full
  explainability and the exact bounded language) -- confirming the hand-authored
  fixtures' predicted activation outcomes match the real
  `matching/eligibility.py` evaluator in all 11 cases.

## 11. Vertical slice on LlamaIndex: deterministic-first ingestion, retrieval, packing (2026-09-10)

Implements the concrete processing pipeline behind the schemas/registry built in
milestones 1-10: a lightweight, mostly-programmatic corpus-time indexer and
query-time retrieval/packing/trace pipeline, with LLM use confined to a narrow,
cached, optional Tier-3 role. No mechanism, evidence record, validator threshold, or
registry schema was touched.

- **Core principle**: `docs/efficiency-and-processing-architecture.md` (written before
  any code, per the milestone brief) sets a strict processing hierarchy --
  deterministic parsing before lightweight NLP/rules before lexical retrieval before
  batched embeddings before small targeted models before a large LLM as a last-resort,
  narrowly-scoped fallback. A full no-LLM baseline mode is a first-class requirement,
  not a degraded path: `proposition.llm_extraction.extract_tier3` treats "no client
  configured" and "client reported unavailable" identically, so the demo's baseline
  mode is not a separate code branch from the general LLM-unavailable fallback.
- **Tier 0 (deterministic parsing)**: `ingestion/parser.py`, a dependency-free
  regex/line-oriented parser producing `SourceSegment`s (heading/paragraph/sentence/
  list_item/table_row/caption/footnote) with exact character-offset provenance for
  every segment type -- fixed a class of offset bugs during this milestone where
  heading/caption/footnote/list_item/table_row segments recorded the *raw* line's
  offsets while storing *stripped* text (e.g. a HEADING segment's `char_start`
  pointed at `"# Heading"` while `text` held `"Heading"`); caught by
  `tests/unit/test_ingestion_parser.py::test_segment_offsets_index_into_original_text`
  round-tripping every segment against the source document, now enforced for all
  seven segment types via a shared `_local_offset` helper.
- **LlamaIndex integration**: `ingestion/llamaindex_adapter.py` uses
  `llama_index.core.Document`/`TextNode`/`SentenceSplitter` (the `llama-index-core`
  package only, not the full metapackage, to avoid pulling in vector-store/embedding
  extras) strictly as an ingestion adapter -- `nodes_to_source_segments` converts every
  node into a canonical `SourceSegment` immediately and completely; no `TextNode` or
  `NodeRelationship` object is retained past that function, and external LlamaIndex
  node ids never replace Wittgenstein's own `segment_id` assignment.
- **Tier 1/2 (rule-based candidates and annotations)**: `proposition/candidates.py`
  splits a Tier-0 segment into `PropositionCandidate`s on semicolons/conjunctions/
  relative clauses/condition markers (regex-based, `is_ambiguous` flags a Tier-3
  escalation trigger, never a semantic judgment). `proposition/annotations.py` tags
  negation/modality/condition/exception/attribution/temporal/numeric-unit/
  cross-reference cues, always labeled `research_hypothesis` or
  `experimental_review_cue` (`CueEpistemicLabel`) -- structurally incapable of
  asserting a confirmed error, mirroring the registry's own epistemic-status
  discipline. Both tiers run only at query time, on retrieved segments -- never
  during corpus-time indexing (`tests/integration/test_demo_pipeline.py::
  test_propositionization_happens_only_at_query_time_not_corpus_time`).
- **Tier 3 (optional LLM)**: `proposition/llm_client.py` defines the `LLMClient`
  protocol plus `NullLLMClient` (the literal default, always unavailable) and
  `FakeLLMClient` (test-only, documented as never used by the demo).
  `proposition/llm_extraction.py::extract_tier3` is the single chokepoint for every
  Tier-3 call: content-addressed cache lookup first (key = source text + extractor
  version + model id + prompt version + schema version, `ingestion/content_hash.py`),
  then -- only on a miss -- a call that always degrades to a typed fallback
  (`llm_unavailable`/`validation_failed`) rather than raising or guessing;
  every outcome, including fallbacks, is cached so an unavailable LLM is not retried
  on every lookup.
- **Retrieval**: `retrieval/lexical.py` is a from-scratch, dependency-free Okapi BM25
  implementation (no embeddings, no external BM25 package, no network) indexing only
  paragraph/list_item/table_row segments (sentences are Tier-0 children used for
  Tier-1 splitting, not independent retrieval units, so both are never double-indexed).
- **Context packing**: `trace/packer.py::pack_context` is fully programmatic --
  greedy, rank-ordered, token-budget-enforcing, using `trace/token_counting.py`
  (`tiktoken`, a transitive `llama-index-core` dependency, with a documented
  `~4-chars/token` fallback when unavailable). Records packed/omitted items
  (`omission_reason="context_budget_exceeded"`), exact `PromptTokenSpan`s, and flags
  duplicate/redundant excerpts without silently dropping them. Never truncates an
  item mid-span to fit a budget -- an item is packed whole or omitted whole, to avoid
  silently corrupting an evidence excerpt at an arbitrary token boundary; no LLM is
  ever consulted to decide what fits.
- **Orchestration and demo**: `demo/pipeline.py` ties Phase A (`ingestion/corpus_index.py`
  index_corpus, content-hash cached) and Phase B (retrieval -> Tier 1/2 -> packing ->
  `QueryTrace`) together; `run_no_llm_baseline_demo` and `run_enhanced_demo` are both
  thin wrappers around one `run_demo` function differing only in whether an LLM client
  (`DemoLLMClient`, a deterministic offline stand-in, never `FakeLLMClient`) is passed.
  `demo/widget_corpus.py` is a small fictional "widget certification program" corpus
  (the same invented domain as `data/examples/local_validation/`) with headings,
  paragraphs, lists, tables, and condition/exception/cross-reference language. Every
  `DemoResult` carries a `context_item_provenance` map (`programmatic_lexical_retrieval`
  / `llm_extracted` / `unknown`) so no field's origin has to be guessed. Wired into the
  CLI as `wittgenstein demo run [--enhanced] [--output-dir ...]`.
  `ProcessingMetrics` (pre-existing companion object, never folded into `QueryTrace`)
  is returned separately for Phase A (corpus-time) and per Phase B query -- no
  throughput claim is asserted anywhere; the benchmark test only guards against a
  pathological regression, not a target number.
- **Tests**: `tests/unit/test_ingestion_parser.py`, `test_corpus_index_caching.py`,
  `test_proposition_tiers.py`, `test_llm_extraction.py`, `test_lexical_retrieval.py`,
  `test_context_packer.py`, `test_processing_metrics_benchmark.py`, and
  `tests/integration/test_demo_pipeline.py` cover: no-LLM-dependency parsing,
  deterministic/round-tripping offsets, content-hash cache hit/miss and invalidation
  on extractor/model/prompt-version change, LLM-unavailable and client-exception
  fallback (never raising), Tier-3 batch processing, LlamaIndex-path provenance
  preservation, BM25 baseline ranking, query-time-only propositionization,
  token-budget packing and selected/omitted/duplicate distinctions, non-causal-only
  annotation language, and full end-to-end baseline/enhanced demo runs. All 18
  pre-existing registry/activation-policy/local-validation test modules remain green
  (236 total passing).

## 12. Human review loop: imported-answer mode, provider client, persistence, minimal frontend (2026-09-10)

Implements the first usable human review loop on top of the vertical-slice pipeline
(§11). No dense/hybrid retrieval, no registry evidence-status/activation-policy/
validator-threshold change, no new failure mechanism, and no live-LLM prerequisite for
reviewing evidence -- imported-answer mode works with zero LLM calls by default.

- **Imported-answer mode** (`review/imported_answer.py::import_answer`): given a
  query, an answer, and either an existing `QueryTrace` or a raw corpus, builds the
  full reviewable audit record -- retrieves/reuses evidence, runs Tier 1/2 processing
  (reusing `proposition/candidates.py` and `proposition/annotations.py` unmodified),
  extracts answer claims (`review/answer_claims.py`, composing the existing
  `ingestion/parser.py::split_sentences` and `proposition/candidates.py::split_candidates`
  rather than writing a new splitter), links each claim to packed evidence by lexical
  overlap (`review/claim_linking.py`), and derives `RiskEvent`s via the existing,
  unmodified `services/applicability_service.py::derive_risk_events` -- so this mode
  inherits every existing epistemic-status/activation-policy guarantee without touching
  the registry.
- **Answer claim support vocabulary**: `core/enums.py::ClaimSupportCandidateStatus`
  (`supported_candidate`/`partial_support_candidate`/`no_support_edge_found`/
  `conflict_candidate`/`unresolved`) on a new, additive
  `AnswerSupportEdge.candidate_support_status` field -- deliberately kept separate from
  the existing, reviewer-facing `support_status` field, which a programmatic linking
  pass never sets to `"unsupported"`/`"contradicted"` on its own. `AnswerClaim` gained
  `extraction_method` (`programmatic_rule_based`/`llm_extracted`/`fallback_whole_answer`).
- **Provider-backed LLMClient**: `proposition/providers/anthropic_client.py::AnthropicProviderClient`,
  opt-in (`pip install '.[anthropic]'`), the `anthropic` package imported lazily inside
  methods only -- the base install, full test suite, and offline demo never require it.
  Credentials read from an environment variable at call time only, never persisted;
  `store_raw_output` defaults to `False`; retry/timeout handled inside `extract()`,
  reusing `proposition/llm_extraction.py::extract_tier3`'s existing fallback machinery
  rather than duplicating it. Not exercised against a live API in this pass (no
  credentials configured in this environment).
- **Reviewer actions and persistence**: `core/enums.py::ReviewCondition`
  (`undifferentiated`/`query_scoped`/`manifest_conditioned`, formalizing the three
  conditions already described in prose in `docs/local-validation-protocol.md`) and one
  additive `ReviewerAction` member, `OVERRIDE_RISK_PRIORITY`. New
  `schemas/review_event.py::ReviewEvent` (the atomic per-action record, deliberately
  separate from the aggregate-study `LocalValidationRecord`), persisted via a new
  `db/models/records.py::ReviewEventRecord` table (Alembic migration `0002`),
  `services/review_service.py`, and `api/routes/review.py`
  (`POST /review/import-answer`, `POST /review/events`, `GET /review/events`). This is
  the one place this milestone writes to the database -- `import-answer` itself stays
  stateless, matching every other existing endpoint.
- **Frontend**: `frontend/public/review.html`, a single static HTML file (no build
  step, no framework) implementing the 11-section review screen against the API via
  CORS-enabled `fetch` calls (dev-only `allow_origins=["*"]` added to `api/app.py`).
  `frontend/src/types/registry.ts` gained additive TypeScript interfaces for the new
  schemas. No visual polish beyond basic legibility, per this milestone's explicit
  scope constraint.
- **Docs**: `docs/review-loop-implementation-plan.md` (written before code, per the
  milestone brief) and `docs/review-loop-demo.md` (the reviewer walkthrough).
- **Tests**: `tests/unit/test_answer_claims.py`, `test_claim_linking.py`,
  `test_provider_client.py`, `test_review_events.py`, and
  `tests/integration/test_imported_answer_review.py` cover all 14 required categories:
  no-LLM imported-answer mode, full trace construction, provider absence/timeout/
  mid-call-error typed fallback, credentials never appearing in persisted output,
  original answer text preserved across claims, unsupported claims staying
  `unresolved`/`no_support_edge_found`/`conflict_candidate` rather than "false",
  risk events carrying evidence status/transfer level/bounded language, reviewer-action
  persistence and trace-scoped listing, full retrieved-set access independent of
  packing, retrieved/packed/omitted/selected staying distinct (including `None` for
  the uninstrumented `selected_context_items` stage), review-condition preservation,
  and the offline demo remaining fully functional. All 236 pre-existing tests remain
  green (272 total passing).
- **Fixed along the way**: found `ReviewerAction`'s hard-coded member-count assertion
  in `tests/unit/test_registry_validation.py` would break on the additive
  `OVERRIDE_RISK_PRIORITY` member -- updated the assertion and its docstring rather
  than avoiding the enum addition.

## 13. Real-trace smoke-test harness (2026-09-10)

A pilot diagnostic harness for manually assessing retrieval and claim-linking behavior
on realistic-shaped manifest/answer pairs, before deciding whether dense/hybrid
retrieval is the next-priority addition (§11's deferred item). Not a benchmark, not the
human-subjects study, no registry/schema change, no dense/hybrid retrieval added.

- **Case format**: `schemas/smoke_test.py::SmokeTestCase`/`CorpusReference` -- never
  embeds document text; a `CorpusReference` is either a `bundled_synthetic_fixture`
  (redistribution-safe, resolved by code) or `local_path_excluded_from_git` (a
  git-ignored local path plus document hashes/source metadata only). Four new
  additive enums (`ProvenanceStatus`, `PilotCoverageLabel`,
  `RetrievalDiagnosticLabel`, `ClaimLinkingDiagnosticLabel`,
  `PropositionProvenanceDiagnosticLabel`, `ReviewInterfaceDiagnosticLabel`) in
  `core/enums.py` -- the manual-diagnostic-label vocabularies are never computed
  automatically, only scaffolded for a human researcher to fill in.
- **Runner**: `smoke_test/{corpus_registry,manifest_registry,runner}.py` resolves a
  case's manifest/corpus and calls the existing, unmodified
  `review.imported_answer.import_answer` -- not a parallel pipeline. Exposed via
  `wittgenstein smoke-test run --cases <path> --output-dir <path> [--enhanced]`;
  `--enhanced` prefers a configured `AnthropicProviderClient`, falling back to the
  offline `DemoLLMClient` when no credentials are set, so it never requires live
  credentials to exercise. `review/claim_linking.py` gained a public
  `score_candidates`/`CandidateScore` (a refactor of `link_claim`'s internals, verified
  behavior-preserving against its existing tests) so the inspection report can show
  every candidate's link score, not just the winner.
- **Bundled pilot**: `data/examples/real_trace_smoke/{cases.example.json,manifests.json,cases.schema.json,README.md}`
  -- 6 cases against the existing fictional widget-certification fixture, covering
  every required pilot-variation category
  (structured/narrative/short/long documents, multiple sections, conditions/
  exceptions, cross-references, temporal/version information, multi-claim answers,
  multi-passage evidence, supported/partial/unsupported answers, conflict/unresolved).
  `smoke-004-conflict-negation` and `smoke-003-unsupported-fabricated` are deliberately
  adversarial: the former confirms the negation-mismatch conflict-candidate path fires
  correctly on a real trace; the latter is a demonstrated, documented limitation --
  a fully fabricated claim can still score `partial_support_candidate` from topical
  lexical overlap alone.
- **Docs**: `docs/real-trace-smoke-test-plan.md` (written first, per the milestone
  brief) and `docs/real-trace-smoke-test-results.md` (a template, not filled in --
  filling it in requires actually running and manually labeling a pilot, which is a
  human research task this milestone enables but does not itself perform).

**Follow-up correction (same day)**: the task brief that specified
`PropositionProvenanceDiagnosticLabel` and `ReviewInterfaceDiagnosticLabel` had been
cut off mid-message on first receipt; this implementation initially completed those
two vocabularies as a documented judgment call. The remainder of the original message
arrived in a follow-up turn with the actual intended lists, so both enums were
corrected to match exactly (`PropositionProvenanceDiagnosticLabel`:
`proposition_requires_dependency`/`dependency_available`/`dependency_missing`/
`extraction_uncertain` replacing the earlier guessed
`proposition_requires_additional_context`/`annotation_cue_relevant`/
`annotation_cue_irrelevant`/`unresolved`; `ReviewInterfaceDiagnosticLabel`:
`evidence_easy_to_locate`/`full_context_sufficient`/
`omitted_competing_evidence_visible`/`reviewer_action_clear`/`unnecessary_alert`/
`missing_useful_warning` replacing the earlier guessed `risk_event_language_*`/
`evidence_navigation_*`/`reviewer_action_set_*`/`missing_information_noted`). The
follow-up also added:

- `smoke_test/report.py::generate_report` (wired as `wittgenstein smoke-test report
  --output-dir <path>`) -- aggregates a completed run's inspection reports and
  filled-in labels templates into `report.json`: case count, corpus/document profile,
  retrieval/claim-linking/provenance/review-interface usefulness (each with
  `labeled_count`/`total_count` so a 0 is never misread as "no problems"), spurious-
  link and claim-split-problem counts, processing latency, LLM calls/cache hits, and
  raw `bottleneck_signals` for the A-E classification -- never a single collapsed
  score, and the report itself never declares a bottleneck dominant or asserts dense
  retrieval is justified (that stays an explicit human judgment against
  `docs/real-trace-smoke-test-plan.md` §11's A-E procedure).
- `expected_evidence_location_labels`, a labels-template slot separate from
  `retrieval_candidate_labels`: a missed location has no retrieved item id to attach a
  per-candidate label to, so `evidence_candidate_missed` needed its own home keyed by
  researcher-annotated location instead.
- Corrected the plan doc's decision procedure to the task's exact A-E bottleneck
  classification (retrieval recall / claim linking / proposition / context-packing /
  review-interface), replacing the earlier three-step approximation.

- **Tests**: `tests/integration/test_real_trace_smoke_cases.py` (22 tests) and
  `tests/unit/test_smoke_test_report.py` (12 tests) cover all 10 required categories:
  valid/invalid case construction, restricted local corpus paths never committed
  (`.gitignore` coverage plus a `git check-ignore` check), zero-LLM-call imported-
  answer mode, complete trace export, processing metrics, and claim-linking/
  provenance/risk-event diagnostics and case-level report generation (via the
  synthetic-fixture report tests, isolated from a full pipeline run), plus a
  determinism test (two independent `run_case` calls produce identical substantive
  output once the legitimately-varying `risk_event_id`/timestamps/wall-clock timing
  are normalized away). All 285 pre-existing tests remain green (306 total passing).

## 14. Conservative programmatic claim-evidence comparison (2026-09-11)

Replaces the pure lexical-overlap claim linker with a field-comparison engine,
fixing the exact smoke-003 failure (§13): "Class III widgets must be inspected every 6
months" scored `partial_support_candidate` against "...once per Program Year" from
token overlap alone, despite an incompatible frequency. No dense/hybrid retrieval, no
registry/evidence-status/activation-policy/validator-threshold/failure-mode-ontology
change, no human-subjects study, default no-LLM behavior unchanged.

- **Schemas**: new `schemas/claim_comparison.py` (`ExtractedField`, `FieldComparison`,
  `ClaimEvidenceComparison`, `SemanticComparisonResult`) and 6 new `core/enums.py`
  vocabularies (`ComparisonFieldName` [17 fields], `ExtractionStatus`,
  `ComparisonOutcome` [the four-state MATCH/MISMATCH/ABSENT/UNKNOWN lattice],
  `MismatchType` [18 values], `SemanticComparisonOutcome`). `ClaimSupportCandidateStatus`
  gained 3 additive members (`DIRECT_SUPPORT_CANDIDATE`, `QUALIFICATION_REQUIRED`,
  `CONTRADICTION_CANDIDATE`); `NO_SUPPORT_EDGE_FOUND` doubles as the task's
  "no_support_found" (one name, not a duplicate). `ImportedAnswerResult` gained
  `claim_evidence_comparisons: list[ClaimEvidenceComparison]`.
- **Extraction** (`review/field_extraction.py`, `review/normalization.py`): regex/
  lexicon only, no spaCy dependency added. Entity/predicate share one "subject
  precedes the verb" anchor (first modal, else first copula/do-support auxiliary);
  predicate compares only the base verb (modal/negation stripped -- MODALITY/POLARITY
  carry those separately). Frequency/duration normalization preserves domain-defined
  periods (e.g. "Program Year") with an explicit `calendar`/`normalization_status` tag
  -- never silently converted to a calendar year.
- **Comparison and classification** (`review/field_comparison.py`,
  `review/relationship_classification.py`): implements the task's rules A-G exactly.
  A confidence-based "noise floor" prevents an inherently noisy field
  (`object_value`'s heuristic) from single-handedly forcing `unresolved`; only
  claim-asserted fields count as "critical" for the direct-support/partial-support
  boundary; entity comparison applies conservative singular/plural normalization.
- **Multi-clause candidates**: a packed candidate excerpt is decomposed into clauses
  (Tier-0 sentence splitting + Tier-1 clause splitting, both reused unmodified) before
  comparison, and the claim is compared against every clause, keeping the most
  informative result -- otherwise the first verb encountered in a multi-clause
  paragraph (possibly in an unrelated clause) silently drove the whole comparison.
- **Multi-source conflict** (`review/claim_linking.py::link_claim_detailed`, rule E):
  if one packed candidate reaches `direct_support_candidate` and another reaches
  `contradiction_candidate` for the same claim, both are reclassified
  `conflict_candidate` rather than the aggregate silently picking a winner.
- **Optional semantic/NLI layer** (`review/semantic_provider.py`): a
  `SemanticProvider` protocol mirroring `proposition/llm_client.py::LLMClient` exactly
  (`NullSemanticProvider` default, never required for the no-LLM baseline). Cached via
  a new `ingestion/kv_cache.py::SqliteKVCache` (third `KVCache` implementation,
  gained a `clear()` method on all three), keyed via the existing
  `content_hash.py::cache_key` over claim/passage text, provider, model, prompt,
  extractor, schema, and normalization versions. No real provider implemented in this
  pass (same treatment as the Anthropic provider in §12 -- interface-complete, not
  exercised live).
- **Reviewer explanations**: bounded, fixed-template sentences only
  (`relationship_classification.py::_bounded_explanation`) -- never a freeform or
  truth-asserting sentence.
- **Smoke-test reporting** (`smoke_test/report.py`, `smoke_test/runner.py`): added
  `automatic_relationship_rates` (topical/direct-support/partial-support/
  qualification/contradiction/conflict/no-support/unresolved rates and structured
  mismatch-type counts, computed directly from `claim_evidence_comparisons` -- no
  manual labeling required) and `manual_support_link_usefulness_rate`/
  `manual_spurious_link_rate`. `build_labels_template` gained
  `claim_evidence_annotations`, a per-(claim, candidate) manual annotation template
  (answer claim, candidate passage, field-comparison vector, candidate relationship
  pre-filled; reviewer label/confidence/rationale/unresolved-reason/notes empty) for
  real/licensed runs.
- **Tests**: `tests/unit/test_field_comparison_engine.py` (18 tests, one per required
  category 1-13 and 15-19; category 14 is multi-candidate, not single-pair, so it
  lives in the next file), `tests/unit/test_claim_linking_conflict.py` (category 14),
  `tests/unit/test_semantic_provider_and_cache.py` (categories 20-26), plus updates to
  `test_claim_linking.py` and `test_real_trace_smoke_cases.py` reflecting the new
  engine's corrected behavior (e.g. a single-source negation mismatch is now
  `contradiction_candidate`, not the old, retired single-source meaning of
  `conflict_candidate`). All 306 pre-existing tests remain green (345 total passing).
- **Known, accepted limitation**: pronoun coreference is not attempted. When a source
  clause refers to its subject only via a pronoun, entity alignment cannot be
  established with regex/lexicon methods, and the conservative outcome is
  `unresolved` -- documented via `smoke-004-conflict-negation` in the bundled pilot,
  which surfaces exactly this case rather than a wrong `direct_support_candidate`.

## 15. Conservative multi-passage evidence-set layer (2026-09-11)

Adds bounded, deterministic composition of *two* packed passages when no single one
reaches `direct_support_candidate` for an answer claim -- e.g. one passage confirming
a rule, another confirming which population it applies to. No dense/hybrid retrieval,
no live semantic/NLI provider, no new registry mechanism, no activation-policy change,
no `TRIAGE_ENABLED` promotion.

- **Schemas**: new `schemas/evidence_set.py` (`ClaimComponent`, `EvidenceSetMember`,
  `EvidenceSetConflict`, `EvidenceSet`) and 2 new `core/enums.py` members
  (`ComponentRequiredness`, `EvidenceSetConstructionMethod`).
  `ClaimSupportCandidateStatus` gained 5 additive `composite_*` members, assigned only
  to `EvidenceSet.relationship_status`, never to `AnswerSupportEdge.candidate_support_status`.
  `ImportedAnswerResult` gained `evidence_sets: list[EvidenceSet]` and
  `evidence_set_metrics: list[EvidenceSetConstructionMetrics]`.
- **Construction** (`review/evidence_set.py::construct_evidence_set`): skips entirely
  when single-passage direct support already exists (§14's engine, reused unmodified);
  otherwise decomposes the claim into components (reusing `field_extraction.py`'s
  17-field extraction unchanged, with population/scope further split into one critical
  component per scope token), searches `itertools.combinations` of packed items
  bounded by `max_set_size` (default 2), checks pairwise member compatibility, and
  classifies the result via the same conservative priority a single-passage
  comparison uses (conflict > unresolved > qualification > partial > support).
- **Axis-aware population/scope**: a claim commonly asserts more than one independent
  scope qualifier (e.g. a widget class *and* a zone); scope tokens are grouped by axis
  (class/zone/region/district/area/general) before comparison, so two passages
  addressing different axes are read as complementary, not conflicting -- the single
  biggest gap the plan's own worked example surfaced (see
  `docs/multi-passage-evidence-plan.md` §11 for the full account).
- **Cross-member compatibility** (`_check_member_compatibility`) deliberately excludes
  PREDICATE (a rule passage and a condition/exception passage legitimately use
  different verbs) and NUMERIC_VALUE (a bare number carries no unit, so two unrelated
  numbers could collide by coincidence); an unresolved pronoun/demonstrative entity is
  never treated as evidence of a *different* entity between two members.
- **Member-introduced qualifiers**: when a claim never mentions a condition/exception
  but a composing member's own text does ("...provided that..."/"...except..."), the
  composite result is downgraded to `composite_qualification_required` rather than
  silently dropping that information.
- **`QueryTrace.support_requirement`** (`schemas/trace.py`, previously unused by
  `import_answer`) is populated when at least one evidence set was proposed with
  members -- connecting to, without modifying or promoting, the registered
  `RET_MULTIHOP_SUPPORT_INCOMPLETE` mechanism's gate condition.
- **Smoke-test reporting** (`smoke_test/report.py`, `smoke_test/runner.py`): inspection
  reports gained `evidence_sets`/`evidence_set_metrics`; the aggregate report gained
  `evidence_set_summary` (claims evaluated, attempted/skipped counts and why,
  composite relationship-status counts, mean pool size/latency) -- computed
  automatically, no manual labeling required.
- **Tests**: `tests/unit/test_evidence_set.py` (16 tests, categories 1-4 and 6-17) and
  `tests/integration/test_multi_passage_smoke_cases.py` (category 18, plus an
  end-to-end real-corpus composition and a report-summary check). All 345 pre-existing
  tests remain green (365 total passing).
- **Known, accepted limitations**: category 5 (cross-reference/definition closure
  outside the packed-item pool) is not implemented -- such a claim stays
  `composite_unresolved`. Regex-based extraction is noticeably less reliable on long,
  complex real-corpus sentences than on the plan's clean worked example; see
  `docs/multi-passage-evidence-plan.md` §11 and `docs/multi-passage-evidence-demo.md`.

## 16. Real-corpus evidence-set diagnostic pass (2026-09-11)

Measures -- does not fix -- the two limitations §15's report surfaced (cross-reference
closure, extraction reliability on long sentences), plus a secondary "prefer smallest
size" bound question. No dense/hybrid retrieval, no live LLM/NLI provider, no
`TRIAGE_ENABLED` promotion, no registry/evidence-status/activation-policy change, no
factual-truth claim, no automatic "fix" of cross-reference closure before measuring
its importance.

- **Labels**: 5 new diagnostic-label enums (`core/enums.py`) --
  `ExtractionQualityDiagnosticLabel`, `ConflictQualityDiagnosticLabel`,
  `CrossReferenceClosureDiagnosticLabel`, `EvidenceSetSizingDiagnosticLabel`,
  `ReviewerWorkflowDiagnosticLabel` -- plus `CrossReferenceTargetState` (an automatic
  trace-observable signal, not a manual label).
- **Cross-reference measurement** (`review/cross_reference_diagnostics.py`,
  `docs/cross-reference-diagnostic-spec.md`): detection reuses
  `ComparisonFieldName.CROSS_REFERENCE` extraction unchanged; target-state resolution
  builds a fresh (cached) `CorpusIndex` and matches marker text against
  `SourceSegment.location`, then checks the trace's own stage lists
  (packed > omitted > selected > retrieved > in_corpus > unknown). Emits the exact
  fixed warning template the brief specified, never a causal/adjudicative claim.
  Measurement only -- closure (pulling a target into an evidence set) is not
  implemented.
- **Conflict-artifact instrumentation** (`review/conflict_diagnostics.py`): read-only
  re-derivation of the exact `extract_fields`/`compare_field` calls
  `_check_member_compatibility` already made, recovering full field
  spans/confidence/extraction method per `EvidenceSetConflict` for a human to label --
  never auto-downgrades a conflict.
- **Real bug found and fixed while building this**: `construct_evidence_set`'s
  "prefer smallest size" search broke the diagnostic size-3 mode entirely -- it
  stopped searching as soon as *any* non-conflicting, non-redundant (but still
  incomplete) combo was found at size 2, so `max_set_size=3` never actually reached
  size-3 combinations. Fixed by breaking only when full critical-component coverage is
  achieved; no effect on the default `max_set_size=2` (see
  `docs/multi-passage-evidence-plan.md` §11).
- **Diagnostic harness** (`evidence_set_diagnostics/`, new package mirroring
  `smoke_test/`): `runner.py::run_diagnostic_case`/`run_evidence_set_diagnostics`,
  `report.py::generate_diagnostic_report` -- computes counts/rates only, never
  classifies a dominant next-priority bottleneck automatically. CLI:
  `wittgenstein evidence-set diagnose --cases <path> --output-dir <path>
  [--diagnostic-max-set-size 3]` / `wittgenstein evidence-set report --output-dir <path>`.
  Reuses `schemas/smoke_test.py::SmokeTestCase`/`SmokeTestCaseFile`/`CorpusReference`
  unchanged as the case format (no second case schema) and
  `smoke_test/corpus_registry.py`/`manifest_registry.py` unchanged for resolution.
  Always no-LLM, deterministic, never modifies `import_answer`'s own output.
- **Diagnostic-only size-3 search**: bounded at `math.comb(pool, 3) <= 500`; above that,
  only the closed-form combination count and an extrapolated latency estimate are
  reported, never an actual search. Never the default; never used by any other command.
- **Tests**: `tests/unit/test_cross_reference_diagnostics.py` (8, fixtures 1-4),
  `tests/unit/test_conflict_diagnostics.py` (5, fixtures 5-8),
  `tests/unit/test_evidence_set_size_diagnostics.py` (6, fixtures 9-12),
  `tests/integration/test_evidence_set_diagnostics_harness.py` (11, full-harness/CLI/
  determinism/no-LLM/restricted-content-excluded). All 386 pre-existing tests remain
  green (397 total passing).
- **Data**: `data/examples/evidence_set_diagnostics/` (2 bundled cases against the
  existing `widget-certification-demo` fixture, chosen because their behavior is
  already empirically verified); `local_corpora/`/`output/` gitignored for real/
  licensed documents.
- **No implementation-priority recommendation made** -- real diagnostics have not yet
  been run against real/licensed documents; see the milestone's final report for what
  is needed next.

## 17. First real-corpus pilot, article cross-reference fix, and comparison tooling (2026-09-11 -- 2026-09-15)

Three tightly coupled follow-on milestones, none changing the registry, activation
policies, retrieval, or claim-linking behavior:

- **EU AI Act pilot** (`docs/eu-ai-act-pilot-execution-plan.md`,
  `docs/eu-ai-act-pilot-run-summary.md`, `docs/eu-ai-act-pilot-annotation-checklist.md`):
  the first real/licensed corpus diagnostic run, against 6 documents (Article 3
  selected definitions, 6, 13, 49, 50, 113) transcribed verbatim from the official
  EUR-Lex PDF into `local_corpora/eu-ai-act-2024/` (gitignored). 6 hand-authored
  cases, one an explicitly labeled controlled perturbation. Found, but did not fix in
  that pass, that cross-reference detection recognized `Section`/`Table`/`Figure`/
  `Exemption`/`Appendix`/`Clause` but not `Article` -- the primary EU-legal citation
  form.
- **Article cross-reference detection fix**
  (`docs/eu-ai-act-article-cross-reference-fix-plan.md`,
  `docs/eu-ai-act-article-cross-reference-run-summary.md`): a second, dedicated
  regex/parser added to `review/cross_reference_diagnostics.py` only (never touching
  the shared `proposition/annotations.py` cue detector or claim-linking behavior),
  recognizing `Article N`, `Article N(M)`, `Article N(M), point (x)`, `Articles N and
  M`/`N, M and P`/`N to M`/`N-M`, and `Annex <roman numeral>`. New `ReferenceTarget`
  dataclass carries per-target normalization (`target_identifier` like
  `article:6:paragraph:4:point:a`) and structural (never semantic) local resolution,
  reusing the existing six-state `CrossReferenceTargetState` vocabulary. A real regex
  bug was found and fixed along the way: a trailing `\b` after an optional
  paragraph/point group silently dropped the suffix whenever the match ended on a
  closing `)` (non-word-to-non-word has no boundary) -- fixed with a negative
  lookahead. Markers detected in the pilot went from 1 to 9; all non-cross-reference
  diagnostic counts stayed byte-identical between the preserved baseline
  (`local_corpora/eu-ai-act-2024/output-baseline-before-article-xref/`) and the
  post-fix run (`output-after-article-xref/`).
- **Comparison tooling** (`docs/eu-ai-act-cross-reference-annotation-protocol.md`,
  `docs/eu-ai-act-cross-reference-comparison-template.md`,
  `docs/eu-ai-act-cross-reference-annotation-summary.md`): a new, read-only,
  deterministic `evidence_set_diagnostics/cross_reference_comparison.py` module and
  `wittgenstein evidence-set compare-cross-reference` CLI command diff two prior
  `diagnose` runs' `*.diagnostic.json` files (plus the cases file, for query/
  answer-origin) into one worksheet -- markers newly detected, target-state changes,
  and whether any non-cross-reference output changed at all. Matches markers by
  surface text only (not `reference_type`, which the baseline predates), and
  deduplicates repeated same-text markers across claim fragments within a case while
  preserving an `occurrence_count`. The CLI command refuses to write its output
  anywhere `git check-ignore` does not confirm is ignored. No human-judgment label is
  ever filled by this tooling -- a full annotation protocol exists for that instead.
- **Tests**: `tests/unit/test_article_cross_reference_detection.py` (22),
  `tests/unit/test_cross_reference_comparison.py` (12). All 435 pre-existing tests
  remain green (457 total passing after the detection fix; comparison tooling adds no
  further regressions).
- **No implementation-priority recommendation made** at any point in this trio of
  milestones -- every annotation label across the pilot, the fix, and the comparison
  worksheet remains unfilled.

## 18. Cross-reference paragraph/point-level granularity resolution (2026-09-16)

Fixes the false-reassurance gap the EU AI Act annotation pass surfaced: a coarse
`target_state=packed` said "something from the cited article is packed," never whether
the *specific cited paragraph* was. No registry/activation-policy/retrieval/packing/
claim-linking change; no automatic retrieval/packing/closure.

- **Plan**: `docs/cross-reference-granularity-resolution-plan.md`, written before code.
- **Schema**: `SourceSegment` gains four additive fields (`legal_article_number`,
  `legal_paragraph_number`, `legal_point_identifier`, `legal_annex_identifier`),
  populated only from explicit source markers (`ingestion/parser.py`, additive,
  no change to segment_type/location/text/offsets). Two new enums,
  `CrossReferenceResolutionGranularity` and `ExactTargetAvailability`.
- **Resolution**: `review/cross_reference_diagnostics.py` gains
  `_resolve_granularity_and_exactness` (deterministic decision rules over the new
  segment fields and trace stage membership) and `exactness_explanation` (bounded,
  non-adjudicative reviewer text, additive to the unchanged `cross_reference_warning`).
  A second, additive structural match, `_legal_article_number_segment_ids`, resolves an
  article by each segment's own parsed number rather than only by one-article-per-file
  naming -- needed for a corpus with more than one article per document (motivated by,
  and later reused by, the Asteria corpus in §19); verified to change nothing for the
  EU AI Act corpus's existing one-article-per-file documents.
- **Real finding**: re-running the EU AI Act pilot's `Article 49(2)` case with the new
  layer showed `exact_target_present`, not the false-reassurance risk an earlier manual
  annotation had (incorrectly, by hand-counting) flagged -- documented as a correction
  in `docs/eu-ai-act-cross-reference-granularity-run-summary.md`, not silently changed.
- **Tests**: `tests/unit/test_cross_reference_granularity.py` (20, all required
  categories). All 469 pre-existing tests remain green (489 total passing).
- **Third preserved output**: `local_corpora/eu-ai-act-2024/output-after-granularity-resolution/`
  (gitignored), distinct from the baseline and the prior post-fix run.

## 19. Controlled synthetic corpus (Asteria) and local frontend integration (2026-09-16)

A product-integration and regression-testing milestone: a second, entirely fictional,
**tracked** corpus with known-in-advance, verified-not-predicted expected pipeline
behavior per case, plus the local frontend/API wiring to interactively run it. Not a
real-corpus benchmark, not a human-subjects study, no registry/evidence-grade/
activation-policy change, no `TRIAGE_ENABLED` promotion, no dense/hybrid retrieval, no
live LLM in the default path.

- **Plan**: `docs/controlled-synthetic-corpus-plan.md`, written before any corpus file
  or frontend change.
- **Corpus**: `data/fixtures/asteria_manual/` -- 4 tracked Markdown documents
  (definitions, two clause documents spanning Articles 2-6, one annex with a
  conformity table), 10 cases (`cases/cases.json`, the existing `SmokeTestCase` schema,
  no second case format), one hand-verified `expected/<case_id>.expected.json` per
  case, and 4 `PipelineManifest`s (P1 baseline, P2 budget-stressed, P3
  representable-but-not-executable parent-context, P4 full-context non-activation
  control). Every case's expected outcome was recorded from actually running the real,
  unmodified pipeline, never predicted in advance -- including one honest, documented
  limitation (`asteria-003`'s two-passage composition reaches `composite_unresolved`,
  not a cleaner classification, on regex-based extraction).
- **Two small, narrow architectural gaps found and closed while wiring this up**: (1)
  `run_diagnostic_case` never threaded `top_k`/`token_budget` from a manifest's own
  `retrieval_manifest.candidate_depth`/`packing_manifest.evidence_budget_tokens` --
  both were purely descriptive, additive optional parameters added, defaulting to
  exactly the prior behavior when omitted. (2) `_legal_article_number_segment_ids`
  (§18) for multi-article-per-file corpora.
- **Fixture-integrity validator**: `fixtures/asteria_validator.py`
  (`wittgenstein fixture load asteria_manual`) actually runs every case through the
  real pipeline and checks it against its `expected/*.json` -- distractor-never-
  satisfies-claim, cross-reference-expectation-matches-observed, perturbation-
  provenance-complete, zero-LLM-calls, no-real-source-provenance-leakage, no-registry-
  vocabulary-collision. New `wittgenstein fixture run` command (mirrors
  `evidence-set diagnose`'s report shape).
- **API**: `POST /review/import-answer` gains three additive response keys
  (`claim_evidence_comparisons`, `evidence_sets`, `cross_reference_markers`) --
  previously entirely absent from the endpoint despite existing in
  `ImportedAnswerResult`. A new shared `review/cross_reference_diagnostics.py::marker_to_dict`
  is the single source of the marker JSON shape, used by both the API and
  `evidence_set_diagnostics/runner.py` (refactor, behavior-preserving).
- **Frontend**: `frontend/public/review.html` gains a corpus selector (Widget/Asteria),
  an Asteria case/manifest picker, and three new render sections (claim/evidence
  comparisons, evidence-set composition, cross-reference targets) -- additive only,
  every existing section/behavior for the widget corpus is unchanged. The Asteria
  corpus/case/manifest data is embedded as generated JS constants (same
  "kept in sync by hand" pattern as the pre-existing `WIDGET_CORPUS`), confirmed
  byte-identical to the tracked source files.
- **Tests**: `tests/unit/test_asteria_fixture.py` (22, all required categories,
  including a live `TestClient`-based API/persistence smoke test and a direct
  `matching/eligibility.py::evaluate_eligibility` check proving genuine segmentation-
  mismatch activation on one designed case and genuine non-activation on another). All
  489 pre-existing tests remain green (511 total passing).
- **Docs**: `docs/controlled-corpus-coverage-matrix.md`,
  `docs/asteria-corpus-authoring-guide.md`, `docs/asteria-frontend-demo.md` (every
  command in it actually run against a live local API/static server before being
  documented); updates to `README.md`, `docs/architecture.md`, `docs/trace-spec.md`,
  `docs/review-loop-demo.md`.
