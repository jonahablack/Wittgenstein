# Retrieval-unit segmentation and granularity mismatch

**ID**: `REP_SEGMENTATION_GRANULARITY_MISMATCH`  
**Epistemic status**: `externally_established`  
**Default evidence grade**: `A2_strong_comparative_peer_reviewed`  
**Default activation policy**: `manifest_conditioned`  
**Pipeline stage**: `index_units`  
**Failure object**: `retrieval_quality`  
**Registry version**: 0.3.0

## Summary

The choice of retrieval unit/chunking granularity can change whether a support relation crosses a segment boundary and becomes unrecoverable at query time. Evidence on which granularity is "better" is mixed/contradictory across studies; this registry does not encode any chunking method as universally superior.

## Causal claim (as stated)

When a corpus is retrieved at a segmentation granularity that separates dependent/supporting content across segment boundaries, retrieval can fail to recover the full support needed for a query, independent of retriever quality.

## Necessary causal ingredients

- The corpus uses independently retrievable segments (chunking applied).
- Chunking method and retrieval unit are known from the manifest.
- The trace shows a dependency/support relation crossing a segment boundary, or a segment-to-context mismatch.

## Known boundary conditions

- Does not apply when retrieval unit is a whole document with no sub-document segmentation.
- Two independent, RAG-native, peer-reviewed controlled comparisons (EV-REP_SEGMENTATION_GRANULARITY_MISMATCH-001, -002) converge on the general causal claim -- segmentation/granularity choice measurably affects RAG retrieval and QA reliability -- which is why epistemic_status is now externally_established (as of the 2026-09-09 literature-review pass). This does NOT mean the literature agrees on which specific chunking method or granularity level is best: the two studies test different specific techniques (retrieval-unit type vs. chunk-boundary placement method) and neither claims a universal ranking. Do not present any single method as universally superior.
- As of the 2026-09-09 second-review pass (docs/literature-review-second-review-results.md), both linked evidence records are verification_status=verified (a same-day solo-contributor second pass, disclosed as such). Both were re-confirmed as genuinely independent (no overlapping authors or institutions between Chen et al. and Wang et al.) and genuinely RAG-native.
- GOVERNANCE NOTE (2026-09-09 activation-policy decision, docs/registry-governance.md): default_activation_policy is now manifest_conditioned, not disabled, and not triage_enabled. (1) externally_established is necessary but not sufficient for universal activation -- it certifies the evidence, not the deployment trust level. (2) This mechanism is activated conditionally because transfer from the two studies' envelopes to any specific deployment still depends on that deployment's actual segmentation manifest and observed trace boundary flags -- manifest_conditioned means the risk event is only ever shown when both gate families genuinely pass, never by default assumption. (3) default_activation_policy is a distinct axis from epistemic_status/verification_status: reaching externally_established with verified evidence removes the validator's structural block on activation, but does not itself justify full (triage_enabled) trust -- that requires a separate, deliberate decision, which this is. (4) Promotion to triage_enabled (full, uncapped reviewer-priority weight) requires a LocalValidationRecord establishing reviewer_yield for this mechanism in a specific deployment (docs/research-protocol.md) -- not merely more literature evidence. Until then, manifest_conditioned risk events are shown to reviewers but capped below PriorityTier.HIGH (services/applicability_service.py).
- Activation gates (manifest+trace, matching/eligibility.py::_eval_rep_segmentation_granularity_mismatch, unchanged by this decision -- already implemented all five conditions below at eligibility-evaluation time): (1) retrieval_unit is not whole_document, i.e. independently retrievable segmented units are in use; (2) chunking_method and retrieval_unit are both known from the manifest; (3)+(4) the trace records at least one segment_boundary_dependency_flags entry -- a support/dependency relation crossing a segment boundary, meaning the dependency is actually separated in the retrieval/packing path, not merely hypothetically possible; (5) if any required manifest field is unknown, the result is unknown_insufficient_data, never an assumed pass. The mechanism does NOT activate merely because chunking exists, the corpus is large, the chunker is fixed-size/semantic/propositional, a retrieved passage is short, or the answer is incorrect -- none of those alone satisfy the trace-level boundary-dependency requirement.

