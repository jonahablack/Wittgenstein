# Wittgenstein RAG Reliability

> "The limits of my language mean the limits of my world." This project is about
> being precise regarding what we actually know about RAG failure -- and equally
> precise about what we don't.

A versioned, evidence-graded registry of experimentally investigated RAG (Retrieval-
Augmented Generation) failure mechanisms, plus schemas and deterministic tooling to
match a pipeline manifest and per-query execution trace to only the failure
mechanisms whose experimental prerequisites are actually present.

This is **not** a chat-with-documents product, and **not** an opaque hallucination
detector. It is infrastructure for a human-in-the-loop RAG verification workflow.

## Rationale

RAG failure discussion online is dominated by plausible-sounding linguistic
heuristics ("the model probably got confused by conflicting sources") asserted with
the same confidence as peer-reviewed findings ("position in a long context measurably
affects recall accuracy"). This project refuses to blur that line. Every mechanism in
the registry carries an explicit epistemic status, and the system will not present a
research hypothesis as an externally established failure mode -- that distinction is
enforced in code, not just documentation.

## Registry-first architecture

The core artifact is not a UI. It is a registry of typed, separately-modeled entities:

| Entity | What it is | What it is *not* |
|---|---|---|
| **Failure Mechanism** | A stable, mechanism-level causal claim (e.g. "query-related non-supporting passages can distract answer generation") | A paper, a detector, a UI warning, or a specific answer failure |
| **Evidence Record** | One paper/study's support for a mechanism: exact quote, venue, study type, effect size, limitations, extraction provenance | A citation string with no verified quote |
| **Experimental Envelope** | The experimental preconditions a study tested (retriever, chunking, context length, etc.) | A vague "similar setting" claim |
| **Manifest Gate** | A hard predicate deciding whether a mechanism could apply to a deployed system at all | An inferred default |
| **Transferability Assessment** | A transparent, field-by-field comparison of a manifest/trace against an evidence record's envelope | A single similarity score |
| **Trace Trigger** | A measurable condition in one actual execution trace | A guess about what "probably" happened |
| **Review Action** | A bounded, human-checkable question | An instruction to blindly accept an automated verdict |
| **Local Validation Record** | A result from this project's own controlled tests, scoped to one deployment | A universal external claim |

## Epistemic status and evidence grade

Every mechanism carries an `epistemic_status`:

- `externally_established` -- requires at least one **peer-reviewed** evidence record
  graded **A1 or A2**. Enforced by the registry validator at load time.
- `manifest_conditioned_transfer` -- established in a related setting; transfers to
  RAG only under specific manifest conditions.
- `trace_integrity_condition` -- a directly observable trace fact (e.g. an item was
  selected then omitted before packing), usable before causal effect is established.
- `research_hypothesis` -- a plausible review cue, disabled by default, not an
  established failure mode.
- `locally_validated` -- has evidence from this project's own testing, scoped to one
  deployment; never promoted to a universal external claim automatically.
- `unsupported_or_retired` -- found unsupported or superseded; kept as a record, not
  silently deleted.

Evidence records carry an independent `evidence_grade` (A1 direct-causal peer-reviewed
down to E hypothesis) -- see `docs/evidence-grading.md`.

## Pipeline lineage

The system never collapses "retrieved" with "available to the generator," or
"available to the generator" with "used correctly":

```
corpus_available -> parsed_representation -> index_units -> retrieval_candidates
  -> reranked_candidates -> selected_context_items -> packed_context_items
  -> actual_prompt_token_spans -> answer_claims -> answer_to_evidence_support_edges
  -> reviewer_judgments
```

A candidate that was retrieved but never packed is not "ignored by the model" -- it
never reached the model. A packed item with no support edge is not automatically
"unsupported" -- it may simply be unreviewed. See `docs/architecture.md` for the full
diagram and the reasoning behind each boundary.

## Installation and development

Requires Python 3.11+ and [`uv`](https://docs.astral.sh/uv/).

```bash
uv sync --extra dev
cp .env.example .env
make dev-check      # format, lint, typecheck, test, schema export, seed validation
make api            # run the FastAPI dev server
uv run wittgenstein registry list
```

## How to add a failure mechanism

`uv run wittgenstein registry add-mechanism` (interactive), or hand-edit
`data/registry/failure_modes.seed.yaml`. New mechanisms always start as
`research_hypothesis` / `E_hypothesis` / `disabled_by_default_or_research_mode`. See
`CONTRIBUTING.md` and `docs/registry-governance.md` for how a mechanism's status may
change, and why local validation never converts to a universal claim automatically.

## How to add/verify evidence

`uv run wittgenstein registry add-evidence` (interactive), or hand-edit
`data/registry/evidence_records.seed.yaml`. `exact_quote` must be verbatim from the
primary source with a precise `quote_location`. See
`docs/literature-review-protocol.md` for the full PRISMA-style procedure.

## How to create a manifest

Write a JSON/YAML file matching `PipelineManifest` (see `docs/manifest-spec.md` and
`data/examples/manifests/`), then:

```bash
uv run wittgenstein manifest validate path/to/manifest.json
uv run wittgenstein manifest profile path/to/manifest.json
```

## How to submit a trace

Write a JSON/YAML file matching `QueryTrace` (see `docs/trace-spec.md` and
`data/examples/traces/`), then:

```bash
uv run wittgenstein trace validate path/to/trace.json
```

## Controlled synthetic corpus and local frontend demo

`data/fixtures/asteria_manual/` is a second, entirely fictional, tracked corpus (the
"Asteria Autonomous Systems Certification Manual") built specifically for regression
testing: every case's expected pipeline behavior is known and verified in advance,
unlike a real-corpus diagnostic pass. See `docs/controlled-synthetic-corpus-plan.md`,
`docs/controlled-corpus-coverage-matrix.md`, and `docs/asteria-frontend-demo.md` for the
full plan, per-case ground truth, and a local API/frontend walkthrough.

```bash
uv run wittgenstein fixture load asteria_manual   # validate all 10 cases
uv run wittgenstein fixture run asteria_manual --case <case_id> --manifest <manifest_id> --output-dir <dir>
```

## How applicability assessment works

```bash
uv run wittgenstein applicability assess --manifest path/to/manifest.json --trace path/to/trace.json
```

For each mechanism with a deterministic evaluator, the engine checks required
manifest predicates, disqualifying predicates, and (for query-level mechanisms)
required trace observables -- purely by typed field inspection, no LLM or embedding
call. A missing field never gets a default; it returns
`insufficient_manifest_information`. If eligible, transferability is computed as a
field-by-field comparison against linked evidence envelopes, yielding
`directly_matched` / `mechanistically_matched` / `partially_matched` -- never a single
score. See `docs/registry-spec.md`.

## Non-goals and limitations

- Not a general chat-with-documents product.
- Not an opaque hallucination detector, and this system never returns a generic
  numerical "hallucination probability."
- Does not claim the seed registry (7 concrete mechanisms + 11 disabled research
  hypotheses) is exhaustive. Absence from the registry is not evidence of absence.
- Does not do automated web scraping for evidence; evidence import is a structured,
  manual, human-verified workflow (`docs/literature-review-protocol.md`).
- Does not claim all linguistically plausible transformation risks (negation
  inversion, modal-strength shifts, cross-reference loss, etc.) are proven RAG
  failure modes -- eleven such candidates are seeded explicitly as disabled
  `research_hypothesis` review cues, not established mechanisms.
- This system prioritizes and structures human review. It does not replace it.

## License

Apache-2.0. See `LICENSE`.
