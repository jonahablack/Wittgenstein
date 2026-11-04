# CLAUDE.md

Persistent rules for working on this repository. This file is a concise index of
binding rules; the linked docs carry the full detail and are the source of truth if
this file and a doc ever appear to disagree.

## Project purpose

Wittgenstein is a versioned, evidence-graded registry of experimentally investigated
RAG (Retrieval-Augmented Generation) failure mechanisms, plus schemas and deterministic
tooling to match a pipeline manifest and per-query execution trace to only the failure
mechanisms whose experimental prerequisites are actually present. It is not a
chat-with-documents product and not an opaque hallucination detector — it is
infrastructure for a human-in-the-loop RAG verification workflow. It prioritizes and
structures human review; it does not replace it. See `README.md` and
`docs/architecture.md`.

## Registry-first implementation order

The registry (schemas, seed data, deterministic matching, CLI/API to query it) is the
first-class artifact, built before any product UI or generic RAG pipeline. Every other
component is a *consumer* of the registry, never a place that invents its own parallel
notion of "this looks like a failure." See `docs/adr/0001-registry-first-architecture.md`
and `docs/implementation-plan.md` for build order.

## Epistemic statuses (`EpistemicStatus`, `core/enums.py`)

- `externally_established` — meets the evidence-threshold rule below. Enforced at
  registry load time (`registry/validator.py`).
- `manifest_conditioned_transfer` — established in a related setting, or by a single
  narrow study; transfers to this system only under specific manifest conditions.
- `trace_integrity_condition` — a directly observable pipeline fact, usable without
  external evidence, but never claims causality toward a specific answer error without
  linked causal evidence or local causal validation.
- `research_hypothesis` — disabled by default, not evidence-backed for RAG. Cannot
  carry an A-grade or `evidence_synthesis` other than `unresolved` — enforced by
  `schemas/failure_mode.py`.
- `locally_validated` — has a `LocalValidationRecord`, scoped to one deployment. Never
  auto-promotes to `externally_established`.
- `unsupported_or_retired` — kept as a record, not deleted.

See `docs/evidence-grading.md`.

## Evidence grades (`EvidenceGrade`, `core/enums.py`)

`A1_direct_causal_peer_reviewed` > `A2_strong_comparative_peer_reviewed` >
`B1_mechanistic_transfer_peer_reviewed` > `B2_component_evidence_peer_reviewed` >
`C_preprint_empirical` > `D_local_empirical` > `E_hypothesis`. Independent of a
mechanism's `epistemic_status` — see `docs/evidence-grading.md`.

## Mechanism vs. subtype rule

Use **one** canonical `FailureMechanism` when the causal trigger and the reviewer
action are the same, even if task, corpus, model, position, or retrieval envelope
differs — envelope differences belong on `ExperimentalEnvelope`/`ManifestGate` fields,
not as a new mechanism. Create a **separate** mechanism only when the causal pathway,
experimental intervention, or reviewer action genuinely differs. Example:
position-sensitive evidence use is one mechanism (`CTX_POSITION_SENSITIVE_USE`) with
position/length fields; it would be split from a hard-distractor-at-position mechanism
only if their causal mechanisms and reviewer actions actually differ. See
`docs/registry-governance.md`.

## Evidence-threshold rule

