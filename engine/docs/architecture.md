# Architecture

## Entity separation

The system deliberately keeps eight entities structurally distinct — separate
Pydantic models, separate seed files, separate reasoning — because collapsing any two
of them is exactly how systems end up overclaiming.

| Entity | Schema | Lives in |
|---|---|---|
| Canonical Failure Mechanism | `FailureMechanism` | `data/registry/failure_modes.seed.yaml` |
| Evidence Record | `EvidenceRecord` | `data/registry/evidence_records.seed.yaml` |
| Experimental Envelope | `ExperimentalEnvelope` | embedded in `EvidenceRecord`; also produced from manifests |
| Manifest Gate | `ManifestGate` | `data/registry/manifest_gates.seed.yaml` |
| Transferability Assessment | `ApplicabilityAssessment` | computed at request time |
| Trace Trigger | `TraceTrigger` | `data/registry/trace_triggers.seed.yaml` |
| Review Action | `ReviewAction` | `data/registry/review_actions.seed.yaml` |
| Local Validation Record | `LocalValidationRecord` | project-specific, not seeded |

A `FailureMechanism` is a mechanism-level claim: "query-related non-supporting
passages can distract answer generation." It is never a paper, a detector
implementation, a UI copy string, or a report of one specific answer being wrong.

An `EvidenceRecord` is one paper's support for exactly one mechanism. Multiple
evidence records can support (or contradict) the same mechanism —
`REP_SEGMENTATION_GRANULARITY_MISMATCH` intentionally carries two records that may
disagree, and the registry does not resolve that disagreement into a single ranking.
Each record carries an explicit `direction` (`supports`/`refutes`/`mixed`/`null`); a
mechanism's `evidence_synthesis` (`convergent`/`mixed`/`limited`/`unresolved`) is a
separate, human-set summary of how its linked records relate as a whole — see
`docs/registry-governance.md`.

## Pipeline lineage

```
corpus_available
   -> parsed_representation
   -> index_units
   -> retrieval_candidates
   -> reranked_candidates
   -> selected_context_items
   -> packed_context_items
   -> actual_prompt_token_spans
   -> answer_claims
   -> answer_to_evidence_support_edges
   -> reviewer_judgments
```

Each arrow is a place information can be lost, and the schema keeps each stage as its
own list on `QueryTrace` so that loss is visible:

- `retrieval_candidates` → `packed_context_items`: a candidate can be selected and
  then dropped by a context-budget or compression step
  (`PACK_OMISSION_OR_TRUNCATION`). `trace/lineage.py::selected_but_not_packed` is the
  one function allowed to make this claim — it is deliberately not phrased as "the
  model ignored evidence," because the model never saw it.
- `packed_context_items` → `answer_to_evidence_support_edges`: a packed item having
  `is_answer_supporting=True` does not mean the answer actually used it correctly.
  That is a separate, explicit judgment (`AnswerSupportEdge.support_status`), and an
  absent edge means "unreviewed," not "unsupported" —
  `trace/lineage.py::is_answer_supported` returns `None` in that case, not `False`.

Two schema decisions enforce this at the type level, not just by convention:

1. The six stage lists on `QueryTrace` (`retrieval_candidates` through
   `compressed_context_items`) are typed `list[ContextItem] | None`, not
   `list[ContextItem] = []`. `None` means "this stage was not instrumented"; `[]`
   means "this stage ran and produced nothing." A gate that requires "candidate,
   selected, and packed stages are all logged" checks for `None`, never for emptiness.
2. `AnswerSupportEdge.support_status` is a string enumeration of `supported` /
   `unsupported` / `contradicted` / `unknown`, not a boolean — a boolean cannot
   represent "genuinely not yet reviewed" without lying in one direction or the other.

## Manifest vs. trace

A `PipelineManifest` describes a *system's configuration* — what it is capable of, in
general. A `QueryTrace` describes *one execution* of that system against one query.
Manifest gates ask "could this mechanism ever apply to a system built this way?"
Trace observables ask "did the specific precondition actually occur on this query?"
Both must pass for a query-level mechanism to be eligible; see
`docs/manifest-spec.md` and `docs/trace-spec.md`.

