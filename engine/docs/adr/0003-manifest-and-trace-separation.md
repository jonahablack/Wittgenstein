# ADR 0003: Separate manifest gates from trace observables

## Status

Accepted.

## Context

A RAG failure mechanism's eligibility depends on two genuinely different kinds of
fact: what a *system is configured to do in general* (can it ever pack more than one
item? is reranking enabled?) and what *actually happened on one query* (was a
distractor actually packed this time? was a required support item actually missing?).
A single flat predicate list over "everything we might know" would blur system-level
capability questions with query-level occurrence questions, making it easy to
misreport "this system's manifest allows distractors" as "this specific answer was
affected by one."

## Decision

Two separate schema/record types — `ManifestGate` (evaluated against `PipelineManifest`
only) and `TraceTrigger` (evaluated against `QueryTrace`, requires a trace to be
supplied at all) — and two separate phases in `matching/eligibility.py`: manifest
predicates are checked first and can definitively disqualify a mechanism with no trace
needed at all (e.g. `CTX_POSITION_SENSITIVE_USE` is disqualified for any manifest
capped at one packed item, regardless of what any trace shows); trace observables are
only checked when a trace is supplied, and their absence yields
`insufficient_manifest_information`, not a default assumption either way.

## Consequences

- `wittgenstein applicability assess --manifest <file>` (no `--trace`) can still
  produce a meaningful, partially-informative eligibility result (manifest-level
  disqualification is real and useful on its own) — the tests exercise this directly
  (`TestUnknownManifestFieldsYieldInsufficientInformation`).
- Query-level mechanisms (`RET_HARD_DISTRACTOR`, `GEN_UNSUPPORTED_DESPITE_CONTEXT`,
  etc.) always need a trace to move past "eligible in principle" — a manifest alone
  can never make them concretely applicable, only rule them out or leave them
  undetermined.
- The registry seed data mirrors this split: `manifest_gates.seed.yaml` and
  `trace_triggers.seed.yaml` are separate files, and several mechanisms
  (`RET_MULTIHOP_SUPPORT_INCOMPLETE`, `PACK_OMISSION_OR_TRUNCATION`,
  `GEN_UNSUPPORTED_DESPITE_CONTEXT`) have an essentially empty `ManifestGate` because
  their entire precondition is trace-level — that emptiness is itself documented
  (`unknown_manifest_behavior` notes it's "not applicable at the manifest level"),
  rather than an accidental gap.
