# ADR 0002: Separate epistemic status, evidence grade, and transfer level

## Status

Accepted.

## Context

A single "confidence" field on a mechanism would conflate three genuinely different
questions: (1) how strong is the underlying research, in general, about this
mechanism (evidence grade, per-record); (2) how strong is our overall claim about the
mechanism (epistemic status, per-mechanism); and (3) does *this specific manifest and
trace* actually match the setting that research was conducted in (transfer level,
per-assessment). Collapsing them produces exactly the "two lists describing the same
categories, drifting out of sync" failure documented in
`docs/implementation-plan.md` §0 — except worse, because it would drift by design
rather than by accident.

## Decision

Three independent enums (`EpistemicStatus`, `EvidenceGrade`, `TransferLevel`), each
computed at a different layer, never merged:

- `EvidenceGrade` lives on `EvidenceRecord`, assigned once during literature review.
- `EpistemicStatus` lives on `FailureMechanism`, computed by aggregating over all its
  evidence records (enforced at registry load time).
- `TransferLevel` is computed per `ApplicabilityAssessment`, comparing one
  manifest/trace against one evidence record's envelope.

## Consequences

- A mechanism can be `manifest_conditioned_transfer` (epistemic status) backed by an
  `A1_direct_causal_peer_reviewed` (evidence grade) study that nonetheless yields
  `partially_matched` (transfer level) for a specific deployment whose manifest
  doesn't match the study's envelope. All three facts are separately visible; none is
  inferred from another.
- Product-facing wording (`matching/explanation.py`) has to read all three, not just
  one, before deciding what language is allowed — more code than a single confidence
  field would need, but each piece is independently auditable.
- Tests can target each layer independently (`test_registry_validation.py` for
  epistemic status rules, `test_transferability.py` for transfer level, no dedicated
  evidence-grade test file since grade rules are simple field-level Pydantic
  constraints already covered inline).
