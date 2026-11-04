# Unresolved conflicting retrieved evidence

**ID**: `GEN_CONTEXT_CONFLICT_UNRESOLVED`  
**Epistemic status**: `manifest_conditioned_transfer`  
**Default evidence grade**: `B2_component_evidence_peer_reviewed`  
**Default activation policy**: `disabled_by_default_or_research_mode`  
**Pipeline stage**: `answer_claims`  
**Failure object**: `answer_consistency`  
**Registry version**: 0.2.0

## Summary

When packed context contains passages that make incompatible claims (differing entity, predicate, value, polarity, condition, time/version, jurisdiction, or authority), a generator may choose or synthesize a claim without surfacing that a conflict existed, rather than flagging the conflict for the user.

## Causal claim (as stated)

When the packed context contains explicitly identifiable, incompatible claims along a stated conflict dimension, and the answer selects or synthesizes among them without a stated resolution, the answer's reliability on that point is at risk independent of which source (if any) is factually correct. This registry does not encode an automatic rule for which conflicting source is correct.

## Necessary causal ingredients

- The packed context contains normalized, explicitly incompatible claims.
- A specific conflict dimension is identified (entity, predicate, value, polarity, condition, time/version, jurisdiction, or authority).
- The answer chooses or synthesizes a claim without a stated resolution or caveat.

## Known boundary conditions

- Does not determine which conflicting source is correct; that remains a reviewer judgment.
- Primary source is now confirmed (RAG-RewardBench, Jin et al., Findings of ACL 2025, verified 2026-09-09), but it is a reward-model benchmark -- it measures whether a reward model can correctly judge RALM responses to synthesized conflicting evidence, not RALM response behavior directly. Its linked evidence record is therefore direction=null, not supports; a primary source directly measuring RALM-response-level conflict handling against naturally-occurring (not synthesized) multi-source conflicts remains an open literature-search task -- see the dossier's open-evidence-gaps section.

## Supporting and conflicting evidence records

0 supporting, 0 refuting/mixed, 1 non-committal (direction=null).

### EV-GEN_CONTEXT_CONFLICT_UNRESOLVED-001 (verified, direction=null)

- **Citation**: Jin, Z., Yuan, H., Men, T., Cao, P., Chen, Y., Xu, J., Li, H., Jiang, X., Liu, K., and Zhao, J. "RAG-RewardBench: Benchmarking Reward Models in Retrieval Augmented Generation for Preference Alignment." Findings of the Association for Computational Linguistics: ACL 2025, pp. 17061-17090.
- **Venue / year**: Findings of ACL 2025 / 2025
- **Peer review status**: peer_reviewed
- **Study type**: observational_benchmark
- **Evidence grade**: B2_component_evidence_peer_reviewed
- **Quote** (Section 3.1 ("Design of Well-Crafted RAG Scenarios"), "(4) Conflict Robustness", page 17065.): "Given the prevalence of misleading and outdated information, RALMs often struggle with conflicting knowledge (Xie et al., 2024). The reward model should robustly distinguish between correct responses and those misled by inaccurate information."
- **Task**: Benchmarking reward models' (RMs) ability to score/prefer RALM response pairs correctly across eight RAG-specific evaluation subsets, one of which ("conflict robustness") targets responses to retrieved context containing injected counterfactual/conflicting documents.
- **Dataset/corpus**: 18 RAG subsets built on NQ, SimpleQA, ASQA, BioASQ, FreshQA, ExpertQA, MultiFieldQA, HotpotQA, MuSiQue, MultiHop-RAG, ELI5, RobustQA, CRAG, and GPT-4o-synthesized counterfactual documents (for the conflict robustness subset specifically, built on NQ/TriviaQA/PopQA).
- **Intervention/comparison**: 45 reward models (discriminative/generative/implicit) are scored on their ability to correctly rank pairs of RALM-generated responses, per subset, including the conflict-robustness subset (GPT-4o-synthesized counterfactual documents injected as retrieved context).
- **Observed effect**: Best-performing reward model (Skywork-Critic-Llama-3.1-70B) reaches 78.3% overall accuracy across all RAG-RewardBench subsets; on the harmlessness "Conflict" column specifically it scores 82.3/100 (Table 2) -- short of perfect even for the strongest model tested, indicating conflict-robustness judgment remains an unsolved evaluation dimension.
- **Statistical evidence**: Pearson correlation coefficient of 0.79 between judgment models used for preference annotation (page 17066); inter-annotator consistency with human preferences averaged 0.864 (Table 1) across three graduate-level annotators.
- **Experimental envelope** (known dimensions only):
  - `rag_presence`: True
  - `task_type`: reward_model_benchmark_for_rag_preference_alignment
- **Stated limitations**: This is a reward-model benchmark, not a direct measurement of production RALM conflict-resolution failure rates: the "conflict robustness" subset evaluates whether a reward model can correctly judge/prefer a response that handles a synthesized (GPT-4o-generated counterfactual) conflict well -- one step removed from measuring how often RALM-generated answers themselves fail to surface/resolve genuinely conflicting retrieved evidence. direction is recorded as "null" rather than "supports" for this reason: the paper is directly on-topic and motivates its conflict-robustness subset by citing that RALMs struggle with conflicting knowledge (that specific claim is attributed to Xie et al., not independently measured here), but it does not itself report a RALM-response-level conflict-resolution failure rate that would let this record directly support the mechanism's causal claim. A more directly on-point primary source (measuring RALM response behavior, not reward-model judgment accuracy, against naturally-occurring multi-source conflicts rather than synthesized counterfactuals) remains an open literature-search task. Second-review pass (2026-09-09, same day, solo contributor): specifically checked the paper's Table 3 ("Evaluation results of RALMs on RAG-RewardBench, employing the same usage as implicit RMs"), which does report RALM-level scores on the Conflict column (e.g. ChatQA-2-8B: 46.2) -- but confirmed this still measures RALM response probabilities used AS an implicit reward/preference signal, not the RALM's own generated-answer conflict-resolution behavior, so it does not change the direction="null" classification. agreement_status=evidence_does_not_fit_mechanism (extraction itself is accurate and verified; the source's construct does not match the mechanism's exact claim) -- see docs/literature-review-second-review-results.md.

## Manifest gates

### MG_GEN_CONTEXT_CONFLICT_UNRESOLVED_01

Can activate only if the system can pack more than one item (a conflict needs at least two conflicting sources present together).

Required:
- More than one context item can be packed. (`selection_manifest.max_selected_items greater_than 1`)

_Unknown-data behavior_: If selection_manifest.max_selected_items is unknown, the gate result is unknown_insufficient_data.


## Trace triggers

### TT_GEN_CONTEXT_CONFLICT_UNRESOLVED_01

The trace records at least one normalized context_conflicts entry (with an explicit dimension) whose conflict_id is not in conflict_ids_addressed_in_answer.

Causal claim permitted from this trigger alone: **False**

## Allowed vs. prohibited product language

- **Allowed**: language consistent with `manifest_conditioned_transfer`.
- **Prohibited**: presenting this mechanism as a confirmed cause of any specific answer error unless a causal evidence record or local causal validation is directly linked.

## Reviewer actions

- **RA_CHECK_CONFLICT_RESOLUTION**: The packed context contains conflicting claims along dimension "{dimension}", and the answer did not state how it resolved them. Check whether the answer's choice is defensible and whether the conflict should have been surfaced to the user instead of silently resolved.

## Open evidence gaps

- None currently open; all linked evidence records are verified.
