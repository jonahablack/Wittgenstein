# Reviewer measures

The measurement dictionary for local-validation studies (`docs/local-validation-protocol.md`).
Every measure named here has a corresponding field on one of the six
`LocalValidationRecord` evidence-layer sub-models (`schemas/review.py`) — this document
is what a study's `outcome_definitions` field should be cross-referenced against, not a
separate, parallel vocabulary that could drift out of sync with the schema.

Six outcome layers, never collapsed into one score: four core layers (A–D) plus
alert-fatigue/AI-burnout as its own named dimension, because a low alert volume does
not by itself mean low fatigue. All measures are optional per study — a study reports
what it actually measured; an absent field means "not measured here," never "zero" or
"failed."

## Scales and instrument format

Perception measures use a 5-point or 7-point Likert scale (pick one per study and
document it in `outcome_definitions`; do not mix scales within one study without
documenting the mapping). Rate measures (`*_rate`) are proportions in `[0, 1]`. Count
measures (`*_count`) are raw integers. Time measures are in seconds. Every study should
also collect free-text/open-ended responses alongside the scaled items — see "Open-ended
questions" below.

## Layer A — Evidence and factual adjudication (`AdjudicatedTraceEvidence`)

Used only where a defensible adjudication target exists (`applicable: bool` gates this
honestly — `False` is a normal outcome for contested/versioned material, not a gap).

| Measure | Field | Definition |
|---|---|---|
| Material support issue detection | `material_support_issue_detection_rate` | Rate at which reviewers correctly identified a materially unsupported/incomplete claim. |
| Unsupported-claim detection | `unsupported_claim_detection_rate` | Rate at which reviewers correctly flagged a claim adjudication found unsupported. |
| Contradiction recognition | `contradiction_recognition_rate` | Rate at which reviewers correctly noticed contradicted evidence. |
| Qualification preservation | `qualification_preservation_rate` | Rate at which reviewers noticed a dropped/altered qualification, exception, or condition. |
| False approval | `false_approval_rate` | Rate at which reviewers approved a claim adjudication found unsupported. |
| False rejection | `false_rejection_rate` | Rate at which reviewers rejected a claim adjudication found supported. |
| Appropriate unresolved/escalation | `appropriate_unresolved_escalation_rate` | Rate at which a genuinely contested/incomplete case was correctly left unresolved or escalated, rather than forced into a false supported/unsupported call. |
| Support-set completeness recognition | `support_set_completeness_recognition_rate` | Rate at which reviewers correctly recognized whether the full multi-part support set was present. |

Per-case adjudication outcomes use `core/enums.py::AdjudicationOutcome` (12 values:
`supported`, `partially_supported`, `unsupported`, `contradicted`,
`qualification_omitted`, `insufficient_evidence`, `source_conflict`,
`version_dependent`, `jurisdiction_dependent`, `requires_clarification`,
`requires_expert_escalation`, `unresolved`) — deliberately not a binary
correct/incorrect. Do not label reviewer disagreement as factual error: a reviewer
choosing `version_dependent` where the adjudicator expected `supported` is not
necessarily a miss — check whether the case was actually version-contingent before
counting it against any rate above.

## Layer B — Contextual judgment (`ContextualJudgmentEvidence`)

Whether reviewers *noticed* context-sensitivity signals — independent of whether they
reached the "right" factual answer.

| Measure | Field |
|---|---|
| Population awareness | `population_awareness_rate` |
| Jurisdiction awareness | `jurisdiction_awareness_rate` |
| Date awareness | `date_awareness_rate` |
| Version awareness | `version_awareness_rate` |
| Source-authority awareness | `source_authority_awareness_rate` |
| Condition awareness | `condition_awareness_rate` |
| Exception awareness | `exception_awareness_rate` |
| Threshold awareness | `threshold_awareness_rate` |
| Cross-reference awareness | `cross_reference_awareness_rate` |
| Missing-dependency awareness | `missing_dependency_awareness_rate` |
| Conflicting-source awareness | `conflicting_source_awareness_rate` |
| Applicability-boundary awareness | `applicability_boundary_awareness_rate` |

## Layer C — Reviewer experience and workflow (`BehavioralWorkflowEvidence`)

Self-reported experience (`reviewer_experience_evidence`) and observed behavior
(`behavioral_workflow_evidence`) share this shape; a study may populate either or both.
`willingness_to_continue_mean` and `willingness_to_reuse_mean` live here as their one
canonical home (also relevant to alert fatigue — read from here, not duplicated).

| Measure | Field |
|---|---|
| Perceived usefulness | `perceived_usefulness_mean` |
| Ease of verification | `ease_of_verification_mean` |
| Evidence-navigation effort | `evidence_navigation_effort_mean` |
| Review time | `review_time_seconds_mean` |
| Source text opened | `source_text_opened_rate` |
| Dependency links followed | `dependency_links_followed_rate` |
| Full-context requests | `full_context_request_rate` |
| Clarification requests | `clarification_request_rate` |
| Escalation decisions | `escalation_rate` |
| Perceived review burden | `perceived_review_burden_mean` |
| Perceived alert relevance | `perceived_alert_relevance_mean` |
| Willingness to continue | `willingness_to_continue_mean` |
| Willingness to reuse the tool | `willingness_to_reuse_mean` |

