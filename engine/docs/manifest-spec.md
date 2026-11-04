# Manifest spec

A `PipelineManifest` (`schemas/manifest.py`) describes a RAG system's *configuration*
— what it is built to do, independent of any single query. It has nine sections, each
mirroring one pipeline stage, plus an explicit `missing_information` list.

## The unknown-field contract

Every field on every section is `X | None`, defaulting to `None`. **`None` means
"unknown," and every consumer of a manifest — every manifest gate in
`matching/eligibility.py` — must treat it that way.** Concretely:

- A required predicate whose field is `None` evaluates to
  `GateResultStatus.UNKNOWN_INSUFFICIENT_DATA`, never `SATISFIED` or `VIOLATED`.
- A disqualifying predicate whose field is `None` also evaluates to
  `UNKNOWN_INSUFFICIENT_DATA` — an unknown disqualifier is never assumed to *not*
  apply, because that would be exactly the kind of silent optimistic default this
  project forbids.
- There is no mechanism anywhere in this codebase that infers a manifest field from
  another field, a corpus profile, or a "typical" default. If you cannot answer a
  question from the manifest as given, the answer is
  `insufficient_manifest_information`.

`missing_information: list[str]` is a separate, explicit channel: a manifest author
can name dotted paths they know are unknown (e.g. because their instrumentation
doesn't capture that field yet), which is useful for audit trails even though `None`
already carries the same semantic meaning to the matching engine.

## `corpus_manifest` vs. `CorpusProfile`

`corpus_manifest` (below) is the system's *declared configuration* — what a manifest
author asserts about the corpus, same as any other manifest section, subject to the
same unknown-field contract. It is a different schema from `CorpusProfile`
(`schemas/corpus_profile.py`), which holds *observed structural statistics*
(heterogeneity, redundancy, table density, evidence dispersion, etc. — see
`docs/registry-governance.md`, "Corpus properties") computed by a separate profiling
pass, not declared by hand. Do not conflate the two: a manifest can correctly declare
`corpus_manifest.domain="legal"` with no `CorpusProfile` ever having been computed for
it at all.

## Sections

| Section | Key fields |
|---|---|
| `corpus_manifest` | `domain`, `document_count`, `corpus_versioning` |
| `ingestion_manifest` | `parser`, `ocr_used`, `structure_extraction_method` |
| `representation_manifest` | `index_unit`, `embedding_family` |
| `retrieval_manifest` | `retriever_family`, `retrieval_unit`, `chunking_method`, `candidate_depth`, `query_transformation_enabled`, `parent_child_expansion`, `graph_retrieval` |
| `reranking_manifest` | `reranking_enabled`, `reranker_family`, `rerank_depth` |
| `selection_manifest` | `selection_policy`, `max_selected_items` |
| `packing_manifest` | `packing_method`, `compression_enabled`, `compression_type`, `context_window_tokens`, `evidence_budget_tokens` |
| `generation_manifest` | `generator_family`, `model_identifier`, `prompting_policy`, `citation_policy`, `abstention_policy` |
| `evaluation_manifest` | `evaluation_metrics`, `human_review_enabled` |

## From manifest to comparable envelope

`profiling/manifest_profile.py::build_envelope` projects a `PipelineManifest` (plus an
optional `QueryTrace` and `CorpusProfile`) into an `ExperimentalEnvelope` — the same
schema an `EvidenceRecord` uses to describe its study's setting. This lets
`matching/transferability.py` do a plain field-by-field comparison instead of
maintaining two parallel vocabularies. Some envelope fields are read straight from the
manifest (`retriever_family`, `chunking_method`); a few (`packed_item_count`) are only
knowable once a trace is supplied, since "how many items were actually packed" is a
per-query fact, not a system-configuration fact — if no trace is given, that field
stays `None`.

## Position-risk threshold

`matching/eligibility.py::POSITION_RISK_TOKEN_THRESHOLD` (4000 tokens) is the
documented cutoff `CTX_POSITION_SENSITIVE_USE` uses to decide whether packed context
is "long enough" to be at risk of position sensitivity. It is a named module constant,
not a magic number buried in a conditional, specifically so it can be audited and
revised as evidence accumulates on where the real risk threshold lies.

## Manifest gates as activation preconditions: `REP_SEGMENTATION_GRANULARITY_MISMATCH`

A `ManifestGate` decides whether a mechanism *could* apply at all; it says nothing
about whether the mechanism should be shown to a reviewer with any particular priority
(that is `ActivationPolicy`'s job — `docs/registry-governance.md`). For
`REP_SEGMENTATION_GRANULARITY_MISMATCH` (`manifest_conditioned` as of 2026-09-09), two
of its five activation conditions are manifest-level and read directly from
`retrieval_manifest`: `chunking_method` and `retrieval_unit` must both be known
(required predicates — unknown yields `unknown_insufficient_data`, never an assumed
pass), and `retrieval_unit == "whole_document"` is disqualifying (no sub-document
segmentation exists to mismatch). Neither corpus size nor which specific chunker family
is configured (fixed-size, semantic, propositional, …) appears anywhere in this gate —
chunking merely existing is not a trigger.

## Example manifests

Five worked examples live in `data/examples/manifests/`, generated by
`scripts/generate_example_data.py`: a single-passage system, a multi-passage
dense-retrieval-plus-reranking system with a finite token budget, a parent-child
proposition-retrieval system with an omitted cross-reference, a compression-enabled
system, and a query-rewriting multi-hop system. Each has a matching trace in
`data/examples/traces/`.
