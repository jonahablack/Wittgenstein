# Position-sensitive use of relevant information in packed long context

**ID**: `CTX_POSITION_SENSITIVE_USE`  
**Epistemic status**: `manifest_conditioned_transfer`  
**Default evidence grade**: `A1_direct_causal_peer_reviewed`  
**Default activation policy**: `disabled_by_default_or_research_mode`  
**Pipeline stage**: `packed_context_items`  
**Failure object**: `context_utilization`  
**Registry version**: 0.2.0

## Summary

Language models are known to use information less reliably when it sits in the middle of a long input context, versus the beginning or end. This is direct long-context evidence; it transfers to RAG only when a system packs multiple passages into a sufficiently long prompt.

## Causal claim (as stated)

In sufficiently long input contexts, model accuracy on information placed in the middle of the context is measurably lower than for the same information placed near the beginning or end. In a RAG system, this transfers only when the packed context is long and multiple items are packed -- it is a context-use risk to review, not proof that a specific answer error was position-caused.

## Necessary causal ingredients

- Multiple items are packed.
- Actual prompt token positions/spans are available in the trace.
- Total packed context length meets or exceeds the configured position-risk threshold.
- Answer-supporting material within the packed context is identifiable.

## Known boundary conditions

- Does not apply to a single short packed passage.
- Source evidence is a direct long-context finding, not a RAG-specific experiment; treat as manifest_conditioned_transfer, not directly_matched, unless a RAG-specific replication is added.

## Supporting and conflicting evidence records

1 supporting, 0 refuting/mixed, 0 non-committal (direction=null).

### EV-CTX_POSITION_SENSITIVE_USE-001 (verified, direction=supports)

- **Citation**: Liu, N.F., Lin, K., Hewitt, J., Paranjape, A., Bevilacqua, M., Petroni, F., and Liang, P. "Lost in the Middle: How Language Models Use Long Contexts." Transactions of the Association for Computational Linguistics, vol. 12, pp. 157-173, 2024. https://doi.org/10.1162/tacl_a_00638
- **Venue / year**: Transactions of the Association for Computational Linguistics (TACL), vol. 12 / 2024
- **Peer review status**: peer_reviewed
- **Study type**: causal_intervention
- **Evidence grade**: A1_direct_causal_peer_reviewed
- **Quote** (Section 1 (Introduction), page 158.): "We find that changing the position of relevant information in the input context can substantially affect model performance, indicating that current language models do not robustly access and use information in long input contexts. Furthermore, we observe a distinctive U-shaped performance curve (Figure 1); language model performance is highest when relevant information occurs at the very beginning (primacy bias) or end of its input context (recency bias), and performance significantly degrades when models must access and use information located in the middle of their input context."
- **Task**: Multi-document question answering (controlled placement of the single answer-bearing document within a fixed-size input context) and a synthetic key-value retrieval task.
- **Dataset/corpus**: NaturalQuestions-Open (2,655 queries with paragraph-length annotated long answers); k-1 distractor Wikipedia passages retrieved via Contriever fine-tuned on MS-MARCO.
- **Intervention/comparison**: Position of the single answer-bearing document is systematically placed at the beginning, middle, or end of a fixed set of k documents, with k varied to control input context length. The distractor documents are retrieved, but the position manipulation itself is a controlled placement, not a retrieval outcome -- hence a causal intervention on position specifically.
- **Observed effect**: With relevant information in the middle of the input context, GPT-3.5-Turbo's multi-document QA accuracy is lower than its closed-book (no-documents) accuracy of 56.1%. With 20 total retrieved documents (~4K tokens), accuracy peaks near the y-axis maximum (~75%) when the answer document is 1st and falls back toward the closed-book baseline (~56-57%) for middle positions (Figure 1).
- **Experimental envelope** (known dimensions only):
  - `rag_presence`: False
  - `task_type`: long_context_question_answering
  - `generator_family`: MPT-30B-Instruct, LongChat-13B (16K), GPT-3.5-Turbo, Claude-1.3
- **Stated limitations**: Direct long-context finding using a fixed, non-retrieved document set (rag_presence=false) -- not a RAG-specific experiment. Extended-context models were found "not necessarily better" at this task than shorter-context counterparts; encoder-decoder models were relatively robust only within their training-time sequence length. A separate retriever-reader case study (Section 5) on NaturalQuestions-Open finds performance saturates before retriever recall saturates (~1.5% gain from 20 to 50 documents for GPT-3.5-Turbo, ~1% for Claude-1.3) -- RAG-flavored but distinct from the core controlled-position experiment, and not the finding quoted above. Second-review pass (2026-09-09, same day, solo contributor): quote, DOI, and rag_presence=false classification re-checked against the source images captured during extraction; agreement_status=verified_agreement, no corrections.

## Manifest gates

### MG_CTX_POSITION_SENSITIVE_USE_01

Can activate only if the system is even capable of packing more than one item and the configured context window is known, so a position-length threshold can be evaluated at all.

Required:
- Configured context window token budget is known. (`packing_manifest.context_window_tokens is_known None`)

Disqualifying:
- System never packs more than a single context item. (`selection_manifest.max_selected_items equals 1`)

_Unknown-data behavior_: If packing_manifest.context_window_tokens is unknown, the gate result is unknown_insufficient_data.


## Trace triggers

### TT_CTX_POSITION_SENSITIVE_USE_01

More than one item is actually packed, prompt token positions are logged, total packed length meets the configured threshold, and answer-supporting material is identifiable among the packed items.

Causal claim permitted from this trigger alone: **False**

## Allowed vs. prohibited product language

- **Allowed**: language consistent with `manifest_conditioned_transfer`.
- **Prohibited**: presenting this mechanism as a confirmed cause of any specific answer error unless a causal evidence record or local causal validation is directly linked.

## Reviewer actions

- **RA_CHECK_POSITION_SENSITIVITY**: Answer-supporting material sits at packed position rank {position_rank} of {packed_item_count} in a long packed context. Check whether the answer correctly used this material, independent of its position -- this flag identifies a context- use risk to review, not proof that a position-caused error occurred.

## Open evidence gaps

- None currently open; all linked evidence records are verified.
