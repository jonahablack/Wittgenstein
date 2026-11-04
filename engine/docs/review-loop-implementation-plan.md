# Review-loop implementation plan

This plan covers the next product milestone: a usable human review loop on top of the
vertical-slice pipeline (`docs/efficiency-and-processing-architecture.md`,
`demo/pipeline.py`). No dense/hybrid retrieval is added here. No registry evidence
status, activation policy, or validator threshold changes. No new failure mechanism is
added. Live LLM generation is never a prerequisite for reviewing evidence.

## 1. Imported-answer review mode

A new `review/` package holds the product-facing (not demo-only) orchestration:

- `review/answer_claims.py` — turns raw answer text into `AnswerClaim`s using the same
  three-tier priority as proposition extraction elsewhere in this codebase:
  1. **Programmatic**: reuse `proposition/candidates.py::split_candidates` against a
     synthetic `SourceSegment` wrapping the answer text (no new splitting logic —
     one splitter, not two that could drift, per `CLAUDE.md`).
  2. **Optional provider-backed**: for a candidate span still ambiguous after rule-based
     splitting, escalate through the existing `proposition/llm_extraction.py::extract_tier3`
     chokepoint — the same cache/fallback machinery Tier 3 already uses, not a new path.
  3. **Typed fallback**: if both are unavailable or fail, one `AnswerClaim` covering the
     whole answer text, `extraction_method="fallback_whole_answer"`. The original answer
     text is always preserved verbatim on `QueryTrace.answer` regardless of extraction
     outcome.
- `review/claim_linking.py` — links each `AnswerClaim` to packed `ContextItem`s by
  lexical token overlap (reusing `retrieval/lexical.py::tokenize`, no new tokenizer) and
  a negation-cue check (reusing `proposition/annotations.py`'s existing patterns, not a
  new heuristic). Produces one `AnswerSupportEdge` per claim with
  `candidate_support_status` (`core/enums.py::ClaimSupportCandidateStatus`) — a
  **programmatic, pre-review** signal, never a final correctness verdict, and never
  rendered as "the answer is false/faithful/hallucinated" (see §3 below and
  `docs/review-loop-implementation-plan.md` §"F. Risk display" language rules).
