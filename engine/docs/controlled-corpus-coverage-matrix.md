# Controlled corpus coverage matrix

The Asteria fixture's per-case ground truth, generated from actually running each case
through the real, no-LLM pipeline (`review.imported_answer.import_answer`) and
recording the observed result -- never predicted in advance and left unverified. Full
detail lives in each case's `data/fixtures/asteria_manual/expected/<case_id>.expected.json`;
this table is the single, at-a-glance index across all ten cases
(`docs/controlled-synthetic-corpus-plan.md` §7's four-way separation is preserved in
the "Signal kind" column below).

**This matrix does not establish real-world RAG reliability, a human-review outcome, or
grounds for any registry/evidence-grade/activation-policy change.** Every "expected
reviewer action" is advisory only -- recorded for documentation and regression-test
purposes, never forced or highlighted in the frontend.

## Signal-kind legend

- **Registry mechanism** -- a real, deterministically-evaluated `FailureMechanism`
  (`matching/eligibility.py`), checked directly via `evaluate_eligibility`.
- **Trace integrity** -- a directly observable pipeline fact (packed/omitted/
  retrieved state, omission reason), never a causal claim.
- **Review cue** -- a Tier-2 `AnnotationCueType` (condition/exception/cross-reference),
  always `research_hypothesis`/`experimental_review_cue`, never a confirmed error.
- **Fixture expectation** -- this case's own author-recorded ground truth about *this
  pipeline's current, deterministic behavior on this one designed input* -- never a
  claim of universal correctness.

## Matrix

