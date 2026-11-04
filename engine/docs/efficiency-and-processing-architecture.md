# Efficiency and processing architecture

Written before any ingestion/retrieval/proposition/LLM-integration code in this
repository — there was none prior to this document (no `docs/vertical-slice-implementation-plan.md`
or LlamaIndex decision document existed; this document is now that decision record).
Governs the vertical slice built on top of the existing registry, matching engine, and
schemas (`docs/architecture.md`), none of which change here.

## Core principle

The system must be lightweight and able to process sizeable text corpora quickly.
Prefer efficient, deterministic, programmatic methods wherever they are adequate. Use
LLMs only for operations that genuinely require semantic interpretation. This is not a
performance nicety — it is a correctness position: a deterministic parser's output is
reproducible and auditable in the way this project's whole epistemic model depends on
(`CLAUDE.md`, "never infer missing values"); an LLM call is neither, so it is reserved
for the minority of operations where no deterministic method is adequate.

Processing hierarchy, cheapest-first, escalate only when a lower tier is inadequate:

1. Existing document structure and deterministic parsing.
2. Lightweight NLP and rule-based annotation.
3. Lexical retrieval and metadata filtering.
4. Batched embeddings and vector retrieval.
5. Small targeted model calls.
6. Large LLM calls only as optional fallback.

## 1. Programmatic versus LLM responsibilities

**Always programmatic, no LLM involved, required for the MVP:**

- Ingestion (file reading, format detection).
- Structure extraction (headings/sections/paragraphs/lists/tables/captions/footnotes)
  from existing document structure.
- Source segmentation (Tier 0) and candidate-proposition splitting (Tier 1) — sentence/
  clause boundaries, semicolons, conjunctions, list structure, relative clauses,
  condition/attribution markers, discourse connectives — all rule-based.
- Lightweight annotation (Tier 2) — negation, modality/hedges, condition markers,
  exceptions, temporal expressions, numbers/units, cross-reference patterns — regex/
  word-list based, never a neural model.
