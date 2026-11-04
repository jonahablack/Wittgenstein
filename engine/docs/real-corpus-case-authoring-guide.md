# Real-corpus case-authoring guide

How to turn one selected document/section (`docs/real-corpus-diagnostic-runbook.md`
step 1-2) into a diagnostic case. Start from
`data/examples/evidence_set_diagnostics/case-template.json`.

## Template fields and where they end up

`case-template.json` is a plain authoring worksheet -- it does not itself validate as
a `schemas/smoke_test.py::SmokeTestCase` (that schema is `extra="forbid"`, so it
never gains new top-level fields; this guide's job is to show you how the worksheet's
fields map onto the actual case object without changing that schema). Fill in the
worksheet, then write the corresponding `SmokeTestCase` entry in your `cases.json`
using this mapping:

| Worksheet field | Goes into (`SmokeTestCase` unless noted) |
|---|---|
| `case_id` | `case_id` |
| `corpus_id` | `corpus.corpus_id` (`CorpusReference`) |
| `document_id` | a key in `corpus.document_hashes`, and the filename stem if you used the one-file-per-document local corpus layout |
| `document_version` | `document_version` |
| `source_title` | `corpus.source_metadata["source_title"]` |
| `source_url` | `corpus.source_metadata["source_url"]` (or omit the key if `null`) |
| `license_or_public_access_basis` | `corpus.source_metadata["license_or_public_access_basis"]` |
| `source_access_date` | `corpus.source_metadata["source_access_date"]` |
| `source_hash` | `corpus.document_hashes[document_id]` |
| `local_source_path` | `corpus.local_path` |
| `query` | `query` |
| `user_stated_constraints` | `query_constraints` (already a `dict[str, str]` -- exact fit) |
| `unresolved_intent_fields` | appended into `user_intent_notes` as free text (e.g. `"Unresolved intent fields: jurisdiction, effective date."`) |
| `answer` | `answer` |
| `answer_origin` | `answer_source_method` |
| `manifest_id` | `pipeline_manifest_id` |
| `expected_evidence_locations` | `expected_evidence_locations` |
| `expected_structure_tags` | `pilot_coverage_labels` (`core/enums.py::PilotCoverageLabel` -- use only its existing values) |
| `known_limitations` | prefixed into `reviewer_notes`, e.g. `"Known limitations: ..."` |
| `annotation_status` | tracked in your own per-case row of the results doc's "Per-case summary" table (`docs/evidence-set-real-corpus-diagnostics-results.md`) -- `SmokeTestCase` has no workflow-status field, and this pass does not add one |

`provenance_status` (a required `SmokeTestCase` field, not on the worksheet since it
follows directly from `license_or_public_access_basis`) -- set it from
`core/enums.py::ProvenanceStatus` (e.g. `user_provided_license_confirmed`,
`public_domain_or_open_license`); never `pending_provenance_review` for a case you
intend to actually run.

`expected_evidence_locations` are **researcher navigation aids for this diagnostic
pass, not universal factual-truth labels** -- exactly the same status they already
have in `docs/real-trace-smoke-test-plan.md`.

## Rules

- **Do not write a fabricated answer as if it were source-derived.** If an answer is
  not something the document actually supports, that must be explicit in
  `answer_origin` -- never leave it looking like `document_verbatim` or
  `manual_transcription_from_document`.
- **If you seed a deliberately unsupported or contradicted answer, label it as a
  controlled perturbation.** Use `answer_origin: "controlled_perturbation_unsupported"`
  or `"controlled_perturbation_contradicted"` (extending the existing free-text
  `answer_source_method` convention already documented on `SmokeTestCase` -- these are
  not enum-constrained, so name the perturbation explicitly rather than inventing an
  ambiguous label) and say exactly what was changed and why in `known_limitations` /
  `reviewer_notes`. A perturbation case is valuable (it's how `smoke-003` and
  `smoke-004` work in the existing bundled fixtures) -- an *unlabeled* one is a
  fabricated case masquerading as a real one.
- **Preserve source wording and offsets.** Do not paraphrase the document when
  constructing `expected_evidence_locations` or when transcribing text into a local
  corpus file -- copy verbatim. If your local corpus text is a re-typed excerpt rather
  than the original file, say so in `known_limitations`.
- **Identify version and effective-date dependencies explicitly.** If the document has
  multiple revisions, or the answer's correctness depends on which revision or
  effective date applies, record that in `document_version` and flag it under
  `expected_structure_tags` (`temporal_or_version_information`).
- **Do not claim a legal or clinical conclusion.** Even for slice-B (policy/
  regulatory-like) documents, this case is testing whether the pipeline links evidence
  correctly -- not whether the underlying rule is correctly stated, current, or
  applicable to any real situation. Keep `answer`/`query` framed as "what does this
  document say," never "what should someone do."
- **Keep answer provenance explicit.** `answer_origin` must always be filled in with
  one of: `human_authored_for_pilot`, `document_verbatim`,
  `manual_transcription_from_document`, `controlled_perturbation_unsupported`,
  `controlled_perturbation_contradicted`, or (only if you have independently verified
  it) `llm_generated_unverified`-with-verification-noted-in `known_limitations`. Never
  leave it blank or use a value that overstates how the answer was produced.
- **Use `unresolved` where interpretation cannot be responsibly pre-decided.** If you
  are not sure whether a document genuinely supports a candidate answer, don't force
  `expected_evidence_locations` to a guess -- leave it sparse and note the uncertainty
  in `unresolved_intent_fields`/`known_limitations`. The diagnostic and annotation
  labels both have an explicit `unresolved` value for exactly this reason.

## Corpus slices and case sampling

See `docs/real-corpus-diagnostic-runbook.md`'s "Corpus guidance" and "Case sampling"
sections -- this guide covers *how to write one case*; that document covers *how many
and what mix*.

Three concrete corpora are catalogued for the first pass
(`data/examples/evidence_set_diagnostics/corpus-catalog.yaml`,
`docs/corpus-selection-rationale.md`): `eu-ai-act-2024`, `hipaa-privacy-rule`, and
`ada-standards-2026`. Each has its own README under
`data/examples/evidence_set_diagnostics/<corpus_id>/` with its official source
URL(s), initial slice, and required local metadata, and
`data/examples/evidence_set_diagnostics/case-sets/README.md` gives the recommended
case shapes per corpus. Whichever corpus you're writing a case for, the mapping table
and rules above still apply unchanged -- `corpus_id`/`document_id` in the worksheet
should just match the corpus you picked.

Regardless of corpus, never let a case's `answer` assert what the source document
*should* mean or require -- only what it *states*, verbatim or clearly paraphrased
with the paraphrase noted. This matters most for `eu-ai-act-2024` and
`hipaa-privacy-rule` (do not phrase a case as legal advice) and especially for
`ada-standards-2026` (do not phrase a case as a clinical recommendation) -- see each
corpus's README §10 warning.
