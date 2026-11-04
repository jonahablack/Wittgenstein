# Real-corpus diagnostic runbook

A step-by-step workflow, with exact commands, for running
`docs/evidence-set-real-corpus-diagnostics-plan.md`'s diagnostic pass against real,
licensed, or public documents. This document is the workflow; see
`docs/real-corpus-case-authoring-guide.md` for how to write a good case, and
`data/examples/evidence_set_diagnostics/annotation-guide.md` for how to label what the
pass produces.

**Scope note.** The materials in this pass are used to test *software behavior* --
extraction, comparison, composition, cross-reference detection -- never to produce or
validate a real clinical or legal conclusion. Real clinical or legal decision-making is
out of scope for this diagnostic pass. If a document happens to be a medical or legal
guideline, this pass never adjudicates what it actually requires; it only measures
whether this pipeline reads and links it well.

## 0. Prerequisites

```bash
uv sync --extra dev
uv run wittgenstein --help   # confirms the CLI is installed
```

No LLM credentials are needed or used anywhere in this workflow.

## 1. Select appropriately licensed or public documents

Choose documents you have a clear right to process locally for this purpose:
material you own, material under a permissive license (CC-BY, CC0, public domain,
government-work-in-the-public-domain), or material you have explicit permission to
use. When in doubt, don't use it. See "Corpus guidance" below for two recommended
document *shapes* (not sources) to look for.

## 2. Record source provenance

For each document, before anything else, record (in your own notes, and later in a
case -- `docs/real-corpus-case-authoring-guide.md`):

- **Source title**
- **Source URL** (or `null` if not URL-accessible, e.g. a PDF you were given directly)
- **License or public-access basis** (e.g. `"CC-BY-4.0"`, `"public domain (US federal
  government work)"`, `"user-owned, license confirmed 2026-01-15"`)
- **Access date** (the date you obtained/downloaded it, `YYYY-MM-DD`)
- **Version / effective date** (the document's own stated version or effective date,
  if any -- e.g. "Rev. 3, effective 2024-03-01"; `null` if the document does not state
  one)
- **Document hash**, computed once the plain-text content is finalized:

```bash
uv run python -c "from wittgenstein.ingestion.content_hash import content_hash; print(content_hash(open('path/to/doc.txt').read()))"
```

- **Local storage path** -- where you are about to put it (step 3).

## 3. Store raw documents under the gitignored `local_corpora/` directory

```bash
mkdir -p data/examples/evidence_set_diagnostics/local_corpora/<your-corpus-id>
```

Two supported layouts (`smoke_test/corpus_registry.py::resolve_corpus`, reused
unchanged by the evidence-set diagnostic harness):

- **One plain-text file per document**: drop `.txt`/`.md` files directly in
  `local_corpora/<your-corpus-id>/`; each file's name (without extension) becomes its
  `document_id`.
- **One JSON file for the whole corpus**: `local_corpora/<your-corpus-id>.json`, a flat
  `{"document_id": "plain text...", ...}` object.

This directory is already gitignored (see `.gitignore`,
`/data/examples/evidence_set_diagnostics/local_corpora/`) -- nothing placed here is
committed. Verify it if you're ever unsure:

```bash
git check-ignore -v data/examples/evidence_set_diagnostics/local_corpora/<your-corpus-id>
```

A non-empty output line means the path is correctly excluded.

## 4. Create a corpus manifest

Copy the template and fill it in:

```bash
cp data/examples/evidence_set_diagnostics/manifest-template.yaml /tmp/my-manifest.yaml
# edit /tmp/my-manifest.yaml
uv run wittgenstein manifest validate /tmp/my-manifest.yaml
```

The diagnostic harness loads manifests from a `{manifest_id: PipelineManifest}` JSON
registry (`smoke_test/manifest_registry.py::load_manifests`, reused unchanged -- not a
per-file loader), so once your YAML manifest validates, add it as one entry to your own
copy of the manifests registry:

