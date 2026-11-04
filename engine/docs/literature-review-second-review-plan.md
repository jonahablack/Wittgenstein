# Literature Review — Second-Review Plan

Status: plan only, written before any registry edits from this pass. Covers
independent verification of all 8 `EvidenceRecord`s populated in the 2026-09-09
literature-review pass (`docs/literature-review-results.md`).

## A note on independence

There is no second human or separately-instantiated reviewer available in this
environment. This pass is executed as **"a solo contributor's second pass after a time
gap, disclosed as such"** — the explicit allowance in
`docs/literature-review-protocol.md`'s "Single vs. dual reviewer procedure" section.
Concretely, this pass: (a) happens in a new session turn, after the first pass's output
was already committed to the registry and re-read fresh rather than from memory; (b)
re-fetches primary-source pages not previously read, specifically targeting
venue/peer-review confirmation and the mechanism-fit questions below; (c) applies an
adversarial checklist (do not accept the first extraction's framing; look for a reason
each field could be wrong) rather than re-deriving the same conclusions by construction.
It is not equivalent to an independent human reviewer at a different institution, and
this document says so rather than implying otherwise.

## 1–3. The 8 records, their primary sources, and what the first reviewer claimed

| # | Evidence record | Mechanism | Primary source (as first reviewer left it) | First reviewer's grade / direction / peer-review status |
|---|---|---|---|---|
| 1 | `EV-RET_HARD_DISTRACTOR-001` | `RET_HARD_DISTRACTOR` | Amiraz, Cuconasu, Filice, Karnin — "The Distracting Effect" — ACL 2025 | A2 / supports / peer_reviewed |
| 2 | `EV-RET_MULTIHOP_SUPPORT_INCOMPLETE-001` | `RET_MULTIHOP_SUPPORT_INCOMPLETE` | Tang, Yang — "MultiHop-RAG" — arXiv:2401.15391 | C / supports / preprint |
| 3 | `EV-CTX_POSITION_SENSITIVE_USE-001` | `CTX_POSITION_SENSITIVE_USE` | Liu et al. — "Lost in the Middle" — TACL 2024, DOI 10.1162/tacl_a_00638 | A1 / supports / peer_reviewed |
| 4 | `EV-REP_SEGMENTATION_GRANULARITY_MISMATCH-001` | `REP_SEGMENTATION_GRANULARITY_MISMATCH` | Chen et al. — "Dense X Retrieval" — EMNLP 2024 | A2 / supports / peer_reviewed |
| 5 | `EV-REP_SEGMENTATION_GRANULARITY_MISMATCH-002` | `REP_SEGMENTATION_GRANULARITY_MISMATCH` | Wang et al. — "Document Segmentation Matters" — Findings ACL 2025 | A2 / supports / peer_reviewed |
| 6 | `EV-PACK_OMISSION_OR_TRUNCATION-001` | `PACK_OMISSION_OR_TRUNCATION` | Gabín, Perez, Parapar — "Lost in the Evidence?" — SIGIR '26, DOI 10.1145/3805712.3808569 | B2 / supports / peer_reviewed |
| 7 | `EV-GEN_CONTEXT_CONFLICT_UNRESOLVED-001` | `GEN_CONTEXT_CONFLICT_UNRESOLVED` | Jin et al. — "RAG-RewardBench" — Findings ACL 2025 | B2 / null / peer_reviewed |
| 8 | `EV-GEN_UNSUPPORTED_DESPITE_CONTEXT-001` | `GEN_UNSUPPORTED_DESPITE_CONTEXT` | Wallat, Heuss, de Rijke, Anand — "Correctness is not Faithfulness in RAG Attributions" — arXiv:2412.18004 | C / null / preprint |

All 8 primary-source PDFs are locally available in the parent workspace's
`literature/` collection and were re-fetched (in whole or in the previously-unread
parts) during this pass — none require external network access.

## 4. Fields requiring independent verification, per record

Per the task brief, every record gets all 18 fields checked: title, authors, venue,
publication year, persistent identifier, peer-review status, source URL, exact
quotation, quote location, study type, task and corpus, retrieval/generation setup,
experimental intervention/comparison, outcome metric, effect-size description, stated
limitations, evidence direction, evidence grade, and RAG-native-vs.-transfer
classification. Priority ordering for this pass, highest-risk first:

1. **Peer-review status** for records 2 and 8 (both `preprint`) — the highest-stakes
   field, since it structurally caps evidence grade and gates `externally_established`
   eligibility. Re-verification target: search the *entire* document (not just the
   pages sampled in the first pass) for any proceedings/camera-ready marking.
2. **Mechanism fit** (does the source measure the mechanism's actual causal claim, or
   something adjacent) for records 6, 7, and 8 — see the special-attention section
   below.
3. **Independence and RAG-nativeness** of records 4 and 5 together — the pair that
   grounds the registry's one `externally_established` mechanism. Re-verification
   target: author/institution overlap, whether one paper's baseline *is* the other
   paper's method (common and not disqualifying, but must be checked and disclosed),
   and whether both genuinely measure RAG-native retrieval/QA metrics.
