# Real-trace smoke-test plan

A small pilot harness for manually diagnosing retrieval and claim-linking behavior on
realistic-shaped manifest/answer pairs, before deciding whether dense/hybrid retrieval
is actually the next-highest-value addition to the vertical slice
(`docs/efficiency-and-processing-architecture.md`,
`docs/review-loop-implementation-plan.md`). This is a diagnostic pilot, not a broad
benchmark, and it does not run or replace the human-subjects study designed in
`docs/local-validation-protocol.md`.

No registry evidence status, activation policy, validator threshold, or the general
`QueryTrace`/`PipelineManifest` schema is changed by this milestone. No dense or hybrid
retrieval is added.

## 1. Corpus/document inclusion rules

A document is eligible for the pilot if, and only if:

- Its provenance is known and recorded (`core/enums.py::ProvenanceStatus`) -- never
  `pending_provenance_review` for a document actually used to produce a case that will
  inform any decision.
- It is either (a) synthetic/fictional (safe to redistribute in this repository), or
  (b) user-provided or under a license the person adding it has confirmed permits the
  use here (local storage, local inspection, not redistribution unless the license
  says so).
- No document is downloaded by this harness itself. A human explicitly places a file
  under `data/examples/real_trace_smoke/local_corpora/` (gitignored) or supplies
  `--cases` pointing at a case file referencing such a path; the harness never fetches
  a URL.

## 2. Provenance and licensing requirements

Every `CorpusReference` (`schemas/smoke_test.py`) records `source_type`
(`bundled_synthetic_fixture` or `local_path_excluded_from_git`), and every
`SmokeTestCase` records a `provenance_status`. Only `bundled_synthetic_fixture` /
`synthetic_fictional` cases may ever be committed to this repository (enforced by
convention and by this doc, not by code -- a human adding a case is the one who must
not commit real document text). Real-document cases store, and only store:

- `corpus_id` (a label, not content).
- `document_hashes` (sha256 per document -- lets drift in the local file be detected
  even though the file itself is never committed).
- `source_metadata` (title/publisher/license/access_date -- metadata, never text).
- `local_path` (a path string on the machine running the smoke test, gitignored).

See `data/examples/real_trace_smoke/README.md` for the concrete workflow.

## 3. Required manifest fields

A case's `pipeline_manifest_id` is looked up in an accompanying `manifests.json`
(`{manifest_id: PipelineManifest}`), validated the same way
`api/routes/manifests.py::validate_manifest` already validates any manifest: successful
`PipelineManifest.model_validate(...)`. No new manifest fields are required beyond the
existing schema (`schemas/manifest.py`) -- an honest, mostly-`None` manifest is
acceptable when the real pipeline configuration is not fully known, per this project's
existing "never infer missing manifest values" rule; it is not required to declare a
retrieval/packing configuration this harness doesn't itself exercise (dense retrieval
fields, for instance, stay `None`).

## 4. Required answer-pair fields

See `schemas/smoke_test.py::SmokeTestCase` for the enforced shape (Pydantic,
`extra="forbid"`): `case_id`, `corpus` (a `CorpusReference`), `document_version`,
`query`, `query_constraints`, `user_intent_notes`, `answer`, `answer_source_method`,
`pipeline_manifest_id`, `expected_evidence_locations`, `pilot_coverage_labels`,
`reviewer_notes`, `provenance_status`. `cases.schema.json` is this model's exported
JSON Schema.

## 5. Trace-generation workflow

`smoke_test/runner.py::run_case` is the whole workflow: resolve the manifest and
corpus, then call the existing, unmodified `review.imported_answer.import_answer` --
the same function the review loop's API (`POST /review/import-answer`) uses. This
smoke test is deliberately not a separate pipeline implementation; it exists to point
the *existing* pipeline at more realistic inputs and capture what happens.

## 6. Manual inspection labels

