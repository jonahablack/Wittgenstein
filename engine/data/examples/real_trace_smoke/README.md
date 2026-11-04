# Real-trace smoke-test fixtures

Supports `docs/real-trace-smoke-test-plan.md`. A small pilot set for manually
diagnosing retrieval and claim-linking behavior on realistic-shaped manifest/answer
pairs -- not a broad benchmark, and `expected_evidence_locations` on each case is a
researcher annotation for diagnosis, never a claim of universal factual ground truth.

## Layout

```
cases.schema.json      # JSON Schema for a SmokeTestCaseFile ({"cases": [SmokeTestCase, ...]})
cases.example.json     # 6 bundled, fully synthetic example cases (see below)
manifests.json         # {manifest_id: PipelineManifest} registry cases.example.json references
local_corpora/         # (gitignored) real/licensed source documents go here -- never committed
output/                # (gitignored) default location for `wittgenstein smoke-test run` output
```

## Provenance discipline

Every case's `corpus.source_type` is one of:

- `bundled_synthetic_fixture` -- a small, fully fictional corpus already shipped with
  this repository (currently: `widget-certification-demo`, the same fixture used by
  `demo/widget_corpus.py` and `data/examples/local_validation/`). Safe to redistribute.
- `local_path_excluded_from_git` -- real or licensed document text that lives only at
  a local filesystem path under `local_corpora/` (gitignored). The case file itself
  stores only the path string, a `document_hashes` map (sha256 per document, so drift
  is detected even though the text is never committed), and `source_metadata`
  (title/publisher/license/access_date) -- never the document text.

`cases.example.json` intentionally contains only `bundled_synthetic_fixture` cases
(`provenance_status: synthetic_fictional`), so this repository never ships or
redistributes real/restricted material. To add real-document cases:

1. Place the document(s) under `local_corpora/<your-corpus-id>/` (gitignored).
2. Add a `CorpusReference` with `source_type: local_path_excluded_from_git`,
   `local_path` pointing at that directory or a `{source_document_id: text}` JSON file,
   and a `provenance_status` reflecting how you obtained it
   (`user_provided_license_confirmed`, `public_domain_or_open_license`, etc. -- see
   `core/enums.py::ProvenanceStatus`; never `pending_provenance_review` for a case you
   intend to run against real people's decisions).
3. Compute and record `document_hashes` (e.g. via
   `python -c "from wittgenstein.ingestion.content_hash import content_hash; print(content_hash(open('doc.txt').read()))"`)
   so later drift in the local file is caught, not silently ignored.
4. Add a matching `PipelineManifest` entry to `manifests.json` if you're not reusing
   an existing one, and add the case to your own (locally kept, not necessarily
   committed) cases file -- or to `cases.example.json` only if the content is
   genuinely safe to redistribute.

## Bundled example cases (`cases.example.json`)

Six cases against the widget-certification-demo fixture, chosen to cover every
required pilot-variation category (`core/enums.py::PilotCoverageLabel`):

| Case | Exercises |
|---|---|
| `smoke-001-supported-single-claim` | structured/long document, multiple sections, a well-supported single claim |
| `smoke-002-partial-multi-claim` | a two-claim answer where the second claim is a fabricated over-generalization |
| `smoke-003-unsupported-fabricated` | a fully fabricated claim with topical-but-not-supporting overlap -- see `docs/real-trace-smoke-test-results.md` for why this is a known limitation of the lexical-overlap heuristic, not a bug |
| `smoke-004-conflict-negation` | a claim that directly contradicts its best-matching source via negation mismatch |
| `smoke-005-multi-passage-cross-reference` | an answer requiring two passages and an explicit cross-reference |
| `smoke-006-narrative-short-document` | the shorter, more narrative `inspection-procedures` document |

Run them:

```bash
uv run wittgenstein smoke-test run \
  --cases data/examples/real_trace_smoke/cases.example.json \
  --output-dir data/examples/real_trace_smoke/output
```

See `docs/real-trace-smoke-test-plan.md` for the manual-inspection workflow that
follows a run, and `docs/real-trace-smoke-test-results.md` for the results template.
