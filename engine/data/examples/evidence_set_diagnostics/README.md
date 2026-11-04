# Evidence-set real-corpus diagnostic fixtures

Supports `docs/evidence-set-real-corpus-diagnostics-plan.md`. A small, manually
reviewed diagnostic pass for the multi-passage evidence-set layer
(`docs/multi-passage-evidence-plan.md`) -- not a benchmark, not a human-subjects study.

## Layout

```
cases.example.json     # bundled, fully synthetic example cases (reuses SmokeTestCaseFile shape)
manifests.json          # {manifest_id: PipelineManifest} registry (copy of real_trace_smoke's)
local_corpora/           # (gitignored) real/licensed source documents go here -- never committed
output/                  # (gitignored) default location for `wittgenstein evidence-set diagnose` output
```

## Case format

Reuses `schemas/smoke_test.py::SmokeTestCase`/`SmokeTestCaseFile`/`CorpusReference`
unchanged -- no separate diagnostic-case schema (see
`docs/evidence-set-real-corpus-diagnostics-plan.md`'s "Reuse notes"). The additional
diagnostic content (candidate propositions, evidence sets considered, field-comparison
vectors, cross-reference target states, conflict explanations, size-3 diagnostics,
manual labels) is *output*, written by `wittgenstein evidence-set diagnose` to
`<case_id>.diagnostic.json` and `<case_id>.diagnostic_labels.json` -- never part of the
case input file.

## Bundled example cases (`cases.example.json`)

Two cases against the same bundled `widget-certification-demo` fixture
`demo/widget_corpus.py` already uses, chosen because their behavior against this
milestone's diagnostic instrumentation is already empirically verified:

| Case | Exercises |
|---|---|
| `diag-001-cross-reference-packed` | an explicit "Section 4" cross-reference that resolves to a packed segment (no warning), and an "Exemption C" reference that is body text, not a heading, so it cannot be location-matched (`UNKNOWN` state) -- demonstrating the cross-reference diagnostic's honest limits |
| `diag-002-compound-claim-real-corpus-conflict` | a genuinely compound (eligibility + threshold) claim whose two real-corpus supporting passages compose into a `composite_conflict_candidate` -- demonstrating the conflict-explanation instrumentation on a real (moderate-confidence, not low-confidence-artifact) finding |

Run them:

```bash
uv run wittgenstein evidence-set diagnose \
  --cases data/examples/evidence_set_diagnostics/cases.example.json \
  --output-dir data/examples/evidence_set_diagnostics/output
```

Add `--diagnostic-max-set-size 3` to also run the (bounded, explicitly warned) size-3
diagnostic search for cases where default (`max_set_size=2`) construction was
attempted but did not reach full composite support -- never the default, never used
by any other command.

## Adding real/licensed documents

Identical procedure to `data/examples/real_trace_smoke/README.md`'s "Provenance
discipline" section (reused, not reimplemented): place source text under
`local_corpora/<your-corpus-id>/` (gitignored), add a `CorpusReference` with
`source_type: local_path_excluded_from_git`, compute `document_hashes`, and add a
matching `PipelineManifest` to `manifests.json` if needed. See
`docs/evidence-set-real-corpus-diagnostics-plan.md` §1-5 for what to prioritize
sampling: long/complex sentences, explicit cross-references with varied target states,
genuine multi-passage compositions, and apparent conflicts.