```bash
cp data/examples/evidence_set_diagnostics/manifests.json /tmp/my-manifests.json
uv run python -c "
import json, yaml
manifest = yaml.safe_load(open('/tmp/my-manifest.yaml'))
registry = json.load(open('/tmp/my-manifests.json'))
registry[manifest['manifest_id']] = manifest
json.dump(registry, open('/tmp/my-manifests.json', 'w'), indent=2)
"
```

(`/tmp/my-manifests.json` must sit in the same directory as your cases file -- the
harness looks for `manifests.json` next to `cases.json` -- so in practice, place both
under a local, gitignored working directory, e.g.
`data/examples/evidence_set_diagnostics/local_corpora/<your-corpus-id>-cases/`.)

## 5. Create diagnostic cases

For each case: copy `data/examples/evidence_set_diagnostics/case-template.json`, fill
it in following `docs/real-corpus-case-authoring-guide.md`, then convert it into an
entry in a `cases.json` file (`schemas/smoke_test.py::SmokeTestCaseFile` shape --
reused unchanged; the case-authoring guide gives the exact field mapping). See
"Case sampling" below for how many cases and what mix to aim for.

Validate your cases file parses correctly before running anything:

```bash
uv run python -c "
import json
from wittgenstein.schemas.smoke_test import SmokeTestCaseFile
SmokeTestCaseFile.model_validate(json.load(open('path/to/cases.json')))
print('OK')
"
```

## 6. Run the diagnostic harness

```bash
uv run wittgenstein evidence-set diagnose \
  --cases path/to/cases.json \
  --output-dir path/to/output
```

`path/to/output` should itself be a path *outside* version control (e.g. under
`local_corpora/`, or anywhere not tracked by git) -- see the note in step 8 about why
per-case diagnostic reports must never be committed for a restricted corpus.

This is always no-LLM and deterministic (`docs/multi-passage-evidence-plan.md`,
`docs/efficiency-and-processing-architecture.md` §7) -- no network calls, no
credentials read.

## 7. Optionally run the bounded size-3 diagnostic

```bash
uv run wittgenstein evidence-set diagnose \
  --cases path/to/cases.json \
  --output-dir path/to/output \
  --diagnostic-max-set-size 3
```

Only ever adds a diagnostic-only, explicitly bounded (`C(pool, 3) <= 500`) search on
top of the same default `max_set_size=2` construction -- it never changes what
`import_answer` itself builds (`docs/evidence-set-real-corpus-diagnostics-plan.md` §9).
Use this once you have a case you suspect needs a third passage (category 16 below).

## 8. Review the generated artifacts

For each case, `path/to/output/<case_id>.diagnostic.json` contains:

- **Field comparisons** (`claim_evidence_comparisons`) -- every (claim, candidate)
  field-by-field vector, with source spans, extraction methods, confidence.
- **Evidence sets** (`evidence_sets`) -- every proposed multi-passage composition, its
  `relationship_status`, covered/unresolved/redundant components, and conflicts.
- **Cross-reference target states** (`cross_reference_markers`) -- per detected
  marker, its resolved state and (if not `packed`) the fixed warning text.
- **Conflict-driver explanations** (`conflict_explanations`) -- per conflict, which
  fields/members conflict, their spans/confidence, and whether the conflict rests on a
  low-confidence field.
- **Processing metrics** (`evidence_set_metrics`, `llm_call_count`,
  `processing_time_seconds`).

`path/to/output/<case_id>.diagnostic_labels.json` is the empty label scaffold for step
9. `path/to/output/summary.json` is a one-line-per-case run index.

**Content-safety note**: `<case_id>.diagnostic.json` embeds raw excerpt text from your
source documents (`packed_context_items[].excerpt`, etc.) -- for a restricted/licensed
corpus, this file must stay under your gitignored output directory and must never be
copied into `data/examples/evidence_set_diagnostics/results/` (see that directory's
README) or committed anywhere.

## 9. Fill in manual labels

