# Contributing

This is a research-integrity-sensitive project: the registry makes claims about what
is and is not empirically established about RAG failure modes. Contributions that add
or edit `FailureMechanism` or `EvidenceRecord` entries are held to a higher bar than
ordinary code changes. Read `docs/registry-governance.md` and
`docs/literature-review-protocol.md` before proposing registry content changes.

## Development setup

```bash
uv sync --extra dev
cp .env.example .env
make dev-check   # format, lint, typecheck, test, schema export, seed validation
```

## Code changes

1. Open an issue or discuss the change first for anything touching `core/enums.py`,
   `schemas/`, or the matching engine — these are the shared contract.
2. Add or update tests alongside the change (`tests/unit`, `tests/integration`).
3. Run `make dev-check` before opening a PR.
4. Keep pipeline-stage and epistemic-status vocabulary confined to the enums in
   `core/enums.py` — do not introduce parallel ad hoc status strings.

## Registry content changes

1. **Adding a mechanism**: use `wittgenstein registry add-mechanism` or hand-edit
   `data/registry/failure_modes.seed.yaml`. New mechanisms default to
   `epistemic_status: research_hypothesis` and
   `default_activation_policy: disabled_by_default_or_research_mode` until evidence is
   attached and reviewed.
2. **Adding evidence**: use `wittgenstein registry add-evidence`. `exact_quote` must
   be copied verbatim from the primary source with a precise `quote_location`
   (e.g. "Table 3", "Section 5.2", "Abstract"). Never paraphrase or generate a quote.
   Leave `TODO` in place for anything you have not personally verified against the
   primary source, and set `verification_status: unverified`.
3. **Raising epistemic status**: an `externally_established` status requires at least
   one linked, peer-reviewed evidence record graded A1 or A2. The registry validator
   enforces this at load time and will fail the build otherwise — see
   `docs/evidence-grading.md`.
4. Run `wittgenstein registry validate` (or `make validate-registry`) after any
   registry content change.

## Reporting issues

Open a GitHub issue. For evidence-accuracy concerns (e.g. a misquoted paper), tag the
issue `evidence-integrity` — these are treated as high priority.
