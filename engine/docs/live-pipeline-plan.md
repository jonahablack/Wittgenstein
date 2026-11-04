# Phase 1: the self-aware live pipeline (plan)

Written 2026-11-04, before any Phase 1 code. Branch `Cosmos` of `jonah410/Wittgenstein`.
Phase 2 (adaptation to corpus type and to the user) is out of scope here except where a
Phase 1 decision must leave room for it (§11).

## 1. The problem, stated precisely

People re-check LLM answers by hand because a RAG answer arrives with no account of
*how* it was produced: what was searched, what was found, what was dropped, and where
the process is known to be weak. Most of the time the answer is fine; occasionally it
silently misses something, and the user cannot tell which case they are in. So they
verify every time.

The goal is to make that manual step unnecessary in the common case and cheap in the
remaining case -- not by asking for trust, but by *demonstrating awareness of the
process*: the pipeline reports what it did, what it measured about its own behavior on
this query, what it noticed might be missing, what it already did about it, and what
remains for a human to check -- each claim tied to a concrete span of source text.

Two constraints pull against each other and both are binding:

1. **Transparency must be real.** Every statement the system makes about itself is a
   measured fact of this run (a score, a rank, a token count, a matched phrase), never a
   guess presented as a finding. The engine's existing rules apply unchanged
   (`CLAUDE.md`): no causal claim from a trace fact alone, unknown is never inferred,
   one canonical enum per axis, research hypotheses are labeled as such.
2. **The tool must stay fast and pleasant to use.** The default experience is an
   answer, not a dashboard. Process detail is one click away, never in the way.

## 2. What already exists and is reused

| Need | Existing piece (engine) | Use in Phase 1 |
|---|---|---|
| Parsing with offsets/provenance | `ingestion/parser.py`, `corpus_index.py` | Segment documents; every flag points at char offsets |
| Lexical retrieval | `retrieval/lexical.py` (BM25) | Lexical retriever |
| Budgeted packing | `trace/packer.py` | Final packing step after selection |
| Trace + manifest schemas | `schemas/trace.py`, `schemas/manifest.py` | Every live run emits a valid `QueryTrace` + `PipelineManifest` |
| Cross-reference detection/resolution | `review/cross_reference_diagnostics.py` | Gap signal: referenced target not in context |
| Answer-to-evidence linking | `review/claim_linking.py` | Post-answer support check per sentence |
| Failure-mechanism registry | `data/registry/*.seed.yaml` | Flags link to mechanism ids and inherit epistemic status |

Ported from the original app (`server/components/risk_triage.py`): the word-boundary-safe
phrase matcher and the segment-level detectors (condition and concession satellites
with the spaCy well-formedness gate, negation scope, explicit backward references,
unresolved definite references, modal strength). Their documented edge cases
(`RISK_TRIAGE_EDGE_CASES.txt`) come with them as regression tests, including the
"no bare substring check" self-test. Citations in their docstrings are carried over
verbatim and marked as carried, not re-verified here.

## 3. Architecture

```
engine/src/wittgenstein/live/
  embedding/      Embedder protocol + backends (model2vec static, fastembed ONNX, hashing-for-tests)
  corpus.py       LiveCorpus: segments + BM25 + per-embedder vector cache + neighbor links + layout
  query.py        Query analysis: facets, hard constraints, question type
  pipelines.py    PipelineSpec (declarative) -> PipelineManifest; presets
  retrieve.py     Lexical, dense, facet sub-queries, reciprocal-rank fusion
  probes.py       Embedding-awareness probes (§4)
  gaps.py         Evidence-gap signals (§5)
  text_artifacts.py  Ported risk_triage detectors, applied to passages and answer sentences
  select.py       Coverage-aware adaptive k (§6)
  generate.py     AnswerProvider protocol: extractive (offline), Claude, OpenAI
  verify.py       Answer sentence -> evidence linking, modal/negation checks
  flags.py        AwarenessFlag model + registry linkage
  events.py       Typed event stream (§7)
  runner.py       Orchestrates one query across one or more pipelines, yields events
engine/src/wittgenstein/api/routes/live.py   Corpus upload, run (SSE), replay, layout
web/              New frontend (§8)
```

The old Flask app (`client/`, `server/`) stays untouched until the new app reaches
feature parity; it is removed in a separate, explicit step.

