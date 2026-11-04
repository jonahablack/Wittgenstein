# Incomplete multi-hop or multi-evidence support retrieval

**ID**: `RET_MULTIHOP_SUPPORT_INCOMPLETE`  
**Epistemic status**: `manifest_conditioned_transfer`  
**Default evidence grade**: `C_preprint_empirical`  
**Default activation policy**: `disabled_by_default_or_research_mode`  
**Pipeline stage**: `retrieval_candidates`  
**Failure object**: `retrieval_quality`  
**Registry version**: 0.2.0

## Summary

Queries whose correct answer requires combining multiple support propositions or documents can fail when retrieval surfaces only a subset of the required support set.

## Causal claim (as stated)

When a query requires multiple support elements (documents, propositions, or dependency-graph edges) and retrieval returns fewer than the full required set, answer correctness on that query is at elevated risk relative to queries whose full support set was retrieved.

## Necessary causal ingredients

- The query/answer is assessed as requiring multiple support elements (multi-hop or multi-document).
- The trace records a support-set or dependency structure to compare against.
- At least one required support element is absent from the actual retrieved/packed set.

## Known boundary conditions

- Does not apply to queries with known single-span support.
- Benchmark-level (observational) evidence is distinct from a direct causal intervention; do not conflate the two.
- Its one linked evidence record (EV-RET_MULTIHOP_SUPPORT_INCOMPLETE-001) is now graded C_preprint_empirical, not A2: the primary-source PDF examined during the 2026-09-09 literature-review pass is an arXiv preprint with no confirmable peer-review venue marking, so evidence_grade was downgraded per the peer-review-gating rule even though the paper's finding (0.56 vs. 0.89 accuracy under retrieved vs. ground-truth evidence) directly supports the mechanism. epistemic_status remains manifest_conditioned_transfer either way.

## Supporting and conflicting evidence records

1 supporting, 0 refuting/mixed, 0 non-committal (direction=null).

### EV-RET_MULTIHOP_SUPPORT_INCOMPLETE-001 (verified, direction=supports)

- **Citation**: Tang, Y. and Yang, Y. "MultiHop-RAG: Benchmarking Retrieval-Augmented Generation for Multi-Hop Queries." arXiv:2401.15391 (2024). Publicly reported as accepted at COLM 2024, but that acceptance is not confirmed within the arXiv preprint PDF examined in this pass -- treated conservatively as an unconfirmed-peer-review preprint (see peer_review_status/evidence_grade).
- **Venue / year**: arXiv preprint (COLM 2024 acceptance publicly reported but not confirmed from this document) / 2024
- **Peer review status**: preprint
- **Study type**: controlled_comparison
- **Evidence grade**: C_preprint_empirical
- **Quote** (Section 4.2 ("Generation-related Task"), page 6, main text following Table 6.): "the response accuracy rate using the retrieved chunks is not satisfactory, with the state-of-the-art GPT-4 model achieving only 0.56 accuracy. This is expected, because the retrieval component falls short in retrieving relevant evidences from the knowledge base."
- **Task**: Multi-hop question answering over a RAG pipeline (LlamaIndex), comparing generation accuracy when fed retrieved (imperfect) evidence vs. ground-truth (complete) evidence for the same multi-hop queries.
- **Dataset/corpus**: MultiHop-RAG (this paper's own dataset: English news-article knowledge base, 2,556 multi-hop queries requiring 2-4 evidence pieces per Table 4).
- **Intervention/comparison**: Same multi-hop queries answered under two evidence conditions: (1) top-6 retrieved chunks from the full RAG pipeline, vs. (2) the ground-truth supporting evidence set for the query (a ceiling/oracle condition).
- **Observed effect**: GPT-4 generation accuracy: 0.56 with retrieved chunks vs. 0.89 with ground-truth chunks (Table 6) -- a 0.33 absolute accuracy gap attributable to incomplete/imperfect retrieved support. Best retrieval configuration (voyage-02 + bge-reranker-large) reaches only Hits@10=0.7467, Hits@4=0.6625 (Table 5).
- **Experimental envelope** (known dimensions only):
  - `rag_presence`: True
  - `task_type`: multi_hop_question_answering
  - `retriever_family`: dense embedding retrieval (voyage-02 best-performing) with bge-reranker-large
  - `candidate_depth`: 6
  - `generator_family`: GPT-4, ChatGPT (GPT-3.5), Claude-2.1, Google-PaLM, Llama2-70b-chat, Mixtral-8x7B-Instruct
- **Stated limitations**: Benchmark/observational comparison across two evidence conditions, not a per-item randomized intervention; ground-truth evidence for a query is capped at 4 pieces (paper's own stated Limitations section), so may understate difficulty of queries needing more evidence. Peer-review status of this specific document could not be confirmed (see venue note above) -- evidence_grade lowered from the seed's original A2 to C accordingly, per this project's rule that A1/A2 require peer_review_status=peer_reviewed (schemas/evidence.py::EvidenceRecord._a_grade_requires_peer_review). Second-review pass (2026-09-09, same day, solo contributor): the full 14-page document (not just the pages sampled in the first pass) was re-read specifically to search for a COLM 2024 proceedings/camera-ready marking; none was found anywhere in the paper, including its final page. This re-confirms, rather than merely repeats, the preprint classification. agreement_status=verified_agreement, no corrections.

## Manifest gates

### MG_RET_MULTIHOP_SUPPORT_INCOMPLETE_01

No manifest-level precondition beyond the system being a RAG pipeline; the operative conditions for this mechanism are all trace-level (see the linked TraceTrigger).

_Unknown-data behavior_: Not applicable at the manifest level; see TT_RET_MULTIHOP_SUPPORT_INCOMPLETE_01 for the trace-level unknown-data behavior.


## Trace triggers

### TT_RET_MULTIHOP_SUPPORT_INCOMPLETE_01

The query is assessed as multi-hop with an explicit required support-item set, and at least one required item is absent from packed_context_items.

Causal claim permitted from this trigger alone: **False**

## Allowed vs. prohibited product language

- **Allowed**: language consistent with `manifest_conditioned_transfer`.
- **Prohibited**: presenting this mechanism as a confirmed cause of any specific answer error unless a causal evidence record or local causal validation is directly linked.

## Reviewer actions

- **RA_CONFIRM_MULTIHOP_SUPPORT_GAP**: This query was assessed as requiring multiple support elements, and at least one required element is missing from the packed context. Confirm whether the missing element is actually necessary for a correct answer, and whether the answer given is in fact incomplete or incorrect without it.

## Open evidence gaps

- None currently open; all linked evidence records are verified.
