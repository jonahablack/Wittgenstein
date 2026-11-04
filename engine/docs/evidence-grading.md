# Evidence grading and epistemic status

Two independent axes. Do not conflate them.

## Epistemic status (`EpistemicStatus`, `core/enums.py`)

A property of a **mechanism**: how strongly its real-world applicability is
established, taken as a whole across all its linked evidence.

- `externally_established` — at least one linked evidence record is peer-reviewed and
  graded A1 or A2. Enforced at registry load time
  (`registry/validator.py::_check_established_status_requires_a_grade_evidence`); the
  registry fails to load otherwise.
- `manifest_conditioned_transfer` — established in a related setting (e.g. plain
  long-context LLM behavior), but transfer to a RAG system is conditional on specific
  manifest facts (multiple packed items, sufficient packed length, etc.).
- `trace_integrity_condition` — a directly observable pipeline fact (e.g. "a selected
  item was never packed"). Usable without any external evidence record at all, because
  the trace itself is the evidence — see `PACK_OMISSION_OR_TRUNCATION`. It cannot,
  however, claim causality toward a specific answer error without a linked causal
  evidence record or local causal validation
  (`schemas/review.py::RiskEvent._causal_claim_requires_support`).
- `research_hypothesis` — plausible, disabled by default, not evidence-backed for RAG.
  A mechanism cannot be `research_hypothesis` and carry an A-grade
  (`schemas/failure_mode.py::FailureMechanism._research_hypothesis_cannot_be_a_graded`).
- `locally_validated` — has a `LocalValidationRecord` from this project's own testing,
  scoped to one deployment. Never auto-promotes to `externally_established` — see
  `docs/registry-governance.md`.
- `unsupported_or_retired` — kept as a record (with `default_activation_policy:
  retired`), not deleted, so the history of "we looked into this and it didn't hold
  up" is preserved.

## Evidence grade (`EvidenceGrade`, `core/enums.py`)

A property of one **evidence record** — independent of the mechanism's overall
status. A mechanism can be `manifest_conditioned_transfer` while its one evidence
record is graded A1, precisely because the *study* was rigorous but its *setting*
wasn't RAG (see `CTX_POSITION_SENSITIVE_USE` / "Lost in the Middle").

| Grade | Meaning |
|---|---|
| `A1_direct_causal_peer_reviewed` | Peer-reviewed, causal intervention, direct to the claim |
| `A2_strong_comparative_peer_reviewed` | Peer-reviewed, strong controlled comparison |
| `B1_mechanistic_transfer_peer_reviewed` | Peer-reviewed, mechanistic but requires transfer reasoning |
| `B2_component_evidence_peer_reviewed` | Peer-reviewed, evidence about one pipeline component |
| `C_preprint_empirical` | Empirical but not (yet) peer-reviewed |
| `D_local_empirical` | This project's own local testing |
| `E_hypothesis` | No empirical support yet |

`A1`/`A2` require `peer_review_status=peer_reviewed`
(`schemas/evidence.py::EvidenceRecord._a_grade_requires_peer_review`) — a preprint
cannot be graded A1/A2 regardless of how strong its result looks.

## Verification is a third, orthogonal axis

`VerificationStatus` (`verified` / `unverified` / `disputed` / `retracted_source`)
tracks whether a human has actually checked `exact_quote` and metadata against the
primary source. A record can be `evidence_grade=A2` (the *type* of study, once
verified, would be A2-strength) while `verification_status=unverified` (nobody has
actually confirmed the quote yet). The registry validator refuses non-disabled
`default_activation_policy` for any mechanism whose `externally_established` or
`manifest_conditioned_transfer` status rests on unverified evidence
(`registry/validator.py::_check_activation_requires_verified_evidence`). As of the
2026-09-09 second-review pass (`docs/literature-review-second-review-results.md`), all
8 evidence records across all 7 concrete mechanisms are `verified` — but verification
alone still does not grant activation; see `data/registry/README.md` and, for the
fourth independent axis this unlocks, "Activation policy is necessary-but-not-sufficient"
below.

## Activation policy is necessary-but-not-sufficient, even once evidence is verified

Evidence grade, epistemic status, transfer level, and verification status are each
already kept independent (ADR 0002; the paragraph above). `ActivationPolicy`
(`core/enums.py`) is a **fourth** independent axis, governing whether a mechanism's
`RiskEvent`s are shown to reviewers at all and with what priority — and reaching
`externally_established` with `verified` evidence, together, remove only the
*structural* block on non-disabled activation (the validator check above); they do not
themselves justify full activation. Changing `default_activation_policy` is always a
separate, deliberate registry-governance decision — see
`docs/registry-governance.md`, "Activation policy: a three-stage graduation path,"
for the `shadow` / `manifest_conditioned` / `triage_enabled` graduation path this
project uses, and the worked example of applying it to
`REP_SEGMENTATION_GRANULARITY_MISMATCH`, the first mechanism to reach this point.

**Factual adjudication is a fifth, still-independent axis, not a synonym for evidence
grade.** `EvidenceGrade` describes the strength of *external published research*
behind a mechanism's causal claim. `AdjudicatedTraceEvidence` (`schemas/review.py`),
part of the local-validation outcome model, describes whether a *specific reviewer, on
a specific trace, in a local study*, correctly judged that trace's evidence — a
completely different kind of evidence, scoped to one deployment, never fed back into
`evidence_grade`. See `docs/local-validation-protocol.md` and
`docs/reviewer-measures.md` for the full multidimensional model this belongs to;
factual adjudication remains part of that evaluation, but it is not the sole metric,
and unresolved/contested outcomes are valid results there, not a failure of grading.

## Evidence thresholds

`externally_established` requires qualifying evidence — peer-reviewed, A1/A2 grade,
`experimental_envelope.rag_presence=True`, `direction=supports` — meeting **either**:

- **Path A**: at least one qualifying record graded A1 ("one closely matched A1 study
  with strong evidence"); or
- **Path B**: at least two independent qualifying records, any mix of A1/A2 ("at least
  two independent, broadly consistent A1/A2 studies").

A single A2-only record no longer qualifies on its own. This is a deliberate
tightening: a single narrow benchmark must not be presented as a universal law. Applied
retroactively to this bootstrap registry, it reclassified three of the original seven
concrete mechanisms (`RET_HARD_DISTRACTOR`, `RET_MULTIHOP_SUPPORT_INCOMPLETE`,
`GEN_UNSUPPORTED_DESPITE_CONTEXT` — each backed by exactly one A2 record) from
`externally_established` to `manifest_conditioned_transfer`; each now carries a
`known_boundary_conditions` entry explaining why. Enforced in
`registry/validator.py::_check_established_status_requires_a_grade_evidence`.

This is distinct from **conditional activation**: `ActivationPolicy` governs whether a
mechanism fires by default at all (independent of this threshold), and is currently
`disabled_by_default_or_research_mode` for every evidence-dependent mechanism in this
bootstrap registry regardless, because no evidence record is yet `verified` — see "Why
`TRACE_INTEGRITY_CONDITION`..." below and `docs/registry-governance.md`.

## Long-context transfer: directly_rag_established / manifest_conditioned_transfer / untransferred

This project deliberately does **not** add a second, parallel enum for this
distinction — that would recreate exactly the "two lists describing the same
categories, drifting out of sync" failure `docs/implementation-plan.md` §0 warns
against. Instead, the three-way distinction maps onto the existing `EpistemicStatus` /
`TransferLevel` model:

- **`directly_rag_established`** — `epistemic_status=externally_established` *and* the
  qualifying evidence is RAG-native (`rag_presence=True`, enforced by the threshold
  rule above) *and*, at assessment time, `transfer_level=directly_matched`.
- **`manifest_conditioned_transfer`** — the existing status. Now deliberately broad
  enough to cover two distinct reasons a mechanism lands here: (a) the evidence is
  strong but was collected in a **non-RAG** setting (long-context/multi-document
  studies without retrieved-context generation — the original meaning, e.g. "Lost in
  the Middle" / `CTX_POSITION_SENSITIVE_USE`), or (b) the evidence **is** RAG-native but
  too narrow on its own (single-study, below the two-path threshold above — the newly
  reclassified three mechanisms). Both share the same underlying shape: the claim is
  real but its application to *your* manifest is conditional on a close envelope match,
  whether the gap is domain or narrowness.
- **`untransferred`** — no separate status; expressed per-assessment as
  `transfer_level` in `{partially_matched, not_applicable, insufficient_manifest_information}`,
  or at the mechanism level as `epistemic_status` in
  `{research_hypothesis, unsupported_or_retired}`.

A non-RAG-native A1/A2 record can never by itself ground `externally_established`,
however strong its grade — this is enforced, not left to convention.

## Transfer level (`TransferLevel`)

Not part of the mechanism record — computed per assessment
(`matching/transferability.py`), by comparing a manifest/trace-derived
`ExperimentalEnvelope` against a linked evidence record's envelope, field by field:

- `directly_matched` — every jointly-known dimension matches, evidence's own setting
  was RAG, and there are no unknown dimensions.
- `mechanistically_matched` — matches on known dimensions, but either the evidence's
  setting wasn't RAG (needs a mechanistic transfer step) or some dimensions remain
  unknown (fewer unknowns than matches).
- `partially_matched` — at least one dimension actively mismatches, or unknowns
  outweigh matches.
- `not_applicable` — a manifest gate or trace observable was definitively violated.
- `insufficient_manifest_information` — not enough is known to say anything.

There is deliberately no numeric similarity score anywhere in this computation.

## Why `TRACE_INTEGRITY_CONDITION` sometimes shows `directly_matched` with no evidence

`services/applicability_service.py::assess_mechanism` special-cases
`trace_integrity_condition` mechanisms: since there is no external study whose
*setting* needs to transfer (the trace observation is the evidence), the standard
evidence-envelope comparison doesn't apply, even if a placeholder `EvidenceRecord`
exists purely to track an open literature-search task
(`PACK_OMISSION_OR_TRUNCATION`'s `EV-PACK_OMISSION_OR_TRUNCATION-001` has an empty
envelope for exactly this reason). In that one case, `directly_matched` means "the
trace directly and unambiguously exhibits this condition," not "matches an evidence
record's envelope." This is documented here precisely because it is the one place the
enum's ordinary meaning is stretched, and future contributors should not assume it
means the same thing it means everywhere else.