- `review/imported_answer.py` — `import_answer(...)` is the one entry point:
  accepts `query`, `corpus` (a `{source_document_id: text}` dict) or `corpus_id`
  (reuses an already-indexed corpus), `answer` text, optional `manifest`, optional
  existing `trace`. If no `trace` is given, it runs the same retrieval/packing path
  `demo/pipeline.py::run_demo_query` already uses (imported directly — see "Known
  layering note" below) to build one. It then runs Tier 1/2 processing on the
  packed items (already implemented, reused unchanged), extracts and links answer
  claims (above), and calls the existing, unmodified
  `services/applicability_service.py::derive_risk_events` to compute `RiskEvent`s —
  the same registry-matching code path the rest of the system already uses, so this
  mode inherits every existing epistemic-status/activation-policy guarantee for free
  without touching the registry.

  Returns an `ImportedAnswerResult` dataclass: `trace`, `manifest`, `corpus_profile`,
  `risk_events`, `audited_non_applicable_assessments`, `candidates`, `annotations`,
  `context_item_provenance`, `metrics`. This is the full audit record §4 exposes.

  **Works with zero LLM calls by default** — `import_answer(..., llm_client=None)` is
  the default and only path exercised by the offline demo and by every required test;
  a provider client is accepted but never required.

**Known layering note (deferred, see §8)**: `run_demo_query`/`build_manifest`/
`build_bm25_index` currently live in `demo/pipeline.py`, which predates this milestone.
`review/imported_answer.py` imports them from there rather than duplicating them. This
is honest but slightly backwards (product code depending on a module named "demo");
renaming that shared orchestration into a neutral `pipeline/` module is deferred to
avoid touching and re-verifying already-green code under this milestone's tight scope.

## 2. Optional provider-backed answer generation

`proposition/providers/anthropic_client.py` — one optional, concrete `LLMClient`
implementation, added as an opt-in extra (`pip install '.[anthropic]'`,
`anthropic` added under `[project.optional-dependencies]` in `pyproject.toml`, **not**
a base dependency). Requirements enforced in this one module (no provider-specific type
or import anywhere else — `proposition/llm_client.py`'s `LLMClient` protocol is
untouched):

- The `anthropic` package is imported lazily, inside `AnthropicProviderClient.__init__`,
  never at module import time — so the base install, the full test suite, and the
  offline demo never require it to be installed at all.
- The API key is read from `ANTHROPIC_API_KEY` (or a caller-supplied env var name) at
  call time only, via `os.environ`. It is never written to any field on
  `LLMCallResult`/`LLMExtractionResult`/`QueryTrace`/`PipelineManifest`, never logged,
  and never accepted as a constructor string literal (env-var-name only, not the key
  itself, matching "credentials only from environment variables or an approved secret
  store").
- `is_available()` returns `True` only if both the package import and the env var
  lookup succeed — so a missing key or missing package both degrade to the existing
  `llm_unavailable` fallback path in `extract_tier3`, not a crash.
- `timeout_seconds`/`max_retries` constructor params; a fixed number of retries with
  linear backoff on the underlying SDK's transient-error exception types, then a plain
  `raise` — `extract_tier3`'s existing `try/except Exception` already converts any
  raised exception into the typed `llm_unavailable` fallback, so retry logic reuses
  that machinery rather than duplicating it.
- `store_raw_output: bool = False` constructor flag — when `False` (the default),
  `LLMCallResult.raw_output` is set to `None` even on a successful call; the parsed,
  schema-validated output is still returned. Never on by default.
- Model id and prompt/schema version are passed straight through to
  `extract_tier3`'s existing parameters, which already record them on
  `LLMExtractionResult` — no new field needed.
- **Not exercised against a live API in this pass** (no credentials configured in this
  environment, consistent with how the LlamaIndex/Tier-3 interface itself was left
  interface-only in the prior milestone) — tests cover `is_available()` behavior,
  credential-absence handling, and that importing this module never requires the
  `anthropic` package.

## 3. Answer claim extraction and support status

`core/enums.py::ClaimSupportCandidateStatus` — `supported_candidate`,
`partial_support_candidate`, `no_support_edge_found`, `conflict_candidate`,
`unresolved`. Added as a **new, additive** field,
`AnswerSupportEdge.candidate_support_status: ClaimSupportCandidateStatus | None`,
deliberately alongside (not replacing) the existing `support_status` string field.
`support_status` remains the reviewer-facing/final field (`supported`/`unsupported`/
`contradicted`/`unknown`, `judged_by="reviewer"` or `"unreviewed"`) exactly as today —
existing tests and callers are unaffected. `candidate_support_status` is the
**programmatic, pre-review** classification this milestone adds; a programmatically
produced edge sets `support_status="unknown"`, `judged_by="unreviewed"`, and
`candidate_support_status` to the richer value — never `support_status="unsupported"`
or `"contradicted"` from the programmatic linker alone, since that field is reserved
for a reviewer or an explicitly causal-evidence-backed pipeline judgment (mirrors the
existing `RiskEvent.causal_claim_allowed` discipline).

`AnswerClaim.extraction_method: str | None` records which tier produced the claim
(`"programmatic_rule_based"` / `"llm_extracted"` / `"fallback_whole_answer"`) — the
same provenance-labeling convention as `context_item_provenance` in
`demo/pipeline.py::DemoResult`.

## 4. Review trace endpoint/service

New `api/routes/review.py`:

- `POST /review/import-answer` — request: `query`, `answer`, one of `corpus`
  (`{source_document_id: text}`) or `corpus_id`, optional `manifest`, optional `trace`,
  optional `use_llm: bool = false`. Calls `review.imported_answer.import_answer`.
  Response is the full audit record: `trace` (includes `retrieval_candidates`,
  `packed_context_items`, `omitted_context_items`, `prompt_token_spans`, `final_prompt`,
  `answer_claims`, `answer_support_edges`, `segment_boundary_dependency_flags`),
  `manifest`, `corpus_profile`, `risk_events` (full objects — evidence status, transfer
  level, bounded language, recommended action, all already on `RiskEvent`), `candidates`
  and `annotations` (source propositions and dependency/condition/exception cues),
  `context_item_provenance`. This is deliberately **stateless** — it does not write to
  the database (see §8; no existing endpoint persists manifests/traces/assessments
  today either, despite the tables existing since the prior milestone's audit-table
  migration — retrofitting that is out of scope here).
- Reuses `QueryTrace`/`PipelineManifest`/`RiskEvent`/`CorpusProfile` — the same schemas
  the rest of the API already returns — so the frontend types file
  (`frontend/src/types/registry.ts`) only needs additive entries, not a parallel shape.

## 5. Reviewer actions and persistence

`core/enums.py::ReviewCondition` — `undifferentiated`, `query_scoped`,
`manifest_conditioned` (formalizing the three conditions already described in prose in
`docs/local-validation-protocol.md`, "Review conditions" — no change to that document's
meaning, just giving it a schema home). `ReviewerAction` (existing enum) gains one new
additive member, `OVERRIDE_RISK_PRIORITY`, to cover "override risk priority" from this
task's action list; every other requested action already has a matching existing member
(`APPROVE_SUFFICIENTLY_SUPPORTED`, `APPROVE_WITH_QUALIFICATION`,
`REQUEST_ADDITIONAL_CONTEXT`, `INSPECT_REFERENCED_SECTION`, `COMPARE_COMPETING_SOURCES`,
`ASK_CLARIFYING_QUESTION`, `ESCALATE_TO_DOMAIN_EXPERT`, `REJECT_AS_UNSUPPORTED`,
`MARK_UNRESOLVED`, `DISMISS_AS_LOW_PRIORITY` for "dismiss risk event").

New `schemas/review_event.py::ReviewEvent` — the atomic, per-action record (distinct
from `LocalValidationRecord`, which is an aggregate *study*-level record produced by
analyzing many `ReviewEvent`s later — kept separate per this project's "never collapse
distinct concepts" rule): `review_event_id`, `trace_id`, `reviewer_id`, `session_id`,
`review_condition`, `displayed_risk_event_ids`, `opened_evidence_item_ids`,
`reviewer_action`, `target_risk_event_id`, `target_claim_id`, `confidence`,
`uncertainty`, `notes`, `timestamp`, `experience_measures` (an open `dict[str, float]`
for optional ad hoc measures, cross-referenced against `docs/reviewer-measures.md`
rather than hard-coding every possible measure name into the schema).

Persistence: new `db/models/records.py::ReviewEventRecord` (SQLModel table, same
indexed-columns-plus-JSON-payload pattern as the existing `RiskEventRecord` etc.), new
Alembic migration `0002_review_events.py`, new `services/review_service.py`
(`save_review_event`/`list_review_events_for_trace`), new API routes
`POST /review/events` and `GET /review/events?trace_id=...`. This is the one place this
milestone actually writes to the database — reviewer actions are exactly the kind of
event that must survive a process restart; the import-answer computation itself does
not need to (§4).

## 6. Privacy and credential handling

- The Anthropic API key never appears in any Pydantic model, any DB row, or any log
  line — enforced by never assigning `os.environ[...]` to anything but a local variable
  passed straight into the SDK client constructor, and tested directly (§7, test 5).
- `reviewer_id`/`session_id` on `ReviewEvent` are opaque strings the caller supplies;
  this milestone does not add authentication — that remains out of scope, noted in §8.
- `raw_output` (the provider's raw response text) is stored only when
  `store_raw_output=True` is explicitly passed, never by default (§2).

## 7. Tests

One or more tests per required category (14 categories, listed verbatim in the task and
implemented as described in the final report), split across
`tests/unit/test_answer_claims.py`, `tests/unit/test_claim_linking.py`,
`tests/unit/test_review_events.py`, `tests/unit/test_provider_client.py`, and
`tests/integration/test_imported_answer_review.py`.

## 8. What remains deferred

- Dense/hybrid retrieval (explicitly out of scope for this task).
- A live network call against the Anthropic API (no credentials in this environment;
  the client is implemented and unit-testable, not integration-tested against the
  real service).
- Persisting `PipelineManifest`/`QueryTrace`/`ApplicabilityAssessment` rows from
  `POST /review/import-answer` into the existing (currently unused) audit tables —
  only `ReviewEvent`s are persisted this milestone, since those are the only records
  the task requires to survive a restart.
- Renaming `demo/pipeline.py`'s generic orchestration into a neutral `pipeline/`
  module now shared by both the demo and `review/imported_answer.py` (see §1's layering
  note).
- Authentication/authorization for reviewer identity — `reviewer_id` is caller-supplied
  and unverified.
- Frontend build tooling — the review screen (§H of the task) is a single static HTML
  file with vanilla JS `fetch` calls, matching `frontend/README.md`'s existing
  "no build tooling wired up yet, no polish before the loop works" stance; a real
  framework-based frontend remains future work.
- A real `conflict_candidate` contradiction detector beyond the existing Tier-2
  negation-cue heuristic — genuine contradiction detection is a harder problem than
  this milestone's scope; the current heuristic is conservative and clearly labeled.