### 3.1 Embedding backends

Embedding is a first-class, *declared* pipeline stage: every run's manifest names the
embedder, its dimensionality, and its input limit, and the probes in §4 measure that
specific model's behavior on that specific query.

- `model2vec` (`minishlab/potion-*`): static embeddings, sub-millisecond per passage on
  CPU, no input-length truncation. Default for speed. Known property to surface:
  mean pooling dilutes long passages (probe D4).
- `fastembed` (`BAAI/bge-small-en-v1.5`, ONNX): contextual, 512-token input limit.
  Known property to surface: text past the limit is invisible to dense search (probe D3).
- `hashing`: deterministic, non-semantic, test-only, labeled as such in every manifest.

Vectors are cached per (content hash, model id); a corpus is embedded once.

### 3.2 Unknown models and architectures: measure, never assume

The end state runs on top of organizations' existing RAG pipelines, whose embedders,
retrievers, rerankers and chunkers this system has never seen. So no awareness check may
depend on knowing a model in advance. The demo ships with one or two embedders, but they
are treated exactly like a stranger's model:

- **Model characterization (calibration).** The first time a model is attached, a
  battery of behavioral probes measures it and stores an `EmbedderProfile`:
  - *Effective input window.* Embed growing prefixes of a long real passage and find the
    length past which appending text no longer moves the vector. Declared limits are
    recorded separately and never trusted over the measurement.
  - *Constraint sensitivity baselines.* Embed controlled minimal pairs built from the
    corpus's own sentences (negation inserted/removed, a number changed, an identifier
    swapped, a content word dropped) and record the distribution of vector shifts for
    each kind of edit. At query time, a constraint's shift is judged against *this
    model's* baseline, not a universal threshold.
  - *Length dilution curve.* Similarity of a sentence to itself embedded inside growing
    amounts of surrounding corpus text.
  - *Similarity geometry.* Corpus-level similarity distribution (anisotropy), so scores
    are always reported relative to this model on this corpus.
- **Three integration levels**, each with the checks it can honestly support:
  1. *Embedding access* (an `embed(texts)` function): every probe.
  2. *Retriever access only* (`retrieve(query) -> ranked ids [+ scores]`): the probes are
     run as query perturbations observed through ranking changes (e.g. does removing
     "not" change the top results?). Checks that need vectors report `not_applicable`.
  3. *Trace/log import only*: gap signals over the recorded trace (omissions, budget,
     cross-references, severed context); no probes.
  The manifest records which level a run had, and every check states whether it was
  measured, inferred from rankings, or not applicable. That keeps a reduced-access run
  from being shown as fully checked.
- **Unfamiliar architectures** (rerankers, query rewriting, parent-child expansion,
  compression) are handled through the trace's stage lists. The system compares what
  entered and left each stage it can observe, and an uninstrumented stage is reported as
  uninstrumented, never as clean.

## 4. Embedding awareness: where the query vector and the user's intent can diverge

A dense retriever compresses the question into one vector and ranks passages by cosine
similarity. The user's intent is richer than that vector: it has parts, hard constraints,
polarity. Each probe below *measures* one way the two can come apart, on this query, with
this model. None asserts that the answer is wrong.

- **D1. Facet dominance.** The query is split into facets (§4.1). Each facet is also
  embedded and searched alone. If a facet has strong matches of its own but none of them
  appears in the whole-query dense top-k, the single vector leaned toward the other
  facets. *Measured:* per-facet best rank in the whole-query ranking vs. facet-only
  ranking. *Remedy available:* facet sub-queries fused into the candidate pool.
- **D2. Constraint sensitivity (ablation probe).** For each hard constraint in the query
  (negation, number, date, identifier, comparator, quoted phrase), embed the query with
  that constraint removed or flipped and measure the cosine between the two query
  vectors. A value near 1.0 means this model barely registers the constraint, so dense
  ranking is effectively blind to it. *Measured:* cosine(query, ablated query), and
  whether the top-k changes. This is the most direct, honest answer to "does the
  embedding understand what I actually asked?" -- it is an experiment run live, not a
  belief about embeddings in general.
- **D3. Embedder truncation.** A passage longer than the model's *measured* effective
  input window (§3.2) is embedded from its prefix only. If query terms occur only in the
  ignored tail, dense search could not have seen them. *Measured:* passage length against
  the measured window, term positions.
