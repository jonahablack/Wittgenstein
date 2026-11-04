# Real-corpus diagnostic pass for the multi-passage evidence-set layer

A small, manually reviewed diagnostic pass over real, licensed, or user-provided
documents, run through `review/evidence_set.py` (`docs/multi-passage-evidence-plan.md`)
to measure -- not fix -- the two limitations that milestone's own report surfaced:
cross-reference/definition closure outside the packed pool, and extraction reliability
on long real-corpus sentences. A secondary measurement target is whether the default
`max_set_size=2` bound ever blocks a reviewer-important composition.

**This is not a human-subjects study** (`docs/local-validation-protocol.md`'s reviewer
study -- real reviewers, review conditions, six outcome layers -- is separate, larger,
and not run or replaced here; this pass produces artifacts one researcher reads alone).
**It is not a benchmark claim** (a handful of pilot cases can reveal that a problem
exists; it cannot establish its true rate, a confidence interval, or that a problem is
absent because it didn't appear in this small a sample -- same posture as
`docs/real-trace-smoke-test-plan.md` §13, restated for this pass in §11 below).

## 1. Document/corpus inclusion and licensing rules

Same rules as `docs/real-trace-smoke-test-plan.md` §1-2, extended, not replaced:

- A corpus is included only if the user has confirmed the right to process it locally
  for this diagnostic purpose (owned, appropriately licensed, or otherwise cleared --
  never scraped or assumed-permissible).
