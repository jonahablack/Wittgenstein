# Registry governance

## Activation policy: a three-stage graduation path, separate from evidence status

`ActivationPolicy` (`core/enums.py`) governs whether a mechanism's `RiskEvent`s are
shown to reviewers and with what priority weight — a question that is **necessary but
not sufficient**-gated by `epistemic_status`, never automatically derived from it.
Reaching `externally_established` certifies the *evidence*; it says nothing about
whether *this specific mechanism, in a specific deployment*, has earned reviewer trust
for queue ordering. Those are different questions, deliberately kept on different
axes — the same discipline ADR 0002 applies to evidence grade / epistemic status /
transfer level extends here to activation policy as a fourth, independent axis.

Alongside the original `ENABLED_BY_DEFAULT` and `ENABLED_WITH_MANIFEST_GATES` values
(unchanged; `PACK_OMISSION_OR_TRUNCATION` uses the latter), three additional values
form an explicit graduation path for a mechanism whose evidence has cleared
`externally_established` but whose deployment-trust level has not yet been separately
earned:

1. **`shadow`** — evaluated and logged (produces an `ApplicabilityAssessment`) but
   never contributes a priority-bearing `RiskEvent`. Pure observability: use this for a
   newly-`externally_established` mechanism before any manifest-gate design has been
   reviewed for false-positive risk.
2. **`manifest_conditioned`** — a `RiskEvent` is created once the mechanism's manifest
   and trace gates all genuinely pass (never by default assumption — the same
   `UNKNOWN_INSUFFICIENT_DATA` discipline as every other gate in this system), but its
   `priority_tier` is capped below `PriorityTier.HIGH`
   (`services/applicability_service.py::_capped_priority_tier`) — displayed to
   reviewers, not yet fully trusted for queue ordering.
3. **`triage_enabled`** — full, uncapped priority weight. Promotion from
   `manifest_conditioned` requires a `LocalValidationRecord` establishing
   `reviewer_yield` for this mechanism in a specific deployment (see
   `docs/research-protocol.md`) — i.e. evidence that reviewers acting on this
   mechanism's flags actually confirm real issues at a useful rate, not merely more
   literature evidence. This is a deliberate, separate registry-governance decision
   each time, following the same status-change discipline as the table below — never a
   pass-through consequence of accumulating more evidence records.

### `REP_SEGMENTATION_GRANULARITY_MISMATCH`: worked example (2026-09-09)

The first mechanism to reach `externally_established` (two independent, RAG-native,
verified A2 records — see `docs/literature-review-second-review-results.md`) was moved
from `disabled_by_default_or_research_mode` to `manifest_conditioned`, not
`triage_enabled`, illustrating the distinction above:

- `externally_established` is necessary but not sufficient for universal activation —
  it certifies the evidence, not this deployment's fit to it.
- This mechanism is activated *conditionally* because transfer from the two studies'
  envelopes to any specific deployment still depends on that deployment's actual
  segmentation manifest and observed trace boundary flags — `manifest_conditioned`
  means the risk event is shown only when both gate families genuinely pass, never by
  default assumption.
- Default activation is a distinct axis from `epistemic_status`/`verification_status`:
  reaching `externally_established` with verified evidence removes the validator's
  structural block on non-disabled activation, but does not itself justify full
  (`triage_enabled`) trust — that is always a separate, deliberate decision.
  `registry/validator.py` was **not** changed to enforce this as a hard rule; it is
  enforced by governance discipline (this document) and locked in by regression tests
  (`tests/integration/test_rep_segmentation_activation_policy.py`).
- Future promotion to `triage_enabled` requires a `LocalValidationRecord` establishing
  `reviewer_yield` for this mechanism in a specific deployment — not merely additional
  literature evidence, and not automatic even after that record exists (see the status
  table below).