- **D4. Dilution.** For top candidates, compare passage-level similarity to the best
  single-sentence similarity. A large gap means the relevant sentence is buried in a long
  passage and the passage was under-ranked. *Measured:* both similarities.
- **D5. Lexical/semantic disagreement.** Compare the lexical and dense rankings over the
  union of their candidates (rank-biased overlap). Items one retriever ranks highly and
  the other ranks low or misses are listed, with the specific reason when it is
  observable (contains a rare exact query term; contains a sibling value such as
  "Class II" for a "Class III" query, i.e. a *near miss* that similarity cannot separate).
- **D6. Score geometry.** Raw cosine values are compressed and model-specific, so scores
  are reported as z-scores against the corpus's own query-passage similarity distribution.
  Measured: (a) *weak best match*: the best passage is not far above the corpus baseline,
  so the answer may not be in the document; (b) *ambiguous cutoff*: the k-th and (k+1)-th
  scores are within noise, so the cutoff is arbitrary and feeds §6; (c) *flat top*: top
  scores are indistinguishable, so their order carries no information.

### 4.1 Query analysis (deterministic)

Facets: content keyphrases after stopword removal; explicit conjunction/comparison splits
("A and B", "A vs B", "compare"). Hard constraints: negation/exclusion, numbers and units,
dates/years, identifiers ("Article 6(2)", "Class III", "§ 4.2"), comparators ("more than",
"at least"), quoted strings, modality. Question type: factoid, enumeration ("list all",
"every", "how many"), comparison, explanation. All rule-based and inspectable, so a probe
result can always be traced back to the exact query substring it concerns.

## 5. Evidence gaps: what might be left out

Each gap signal names the missing piece concretely and links to it when it exists.

- **G1. Facet uncovered.** A facet has no supporting passage in the packed context
  (lexical or semantic match above threshold).
- **G2. Cross-reference not followed.** A packed passage cites a section/article/annex
  whose target is in the corpus but not in context (existing cross-reference module).
