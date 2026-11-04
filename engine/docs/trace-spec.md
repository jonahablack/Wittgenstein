# Trace spec

A `QueryTrace` (`schemas/trace.py`) is the record of one query's actual journey
through a RAG pipeline: what was retrieved, reranked, selected, packed, omitted,
compressed, prompted, and answered — plus whatever reviewer judgments exist about
whether the answer was actually supported.

## Pipeline lineage stages preserved by this schema

```
corpus_available -> parsed_representation -> index_units -> retrieval_candidates
  -> reranked_candidates -> selected_context_items -> packed_context_items
  -> actual_prompt_token_spans -> answer_claims -> answer_to_evidence_support_edges
  -> reviewer_judgments
```

`QueryTrace` instruments every stage from `retrieval_candidates` onward as its own
field (see "Stage lists" below); `corpus_available`/`parsed_representation`/`index_units`
are corpus-level, not query-level, and are instead the province of `CorpusProfile` and
the manifest's `ingestion_manifest`/`representation_manifest` sections
(`docs/manifest-spec.md`). No two adjacent stages are ever collapsed into one field —
this is what lets the matching engine distinguish "retrieved," "available to the
generator," and "used correctly" as three different, independently-checkable facts.

## Stage lists: `None` vs. `[]`

`retrieval_candidates`, `reranked_candidates`, `selected_context_items`,
`packed_context_items`, `omitted_context_items`, and `compressed_context_items` are
all typed `list[ContextItem] | None`, defaulting to `None`. This is a deliberate,
load-bearing distinction:

- `None` — this stage was not instrumented for this trace. The matching engine cannot
  say anything about it.
- `[]` — this stage *was* instrumented, and genuinely produced zero items.

`PACK_OMISSION_OR_TRUNCATION`'s manifest-independent trace trigger
(`trace/lineage.py::stages_fully_logged`) checks for `is not None` on the first three
of these, not for truthiness — a system that never logs `selected_context_items` must
not be silently treated as "selected nothing."

## `ContextItem`

Each item carries `is_query_related` and `is_answer_supporting` as independent,
optional booleans. Both `None` (unassessed) — this is what lets
`RET_HARD_DISTRACTOR` distinguish a **hard distractor** (`is_query_related=True`,
`is_answer_supporting=False`) from **random noise** (`is_query_related=False`): both
"look like an unsupported item" if you only check the second field, but they are
different phenomena with different evidence behind them (see the source candidate's
own framing in `data/registry/failure_modes.seed.yaml`).

## `AnswerSupportEdge`

`support_status` is a string over `supported` / `unsupported` / `contradicted` /
`unknown` — never a boolean. An answer claim with no edge at all
(`trace/lineage.py::is_answer_supported` returns `None`) means "nobody has reviewed
whether this claim is supported," which is a materially different state from a
reviewer having actively marked it `unsupported`. Conflating the two would turn every
un-reviewed claim into a false positive.

## `ContextConflict` vs. a "contradicted" support edge

These are two different signals and must not be merged:

