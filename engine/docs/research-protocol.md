# Research protocol

This document covers **local** research conducted by this project — controlled tests
and human-review studies against a specific deployment, producing
`LocalValidationRecord` entries. For external literature review (finding and grading
published papers), see `docs/literature-review-protocol.md`. For how a mechanism's
registry status changes as a result of either, see `docs/registry-governance.md`. For
the specific, multidimensional protocol a reviewer-facing warning study must follow —
factual adjudication is retained but is not the sole endpoint; reviewer experience,
context sensitivity, user-intent responsiveness, alert fatigue, and autonomy/trust are
each measured as their own outcome layer, never collapsed into one score — see
`docs/local-validation-protocol.md` and its measurement dictionary,
`docs/reviewer-measures.md`. That protocol is what governs eligibility for
`ActivationPolicy.TRIAGE_ENABLED` specifically (`docs/registry-governance.md`); this
document's simpler causal/correlational model still applies to promoting a mechanism's
`epistemic_status` to `locally_validated` (`LocalValidationRecord.meets_promotion_bar()`),
a different, independent axis.

## Schema fields backing this protocol

Every item below has a corresponding `LocalValidationRecord` field
(`schemas/review.py`): `deployment_scope` (item 2), `method`/`causal_or_correlational`
(item 3), `sample_size`/`evaluation_split`/`preregistered` (item 4),
`reviewers`/`label_source` (item 5), and `precision`/`recall`/`reviewer_yield`/
`uncertainty` for the outcome measure (item 6). `LocalValidationRecord.meets_promotion_bar()`
checks that all of these are populated before a record is eligible for the
`locally_validated` status-change review — see `docs/registry-governance.md`, "Local
validation: promotion requirements".

## What counts as a local validation study

A study that produces a `LocalValidationRecord` must specify, before running it:

1. **The mechanism under test** and its current `epistemic_status`.
2. **`deployment_scope`** — the exact system/dataset/time window the result applies
   to. A local validation record is never a claim about RAG systems in general.
3. **Method** — how the study was designed: a controlled intervention (e.g. rerun the
   same query with and without a candidate distractor item) is preferred over a purely
   observational count, because only an intervention can support
   `causal_or_correlational: "causal"`.
4. **Sample size and selection** — how queries/traces were chosen, and whether that
   selection could bias the result (e.g. only sampling queries that already triggered
   a `RiskEvent` will overestimate the mechanism's real-world frequency).
5. **Reviewer(s) and blinding** — whether the human reviewer(s) judging outcomes knew
   which condition (with/without the candidate factor) they were looking at. Unblinded
   review of a mechanism's own hypothesis is a known source of confirmation bias and
   must be disclosed in `limitations`, not silently omitted.
6. **Outcome measure** — stated in advance, not selected after seeing results.

## Human review procedure

Every `ReviewAction` (`schemas/review.py`) is a bounded question, never an instruction
to accept an automated verdict (`instructs_acceptance` is structurally forced to
`False`). A local validation study's reviewer procedure should reuse the same bounded
question format:

- State the observed trace condition factually (what the eligibility engine actually
  found — `EligibilityGateResult.reason` strings are good source material).
- Ask a specific, answerable question ("Does the answer's correctness change if this
  item is removed from context?"), not an open-ended "is this a problem?"
- Record disagreement between reviewers explicitly rather than resolving it silently;
  a single-reviewer study should say so in `limitations`.

## From local validation to registry status

A `LocalValidationRecord` can:

- Raise a `research_hypothesis` mechanism's priority in triage output *for that
  deployment*, without changing its global `epistemic_status`.
- Support a mechanism reaching `locally_validated` status, per the process in
  `docs/registry-governance.md`.

A `LocalValidationRecord` can never, by itself:

- Convert a mechanism to `externally_established` (that status requires peer-reviewed
  A1/A2 evidence, enforced by `registry/validator.py`).
- Apply to a deployment other than the one named in `deployment_scope`.

## Inter-rater reliability

For any study with more than one reviewer, report agreement (e.g. Cohen's kappa or raw
percent agreement, whichever is meaningful given the sample size) in `result_summary`.
A study with substantial reviewer disagreement is evidence about the mechanism's
*definitional clarity*, not just its frequency — that finding belongs in
`limitations`, and may itself motivate tightening the mechanism's
`necessary_causal_ingredients`.
