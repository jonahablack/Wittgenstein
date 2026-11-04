# hipaa-privacy-rule

## 1. Corpus ID

`hipaa-privacy-rule`

## 2. Purpose in the diagnostic matrix

Secondary corpus for the first real-corpus diagnostic pass
(`docs/corpus-selection-rationale.md`). A long-established, hierarchically organized
US federal regulation -- used to test field extraction and claim linking against
dense permitted-versus-required distinctions and covered-entity scope conditions, on
a public-domain source. **Not** used to determine or advise on actual HIPAA
compliance.

## 3. Official source URL(s)

- <https://www.ecfr.gov/current/title-45/subtitle-A/subchapter-C/part-164/subpart-E>
- <https://www.hhs.gov/hipaa/for-professionals/privacy/index.html> (explanatory
  source only, not the regulatory text itself)

## 4. Access date placeholder

`<REPLACE: YYYY-MM-DD -- the date you actually retrieved the text>`

## 5. License/public-access or source-use note

The eCFR text itself is a US federal government work and is in the public domain.
The HHS explanatory page is a separate, secondary source that may carry its own terms
of use -- if you use any HHS explanatory text (not just the regulation itself),
confirm and record its terms separately. Record which specific page(s) you relied on
and their access date in the local metadata (§7 below).

## 6. Required local directory

```
data/examples/evidence_set_diagnostics/local_corpora/hipaa-privacy-rule/
```

Gitignored (`local_corpora/*` in `.gitignore`) -- nothing placed here is committed.
One `.txt`/`.md` file per section, or a single `{document_id: text}` JSON file -- see
`docs/real-corpus-diagnostic-runbook.md` step 3 for both supported layouts.

## 7. Required local metadata (record per document, alongside the file)

- Source title (e.g. "45 CFR §164.508 -- Uses and disclosures for which an
  authorization is required")
- Source URL
- Access date
- Publisher (`"Electronic Code of Federal Regulations (eCFR)"`)
- Document version/effective date (the eCFR "current as of" date shown on the page
  at the time you accessed it -- the eCFR updates continuously, so this date matters)
- Local file name
- SHA-256 hash (via `ingestion.content_hash.content_hash` -- see `docs/real-corpus-diagnostic-runbook.md` step 2's exact command)
- License/public-access note (public domain -- US government work; note this
  explicitly per document)
- Extraction/parser notes (e.g. "copied section text only, cross-reference footnotes
  to Part 160 omitted")
- Selected section/article range (e.g. "§164.508(a)-(c) only")

## 8. Initial slice specification

- 45 CFR §§164.502, 164.506, 164.508, and 164.512.
- Definitional context from §164.501 or the relevant Part 160 definitions.
- Only direct cross-references necessary for a selected diagnostic case.

## 9. Recommended diagnostic-case categories

- Definition plus permitted disclosure
- Condition or exception
- Covered-entity scope
- Cross-reference
- Multiple nearby sections with similar terminology
- Unresolved applicability

See `data/examples/evidence_set_diagnostics/case-sets/README.md` for the full
case-shape guidance and `docs/real-corpus-case-authoring-guide.md` for how to write
one.

## 10. Warning

**This corpus is for software evaluation only. Output derived from it is never legal
advice, a compliance determination, or an authoritative statement of what HIPAA
requires in any real situation.**

## 11. Raw material statement

Raw section text is never committed to this repository. It stays under the
gitignored `local_corpora/hipaa-privacy-rule/` directory on your own machine. Even
though the eCFR text itself is public domain, keep it local and gitignored anyway
unless you have deliberately decided to redistribute a specific excerpt and documented
that decision.
