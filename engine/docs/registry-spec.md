# Registry spec

## Entities

Full field lists live in the Pydantic schemas (`src/wittgenstein/schemas/`), which are
the source of truth; this is a summary of what each entity is and its lifecycle:

| Entity | Schema module | What it is | Lifecycle / status rules |
|---|---|---|---|
| `FailureMechanism` | `schemas/failure_mode.py` | A stable, mechanism-level causal claim, keyed by `id`. Carries `epistemic_status`, `default_evidence_grade`, `default_activation_policy`, `evidence_synthesis`. | New mechanisms start `research_hypothesis`/`E_hypothesis`/`disabled_by_default_or_research_mode`/`evidence_synthesis=unresolved`. Status changes follow `docs/registry-governance.md`. `unsupported_or_retired` is never deleted. |
| `EvidenceRecord` | `schemas/evidence.py` | One paper/study's support (or non-support) for exactly one mechanism, with `exact_quote`, `evidence_grade`, `direction`, `verification_status`. | `exact_quote` verbatim or `TODO` + `verification_status=unverified`. `verified` records cannot contain a `TODO`. A1/A2 grades require `peer_review_status=peer_reviewed`. |
| `ExperimentalEnvelope` | `schemas/evidence.py` | The experimental preconditions a study tested (or a manifest/trace-derived equivalent) — task, retrieval config, generator, `rag_presence`, etc. Every field optional; `None` means unknown, never inferred. | Embedded in `EvidenceRecord`; also produced by `profiling/manifest_profile.py`. |
| `ManifestGate` | `schemas/failure_mode.py` | The declarative, documented form of a mechanism's manifest-level predicates (required/disqualifying/strengthening). | One per query-independent precondition set; executable form lives in `matching/eligibility.py`, linked by `gate_id`. |
| `TraceTrigger` | `schemas/failure_mode.py` | The declarative form of a mechanism's required trace-level observables, plus `causal_claim_permitted`. | Same code/registry linkage discipline as `ManifestGate`. |
| `ReviewAction` | `schemas/review.py` | A bounded, human-checkable question. `instructs_acceptance` is structurally forced `False`. | Never mutates evidence directly; a human acts on its answer. |
| `LocalValidationRecord` | `schemas/review.py` | A result from this project's own controlled testing, scoped to `deployment_scope`. Carries `external_evidence_status`, `local_validation_status`, and `deployment_priority` as three separate fields (never merged). | `meets_promotion_bar()` gates promotion to `locally_validated`; promotion is always a deliberate, separate edit — never automatic. See `docs/registry-governance.md`. |

Required provenance on every evidence-bearing record: `extraction_reviewer`,
`extraction_date`, and (once verified) a second reviewer's confirmation noted outside
the record itself (`docs/literature-review-protocol.md`, "Single vs. dual reviewer
procedure") — the schema tracks who extracted it and when, not who verified it, so a
verification pass is always independently auditable against the extraction.

## Files

```
data/registry/
  failure_modes.seed.yaml      # FailureMechanism records
  evidence_records.seed.yaml   # EvidenceRecord records
  manifest_gates.seed.yaml     # ManifestGate records
  trace_triggers.seed.yaml     # TraceTrigger records
  review_actions.seed.yaml     # ReviewAction records
  README.md                    # bootstrap-scope disclaimer
```

`registry/loader.py::load_registry(seed_dir)` reads all five files, validates each
record against its Pydantic schema, then runs `registry/validator.py::validate_registry`
for cross-record integrity. Both stages fail loudly (raise, with every problem
collected, not just the first) — there is no partial-load mode.

## Declarative rules vs. the executable engine

`ManifestGate` and `TraceTrigger` records are the *documented* form of a mechanism's
predicates: human-readable descriptions plus a `field_path`/`operator`/`expected_value`
triple per predicate, meant for the dossier and for registry consumers that only need
to read what a mechanism checks. The *executable* form lives in
`matching/eligibility.py` as one plain Python function per mechanism id
(`MECHANISM_EVALUATORS`). Every `EligibilityGateResult` the executable form produces
carries a `gate_id` matching a declarative record's `id`, so the two are always
linkable — but they are not auto-generated from each other. If you change a
mechanism's logic in `eligibility.py`, update the matching seed YAML by hand, and vice
versa; `tests/unit/test_eligibility_gates.py` exercises the executable behavior
directly.

This split — declarative predicate text in the registry, executable logic in Python —
is deliberate: a fully generic predicate-interpreter DSL would make eligibility rules
"data," but at the cost of making every rule's actual behavior one layer harder to
read and test than a plain function. Given the task's requirement that eligibility
decisions be deterministic and auditable by a human reviewer, readable code won out
over a generic interpreter.

## Evidence direction and synthesis fields

Added to encode how conflicting studies are represented without averaging them into a
single confidence number (see `docs/registry-governance.md`, "Conflicting studies"):

- `EvidenceRecord.direction` (`EvidenceDirection`: `supports` | `refutes` | `mixed` |
  `null`) — required on every evidence record, never defaulted. `null` is an explicit
  value (a record that speaks to the mechanism's setting without taking a clear
  position), distinct from omitting the field.
- `FailureMechanism.evidence_synthesis` (`EvidenceSynthesis`: `convergent` | `mixed` |
  `limited` | `unresolved`) — a human-set summary of how the mechanism's *linked*
  evidence records, taken together, agree or disagree. `research_hypothesis` mechanisms
  must be `unresolved` (enforced by `schemas/failure_mode.py`, mirroring the existing
  `evidence_grade=E_hypothesis` constraint). A mechanism whose evidence records disagree
  (e.g. `REP_SEGMENTATION_GRANULARITY_MISMATCH`, seeded with one `supports` and one
  `mixed` record) is `mixed`, not resolved into a single ranking.

A separate contradiction entity is used only when disagreement itself is the object of
study (e.g. a meta-analysis of why studies disagree) — the default representation is
multiple `EvidenceRecord`s under one mechanism, each independently directioned.

## Versioning

`registry_version` (semver, `core/versioning.py`) is carried on every
`FailureMechanism`. Bump discipline:

- **PATCH** — metadata fixes (typo, `TODO` → verified quote) that don't change any
  mechanism's `epistemic_status` or `default_activation_policy`.
- **MINOR** — a new mechanism or evidence record is added; no existing mechanism's
  status is loosened.
- **MAJOR** — an existing mechanism's `epistemic_status` changes (either direction),
  or a mechanism is retired/merged.

See `docs/registry-governance.md` for the review process behind each kind of change.

## Adding a mechanism or evidence record

Prefer `wittgenstein registry add-mechanism` / `add-evidence` (interactive, appends to
the seed YAML) over hand-editing for the field-completeness prompts, though either
works — both routes must pass `wittgenstein registry validate` afterward. See
`CONTRIBUTING.md` for the review bar.

## Exporting

`wittgenstein registry export --format json|csv|yaml` dumps every `FailureMechanism`.
`wittgenstein registry dossier <id>` renders the full Markdown dossier
(`registry/dossier.py`) for one mechanism — canonical claim, evidence with quotes and
locations, manifest gates, trace triggers, allowed/prohibited language, reviewer
actions, and an explicit open-evidence-gaps section.

## Public interchange schemas

`scripts/export_json_schemas.py` (`make schemas`) dumps JSON Schema for every schema
in `exports/json_schema.py::EXPORTED_MODELS` to `schemas/generated/` — the format
external tools should validate against, kept independent of internal Pydantic
refactors.