Open each `<case_id>.diagnostic_labels.json` and fill in every label slot using
*only* the values listed in its own `allowed_values` block --
`data/examples/evidence_set_diagnostics/annotation-guide.md` defines every label with
examples. Leave a slot `null` rather than guessing if you are genuinely unsure; write
your reasoning in the corresponding rationale/notes field either way.

## 10. Generate an aggregate report

```bash
uv run wittgenstein evidence-set report --output-dir path/to/output
```

Writes `path/to/output/diagnostic_report.json` -- counts and rates only, computed from
whatever labels you filled in. **It never recommends a next implementation priority**
(`docs/evidence-set-real-corpus-diagnostics-plan.md` §10) -- that classification is
yours to make in step 11, after reading the aggregate.

`diagnostic_report.json` itself contains no raw source excerpts (only label
tallies/counts/rates), so unlike the per-case `.diagnostic.json` files, it is safe to
copy into `data/examples/evidence_set_diagnostics/results/` if you want to keep it.

## 11. Complete the results document

```bash
cp docs/evidence-set-real-corpus-diagnostics-results.md \
   docs/evidence-set-real-corpus-diagnostics-results-$(date +%Y-%m-%d).md
```

Fill in every section from `diagnostic_report.json` and your own case-by-case reading
-- never from memory. Section 12 ("Proposed next implementation priority") is filled
in only after every other section is complete, using the decision rules restated in
`docs/evidence-set-real-corpus-diagnostics-plan.md` §10 -- see also
"Next-priority decision rule" below.

## 12. Keep these four things distinct throughout

Every step above produces one of four *different* kinds of statement. Conflating any
two of them is the single most important thing this runbook asks you not to do:

1. **Diagnostic observation** -- what the software computed (a field comparison, a
   `relationship_status`, a `CrossReferenceTargetState`, a metric). Automatic, never
   requires a human, never itself a judgment about correctness.
2. **Reviewer annotation** -- a human's label from the five vocabularies in
   `data/examples/evidence_set_diagnostics/annotation-guide.md`, describing *this
   pipeline's* behavior (extraction quality, conflict quality, closure completeness,
   sizing adequacy, workflow value). Still not a claim about the real world.
3. **Factual/domain adjudication** -- a claim about what the source document actually
   says or requires. This diagnostic pass does not perform this, does not require it,
   and explicitly stays out of it for clinical/legal material (see the scope note
   above). If a case's answer is contested or version-dependent, use `unresolved` --
   never force a factual call to complete a label.
4. **Implementation-priority recommendation** -- a judgment about what to build next in
   this codebase, made only in step 11 after real diagnostics have been run and
   labeled, using the decision rules below. Never made automatically by any command in
   this runbook.

## Corpus guidance

Two initial corpus slices are recommended -- not as sources, as document *shapes*:

