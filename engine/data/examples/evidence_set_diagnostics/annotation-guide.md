# Annotation guide

Defines every label in `core/enums.py`'s five diagnostic-label vocabularies
(`ExtractionQualityDiagnosticLabel`, `ConflictQualityDiagnosticLabel`,
`CrossReferenceClosureDiagnosticLabel`, `EvidenceSetSizingDiagnosticLabel`,
`ReviewerWorkflowDiagnosticLabel`) and the process for applying them to a completed
`wittgenstein evidence-set diagnose` run
(`docs/evidence-set-real-corpus-diagnostics-plan.md` §6).

## What these labels are -- and are not

Every label below describes one of:

- **software output quality** -- did the extractor/comparator/composer do what it was
  supposed to do on this specific input;
- **evidence-navigation needs** -- does a reviewer need to see more source context
  than what's in front of them;
- **review workflow value** -- did the explanation/warning actually help a reviewer
  decide what to do;
- **uncertainty** -- is the honest answer "not enough information to say."

**No label in this guide is a universally settled factual-truth claim about the
underlying document.** A `genuine_source_conflict` label means "these two passages, as
extracted and compared, appear to genuinely disagree" -- not "this document is wrong"
or "this is definitively unresolved as a matter of law/policy/clinical fact." Keep
that distinction in mind especially for slice-B (policy/regulatory-like) documents,
where a real, defensible ambiguity in the source text is a completely valid thing to
observe and label -- it is not this pipeline's job, or this pass's job, to resolve it.

## A. Extraction quality

