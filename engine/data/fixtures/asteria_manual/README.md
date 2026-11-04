# Asteria Autonomous Systems Certification Manual (controlled synthetic corpus)

**Fictional, research-only content.** The "Asteria Standards Authority," "autonomous
inspection units," clause numbers, and clearance-margin thresholds below are entirely
invented for this repository's regression testing. This is not a real standard,
regulation, product manual, or clinical guideline, and none of its requirements apply
to any real system. See `docs/controlled-synthetic-corpus-plan.md` for the full plan
this corpus was built from, and `docs/controlled-corpus-coverage-matrix.md` for what
each case is designed to exercise.

## What this is

A controlled, hand-authored, fully-understood corpus for regression-testing the
existing pipeline (retrieval, packing, claim-linking, multi-passage evidence-set
composition, cross-reference/granularity resolution) against *known* expected
outcomes. Complementary to, and structurally distinct from, the EU AI Act real-corpus
diagnostic pilot (`docs/eu-ai-act-pilot-execution-plan.md`): that pilot tells you what
the system does on genuine, licensed legal text of unknown-in-advance shape; this
corpus tells you whether the system does what it is supposed to on inputs whose correct
behavior was decided before the pipeline ever ran.

**This is not**: a real-corpus benchmark, a human-subjects study, legal/medical/
financial/safety advice, evidence that any failure mode is prevalent in production, or
grounds for changing the registry, evidence grades, or activation policies. See
`docs/controlled-synthetic-corpus-plan.md` §1 for the full list.

## Layout

```
documents/     4 tracked Markdown documents (the corpus text)
cases/         cases.json -- 10 SmokeTestCase entries (query/answer/manifest per case)
expected/      one <case_id>.expected.json per case -- hand-recorded, verified ground truth
manifests.json the 4 PipelineManifests (P1-P4)
manifest.yaml  human-readable mirror of manifests.json, generated together (never hand-edited separately)
```

## Documents

- `d1-definitions.md` -- Definitions D-01 through D-06.
- `d2-classification.md` -- Article 2 (classification requirement, two numbered
  paragraphs: Class R / Class S), Article 3 (exception for legacy units), Article 4
  (scope of application).
- `d3-registration.md` -- Article 5 (registration obligation, four numbered
  paragraphs), Article 6 (reporting deadlines, cites Article 5(1) and Table A.2).
- `annex-i-conformity-table.md` -- Annex I, a Markdown conformity table (Table A.2) and
  closing cross-references.

Every numbered clause is written as a single, unwrapped line -- the deterministic
parser's list-item detection is line-oriented, so a manually soft-wrapped numbered
paragraph silently splits into two segments mid-sentence (discovered and fixed during
this corpus's own authoring; see `docs/controlled-synthetic-corpus-plan.md` §6).

## How this corpus resolves cross-references across multiple articles per file

Unlike the EU AI Act pilot corpus (one article per file), this corpus's four documents
each contain more than one `Article <N>` clause. `review/cross_reference_diagnostics.py`
gained one small, additive resolution path for this milestone
(`_legal_article_number_segment_ids`) that matches a cited article by each segment's own
parsed `legal_article_number` field rather than only by filename -- see
`docs/cross-reference-granularity-resolution-plan.md`'s module docstring update and
`tests/unit/test_cross_reference_granularity.py` for the coverage. This does not change
any existing corpus's (including the EU AI Act pilot's) resolution behavior -- confirmed
by the full existing test suite remaining green.

## Running this corpus

```bash
uv run wittgenstein fixture load asteria_manual
uv run wittgenstein fixture run asteria_manual --case asteria-001-direct-single-span-class-s \
  --manifest asteria-p1-baseline --output-dir <local-output-dir>
```

See `docs/asteria-frontend-demo.md` for the full local API/frontend workflow.

## Manifests

- **P1 `asteria-p1-baseline`**: executable. Deterministic parsing, BM25 lexical
  retrieval, `candidate_depth=5`, `evidence_budget_tokens=600`, no LLM.
- **P2 `asteria-p2-budget-stressed`**: executable. Same as P1 with
  `evidence_budget_tokens=60`.
- **P3 `asteria-p3-parent-context`**: **not executable**. Describes a
  parent/neighbor-context-reconstruction configuration (`parent_child_expansion=true`)
  that no code in this repository implements. Schema-valid (`wittgenstein manifest
  validate` passes); never run by `wittgenstein fixture run` or any automated demo
  claim. See `docs/controlled-synthetic-corpus-plan.md` §11.
- **P4 `asteria-p4-full-context-control`**: executable. Same retrieval configuration as
  P1 except `candidate_depth=1` -- used specifically as the segmentation-mismatch
  non-activation control for case `asteria-001` (see that case's
  `expected/*.json`).

## Ground-truth boundaries

Every `expected/<case_id>.expected.json` file is a **fixture regression label** --
recorded after directly observing this codebase's real, deterministic pipeline output,
checked by tests and the fixture-integrity validator, and never exposed to a reviewer
in the frontend as objective truth. `expected_reviewer_action` fields are explicitly
advisory-only. See `docs/controlled-synthetic-corpus-plan.md` §10.