## The matching engine

`matching/eligibility.py` holds one Python function per mechanism, each a direct,
readable sequence of typed field checks — no generic rules interpreter, no LLM call,
no embedding similarity. Every check produces an `EligibilityGateResult` with a
`gate_id` referencing the declarative `ManifestGate`/`TraceTrigger` record in the
registry, so the human-readable predicate text and the executable check are always
linked by ID (see `docs/registry-spec.md`).

Aggregation (`matching/eligibility.py::_aggregate`) is a small, fixed state machine:

- Any required predicate `VIOLATED`, or any disqualifying predicate `SATISFIED` → the
  mechanism is `NOT_APPLICABLE`. This is conclusive and takes precedence over any
  unrelated unknown field.
- Otherwise, any required/disqualifying predicate `UNKNOWN_INSUFFICIENT_DATA` → the
  result is `INSUFFICIENT_MANIFEST_INFORMATION`. The system never defaults an unknown
  field to "assume satisfied" or "assume violated."
- Otherwise the mechanism is eligible, and `matching/transferability.py` compares the
  manifest/trace-derived `ExperimentalEnvelope` against each linked evidence record's
  envelope, field by field, to compute `TransferLevel`.

`matching/explanation.py` is the single place epistemic status becomes English. It
enforces: a causal claim is only permitted when the mechanism is
`externally_established`, the transfer level is `directly_matched` or
`mechanistically_matched`, and at least one linked, **verified**, peer-reviewed,
A-grade evidence record has `study_type=causal_intervention`. Every other case gets an
explicit "do not phrase this as having caused" suffix appended to its allowed claim
language.

## Diagram: request flow

```
PipelineManifest + QueryTrace
        |
        v
matching/eligibility.py   --(per mechanism, typed checks only)-->  EligibilityResult
        |
        v
matching/transferability.py --(envelope comparison vs. evidence)--> TransferLevel
        |
        v
matching/explanation.py   --(epistemic-status-gated wording)-->    ApplicabilityAssessment
        |
        v
services/applicability_service.py --(filter by activation_policy)--> RiskEvent(s)
```

## Review layer: a consumer, not a registry mechanism

`review/claim_linking.py` (per-claim, single-passage field comparison,
`docs/claim-linking-improvement-plan.md`) and `review/evidence_set.py` (bounded,
multi-passage evidence-set composition, `docs/multi-passage-evidence-plan.md`) sit
downstream of, and never modify, the matching engine above: they determine whether
packed context *supports an answer claim*, which is a different question from whether
a *failure mechanism applies to this manifest/trace*. Both layers produce candidate
relationships (`ClaimEvidenceComparison.relationship_status` /
`EvidenceSet.relationship_status`) that are read by `services/applicability_service.py`
exactly like any other trace fact feeding `matching/eligibility.py` — they never add a
new registry mechanism, never set an `EpistemicStatus`/`EvidenceGrade`, and never
bypass `ActivationPolicy`. `review/imported_answer.py::import_answer` is the one entry
point that runs claim-linking and evidence-set construction, then calls
`derive_risk_events` unmodified — see `docs/review-loop-implementation-plan.md`.

## Fixture layer: controlled corpora as regression tests, not evidence

Two fictional corpora exercise the pipeline above without ever feeding it: the
bundled `widget-certification-demo` (`demo/widget_corpus.py`, inlined Python) and the
Asteria manual (`demo/asteria_corpus.py`, read from tracked Markdown files under
`data/fixtures/asteria_manual/`). Both are resolved as `bundled_synthetic_fixture`
`CorpusReference`s (`schemas/smoke_test.py`), the same case format the real-trace
smoke-test and real-corpus diagnostic harnesses already use — a controlled corpus is
not a parallel case schema, only a different corpus with the same shape. A dedicated
fixture-integrity validator (`fixtures/asteria_validator.py`) runs every case through
the real, unmodified `import_answer` and checks the result against hand-recorded
`expected/<case_id>.expected.json` ground truth — never the other way around; a
fixture's expected file is written from observed pipeline output, never used to
constrain what the pipeline is allowed to do. See
`docs/controlled-synthetic-corpus-plan.md`.