Applied per field comparison (one label per entry in a case's
`claim_evidence_comparisons`, or per field within one, at your discretion -- see the
label template's `extraction_quality_labels`, keyed by `comparison_id`).

| Label | Meaning | Example |
|---|---|---|
| `extraction_correct` | The extracted value, span, and method are all right for what the field claims to capture. | ENTITY extracted as "Class III widgets" from "Class III widgets must be inspected annually" -- correct span, correct value. |
| `extraction_partially_correct` | The right general answer, but the span or value is imprecise (e.g. includes extra trailing text, or a slightly wrong boundary). | OBJECT_VALUE captured as "annually, per Section 3" when the claim itself only says "annually" -- directionally right, span too wide. |
| `extraction_artifact` | The extracted value is simply wrong -- a genuine bug in the regex/lexicon heuristic, not a defensible judgment call. | A quantifier regex mis-reads "every 6 months" as a population-scope token (a real, fixed bug from this project's history -- see `docs/multi-passage-evidence-plan.md` §11). |
| `source_span_invalid` | The recorded `(start, end)` offset does not actually correspond to the stated surface text in the source excerpt. | Off-by-one or stale offset after normalization. |
| `source_span_incomplete` | The span is valid but doesn't cover the full relevant text (cuts off mid-phrase). | CONDITION span captures "if" but not the rest of the conditional clause. |
| `normalization_correct` | A normalized value (frequency/duration, numeric, comparator) correctly represents the source's stated meaning. | "once per Program Year" normalized with `calendar: domain_defined`, not silently treated as a calendar year. |
| `normalization_uncertain` | The comparator declined to fully resolve a normalization (e.g. returned `UNKNOWN`) and that caution looks appropriate given genuinely ambiguous source text. | A domain-defined period compared against a calendar period, close enough that `_compare_frequency_duration` returned `UNKNOWN` rather than guessing. |
| `parser_disagreement` | Two extraction signals for the same field genuinely conflict (`ExtractionStatus.EXTRACTION_CONFLICT`), and the comparator correctly treated this as `UNKNOWN` rather than picking a side. | See `tests/unit/test_conflict_diagnostics.py::test_07_parser_disagreement_preserved_as_unknown` for the mechanism this labels. |
| `unsupported_inference` | The extractor appears to have inferred something the source text does not actually state. | A value construed from context rather than an explicit textual signal. |
| `unresolved` | You cannot confidently apply any of the above -- the source text itself is ambiguous, or you lack the context to judge. | Legitimate and expected some of the time; do not force a call. |

## B. Conflict quality

Applied per conflict (one label per entry in `conflict_explanations`, keyed
`"<evidence_set_id>:<index>"` in the label template).

| Label | Meaning | Example |
|---|---|---|
| `genuine_source_conflict` | The two members really do state incompatible things about the same requirement. | Two passages give different numeric thresholds for the same entity/predicate/scope, with no version or population difference to explain it. |
| `claim_source_contradiction_candidate_justified` | A single-passage `contradiction_candidate` result is correct -- the source really does contradict the claim. | The claim asserts a rule is allowed; the source states a matching negation. |
| `evidence_set_member_conflict_justified` | A `composite_conflict_candidate` between two evidence-set members is correct given what each member actually says. | See `data/examples/evidence_set_diagnostics/cases.example.json`'s `diag-002-compound-claim-real-corpus-conflict` for a real, moderate-confidence ENTITY conflict worth this label (pending your own read of the specific extracted spans). |
| `apparent_conflict_caused_by_extraction_artifact` | The conflict would not exist if the extraction on one side were correct -- see `field_comparison.rests_on_low_confidence_field`/`alternative_non_conflict_classification_plausible` in the diagnostic report as a hint, never a verdict. | An OBJECT_VALUE "mismatch" driven entirely by the heuristic's low-confidence "rest of the sentence" capture. |
| `apparent_conflict_caused_by_version_time_mismatch` | The conflict resolves once you account for the two members describing different versions/effective dates. | "Program Year 2019" vs. "Program Year 2023" values that are each individually correct for their stated period. |
| `apparent_conflict_caused_by_scope_population_mismatch` | The conflict resolves once you account for the two members describing different populations/scopes. | Two passages about different widget classes, correctly flagged as a scope conflict by `population_scope_conflict`, but not actually contradictory once the reader notices they're about different classes. |
| `conflict_unresolved` | You cannot determine which of the above applies from the available context. | Legitimate; do not force a call. |
| `no_conflict` | On inspection, there is no real disagreement at all -- the system's conflict classification itself looks wrong for reasons other than a known artifact category above. | Rare; if you use this often, say so in `known_limitations` for the run. |

## C. Cross-reference and definition closure

Applied per detected cross-reference marker (one label per entry in
`cross_reference_markers`, keyed `"<claim_id>:<index>"`).

| Label | Meaning | Example |
|---|---|---|
| `explicit_cross_reference_present` | The claim does contain an explicit reference marker (confirms the automatic detection, doesn't re-derive it). | "as defined in Section 4" -- confirms `Section 4` was correctly detected as a marker. |
| `cross_reference_target_available_in_corpus` | A segment matching the marker genuinely exists in the corpus (confirms `target_segment_ids` is non-empty and correct, not a spurious location-text match). | |
| `target_retrieved` | Matches `CrossReferenceTargetState.RETRIEVED`; apply this label to confirm the automatic state looks right given the retrieval ranking you can see in the report. | |
| `target_selected` | Matches `CrossReferenceTargetState.SELECTED`. | |
| `target_packed` | Matches `CrossReferenceTargetState.PACKED`. | |
| `target_omitted_by_budget` | Matches `CrossReferenceTargetState.OMITTED`. | |
| `target_needed_to_interpret_claim` | A human judgment the system cannot make: without the target, the claim genuinely cannot be correctly interpreted or verified. | "Exemption C" without its Section-4 definition leaves the claim's numeric threshold unverifiable. |
| `target_only_clarifies_claim` | The target adds helpful context but the claim is already interpretable/verifiable without it. | A "see also" style reference to background material. |
| `dependency_closure_complete` | Every target this claim needed was in fact packed. | |
| `dependency_closure_incomplete` | At least one needed target was not packed. | |
| `closure_unresolved` | You cannot tell whether the target was needed from the available context. | |

## D. Evidence-set sizing

Applied per (claim, evidence-set-construction-attempt) -- one label per entry in
`size3_diagnostics`.

| Label | Meaning | Example |
|---|---|---|
| `one_item_sufficient` | A single packed passage genuinely and fully supports the claim -- composition was correctly skipped. | |
| `two_items_sufficient` | The default two-item composition fully and correctly covers the claim. | The worked example in `docs/multi-passage-evidence-demo.md` §3. |
| `three_items_plausibly_required` | The claim plausibly needs a third passage to be fully supported -- check `uncovered_critical_component_ids` and, if run, whether `--diagnostic-max-set-size 3` resolved it. | |
| `more_than_three_items_plausibly_required` | Even a hypothetical size-3 search would not plausibly cover this claim -- record why in your notes; this pass does not search beyond size 3. | |
| `missing_evidence_outside_candidate_pool` | No combination of packed items -- at any size -- would cover the claim, because the needed passage was never retrieved at all. | |
| `set_size_bound_prevented_adequate_composition` | A third item genuinely was available and needed, and the default `max_set_size=2` bound is why it wasn't used -- the diagnostic size-3 search should confirm this. | |
| `candidate_set_redundant` | Additional packed items add nothing beyond what's already covered. | |
| `composition_unresolved` | You cannot tell from the available context whether more evidence would help. | |

## E. Reviewer/workflow value

Applied once per case (a list, not a dict, in the label template -- append as many as
apply).

| Label | Meaning |
|---|---|
| `evidence_set_explanation_useful` | The evidence-set's bounded explanation text helped you understand why it composed/didn't compose. |
| `conflict_explanation_useful` | The conflict-driver explanation helped you judge genuine-vs-artifact. |
| `cross_reference_warning_useful` | The fixed cross-reference warning correctly flagged something worth checking. |
| `extraction_uncertainty_visible` | Low-confidence/uncertain extraction was visible enough in the report that you didn't mistake it for a confident result. |
| `likely_false_reassurance` | The absence of a warning/conflict on this case could plausibly make a reviewer overconfident when they shouldn't be. |
| `likely_unnecessary_escalation` | A warning/conflict fired where, on inspection, nothing needed a reviewer's attention. |
| `reviewer_requested_full_context` | While annotating, you found yourself needing to open the full source document beyond what the report showed. |
| `reviewer_requested_source_expansion` | You found yourself wanting a passage the candidate pool didn't include at all. |
| `reviewer_marked_unresolved` | Overall, this case's correct reviewer outcome is genuinely `unresolved` or `escalate_to_domain_expert` (`core/enums.py::ReviewerAction`, `docs/local-validation-protocol.md`) -- not a failure of annotation, a valid outcome. |

## Annotation process

1. Read the case's `query` and stated constraints (`query_constraints`/
   `user_intent_notes` in the case file).
2. Read the `answer` and its `answer_source_method`/`answer_origin` metadata -- know
   before you start whether this is a real, document-derived answer or a labeled
   controlled perturbation.
3. Examine the candidate evidence (`retrieval_candidates`, `packed_context_items`,
   `omitted_context_items`) and their source locations.
4. Review the field-comparison vectors (`claim_evidence_comparisons`) -- apply
   category A labels.
5. Review the evidence sets (`evidence_sets`) and, for a claim where construction was
   attempted but skipped/incomplete, the rejection reasons implied by
   `evidence_set_metrics` (`sets_discarded_redundant`, `sets_discarded_conflicting`,
   `skip_reason`).
6. Check the conflict-driver explanations (`conflict_explanations`) -- apply category
   B labels.
7. Check the cross-reference target states (`cross_reference_markers`) -- apply
   category C labels.
8. For each warning/evidence-set result, decide whether it is useful, unnecessary,
   unresolved, or needs more source context -- apply category D and E labels.
9. Write a short rationale wherever the label template has a notes/rationale field --
   a label without a rationale is much less useful to a future reader, including
   yourself.
10. A second reviewer, or a later self-review pass with fresh eyes, may resolve
    disputed or uncertain labels. **Two reviewers are not required for this initial
    engineering diagnostic pass** -- but independent second review is advisable before
    treating any finding here as a basis for an implementation-priority decision
    (`docs/real-corpus-diagnostic-runbook.md` step 12,
    `docs/local-validation-protocol.md`'s broader reviewer-study design for why
    independent adjudication matters once conclusions carry more weight).
