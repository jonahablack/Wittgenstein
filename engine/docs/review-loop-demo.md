# Review-loop demo

A reviewer walkthrough of the human review loop described in
`docs/review-loop-implementation-plan.md`, using the same fictional "widget
certification program" domain as `data/examples/local_validation/` and
`src/wittgenstein/demo/widget_corpus.py`. Everything below runs offline -- no LLM
provider credentials are required or used.

## 1. Run the offline widget-corpus pipeline

```bash
uv run wittgenstein demo run
```

This runs `demo/pipeline.py::run_no_llm_baseline_demo` against three sample queries and
prints a summary table (retrieved/packed/omitted counts, prompt token counts). It
confirms the underlying pipeline works before layering the review loop on top.

## 2. Start the API and the static review screen

```bash
make api                                    # terminal 1: FastAPI on :8000
cd frontend/public && python -m http.server 8080   # terminal 2: static file server
```

Open `http://localhost:8080/review.html`.

## 3. Load or enter an answer

The page is pre-filled with:

- **Query**: "What is the pass threshold for a Class I widget?"
- **Answer**: "A Class I widget must pass the Load Stress Test at a 95% threshold. It
  is exempt from inspection." -- deliberately a two-sentence answer where the first
  sentence is well-supported by the bundled corpus and the second is not, so the demo
  shows both a `supported_candidate` and a weaker outcome side by side.

"Use the bundled widget-certification demo corpus" is checked by default, so clicking
**Run imported-answer review** calls `POST /review/import-answer` with the corpus text
inlined -- no separately hosted corpus or database is required for this demo. (A real
deployment would instead pass an existing `trace` from its production RAG pipeline; see
`docs/review-loop-implementation-plan.md` §1.)

## 4. View answer claims and evidence

The response renders as:

- **Answer claims** (section 2/3): each claim, its `extraction_method`
  (`programmatic_rule_based` here -- no LLM call was made), and its
  `candidate_support_status` (a programmatic, pre-review classification -- never a
  final "true"/"false" verdict).
- **Query-relevant evidence** (section 4/5/6): the packed context items actually
  available to answer generation, with source document/segment location and any
  Tier-2 dependency/annotation cues (condition, exception, cross-reference language).

## 5. See applicable segmentation or trace risks

**Risk events** (section 7) lists every `RiskEvent` the registry-matching engine
derived for this trace, sorted by priority tier, each showing: what was observed, the
mechanism id, evidence status, transfer level, the bounded reviewer-facing language
(never "the answer is wrong"), the recommended review action, and an explicit note that
the risk event does not by itself prove the answer is false.

## 6. Open source/dependency context

**Retrieved but not packed** (section 8) and **Full retrieved set** (section 9) stay
visible regardless of what was packed -- low-priority or unflagged evidence is never
hidden. Clicking "Mark opened/inspected" on any evidence card records that the reviewer
looked at it, included in the next review event's `opened_evidence_item_ids`.

## 7. Take a review action

The reviewer panel (section 10/11) lets you set a reviewer id, review condition
(`query_scoped` or `manifest_conditioned` -- the two exposed in this prototype, per
`docs/review-loop-implementation-plan.md` §G), confidence, uncertainty, and notes, then
click one of the bounded reviewer-action buttons (approve, request more context,
escalate, reject as unsupported, mark unresolved, override risk priority, ...).

## 8. Save the review record

Clicking an action button posts to `POST /review/events`, which persists a
`ReviewEvent` row (trace id, reviewer id, review condition, displayed risk events,
opened evidence, the action taken, confidence/uncertainty/notes, timestamp) to the
local SQLite database. The page shows the returned `review_event_id` on success.
Fetch `GET /review/events?trace_id=<id>` (e.g. via `curl`) to confirm it was saved.

## Multi-passage evidence sets

When no single packed passage directly supports an answer claim, `import_answer` also
attempts bounded, deterministic multi-passage composition
(`review/evidence_set.py`, `docs/multi-passage-evidence-plan.md`) -- e.g. one passage
confirming a rule, another confirming which cases it applies to. This is not yet
exposed in the static review screen (`frontend/public/review.html`); see
`docs/multi-passage-evidence-demo.md` for a walkthrough using
`ImportedAnswerResult.evidence_sets` directly.

## Enhanced mode (optional, not required for this demo)

`review/imported_answer.py::import_answer` accepts an `llm_client` for provider-backed
answer-claim decomposition of ambiguous candidates
(`proposition/providers/anthropic_client.py::AnthropicProviderClient`, opt-in via
`ANTHROPIC_API_KEY` and `pip install '.[anthropic]'`). This is not exercised by the
static review screen or by any required test in this pass -- it is available for a
future CLI/API flag, not part of this walkthrough.

## A second, controlled corpus: Asteria

The same `review.html` page now also supports a second, entirely fictional corpus --
the "Asteria Autonomous Systems Certification Manual" -- purpose-built as a
regression-testing fixture with known-in-advance expected behavior per case, rather
than the widget corpus's original illustrative role. Select it from the **Corpus**
dropdown at the top of the page. See `docs/asteria-frontend-demo.md` for the full
walkthrough, including the new claim/evidence-comparison, evidence-set-composition, and
cross-reference-target sections this milestone added to the page (visible for both
corpora, not just Asteria).
