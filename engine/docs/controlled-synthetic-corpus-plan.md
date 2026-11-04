# Controlled synthetic corpus plan

A fully fictional, tracked, redistributable documentation corpus ("Asteria Autonomous
Systems Certification Manual") plus a local frontend/API integration demo, built as a
**product-integration and regression-testing milestone**. Written before any corpus
file or frontend change, per project convention.

## 1. Corpus purpose and explicit non-goals

**Purpose**: a controlled, hand-authored, fully-understood corpus that exercises the
existing pipeline's retrieval/packing/claim-linking/evidence-set/cross-reference layers
against *known* ground truth -- every case's expected outcome is fixed at authoring
time, not discovered afterward. This is what a real/licensed corpus (the EU AI Act
pilot, `docs/eu-ai-act-pilot-execution-plan.md`) cannot offer: a real corpus tells you
what the system does on genuine text; a controlled corpus tells you *whether the system
does what it is supposed to*, because the author already knows the answer. The two are
complementary, not competing, diagnostic tools.

**Explicit non-goals** (all restated from the milestone brief, binding throughout):

- Not a real-corpus benchmark -- `Asteria` is entirely invented; no rate or count
  computed against it generalizes to real documents. See
  `docs/real-corpus-diagnostic-runbook.md` for the real-corpus counterpart.
- Not a human-subjects study -- no reviewer-experience claim, no usability finding, no
  measure from `docs/reviewer-measures.md` is collected here. Building the frontend
  demo is not running the study `docs/local-validation-protocol.md` designs.
- Not legal, medical, financial, or safety advice -- Asteria's fictional "certification"
  domain is deliberately generic and structurally similar to real regulatory documents
  (numbered clauses, definitions, annexes, tables) without being drawn from, or
  resembling in content, any real regulation, standard, or policy manual.
- Not evidence that any failure mode is prevalent in production -- a fixture case that
  demonstrates `REP_SEGMENTATION_GRANULARITY_MISMATCH` activating correctly proves the
  *gate logic* is wired correctly on this one designed input; it says nothing about how
  often that condition occurs on real traffic.
- Not grounds for changing the registry, evidence grades, or activation policies -- no
  fixture "expected activation" label is ever fed back into `EpistemicStatus`,
  `EvidenceGrade`, or `ActivationPolicy`. A fixture label that says "this mechanism
  should activate here" is a regression-test assertion about *this codebase's current
  gate logic*, never a claim about the mechanism's real-world validity.

## 2. Fictional domain and anti-copying rule

Domain: **Asteria Autonomous Systems Certification Manual**, published by a fictional
"Asteria Standards Authority" governing certification of fictional "autonomous
inspection units" (AIUs) -- entirely invented terminology, entities, thresholds, and
rule structure. Chosen to be structurally rich (numbered clauses, definitions, annexes,
tables, cross-references, effective dates) without being a real domain, avoiding any
risk of being mistaken for real guidance the way a "widget certification" corpus never
could be mistaken for real product-safety law, and matching the existing bundled
`widget-certification-demo` fixture's own fictional-domain precedent
(`src/wittgenstein/demo/widget_corpus.py`) but built independently and never merged
with it.

**Anti-copying rule**: no long passages, entity names, rule wording, numeric
thresholds, or organizational names are borrowed from any real regulation, standard,
product manual, clinical guideline, or policy document. All entity names ("Asteria
Standards Authority", "Class R inspection unit", "Directive Annex A"), numeric
thresholds, and clause text are invented for this corpus. Structural *patterns*
(numbered clauses with sub-points, a definitions annex, a conformity table, effective-
date language) are common to essentially all regulatory-style documents and are not
themselves copyrightable content -- using that shape is not "borrowing" any specific
source.

## 3. Source-document hierarchy

```
data/fixtures/asteria_manual/
  README.md                      fictional/research-only notice, corpus summary
  manifest.yaml                  human-readable copy of the four PipelineManifests (documentation only)
  manifests.json                 the actual machine-readable manifest registry (SmokeTestCase-compatible)
  documents/
    d1-definitions.md            Definitions (D-01..D-xx)
    d2-classification.md         Clause 2.x: classification rules, conditions, exceptions
    d3-registration.md           Clause 3.x: registration/reporting obligations, cross-references
    annex-a-conformity-table.md  Annex A: a Markdown conformity table + explicit cross-references to it
  cases/
    cases.json                   SmokeTestCaseFile -- the 8-10 vertical-slice cases
  expected/
    <case_id>.expected.json      per-case ground-truth/perturbation metadata (see §10)
```

Four documents in the initial vertical slice (the brief's "3-4 Markdown documents"):
`d1-definitions.md` (a definitions document, required by the brief), `d2-classification.md`
and `d3-registration.md` (clause-bearing normative documents, mirroring the two-document
"rule + registration obligation" shape the EU AI Act pilot exercised), and
`annex-a-conformity-table.md` (an annex containing the required Markdown table). This
mirrors the existing bundled `widget-certification-demo` corpus's multi-document shape
(`certification-handbook`/`inspection-procedures`) without reusing any of its content.

## 4. Stable identifiers and source-location strategy

Every clause/definition/annex/table carries an explicit, stable, human-citable
identifier, chosen to be parseable by the *existing* deterministic parser
(`ingestion/parser.py`) without any parser change:

- Numbered clauses as ATX headings: `## Clause 2.1 Classification of inspection units`
  -- the parser's `_HEADING_RE` already gives each such heading its own `SourceSegment`
  with `location` = the full heading path, so "Clause 2.1" is directly addressable by
  heading text, exactly as `docs/multi-passage-evidence-plan.md`'s worked examples and
  the widget corpus's `"## Section 3: Testing Standards"` headings already are.
- Sub-clauses as explicit lettered/numbered markers at the start of a line: `(a)`, `(b)`
  and `1.`/`2.` -- reusing the *same* deterministic patterns
  `docs/cross-reference-granularity-resolution-plan.md` added
  (`_NUMBERED_PARAGRAPH_MARKER_RE`, `_POINT_MARKER_RE`) plus the pre-existing
  `_ARTICLE_TITLE_RE`-style convention adapted to "Clause": each clause document opens
  with a standalone title paragraph (e.g. `Clause 2.1`) so `legal_article_number`-style
  carry-forward context applies -- see §6 for the exact authoring convention this
  requires.
- Definitions as `Definition D-01`, one per numbered list item (`1. **D-01** ...`) in
  `d1-definitions.md`, addressable the same way EU AI Act Article 3's definitions were
  (`article-3-definitions-selected.txt`'s pattern, reused for a fictional domain).
- The annex as `Annex A`, with its Markdown table's rows individually addressable via
  the parser's existing `TABLE_ROW` segment type (`location` = `"Annex A > Table row
  N"`).
- `Table A.2` names a specific table inside Annex A when more than one table exists (a
  disambiguating label used inside cross-reference text, e.g. "see Table A.2" --
  resolved the same structural, non-semantic way any other cross-reference target is:
  location-text substring match against `SourceSegment.location`, never a new parser
  code path).

No new segment type and no new `SourceSegment` field are required for the vertical
slice: `docs/cross-reference-granularity-resolution-plan.md`'s existing
`legal_article_number`/`legal_paragraph_number`/`legal_point_identifier` machinery
already covers "Clause 2.1" (article-analog), numbered/lettered sub-points, and the
existing cross-reference regex already covers `Section`/`Table`/`Annex`/`Clause`-style
markers via the pre-existing generic-cue path (`Clause` is already one of its
recognized keywords -- `proposition/annotations.py::_CROSS_REFERENCE_RE`). Where a
citation needs paragraph/point-level exactness (mirroring the EU AI Act "Article 49(2)"
case), the existing `_ARTICLE_SINGLE_RE`-equivalent behavior is reused by phrasing the
citation as `Clause 2.1(b)` -- the granularity-resolution plan's parser additions key
off the bare numbered/lettered *markers*, not the word "Article" specifically, so this
works for "Clause" citations without any code change (verified empirically in §14,
fixture-integrity tests).

## 5. Corpus scale and phased expansion strategy

- **Initial vertical slice** (this milestone): 4 documents, ~10-15 numbered
  clauses/sub-clauses/definitions, 8-10 cases, roughly 1,500-2,500 words total --
  enough for real retrieval competition and a meaningful low-token-budget packing
  configuration (P2), far short of the eventual 12,000-25,000-word target.
- **Deferred expansion** (explicitly out of scope for this milestone, §16): additional
  clause documents, a second annex, more definitions, deeper cross-reference chains,
  and enough content that a top-k retrieval pass genuinely has to discriminate among
  many topically similar candidates rather than the small pool this slice provides.
  Expansion happens only after this slice's fixture-integrity validation, pipeline
  traces, and frontend wiring are all green -- per the milestone's own "Implementation
  order" §10.

## 6. Controlled source-authoring protocol

Every document is authored with the same discipline used for the EU AI Act pilot's
`metadata.json` (`docs/eu-ai-act-pilot-execution-plan.md`), adapted for fictional,
hand-authored (not transcribed) content:

1. Write the clause text first, in isolation, deciding exactly what it supports before
   any case references it.
2. Give it a stable heading (`## Clause N.M <short title>`) and, where it establishes a
   citable rule, an explicit paragraph/point marker (`1.`, `(a)`) so it is addressable
   at the granularity a case needs.
3. Author distractor clauses only after the supporting clause is finalized and stable
   (§9's "add distractors last" rule) -- never interleaved with primary content, so a
   later edit to a support clause cannot silently invalidate an already-checked
   distractor.
4. Record the clause's exact heading path (the parser's `location` string) in the
   case's `expected/<case_id>.expected.json` the moment the clause is written -- never
   reconstructed from memory afterward.
5. Every document opens with a version/effective-date line (e.g. "Version 3.2,
   effective 1 March 2027") in the same free-text style as the EU AI Act corpus's
   Article 113 entry-into-force language, giving the temporal-mismatch perturbation
   category (§9) something real to alter.

## 7. Failure/trace-condition coverage matrix

See `docs/controlled-corpus-coverage-matrix.md` (a separate, generated-by-hand
document, not duplicated here per CLAUDE.md's "avoid two lists describing the same
categories that can drift out of sync" -- this plan states the *categories*; the matrix
holds the *per-case* mapping). The matrix's columns are fixed in advance (§ "COVERAGE
MATRIX" of the milestone brief, reproduced verbatim as the matrix's own column
headers), separating four kinds of expectation per case:

- **Externally supported registry mechanism** -- a mechanism at
  `epistemic_status=externally_established` with a real deterministic evaluator in
  `matching/eligibility.py` (only `REP_SEGMENTATION_GRANULARITY_MISMATCH` and
  `PACK_OMISSION_OR_TRUNCATION` currently qualify; `GEN_CONTEXT_CONFLICT_UNRESOLVED`/
  `GEN_UNSUPPORTED_DESPITE_CONTEXT` are `manifest_conditioned_transfer`, still
  deterministically evaluated but not "externally established").
- **Trace integrity event** -- a directly observable pipeline fact
  (`trace_integrity_condition`-status mechanisms, or a bare `ContextItem`/
  `AnswerSupportEdge` field like `omission_reason`), never itself a causal claim.
- **Experimental linguistic review cue** -- a Tier-2 annotation
  (`AnnotationCueType.CONDITION`/`EXCEPTION`/`CROSS_REFERENCE`/etc.), always labeled
  `research_hypothesis`/`experimental_review_cue`, never presented as confirmed.
- **Synthetic fixture expectation** -- a value this plan's own authors assert about
  *this specific hand-built case* (e.g. "the minimum evidence set is {clause 2.1,
  clause 3.2}"), true by construction, never inferred or asserted as a general system
  property.

## 8. Query and answer-case taxonomy

The 13 required scenario categories (direct single-span support; definition +
requirement; two-passage complementary support; rule + condition; rule + exception;
cross-reference where the exact target is packed; cross-reference where a target is
in-corpus-but-not-retrieved/packed under budget stress; same-topic non-supporting
distractor; numeric/frequency/unit/threshold mismatch; segmentation-boundary
dependency case; full-context non-activation control; underspecified user intent;
unresolved/source-expansion/clarification review outcome) map to 8-10 cases, several
categories doubled up per case where natural (the brief explicitly permits this). The
exact per-case mapping is fixed in `docs/controlled-corpus-coverage-matrix.md`,
authored alongside the case files themselves (§14's Implementation order), not
predicted here before the clause text exists.

## 9. Controlled perturbation protocol

Perturbation categories used (a subset of the brief's list, chosen to exercise
mechanisms the existing field-comparison/evidence-set engine already detects --
`docs/claim-linking-improvement-plan.md`'s rules A-G, `MismatchType`'s 18 values):
**polarity/negation change**, **condition omission**, **numeric/threshold mismatch**,
**wrong cross-reference target**. Each perturbed case's `expected/<case_id>.expected.json`
records, per the brief's exact 5-field list:

```json
{
  "controlled_perturbation": true,
  "source_supported_answer": "...",
  "perturbed_answer": "...",
  "perturbation_type": "numeric_threshold_mismatch",
  "changed_claim_component": "numeric_value",
  "expected_claim_linking_status": "contradiction_candidate",
  "expected_reviewer_action": "reject_as_unsupported"
}
```

Authoring order per case (the brief's 9-step protocol, applied identically to every
case regardless of whether it is perturbed): write the source-supported material first;
record exact source locations and the minimum required evidence set; write the query
and constraints; write the source-supported answer (or the imported-answer fixture);
only then author a perturbation (if any) with full before/after provenance; add
distractors last, and verify by construction that a distractor does not accidentally
satisfy the claim it is meant to fail to support (checked mechanically -- §14, fixture
integrity). No automated UI output is ever made to declare an answer objectively true
or false; `expected_*` fields are fixture regression labels compared against the
system's own candidate/diagnostic output in tests, never surfaced to a reviewer as
ground truth in the frontend (the milestone brief's explicit UI constraint, §12).

## 10. Ground-truth boundaries

An `expected/<case_id>.expected.json` file is a **fixture regression label**, checked
against this codebase's *current, deterministic* behavior by the fixture-integrity
validator and by tests -- it is never treated as, or exposed to a reviewer as, a
factual truth about the fictional Asteria domain (which has no external truth to
recover, being invented) nor as a claim about real RAG systems. Concretely bounded:

- `expected_evidence_locations` / `minimum_evidence_set`: what *this case's author*
  determined is needed, recorded before any pipeline run, used only to check the
  pipeline's *retrieval and evidence-set construction* found (or omitted) the same
  locations -- never presented to a reviewer as "the correct answer."
- `expected_claim_link_relationship` / `expected_evidence_set_status`: the
  `ClaimSupportCandidateStatus`/`EvidenceSet.relationship_status` this case's
  field-comparison inputs were deliberately constructed to produce -- a test assertion
  about the *engine's classification logic*, not a legal or factual adjudication.
- `expected_reviewer_action`: **advisory only** -- present in the fixture data for
  regression-test and documentation purposes, but never passed to, forced by, or
  highlighted as correct in the review frontend, which the milestone brief requires
  stays fully open (all eleven reviewer actions available on every case, §13).

## 11. Available pipeline manifests

Four `PipelineManifest`s, `manifests.json` (machine-readable, `load_manifests`-
compatible) plus a human-readable `manifest.yaml` mirror for documentation (the two are
generated together, never hand-edited separately, to avoid CLAUDE.md's "two lists that
must stay in sync" trap -- `manifest.yaml` states this in its own header comment):

- **P1 `asteria-p1-baseline`**: deterministic Markdown parsing (the existing
  `ingestion/parser.py`, unchanged), `chunking_method="structural_segmentation_no_fixed_window"`,
  `retrieval_unit="paragraph_list_item_table_row"` (sub-document, satisfying
  `REP_SEGMENTATION_GRANULARITY_MISMATCH`'s manifest gates), BM25 lexical retrieval
  (`retrieval/lexical.py`, unchanged), `candidate_depth=5`, verbatim deterministic
  packing (`trace/packer.py`, unchanged), `evidence_budget_tokens=600`, no LLM.
  **Executable** -- this is exactly the existing `demo/pipeline.py::build_manifest`
  shape, already proven against the widget corpus.
- **P2 `asteria-p2-budget-stressed`**: identical to P1 except
  `evidence_budget_tokens`/`context_window_tokens` reduced (e.g. to 120 tokens) so that,
  for the specific cases designed against it, at least one selected item is
  identifiably omitted by the token budget (`trace/packer.py`'s existing
  `omission_reason="context_budget_exceeded"` path, unchanged). **Executable**.
- **P3 `asteria-p3-parent-context`**: a manifest configuration representing
  "parent/neighbor context reconstruction is enabled" at the *manifest-description*
  level (`representation_manifest`/`retrieval_manifest` fields set to describe such a
  system) -- **not executable**: no code in this repository actually reconstructs
  parent/neighbor context around a retrieved child segment (confirmed by inspecting
  `trace/packer.py` and `retrieval/lexical.py`; no such step exists). Documented,
  per the milestone brief's explicit instruction, as representable-but-not-executable
  and excluded from every automated demo claim and from the fixture-integrity
  validator's "must run cleanly" set -- included in `manifests.json` for schema
  validation only (`wittgenstein manifest validate` passes; `wittgenstein fixture run`
  is never invoked against it).
- **P4 `asteria-p4-full-context-control`**: identical to P1's retrieval, but a case run
  against it is deliberately chosen (§8, case 11) so its packed excerpt carries no
  CONDITION/EXCEPTION/CROSS_REFERENCE Tier-2 cue at all -- `trace.segment_boundary_dependency_flags`
  stays empty, so `REP_SEGMENTATION_GRANULARITY_MISMATCH`'s trace-observable gate
  (`TO_REP_SEG_boundary_flags`) is `VIOLATED` and the mechanism does not activate, a
  genuine (not asserted) non-activation confirmed by directly calling
  `matching/eligibility.py::evaluate_eligibility` in a test. **Executable**.

## 12. Local frontend/API workflow

`review/imported_answer.py::import_answer`'s existing corpus-branch (`corpus=<dict>`)
already produces a trace with `segment_boundary_dependency_flags` populated correctly
via the existing, unmodified `demo/pipeline.py::run_demo_query` -- confirmed empirically
against the existing widget corpus before writing this plan (no `import_answer` code
change is needed for the segmentation-mismatch case to work). Two small, additive gaps
exist and are closed by this milestone:

1. `api/routes/review.py`'s `POST /review/import-answer` response omits
   `claim_evidence_comparisons`, `evidence_sets`, and cross-reference marker data
   entirely -- the milestone brief requires the frontend to display all three. Closed
   by adding these as new, additive response keys (never removing or renaming an
   existing key), reusing the existing `ClaimEvidenceComparison`/`EvidenceSet.model_dump`
   calls and a small new shared helper,
   `review/cross_reference_diagnostics.py::marker_to_dict`, factored out of
   `evidence_set_diagnostics/runner.py::build_diagnostic_report`'s existing inline dict
   construction (a refactor, verified behavior-preserving against that module's
   existing tests -- not a new detection/resolution algorithm).
2. `smoke_test/corpus_registry.py::_bundled_fixture` only knows `"widget-certification-demo"`.
   Closed by adding `"asteria-manual"`, resolved by a new
   `src/wittgenstein/demo/asteria_corpus.py::documents()` that reads
   `data/fixtures/asteria_manual/documents/*.md` from disk (the corpus lives as tracked
   Markdown files, not inlined Python strings, per the milestone brief's explicit
   directory layout) -- unlike `widget_corpus.py`, but consistent with how
   `smoke_test/corpus_registry.py::_load_local_path` already reads `.md`/`.txt` files
   from a directory for the `local_path_excluded_from_git` source type (the same
   file-reading logic, reused for a *tracked* directory instead of a gitignored one).

Frontend (`frontend/public/review.html`) changes, additive only: a corpus selector
(Widget / Asteria, defaulting to the existing Widget behavior unchanged), an Asteria
case-picker dropdown (pre-fills query/answer from the 8-10 fixture cases, embedded as a
small inline JS array generated from `cases/cases.json` -- the same "kept in sync by
hand, documented as such" pattern the existing `WIDGET_CORPUS` constant already uses),
an `ASTERIA_CORPUS` inline JS object generated from `documents/*.md` (same pattern), and
new render sections for claim/evidence-comparison fields, evidence-set composition, and
cross-reference targets (coarse state, resolution granularity, exact-target
availability) -- append-only additions to the existing render pipeline; every existing
section (answer claims, risk events, packed/omitted/retrieved evidence, reviewer panel)
is unchanged in behavior.

## 13. Review-action workflow

Unchanged from the existing `ReviewerAction` vocabulary already wired end-to-end
(`review.html`'s `REVIEWER_ACTIONS` array, `POST /review/events`,
`schemas/review_event.py::ReviewEvent`, `db/models/records.py::ReviewEventRecord`) --
all eleven actions remain available on every Asteria case exactly as they are for the
widget corpus today; no fixture-specific restriction is added, and no
`expected_reviewer_action` fixture value is ever passed into the UI as a default,
highlighted, or forced choice (§10). `ReviewEvent` persistence (trace id, reviewer id,
review condition, displayed risk events, opened evidence, action, confidence,
uncertainty, notes, timestamp) is exercised against Asteria traces using the exact same
code path already proven for the widget corpus -- no schema or service change.

## 14. Fixture-integrity tests

A new deterministic validator (`src/wittgenstein/fixtures/asteria_validator.py`, wired
as `wittgenstein fixture load asteria_manual`'s validation step -- folded into `load`
rather than a separate subcommand, per the milestone brief's "keep it minimal, adapt to
the existing CLI" instruction) checks, before any case is run: every document/section id
referenced by a case's `expected_evidence_locations` actually exists in the parsed
corpus index; no duplicate `source_document_id`; every cross-reference target a case's
`expected/*.json` claims should exist does exist (or is deliberately marked
`expected_target_state: unknown`); every controlled-perturbation case's `expected/*.json`
carries full before/after provenance; every distractor location's field-comparison
output does *not* satisfy the claim it is designed to fail (checked by literally running
`field_comparison`/`construct_evidence_set` against it and asserting the outcome is not
`direct_support_candidate`); no fixture `expected/*.json` field name collides with a
registry/`EpistemicStatus`/`ActivationPolicy` vocabulary term in a way that could be
mistaken for one (a naming-convention check, not a runtime capability check -- this
validator has no way to *change* a registry value, so this guards against confusing
naming only); no tracked file under `data/fixtures/asteria_manual/` matches any
real-source provenance marker already used by the EU AI Act pilot's `metadata.json`
schema (i.e. Asteria's own metadata never claims a `source_url`/`publisher` pointing at
a real external body); the P1/P2/P4 baseline execution invokes zero LLM calls
(`ImportedAnswerResult.llm_extractions == []` when no `llm_client` is passed); and two
independent runs of the same case produce byte-identical trace/comparison/evidence-set
output modulo the known-legitimately-varying fields (uuids, timestamps -- the same
normalization already used by every prior determinism test in this repository).

## 15. No-LLM reproducibility requirements

Every fixture case's default execution path (`fixture run`, the frontend's default
"Run imported-answer review" button, and every fixture-integrity test) passes no
`llm_client` -- `import_answer`'s existing "no client = no client passed to
`extract_tier3`, which already treats absence and unavailability identically" guarantee
(`docs/efficiency-and-processing-architecture.md` §1) is reused unmodified, not
reimplemented. No network access occurs at runtime because no code path in the default
Asteria demo ever imports `anthropic` or performs an HTTP call
(`proposition/providers/anthropic_client.py` is imported lazily inside methods only,
per §12 of `docs/implementation-plan.md`, and nothing in this milestone changes that).
An optional enhanced-mode toggle may remain visible in the frontend as a disabled/
unavailable control (mirroring `docs/review-loop-demo.md`'s existing "Enhanced mode"
section, which documents but does not wire an LLM path into the static page) --
implementing a live enhanced path for Asteria is explicitly out of scope.

## 16. What remains deferred

- Corpus expansion beyond the ~10-15-clause vertical slice (§5) -- a second annex,
  additional clause documents, deeper cross-reference chains, and enough retrieval
  competition to meaningfully stress top-k discrimination at the eventual
  12,000-25,000-word scale.
- P3 (`asteria-p3-parent-context`) becoming actually executable -- would require
  implementing parent/neighbor context reconstruction in `trace/packer.py` or a new
  module, explicitly out of scope for this milestone (no new retrieval system is to be
  built).
- Any real human-review usability/effectiveness measurement
  (`docs/local-validation-protocol.md`'s six-layer study) -- this milestone builds the
  fixture and the local demo surface that *could* support such a study later; it does
  not run one, collect any reviewer-experience measure, or recruit any participant.
- Any registry/evidence-grade/activation-policy change motivated by anything observed
  against Asteria -- fixture pass/fail is a statement about this codebase's current
  deterministic logic on a designed input, never a promotion signal.
- An enhanced (LLM-backed) Asteria demo path.