`externally_established` requires evidence meeting **all** of: peer-reviewed, A1/A2
grade, `experimental_envelope.rag_presence=True`, `direction=supports` — **and** either
(a) at least one such record graded A1 ("one closely matched A1 study with strong
evidence"), or (b) at least two independent such records ("at least two independent,
broadly consistent A1/A2 studies"). A single A2-only record is not sufficient — a
single narrow benchmark must never be presented as a universal law. Enforced in
`registry/validator.py::_check_established_status_requires_a_grade_evidence`. See
`docs/evidence-grading.md`.

## Long-context transfer rule

A finding from a non-RAG setting (long-context QA, multi-document summarization without
retrieval) can never by itself reach `externally_established`, however strong its
grade — it is capped at `manifest_conditioned_transfer` until RAG-specific evidence
justifies promotion. "Lost in the Middle" (`CTX_POSITION_SENSITIVE_USE`) is seeded this
way and is the canonical example. Enforced via the `rag_presence` check in the rule
above, not left to convention. See `docs/evidence-grading.md`.

## Corpus-profile rule

Corpus heterogeneity, redundancy, document length, cross-reference density, table
density, version density, terminology variation, and evidence dispersion are
`CorpusProfile` **profiling variables** by default — they may condition manifest gates
and transferability, but do not become a standalone `FailureMechanism` unless a study
demonstrates a generalizable causal pathway and downstream reliability effect. See
`docs/registry-governance.md`.

## Local-validation rule

A `LocalValidationRecord` may change **deployment-specific triage priority**
(`deployment_priority`) but must never alter a mechanism's global
`external_evidence_status`/`epistemic_status`. Promotion to `locally_validated` requires
`LocalValidationRecord.meets_promotion_bar()`: preregistered flag+outcome, a documented
held-out/preregistered split, documented corpus/manifest/query-distribution/reviewers/
labels, and reported precision/recall/reviewer-yield/uncertainty (replication across
corpus slices or task types noted where feasible). Promotion itself is always a
deliberate, separate registry-governance edit — never automatic. See
`docs/registry-governance.md` and `docs/research-protocol.md`.

## Local-validation and `TRIAGE_ENABLED` promotion rule

A local-validation study evaluating a manifest-conditioned warning is never a single
accuracy score. It has six independent outcome layers — evidence/factual adjudication,
contextual judgment, reviewer experience/workflow, human autonomy/trust calibration,
alert fatigue/AI burnout, and user-intent responsiveness — each backed by its own
`LocalValidationRecord` evidence-layer sub-model (`schemas/review.py`;
`docs/reviewer-measures.md` is the measurement dictionary). Factual adjudication
remains part of the evaluation wherever a defensible target exists, but it is not the
sole endpoint, and reviewer experience is not a substitute for it either — a tool that
saves time but increases false reassurance (`FalseReassuranceAnalysis`) is not a
success. Unresolved, version-dependent, jurisdiction-dependent, and other contested
outcomes (`core/enums.py::AdjudicationOutcome`) are valid results, never automatically
counted as reviewer error. `LocalValidationRecord.meets_triage_promotion_bar()` checks
only record completeness for `ActivationPolicy.TRIAGE_ENABLED` eligibility — it is
necessary, never sufficient; the full ten-point checklist
(`docs/registry-governance.md`) always requires a human decision, and local validation
may change deployment priority only, never external evidence grade, epistemic status,
or the historical evidence record. See `docs/local-validation-protocol.md`.

## Risk-triage engineering conventions

Generalizable, durable lessons — some informed by a sibling artifact in the parent
workspace, `../risk_triage_edge_cases.txt` (an unrelated, non-RAG claim-formalization
classifier's edge-case log; extracted only where the lesson is general enough to apply
here, never copied wholesale — see `docs/implementation-plan.md` §0):

- Never infer missing manifest values. An unknown field is
  `insufficient_manifest_information`, never assumed satisfied or violated.
- Distinguish possible risk from observed failure. A `RiskEvent` reports an observed
  trace condition, not a confirmed cause, unless causal language is explicitly gated on
  (`matching/explanation.py`).
- Distinguish source conflict from answer conflict. `QueryTrace.context_conflicts`
  (packed context contains incompatible claims) and
  `AnswerSupportEdge.support_status="contradicted"` (the answer itself contradicts a
  packed item) are separate signals and must not be merged — see `docs/trace-spec.md`.
- Never infer causality from a trace fact alone. `RiskEvent.causal_claim_allowed=True`
  requires a linked evidence record or local causal validation
  (`schemas/review.py::RiskEvent._causal_claim_requires_support`).
- Preserve inactive mechanisms and explain non-activation. `unsupported_or_retired` is
  a real status, never a deleted row; every `EligibilityGateResult` carries a `reason`.
- Do not silently suppress low-priority evidence. Contradictory, null, or
  non-peer-reviewed evidence is recorded as its own `EvidenceRecord`, never discarded or
  averaged away — see `evidence_synthesis` on `FailureMechanism`.
- Every risk event must expose its trigger, evidence status, transfer level, and
  reviewer action — `RiskEvent` carries `trace_trigger_id`, `epistemic_status`,
  `transfer_level`, and `reviewer_action` as separate, always-populated fields.

General engineering lessons also adopted as design constraints (see
`docs/implementation-plan.md` §0 for the full derivation): avoid boolean collapse of
distinct outcomes (three-valued `GateResultStatus`, four-valued `TransferLevel`, etc.);
avoid two lists/tables describing "the same categories" that can drift out of sync (one
canonical enum per axis, in `core/enums.py`, imported everywhere); distinguish "a
trigger condition is present" from "present and well-formed enough to support the claim
being made"; prefer deterministic, inspectable rules over ML/embedding heuristics for
primary eligibility decisions; when retiring/rejecting something, mark it explicitly
rather than leaving a silently inert entry.

## Prohibition on fabrication

Never fabricate citations, quotes, effect sizes, venues, or any other evidence
metadata. `exact_quote` must be copied verbatim from the primary source; if unverified,
leave the literal `"TODO: verify against primary source"` placeholder and set
`verification_status: unverified` — never invent plausible-sounding text.
`registry/validator.py` enforces this in code (a `verified` record cannot contain a
`TODO`; non-disabled activation cannot rest on unverified evidence) — see
`CONTRIBUTING.md` and `docs/literature-review-protocol.md`.

## Commands

```bash
uv sync --extra dev          # install
make fmt                     # ruff format
make lint                    # ruff check
make typecheck                # mypy src
make test                     # pytest
make schemas                  # export JSON Schema to schemas/generated/
make validate-registry        # uv run python scripts/validate_seed_registry.py
make dev-check                 # all of the above, in order — run before declaring work complete
make api                       # run the FastAPI dev server
uv run wittgenstein registry list
```

## Working conventions

- Use plan mode for any change touching more than one architectural component (e.g.
  registry schema + validator, or matching engine + explanation renderer).
- Add or update tests alongside any change to epistemic-status or manifest/trace-gating
  behavior (`tests/unit`, `tests/integration`) — this project treats that coverage as
  part of the change, not optional follow-up.
- Run `make dev-check` before declaring work complete.
- Keep pipeline-stage and epistemic vocabulary confined to `core/enums.py` — never
  introduce a parallel ad hoc status string.
- See `CONTRIBUTING.md` for the higher review bar on registry content changes
  (`FailureMechanism`/`EvidenceRecord` edits).
