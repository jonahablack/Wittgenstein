# ADR 0001: Registry-first architecture

## Status

Accepted.

## Context

The task this project starts from could have been built as a chat-with-documents
product with an ad hoc "hallucination warning" bolted on, driven by whatever
heuristics seemed plausible at implementation time. That is exactly the failure mode
this project exists to avoid: plausible-sounding linguistic heuristics presented with
the same confidence as peer-reviewed findings.

## Decision

Build the registry — the typed, evidence-graded catalog of failure mechanisms — as
the first-class artifact, before any product UI. Schemas, seed data, deterministic
matching, and a CLI/API to query them are milestone one. A frontend is a documented
stub only.

## Consequences

- Every other component (matching engine, API, CLI) is a *consumer* of the registry,
  never a place that invents its own parallel notion of "this looks like a failure."
- The bar for adding a mechanism is a registry-governance decision
  (`docs/registry-governance.md`), not a code-review nod on a PR that happens to add a
  regex.
- Early milestones look "product-thin" (no polished UI, few default-enabled
  mechanisms) because the registry's own integrity rules currently block most
  mechanisms from default activation pending evidence verification. This is treated as
  correct, not as a gap to paper over — see `data/registry/README.md`.
