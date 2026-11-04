# ada-standards-2026

## 1. Corpus ID

`ada-standards-2026`

## 2. Purpose in the diagnostic matrix

Tertiary corpus for the first real-corpus diagnostic pass
(`docs/corpus-selection-rationale.md`), added only after the EU AI Act and HIPAA
slices are working and access/licensing for this corpus specifically has been
confirmed. Clinical guidance with a different diagnostic shape from the first two
corpora -- used to test recommendation-strength/modality extraction, population
eligibility conditions, numeric thresholds, and table/text dependencies. **Not** used
to determine or advise on actual clinical care.

## 3. Official source URL(s)

- <https://professional.diabetes.org/standards-of-care>

## 4. Access date placeholder

`<REPLACE: YYYY-MM-DD -- the date you actually retrieved the text>`

## 5. License/public-access or source-use note

Published by the American Diabetes Association. This is **copyrighted professional
clinical guidance, not a public-domain regulatory text** -- do not assume open reuse
rights. Before storing any local excerpt, confirm the specific access/use terms that
actually apply to you (e.g. individual-use terms, an institutional subscription, or
an explicitly open-access chapter) and record exactly what you confirmed and when.
If you cannot confirm a clear basis for local, non-redistributed use, do not proceed
with this corpus.

## 6. Required local directory

```
data/examples/evidence_set_diagnostics/local_corpora/ada-standards-2026/
```

Gitignored (`local_corpora/*` in `.gitignore`) -- nothing placed here is committed.
One `.txt`/`.md` file per section, or a single `{document_id: text}` JSON file -- see
`docs/real-corpus-diagnostic-runbook.md` step 3 for both supported layouts.

## 7. Required local metadata (record per document, alongside the file)

- Source title (e.g. "Standards of Care in Diabetes -- 2026: Chapter 9,
  Pharmacologic Approaches to Glycemic Treatment")
- Source URL
- Access date
- Publisher (`"American Diabetes Association"`)
- Document version/effective date (`"2026 edition"`, plus the chapter's own
  last-revised date if stated)
- Local file name
- SHA-256 hash (via `ingestion.content_hash.content_hash` -- see `docs/real-corpus-diagnostic-runbook.md` step 2's exact command)
- License/public-access note (your specific confirmed access basis -- see §5; never
  leave this blank or assumed)
- Extraction/parser notes (e.g. "table 9.1 not extracted -- image-only in source
  PDF"; note any table/algorithm you could not extract rather than silently omitting
  it)
- Selected section/article range (e.g. "Chapter 9, sections 9.1-9.3 only")

## 8. Initial slice specification

- One or two complete sections only.
- Associated tables/algorithms only where source access and extraction are
  permitted.
- Recommended starting chapters: pharmacologic treatment, cardiovascular risk
  management, or chronic kidney disease -- but use the exact accessible 2026 source
  section(s) you actually have confirmed rights to, not necessarily these three.

## 9. Recommended diagnostic-case categories

- Recommendation plus population condition
- Modality/strength comparison
- Numeric threshold
- Table/text dependency
- Temporal follow-up
- Unresolved/insufficient evidence

See `data/examples/evidence_set_diagnostics/case-sets/README.md` for the full
case-shape guidance and `docs/real-corpus-case-authoring-guide.md` for how to write
one.

## 10. Warning

**This corpus is for software evaluation only. Output derived from it is never
medical advice, a clinical recommendation, or an authoritative statement of current
standard-of-care guidance for any real patient or situation.**

## 11. Raw material statement

Raw section/table text is never committed to this repository. It stays under the
gitignored `local_corpora/ada-standards-2026/` directory on your own machine, and only
if you have confirmed and documented a use basis that permits local storage (§5) --
do not add this corpus at all if you cannot confirm that basis.
