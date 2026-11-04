# Evidence selection, truncation, or compression loss prior to generation

**ID**: `PACK_OMISSION_OR_TRUNCATION`  
**Epistemic status**: `trace_integrity_condition`  
**Default evidence grade**: `D_local_empirical`  
**Default activation policy**: `enabled_with_manifest_gates`  
**Pipeline stage**: `packed_context_items`  
**Failure object**: `context_integrity`  
**Registry version**: 0.2.0

## Summary

A candidate that was selected as relevant can still fail to reach the generator because of context-budget truncation or lossy compression before packing. This is reportable as a directly observable trace fact -- distinct from and prior to any claim that it caused a specific answer error.

## Causal claim (as stated)

A selected context item, or a support dependency it carries, was omitted, truncated, or compressed away before the final prompt was constructed. This is a trace-integrity condition: it states what happened in the pipeline, and does not by itself claim the omission caused an answer error unless linked to direct causal evidence or local causal validation.

## Necessary causal ingredients

- Candidate, selected, and packed-context stages are all logged in the trace.
- A selected item or a support dependency it carries was omitted, truncated, or compressed.
- The omitted/truncated material is identifiable (not just an aggregate count).

## Known boundary conditions

- Usable as a trace fact even before a direct, matched answer-error causal effect is established for a given deployment.
- Does not apply when no compression, truncation, or budget-driven omission occurred in the trace.

## Supporting and conflicting evidence records

1 supporting, 0 refuting/mixed, 0 non-committal (direction=null).

### EV-PACK_OMISSION_OR_TRUNCATION-001 (verified, direction=supports)

- **Citation**: Gabin, J., Perez, A., and Parapar, J. "Lost in the Evidence? Reproducing Document Position and Context Size Effects in RAG." Proceedings of the 49th International ACM SIGIR Conference on Research and Development in Information Retrieval (SIGIR '26), Melbourne, VIC, Australia. https://doi.org/10.1145/3805712.3808569
- **Venue / year**: SIGIR '26 / 2026
- **Peer review status**: peer_reviewed
- **Study type**: controlled_comparison
- **Evidence grade**: B2_component_evidence_peer_reviewed
- **Quote** (Section 5.2 ("Impact of Retrieval Quality and Reranking", RQ2), page 6.): "both oracle-passages (all gold-relevant passages) and oracle-sents (only the sentences containing the answer) form the upper bound, clustering a bit above 0.70 F1 across k. This isolates the upper bound attributable to evidence quality, not the LLM capacity."
- **Task**: Question answering under a RAG pipeline, comparing model accuracy across evidence-quality conditions ranging from closed-book, through realistic BM25/reranked retrieval, up to oracle (complete gold-evidence) context, and across varied context sizes (number of retrieved passages).
- **Dataset/corpus**: Natural Questions (NQ) and HotpotQA (via their KILT-formatted and standard releases).
- **Intervention/comparison**: Same queries and generator, evidence condition varied from closed-book (no retrieval) through BM25-retrieved top-k (k in {5,10,25,50,75,100}) up to oracle-passages/oracle-sents (complete gold-relevant evidence), isolating how much of the accuracy gap is attributable to incomplete/imperfect evidence versus generator capability.
- **Observed effect**: On HotpotQA, oracle conditions (complete gold evidence) cluster just above 0.70 F1 across all context sizes, while realistic BM25 retrieval remains substantially lower (roughly 0.45-0.50 F1, Figure 7) -- a large, persistent gap attributable to incomplete evidence reaching the generator, not model capacity.
- **Experimental envelope** (known dimensions only):
  - `rag_presence`: True
  - `retriever_family`: BM25; BM25+E5 dense reranking
  - `candidate_depth`: 100
  - `generator_family`: LLaMA-3.1:8B, Mistral-Nemo:12B
- **Stated limitations**: This is an explicitly reproducibility-focused study: the authors find that context-size and ordering effects are more variable and topic-sample- dependent than prior work reported, and that "conclusions drawn from idealised setups do not always transfer to real-world RAG pipelines" (their own conclusion). It studies evidence completeness/quality broadly (oracle vs. realistic retrieval) rather than specifically instrumenting a selected-but-then-omitted-before-packing trace event; used here as motivating/background support for why omission matters, not as a direct trace-level replication. PACK_OMISSION_OR_TRUNCATION's own epistemic_status remains trace_integrity_condition regardless of this record's grade -- see docs/evidence-grading.md. Second-review pass (2026-09-09, same day, solo contributor): quote and DOI re-checked against the source images captured during extraction; the B2 grade (component evidence, not A-tier) was re-confirmed appropriate given the paper's own reproducibility-focused framing; agreement_status=verified_agreement, no corrections.

## Manifest gates

### MG_PACK_OMISSION_OR_TRUNCATION_01

No manifest-level precondition beyond a RAG pipeline being present; whether candidate/selected/packed stages are actually logged, and whether an omission occurred, are trace-level facts (see the linked TraceTrigger).

_Unknown-data behavior_: Not applicable at the manifest level; see TT_PACK_OMISSION_OR_TRUNCATION_01.


## Trace triggers

### TT_PACK_OMISSION_OR_TRUNCATION_01

Candidate, selected, and packed-context stages are all logged (not null), and at least one selected item is identifiably missing from packed_context_items or present in omitted_context_items/compressed_context_items with an omission_reason.

Causal claim permitted from this trigger alone: **False**

## Allowed vs. prohibited product language

- **Allowed**: language consistent with `trace_integrity_condition`.
- **Prohibited**: presenting this mechanism as a confirmed cause of any specific answer error unless a causal evidence record or local causal validation is directly linked.

## Reviewer actions

- **RA_CONFIRM_OMISSION_MATERIALITY**: A selected context item (or a support dependency it carried) was omitted, truncated, or compressed before the final prompt was built. Confirm whether the omitted material was actually needed for a correct, complete answer.

## Open evidence gaps

- None currently open; all linked evidence records are verified.