**A. Structured guidance/policy-like documents.** Look for: section hierarchy,
conditions, exceptions, recommendations or requirements, thresholds, tables or lists,
version/effective-date information. (Public standards documents, style guides,
internal-process handbooks you're permitted to use, public product documentation.)

**B. Policy/regulatory-like documents.** Look for: definitions, cross-references,
scope clauses, exceptions, authority/jurisdiction distinctions, temporal applicability,
versioning. (Public regulations, municipal codes, public-domain government guidance,
open-license terms-of-service-style documents.)

Both slices deliberately mirror the structural features
`docs/multi-passage-evidence-plan.md` and `docs/cross-reference-diagnostic-spec.md`
were built to handle -- the point is to stress those features on real prose, not to
adjudicate the documents' subject matter.

**Three concrete corpus slices are now catalogued** --
`data/examples/evidence_set_diagnostics/corpus-catalog.yaml`,
`docs/corpus-selection-rationale.md`, and each corpus's own
`data/examples/evidence_set_diagnostics/<corpus_id>/README.md`
(`eu-ai-act-2024`, `hipaa-privacy-rule`, `ada-standards-2026`) give the exact
official source URLs, initial slice, required local metadata, and
research-only/non-advice warning for each. Use these three as your starting point
rather than sourcing a fourth document shape from scratch, unless none of them fit
what you're trying to diagnose.

## Recommended corpus order

1. **Start with the `eu-ai-act-2024` slice.** It is the primary corpus -- modern,
   heavily cross-referenced, and the closest structural match to this pipeline's own
   field vocabulary (see `docs/corpus-selection-rationale.md`).
2. **Add the `hipaa-privacy-rule` slice.** A different drafting convention and a
   public-domain source, once the first slice's workflow is working end to end.
3. **Add the `ada-standards-2026` slice only after confirming access/licensing and
   safe research-only labeling.** This corpus is copyrighted clinical guidance, not a
   public regulatory text -- do not add it until you have confirmed and documented a
   specific use basis (see its README's §5).
4. **Run a 6-8 case pilot** (`data/examples/evidence_set_diagnostics/case-sets/README.md`)
   before committing to the full case set.
5. **Review diagnostics and annotation usability** on that pilot -- is the labels
   template actually fillable, are the diagnostic reports actually readable, before
   investing in more cases.
6. **Expand to 12-20 cases only if the pilot workflow is usable.** Expanding a
   workflow that's already awkward at 6-8 cases just produces more unusable output.
7. **Use `--diagnostic-max-set-size 3` only on selected cases** with uncovered
   critical components or an explicit third-source dependency (category 16 in the
   table below) -- never as a blanket setting across the whole case set.

## Case sampling

- **12-20 cases total**, roughly balanced across slices A and B.
- **3-5 documents or document sections per slice** -- enough structural variety
  without becoming a large corpus.
- Not statistically powered -- select for *structural diversity*, not answer
  difficulty alone.
- Selected deliberately to exercise the 18 categories below; a first 12-case pilot
  need not cover all 18 -- **record which categories are absent, explicitly**, in the
  results doc's coverage section, rather than silently omitting them.

| # | Category |
|---|---|
| 1 | Direct single-span support |
| 2 | Multi-claim answer |
| 3 | Two-passage complementary support |
| 4 | Rule plus condition |
| 5 | Rule plus exception |
| 6 | Definition plus requirement |
| 7 | Cross-reference target available and packed |
| 8 | Cross-reference target available but omitted/unretrieved |
| 9 | Version/date-sensitive answer |
| 10 | Numeric threshold, unit, or frequency |
| 11 | Same-topic non-supporting passage |
| 12 | Multiple potentially conflicting passages |
| 13 | Long sentence with nested qualification |
| 14 | Underspecified user intent |
| 15 | Evidence likely outside the lexical candidate pool |
| 16 | Case where three evidence items may be required |
| 17 | Case where full-document/section context makes segmentation concern inapplicable |
| 18 | Case where the correct reviewer outcome is unresolved or escalation |

## Next-priority decision rule (restated, not modified)

From `docs/evidence-set-real-corpus-diagnostics-plan.md` §10 -- unchanged here:

- **A. Cross-reference/definition closure** -- prioritize only if unresolved/
  reviewer-important cases commonly need identifiable targets available in the corpus
  but absent from the packed evidence set.
- **B. Extraction reliability** -- prioritize only if conflict/qualification outcomes
  are commonly driven by artifacts, low-confidence extraction, parser disagreement, or
  invalid spans.
- **C. Adaptive evidence-set size** -- prioritize only if reviewer-important cases
  commonly need a third complementary item and bounded size-3 diagnostics indicate
  feasible cost.
- **D. Retrieval** -- prioritize dense/hybrid retrieval only if necessary evidence is
  repeatedly absent from lexical candidate pools (not merely absent from the size-2
  set).
- **E. Review interface** -- prioritize UI work only if trace/evidence diagnostics are
  valid but users cannot understand, navigate, or act on them.

**Do not apply this rule until real cases have been run and manually annotated.** No
command in this repository applies it automatically.