Four label vocabularies (`core/enums.py`), applied by a human researcher reading a
case's `<case_id>.inspection.json` (auto-generated) and filling in the matching
`<case_id>.labels_template.json` (also auto-generated, with `None`/empty slots and an
`allowed_values` block listing every valid label) -- never computed automatically.
Every label in every one of these four vocabularies is a **diagnostic label about this
pipeline's own behavior** (did retrieval find it, did linking connect it correctly, is
the extracted span faithful, is the interface usable) -- **never a factual-truth label
about the underlying document's content**. A `spurious_support_link` says the linker
made a bad connection; it says nothing about whether the claim itself is true.

- `RetrievalDiagnosticLabel` (§8): `evidence_candidate_found`, `evidence_candidate_missed`,
  `candidate_too_broad`, `candidate_too_narrow`, `candidate_query_related_non_supporting`,
  `evidence_source_version_mismatch`, `unresolved`.
- `ClaimLinkingDiagnosticLabel` (§7): `useful_support_link`, `spurious_support_link`,
  `missed_support_link`, `claim_split_problem`, `claim_too_broad`, `claim_too_narrow`,
  `unresolved`.
- `PropositionProvenanceDiagnosticLabel` (§9): `source_span_valid`, `source_span_invalid`,
  `proposition_independently_interpretable`, `proposition_requires_dependency`,
  `dependency_available`, `dependency_missing`, `extraction_uncertain`.
- `ReviewInterfaceDiagnosticLabel` (§10): `evidence_easy_to_locate`,
  `risk_explanation_understandable`, `full_context_sufficient`,
  `omitted_competing_evidence_visible`, `reviewer_action_clear`, `unnecessary_alert`,
  `missing_useful_warning`, `unresolved`.

`expected_evidence_location_labels` (in the labels template, keyed by researcher-
annotated location rather than by retrieved item id) is where `evidence_candidate_missed`
is actually recorded -- a missed location has no retrieved candidate to attach a label
to, so it needs its own slot distinct from `retrieval_candidate_labels` (which is keyed
only by candidates that *were* retrieved).

## 7. Claim-linking assessment

For each `AnswerSupportEdge`, a researcher reads the claim text, the packed items
`context_item_ids` points at, and `link_scores[claim_id]` (every packed item's overlap
score and negation flags, `review/claim_linking.py::CandidateScore` -- not just the
winner) from the inspection report, then applies a `ClaimLinkingDiagnosticLabel`.
`smoke-003-unsupported-fabricated` in the bundled example set is a demonstrated
instance worth specifically checking: a fully fabricated claim can still score
`partial_support_candidate` from topical lexical overlap alone -- this is exactly the
kind of case this label set exists to catch (likely `spurious_support_link`).

## 8. Retrieval assessment

For each retrieved candidate (`retrieval_candidates` in the inspection report), a
researcher checks it against `expected_evidence_locations` (where independently
available) and the query, then applies a `RetrievalDiagnosticLabel`. Because BM25 is
lexical, `evidence_candidate_missed` (a real, relevant passage that never appeared in
`retrieval_candidates` at all) is the single most important signal for §11 below --
distinct from a candidate that was retrieved but ranked low or excluded from packing.

## 9. Proposition/provenance assessment

For each packed item, a researcher checks that its Tier-0 span (`excerpt`,
`source_document_id`, `segment_id`) is a faithful, independently-checkable quotation of
the source (not a parsing artifact -- e.g. a table row rendered without its header
context) and that any Tier-2 annotation cue attached to text derived from it
(`segment_boundary_dependency_flags` in the trace) is actually relevant, then applies a
`PropositionProvenanceDiagnosticLabel`.

## 10. Review-interface assessment

Working through `frontend/public/review.html` against a real case's inspection report
(or the live API response for that case), a researcher checks whether the risk-event
language, evidence navigation, and reviewer-action set were adequate for a real
document, then applies a `ReviewInterfaceDiagnosticLabel`. This is the one assessment
this milestone does not automate any output for beyond the case itself being loadable
into the review screen -- see `docs/review-loop-demo.md` for the walkthrough this
reuses.

## 11. How to decide whether dense retrieval is the next priority

**Dense retrieval is never implemented automatically from this smoke test's output.**
`wittgenstein smoke-test report` (§13) only ever surfaces raw signal counts
(`bottleneck_signals` in `report.json`) -- it never itself declares a bottleneck
dominant or asserts that dense retrieval is justified. That judgment is made by a
human, working through the classification below against the counts in the report.

