# Registry seed data

This directory is a **bootstrap scaffold**, not a finished or exhaustive registry.

## What "bootstrap" means here

- It contains 7 concrete (non-`research_hypothesis`) failure mechanisms and 11 disabled
  research-hypothesis entries. RAG failure modes not represented here are not thereby
  ruled out -- absence from this seed set is not evidence of absence, and no entry here
  should be read as "the complete list."
- As of registry version 0.2.0 and the 2026-09-09 literature-review pass (see
  `docs/literature-review-results.md` for the full report), exactly one of the 7
  concrete mechanisms is `externally_established`:
  `REP_SEGMENTATION_GRANULARITY_MISMATCH`, backed by two independent, RAG-native,
  peer-reviewed, `direction=supports` A2 records (`EV-REP_SEGMENTATION_GRANULARITY_MISMATCH-001`,
  `-002`) -- satisfying the evidence-threshold rule's path B (`docs/evidence-grading.md`,
  "Evidence thresholds"). `RET_HARD_DISTRACTOR`, `RET_MULTIHOP_SUPPORT_INCOMPLETE`,
  `GEN_UNSUPPORTED_DESPITE_CONTEXT`, `GEN_CONTEXT_CONFLICT_UNRESOLVED`, and
  `CTX_POSITION_SENSITIVE_USE` are `manifest_conditioned_transfer` (single-study,
  non-RAG-native, or indirect/component evidence -- see each mechanism's
  `known_boundary_conditions` for the specific reason). `PACK_OMISSION_OR_TRUNCATION`
  is `trace_integrity_condition` and does not depend on external evidence for its core
  function.
- Every `exact_quote` in `evidence_records.seed.yaml` is now a real, verbatim quotation
  extracted directly from the located primary-source PDF, with a precise
  `quote_location`, populated `experimental_envelope`, and reported effect sizes.
  Bibliographic metadata (title/authors/venue/year) was confirmed against each source
  document directly; three records' original "candidate" citations from the pre-review
  seed were revised where the original candidate could not be located/verified or
  turned out to study a different mechanism -- see
  `docs/literature-review-execution-plan.md` for the reasoning behind each substitution
  or confirmation.
- **All 8 records are now `verification_status: verified`**, following a same-day
  second-review pass (a solo-contributor second pass after a time gap, disclosed as
  such, per `docs/literature-review-protocol.md`) -- see
  `docs/literature-review-second-review-results.md`. "Verified" describes extraction
  accuracy (a second, independent read confirmed `exact_quote` and metadata against the
  primary source); it is a different axis from whether the source's construct actually
  matches its mechanism's exact claim (see `direction`) -- two records are verified
  *and* `direction: "null"` at once, which is not a contradiction. Verification alone
  never changes `default_activation_policy` automatically -- that is always a separate,
  deliberate registry-governance decision (`docs/registry-governance.md`). Such a
  decision *was* made, deliberately, for `REP_SEGMENTATION_GRANULARITY_MISMATCH`
  specifically: as of 2026-09-09 its policy is `manifest_conditioned` (a new,
  intermediate value in the `shadow` / `manifest_conditioned` / `triage_enabled`
  graduation path -- `docs/registry-governance.md`), not `disabled` and not
  `triage_enabled`. Its risk events are shown only when its five manifest/trace
  activation gates all genuinely pass, and its priority is capped below
  `PriorityTier.HIGH` pending a future `LocalValidationRecord.reviewer_yield`-backed
  promotion. Every other mechanism's `default_activation_policy` is unchanged.
  `PACK_OMISSION_OR_TRUNCATION`'s `trace_integrity_condition` status was never
  evidence-gated for activation in the first place -- see its mechanism entry and
  `docs/evidence-grading.md`.
- Two records (`GEN_CONTEXT_CONFLICT_UNRESOLVED`, `GEN_UNSUPPORTED_DESPITE_CONTEXT`)
  have a confirmed, real, peer-review-status-checked primary source, but that source
  was found to test a related-but-not-identical claim to the mechanism's own -- both are
  linked with `direction: "null"` rather than `supports`, honestly reflecting a partial
  match rather than being forced to fit. A more directly on-point primary source for
  each remains an open literature-search task; see each mechanism's dossier for detail.

## Discovery sources vs. primary evidence

A "source candidate" is a *discovery-stage* pointer to where evidence probably exists.
It becomes primary evidence once a human reviewer has:

1. Located the actual paper (PDF or authoritative HTML).
2. Copied the exact quote verbatim, with a precise `quote_location`.
3. Confirmed peer-review status, venue, and year against the source itself (not a
   citation manager's guess or general bibliographic recall).
4. Independently, on a second pass, re-checked the quote and metadata, and only then set
   `verification_status: verified`.

All 8 records here have completed all four steps as of the 2026-09-09 second-review
pass. See `docs/literature-review-protocol.md` for the full procedure,
`docs/literature-review-results.md` for what the first pass found, downgraded, or left
as an open gap for each record, and
`docs/literature-review-second-review-results.md` for the independent re-verification
outcome.

## No entry is "exhaustive" merely because it appears here

`REP_SEGMENTATION_GRANULARITY_MISMATCH`'s two evidence records were originally seeded to
preserve a *speculated* contradiction between studies; on actual reading, both were
found to support (not contradict) the same mechanism-level claim while testing different
specific techniques -- the registry does not collapse distinct specific findings into a
single "which method is best" ranking even when their general direction agrees. Two
mechanisms (`GEN_CONTEXT_CONFLICT_UNRESOLVED`, `GEN_UNSUPPORTED_DESPITE_CONTEXT`) have a
confirmed but only partially-matching primary source, as described above; their evidence
records exist to record that real, honest partial match and to track the remaining
literature-search task, not to assert a finding beyond what was actually verified.

The 11 `HYP_*` mechanisms are explicitly disabled-by-default review cues, not
established RAG failure modes. See their `known_boundary_conditions` and
`docs/registry-governance.md` for how one could graduate to `research_hypothesis` with
attached evidence, and eventually toward `locally_validated` or
`manifest_conditioned_transfer`/`externally_established` -- never automatically. One
candidate new mechanism (parametric-vs-context knowledge conflict misresolution) was
identified during the 2026-09-09 pass but deliberately not added to this seed file --
see `docs/literature-review-execution-plan.md`.
