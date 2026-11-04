# eu-ai-act-2024

## 1. Corpus ID

`eu-ai-act-2024`

## 2. Purpose in the diagnostic matrix

Primary corpus for the first real-corpus diagnostic pass
(`docs/corpus-selection-rationale.md`). A modern, heavily cross-referenced regulatory
text -- used to test this pipeline's field extraction, claim linking, evidence-set
construction, and cross-reference detection on real numbered-article prose with
explicit definitions, scope conditions, and temporal applicability language. **Not**
used to determine or advise on actual AI Act compliance.

## 3. Official source URL(s)

- <https://eur-lex.europa.eu/eli/reg/2024/1689/oj/eng>
- <https://eur-lex.europa.eu/legal-content/EN/TXT/PDF/?uri=OJ:L_202401689>

## 4. Access date placeholder

`<REPLACE: YYYY-MM-DD -- the date you actually retrieved the text>`

## 5. License/public-access or source-use note

Official EU legislation published via EUR-Lex. EU legal texts are generally reusable
for non-commercial/informational purposes, but **confirm EUR-Lex's reuse notice as it
stands on your access date** and record exactly what it says -- do not rely on this
README's summary as the license record. Record your finding in the local metadata
(§7 below), not only here.

## 6. Required local directory

```
data/examples/evidence_set_diagnostics/local_corpora/eu-ai-act-2024/
```

Gitignored (`local_corpora/*` in `.gitignore`) -- nothing placed here is committed.
One `.txt`/`.md` file per article/section, or a single
`{document_id: text}` JSON file -- see
`docs/real-corpus-diagnostic-runbook.md` step 3 for both supported layouts.

## 7. Required local metadata (record per document, alongside the file)

- Source title (e.g. "Regulation (EU) 2024/1689 -- Article 6")
- Source URL
- Access date
- Publisher (`"Official Journal of the European Union"` / `"EUR-Lex"`)
- Document version/effective date (`"OJ L, 2024/1689, entered into force 2024-08-01"`)
- Local file name
- SHA-256 hash (via `ingestion.content_hash.content_hash` -- see `docs/real-corpus-diagnostic-runbook.md` step 2's exact command)
- License/public-access note (your own confirmed reading of EUR-Lex's reuse notice)
- Extraction/parser notes (e.g. "copied from the PDF's Article 6 section; tables in
  Annex III were not extracted")
- Selected section/article range (e.g. "Article 6(1)-(2) only")

## 8. Initial slice specification

- Relevant definitions from Article 3.
- Articles 6, 13, 50, and 113.
- Any directly referenced definitions/articles required to interpret the selected
  sections.
- Optionally a small relevant Annex excerpt, only if needed for a cross-reference
  case.

## 9. Recommended diagnostic-case categories

- Definition plus obligation
- Scope/condition
- Temporal applicability
- Cross-reference target
- Exception
- Same-topic but non-supporting evidence
- Multi-article evidence set

See `data/examples/evidence_set_diagnostics/case-sets/README.md` for the full
case-shape guidance and `docs/real-corpus-case-authoring-guide.md` for how to write
one.

## 10. Warning

**This corpus is for software evaluation only. Output derived from it is never legal
advice, a compliance determination, or an authoritative statement of what the EU AI
Act requires in any real situation.**

## 11. Raw material statement

Raw article/section text is never committed to this repository. It stays under the
gitignored `local_corpora/eu-ai-act-2024/` directory on your own machine unless you
have separately confirmed and documented redistribution rights for the specific
excerpt in question.
