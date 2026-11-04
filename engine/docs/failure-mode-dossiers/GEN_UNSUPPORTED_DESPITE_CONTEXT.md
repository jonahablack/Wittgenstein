# Unsupported answer generation despite relevant packed evidence

**ID**: `GEN_UNSUPPORTED_DESPITE_CONTEXT`  
**Epistemic status**: `manifest_conditioned_transfer`  
**Default evidence grade**: `C_preprint_empirical`  
**Default activation policy**: `disabled_by_default_or_research_mode`  
**Pipeline stage**: `answer_to_evidence_support_edges`  
**Failure object**: `answer_attribution`  
**Registry version**: 0.2.0

## Summary

A generator can produce an answer claim that is not supported by the packed context even when genuinely supporting material was present and packed. This is defined structurally, via answer-to-evidence support edges -- "hallucination" is not used as a sufficient formal definition on its own.

## Causal claim (as stated)

An answer claim can lack a supporting answer-to-evidence edge to any packed context item, even when a packed item that could support a correct answer to the query was present in the final prompt.

## Necessary causal ingredients

- The packed context contains at least one item assessed as capable of supporting a correct answer.
- The produced answer claim has no support edge to any packed context item, or its support edge is assessed as unsupported/contradicted.

## Known boundary conditions

- Distinct from cases where no supporting material was ever packed (that is a retrieval/packing failure, not this mechanism).
- 'Hallucination' alone is not treated as a sufficient formal trigger; the support-edge structure must actually be evaluated.
- Its linked evidence record (EV-GEN_UNSUPPORTED_DESPITE_CONTEXT-001, Wallat et al. 2024, verified 2026-09-09) studies a related but distinct phenomenon -- citation faithfulness (does an existing, textually-correct citation reflect genuine causal reliance) rather than this mechanism's exact claim (an answer claim with NO support edge at all despite genuinely supporting material being packed) -- so it is linked with direction=null, not supports. A primary source directly measuring the zero-support-edge claim remains an open literature-search task; see the dossier's open-evidence-gaps section. Wallat et al.'s correctness-vs-faithfulness distinction also surfaces a candidate future refinement to AnswerSupportEdge.support_status (schemas/trace.py), not acted on in this pass.

## Supporting and conflicting evidence records

0 supporting, 0 refuting/mixed, 1 non-committal (direction=null).

### EV-GEN_UNSUPPORTED_DESPITE_CONTEXT-001 (verified, direction=null)

- **Citation**: Wallat, J., Heuss, M., de Rijke, M., and Anand, A. "Correctness is not Faithfulness in RAG Attributions." arXiv:2412.18004 (2024).
- **Venue / year**: arXiv preprint (no confirmed peer-reviewed proceedings version found in the PDF examined) / 2024
- **Peer review status**: preprint
- **Study type**: causal_intervention
- **Evidence grade**: C_preprint_empirical
- **Quote** (Section 5 ("Post-Rationalization - A Study of Unfaithful Behavior"), Results, page 11.): "the number of adversarial documents cited is much higher when forging relevant but uncited documents (57%) and documents cited for different reasons (55%). Based on our results, we conjecture post-rationalization to be a common phenomenon."
- **Task**: Attributed question answering with a RAG-optimized LLM (Cohere Command-R+), studying whether citations reflect genuine causal reliance on the cited document ("citation faithfulness") as opposed to merely being textually correct ("citation correctness").
- **Dataset/corpus**: NaturalQuestions QA (1,444 real user questions); temporally-aligned KILT Wikipedia dump, split into 100-token chunks, BM25 top-30 reranked by ColBERT v2 to a final top-5 packed into the prompt.
- **Intervention/comparison**: A short factual statement previously cited from one document is adversarially appended to a different document (three conditions: random document, a relevant-but-never-cited document, a document cited for a different reason), the answer is regenerated, and the model's new citation behavior toward the adversarial document is observed.
- **Observed effect**: Adversarial document cited in 12% (116/936) of random-document cases, 57% (273/476) of relevant-but-not-originally-cited cases, and 55% (290/525) of cited-for-other-reason cases -- the much higher rates for the latter two conditions are the paper's evidence for common post-rationalization (a citation that is textually correct but was not the actual cause of the generated statement).
- **Experimental envelope** (known dimensions only):
  - `rag_presence`: True
  - `retriever_family`: BM25 + ColBERT v2 reranking
  - `packing_method`: top-5 reranked chunks
  - `generator_family`: Cohere Command-R+ (104B parameters, 128k context, 4-bit quantized)
- **Stated limitations**: Scope mismatch, recorded honestly rather than forced to fit: this paper's "post-rationalization" phenomenon (an EXISTING citation that looks textually correct but is not causally faithful) is adjacent to, not the same as, GEN_UNSUPPORTED_DESPITE_CONTEXT's current definition (an answer claim with NO support edge at all despite genuinely supporting material being packed). It reveals a related blind spot in this project's own AnswerSupportEdge.support_status field (schemas/trace.py), which currently only asks whether a citation is correct/supported, not whether it is causally faithful -- worth a future registry-governance discussion, not implemented in this pass. direction is set to "null" (not "supports") because this record does not itself demonstrate the mechanism's exact claim. Single-model (Command-R+), single-dataset (NaturalQuestions) study; the authors themselves call the empirical analysis limited and call for replication across models/datasets (Section 7). Peer-review status could not be confirmed from the PDF in hand (arXiv:2412.18004v1, no proceedings footer found in the pages examined) -- graded conservatively as preprint. A primary source directly measuring "answer claim with zero support edge despite available supporting material" remains an open literature-search task. Second-review pass (2026-09-09, same day, solo contributor): the complete 19-page document (all pages, not just those sampled in the first pass) was re-read; no proceedings/camera-ready marking was found anywhere, including the bibliography's final page -- this re-confirms the preprint classification. Page 8 (not read in the first pass) further reinforces the scope-mismatch finding: it explicitly contrasts "faithful (right for the right reason)" against "post-rationalized but correct (right for the wrong reason)," confirming this paper's phenomenon is about existing citations being right-for-the-wrong-reason, not about zero-support-edge claims. agreement_status=evidence_does_not_fit_mechanism (extraction itself is accurate and verified; the source's construct does not match the mechanism's exact claim) -- see docs/literature-review-second-review-results.md.

## Manifest gates

### MG_GEN_UNSUPPORTED_DESPITE_CONTEXT_01

No manifest-level precondition beyond a RAG pipeline being present with a generation stage; the operative conditions are trace-level answer-support facts.

_Unknown-data behavior_: Not applicable at the manifest level; see TT_GEN_UNSUPPORTED_DESPITE_CONTEXT_01.


## Trace triggers

### TT_GEN_UNSUPPORTED_DESPITE_CONTEXT_01

At least one packed_context_items entry is assessed as answer-supporting, and at least one answer_claims entry has no support_status=supported edge to any packed item.

Causal claim permitted from this trigger alone: **False**

## Allowed vs. prohibited product language

- **Allowed**: language consistent with `manifest_conditioned_transfer`.
- **Prohibited**: presenting this mechanism as a confirmed cause of any specific answer error unless a causal evidence record or local causal validation is directly linked.

## Reviewer actions

- **RA_CONFIRM_ANSWER_SUPPORT_EDGE**: An answer claim has no confirmed supporting edge to any packed context item, even though at least one packed item was assessed as capable of supporting a correct answer. Confirm whether the claim is actually supported by material present in the context, misattributed, or genuinely unsupported.

## Open evidence gaps

- None currently open; all linked evidence records are verified.