| # | Case ID | Doc/Section IDs | Query | User-intent constraints | Answer origin | Expected evidence locations | Min. evidence set | Dependency/cross-ref target | Distractor locations | Expected claim-link relationship | Expected evidence-set status | Cross-ref coarse state | Resolution granularity | Exact-target availability | Trace/integrity events | Segmentation-mechanism activation | Expected reviewer action (advisory) | Perturbation status | Known limitations |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | asteria-001-direct-single-span-class-s | d2-classification, Article 2(2) | Class S clearance margin | well-specified | human_authored_for_pilot | Article 2(2) | [d2-classification-seg10] | none | none | direct_support_candidate | n/a | n/a | n/a | n/a | packed (P1); no dependency flags under P4 top_k=1 (Trace integrity) | non-activation (P4, Registry mechanism, verified) | approve_sufficiently_supported | none | P1's top-5 pool also pulls in cue-bearing content -- P4 needed for the clean control |
| 2 | asteria-002-definition-plus-requirement | d1-definitions D-02; d2-classification Article 2(1) | Class R def + clearance margin | well-specified, two-part | human_authored_for_pilot | Definition D-02; Article 2(1) | [d1-definitions-seg10, d2-classification-seg9] | none | none | direct_support_candidate (both claim fragments) | n/a | n/a | n/a | n/a | packed (P1) | not evaluated | approve_sufficiently_supported | none | none |
| 3 | asteria-003-two-passage-complementary | d3-registration Article 5(3), 5(4) | renewal frequency + scope | well-specified | human_authored_for_pilot | Article 5(3); Article 5(4) | [d3-registration-seg11, d3-registration-seg12] | Article 5 internal (no external cross-ref marker) | none | unresolved (per-candidate) | composite_unresolved (Fixture expectation, verified) | n/a | n/a | n/a | packed (P1), both members composed | not evaluated | request_additional_context | none | Regex-based multi-passage composition reaches composite_unresolved, not composite_direct_support, on this real sentence pair -- documented as a real, current limitation, not rewritten to force a cleaner result |
| 4 | asteria-004-rule-plus-condition | d2-classification Article 2(1) | Article 2 pre-deployment requirement | well-specified | human_authored_for_pilot | Article 2(1) | [d2-classification-seg9] | none | none | direct_support_candidate | n/a | n/a | n/a | n/a | packed (P1); CONDITION cue 'provided that' (Review cue) | **activation** (P1, Registry mechanism, verified via evaluate_eligibility) | approve_sufficiently_supported | none | none |
| 5 | asteria-005-rule-plus-exception | d2-classification Article 3 | legacy-unit exemption | well-specified | human_authored_for_pilot | Article 3 | [d2-classification-seg15] | Article 2 (secondary, incidental) | none | direct_support_candidate | n/a | unknown/in_corpus (secondary marker, not this case's primary assertion) | n/a | n/a | packed (P1); EXCEPTION cue 'except' (Review cue) | not evaluated | approve_with_qualification | none | none |
| 6 | asteria-006-cross-reference-exact-target-packed | d3-registration Article 5(1); Article 6 | Article 5(1)/Article 6 registration+reporting | names cited paragraph | human_authored_for_pilot | Article 5, paragraph 1; Article 6 | [d3-registration-seg9, d3-registration-seg16] | Article 5(1) (exact paragraph) | none | best_effort_observed_not_forced | n/a | **packed** (verified) | **paragraph** (verified) | **exact_target_present** (verified) | packed (P1) | not evaluated | approve_sufficiently_supported | none | none |
| 7 | asteria-007-cross-reference-budget-stressed | d3-registration Article 5(1); Annex I | Article 5(1) registry location | names cited paragraph | human_authored_for_pilot | Article 5, paragraph 1 | [d3-registration-seg9] | Annex I (not retrieved under budget stress) | none | best_effort_observed_not_forced | n/a | Article 5(1): packed/exact_target_present; **Annex I: in_corpus** (verified) | Article 5(1): paragraph; Annex I: **annex** | Article 5(1): exact_target_present; Annex I: **target_missing** | 3 of 5 candidates omitted, `context_budget_exceeded` (Trace integrity, verified, P2 evidence_budget_tokens=60) | not evaluated | request_additional_context / mark_unresolved | none | Whether Annex I's actual content supports the claim cannot be determined from what is packed -- the intended unresolved/source-expansion scenario |
| 8 | asteria-008-distractor-same-topic | d2-classification Article 2(1) | Class R clearance margin | well-specified | human_authored_for_pilot | Article 2(1) | [d2-classification-seg9] | none | [d2-classification-seg10] (Class S, same-topic) | direct_support_candidate (correct source); **unresolved, never direct_support** (distractor, verified) | n/a | n/a | n/a | n/a | packed (P1), both correct source and distractor | not evaluated | approve_sufficiently_supported | none | none |
| 9 | asteria-009-numeric-threshold-mismatch | d2-classification Article 2(1) | Class R clearance margin | well-specified | **controlled_perturbation_numeric_threshold_mismatch** | Article 2(1) (actual: 12 cm) | [d2-classification-seg9] | none | none | source-supported: direct_support_candidate; perturbed: **contradiction_candidate** (both verified) | n/a | n/a | n/a | n/a | packed (P1) | not evaluated | reject_as_unsupported | **numeric_threshold_mismatch** (12 cm -> 20 cm, changed_claim_component=numeric_value) | none |
| 10 | asteria-010-underspecified-intent | none (query too broad) | minimum clearance margin, no class named | **underspecified** | human_authored_for_pilot | (none -- ambiguous between Article 2(1)/2(2)) | [] | none | none | **no candidate reaches direct_support** (verified) | composite_unresolved | n/a | n/a | n/a | packed (P1), no candidate matches cleanly | not evaluated | ask_clarifying_question | none | Reflects genuine query ambiguity, not a retrieval/claim-linking defect |

## Pipeline manifests used

- **asteria-p1-baseline** (cases 2, 3, 4, 5, 6, 8, 9, 10; also case 1's primary run):
  `candidate_depth=5`, `evidence_budget_tokens=600`.
- **asteria-p2-budget-stressed** (case 7): same retrieval, `evidence_budget_tokens=60`.
- **asteria-p4-full-context-control** (case 1's non-activation-control variant only,
  not a separate case file entry): `candidate_depth=1`.
- **asteria-p3-parent-context**: not used by any case -- representable-but-not-executable
  (`docs/controlled-synthetic-corpus-plan.md` §11), schema-validated only.

## What this matrix does not establish

Restated from `docs/controlled-synthetic-corpus-plan.md` §1: not a real-corpus
benchmark, not a human-subjects study, not legal/medical/financial/safety advice, not
evidence of prevalence in production, and not grounds for changing the registry,
evidence grades, or activation policies. Every "verified" annotation above means
"independently confirmed by running the real, unmodified pipeline against this one
designed case and reading its actual output" -- never "asserted" or "predicted."