Its five activation gates — implemented, unchanged, in
`matching/eligibility.py::_eval_rep_segmentation_granularity_mismatch` — are: (1) the
system uses independently retrievable segmented units (`retrieval_unit` is not
`whole_document`); (2) `chunking_method` and `retrieval_unit` are both known; (3)+(4)
the trace records a support/dependency relation crossing a segment boundary — the
`segment_boundary_dependency_flags` field, which by construction means that dependency
is actually separated in the retrieval/packing path, not merely hypothetically
possible; (5) any unknown required manifest field yields
`unknown_insufficient_data`, never an assumed pass. Chunking merely existing, a large
corpus, a specific chunker family (fixed-size/semantic/propositional), a short
retrieved passage, or an incorrect-looking answer are each, alone, insufficient — the
mechanism has no field that reads answer correctness at all, and the manifest gates
have no field that reads corpus size or chunker family as a trigger.

The risk event's reviewer-facing language is bounded to a specific, pre-approved
sentence for this mechanism (`matching/explanation.py::_MECHANISM_BOUNDED_CLAIM_LANGUAGE`):
"This trace exhibits a segmentation/evidence-boundary configuration under which
segmentation-related retrieval or answer-quality degradation has been experimentally
observed." It must never be rendered as "the chunker caused the error," "this answer is
wrong," or "this chunking method is generally unsafe" — none of those are supported by
the underlying evidence (both linked records are `controlled_comparison`, not
`causal_intervention`, so `causal_claim_allowed` is structurally `False` for this
mechanism regardless of transfer level — see `matching/explanation.py::_causal_claim_allowed`).

## Mechanism vs. subtype

Use **one** canonical `FailureMechanism` when the causal trigger and the reviewer
action are the same, even if the task, corpus, model, position, or retrieval envelope
differs — that variation belongs on `ExperimentalEnvelope`/`ManifestGate` fields
(`position_rank`, `context_window_tokens`, `chunking_method`, etc.), not as a new
mechanism id. Create a **separate** mechanism only when the causal pathway,
experimental intervention, or reviewer action genuinely differs.

Example: position-sensitive use of long packed context is one mechanism
(`CTX_POSITION_SENSITIVE_USE`) parameterized by position and context-length fields. It
would be split into a second mechanism from, say, a hypothetical
"position-amplified hard distractor" only if that phenomenon's causal pathway (what
makes the item risky) and reviewer action (what a human is asked to check) actually
differ from plain position-sensitivity — not merely because the envelope differs.

## Additions

A new `FailureMechanism` always starts `epistemic_status=research_hypothesis`,
`default_evidence_grade=E_hypothesis`,
`default_activation_policy=disabled_by_default_or_research_mode` — enforced by
`schemas/failure_mode.py::FailureMechanism._research_hypothesis_cannot_be_a_graded`.
There is no path to add a mechanism directly as `externally_established`; it must
earn that status through the process below.

## Edits

Non-status edits (description clarity, additional boundary conditions, tag changes)
require no special review beyond normal code review, but must not silently change
`epistemic_status`, `default_evidence_grade`, or `default_activation_policy` as a side
effect — those are always separate, deliberate edits.

## Status changes

| From | To | Requirement |
|---|---|---|
| `research_hypothesis` | `manifest_conditioned_transfer` or `externally_established` | At least one new, verified evidence record meeting the target status's requirements (see `docs/evidence-grading.md`) |
| any evidence-dependent status | `trace_integrity_condition` | The claim is re-scoped to a directly observable trace fact rather than a broader causal claim |
| `research_hypothesis` or `manifest_conditioned_transfer` | `locally_validated` | A `LocalValidationRecord` per `docs/research-protocol.md`, scoped to one deployment |
| `locally_validated` | `externally_established` | **Never automatically.** Requires independent, external, peer-reviewed A1/A2 evidence — a local result is not that, no matter how strong, because it hasn't been independently replicated or peer-reviewed. See "why local validation doesn't universalize" below. |
| any | `unsupported_or_retired` | A literature review or local study found the claim unsupported, or a mechanism was merged into another; `default_activation_policy` must become `retired` |

Every status change bumps `registry_version` at the MAJOR level
(`docs/registry-spec.md`).

## Deprecations and merges

A retired mechanism keeps its record (`epistemic_status=unsupported_or_retired`) —
it is never deleted from the seed file. If two mechanisms are found to describe the
same underlying signal (the way this project's design notes describe collapsing
`detect_hedges` into `detect_modal_mismatch` in an earlier, unrelated tool — see
`docs/implementation-plan.md` §0), retire the redundant one and note the merge target
in its `known_boundary_conditions`, rather than silently deleting it and leaving any
external reference dangling.