## Layer D — Human autonomy and trust calibration (`AutonomyAndTrustEvidence`)

| Measure | Field |
|---|---|
| Perceived autonomy | `perceived_autonomy_mean` |
| Supported independent judgment | `supported_independent_judgment_mean` |
| Encouraged blind acceptance (higher is worse) | `encouraged_blind_acceptance_mean` |
| Felt pressured to follow the tool | `felt_pressured_to_follow_tool_mean` |
| Confidence in the answer | `confidence_in_answer_mean` |
| Confidence in the evidence | `confidence_in_evidence_mean` |
| Confidence in the tool's warning | `confidence_in_tool_warning_mean` |
| Recognized need for more information | `recognized_need_for_more_information_rate` |
| Override/reject rate | `override_or_reject_rate` |

## Alert fatigue and AI burnout (`AlertFatigueEvidence`)

An explicit evaluation dimension, not an informal motivation. A low alert volume does
not by itself mean low fatigue — a warning can be low-volume but still opaque,
repetitive, or unhelpful.

| Measure | Field |
|---|---|
| Perceived alert volume | `perceived_alert_volume_mean` |
| Perceived alert actionability | `perceived_alert_actionability_mean` |
| Repeated-warning annoyance | `repeated_warning_annoyance_mean` |
| Alerts displayed | `alerts_displayed_count` |
| Alerts dismissed | `alerts_dismissed_count` |
| Alerts leading to a meaningful action | `alerts_leading_to_meaningful_action_count` |
| **Actionable alert rate** | `actionable_alert_rate` = `alerts_leading_to_meaningful_action_count / alerts_displayed_count`. A meaningful action: opening a dependency, inspecting omitted context, checking a competing source, requesting clarification, qualifying the answer, escalating, or marking unresolved. |
| Unnecessary escalations | `unnecessary_escalation_count` — escalations that increased burden without improving reviewer-perceived understanding or usefulness; a distinct risk from a low actionable-alert rate. |
| Mental workload | `mental_workload_mean` |
| Frustration | `frustration_mean` |
| Fatigue after a review block | `fatigue_after_block_mean` |
| Perceived repetitiveness | `perceived_repetitiveness_mean` |

`AlertFatigueEvidence` validates that `actionable_alert_rate` is arithmetically
consistent with the two counts when all three are reported, so the rate and the raw
counts cannot silently drift apart.

## False reassurance (`FalseReassuranceAnalysis`)

A separate, named risk, never inferred from a low disagreement rate or a high
usefulness score alone: **the tool appears to make reviewers prematurely comfortable or
less likely to investigate when investigation remains warranted.** `observed: bool`
records whether a study looked for this at all — absence of this analysis is itself
meaningful (see the `TRIAGE_ENABLED` criteria, `docs/registry-governance.md`).

## Primary and co-primary outcomes

- Perceived usefulness
- Perceived ability to identify what deserves scrutiny
- Perceived ease of verification
- Perceived context sensitivity
- Perceived user-intent responsiveness
- Perceived alert burden
- Perceived mental workload / fatigue
- Perceived autonomy
- Perceived trust calibration

## Secondary outcomes

- Factual/evidence adjudication (Layer A), where available
- Review time
- Text exposure (source text opened, dependency links followed)
- Source/dependency navigation
- Clarification requests
- Escalation decisions
- Reviewer overrides
- Alert dismissal
- Actionable-alert rate
- False reassurance
- Unnecessary escalation
- False approval and false rejection, where adjudication supports them

## Example survey items (5- or 7-point agreement scale)

1. "The tool helped me identify which evidence deserved closer scrutiny."
2. "The warning was understandable."
3. "The tool helped me recognize when I needed more information."
4. "The tool helped me distinguish topic relevance from relevance to the user's actual
   request."
5. "The tool reduced the burden of reviewing the retrieved evidence."
6. "The tool made the review process feel repetitive or fatiguing."
7. "The tool supported my own judgment."
8. "The tool made me more likely to accept the answer without sufficient review."
9. "I could override the tool's prioritization when appropriate."
10. "I would use this warning in future reviews of similar material."

## Open-ended questions

- What did the warning help you notice?
- What did it fail to help you notice?
- Did it ever make you more confident than you should have been?
- Did it create unnecessary work?
- What would you have wanted to inspect next?
- Did the warning fit the user's actual question?

## What this document does not do

It does not assert that any of these measures have been collected yet for
`REP_SEGMENTATION_GRANULARITY_MISMATCH` or any other mechanism — this is the
instrument, not a results report. No external empirical claim is made here beyond what
is already verified in the registry (`docs/literature-review-second-review-results.md`).