- Provenance and offset tracking.
- Lexical retrieval (BM25-equivalent) and metadata filtering.
- Context packing (token-budget enforcement, selected/omitted bookkeeping; an item is
  always packed whole or omitted whole -- deliberately never truncated mid-span to fit
  a budget, since cutting an evidence excerpt at an arbitrary token boundary risks
  silently corrupting what a reviewer sees; `compressed_context_items` exists on
  `QueryTrace` for a future extractive-compression stage but is not populated by this
  MVP's packer, see §8).
- Basic risk cues from Tier 2 annotations, surfaced only as `research_hypothesis` /
  `experimental_review_cue` — never as established findings (`RISK ANALYSIS` below).
- Registry matching (`matching/eligibility.py` et al.) — already deterministic, unchanged
  by this document.

**LLM-eligible, optional, selective (Tier 3), never required for the MVP:**

- Difficult proposition decomposition (a Tier 1 fragment stays ambiguous after
  rule-based splitting).
- Predicate normalization (mapping a candidate predicate to canonical form).
- Answer claim decomposition (splitting a generated/imported answer into checkable
  claims), when rule-based sentence splitting is inadequate.
- Uncertain support linking (deciding whether a packed item supports an answer claim,
  when lexical overlap does not resolve it).
- Optional high-quality semantic review, on reviewer request.

**Never LLM, even optionally:** deciding what fits in the context window (packing is
always a deterministic budget algorithm — "CONTEXT PACKING" below); computing
`EligibilityGateResult`s or `TransferLevel` (unchanged, `docs/architecture.md`);
asserting that a programmatic risk cue is a confirmed error (`RISK ANALYSIS` below).

## 2. Corpus-time versus query-time processing

Two-phase architecture, `docs/architecture.md`'s pipeline lineage restated at
implementation granularity:

**Phase A — corpus-time indexing** (`ingestion/`): runs once per corpus version, over
the whole corpus, using only Tier 0/1/2 programmatic methods plus batched embeddings if
enabled. Produces a persistent index: `SourceDocument` + `SourceSegment` records (with
full offsets/provenance), a lexical index, an optional embedding index, and a
`CorpusProfile`. **Does not propositionize the whole corpus** and does not call an LLM
by default.

```
source files -> parser -> normalized source representation
  -> pages/sections/headings/paragraphs/lists/tables -> source segments
  -> offsets and provenance -> lexical metadata -> [batched embeddings]
  -> indexes -> CorpusProfile
```

**Phase B — query-time audit** (`retrieval/`, `proposition/`, `packing`): runs per
query. Retrieves candidates from the Phase A index, selects relevant segments,
propositionizes *only the selected (or near-selected, for context) segments* — never
the whole corpus — adds Tier 2 annotations to those segments, derives registry-
conditioned risks, packs context under a token budget, and (optionally) decomposes the
answer into claims and links them to evidence.

```
query -> retrieve candidates -> select relevant source segments
  -> propositionize selected/near-selected segments -> predicate/dependency annotations
  -> derive registry-conditioned risks -> pack context -> generate/import answer
  -> decompose answer claims -> link claims to evidence -> reviewer view
```

The default query-time path minimizes LLM calls: Tiers 0–2 and lexical retrieval run
unconditionally; Tier 3 (LLM) runs only per the triggers in "TIER 3" below, and its
absence degrades gracefully (§7).

## 3. Caching and content-hash behavior

One generic hashing primitive (`ingestion/content_hash.py`: `content_hash` for a single
text's sha256, `cache_key` for a length-prefixed composite of several parts) and one
generic `KVCache` protocol (`ingestion/kv_cache.py`, with `MemoryKVCache` and
`FileKVCache` implementations), shared by both corpus-time caching and the Tier-3 LLM
cache — a single hashing scheme and a single cache abstraction, not two of each that
could drift (`CLAUDE.md`, "avoid two lists/tables describing the same category").

- **Corpus-time**: a document's cache key is `cache_key(source_document_id,
  content_hash(text), parser_version, "deterministic")` (`ingestion/corpus_index.py`).
  If a document with a matching key was already parsed/segmented, its cached segments
  are reused as-is — not reparsed. Changing the content or `parser_version` invalidates
  only that document, never the whole corpus. (Embedding-stage caching is not part of
  this pass — no embedding stage is implemented, §8.)
- **Tier-3 LLM cache**: cache key is `cache_key(source_text, extractor_version,
  model_id, prompt_version, schema_version)` (`proposition/llm_extraction.py`, using
  the same `ingestion/content_hash.py::cache_key`). An unchanged key never repeats the
  call. The cache stores the raw response, parsed response, validation status/errors,
  timestamp, model/version identifiers, and token counts —
  `schemas/proposition.py::LLMExtractionResult` is exactly this record, and is also the
  cache *value* type, not a separate shape. Every non-cache-hit outcome is written to
  the cache, including fallbacks, so an unavailable LLM is not retried on every lookup
  within the same cache scope.
- Cache storage in this MVP is `MemoryKVCache` (in-process, used by tests and the demo)
  or `FileKVCache` (one JSON file per key, for a persistent single-machine deployment) —
  both implement the same two-method `get`/`put` interface, so a different backend
  (e.g. a shared database) can be swapped in later without changing any caller.

## 4. Batch and asynchronous processing

- **Batching**: Tier-3 LLM calls accept a list of items via
  `proposition/llm_extraction.py::extract_tier3_batch`, the interface callers should
  use even though this pass simply calls `extract_tier3` once per item — a single-item
  call is a batch of one, not the other way around, so a future batched-provider client
  (one HTTP call for many items) can be substituted behind this same function without
  changing call sites. No embedding stage exists in this pass to batch (§8).
- **Resumability**: corpus-time processing is idempotent per document (content-hash
  skip, above), so a partial run can simply be re-run — no separate checkpoint format
  is needed for the MVP.
- **Rate-limit awareness**: not implemented in this pass. The `LLMClient` protocol
  (`proposition/llm_client.py`) is intentionally minimal (`is_available`/`extract`/
  `extract_batch`); a real provider-backed client, out of scope here (§8), is where
  throttling would be added, and could do so without changing the protocol.
- **Async**: out of scope for the MVP. All interfaces here are synchronous. They are
  written batch-first specifically so a later async/concurrent implementation can be
  swapped in behind the same function signatures without changing callers — this is a
  documented future optimization (§8), not implemented now, to keep this pass reviewable
  and avoid concurrency bugs in a first cut.

## 5. Provenance and offset preservation

Every `SourceSegment` (`schemas/proposition.py`) carries: `source_document_id`,
`source_version` (content hash), `location` (page/section/table/list path, human-
readable), `char_start`/`char_end` (always present — character offsets are always
computable from raw text), `token_start`/`token_end` (present only when a tokenizer
was actually run; `None` otherwise, never inferred — same `None`-means-unknown
discipline as `PipelineManifest`), `parent_segment_id` (parent/child relationship),
`cross_reference_targets` (raw pattern matches, Tier 2, not resolved), `parser_version`,
and `corpus_id`/`corpus_version`. A `PropositionCandidate` (Tier 1) always retains both
`source_segment_id` (pointer to the untouched original) and its own `char_start`/
`char_end` within that segment — Tier 1 never rewrites source text, only marks spans.

## 6. Performance instrumentation

`metrics/processing_metrics.py::ProcessingMetrics` — a companion object to a run, not a
field folded into `QueryTrace` or `PipelineManifest` (same reasoning as
`LocalValidationRecord`: a different kind of fact, kept on its own object rather than
overloading an existing schema). Fields: ingestion/parsing/indexing/embedding/
retrieval/proposition-extraction/answer-generation latency (seconds), LLM call count,
input/output token counts, cache hit/miss counts, memory usage (best-effort, `None` if
unavailable — `resource.getrusage` on POSIX, `None` on platforms without it, never a
fabricated number), corpus size (document/segment counts), candidate count, packed
token count. No arbitrary throughput claim is made anywhere in code or docs; §8 and the
final report state what was actually measured, on what hardware, on what corpus size,
and nothing beyond that. `demo/widget_corpus.py` (a small, fictional, in-code corpus —
not a data-directory fixture, since it needs no external file parsing) plus
`tests/unit/test_processing_metrics_benchmark.py` are the benchmark fixture — see that
test for how to measure a larger corpus (it builds a larger synthetic corpus
programmatically and reads the resulting `ProcessingMetrics`; pointing the same
`ingestion.corpus_index.index_corpus` function at a real, larger `sources` dict works
identically).

## 7. Fallback behavior when an LLM is unavailable

Tier 3 is optional everywhere it is used. If the configured `LLMClient` is unavailable
(no client configured, a network/auth error, or a timeout) or returns output that fails
schema validation, the caller receives the Tier 0–2 programmatic result unchanged, with
`LLMExtractionResult.validation_status="llm_unavailable"` (or `"validation_failed"` for
a call that returned but didn't parse) and every LLM-only field (parsed semantic
decomposition, normalized predicate, etc.) left `None` — never a guess presented as if
it were the LLM's output, and never an exception that aborts the rest of the pipeline.
`NullLLMClient` (always reports unavailable) is the default client in this MVP, which is
exactly how the no-LLM demo mode (`demo/pipeline.py::run_no_llm_baseline_demo`) is
implemented — not a separate code path, the same code path with no client configured.

## 8. Required for the MVP vs. optional

| Capability | MVP (this pass) | Optional / future |
|---|---|---|
| Deterministic parsing, Tier 0/1/2 | **Required, implemented** | — |
| Content-hash corpus-time cache | **Required, implemented** | Distributed cache backend |
| Provenance/offsets | **Required, implemented** | Token offsets for formats without a tokenizer configured (stay `None`) |
| Lexical (BM25-equivalent) retrieval | **Required, implemented** | — |
| LlamaIndex `Document`/`TextNode` ingestion adapter, converted immediately to Wittgenstein schemas | **Required, implemented** | LlamaIndex-native retrievers/vector stores wired in as an alternative retrieval backend behind the same adapter boundary |
| Context packing (budget, selected/omitted bookkeeping) | **Required, implemented** | Truncation/compression of an individual item (deliberately not done — see §1) |
| Performance instrumentation | **Required, implemented** | Wall-clock benchmarking across real large corpora (a ~1,000-paragraph synthetic benchmark is included, `tests/unit/test_processing_metrics_benchmark.py`; a real production-scale corpus is not shipped here) |
| Tier 3 LLM interface + content-addressed cache + fallback | **Required, implemented (`LLMClient` protocol + `NullLLMClient` + `DemoLLMClient` + tests)** | A real provider-backed `LLMClient` (needs API credentials — not configured in this pass) |
| Batched dense embeddings / vector retrieval | Not implemented | No embedding dependency added in this pass; `RepresentationManifest.embedding_family` exists on the manifest schema for declaring one later |
| Hybrid retrieval (lexical + dense) | Not implemented | Depends on dense retrieval above |
| Async/concurrent execution | Documented (§4) | Not implemented |
| Answer generation / answer-claim decomposition against a real generator | Interface only (`schemas/proposition.py`) | No generator is wired up in this pass — the demo imports a fixed answer string, consistent with "generate or import answer" in the query-time path |
| Rate-limit-aware real LLM client | Interface only | Real client implementation |

Nothing in the "optional / future" column is asserted as working in this pass's report.

## 9. Real-corpus evidence-set diagnostics (measurement, not a new processing tier)

`evidence_set_diagnostics/` (`docs/evidence-set-real-corpus-diagnostics-plan.md`) adds
no new processing tier and no LLM call -- it is a read-only diagnostic pass built
entirely from Tier 0-2 primitives already covered above: a second, cached
`ingestion.corpus_index.index_corpus` call (idempotent per §3, since the corpus text
and `parser_version` are unchanged) supplies segment locations for cross-reference
target-state matching, and `review/field_extraction.py::extract_fields`/
`review/field_comparison.py::compare_field` (already covered under "Programmatic
versus LLM responsibilities" above) are re-invoked read-only to recover per-conflict
field spans/confidence for a diagnostic report. The one deliberately bounded exception
is the opt-in `--diagnostic-max-set-size 3` evidence-set search
(`evidence_set_diagnostics/runner.py::MAX_DIAGNOSTIC_SIZE3_COMBINATIONS = 500`): never
run by default, capped combinatorially, and its own report always states the
closed-form `C(pool_size, 3)` combination count and an extrapolated latency estimate
rather than letting a large pool silently run an expensive search.
