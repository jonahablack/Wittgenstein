# Query-related hard distractor contamination

**ID**: `RET_HARD_DISTRACTOR`  
**Epistemic status**: `manifest_conditioned_transfer`  
**Default evidence grade**: `A2_strong_comparative_peer_reviewed`  
**Default activation policy**: `disabled_by_default_or_research_mode`  
**Pipeline stage**: `packed_context_items`  
**Failure object**: `answer_correctness`  
**Registry version**: 0.2.0

## Summary

A retrieved/packed passage that is topically related to the query but does not support the answer ("hard distractor") can measurably reduce answer correctness relative to a context without it, independent of simple irrelevant noise.

## Causal claim (as stated)

Packing a query-related, non-supporting passage into the generation context can distract the generator and reduce answer correctness, compared to an otherwise identical context without that passage.

## Necessary causal ingredients

- More than one context item is packed alongside the distractor.
- The distractor is query-related (not random noise).
- The distractor does not support the answer.

## Known boundary conditions

- Does not apply when only a single, short passage is packed (no distractor can coexist).
- Distinct from random/irrelevant noise, which the source evidence treats as a separate condition.
- Effect magnitude and generalization across generator families is not yet confirmed pending quote verification.
- epistemic_status is manifest_conditioned_transfer, not externally_established: only one A2-grade record is linked, and the evidence-threshold rule requires either one A1 study or >=2 independent A1/A2 studies (see docs/evidence-grading.md). A single narrow benchmark is not presented as a universal law.

## Supporting and conflicting evidence records

1 supporting, 0 refuting/mixed, 0 non-committal (direction=null).

### EV-RET_HARD_DISTRACTOR-001 (verified, direction=supports)

- **Citation**: Amiraz, C., Cuconasu, F., Filice, S., and Karnin, Z. "The Distracting Effect: Understanding Irrelevant Passages in RAG." Proceedings of the 63rd Annual Meeting of the Association for Computational Linguistics (Volume 1: Long Papers), pp. 18228-18258. ACL, 2025.
- **Venue / year**: ACL 2025 (Volume 1: Long Papers) / 2025
- **Peer review status**: peer_reviewed
- **Study type**: controlled_comparison
- **Evidence grade**: A2_strong_comparative_peer_reviewed
- **Quote** (Section 4.4 ("Prompting with Relevant and Distracting Passages"), page 18234, main text following Table 1.): "Both weak and hard distracting passages affect accuracy when compared to having only a gold document in the prompt, however, the impact of hard distracting passages is significantly larger, making the accuracy drop from 6 to 11 accuracy points, depending on the LLM. Notably, this degradation persists even for larger LLMs, like Llama-3.3-70B."
- **Task**: Open-domain question answering; LLM prompted with a gold (answer-bearing) passage combined with a distracting passage. Headline result is on NQ (Table 1); the paper's broader distracting-effect measurement also spans TriviaQA, PopQA, and WebQA.
- **Dataset/corpus**: Natural Questions (NQ), TriviaQA, PopQA, WebQA
- **Intervention/comparison**: Within-prompt comparison: gold passage only vs. gold passage + a hard distracting passage (query-related, non-supporting; distracting effect > 0.8) vs. gold passage + a weak distracting passage (distracting effect < 0.2), averaged over both orderings (gold-first and distractor-first) to control for position bias.
- **Observed effect**: Accuracy drop of 6 to 11 percentage points when a hard distracting passage is added to a prompt already containing the gold passage, vs. gold-only (Table 1: e.g. Llama-3.2-3B 82.6% -> 71.5%; Llama-3.1-8B 80.6% -> 73.9%).
- **Statistical evidence**: Wilcoxon signed-rank test, p < 0.01, reported significant for the Gold+HD vs. Gold-only comparison across the LLMs in Table 1 (values not underlined in Table 1 are reported as statistically significant).
- **Experimental envelope** (known dimensions only):
  - `rag_presence`: True
  - `generator_family`: Llama-3.2/3.1/3.3, Falcon-3, Qwen-2.5 (multiple parameter sizes, 3B-70B)
- **Stated limitations**: Distracting effect is measured per-LLM via a probability-of-non-abstention score; the paper notes distracting-effect scores correlate strongly but not perfectly across LLMs (Figure 4), so magnitude may vary by model family. The quoted 6-11 point drop is the NQ result specifically; similar trends are reported for TriviaQA/PopQA/WebQA but their exact accuracy-point drops were not extracted in this pass. Second-review pass (2026-09-09, same day, solo contributor): quote and Table 1 figures re-checked against the source images captured during extraction; agreement_status=verified_agreement, no corrections.

## Manifest gates

### MG_RET_HARD_DISTRACTOR_01

Can activate only if the system's selection policy allows more than one context item to be packed -- a distractor cannot coexist with the supporting passage in a single-item context.

Required:
- More than one context item can be packed. (`selection_manifest.max_selected_items greater_than 1`)

Strengthening (informational only):
- Reranking is disabled, so a distractor is less likely to have been filtered before packing.

_Unknown-data behavior_: If selection_manifest.max_selected_items is unknown, the gate result is unknown_insufficient_data, not assumed satisfied or violated.


## Trace triggers

### TT_RET_HARD_DISTRACTOR_01

At least one packed context item is query-related but not answer-supporting, and both properties are actually assessed (not unknown) in the trace.

Causal claim permitted from this trigger alone: **False**

## Allowed vs. prohibited product language

- **Allowed**: language consistent with `manifest_conditioned_transfer`.
- **Prohibited**: presenting this mechanism as a confirmed cause of any specific answer error unless a causal evidence record or local causal validation is directly linked.

## Reviewer actions

- **RA_COMPARE_WITH_WITHOUT_DISTRACTOR**: A query-related, non-supporting passage is present in the packed context. Compare the answer generated with this passage included against the answer generated with it removed. Does removing it change correctness or attribution?

## Open evidence gaps

- None currently open; all linked evidence records are verified.