4. **Exact quotation and quote location** for all 8 — re-read the cited page and
   character-compare against what the first pass recorded.
5. **Persistent identifiers left `null`** (records 1, 4, 5, 7) — confirm whether a DOI
   or ACL Anthology ID is genuinely absent from the document text (ACL/EMNLP/Findings
   papers in this era commonly do not print one in-document) rather than merely
   unsearched.
6. Remaining fields (task/corpus, envelope, effect size, outcome metrics) — spot-checked
   against the same source pages for transcription accuracy.

## 5. How disagreements will be recorded

- Both extraction passes are preserved in full: the first pass's values remain
  legible in `docs/literature-review-results.md` (already published) and in this
  record's `stated_limitations` narrative; the second pass's findings are recorded in
  `docs/literature-review-second-review-results.md`, not by silently overwriting the
  first document.
- A field the second pass leaves unchanged is recorded as confirmed, not re-derived
  from scratch and coincidentally matching — the second-review results table states
  explicitly what was re-checked against the source for each record.
- A field the second pass corrects gets the corrected value in the seed YAML plus an
  explicit note in that record's `stated_limitations` naming the second-review pass and
  what changed, so the audit trail is visible in the data itself, not only in the
  standalone docs (the same convention the first pass already used for its own
  corrections to the pre-review seed).
- Where the two passes cannot be reconciled with the primary source in hand, the record
  is marked `unresolved_disagreement`, `verification_status` is **not** advanced to
  `verified`, and the narrower/more conservative of the two claims governs
  `evidence_grade`/`direction` until a further pass resolves it — per the
  "use the narrower claim until adjudication" instruction.

## 6. When a record becomes `verified`

Per `docs/literature-review-protocol.md`: only once an independent second pass has
re-confirmed `exact_quote` and metadata against the primary source with **no**
unresolved disagreement. Concretely here: `verification_status: verified` is applied
only to records reaching agreement status `verified_agreement` or
`verified_with_correction` below — never to `unresolved_disagreement`,
`insufficient_primary_source_access`, or `evidence_does_not_fit_mechanism`. Reaching
`verified` changes nothing about `default_activation_policy` by itself — per this task's
explicit instruction, activation-policy changes are a separate, deliberate
registry-governance decision, not an automatic consequence of verification or of
`externally_established` status.

## 7. When a record must be downgraded, split, merged, or marked mixed/null

- **Downgrade**: `evidence_grade` drops whenever `peer_review_status` cannot be
  confirmed as `peer_reviewed` (the existing `_a_grade_requires_peer_review` rule
  already makes A1/A2 structurally impossible in that case), or when the second pass
  finds the source's actual study design weaker than first recorded.
- **Mixed/null**: `direction` is set to `null` (not `supports`) whenever the source is
  genuinely on-topic but does not itself demonstrate the mechanism's specific causal
  claim — already applied to records 7 and 8 in the first pass; this second pass checks
  whether that classification still holds or whether either source is close enough to
  warrant `supports`, or distant enough to warrant `refutes`.
- **Split**: would apply if a single evidence record were found to conflate two
  genuinely different findings from the same paper that support different mechanisms —
  not expected for these 8 based on the first pass's per-record scoping, but checked for
  during re-reading.
- **Merge**: would apply if two records turned out to report the same underlying
  experiment (e.g. a preprint and its later peer-reviewed version) — checked for
  between records 4 and 5 specifically (they are not the same experiment; confirmed
  different institutions, different specific techniques).
- Mechanism-level `epistemic_status`/`evidence_synthesis` are re-derived from whatever
  the corrected record set implies, via the *same*, unmodified validator rule
  (`registry/validator.py::_check_established_status_requires_a_grade_evidence`) — this
  pass does not change that rule, only (potentially) the facts it operates on.

## 8. Peer-review status vs. verification status — kept distinct

These remain two independent axes, per `docs/evidence-grading.md`'s existing "Verification
is a third, orthogonal axis" section: `peer_review_status` describes the *venue* (can a
record ever reach A1/A2, regardless of who has checked it); `verification_status`
describes whether *a human has checked* the quote/metadata against the primary source
(can a record's evidence-dependent mechanism ever be considered for non-disabled
activation, regardless of how prestigious the venue is). A record can be
`peer_review_status=peer_reviewed` and `verification_status=unverified` (true of all 8
before this pass), or, after this pass, `peer_review_status=preprint` and
`verification_status=verified` (a human confirmed the quote; the venue still caps the
grade) — the two facts never substitute for each other anywhere in this system.

## Special-attention items (addressed in the second-review results, not here)

The six items listed in the task brief — `REP_SEGMENTATION_GRANULARITY_MISMATCH`'s
two-path justification, `RET_MULTIHOP_SUPPORT_INCOMPLETE`'s peer-review status,
`GEN_UNSUPPORTED_DESPITE_CONTEXT`'s construct match, `GEN_CONTEXT_CONFLICT_UNRESOLVED`'s
construct match, the parametric-vs-context candidate mechanism staying unadded, and the
correctness-vs-faithfulness schema question staying a documented future item and not a
code change — are each addressed as part of the per-record review in
`docs/literature-review-second-review-results.md`, not duplicated here.
