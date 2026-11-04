# EU AI Act cross-reference annotation protocol

How to manually review the baseline-versus-post-fix cross-reference comparison
worksheet (`docs/eu-ai-act-cross-reference-comparison-template.md` explains its
format; `wittgenstein evidence-set compare-cross-reference` generates it -- see
`docs/eu-ai-act-article-cross-reference-fix-plan.md` and
`docs/eu-ai-act-article-cross-reference-run-summary.md` for what the fix changed and
why). This protocol governs *judgment* only -- the worksheet itself is generated
read-only and deterministically and contains no judgment (see its own disclaimer).

## What this protocol is not

Every outcome below is a diagnostic judgment about this pipeline's cross-reference
detection and target-state reporting. **None of them are a legal conclusion.**
Deciding that "Article 49" is the correct target for a citation is not the same as
deciding that Article 49 is legally controlling, and this protocol never asks an
annotator to make the latter judgment.

## Review order, per case

1. Read the case's `query` and any stated constraints.
2. Read the `answer` and its `answer_origin` metadata (verbatim quote, controlled
   perturbation, etc. -- see `docs/real-corpus-case-authoring-guide.md`).
3. Inspect the source clause containing the explicit reference (open the relevant
   local corpus file under `local_corpora/eu-ai-act-2024/` -- gitignored, local only).
4. Compare the baseline and post-fix reference detections for this case in the
   worksheet (`baseline_markers` vs. `post_fix_markers`, `markers_newly_detected`).
5. Check whether the reference's surface span is correct (does `marker_text` exactly
   match what the source clause says?).
6. Check whether the normalized target identifier is correct (does `target_identifier`
   -- e.g. `article:49:paragraph:2` -- actually correspond to what the citation names?).
7. Check whether the target-state classification is correct (does `target_state`
   match what you can independently see in `linked_evidence_propositions`/
   `packed_context_items`?).
8. Inspect the target's own source text, if the target resolved to a document present
   in this pilot's local slice (only for `in_corpus`/`retrieved`/`selected`/`packed`/
   `omitted` -- an `unknown` target has no local text to inspect).
9. Decide whether the target appears (see "Valid outcomes" below): needed to
   interpret the claim, only clarifying, unrelated to the answer, or
   uncertain/unresolved.
10. Decide whether the warning would: help targeted review, create unnecessary
    escalation, create false reassurance, require full-context review, or warrant a
    source-expansion request.
11. Record a short rationale for each judgment made.

## Valid outcomes (record these, not a factual/legal adjudication)

**Detection and normalization:**
- reference correctly detected
- reference incorrectly detected
- target correctly identified
- target incorrectly identified
- target state correct
- target state incorrect

**Relevance to the claim (a diagnostic judgment about this specific case's answer,
never a legal necessity ruling):**
- target needed to interpret the claim
- target only clarifies the claim
- target not relevant to the claim
- necessity unresolved

**Reviewer/workflow value:**
- warning useful
- warning not useful
- likely unnecessary escalation
- likely false reassurance
- requires full context
- requires source expansion
- unresolved

None of the above is a legal or factual adjudication. "Target needed to interpret the
claim" means *this pipeline's specific claim, as split and compared*, reads
incompletely without the target -- it is not a statement that the cited provision is
legally binding, controlling, or the correct authority for any real situation.

## What the worksheet already tells you (do not re-derive it)

The comparison worksheet (`local_corpora/eu-ai-act-2024/output-after-article-xref/`,
gitignored) already computes, deterministically: which markers are new, which target
states changed, per-case processing time before/after, and whether any
non-cross-reference trace output changed at all. Use these fields directly -- this
protocol is about judgment on top of them, not about recomputing them by hand.