- No restricted document text is ever committed to git (§3).
- A corpus may be real (licensed/user-provided, `local_path_excluded_from_git`) or the
  bundled synthetic `widget-certification-demo` fixture
  (`bundled_synthetic_fixture`) -- both source types are valid for this pass exactly as
  they are for the smoke-test harness; the difference is purpose (diagnosing this
  layer's real-corpus behavior), not a new corpus-eligibility rule.
- A corpus is preferred for this pass if it plausibly contains: long/complex
  sentences, explicit cross-references, multiple independent scope/condition
  qualifiers, and more than one document version -- see §5.

## 2. Source/version/provenance requirements

Reuses `schemas/smoke_test.py::CorpusReference` unchanged (`corpus_id`, `source_type`,
`local_path`, `document_hashes`, `source_metadata`) and `SmokeTestCase.document_version`/
`provenance_status` unchanged -- no new provenance schema. A real document's
`document_hashes` entry is required (content-hash pinned, per
`docs/real-trace-smoke-test-plan.md` §2's drift-detection rule) so a diagnostic finding
is always reproducible against the exact document version it was observed on.

## 3. How restricted content is excluded from git

Identical mechanism to the smoke-test harness, reused, not reimplemented: a real
corpus is `source_type="local_path_excluded_from_git"`, read only from
`data/examples/evidence_set_diagnostics/local_corpora/` (a new, `.gitignore`d sibling
directory to the existing `data/examples/real_trace_smoke/local_corpora/`), resolved
at run time by `smoke_test/corpus_registry.py::resolve_corpus` (reused directly, not
forked -- see §RE-USE note below). Only the *diagnostic case file itself* (query,
answer, hashes, manual labels -- never source document text) and any
`bundled_synthetic_fixture` cases are committed.

## 4. Query and answer-pair selection

Selected (not generated) by the researcher running the pass, the same way
`docs/real-trace-smoke-test-plan.md` §5's cases are hand-authored: pick real questions
a reviewer plausibly asked of this corpus, write an answer that is either the
document's own stated answer or a deliberately crafted compound answer exercising a
specific scenario (§5). `answer_source_method` (reused from `SmokeTestCase`) records
whether the answer is `human_authored_for_pilot`, `document_verbatim`, or
`llm_generated_unverified` -- never fabricated and presented as verified.

## 5. Intentional sampling of long sentences, cross-references, multi-passage evidence, and conflicts

At least one case each, across the diagnostic case set, for:

- A long (>25-word), syntactically complex real sentence carrying 3+ of the 17
  extractable fields at once (stresses OBJECT_VALUE/NUMERIC_VALUE's "rest of the
  sentence" heuristics -- the exact weakness `docs/multi-passage-evidence-plan.md` §11
  flagged).
- An explicit cross-reference marker ("Section 4", "Exemption C", ...) whose target is
  (a) packed, (b) retrieved but not packed, (c) in the corpus but never retrieved.
- A compound claim genuinely requiring two packed passages (mirrors
  `docs/multi-passage-evidence-demo.md` §2/§3).
- Two real passages stating apparently different values for what may or may not be the
  same requirement (to distinguish a genuine conflict from a version/scope/extraction
  artifact -- §7).
- A claim whose complete support plausibly requires a third passage (to populate the
  size-3 diagnostic -- §9).

Cases are added to reach this coverage deliberately, not drawn at random from the
corpus -- this pass diagnoses known suspected weaknesses, it does not sample for
prevalence (see §11).

## 6. Manual annotation protocol

One researcher reads each case's diagnostic report (`<case_id>.diagnostic.json`, §
"IMPLEMENT DIAGNOSTIC HARNESS" below) and fills in the accompanying
`<case_id>.diagnostic_labels.json` template using *only* the five label vocabularies
below (`core/enums.py`) -- never a free-text substitute for a listed label, though
`notes` fields remain free text throughout. A label is assigned per (claim, candidate)
pair for extraction-quality labels, per conflict for conflict-quality labels, per
cross-reference marker for closure labels, per (claim, evidence-set) for sizing
labels, and per case for reviewer/workflow labels -- mirroring
`docs/real-trace-smoke-test-plan.md` §6's existing per-artifact-type annotation
granularity. **These are diagnostic labels describing this pipeline's behavior, never
universal factual-truth labels about the underlying documents.**

## 7. Artifact-versus-genuine-conflict adjudication

For every `composite_conflict_candidate` in a case's evidence sets, the diagnostic
report includes a re-derived, per-conflict explanation (`conflict_diagnostics.py`,
computed read-only from the same `extract_fields`/`compare_field` calls
`_check_member_compatibility` already made, never a second extraction method):
conflicting members and fields, each side's exact source span, extraction method,
extraction confidence, and whether the conflicting field's confidence sits below a
diagnostic-only exposure threshold (`_DIAGNOSTIC_LOW_CONFIDENCE_THRESHOLD = 0.5`,
distinct from and never substituted for `relationship_classification.py`'s own
`_NOISE_FLOOR_CONFIDENCE`/`_CONTRADICTION_CONFIDENCE_THRESHOLD`, which remain the only
thresholds that affect actual classification). The researcher then assigns one Category
B label per conflict (§ "MANUAL DIAGNOSTIC LABELS"). The system never downgrades a
conflict on its own on the basis of this exposure -- see the milestone brief's explicit
prohibition, restated in code-level comments at the instrumentation site.

## 8. Cross-reference/definition-closure annotation

For every explicit cross-reference marker detected in an answer claim
(`core/enums.py::CrossReferenceTargetState`, computed by
`review/cross_reference_diagnostics.py` -- detection reuses
`ComparisonFieldName.CROSS_REFERENCE`'s existing extraction unchanged; target-state
resolution builds a fresh `ingestion.corpus_index.CorpusIndex` over the same corpus
text (idempotent/cached per `docs/efficiency-and-processing-architecture.md` §3) and
matches the marker text against each `SourceSegment.location`), the report records
which of `in_corpus` / `retrieved` / `selected` / `packed` / `omitted` / `unknown`
applies, plus the bounded warning text (§ "CROSS-REFERENCE MEASUREMENT ONLY")
when the target is not `packed`. The researcher assigns Category C labels judging
whether the target was actually *needed* to interpret the claim (a judgment the system
cannot make) versus merely clarifying.

## 9. Evidence-set-size diagnostic

For every claim where evidence-set construction was attempted (`attempted=True`) but
did not reach `composite_support_candidate` at the default `max_set_size=2`, the
report additionally computes (never searches, unless `--diagnostic-max-set-size 3` is
passed explicitly, § "ADAPTIVE SET-SIZE MEASUREMENT ONLY"): the uncovered critical
component ids after the best size-2 attempt, whether any of those components have an
explicit dependency/cross-reference suggesting a third item exists, the closed-form
count of size-3 combinations the pool would require (`math.comb(pool_size, 3)`, no
actual search), and an estimated wall-clock cost extrapolated from the case's own
measured size-2 `construction_latency_seconds`. The researcher assigns Category D
labels judging whether a third item was plausibly required and, if
`--diagnostic-max-set-size 3` was run for that case, whether it actually resolved the
gap.

## 10. Decision rules for next implementation priority

Restated verbatim from the milestone brief (not weakened): classify the dominant next
bottleneck as (A) cross-reference/definition closure, (B) extraction reliability, (C)
adaptive evidence-set size, (D) retrieval, or (E) review interface, using the exact
conditions given in the brief's "DECISION RULES" section. **No next-priority
recommendation is made in this plan doc, in `docs/evidence-set-real-corpus-diagnostics-results.md`'s
template, or by the diagnostic report generator itself** -- `generate_diagnostic_report`
computes only counts and rates; the classification is a human judgment made after
manual labels exist, recorded in the *filled-in* results doc, never inferred
automatically from unlabeled counts.

## 11. Limitations and non-generalization statement

- A handful of hand-selected cases can demonstrate that a problem exists; it cannot
  establish its true rate, a confidence interval, or that a problem is absent.
- Cases are deliberately sampled to stress known suspected weaknesses (§5), not drawn
  at random -- this pass is not representative of "typical" claims over the corpus and
  must never be reported as such.
- A conflict-vs-artifact or closure-necessity judgment made by one researcher reading
  one report is not inter-rater-reliability-checked here; it is a diagnostic opinion,
  not an adjudicated fact.
- This pass makes no claim about any real-world document's factual content -- every
  label describes this pipeline's behavior on that document, never the document's
  correctness.
- This pass is not evidence for or against promoting any registry mechanism, changing
  any `EpistemicStatus`/`ActivationPolicy`/validator threshold, or enabling
  `TRIAGE_ENABLED` -- that remains governed exclusively by
  `docs/registry-governance.md`.
- No implementation-priority decision is made until real diagnostics have actually
  been run and manually reviewed (§10); this plan and its harness only make that
  decision *possible*, they do not make it.

## Reuse notes (avoids duplicating existing schemas/modules, `CLAUDE.md`)

- **Case format**: reuses `schemas/smoke_test.py::SmokeTestCase`/`SmokeTestCaseFile`/
  `CorpusReference` unchanged as the diagnostic case input shape -- every field the
  milestone brief's "CREATE DIAGNOSTIC DATA FORMAT" section lists as case-level input
  (case ID, corpus/document ID, document version, source provenance, licensing status,
  query, query constraints, answer, answer source/method, pipeline manifest ID) already
  exists on `SmokeTestCase`. The remaining listed items (trace ID, candidate
  propositions, evidence sets considered, final status, field-comparison vectors,
  extraction methods/statuses, risk events, manual labels, reviewer notes) are *output*
  of running a case, not part of its input definition -- exactly the same input/output
  split `SmokeTestCase` vs. the inspection report already uses -- and live in the new
  `<case_id>.diagnostic.json` report and `<case_id>.diagnostic_labels.json` template
  (§ "IMPLEMENT DIAGNOSTIC HARNESS").
- **Corpus/manifest resolution**: reuses `smoke_test/corpus_registry.py::resolve_corpus`
  and `smoke_test/manifest_registry.py::load_manifests` directly.
- **Pipeline execution**: reuses `review/imported_answer.py::import_answer` unchanged
  (same no-LLM-by-default, same evidence-set construction call already wired in).
- **Field extraction/comparison**: reuses `review/field_extraction.py::extract_fields`
  and `review/field_comparison.py::compare_field` unchanged for diagnostic
  re-derivation (§7) -- never a second extraction implementation.
