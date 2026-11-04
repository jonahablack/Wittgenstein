# EU AI Act cross-reference comparison template

Documents the format of the machine-generated comparison worksheet
(`wittgenstein evidence-set compare-cross-reference`, output written under
`local_corpora/eu-ai-act-2024/output-after-article-xref/`, gitignored) and gives the
empty summary-table template to fill in **after** annotation
(`docs/eu-ai-act-cross-reference-annotation-protocol.md`) is complete.

**The worksheet itself makes no claim of improvement.** More markers detected is not
evidence of a better outcome by itself -- every summary table below stays blank until
real human labels exist.

## Worksheet format (what the generator produces)

Top-level: `generated_at`, `baseline_dir`, `post_fix_dir`, `cases_file`,
`disclaimer` (the fixed 5-statement list, always present verbatim), `case_ids`
(`common`/`baseline_only`/`post_fix_only`/`in_cases_file_only` -- any non-empty list
other than `common` means a missing/mismatched case to investigate first), `cases`
(one entry per case).

Per case:

| Field | Meaning |
|---|---|
| `case_id` | The case's identifier |
| `query` | From the cases file |
| `answer_origin` | `answer_source_method` from the cases file |
| `expected_evidence_locations` | Researcher navigation aids from the cases file -- never a factual-truth claim |
| `present_in_baseline` / `present_in_post_fix` | Whether this case's diagnostic report exists in each run |
| `baseline_markers` / `post_fix_markers` | Every detected marker, deduplicated by surface text within the case (`occurrence_count` records how many claim fragments repeated it) -- `marker_text`, `reference_type`, `target_identifier`, `target_state`, `extraction_method`, `extraction_confidence`, `warning` |
| `markers_newly_detected` | Markers present post-fix but absent in baseline (matched by `marker_text` only -- robust to the baseline predating the `reference_type` field) |
| `target_states_changed` | Markers present in both runs whose `target_state` differs |
| `relevant_answer_claims` | This case's answer claims (id + text) |
| `linked_evidence_propositions` | Packed segment ids for this case |
| `evidence_set_statuses` | Each evidence set's `relationship_status` |
| `baseline_processing_time_seconds` / `post_fix_processing_time_seconds` | Per-case wall-clock time in each run |
| `non_cross_reference_output_changed` | Boolean -- whether any non-cross-reference field (retrieval/packing/claim-linking/evidence-sets/conflicts/size-3/risk-events) differs between the two runs |
| `non_cross_reference_diff_fields` | Which specific fields differ, if any |

## Statements the worksheet always carries

Verbatim, unconditionally, in its `disclaimer` field:

1. This worksheet records parser output, not legal interpretation.
2. Target resolution is structural (location-text or document-id pattern matching),
   never semantic.
3. Target presence does not establish that a reference is necessary to interpret the
   claim.
4. Target presence does not establish that the target supports, contradicts, or
   resolves the answer.
5. Human annotation is required for usefulness, necessity, false reassurance,
   unnecessary escalation, and interpretation.

## A. Parser coverage (fill in after annotation)

| Metric | Count |
|---|---|
| Explicit markers detected (post-fix total) | |
| Correct detections (human-labeled) | |
| Incorrect detections (human-labeled) | |
| Correctly normalized targets | |
| Incorrectly normalized targets | |
| Correct target-state assignments | |
| Incorrect target-state assignments | |

## B. Dependency visibility (fill in after annotation)

| Metric | Count |
|---|---|
| References newly surfaced (post-fix only) | |
| Targets `in_corpus` | |
| Targets `retrieved` | |
| Targets `selected` | |
| Targets `packed` | |
| Targets `omitted` | |
| Targets `unknown` | |

## C. Reviewer value (fill in after annotation)

| Metric | Count |
|---|---|
| Warnings marked useful | |
| Warnings marked not useful | |
| Warnings likely to cause unnecessary escalation | |
| Warnings likely to cause false reassurance | |
| Cases requiring source expansion/full context | |
| Unresolved cases | |

## D. Non-goals (always state explicitly, never inferred)

- No legal correctness conclusion is made or implied by any count above.
- No factual-answer accuracy conclusion is made or implied by any count above.
- No causal RAG-reliability conclusion is made or implied by any count above.
- No generalization beyond this six-case, single-corpus-slice pilot is made.
- No activation-policy change is made or recommended by this comparison.

## Filling this in

Copy this file to a dated version (matching the pattern in
`docs/evidence-set-real-corpus-diagnostics-results.md`) once
`docs/eu-ai-act-cross-reference-annotation-summary.md` has been completed, and
transfer the final counts here. Do not fill in section A/B/C from the worksheet's raw
counts alone -- sections A and C specifically require the human-labeled outcomes from
`docs/eu-ai-act-cross-reference-annotation-protocol.md`, not just automatic detection
counts (section B's raw target-state counts are the one section that can be copied
directly from the worksheet, since target state is itself an automatic, deterministic
observation -- but even there, "correct" vs. "incorrect" judgments in section A still
require annotation).
