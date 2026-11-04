# Local-validation example fixtures

Eleven synthetic, domain-neutral manifest/trace scenarios supporting
`docs/local-validation-protocol.md` and `docs/segmentation-local-validation.md`. All
content is fictional (a "widget certification program"); none of it makes claims about
real clinical or legal guidance.

## Layout

```
manifests/
  segmented_rag.json                    # proposition-level segmentation, used by most scenarios
  whole_document_rag.json               # retrieval_unit=whole_document, no sub-document segmentation
  segmented_rag_unknown_metadata.json   # chunking_method/retrieval_unit both unknown
traces/
  01_cross_boundary_genuine_dependency.json
  02_segmented_no_relevant_dependency.json
  03_whole_document_inapplicable.json
  04_unknown_segmentation_metadata.json
  05_boundary_present_complete_support_packed.json
  06_boundary_present_dependency_omitted.json
  07_boundary_present_alternate_source_supports.json
  08_clarification_needed_underspecified_intent.json
  09_conflicting_sources_unresolved.json
  10_unnecessary_escalation_risk.json
  11_low_priority_false_reassurance_risk.json
scenarios.json                          # structured catalog cross-referencing every trace above
```

`scenarios.json` is the source of truth for what each scenario is *for* — which
manifest/trace pair it uses, whether `REP_SEGMENTATION_GRANULARITY_MISMATCH` should
activate, whether factual adjudication is applicable, the expected
`AdjudicationOutcome`, the `IntentSource` classification, and the appropriate
`ReviewerAction`s (all three vocabularies: `core/enums.py`). This lets
`tests/unit/test_local_validation_protocol_examples.py` load and cross-check every
fixture programmatically, not just eyeball them.

## Coverage

| # | Scenario | Activates? | Adjudication applicable? |
|---|---|---|---|
| 1 | Genuine cross-boundary dependency, omitted | yes | yes (unsupported) |
| 2 | Segmented, no relevant dependency | no | yes (supported) |
| 3 | Whole-document retrieval, inapplicable | no | yes (supported) |
| 4 | Unknown segmentation metadata | no | yes (insufficient_evidence) |
| 5 | Boundary crossed, complete support still packed | yes | yes (supported) |
| 6 | Boundary crossed, dependency omitted (traced reason) | yes | yes (unsupported) |
| 7 | Boundary crossed, alternate complete source supports | yes | yes (supported) |
| 8 | Underspecified user intent | no | **no** (requires_clarification) |
| 9 | Conflicting sources, unaddressed | no | yes (source_conflict) |
| 10 | Immaterial split (unnecessary-escalation risk) | yes | yes (supported) |
| 11 | Material safety carve-out omitted (false-reassurance risk) | yes | yes (unsupported) |

Six activate the mechanism, five do not — deliberately including cases where
`REP_SEGMENTATION_GRANULARITY_MISMATCH` fires but the "right" reviewer action is not
simply rejection (5, 7, 10) and one case (11) structurally identical to a clear positive
(6) but included specifically to probe whether priority-capping under
`manifest_conditioned` (`docs/registry-governance.md`) risks under-prioritizing a
genuinely material issue.

Scenarios 8 and 9 do not involve segmentation at all — they exist to give the
local-validation protocol material for user-intent-responsiveness and
source-conflict/unresolved-outcome measurement independent of this one mechanism, per
`docs/local-validation-protocol.md`'s multidimensional design.