- **G3. Severed context (chunk boundary).** A packed passage opens with an anaphor or
  connective whose antecedent is elsewhere ("However, this does not apply...", "Such
  devices...", "The latter...") or ends by introducing material it does not contain
  ("...the following:"). The neighbor segment is identified; whether it is packed is a
  trace fact. Text artifact (anaphora, concession) + pipeline artifact (chunking).
- **G4. Budget omission.** Relevant candidates omitted only because the token budget ran
  out, especially when they are the sole cover for a facet.
- **G5. Enumeration incompleteness.** For "list all / every / how many" questions, the
  number of candidates matching the enumerated pattern beyond the selected set.
- **G6. Definition not in context.** A packed passage uses a term the corpus defines
  elsewhere ('"X" means', "X is defined as", definitions sections) and the definition is
  not packed.
- **G7. Redundancy.** Packed items that are near-duplicates (cosine above threshold),
  spending budget without adding coverage.

Text artifacts (ported detectors) are attached to the passages they occur in, e.g. a
condition satellite ("unless ...") in an evidence passage, or an answer sentence whose
modal strength is stronger than its cited evidence ("must" vs. "may").

## 6. Adaptive top-k: coverage-aware selection

A fixed k is a guess made before seeing the query. Instead, selection runs a greedy,
deterministic loop over a deep candidate pool (fused lexical + dense + facet
sub-queries; default depth 60):

```
score(c) = relevance_z(c) + λ · new_facet_coverage(c) − μ · redundancy(c, selected)
```

Stop when *all* of: every facet covered (or provably uncoverable from the pool); next
best candidate falls below the relevance elbow (largest gap in the z-sorted pool,
bounded); and k ≥ k_min. Stop unconditionally at the token budget or k_max. Enumeration
questions keep going while candidates still match the enumerated pattern.

After selection, **remediation passes**, each recorded as a decision with its reason:
pull in the neighbor of a severed passage (G3); pull in a cross-reference target (G2);
pull in a definition (G6). Every candidate in the pool ends with exactly one recorded
fate (`selected`, `pulled_in`, `skipped_redundant`, `below_elbow`, `omitted_budget`,
`not_reached`), each with a human-readable reason. That ledger is what the "what was
left out, and why" view renders.

Fixed-k pipelines run through the same code with the adaptive stopping rule disabled,
so all probes and gap signals still run on them and pipelines are directly comparable.

New fates and flag kinds are added to `core/enums.py`, not defined ad hoc.

## 7. Multiple pipelines and the event stream

A `PipelineSpec` declares chunking, retriever(s), embedder, candidate depth, k policy,
expansion, and budget, and compiles to an honest `PipelineManifest` (fields the spec
does not determine stay `None`). Presets: lexical/fixed-k, dense/fixed-k,
hybrid/adaptive (default), hybrid/adaptive + neighbor expansion. One query can run
across several pipelines concurrently; the comparison (shared vs. unique evidence,
answer agreement) is itself a signal.

Every stage emits typed events (Pydantic models; TypeScript types are generated from
their JSON Schema, so the frontend can't drift from the backend):

`run.started` · `query.analyzed` · `stage.started/completed` (embed, retrieve.lexical,
retrieve.dense, retrieve.facets, fuse, probe, select, remediate, pack, generate,
verify) · `candidates.scored` · `selection.decision` · `flag.raised` · `answer.delta` ·
`answer.sentence_linked` · `run.completed` (full `QueryTrace`, manifest, ledger, flags).

Transport: `POST /live/runs` streams Server-Sent Events. Every run is stored, so
`GET /live/runs/{id}` replays it exactly, which is how the process animation can be
scrubbed after the fact. Retrieval is fast (target < 150 ms for ~5k passages); the slow
step is generation, so the visual process naturally plays out while the answer streams.

## 8. Frontend: answer-first, process on demand

Stack (pinned exact versions at install): React 19, TypeScript, Vite, Tailwind CSS v4,
Motion for UI transitions, PixiJS 8 (WebGPU with WebGL fallback) for the evidence field,
d3 for scales and the stage-flow diagram, Zustand for state. The process view and PixiJS
are code-split, so the default answer view stays light.

### 8.1 Three levels of disclosure

1. **Answer** (default). The answer streams with inline citation chips. Below it, one
   line, the *process receipt*: "Searched 1,240 passages by keyword and by meaning ·
   used 9 · 2 things worth a look · 14 checks passed." Hovering a citation shows the
   exact source sentence.
2. **Checks** (one click on the receipt). Three groups, in this order:
   - *Worth a look*: unresolved items that could change the answer, at most three shown
     by default, ranked. Each says what was observed, why it might matter, and offers
     **Show me**, which opens the source at the exact span.
   - *Handled*: "We noticed X, so we did Y." For example: "This passage begins with
     'However, this does not apply' and its subject was in the previous passage, so we
     included that passage too."
   - *Passed*: collapsed list of the checks that found nothing. Showing that checks ran
     and passed is a large part of what earns trust.
3. **Process** (toggle, remembered per user). The full animated view: the evidence field,
   the stage timeline, and the decision ledger, synchronized and scrubbable.

The point of this split: the user who trusts the answer reads one line and moves on; the
user who doubts it can verify the specific doubtful thing in one click instead of
re-reading the source; the user who wants to understand the machine can watch it.
Alert fatigue is treated as a real failure: surfaced flags are capped and ranked, and
"handled" items never masquerade as warnings.

### 8.2 The evidence field (process view)

A query-centered radial layout, chosen because every visual dimension *means* something
(unlike a UMAP projection, whose axes do not):

- Center: the query. Distance from center: semantic distance (z-scored, so a
  near-center dot is genuinely unusually close, not just "high cosine").
- Angle: position in the document (the ring is the document, read clockwise), so
  clusters show *where* in the text the evidence lives, and a missed passage is visibly
  next to the ones that were found.
- Color: how it was found (keyword, meaning, both, facet search); outline: its fate
  (selected, pulled in, omitted for budget, below cutoff).

Animation (driven by real events, replayed at human pace, about 4 s, skippable, honors
`prefers-reduced-motion`): the query pulses outward; keyword hits and semantic hits light
up in their own colors; disagreements stay lit in one color only; selected passages
travel inward to an answer zone; omitted ones dim with their reason; remediation pulls
arrive along an arc from their neighbor. Flags appear as markers on the passages they
concern. A document strip under the field shows the same states linearly, which reads
better for a 300-page document.

Alongside it: a stage-flow diagram (counts flowing pool → selected → packed → cited)
and the ledger, filterable by fate.

### 8.3 Comparing pipelines

Small multiples of the evidence field, one per pipeline, with a shared legend and a diff:
evidence only one pipeline found, and whether the answers agree.

## 9. Testing

- Unit tests per probe and gap signal with constructed cases where the right answer is
  known by construction (e.g. a query whose negation the hashing embedder provably
  ignores; a corpus where a passage's subject is in the preceding segment).
- The ported risk-triage regression tests, including the source self-scan for bare
  substring matching.
- Adaptive-k determinism: same inputs give the same ledger, byte for byte.
- End-to-end: the Asteria fixture through every preset, asserting the `QueryTrace`
  validates and every pool candidate has exactly one fate.
- Event-stream contract: the generated TypeScript types and the Python models agree.
- `make dev-check` stays green; the 511 existing tests stay green.

## 10. Build order

1. Embedding backends, `LiveCorpus`, model characterization (`EmbedderProfile`, §3.2),
   query analysis.
2. Retrieval, fusion, probes D1–D6.
3. Selection, gap signals, remediation, ledger.
4. Ported text-artifact detectors and flag model with registry linkage.
5. Answer providers (extractive offline default; Claude and OpenAI adapters) and
   verification.
6. Event stream, runner, API, stored runs.
7. Frontend: answer view and receipt, then checks, then the process view, then
   pipeline comparison.
8. Sample corpora for development: Asteria (tracked), plus a public-domain novel and a
   public-domain dense technical document fetched by script, not committed.

## 11. Explicit non-goals for Phase 1, and hooks left for later

- No corpus-type adaptation yet (Phase 2), but `CorpusProfile` is computed for every
  corpus and recorded in the run, and pipeline defaults are read from one place, so
  Phase 2 can make them profile-dependent without reshaping anything.
- No user modeling yet (Phase 2); the disclosure level is a stored preference only.
- No open-weights model tracing yet (later): the `AnswerProvider` protocol reserves an
  optional attribution channel (answer token span → context span with weight), so a local
  model's attention/attribution can feed the same verification view.
- No new registry mechanisms. Embedding probes are measured observations of this run,
  not failure mechanisms; they carry no `mechanism_id` and make no claim about embeddings
  in general.
- No public deployment.

## 12. Status (2026-11-04, end of first build session)

Built and running locally (`make live` in `engine/`, then http://127.0.0.1:8100):

- Backend: build steps 1-6 complete (`live/`), 28 new tests, 539 total passing, ruff and
  mypy clean on the new code. Warm runs: ~0.1-0.25 s for four pipelines over a 770 KB novel;
  corpora warm in a background thread on upload.
- Frontend (`web/`): answer view with citation popovers and sentence-level flags, the
  one-line receipt, the Checks panel (worth a look / handled / good to know / passed),
  "Show me" source drawer, question anatomy with the measured model profile, pipeline
  comparison, and the lazy-loaded process view (PixiJS evidence field, replay timeline,
  passage flow, live findings, full decision ledger). Light and dark themes; phone width
  verified with no horizontal scroll.
- TypeScript types are generated from the backend's JSON Schema (`npm run gen:types`).

Changes made while building, relative to the plan above:

- Answerability (D6a) uses "key terms absent from the whole document + meaning no closer
  than off-topic calibration questions", not a z-score of the best match: measured, the
  best-match z of real and off-topic questions overlapped on a novel (§3.2 calibration).
- Thresholds originally written as constants were replaced by measured ones where they
  existed (facet coverage by meaning, redundancy, keyword-only blind spots).
- Adaptive k falls back to the configured k when relevance declines smoothly with no
  natural cutoff, and says so in the ledger.
- The static embedding model *does* truncate (512 tokens); the window measurement caught
  the wrong assumption.

Added later the same day: medical checks (doses/units vs. source, patient-population
qualifiers, drug-label numbered cross-references), an FDA-label sample corpus, and the
external-pipeline integration API (`POST /live/check`, docs/integration.md) with access
levels trace / document / +embeddings (the caller's own model reached by callback and
measured like any other).

Not yet done: retriever-only access (ranking callbacks without texts), a reranker
channel, LLM answers exercised against a live API (no credentials configured here), and
a browser-level test suite.