## Supporting and conflicting evidence records

2 supporting, 0 refuting/mixed, 0 non-committal (direction=null).

### EV-REP_SEGMENTATION_GRANULARITY_MISMATCH-001 (verified, direction=supports)

- **Citation**: Chen, T., Wang, H., Chen, S., Yu, W., Ma, K., Zhao, X., Zhang, H., and Yu, D. "Dense X Retrieval: What Retrieval Granularity Should We Use?" Proceedings of the 2024 Conference on Empirical Methods in Natural Language Processing (EMNLP 2024), pp. 15159-15177.
- **Venue / year**: EMNLP 2024 / 2024
- **Peer review status**: peer_reviewed
- **Study type**: controlled_comparison
- **Evidence grade**: A2_strong_comparative_peer_reviewed
- **Quote** (Section 6.1 ("Open-domain QA Performance"), page 15165.): "Using propositions rather than passages in the prompts, the four dense retrievers -- SimCSE, Contriever, DPR, and GTR -- improve by +4.1, +3.2, +2.7, and +2.8 in the EM@500 score."
- **Task**: Open-domain QA with retrieval-augmented LLaMA-2-7B, comparing retrieval unit granularity (passage/sentence/proposition) for both passage retrieval and downstream generation.
- **Dataset/corpus**: FactoidWiki (English Wikipedia dump, 2021-10-13, segmented into passages/sentences/propositions); five open-domain QA datasets: NQ, TQA, WebQ, SQuAD, EntityQuestions.
- **Intervention/comparison**: Same corpus indexed at three granularities (passage/sentence/proposition); same four retrievers and same generator; prompt token budget held fixed (l=100 or 500 tokens) across conditions -- an isolated-variable comparison of retrieval-unit granularity.
- **Observed effect**: EM@500 improvement from passage to proposition granularity: +4.1 (SimCSE), +3.2 (Contriever), +2.7 (DPR), +2.8 (GTR), averaged across NQ/TQA/WebQ/SQuAD/EQ (Table 5).
- **Experimental envelope** (known dimensions only):
  - `rag_presence`: True
  - `retriever_family`: SimCSE, Contriever, DPR, GTR (four dual-encoder dense retrievers)
  - `retrieval_unit`: proposition (compared against passage and sentence)
  - `generator_family`: LLaMA-2-7B
- **Stated limitations**: Paper's own stated limitations: corpus restricted to English Wikipedia; only 6 dense dual/bi-encoder retriever types evaluated (no sparse/hybrid); English-only. This record's evidence_grade was raised from the seed's original B1 (mechanistic_transfer) to A2 (strong_comparative) during the 2026-09-09 literature-review pass: B1 is for evidence requiring an extra transfer argument (e.g. a non-RAG finding applied to RAG), but this study directly and RAG-natively measures retrieval and downstream QA metrics under controlled granularity variation, which is what A2 describes. Second-review pass (2026-09-09, same day, solo contributor): re-checked for independence from EV-REP_SEGMENTATION_GRANULARITY_MISMATCH-002 specifically (see that mechanism's known_boundary_conditions) -- no overlapping authors or institutions between the two papers; agreement_status=verified_agreement, no corrections.

### EV-REP_SEGMENTATION_GRANULARITY_MISMATCH-002 (verified, direction=supports)

