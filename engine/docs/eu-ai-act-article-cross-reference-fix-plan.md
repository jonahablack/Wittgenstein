# EU AI Act article cross-reference detection fix plan

A narrow, backward-compatible extension of `review/cross_reference_diagnostics.py` to
recognize explicit legal citation forms ("Article 6(4)", "Articles 6 and 49", "Annex
III") that `docs/eu-ai-act-pilot-run-summary.md` found were not being detected at all.
Measurement only -- this does not implement legal reasoning, does not resolve
references semantically, and does not change any registry, activation policy,
retrieval, or claim-linking behavior.

## Baseline artifact location

`data/examples/evidence_set_diagnostics/local_corpora/eu-ai-act-2024/output-baseline-before-article-xref/`
(gitignored, local only) -- an exact copy of the pre-fix pilot's `output/` directory
(all 6 `.diagnostic.json` + 6 `.diagnostic_labels.json` + `summary.json`), plus
`manifest.yaml`, `manifests.json`, `cases.json`, and `metadata.json` as they stood at
that run. Never modified after this point. The post-fix re-run
(`docs/eu-ai-act-article-cross-reference-run-summary.md`) writes to a separate
`output-after-article-xref/` directory, never overwriting this baseline.

## Observed parser limitation

`proposition/annotations.py::_CROSS_REFERENCE_RE` (unchanged, unmodified by this fix)
recognizes `Section|Table|Figure|Exemption|Appendix|Clause` as cross-reference marker
prefixes -- built against the bundled widget-certification corpus's citation style.
It does not recognize `Article`, the primary citation form in the EU AI Act and most
EU/international legal texts, so genuine cross-references in the pilot (e.g. Article
6(4)'s reference to Article 49(2)) were never detected as markers at all.

## Design: isolated to the diagnostic layer, not the shared extractor

This fix adds a **second, dedicated legal-citation regex and parser inside
`review/cross_reference_diagnostics.py` only** -- it does not modify
`proposition/annotations.py::_CROSS_REFERENCE_RE` or
`review/field_extraction.py::extract_fields`'s existing `ComparisonFieldName.CROSS_REFERENCE`
field. Reasons:

- **Narrower blast radius.** `_CROSS_REFERENCE_RE` is shared with claim-linking's
  general field-comparison engine (`review/field_comparison.py`'s CROSS_REFERENCE
  field, used in ordinary claim-vs-candidate comparison, not just this diagnostic).
  Changing it risks altering claim-linking classification behavior on any corpus that
  happens to contain the word "Article" -- out of scope for a "narrow,
  backward-compatible... cross-reference-detection improvement" whose explicit purpose
  is diagnostic, not claim-linking.
- **The structured object this task requires (paragraph/point/range/multi-target
  breakdown) has no equivalent in the generic cue-detector**, which only ever produces
  a flat list of matched strings. Building it as a second pass inside the module that
  already owns cross-reference *diagnosis* keeps one coherent structure, rather than
  forcing the generic Tier-2 annotation format to grow legal-citation-specific fields
  it has no other use for.
- `detect_cross_reference_markers` already unions signal from `extract_fields` for the
  existing Section/Table/... forms; this fix adds a second, independent scan of the
  same claim text for Article/Annex forms and merges the results. The two paths cannot
  double-detect the same span ("Article"/"Articles"/"Annex" are not matched by the
  existing regex at all).

## Explicit reference forms to support

1. Singular article: `Article 49`, `Article 6`.
2. Article with paragraph: `Article 6(4)`, `Article 50(2)`.
3. Article with paragraph and point: `Article 6(4), point (a)`.
4. Plural/multiple articles: `Articles 6 and 49`, `Articles 6, 13 and 50`,
   `Articles 6 to 13`, `Articles 6–13` (en dash) / `Articles 6-13` (hyphen).
5. Annex references, structurally simple only: `Annex III`, `Annex IV` (roman
   numerals).
6. Existing non-legal forms (Section/Table/Figure/Exemption/Appendix/Clause) --
   unchanged, still handled by the existing, untouched `_CROSS_REFERENCE_RE` path.

Matching is case-insensitive on the keyword ("article"/"Article"/"ARTICLE" all match)
while the exact original surface form and character span are always preserved
verbatim from the source text -- never normalized in place.

## Normalization format

One `ReferenceTarget` per individual cited article/annex (a plural/range reference
expands to multiple `ReferenceTarget`s, never silently collapsed to the first):

- `target_identifier`: `article:<N>` / `article:<N>:paragraph:<M>` /
  `article:<N>:paragraph:<M>:point:<letter>` / `annex:<roman numeral>`.
- `article_number` / `paragraph_number` / `subdivision_type` (`point` for the given
  examples; `unknown` if a future form adds an unrecognized subdivision keyword) /
  `subdivision_identifier`.

The parent `CrossReferenceMarker` (one per detected citation span, e.g. the whole
"Articles 6, 13 and 50") keeps its existing fields (`marker_text`, `source_span`,
`target_segment_ids`, `target_state` -- all backward compatible, unchanged meaning)
and gains: `reference_type` (`article`/`annex`/`section`/`table`/`figure`/
`exemption`/`appendix`/`clause` -- the last six always `"section"`-family values for
markers detected via the pre-existing path, for uniformity), `range_start`/
`range_end` (only for an explicit "to"/en-dash/hyphen range), `target_identifier`
(populated only when the marker has exactly one target -- `None` when plural/range),
`targets` (the full list of one or more `ReferenceTarget`s -- always populated),
`extraction_method` (`"regex"`), `extraction_confidence` (`1.0` for an exact
structural match against one of the supported forms above -- this is a statement about
match confidence in the citation *pattern*, never a claim about the target's legal
relevance).

## Target-resolution behavior

Deterministic and local only. A `ReferenceTarget` resolves against the locally parsed
`CorpusIndex` two ways, unioned:

1. **Location-text match** (existing, unchanged): the target's surface tokens as a
   case-insensitive substring of a segment's `location`.
2. **Document-id structural match** (new, additive): `source_document_id` tokens
   (split on `-`) whose first two tokens equal `("article", "<N>")` or
   `("annex", "<roman numeral>")` -- i.e. a corpus that names one file per article
   (exactly this pilot's `local_corpora/eu-ai-act-2024/article-<N>-<slug>.txt`
   convention) resolves at the whole-document level. This is a structural match on an
   explicit identifier already present in the corpus (the filename-derived
   `source_document_id`), never a semantic-similarity guess -- a corpus that does not
   follow this naming convention simply finds nothing via this path and falls back to
   location matching or `unknown`.

Paragraph/point-level `ReferenceTarget`s resolve at the same document granularity as
their parent article (this codebase's deterministic parser does not produce
legal-paragraph-numbered segments for plain-text documents, so claiming
paragraph-level segment resolution would overstate what is structurally known --
`paragraph_number`/`subdivision_identifier` are preserved on the `ReferenceTarget` for
a human to use, never used to narrow which segment is considered the target).

When no segment matches by either method: `target_state = unknown`. The existing six
states (`in_corpus`/`retrieved`/`selected`/`packed`/`omitted`/`unknown`) and the
existing fixed, bounded warning template are unchanged.

## Uncertainty behavior

Never silently resolved. An ambiguous document-id match (more than one document's
first two tokens equal the target) is treated as **no match** (falls through to
`unknown`) rather than picking one -- ambiguity is not resolution.
`extraction_confidence` on a `ReferenceTarget` is about the *citation pattern* match
only; it is never conflated with, or used to infer, whether the target is legally
necessary, controlling, or relevant to the answer (see "What this fix does not
establish").

## Tests

22 categories per the milestone brief, in
`tests/unit/test_article_cross_reference_detection.py` (new) plus additions to
`tests/unit/test_cross_reference_diagnostics.py` and
`tests/integration/test_evidence_set_diagnostics_harness.py` where a pre-existing
file already owns that behavior (e.g. "existing widget behavior unchanged",
"deterministic diagnostics").

## How the post-fix run stays distinguishable from the baseline

Separate output directory (`output-after-article-xref/`, never overwriting
`output-baseline-before-article-xref/`), a separate summary document
(`docs/eu-ai-act-article-cross-reference-run-summary.md`) that only ever compares the
two directories' contents (never edits the baseline in place), and this plan doc
itself, committed, recording the baseline's location and exact contents (by file name
and count, never by reproducing source text) so the comparison is auditable without
re-running anything.

## What this fix does not establish

- Whether a detected reference is legally necessary, controlling, or correctly
  resolved as a matter of law -- purely a trace-observable "a citation pattern
  matched, and here is where the corresponding local file/segment is, if any."
- Improved review outcomes, factual accuracy, or human-review effectiveness --
  detecting more cross-references is not evaluated here at all; that is exactly what
  the (still entirely unfilled) annotation labels are for.
- A recommendation to implement semantic reference resolution, closure, or any other
  next feature.

## Reference forms intentionally out of scope (documented, left unresolved)

Implicit references ("the preceding Article"); references requiring legal-document
hierarchy interpretation; references to external legislation not in the local corpus;
amendment chains; corrigenda; citations whose target cannot be structurally
identified; whether a cited provision is legally *necessary* rather than merely
present; semantic dependency closure; cross-jurisdiction equivalence. Every one of
these, if encountered, falls through to `target_state = unknown` -- never a guess.
