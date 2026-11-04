# results/

Where a completed real-corpus diagnostic pass's *derived* artifacts go, following
`docs/real-corpus-diagnostic-runbook.md` steps 10-11:

- Your filled-in results document, copied from
  `docs/evidence-set-real-corpus-diagnostics-results.md` and named
  `evidence-set-real-corpus-diagnostics-results-<date>.md` (this can live here or
  directly under `docs/` -- either is fine, keep it wherever your other dated results
  docs live).
- The aggregate `diagnostic_report.json` from `wittgenstein evidence-set report`, if
  you want to keep it for future reference.

## What belongs here versus what does not

`diagnostic_report.json` (the aggregate) contains **only label tallies, counts, and
rates** -- no raw source text -- so it is safe to commit for a real/licensed corpus.

**Per-case `<case_id>.diagnostic.json` files are different: they embed raw excerpt
text from your source documents** (`packed_context_items[].excerpt` and similar
fields). For a real/licensed/restricted corpus, these files must stay under your
gitignored output directory (`docs/real-corpus-diagnostic-runbook.md` step 6 --
outside `data/examples/evidence_set_diagnostics/`, or under
`local_corpora/` if you keep them local) and must **never** be copied here or
committed anywhere. If you want to preserve a specific finding for the record,
summarize it in the results document in your own words instead of pasting the raw
JSON.

This directory is not gitignored -- only put derived, excerpt-free summaries in it.
