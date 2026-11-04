# Asteria corpus authoring guide

How to add a new document or case to `data/fixtures/asteria_manual/` without breaking
the fixture-integrity validator or the existing 10 cases. See
`docs/controlled-synthetic-corpus-plan.md` for the full plan and
`docs/controlled-corpus-coverage-matrix.md` for what already exists.

## Fictional-domain rule

Every new document, entity, threshold, and rule must be invented for this corpus. Never
copy wording, thresholds, or structure from a real regulation, standard, product
manual, or clinical guideline -- not even paraphrased. Structural *patterns* (numbered
clauses, a definitions section, a conformity table) are fine to reuse; specific content
is not.

## Structural conventions (do not deviate without updating this guide)

1. **One unwrapped line per numbered clause.** `_LIST_ITEM_RE`
   (`ingestion/parser.py`) is line-oriented -- a manually soft-wrapped numbered
   paragraph ("1. Foo\nbar.") silently splits into a `LIST_ITEM` segment ("Foo") and a
   separate `PARAGRAPH` segment ("bar."), discovered and fixed during this corpus's own
   authoring (`docs/controlled-synthetic-corpus-plan.md` §6). Always write a numbered
   clause as one line, however long.
2. **`Article <N>` as its own standalone paragraph**, immediately preceding a subtitle
   paragraph, exactly as EU AI Act's `article-<N>-<slug>.txt` files and this corpus's
   `d2-classification.md`/`d3-registration.md` already do -- this is what
   `_ARTICLE_TITLE_RE` matches to populate `legal_article_number` (carried forward to
   every later segment in the document until the next `Article <N>` title).
3. **Article numbers must be globally unique across the whole corpus** (not just within
   one file). This corpus's cross-reference resolution now supports multiple articles
   per file via each segment's own `legal_article_number`
   (`_legal_article_number_segment_ids`,
   `docs/cross-reference-granularity-resolution-plan.md`) -- but that match is
   ambiguity-safe: if two different articles anywhere in the corpus ever shared the
   same number, resolution for that number silently falls back to `unknown` rather than
   guessing. Check the existing numbers (Article 2-6) before adding a new one.
4. **`Annex <roman numeral>` as its own standalone paragraph**, same convention as
   `Article <N>` (`_ANNEX_TITLE_RE`) -- letters (`Annex A`) will not match; only roman
   numerals do, matching the EU AI Act corpus's own annex-numbering convention.
5. **A cited paragraph needs an entity-aligned subject to compose cleanly.** If you want
   two passages to combine into `composite_direct_support` (not merely
   `composite_unresolved`), give both sentences the *same* grammatical subject (e.g.
   both start with "A registered operator...") -- `review/field_extraction.py`'s entity
   extractor anchors on the subject before the first modal/verb, and a genuine subject
   mismatch is correctly, conservatively treated as a possible conflict or unresolved
   composition, not silently merged. See case 3's authoring history in
   `docs/controlled-synthetic-corpus-plan.md` for a worked example of getting this
   wrong, then right.
6. **Retrieval depth and packing budget are manifest fields, not automatic.**
   `review.imported_answer.import_answer`'s `top_k`/`token_budget` parameters are
   independent of a `PipelineManifest`'s own `retrieval_manifest.candidate_depth`/
   `packing_manifest.evidence_budget_tokens` -- nothing reads the manifest fields
   automatically. `wittgenstein fixture run` and the fixture-integrity validator both
   read and apply them explicitly; if you call `import_answer` directly in a new
   script/test, do the same (`top_k=manifest.retrieval_manifest.candidate_depth`,
   `token_budget=manifest.packing_manifest.evidence_budget_tokens`) or your case will
   silently run under the library defaults (`top_k=5`, `token_budget=300`) regardless
   of what the manifest says.

## Adding a new case

1. Write the source clause(s) first, in isolation, and run them through
   `ingestion.parser.parse_document` directly (see the pattern in
   `docs/controlled-synthetic-corpus-plan.md` §6) to confirm the exact segment IDs,
   `legal_article_number`/`legal_paragraph_number`/`legal_point_identifier` values
   before writing anything that depends on them.
2. Pick a query/answer pair and run it through `review.imported_answer.import_answer`
   directly (a throwaway script under the session scratchpad, not committed) to observe
   the *actual* retrieved/packed/claim-linking/evidence-set/cross-reference output --
   never guess what the field-comparison engine will decide. Iterate on wording until
   the case demonstrates the behavior you intend, or accept and document the real
   observed behavior if it doesn't (see case 3's `composite_unresolved` outcome for a
   worked example of the latter).
3. Add the case to `cases/cases.json` using the existing `SmokeTestCase` schema fields
   only (`extra="forbid"` -- no new fields). Encode perturbation status via
   `answer_source_method` (e.g. `"controlled_perturbation_<type>"`), matching the EU AI
   Act pilot's own convention.
4. Write `expected/<case_id>.expected.json` from the *actually observed* output --
   never from what you expected before running it. Include `controlled_perturbation`
   (with all 6 required provenance fields, if true), `minimum_evidence_set`,
   `expected_claim_link_relationship`, `expected_evidence_set_status`,
   `expected_cross_reference` (if any explicit citation is involved),
   `expected_reviewer_action` (always advisory), and `distractor_locations` (if any,
   with `expected_distractor_relationship` explicitly not `direct_support_candidate`).
5. Run `uv run wittgenstein fixture load asteria_manual` -- it re-runs every case
   through the real pipeline and checks it against your `expected/*.json`. Fix either
   the case or the expected file (never force one to match the other by assertion
   alone) until it passes.
6. Update `docs/controlled-corpus-coverage-matrix.md`'s table with the new row.
7. Add a corresponding entry to the frontend's `ASTERIA_CASES` constant in
   `frontend/public/review.html` (regenerate via the same script pattern documented in
   that file's surrounding comment -- kept in sync by hand, same as `WIDGET_CORPUS`).

## Adding a new document

1. Give it a stable `source_document_id` (the filename stem) that does not collide with
   an existing one.
2. If it introduces new articles, follow convention #2/#3 above.
3. Re-run `uv run wittgenstein fixture load asteria_manual` after adding it -- a new,
   unreferenced document does not break anything by itself, but confirm no accidental
   cross-reference ambiguity was introduced (two documents now sharing an article
   number, etc.).
4. Update `data/fixtures/asteria_manual/README.md`'s document list.

## What the fixture-integrity validator checks

See `src/wittgenstein/fixtures/asteria_validator.py` and
`docs/controlled-synthetic-corpus-plan.md` §14 for the full list. In short: every case
runs through the real pipeline with zero LLM calls; every distractor is confirmed to
never reach `direct_support_candidate`; every declared cross-reference expectation is
checked against the real detection/resolution output; every controlled perturbation
carries complete provenance; and no tracked file claims real-source provenance or
collides with real registry vocabulary.
