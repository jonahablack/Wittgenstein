# Local-validation protocol: multidimensional reviewer-study design

This document extends `docs/research-protocol.md` (which covers the general
`LocalValidationRecord` schema and the basic causal/correlational study design) with a
specific, multidimensional protocol for studies whose subject is a reviewer's
experience of a manifest-conditioned mechanism warning — the kind of study needed
before any mechanism can be considered for `ActivationPolicy.TRIAGE_ENABLED`
(`docs/registry-governance.md`). `docs/segmentation-local-validation.md` applies this
protocol concretely to `REP_SEGMENTATION_GRANULARITY_MISMATCH`, the first mechanism
this applies to.

This document defines the study design. It does **not** implement a human-subjects
study interface — no UI, no participant-facing tool, no data-collection pipeline. That
remains explicitly out of scope until a study is actually commissioned.

## Core evaluation principle

This tool is **not** evaluated solely by whether it recovers a fixed factual ground
truth. The intended domains contain changing, versioned, contested, incomplete, and
context-dependent information; in some cases there is no single timeless answer that
can be treated as an unquestionable gold label. Factual and evidence adjudication is
not removed from the evaluation — it remains an important dimension wherever a
defensible adjudication target actually exists — but it is one dimension among several,
never the sole endpoint. Collapsing everything into one accuracy score would misrepresent
what this tool is for: structuring human review, not replacing factual judgment with an
automated one.

The evaluation is therefore multidimensional, matching the six outcome layers defined
in `docs/reviewer-measures.md`:

1. Evidence and factual adjudication (where a defensible target exists).
2. Context sensitivity and applicability awareness.
3. User-intent responsiveness.
4. Reviewer experience and workflow.
5. Alert fatigue and AI-burnout burden.
6. Human autonomy and trust calibration.

**Reviewer experience is not a substitute for all safety checks.** A tool that reduces
review time but increases false reassurance is not a success. A tool that improves
targeted scrutiny while reducing unnecessary burden may be a success even when some
factual disputes remain unresolved — unresolved and contested outcomes are valid, not a
study failure. These are reported separately, never blended.

## The evaluation target

The study does not ask "did the reviewer identify the objectively wrong answer?" It
asks: **did the tool help the reviewer allocate attention, inspect dependencies,
recognize uncertainty and conflict, respond to user intent, and choose an appropriate
review action with less unnecessary burden and without false reassurance?**

For factual/evidence cases where a defensible adjudication target exists, structured
adjudication (Layer A) is retained. For contested or moving cases, a valid outcome is
one of the twelve `AdjudicationOutcome` values (`core/enums.py`) — including
`unresolved`, `version_dependent`, `jurisdiction_dependent`, `source_conflict`,
`requires_clarification`, and `requires_expert_escalation` — never forced into a binary
correct/incorrect call. Reviewer disagreement with a prior label is not automatically
factual error; it may reflect genuine contestedness that the adjudication protocol
itself must be able to represent (see "Factual adjudication design" below).

## Review conditions

1. **Undifferentiated review** — the reviewer sees the answer and ordinary retrieved
   evidence, with no segmentation risk event. Usable as a broad baseline: what review
   quality looks like with no manifest/trace-conditioned tooling at all, closest to
   current unaided practice.
2. **Query-scoped review** — the reviewer sees answer-linked evidence and relevant
   source context, but without the mechanism's risk event.
3. **Manifest-conditioned risk review** — the reviewer sees the same evidence as
   condition 2, plus the mechanism's warning: its evidence status, manifest/trace
   rationale, and bounded reviewer action.

The primary comparison, when the goal is isolating the warning's specific value, is
**condition 2 vs. condition 3** — this holds evidence exposure constant and varies only
the presence of the warning and its explanation. Condition 1 serves as a broader
baseline for how much of any observed effect is attributable to query-scoped evidence
presentation at all, versus the warning specifically; a study that only ever compares
conditions 2 and 3 should still describe condition 1's likely relationship in its
`unresolved_limitations`.

**Full retrieved evidence is available in every condition.** The intervention under
test is attention allocation and explanation, not evidence withholding. Conditions must
not reveal different factual source content unless the experimental design explicitly
documents that difference and the reason for it (e.g. a deliberate manipulation check) —
undocumented content differences between conditions would confound the warning's effect
with an evidence-availability effect.

## User-intent responsiveness

User intent is represented conservatively via `core/enums.py::IntentSource`:
`user_stated`, `system_inferred`, `reviewer_confirmed`, `unresolved`.
**System-inferred intent is never treated as ground truth.** The review protocol must
let reviewers identify:

- topic relevance versus relevance to the actual request;
- missing jurisdiction, population, date, comparator, or scope;
- retrieved context that answers a nearby but different question;
- when a clarification question is preferable to a definitive answer.

A reviewer choosing `ask_clarifying_question` (`core/enums.py::ReviewerAction`) over a
definitive approval/rejection is a legitimate, sometimes-correct outcome, not a
non-answer to be penalized.

