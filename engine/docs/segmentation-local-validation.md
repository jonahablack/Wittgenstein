# Local validation: `REP_SEGMENTATION_GRANULARITY_MISMATCH`

Applies `docs/local-validation-protocol.md` concretely to
`REP_SEGMENTATION_GRANULARITY_MISMATCH` — the first (and, as of this document, only)
mechanism structurally eligible for a `TRIAGE_ENABLED` local-validation study, per
`docs/registry-governance.md`. No study has been run yet; this document specifies the
design, not results.

## Why this mechanism first

It is the only mechanism currently `externally_established` (two independent,
RAG-native, verified A2 records — `docs/literature-review-second-review-results.md`)
and already `manifest_conditioned` (`docs/failure-mode-dossiers/REP_SEGMENTATION_GRANULARITY_MISMATCH.md`).
Its risk event is shown only when its five manifest/trace gates genuinely pass
(`matching/eligibility.py::_eval_rep_segmentation_granularity_mismatch`), and its
reviewer-facing language is a single, bounded, pre-approved sentence
(`matching/explanation.py::_MECHANISM_BOUNDED_CLAIM_LANGUAGE`) that makes no causal
claim and no assertion that any specific answer is wrong — a clean, well-scoped subject
for a first study of whether a manifest-conditioned warning changes review behavior.

## The evaluation target, applied here

Not "did the reviewer catch that the segmentation caused an error" — this mechanism's
own evidence is `controlled_comparison`, not `causal_intervention`
(`docs/registry-governance.md`), so no study should be designed around a causal-error
framing the evidence does not support. The target is: **given a trace where a
support/dependency relation crosses a segment boundary, does the warning help the
reviewer notice the boundary, inspect whether the full support set actually reached the
generator, and choose an appropriate action** — approve, approve with qualification,
inspect the referenced segment, compare competing sources, escalate, or mark
unresolved — **with less unnecessary burden and without becoming prematurely
comfortable that the answer is fine?**

## Review conditions, applied here

1. **Undifferentiated review** — reviewer sees the query, the answer, and the packed
   context, with no mention of segmentation or the mechanism.
2. **Query-scoped review** — reviewer additionally sees the full retrieval/selection/
   packing lineage (what was retrieved, selected, packed, omitted) and the
   `segment_boundary_dependency_flags`-relevant source segments, but not the
   `RiskEvent` itself.
3. **Manifest-conditioned risk review** — reviewer sees everything in condition 2, plus
   the `REP_SEGMENTATION_GRANULARITY_MISMATCH` `RiskEvent`: its `epistemic_status`
   (`externally_established`), `transfer_level`, the manifest-gate/trace-trigger
   evaluation trace (`reviewer_explanation`), the bounded reviewer language, and the
   linked `RA_CHECK_SEGMENTATION_BOUNDARY` review action.

Primary comparison: condition 2 vs. 3, isolating the warning's marginal value given
identical evidence exposure. Condition 1 is available as a broader baseline for
interpreting how much of any effect is attributable to lineage visibility in general.

## Fixtures for this study

`data/examples/local_validation/` provides eleven scenarios exercising this mechanism's
positive and negative cases, plus adjacent reviewer-workflow cases (clarification
needed, conflicting sources, unnecessary-escalation risk, false-reassurance risk) — see
`data/examples/local_validation/README.md` for the full catalog. Scenarios 1, 6 are the
clean positive cases (genuine cross-boundary omission); 2–4 are clean negative cases
(no relevant dependency, whole-document retrieval, unknown segmentation metadata) that
must never activate the mechanism regardless of condition; 5 and 7 are deliberately
ambiguous (boundary technically crossed, but either full support is still packed, or an
alternate complete source exists) — these are the cases most informative about
reviewer-perceived usefulness and false-reassurance risk, since the warning fires but
the "right" review action is not simply "reject."

## What this document does not claim

No study has been run. No effect size, reviewer-yield number, or outcome value from
this protocol is asserted anywhere in the registry for this mechanism — its
`default_activation_policy` remains `manifest_conditioned`
(`data/registry/failure_modes.seed.yaml`), not `triage_enabled`, and no
`LocalValidationRecord` for it exists yet. Building the actual reviewer-facing study
interface is explicitly deferred — this document specifies what that interface, once
built, must be able to represent and measure.
