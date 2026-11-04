# Asteria local frontend demo

A reviewer walkthrough of the Asteria controlled synthetic corpus
(`docs/controlled-synthetic-corpus-plan.md`) through the existing local review
frontend, using the same `frontend/public/review.html` as the widget-certification demo
(`docs/review-loop-demo.md`). Every command below was actually run against this
repository before being documented here. "Deploy" means reproducible local launch
only -- nothing here is exposed to a public host.

## Fictional, research-only

The Asteria manual is entirely invented (`data/fixtures/asteria_manual/README.md`). No
LLM call, no network access, and no provider credentials are required or used by
anything in this walkthrough.

## 1. Validate the fixture (optional but recommended first)

```bash
uv run wittgenstein fixture load asteria_manual
```

Runs every one of the 10 fixture cases through the real, no-LLM pipeline and checks
each against its hand-recorded `expected/<case_id>.expected.json` ground truth. Prints
`All fixture-integrity checks passed.` on success.

## 2. Run one fixture case from the CLI (optional)

```bash
uv run wittgenstein fixture run asteria_manual \
  --case asteria-006-cross-reference-exact-target-packed \
  --manifest asteria-p1-baseline \
  --output-dir /tmp/asteria-output
```

Writes `<case_id>.diagnostic.json`/`.diagnostic_labels.json` to the given directory --
the same JSON shape `wittgenstein evidence-set diagnose` produces. Prints retrieved/
packed/omitted counts and confirms `llm_call_count: 0`.

## 3. Start the API

```bash
uv run uvicorn wittgenstein.api.app:app --reload
```

Runs on `http://localhost:8000` by default. (This walkthrough was tested against a
non-default port to avoid colliding with a locally running instance; the default port
8000 works identically.)

## 4. Launch the static frontend

```bash
cd frontend/public && python -m http.server 8080
```

Open `http://localhost:8080/review.html`.

## 5. Select the Asteria corpus and a case

At the top of the page, change **Corpus** from "Widget certification demo" to "Asteria
Autonomous Systems Certification Manual." The page reveals:

- **Asteria fixture case** -- a dropdown of all 10 cases (`asteria-001-...` through
  `asteria-010-...`). Selecting one pre-fills the Query and Answer fields below and
  selects that case's own pipeline manifest.
- **Pipeline manifest** -- `asteria-p1-baseline`, `asteria-p2-budget-stressed`, or
  `asteria-p4-full-context-control` (P3 is intentionally absent here -- it is
  representable but not executable, see `docs/controlled-synthetic-corpus-plan.md`
  §11).

You may also leave the dropdown at "-- enter query/answer manually --" and type your
own query/answer against the Asteria corpus text.

## 6. Run the review

Click **Run imported-answer review**. This calls `POST /review/import-answer` with the
Asteria corpus text and the selected manifest inlined -- no separately hosted corpus or
database is required.

## 7. Inspect the trace

The response renders as:

- **Answer claims**, **risk events**, **query-relevant (packed) evidence**,
  **retrieved but not packed**, **full retrieved set** -- identical sections to the
  widget-demo walkthrough (`docs/review-loop-demo.md`), now populated from Asteria data.
- **Claim/evidence comparison fields** (new) -- every (claim, candidate) field-by-field
  comparison outcome, with mismatched fields called out.
- **Evidence-set composition** (new) -- any multi-passage composition attempt, its
  members, and its relationship status.
- **Cross-reference targets** (new) -- every detected `Article`/`Annex` citation, its
  coarse pipeline-stage state, resolution granularity, exact-target availability, and
  bounded reviewer explanation (e.g. case `asteria-006-...` under the default manifest:
  *"The cited target, Article 5(1), is present in the packed context. Human review is
  recommended when the precise cited provision matters."*).

## 8. Take a reviewer action and save it

Section 10/11 is unchanged from the widget demo -- set a reviewer id, review condition,
confidence/uncertainty/notes, and click one of the eleven bounded reviewer-action
buttons. This posts to `POST /review/events` and persists a `ReviewEvent` row to the
local SQLite database, showing the returned `review_event_id` on success. No fixture
case's own `expected_reviewer_action` is shown, forced, or highlighted anywhere on this
page -- the reviewer chooses freely among all eleven actions on every case.

## 9. Inspect the persisted review record

```bash
curl -s "http://localhost:8000/review/events?trace_id=<trace_id_from_step_6>"
```

Returns the saved event(s) for that trace, confirming persistence.

## What this demo does and does not show

- Shows: the existing review pipeline (retrieval, packing, claim-linking, evidence-set
  composition, cross-reference/granularity resolution, risk-event derivation, reviewer
  actions) working end to end against a second, controlled, fully-understood corpus,
  entirely offline.
- Does not show: real-world RAG reliability, a human-review usability finding, or any
  outcome that should influence registry/evidence-grade/activation-policy decisions --
  see `docs/controlled-synthetic-corpus-plan.md` §1.