## Reviewer actions

No binary correct/incorrect judgment is forced. The bounded action vocabulary
(`core/enums.py::ReviewerAction`):

`approve_sufficiently_supported` · `approve_with_qualification` ·
`request_additional_context` · `inspect_referenced_section` ·
`compare_competing_sources` · `check_date_version_jurisdiction` ·
`ask_clarifying_question` · `escalate_to_domain_expert` · `reject_as_unsupported` ·
`mark_unresolved` · `dismiss_as_low_priority`

Each recorded decision should carry the selected action, a confidence rating, a
rationale, and an optional free-text explanation — this record-keeping is part of the
future human-subjects interface, not built in this pass; this document specifies the
vocabulary and requirements it must satisfy when built.

## Factual adjudication design

Where factual adjudication is possible (`AdjudicatedTraceEvidence.applicable=True`), a
study must define, in advance:

- **The adjudication target** — claim-level statement or query-level answer
  (`label_granularity`).
- **Who adjudicates** (`adjudicator`) and **what source/version governs**
  (`governing_source_or_version`) — for contested material, the adjudication itself is
  scoped to a stated authority, not presented as timeless.
- **How disagreement is represented** (`disagreement_handling`) — never silently
  resolved; report raw disagreement, not just a post-hoc consensus label.
- **How unresolved or contested cases are handled**
  (`unresolved_or_contested_case_handling`) — an `AdjudicationOutcome` other than a
  clean supported/unsupported call is a first-class result, not a data-quality problem.
- **What counts as a material issue** (`material_issue_definition`), stated before the
  study runs, not selected after seeing results (mirrors
  `docs/research-protocol.md`'s existing "Outcome measure" requirement).

Adjudication in this protocol serves three roles, never as the sole study endpoint:

1. A safety safeguard (bounding how much a reviewer-experience improvement is allowed
   to trade off against detection of material issues — criterion 6 in
   `docs/registry-governance.md`'s `TRIAGE_ENABLED` checklist).
2. A characterization of trace conditions (what fraction of study cases actually had a
   material issue at all).
3. A tool for analyzing false reassurance (whether reviewers approved cases adjudication
   found materially unsupported).

## Alert fatigue and AI burnout

Tracked as an explicit evaluation concern (`AlertFatigueEvidence`,
`docs/reviewer-measures.md`), not an informal motivation. Do not assume fewer alerts
automatically means less fatigue — a low-volume warning can still be opaque, repetitive,
or unhelpful; `perceived_alert_actionability_mean` and `actionable_alert_rate` are
reported alongside raw volume, never instead of it.

```
actionable_alert_rate = alerts_leading_to_meaningful_action_count / alerts_displayed_count
```

A meaningful action: opening a dependency, inspecting omitted context, checking a
competing source, requesting clarification, qualifying the answer, escalating, or
marking unresolved.

Two risks are tracked as named, separate concerns, never conflated:

- **False reassurance** (`FalseReassuranceAnalysis`) — the tool appears to make
  reviewers prematurely comfortable or less likely to investigate when investigation
  remains warranted.
- **Unnecessary escalation** (`AlertFatigueEvidence.unnecessary_escalation_count`) —
  the tool increases review burden or escalation without improving reviewer-perceived
  understanding or usefulness.

A tool that reduces time but increases false reassurance is not successful. A tool that
improves targeted scrutiny while reducing unnecessary burden may be successful even
with some factual disputes left unresolved.

## Promotion to `TRIAGE_ENABLED`

See `docs/registry-governance.md`, "Promotion to TRIAGE_ENABLED," for the full
ten-point checklist. In brief: a `LocalValidationRecord` never *automatically* promotes
a mechanism — `LocalValidationRecord.meets_triage_promotion_bar()` checks only
record-completeness (reviewer-experience evidence present, false-reassurance analysis
present, preregistered design, documented reviewer population/corpus-slice coverage);
it is necessary, never sufficient, and a human registry-governance decision always
applies the full ten-point checklist, including the substantive judgment calls
(criteria 3–6 and 10) this method cannot evaluate mechanically.

Local validation may change **deployment priority only**
(`LocalValidationRecord.deployment_priority`). It must never change: external evidence
grade, the canonical mechanism claim, universal epistemic status, or the historical
evidence record — see `docs/registry-governance.md` and `docs/evidence-grading.md`.

## Example fixtures

Eleven domain-neutral manifest/trace scenarios exercising this protocol live in
`data/examples/local_validation/` (catalogued in `data/examples/local_validation/README.md`
and cross-referenced in `data/examples/local_validation/scenarios.json`), loaded and
validated by `tests/unit/test_local_validation_protocol_examples.py`. None of the
fixtures make claims about real clinical or legal guidance — the domain is a fictional
regulatory-filing scenario, consistent with the existing `data/examples/` fixtures.