## How contradictory evidence is recorded

As two (or more) separate `EvidenceRecord`s linked to the same mechanism, each with
its own `stated_limitations` and its own `direction` (`supports` / `refutes` / `mixed`
/ `null`). The registry does not compute a "winner" or average directions into a
confidence score — see `REP_SEGMENTATION_GRANULARITY_MISMATCH`, seeded with one
`supports` and one `mixed` record. The mechanism's own `evidence_synthesis` field
(`convergent` / `mixed` / `limited` / `unresolved`) is a separate, human-set summary of
how the full set of linked records relate: `convergent` only once independent records
broadly agree, `mixed` when they genuinely disagree, `limited` for one study (or too
few/weak to call convergent), `unresolved` when no qualifying evidence exists yet
(every `research_hypothesis` mechanism is `unresolved` by construction). A dossier
reader sees every record and forms their own judgment; a mechanism whose evidence is
genuinely contradictory should say so plainly in its `known_boundary_conditions` rather
than presenting one study as representative.

A separate contradiction entity (rather than multiple directioned `EvidenceRecord`s) is
used only when the disagreement itself is the object of study — e.g. a meta-analysis
explaining why two lines of research disagree — which this registry does not currently
seed any instance of.

## Corpus properties

The following are `CorpusProfile` **profiling variables** by default, not failure
mechanisms: corpus heterogeneity (`topic_heterogeneity_metrics`), redundancy
(`redundancy_metrics`), document length (`document_length_distribution`),
cross-reference density (`cross_reference_density`), table density (`table_density`),
version density (`version_or_effective_date_density`), terminology variation
(`terminology_variability_metrics`), and evidence dispersion
(`evidence_dispersion_metrics`). They may condition manifest gates and
transferability (e.g. a high-redundancy corpus might strengthen a distractor
mechanism's `strengthening_predicates`), but a corpus property does not become its own
`FailureMechanism` unless a study demonstrates a generalizable causal pathway *and* a
downstream reliability effect specifically attributable to that property — a
correlational note ("failures seem more common in heterogeneous corpora") is not
sufficient on its own; see the evidence-threshold rule in `docs/evidence-grading.md`
for what "demonstrates" requires.

Note `CorpusProfile` (observed structural statistics, above) is a different schema
from `PipelineManifest.corpus_manifest` (declared system configuration: `domain`,
`document_count`, `corpus_versioning`) — see `docs/manifest-spec.md`.

## Local validation: promotion requirements

Promotion of a `LocalValidationRecord` toward supporting a mechanism's `locally_validated`
status requires `LocalValidationRecord.meets_promotion_bar()` to be `True`:

- `preregistered=True` — the flag and outcome measure were specified before the
  evaluation ran, not selected after seeing results.
- `evaluation_split` — a described held-out or preregistered split.
- `corpus_description`, `manifest_description`, `query_distribution_description` — the
  exact conditions the result applies to, documented (not just named in
  `deployment_scope`).
- `label_source` — how ground-truth labels were produced.
- `reviewers` — non-empty.
- `precision`, `recall`, `reviewer_yield` — all reported, not just a headline number.
- `uncertainty` — a confidence interval or qualitative uncertainty statement.
- `replication_notes` — encouraged where feasible (replication across corpus slices or
  task types) but not required by `meets_promotion_bar()`, since not every deployment
  can support multiple slices.

Meeting the bar makes a record *eligible* for the status-change review in the table
above; it does not itself perform the promotion, which remains a deliberate,
separately-reviewed registry edit.

## Promotion to `TRIAGE_ENABLED`

A distinct gate from the `locally_validated` promotion above — `epistemic_status` and
`ActivationPolicy` are independent axes (see "Activation policy," top of this
document). **A mechanism is never automatically promoted to `TRIAGE_ENABLED` based on a
`LocalValidationRecord`.** `LocalValidationRecord.meets_triage_promotion_bar()` checks
only record-completeness — it is necessary, never sufficient. A mechanism may be
*considered* for `TRIAGE_ENABLED` only when a human registry-governance decision
confirms all ten of the following against the full study design
(`docs/local-validation-protocol.md`):

1. External evidence and manifest-conditioned activation requirements are met (i.e.
   the mechanism is already `externally_established` or `manifest_conditioned_transfer`
   and currently `manifest_conditioned`).
2. Reviewers understand the warning and its evidence status.
3. The warning improves at least one meaningful reviewer-experience or workflow
   outcome (`docs/reviewer-measures.md`, Layer C).
4. It improves or preserves context sensitivity and user-intent responsiveness
   (Layer B; `docs/local-validation-protocol.md`, "User-intent responsiveness").
5. It does not materially worsen false reassurance, false approval, false rejection,
   unnecessary escalation, alert burden, or reviewer autonomy.
6. Where a defensible factual/evidence adjudication target exists, the warning does not
   reduce detection of material support problems beyond a pre-specified tolerance
   (Layer A).
7. Results are documented for the tested corpus, manifest, query distribution, and
   reviewer population (`LocalValidationRecord.reviewer_population`, `corpus_slices`,
   `study_design`).
8. The result is replicated across at least two corpus slices or task types where
   feasible (`corpus_slices`; `len(corpus_slices) >= 2` or documented infeasibility in
   `replication_notes`).
9. Reviewers can override, dismiss, or escalate the warning (`AutonomyAndTrustEvidence.override_or_reject_rate`
   measured, not merely assumed possible).
10. The mechanism-specific warning is more useful than simply showing generic
    provenance or the full retrieved set (i.e. the study's condition 2 vs. 3
    comparison, `docs/local-validation-protocol.md`, actually isolates a marginal
    effect attributable to the warning).

Criteria 3–6 and 10 require substantive judgment about the *results*, not just the
record's completeness, and are therefore never checked by code — `meets_triage_promotion_bar()`
covers only criteria 2 (evidenced by having reviewer-experience data at all), 7, 8, and
the structural preconditions for 1 (it does not itself verify the mechanism's current
`epistemic_status`/`ActivationPolicy`, which the registry, not the record, tracks).

Local validation may change **deployment priority only**. It must never change:
external evidence grade, the canonical mechanism claim, universal epistemic status, or
the historical evidence record — a `LocalValidationRecord`, however negative its
result, is additive to the registry's history, never a deletion or silent overwrite of
the mechanism it studied.

## Why local validation does not convert to a universal external claim

A `LocalValidationRecord` is, by construction, scoped to one `deployment_scope`: one
corpus, one retriever config, one generator, observed over some time window. Even a
well-designed local causal study cannot rule out that the effect is specific to that
deployment's corpus structure, query distribution, or model choice — the same
limitation that makes any single-site study weaker evidence than an independently
replicated, peer-reviewed one. Treating a local result as globally established would
mean this project's own convenience sample silently became the entire evidentiary
basis for a claim presented to every user of the registry. `registry/validator.py`
enforces the code-level half of this: `externally_established` status checks for
peer-reviewed A1/A2 `EvidenceRecord`s specifically, and a `LocalValidationRecord` is a
structurally different type that the check does not (and must not) accept.

What a strong local validation result *can* do: raise `priority_tier` for risk events
from that mechanism *within that deployment* (see `services/applicability_service.py`),
and make a strong case for prioritizing that mechanism in the next literature-review
pass, since local evidence is a signal that external evidence may exist or be worth
generating.

## How interface language is controlled by evidence status and transfer level

All product-facing wording is generated by `matching/explanation.py`, keyed off
`epistemic_status` (`_CLAIM_LANGUAGE`) and gated by `_causal_claim_allowed`, which
additionally requires `transfer_level` to be `directly_matched` or
`mechanistically_matched` and at least one verified, peer-reviewed, A-grade,
`causal_intervention`-type evidence record. There is no code path that lets a UI or
API caller override this wording with a stronger claim — a caller can only ask for
the assessment of a different mechanism/manifest/trace, not for different phrasing of
the same one. Any future UI work must render `allowed_claim_language` and
`explanation` as given, not paraphrase them.
