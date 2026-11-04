# Literature Review Execution Plan

Status: plan only — no `data/registry/` edits have been made yet. Written per
`docs/literature-review-protocol.md` before extraction begins, covering all 8
placeholder `EvidenceRecord`s in `data/registry/evidence_records.seed.yaml`.

## Candidate changes from the seed file's original citations

Two records' original candidate citations are revised here, based on locating and
reading the actual primary sources (not on title-guessing):

- **`EV-PACK_OMISSION_OR_TRUNCATION-001`** had no identified candidate at all
  (`title: "TODO: identify candidate..."`). This plan proposes
  `gabin_2026_lostevidencereproducing` ("Lost in the Evidence? Reproducing Document
  Position and Context Size Effects in RAG," SIGIR '26), found in the parent
  workspace's `literature/` collection and confirmed by reading it to directly study
  context-size (truncation/budget) effects on RAG output quality under realistic,
  retriever-mediated (not oracle) conditions.
- **`EV-GEN_UNSUPPORTED_DESPITE_CONTEXT-001`** had a candidate ("RAGTruth," Wu et al.
  ACL 2024) that the seed file itself flags as drawn from general bibliographic
  knowledge rather than supplied, and it is not present in the local `literature/`
  collection — it cannot be verified without an unverifiable external fetch. This plan
  proposes `wallat_2024_correctnessnotfaithfulness` ("Correctness is not Faithfulness
  in RAG Attributions"), present locally and read to confirm topical fit, with the
  scope caveat noted in item 8 below.

One record's original candidate is **reconsidered and then reconfirmed**:
`EV-GEN_CONTEXT_CONFLICT_UNRESOLVED-001`'s candidate ("RAG-RewardBench") was seeded as
unconfirmed. Initial title-matching suggested `yamin_2025_canllmsreconcile` ("Can LLMs
Reconcile Knowledge Conflicts in Counterfactual Reasoning?") as a possible substitute,
but reading it shows it studies a **different mechanism**: parametric-knowledge-vs.
single-in-context-premise conflict during counterfactual multi-hop reasoning
(the paper's own "context-ignoring" / "context-overfitting" failure modes), not
conflict *among multiple retrieved passages*. That is not what
`GEN_CONTEXT_CONFLICT_UNRESOLVED` claims (packed context containing incompatible
retrieved claims). Reading the original candidate, `jin_2025_ragrewardbenchbenchmarking`
("RAG-RewardBench: Benchmarking Reward Models in Retrieval Augmented Generation for
Preference Alignment," Findings of ACL 2025), confirms it is peer-reviewed and directly
on-topic — it designs an explicit "conflict robustness" evaluation scenario for exactly
this phenomenon. The original candidate is retained; see item 7.

## Candidate new mechanism found (not added this pass)

`yamin_2025_canllmsreconcile` is strong evidence for a mechanism **absent from the
registry**: an answer claim can resolve a conflict between the model's parametric
knowledge and a single in-context premise/fact incorrectly (defaulting to stored
knowledge — "context-ignoring" — or over-applying the premise past its actual scope —
"context-overfitting"), independent of any conflict *among* retrieved passages. This is
conceptually the "parametric/context knowledge conflict" item from family 4 of the
original registry-design ontology, which was never seeded as its own
`FailureMechanism`. Per instructions, this is **not** added to the registry in this
pass. Proposed for a future pass, inactive pending review:

- Working id: `GEN_PARAMETRIC_CONTEXT_CONFLICT_MISRESOLUTION`
- Working canonical name: "Parametric-vs-context knowledge conflict misresolution"
- Working causal claim: when in-context information conflicts with a model's
  parametric knowledge, the model can resolve the conflict incorrectly in either
  direction — ignoring the context (reverting to stored knowledge) or over-applying it
  beyond its actual logical scope (dropping still-valid parametric facts that don't
  conflict) — with degraded multi-hop accuracy in both directions.
- Would start `research_hypothesis` / `E_hypothesis` / disabled, pending its own
  literature-review pass (`yamin_2025_canllmsreconcile` alone is one preprint; the
  paper's own related-work section names further candidate sources: Yuan et al. 2024,
  Xie et al. context-vs-parametric priority studies, Longpre et al. — none yet located
  or verified here).
- Distinct from `GEN_CONTEXT_CONFLICT_UNRESOLVED` (source-vs-source, within packed
  context) — per the mechanism/subtype rule (`docs/registry-governance.md`), this is a
  different causal pathway and a different reviewer action ("does the answer correctly
  prioritize an explicit in-context override" vs. "did the answer surface/resolve a
  cross-source disagreement"), so it is a separate mechanism, not a subtype.

## The 8 evidence records

### 1. `EV-RET_HARD_DISTRACTOR-001` → `RET_HARD_DISTRACTOR`

1. **Candidate paper**: Amiraz, Cuconasu, Filice, Karnin, "The Distracting Effect:
   Understanding Irrelevant Passages in RAG," ACL 2025 (Volume 1: Long Papers), pp.
   18228–18258.
2. **Source**: `literature/amiraz_2025_distractingeffectunderstanding/paper.pdf`
   (local; title/authors/venue/pages confirmed by reading pages 1–2).
3. **Verification tasks**: confirm ACL Anthology persistent ID; extract the
   quantifiable "distracting effect" definition and the reported accuracy-reduction
   result comparing distracting vs. non-distracting/random-irrelevant passages.
4. **Claims to verify**: that a query-related-but-non-supporting ("hard distracting")
   passage measurably reduces answer accuracy when packed alongside a supporting
   passage, distinct from random/irrelevant noise.
5. **Envelope fields**: task (open QA), retriever(s)/reranker used to obtain
   distractors, `candidate_depth`/`top_k` if stated, generator(s) tested, whether
   fine-tuning was involved (their contribution 3 is a fine-tuning use of distractors —
   keep the *measurement* result separate from the *fine-tuning-benefit* result).
6. **Outcome fields**: the DE_q(p) distracting-effect metric definition; the reported
   accuracy delta (paper's abstract states "up to a 7.5% increase in answering
   accuracy" for the fine-tuning application — need the separate base-rate distraction
   effect number from the main measurement section, not just the fine-tuning result).
7. **Expected grade**: A2 (strong controlled comparison; check whether any result rises
   to A1 causal-intervention strength — the DE_q(p) measurement across passage
   presence/absence looks like a controlled intervention).
8. **RAG-native**: yes (`rag_presence=True`) — this is a RAG-specific study throughout.
9. **May support `externally_established`?**: not alone — one record cannot pass the
   two-path threshold (needs a second independent qualifying record). Stays
   `manifest_conditioned_transfer` after this pass unless a second A1/A2 RAG-native
   supporting record is found.
10. **Boundary conditions / contradictory evidence to search for**: the paper's own
    §2 "Related Work" distinguishes hard distractors from random noise
    (Cuconasu et al. 2024) — check whether that source (`cuconasu_2025_doragsystems` is
    also in the local corpus) shows the same or a conflicting effect size; note if so
    for a future evidence record rather than conflating into this one.

### 2. `EV-RET_MULTIHOP_SUPPORT_INCOMPLETE-001` → `RET_MULTIHOP_SUPPORT_INCOMPLETE`

1. **Candidate paper**: Tang, Yang, "MultiHop-RAG: Benchmarking Retrieval-Augmented
   Generation for Multi-Hop Queries."
2. **Source**: `literature/tang_2024_multihopragbenchmarking/paper.pdf` (local; the PDF
   in hand is the arXiv preprint, arXiv:2401.15391, dated 27 Jan 2024 — no proceedings
   footer visible on pages 1–3). The seed file's candidate venue ("COLM 2024") is
   **not confirmed by this PDF** and must be treated as unconfirmed pending either
   locating a COLM-branded version or independent confirmation; peer-review status
   will be graded conservatively (`preprint`) unless confirmed otherwise.
3. **Verification tasks**: search the remainder of the PDF for any COLM
   acceptance/copyright notice; if none found, keep `peer_review_status=preprint`.
4. **Claims to verify**: that existing RAG retrieval/generation is measurably worse on
   multi-hop queries (requiring multiple supporting documents) than the benchmark's
   single/full-support baseline — the specific retrieval-evaluation and
   generation-evaluation numbers from their two experiments.
5. **Envelope fields**: retriever(s)/embedding models compared, `candidate_depth`/top-k,
   generators tested (GPT-4, GPT-3.5, PaLM, Claude-2, Llama2-70B, Mixtral-8x7B per
   abstract), corpus (news-article knowledge base), query types (inference/comparison/
   temporal/null).
6. **Outcome fields**: MAP@K / MRR@K / Hit@K retrieval numbers and the
   response-evaluation numbers from their two experiments, exactly as reported.
7. **Expected grade**: A2 at best (observational/benchmark comparison, not a designed
   causal intervention) — the seed's current A2 is plausible; verify against the
   study-type decision order in `docs/literature-review-protocol.md`.
8. **RAG-native**: yes.
9. **May support `externally_established`?**: no — single record, and grade ceiling is
   A2 not A1, so it cannot satisfy either path of the two-path rule alone.
10. **Boundary conditions**: benchmark/observational evidence conflates retrieval
    quality with reasoning quality — note explicitly that this doesn't isolate "missing
    support caused the error" from "the model couldn't reason over multiple hops even
    when given full support"; search for whether the paper reports a full-support
    control condition that isolates retrieval incompleteness specifically.

### 3. `EV-CTX_POSITION_SENSITIVE_USE-001` → `CTX_POSITION_SENSITIVE_USE`

1. **Candidate paper**: Liu, Lin, Hewitt, Paranjape, Bevilacqua, Petroni, Liang, "Lost
   in the Middle: How Language Models Use Long Contexts," TACL 2024.
2. **Source**: `literature/liu_2024_lostmiddlehow/paper.pdf` (local; confirmed: TACL
   vol. 12, pp. 157–173, DOI `10.1162/tacl_a_00638`, CC-BY 4.0 — peer-reviewed journal,
   visible on page 1 footer).
3. **Verification tasks**: extract the exact U-shaped-curve finding statement and the
   closed-book-vs.-worst-position comparison number quoted in the introduction.
4. **Claims to verify**: that accuracy is highest when the answer-bearing document is
   at the start or end of the input context and significantly lower when it is in the
   middle, for multi-document QA.
5. **Envelope fields**: models tested (MPT-30B-Instruct, LongChat-13B(16K), GPT-3.5-
   Turbo, Claude-1.3), number of documents/context length levels, task (multi-document
   QA on NaturalQuestions-Open + a synthetic key-value retrieval task), whether this is
   retrieval-augmented or oracle/fixed-document-set (fixed set — confirms
   `rag_presence=False` for the core position experiment; §5's retriever-reader case
   study is a separate, more RAG-like result worth extracting as a second data point
   within the same record's `stated_limitations`, not a separate envelope).
6. **Outcome fields**: the specific accuracy numbers at each document position (Figure
   1 shows the shape; get the closed-book baseline number, 56.1%, already visible, and
   the peak/trough numbers), plus the §5 finding that performance saturates well before
   retriever recall saturates (the ~1.5%/~1% marginal-improvement numbers already
   visible on page 3).
7. **Expected grade**: A1 (peer-reviewed, controlled causal intervention on document
   position) — matches the seed's current grade.
8. **RAG-native**: no for the core experiment (`rag_presence=False`, confirmed:
   "exactly one of the documents contains the answer... k-1 distractor documents," a
   fixed/oracle multi-document set, not an end-to-end retrieval pipeline). The §5
   case study is retriever-based but is a secondary result. Keep `rag_presence=False`
   on the primary envelope, consistent with the seed's existing, correct classification.
9. **May support `externally_established`?**: no — non-RAG-native evidence is capped
   at `manifest_conditioned_transfer` by the validator rule regardless of grade.
10. **Boundary conditions**: note the paper's own finding that extended-context models
    are "not necessarily better at using their input context" (i.e. longer context
    windows don't fix this) and that encoder-decoder models were relatively robust
    within their training-length window — both are real boundary/moderator conditions
    to record, not omit.

### 4. `EV-REP_SEGMENTATION_GRANULARITY_MISMATCH-001` → `REP_SEGMENTATION_GRANULARITY_MISMATCH`

1. **Candidate paper**: Chen, Wang, Chen, Yu, Ma, Zhao, Zhang, Yu, "Dense X Retrieval:
   What Retrieval Granularity Should We Use?," EMNLP 2024.
2. **Source**: `literature/chen_2024_densexretrieval/paper.pdf` (local; confirmed:
   EMNLP 2024 proceedings, pp. 15159–15177).
3. **Verification tasks**: extract the Recall@20 improvement numbers already visible on
   page 2 (+10.1 unsupervised, +2.7 supervised) with their exact surrounding sentence;
   confirm which retrievers (Contriever, GTR) and which comparison (proposition vs.
   passage) those numbers refer to.
4. **Claims to verify**: that indexing/retrieving at proposition-level granularity
   outperforms passage-level granularity, i.e. that granularity choice materially
   changes retrieval (and downstream QA) quality.
5. **Envelope fields**: retrieval unit levels compared (passage/sentence/proposition),
   retrievers (Contriever, GTR — both dual-encoder dense), corpus (FactoidWiki, a
   processed English Wikipedia dump), downstream QA datasets (five open-domain QA
   benchmarks per abstract).
6. **Outcome fields**: Recall@k numbers, EM@k numbers (Figure 1 shows an EM@500 panel),
   with exact deltas.
7. **Expected grade**: the seed's current B1 looks too conservative given this is a
   direct, controlled, peer-reviewed comparison of retrieval unit granularity on
   retrieval and QA metrics — re-assess toward A2 during extraction, but only if the
   comparison is a clean controlled one and not a "mechanistic transfer" case (B1 is
   for evidence that requires a transfer argument, e.g. non-RAG); this study directly
   measures RAG-relevant retrieval/QA metrics, so B1 may have been an under-grade.
   Assign conservatively based on what's actually found, not the pre-existing label.
8. **RAG-native**: yes.
9. **May support `externally_established`?**: only in combination with record 5 below
   if both turn out to be genuinely independent, broadly consistent, A1/A2-qualifying,
   RAG-native, `supports`-direction records (path B of the two-path rule) — assess
   after both are extracted; do not assume.
10. **Boundary conditions**: the mechanism's own text warns findings on "best"
    granularity are mixed across the literature — record whether this paper's
    proposition-level claim is qualified (e.g. added indexing/storage cost, applicable
    corpus types) rather than presented as a universal recommendation.

### 5. `EV-REP_SEGMENTATION_GRANULARITY_MISMATCH-002` → `REP_SEGMENTATION_GRANULARITY_MISMATCH`

1. **Candidate paper**: Wang, Gao, Xiao, Huang, Si, Luo, Bai, Li, Duan, Lv, Lu, Chen,
   Qi, Sun, "Document Segmentation Matters for Retrieval-Augmented Generation,"
   Findings of ACL 2025.
2. **Source**: `literature/wang_2025_documentsegmentationmatters/paper.pdf` (local;
   confirmed: Findings of ACL 2025, pp. 8063–8075).
3. **Verification tasks**: extract the specific Hits@k and Exact-Match improvement
   numbers for their proposed method (PIC) vs. baseline (fixed-length/rule-based)
   chunking.
4. **Claims to verify**: on first read, this paper's framing ("larger chunks may
   include irrelevant information... smaller chunks may lack sufficient semantic
   information," "suboptimal splits") is about the *same* underlying phenomenon as
   record 4 (segmentation/chunking boundary placement affecting what's recoverable at
   query time), not a contradictory finding — the seed file's placeholder `direction:
   mixed` was a speculative guess made before either paper was read and should be
   re-examined against the actual extracted claim, not assumed. If, after extraction,
   both records support the same general causal claim (chunking granularity/boundary
   choice affects RAG reliability) without disagreeing on a specific point, `direction`
   for this record should likely become `supports`, and the mechanism's
   `evidence_synthesis` should be reconsidered (`mixed` requires genuine disagreement,
   not merely two different specific methods).
5. **Envelope fields**: chunking baseline methods compared against, corpus (PICWiki,
   derived from English WikiDump), QA benchmarks, retrievers used for the Hits@k
   evaluation.
6. **Outcome fields**: Hits@k deltas, EM deltas, exact numbers as reported.
7. **Expected grade**: B1/B2 pending read — this compares a new chunking *method*
   against baselines, closer to component evidence (B2) than a clean isolated-variable
   granularity comparison (which is closer to what record 4 is); assign based on actual
   study design once read.
8. **RAG-native**: yes.
9. **May support `externally_established`?**: see item 9 above (record 4) — assess
   jointly once both are extracted.
10. **Boundary conditions**: note whether the paper's summary metric requires their own
    LLM-generated pseudo-instruction/summary step (a cost/dependency worth recording as
    a boundary condition, distinct from a pure passive chunking-size claim).

### 6. `EV-PACK_OMISSION_OR_TRUNCATION-001` → `PACK_OMISSION_OR_TRUNCATION`

1. **Candidate paper** (revised — see "Candidate changes" above): Gabín, Perez,
   Parapar, "Lost in the Evidence? Reproducing Document Position and Context Size
   Effects in RAG," SIGIR '26.
2. **Source**: `literature/gabin_2026_lostevidencereproducing/paper.pdf` (local;
   confirmed: SIGIR '26 proceedings, ACM, DOI `10.1145/3805712.3808569`, CC-BY-NC-ND).
3. **Verification tasks**: extract the specific context-size (number of retrieved
   passages / k) effect-on-accuracy findings, separated from the ordering/position
   findings (this paper studies both; `PACK_OMISSION_OR_TRUNCATION` needs the
   context-size/budget result specifically, not the ordering result — that belongs
   conceptually with `CTX_POSITION_SENSITIVE_USE`, but adding a second evidence record
   to that mechanism is out of scope for this pass per the instructions; note the
   opportunity in the results doc instead).
4. **Claims to verify**: whether/how reducing available context size (a proxy for
   truncation/budget-driven omission) measurably changes downstream QA accuracy, and
   under what retrieval-quality conditions.
5. **Envelope fields**: datasets (NQ, HotpotQA), retriever (dense reranking mentioned
   in abstract), model (LLaMA-3.1-8B per page 2), context sizes tested (5 to 100
   passages, visible in Figure 1/2 axes), topic-sampling/calibration procedure (their
   own methodological contribution — relevant as a limitation/caveat on any other
   context-size study that used fewer topics).
6. **Outcome fields**: ΔF1 numbers across context sizes (visible in Figure 1/2), and
   any accuracy-vs-context-size main-result numbers found in later sections (need pages
   beyond 3).
7. **Expected grade**: this is a *reproducibility* study explicitly built to test
   whether prior context-size/ordering claims are robust — grade conservatively; likely
   B1/B2 (peer-reviewed, but reproduces/complicates rather than establishing a novel
   direct effect) rather than A1/A2, pending the main results.
8. **RAG-native**: yes — explicitly studies "a more realistic RAG scenario in which
   relevance is mediated by a retriever rather than oracle access to gold documents."
9. **May support `externally_established`?**: `PACK_OMISSION_OR_TRUNCATION`'s
   `epistemic_status` is `trace_integrity_condition`, which per
   `docs/evidence-grading.md` does not require or use external evidence for its core
   function — this record remains a supporting/motivating citation, not a load-bearing
   one for activation. No status change expected regardless of grade.
10. **Boundary conditions**: this paper's own conclusion — "conclusions drawn from
    idealised setups do not always transfer to real-world RAG pipelines" — is itself a
    boundary condition worth recording almost verbatim: it means any *other* study's
    context-size claim (idealized/oracle setup) should be treated cautiously until
    replicated under realistic retrieval, which directly reinforces this project's own
    manifest-conditioned-transfer discipline.

### 7. `EV-GEN_CONTEXT_CONFLICT_UNRESOLVED-001` → `GEN_CONTEXT_CONFLICT_UNRESOLVED`

1. **Candidate paper** (reconfirmed after considering and rejecting a substitute — see
   above): Jin, Yuan, Men, Cao, Chen, Xu, Li, Jiang, Liu, Zhao, "RAG-RewardBench:
   Benchmarking Reward Models in Retrieval Augmented Generation for Preference
   Alignment," Findings of ACL 2025.
2. **Source**: `literature/jin_2025_ragrewardbenchbenchmarking/paper.pdf` (local;
   confirmed: Findings of ACL 2025, pp. 17061–17090).
3. **Verification tasks**: locate the "conflict robustness" scenario's construction
   method and any reported statistic on how often base RALM responses fail it (as
   opposed to only reward-model judging accuracy on it).
4. **Claims to verify**: this is a reward-model benchmark, not a direct RALM-behavior
   study — the claim it can support is narrower than the mechanism's ideal form. Verify
   exactly what "conflict robustness" measures (does it test whether a *response*
   correctly prioritizes truthful facts over conflicting retrieved noise, i.e. does it
   provide response-level pass/fail data suitable as evidence for
   `GEN_CONTEXT_CONFLICT_UNRESOLVED`, or only reward-model preference-accuracy data one
   step removed?). This distinction determines `study_type` and grade.
5. **Envelope fields**: the four scenario types (multi-hop reasoning, fine-grained
   citation, appropriate abstain, conflict robustness), 18 RAG subsets, 6 retrievers,
   24 RALMs tested, 45 reward models evaluated.
6. **Outcome fields**: the reward-model accuracy figures already visible (78.3% top
   RM), and — if present — any conflict-robustness-specific pass rate for RALM
   responses themselves (need pages beyond 2).
7. **Expected grade**: likely B2 (component evidence — evaluates reward models'
   ability to detect the failure, one step removed from directly measuring RALM
   conflict-resolution failure rates) unless a direct RALM-response conflict-handling
   statistic is found, in which case reconsider upward.
8. **RAG-native**: yes.
9. **May support `externally_established`?**: no — single record, grade ceiling likely
   below A1/A2 once read; stays `manifest_conditioned_transfer`.
10. **Boundary conditions**: this benchmark evaluates reward models, not production
    RALM behavior directly — record this scope limitation explicitly in the dossier so
    the mechanism's claim isn't overstated relative to what was actually measured.

### 8. `EV-GEN_UNSUPPORTED_DESPITE_CONTEXT-001` → `GEN_UNSUPPORTED_DESPITE_CONTEXT`

1. **Candidate paper** (revised — see "Candidate changes" above): Wallat, Heuss, de
   Rijke, Anand, "Correctness is not Faithfulness in RAG Attributions."
2. **Source**: `literature/wallat_2024_correctnessnotfaithfulness/paper.pdf` (local;
   PDF in hand is arXiv:2412.18004v1, 23 Dec 2024 — no proceedings footer visible on
   pages 1–3; peer-review status to be graded conservatively pending further check).
3. **Verification tasks**: extract the exact "up to 57% of citations" post-
   rationalization statistic and its precise definition/measurement method
   (§4/§5, not yet read).
4. **Claims to verify — scope caveat, stated up front per instructions not to force
   fit**: this paper's central claim is narrower than and adjacent to, not identical
   to, `GEN_UNSUPPORTED_DESPITE_CONTEXT`'s current definition. The mechanism claims an
   answer claim can have **no support edge at all** to any packed item despite
   supporting material being present. Wallat et al. instead study citations that
   are **correct** (the cited document does support the statement) but **unfaithful**
   (the citation doesn't reflect the model's actual generation process —
   "post-rationalization"). That is evidence that generators can produce
   claims not genuinely grounded in packed evidence even when a technically-adequate
   citation exists — related to, but not a direct test of, the registry's exact
   structural "zero support edge" definition. This will be recorded honestly as
   partial/component support, not forced into a full match.
5. **Envelope fields**: models tested, datasets/QA benchmarks used, how "faithfulness"
   is operationally measured (their stated experiment design, not yet read).
6. **Envelope/outcome fields still needed**: exact experimental setup and the 57%
   figure's precise denominator (per-citation? per-answer?).
7. **Expected grade**: B2 (component evidence — measures a related-but-narrower
   phenomenon, not a direct controlled test of the registry's exact claim) rather than
   the seed's current A2; downgrade expected and will be applied unless the full read
   reveals a more direct match than the abstract suggests.
8. **RAG-native**: yes.
9. **May support `externally_established`?**: no — single record, and the expected
   grade downgrade (B2) removes it from the A1/A2 floor entirely, so it cannot ground
   `externally_established` even in principle until a better-matched or additional
   source is found.
10. **Boundary conditions**: record the scope mismatch explicitly in
    `known_boundary_conditions` — this is citation-faithfulness evidence, not direct
    zero-support-edge evidence; the mechanism dossier's open-evidence-gaps section
    should note that a more directly on-point primary source (measuring answer claims
    with literally no supporting packed item) is still an open literature-search task.

## Execution order

Batch A (already-read papers, most direct fit): 1, 2, 3. Batch B: 4, 5 (assess jointly
for possible path-B qualification). Batch C: 6, 7, 8. Seed validation + relevant unit
tests run after each batch; schemas regenerated only if any schema changed (none
expected — this pass only edits YAML data and docs); git diff inspected after each
batch for fabricated, paraphrased, or unsupported claims before moving on.