After labeling every case, classify the dominant bottleneck as one or more of:

- **A. Retrieval recall bottleneck** -- relevant evidence is absent from lexical
  candidates entirely (`missed_evidence_count` / `evidence_candidate_missed`, §8),
  while claim splitting, provenance, and support linking are otherwise adequate.
- **B. Claim-linking bottleneck** -- relevant evidence *is* retrieved
  (`evidence_candidate_found`), but lexical linking fails or creates excessive
  spurious links (`spurious_link_count`/`missed_support_link`, §7).
- **C. Proposition bottleneck** -- source segmentation or proposition extraction is
  inadequate (`provenance_failures`, §9, or `claim_split_problem`, §7).
- **D. Context/packing bottleneck** -- evidence is retrieved but omitted, poorly
  ordered, or difficult to inspect (`omitted_context_items` counts, computed
  automatically, no manual labeling required).
- **E. Review-interface bottleneck** -- evidence and risks exist but are difficult for
  a reviewer to understand or navigate (`unnecessary_alert`/`missing_useful_warning`/
  `unresolved` review-interface labels, §10).

**Only prioritize dense retrieval next if the pilot shows a material A-type
bottleneck.** If B, C, D, or E dominates instead, improve that layer first -- dense
retrieval cannot fix a linking, extraction, packing, or interface problem, and adding
it while one of those dominates would not address the pilot's actual finding.

Record the decision and its basis in `docs/real-trace-smoke-test-results.md`
("Dense-retrieval priority decision") rather than deciding from impression alone.

## 12. Summary metrics (never one score)

`wittgenstein smoke-test report --output-dir <path>` (`smoke_test/report.py::generate_report`)
aggregates a completed run's inspection reports and filled-in labels templates into
`report.json`, reporting -- as separate counts, each with per-case examples and a
`labeled_count`/`total_count` denominator, never collapsed into one score -- case
count, corpus/document profile, retrieval candidate usefulness, missed-evidence count,
claim-linking usefulness, spurious-link count, answer-claim split problems, provenance
failures, risk-event usefulness, review-interface problems, processing latency, and
LLM calls/cache hits. The report also always carries three fixed caveats verbatim
(non-factual-truth, non-statistical-generalization, "0 may mean unlabeled") so the
artifact itself, not just this doc, states its own limits.

It also reports `evidence_set_summary` (`docs/multi-passage-evidence-plan.md`): claims
evaluated, attempted-vs-skipped counts and why (most skips are the correct,
single-passage-preferred outcome, not a problem), composite relationship-status
counts, mean candidate-pool size, and mean construction latency -- computed
automatically from `evidence_sets`/`evidence_set_metrics`, never requiring manual
labeling, the same way `automatic_relationship_rates` is.

## 13. What this smoke test does not establish

- **Not a factual ground-truth benchmark.** `expected_evidence_locations` is a
  researcher annotation used to diagnose this system's behavior, not an independently
  verified, universal statement of what is factually correct in the source documents.
- **Not statistically powered.** A handful of pilot cases can reveal that a failure
  mode exists; it cannot establish its true rate, a confidence interval, or that a
  failure mode is absent because it didn't appear in this small a sample.
- **Not the human-subjects study.** `docs/local-validation-protocol.md`'s reviewer
  study (real reviewers, review conditions, the six outcome layers) is separate,
  larger, and not run or replaced by this smoke test -- this harness produces
  artifacts a researcher reads alone, not a study with real reviewer subjects.
- **Not a claim about any specific real document's content.** Every claim this plan
  doc or its results template makes about the *bundled* corpus concerns the fictional
  widget-certification fixture only; this smoke test makes no factual claim about any
  real-world regulatory, legal, or clinical material, whether or not a user later adds
  real documents locally.
- **Not evidence for or against promoting any registry mechanism.** Nothing here
  changes, or is intended to support changing, any `EpistemicStatus`,
  `ActivationPolicy`, or validator threshold -- that remains governed exclusively by
  `docs/registry-governance.md` and the literature-review/local-validation processes.
