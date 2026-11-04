# local_corpora/ (gitignored)

Real, licensed, or user-provided source documents for the real-corpus diagnostic
pass go here -- and **only** here. This directory is excluded from git (see
`.gitignore`, `/data/examples/evidence_set_diagnostics/local_corpora/`); nothing
placed in it is ever committed.

See `docs/real-corpus-diagnostic-runbook.md` steps 1-3 for the full workflow:
selecting appropriately licensed documents, recording their provenance, and the two
supported layouts (one `.txt`/`.md` file per document, or one
`{document_id: text}` JSON file per corpus).

Verify a path is actually ignored if you're ever unsure:

```bash
git check-ignore -v data/examples/evidence_set_diagnostics/local_corpora/<your-path>
```

Do not place restricted, copyrighted (without a permitting license), private,
clinical, legal, or personally identifying material here without having confirmed you
have the right to use it for this purpose -- see
`docs/real-corpus-diagnostic-runbook.md`'s scope note.
