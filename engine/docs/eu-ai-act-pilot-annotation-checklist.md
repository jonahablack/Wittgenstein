# EU AI Act pilot annotation checklist

What a human annotator must do next to finish this pilot, following
`data/examples/evidence_set_diagnostics/annotation-guide.md`'s label definitions and
process. Nothing below has been done yet -- every label slot in every file listed here
is currently `null` (`docs/eu-ai-act-pilot-run-summary.md`, "Files requiring human
annotation").

**Reminder throughout**: every label is a diagnostic judgment about this pipeline's
behavior, never a legal conclusion, and never inferred automatically -- see the
annotation guide's "What these labels are -- and are not."

## Files to open

**Updated after `docs/eu-ai-act-article-cross-reference-fix-plan.md`**: label against
the post-fix run, `output-after-article-xref/`, not the original `output/` directory
(the two are identical outside cross-reference detection -- see
`docs/eu-ai-act-article-cross-reference-run-summary.md` for exactly what changed and
why post-fix is the more complete/accurate basis for category C labels specifically).

All six, under
`data/examples/evidence_set_diagnostics/local_corpora/eu-ai-act-2024/output-after-article-xref/`
(gitignored -- read them locally, do not attempt to commit them):

1. `euaia-001-direct-single-provision-transparency.diagnostic.json` +
   `.diagnostic_labels.json`
2. `euaia-002-definition-plus-obligation-deployer.diagnostic.json` +
   `.diagnostic_labels.json`
3. `euaia-003-explicit-cross-reference-registration.diagnostic.json` +
   `.diagnostic_labels.json`
4. `euaia-004-conditional-applicability-annex-iii.diagnostic.json` +
   `.diagnostic_labels.json`
5. `euaia-005-temporal-applicability-entry-into-force.diagnostic.json` +
   `.diagnostic_labels.json`
6. `euaia-006-controlled-perturbation-transparency-overclaim.diagnostic.json` +
   `.diagnostic_labels.json`

Plus the aggregate `output/diagnostic_report.json` (safe to read alongside; contains
no raw source excerpts).

## Category A: extraction quality (116 field comparisons across 6 cases)

Follow the annotation guide's process steps 1-4. Priority cases to inspect first
(most likely to show something worth labeling, per the run summary):

- Case 4 and case 5's finely split claim fragments -- read each fragment's own
  `claim_evidence_comparisons` entries and judge whether the answer-claim splitter
  produced a sensible fragment, or an `extraction_artifact`/`source_span_incomplete`.
- Case 3's `Article 49(2)` / `Article 6(4)` references, and case 5's "Chapter III
  Section 4" reference -- these did **not** get detected as cross-reference markers
  at all (see below); while filling in category A, note whether the CONDITION/
  cross-reference extraction on these specific sentences looks like a genuine
  `extraction_artifact` or just an expected consequence of the "Article" vs
  "Section/Table/..." prefix gap.

## Category B: conflict quality (1 conflict, case 4)

One `composite_conflict_candidate` on the `entity` field between two Article 6
sub-passages, confidence 0.55. Read `conflict_explanations["EVSET-..."]` in case 4's
diagnostic report (member spans, extraction method) and judge: `genuine_source_conflict`,
`evidence_set_member_conflict_justified`, `apparent_conflict_caused_by_extraction_artifact`,
or another category-B label. This is the single highest-value label in this pilot --
it directly informs decision rule B.

Also assign a category B label for case 6's outcome even though no
`composite_conflict_candidate`/`contradiction_candidate` was produced: judge whether
the system's `unresolved` result for the controlled-perturbation claim should have
been a contradiction instead (`conflict_unresolved`, or a note that a conflict was
plausibly missed -- there is no single perfect label for "should have conflicted but
didn't"; use `conflict_unresolved` and say so explicitly in the notes field).

## Category C: cross-reference and definition closure

**Updated after `docs/eu-ai-act-article-cross-reference-fix-plan.md`.** The original
pilot (`output-baseline-before-article-xref/`) detected only 1 marker in this entire
pilot (case 5, "Section 4", state `unknown`) -- "Article N"/"Annex N" citations were
not detected at all. The post-fix run (`output-after-article-xref/`) detects 9 markers
across cases 3, 4, and 5 -- see
`docs/eu-ai-act-article-cross-reference-run-summary.md` for the full trace-level
comparison. **Label against `output-after-article-xref/`, not the baseline** -- the
baseline's labels file is preserved only as a historical record of what the pre-fix
system produced (still worth a quick look at, per the cross-reference comparison
section below, but not where category C labels should be entered).

## Cross-reference comparison (baseline vs. post-fix) -- see the dedicated protocol

A full, dedicated annotation protocol for the baseline-vs-post-fix cross-reference
comparison now exists and supersedes the inline checklist that used to live here:

- `docs/eu-ai-act-cross-reference-annotation-protocol.md` -- the review order and
  valid outcomes (11 steps; detection/normalization/relevance/reviewer-value
  judgments, explicitly not legal or factual adjudications).
- `docs/eu-ai-act-cross-reference-comparison-template.md` -- the worksheet's field
  format and the empty A/B/C/D summary tables to fill in after annotation.
- `docs/eu-ai-act-cross-reference-annotation-summary.md` -- the initially empty
  results document to copy and complete.
- The machine-generated worksheet itself:
  `local_corpora/eu-ai-act-2024/output-after-article-xref/cross-reference-comparison-worksheet.json`
  (gitignored; regenerate with `wittgenstein evidence-set compare-cross-reference` if
  either output directory changes).

Follow that protocol for every marker in the worksheet rather than the category C
label above in isolation -- it covers the same ground with the full baseline/post-fix
diff already computed for you.

## Category D: evidence-set sizing (14 claim fragments across 5 cases)

For each fragment with a non-`null` `evidence_set_sizing_labels` slot: read its
`size3_diagnostics` entry (uncovered components, `size3_relationship_status`) and
judge `one_item_sufficient` / `composition_unresolved` / etc. Given none of the 14
resolved at size 3 (run summary), most of these are likely `composition_unresolved`
or `missing_evidence_outside_candidate_pool` -- but confirm per-fragment rather than
assuming the pattern holds uniformly.

## Category E: reviewer/workflow value (case-level, all 6 cases)

For each case, after reading its full diagnostic report: would `evidence_set_explanation_useful`,
`conflict_explanation_useful` (case 4 especially), `cross_reference_warning_useful`
(case 5), `extraction_uncertainty_visible`, `likely_false_reassurance`,
`likely_unnecessary_escalation`, or `reviewer_marked_unresolved` apply? Append as many
as apply to each case's `reviewer_workflow_labels` list.

## After labeling

1. Re-run `wittgenstein evidence-set report --output-dir .../output` to regenerate
   `diagnostic_report.json` with real label counts (currently all-zero, since nothing
   is labeled yet).
2. Copy `docs/evidence-set-real-corpus-diagnostics-results.md` to a dated results doc
   and fill it in from the regenerated report plus your own reading, per
   `docs/real-corpus-diagnostic-runbook.md` step 11.
3. Only after that is complete, apply decision rules A-E
   (`docs/evidence-set-real-corpus-diagnostics-plan.md` §10) to judge a dominant
   bottleneck -- not before. Two candidate signals already visible in this
   unlabeled run (worth weighing once real labels exist): the "Article N"
   cross-reference detection gap (rule A vs. rule B: is this a closure problem or an
   extraction-vocabulary problem?), and the case-4 conflict's confidence level (rule
   B). Neither is a conclusion yet -- both need your labels first.

## Second review

Independent second review of these labels is not required for this initial
engineering diagnostic pass, but is advisable before treating any finding here (the
case-4 conflict judgment especially) as input to an implementation-priority decision
(`data/examples/evidence_set_diagnostics/annotation-guide.md`, "Annotation process"
step 10).
