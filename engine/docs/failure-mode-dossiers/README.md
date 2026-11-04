# Failure mode dossiers

This directory is a place to commit generated Markdown dossiers you want tracked in
git history (e.g. a snapshot before/after a major evidence-verification pass).

Dossiers are generated, not hand-written:

```bash
uv run wittgenstein registry dossier RET_HARD_DISTRACTOR --output docs/failure-mode-dossiers/RET_HARD_DISTRACTOR.md
```

or via the API: `GET /registry/mechanisms/{id}/dossier`.

Do not hand-edit a committed dossier file — edit the underlying registry records
(`data/registry/*.seed.yaml`) and regenerate. A hand-edited dossier will silently
drift from the registry it claims to describe.

All 7 concrete (non-`research_hypothesis`) mechanisms' dossiers are committed here as of
the 2026-09-09 literature-review pass (`docs/literature-review-results.md`), as a
snapshot of the registry immediately after that pass. Regenerate (do not hand-edit) any
time the underlying registry records for a mechanism change, so the committed file
doesn't silently drift from what it claims to describe.