- `context_conflicts` — the packed *context itself* contains incompatible claims
  (`GEN_CONTEXT_CONFLICT_UNRESOLVED`'s trigger condition). This exists whether or not
  the model ever generates an answer.
- `AnswerSupportEdge.support_status="contradicted"` — the *answer* contradicts one
  specific packed item. This can happen with no `context_conflicts` present at all
  (the model simply asserted something the context didn't say), and a
  `context_conflicts` entry existing doesn't by itself mean the answer contradicted
  anything (the answer might have picked one side cleanly).

`tests/unit/test_eligibility_gates.py::test_answer_conflict_with_context_distinct_from_conflicting_context`
locks this distinction in.

## `SupportRequirement`

Presence of `support_requirement` on a trace means the query's support-set
requirement has been assessed at all. `is_multi_hop=False` (assessed, single-span) is
a real, distinct state from `support_requirement=None` (not assessed) — collapsing
them would make `RET_MULTIHOP_SUPPORT_INCOMPLETE` either fire on every un-assessed
query (false positives) or silently skip every un-assessed query without flagging the
gap (silent under-reporting). The engine reports
`insufficient_manifest_information` for the `None` case specifically to avoid both.

`review/imported_answer.py::import_answer` is one automatic source of this field (in
addition to `assessment_method="reviewer_assessed"` from a human): when
`review/evidence_set.py::construct_evidence_set` (`docs/multi-passage-evidence-plan.md`)
proposes an `EvidenceSet` with actual members for at least one answer claim,
`import_answer` sets `is_multi_hop=True`, `required_support_item_ids` to the union of
those members' item ids, and `assessment_method="evidence_set_construction"`. It never
sets `is_multi_hop=False` or overwrites an existing (e.g. reviewer-assessed) value —
an attempt that finds no valid multi-passage set tells us evidence was insufficient,
not that the claim is single-span, so `support_requirement` is left as-is (or `None`)
in that case, consistent with the "absence means not assessed" contract above.

## Cross-reference target state (diagnostic only)

`review/cross_reference_diagnostics.py::CrossReferenceTargetState`
(`docs/cross-reference-diagnostic-spec.md`) is a read-only measurement over an
existing trace's stage lists (`retrieval_candidates`/`selected_context_items`/
`packed_context_items`/`omitted_context_items`) plus a freshly built `CorpusIndex` --
it is not a `QueryTrace` field and never writes back onto the trace. It answers "where
did an explicitly cross-referenced target land in this pipeline," never "is this
target needed" (a human judgment) or "does this resolve the claim" (never asserted).
Used only by the real-corpus diagnostic harness
(`docs/evidence-set-real-corpus-diagnostics-plan.md`).

## `segment_boundary_dependency_flags`

A trace-level list of human-readable flags identifying a support/dependency relation
that crosses a retrieval-segment boundary — the trace-level signal
`REP_SEGMENTATION_GRANULARITY_MISMATCH` requires. This is intentionally a flat list of
strings rather than a structured cross-reference graph: instrumenting the actual
graph is future work, and a flat flag list is honest about what's currently captured.

This field carries the entire trace-level half of that mechanism's activation gate
(`docs/registry-governance.md`): a non-empty list means a needed dependency is actually
separated in the observed retrieval/packing path, not merely hypothetically possible
given the chunking configuration. An empty list (stage instrumented, genuinely no
flags) and `None` (stage not instrumented) both correctly fail to activate the
mechanism, but for different reasons — `[]` means "checked, none found";
`None`-equivalent absence means "not checked at all" — see "Stage lists" above for the
general `None` vs. `[]` discipline this mirrors. Neither an incorrect-looking `answer`
nor any other trace field is read by this mechanism's gate — segmentation risk is
assessed independently of whether the final answer happened to be right or wrong.

`review/imported_answer.py::import_answer`'s corpus-branch (no pre-existing `trace`
supplied) already populates this field correctly, unmodified, via
`demo/pipeline.py::run_demo_query`'s existing Tier-2 annotation pass — no separate
wiring was needed to demonstrate genuine activation/non-activation against a corpus
built for exactly that purpose (`data/fixtures/asteria_manual`,
`docs/controlled-synthetic-corpus-plan.md`, case `asteria-004-rule-plus-condition`
activating and `asteria-001-...` under `asteria-p4-full-context-control` not
activating, both verified directly against `matching/eligibility.py::evaluate_eligibility`).
The caller-supplied-`trace` branch does not populate this field — an existing,
unchanged gap, not something this milestone altered.

## Relationship to the local-validation outcome vocabulary

`docs/local-validation-protocol.md` adds two enum vocabularies used by reviewer-study
fixtures and `LocalValidationRecord` outcome layers, deliberately **not** added as new
`QueryTrace` fields in this pass (out of scope until a study interface is actually
built): `core/enums.py::IntentSource` (`user_stated` / `system_inferred` /
`reviewer_confirmed` / `unresolved`) for classifying where a query constraint came
from — `QueryTrace.query_constraints` (a plain `dict[str, str]`) is where such a
constraint would be recorded today, but the schema does not yet tag each entry with an
`IntentSource`; and `core/enums.py::AdjudicationOutcome` (12 values including
`unresolved`, `version_dependent`, `source_conflict`) for per-case factual/evidence
adjudication labels, which is a reviewer-study-time judgment, not a trace-time
observation, and therefore does not belong on `QueryTrace` or `AnswerSupportEdge` at
all — `AnswerSupportEdge.support_status` (`supported`/`unsupported`/`contradicted`/
`unknown`) remains the trace-level vocabulary and is not extended or replaced by
`AdjudicationOutcome`.

## Structural validation beyond Pydantic types

`trace/validator.py::validate_trace` checks referential integrity Pydantic's field
types can't express on their own: a packed item must appear in `selected_context_items`
too (lineage sanity), `prompt_token_spans`/`answer_support_edges`/`context_conflicts`
must reference known item/claim ids, `end_token >= start_token`, and a
`support_requirement.is_multi_hop=True` must carry a non-empty
`required_support_item_ids`. `wittgenstein trace validate <file>` and
`POST /traces/validate` both run this after Pydantic parsing succeeds.