- **Citation**: Wang, Z., Gao, C., Xiao, C., Huang, Y., Si, S., Luo, K., Bai, Y., Li, W., Duan, T., Lv, C., Lu, G., Chen, G., Qi, F., and Sun, M. "Document Segmentation Matters for Retrieval-Augmented Generation." Findings of the Association for Computational Linguistics: ACL 2025, pp. 8063-8075.
- **Venue / year**: Findings of ACL 2025 / 2025
- **Peer review status**: peer_reviewed
- **Study type**: controlled_comparison
- **Evidence grade**: A2_strong_comparative_peer_reviewed
- **Quote** (Section 5.1 ("Retrieval Performance"), page 8067.): "PIC achieves the highest average retrieval performance across six datasets, with the highest 2-point increase on WebQ. This suggests that our PIC method captures semantic information more effectively, leading to superior retrieval outcomes."
- **Task**: Open-domain QA with retrieval-augmented generation, comparing 5 document chunking methods (sentence/paragraph/fixed-size/semantic/proposition) against the authors' proposed PIC method for both retrieval and end-to-end QA.
- **Dataset/corpus**: PICWiki (English WikiDump processed by the paper's own method) plus six OpenQA benchmarks: NQ, TriviaQA, WebQ, SQuAD, EntityQuestions, PopQA.
- **Intervention/comparison**: Same corpus, retriever, and generators; only the chunking/segmentation method varied (6 methods compared: Table 1 for retrieval, Table 2 for end-to-end QA).
- **Observed effect**: Average Hits@k across 6 datasets: PIC 58.4/69.5 (Top5/Top20) vs. the strongest baseline (Proposition) 57.7/68.9 -- a modest ~0.6-0.7 point average retrieval-level gain (the paper's own headline callout is a 2-point increase specifically on WebQ). End-to-end QA (Table 2, Qwen2.5-7B-Instruct): PIC averages 45.7/48.0 (Top5/Top20) vs. Proposition baseline 42.5/44.3 -- a larger QA-level gain than the retrieval-level gain, and PIC shows a smaller Top20-to-Top5 QA-accuracy drop than the baselines.
- **Experimental envelope** (known dimensions only):
  - `rag_presence`: True
  - `retriever_family`: bge-large-en-v1.5
  - `chunking_method`: PIC (pseudo-instruction-guided semantic chunking), compared against sentence/paragraph/fixed-size/semantic/proposition baselines
  - `generator_family`: Qwen2.5-7B-Instruct, Meta-Llama-3-8B-Instruct
- **Stated limitations**: This evaluates the authors' own proposed method (PIC) against baselines, not a neutral isolated-variable sweep; the retrieval-level improvement over the strongest baseline (proposition-based chunking) is modest (<1 point average). This record's direction was changed from the seed's original speculative "mixed" to "supports" during the 2026-09-09 literature-review pass: after reading both this paper and EV-REP_SEGMENTATION_GRANULARITY_MISMATCH-001 (Chen et al.), they test different specific techniques (chunking-boundary placement vs. retrieval-unit type) but do not contradict each other -- both support the same mechanism-level claim that segmentation/granularity choice measurably affects RAG retrieval and QA reliability. Which specific method is "best" remains unresolved across the literature and is not what this registry claims. Second-review pass (2026-09-09, same day, solo contributor): confirmed the "Proposition" baseline in this paper's own Table 1 is a comparison against Chen et al.'s method, not a collaboration between the two author groups -- this is normal independent-baseline scientific practice and does not undermine the two records' independence (no overlapping authors/institutions); agreement_status=verified_agreement, no corrections.

## Manifest gates

### MG_REP_SEGMENTATION_GRANULARITY_MISMATCH_01

Can activate only if the corpus is retrieved via independently retrievable segments, and chunking method/retrieval unit are known.

Required:
- Chunking method is known. (`retrieval_manifest.chunking_method is_known None`)
- Retrieval unit is known. (`retrieval_manifest.retrieval_unit is_known None`)

Disqualifying:
- Retrieval unit is the whole document, i.e. no sub-document segmentation exists. (`retrieval_manifest.retrieval_unit equals whole_document`)

_Unknown-data behavior_: If chunking_method or retrieval_unit is unknown, the gate result is unknown_insufficient_data.


## Trace triggers

### TT_REP_SEGMENTATION_GRANULARITY_MISMATCH_01

The trace records at least one explicit segment-boundary dependency flag (a support/dependency relation crossing a segment boundary, or a segment-to-context mismatch).

Causal claim permitted from this trigger alone: **False**

## Allowed vs. prohibited product language

- **Allowed**: language consistent with `externally_established`.
- **Prohibited**: presenting this mechanism as a confirmed cause of any specific answer error unless a causal evidence record or local causal validation is directly linked.

## Reviewer actions

- **RA_CHECK_SEGMENTATION_BOUNDARY**: A support/dependency relation was flagged as crossing a retrieval-segment boundary. Check whether the retrieved segments together still supplied everything needed for a correct answer.

## Open evidence gaps

- None currently open; all linked evidence records are verified.
