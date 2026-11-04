# EU AI Act pilot execution plan

The first real-corpus diagnostic pilot, following
`docs/real-corpus-diagnostic-runbook.md` and `docs/real-corpus-case-authoring-guide.md`
exactly, against the `eu-ai-act-2024` corpus slice recommended first in
`docs/corpus-selection-rationale.md`. This document is the plan; see
`docs/eu-ai-act-pilot-run-summary.md` for what actually happened and
`docs/eu-ai-act-pilot-annotation-checklist.md` for the human annotation tasks that
remain.

**No raw source text is reproduced in this document or in
`docs/eu-ai-act-pilot-run-summary.md`** -- both are committed, and per
`docs/real-corpus-diagnostic-runbook.md`'s content-safety note, only the gitignored
`local_corpora/` directory may hold source excerpts. Findings below are described
structurally (which article, what kind of clause) rather than by quotation.

## Source handling

1. Checked whether `data/examples/evidence_set_diagnostics/local_corpora/eu-ai-act-2024/`
   already existed -- it did not (only the corpus's top-level, non-local `README.md`
   sibling directory existed, per the prior onboarding milestone).
2. Attempted retrieval of the official EUR-Lex text via this session's available
   `WebFetch` tool. A direct HTML/PDF-summarization fetch could not reliably return
   full verbatim article text (the source page is long enough that a fetch is
   truncated or the tool's summarization step declines to quote at length) --
   however, fetching the official PDF URL directly caused the tool to save the actual
   PDF binary locally, which was then read page-by-page with the file-reading tool's
   PDF-page-extraction mode (not the summarization path) to obtain exact page images,
   transcribed verbatim into local `.txt` files. No summarization model was used for
   the transcribed article text itself -- every quoted sentence was copied from a
   directly rendered page image of the official PDF.
3. This is the "environment can obtain the official text" branch of the runbook's
   source-handling contingency (step 3.2) -- the text was retrieved and stored
   locally, never committed.

## Corpus slice

The smallest workable slice, per the runbook's "Prefer" list plus the two additional
provisions genuinely needed to interpret the selected sections and support the
cross-reference case:

| Document ID | Content |
|---|---|
| `article-3-definitions-selected` | 9 of Article 3's 68 definitions -- only the terms Articles 6/13/49/50/113 actually use (AI system, provider, deployer, placing on the market, making available on the market, putting into service, emotion recognition system, biometric categorisation system, deep fake) |
| `article-6-classification` | Article 6, complete (8 paragraphs) |
| `article-13-transparency-deployers` | Article 13, complete (3 paragraphs, all sub-points) |
| `article-49-registration` | Article 49, complete (5 paragraphs) -- included only because Article 6(4) explicitly cross-references Article 49(2) |
| `article-50-transparency-obligations` | Article 50, complete (7 paragraphs) |
| `article-113-entry-into-force` | Article 113, complete (signature block omitted as non-substantive) |

The full Act (144 pages) was not ingested -- six documents, none longer than one
article, were extracted and stored as separate small files under
`local_corpora/eu-ai-act-2024/` (one `.txt` file per document, `document_id` = file
stem, per the runbook's supported local-corpus layout).

## Provenance recorded

`local_corpora/eu-ai-act-2024/metadata.json` (gitignored, local only) records, per
document: source title, official source URL, publisher, document version/effective-
date notes, access date, retrieval method, license/public-access basis, extraction
notes, and the exact selected range. Each document's SHA-256 hash (via
`ingestion.content_hash.content_hash`, the runbook's exact command) is recorded there
and duplicated into each case's `CorpusReference.document_hashes`.

## Six planned cases

Following the six required categories exactly, each mapped to a document (or pair of
documents) that genuinely supports it -- no case was authored where the retrieved
slice didn't directly support the category:

| # | Category | Case ID | Evidence |
|---|---|---|---|
| 1 | Direct single-provision support | `euaia-001-direct-single-provision-transparency` | Article 50(1) alone |
| 2 | Definition plus obligation | `euaia-002-definition-plus-obligation-deployer` | Article 3(4) + Article 13(1) |
| 3 | Explicit cross-reference | `euaia-003-explicit-cross-reference-registration` | Article 6(4) (references Article 49(2)) + Article 49(2) |
| 4 | Conditional applicability/scope | `euaia-004-conditional-applicability-annex-iii` | Article 6(3) alone |
| 5 | Temporal applicability | `euaia-005-temporal-applicability-entry-into-force` | Article 113 alone |
| 6 | Same-topic non-supporting evidence (controlled perturbation) | `euaia-006-controlled-perturbation-transparency-overclaim` | Article 50(1) (topically relevant, does not support the perturbed claim) |

No planned category was omitted -- all six were directly supported by the selected
slice, so no "missing case category" note is needed for this pilot (contrast with the
runbook's "document the missing case category instead" instruction, which did not
apply here).

## Planned execution steps

1. Validate the manifest (`wittgenstein manifest validate`).
2. Validate the six cases against `SmokeTestCaseFile` (the implemented diagnostic
   case format, reused unchanged).
3. Run `wittgenstein evidence-set diagnose` (default `max_set_size=2`).
4. Inspect each case's `evidence_set_metrics`/`evidence_sets` for uncovered critical
   components; re-run with `--diagnostic-max-set-size 3` only for claims where that
   applies (per the runbook's step 7 rule), or for the whole case set in one pass if
   every case qualifies (the size-3 diagnostic is a no-op, by design, for any claim
   that does not need it -- see `docs/evidence-set-real-corpus-diagnostics-plan.md` §9).
5. Run `wittgenstein evidence-set report`.
6. Read every generated `<case_id>.diagnostic_labels.json` to confirm all human-
   judgment label slots are `null` (never prefilled) and only deterministic/system
   fields (`case_id`, `allowed_values`) are populated.
7. Write `docs/eu-ai-act-pilot-run-summary.md` from the actual generated artifacts,
   and `docs/eu-ai-act-pilot-annotation-checklist.md` listing exactly what a human
   annotator must do next.

## What this plan does not authorize

Per the milestone's explicit constraints: no change to the corpus-onboarding
materials, templates, runbook, case-authoring guide, corpus catalog, diagnostic
harness, registry, schemas, retrieval pipeline, claim linker, evidence-set
constructor, or activation policies -- unless a small bug actually prevents the pilot
from running (none did; see the run summary for a documented *finding*, not a bug,
about cross-reference detection on "Article N" citations).
