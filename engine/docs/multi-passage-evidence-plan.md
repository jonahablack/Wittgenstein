# Multi-passage evidence-set plan

A conservative, bounded, deterministic layer that determines whether two (occasionally
three) packed passages *jointly* provide the components a claim requires, when no
single passage does. Motivated by `smoke-005-multi-passage-cross-reference` in the
real-trace smoke pilot: an answer combining "Exemption C applies to widgets
manufactured before January 2023" with "Section 4 of the Handbook" currently resolves
`unresolved` because no single packed passage covers both the exemption's threshold
and its cross-reference -- the single-passage engine (`docs/claim-linking-improvement-plan.md`)
has no way to say "these two passages together cover it."

No dense/hybrid retrieval, no live semantic/NLI provider, no new/promoted registry
mechanism, no activation-policy change, no `TRIAGE_ENABLED` promotion. This layer never
asserts factual truth -- an `EvidenceSet` is a candidate relationship, exactly like a
single-passage `ClaimEvidenceComparison`, never a factual adjudication.

## 1. What counts as an evidence set

An `EvidenceSet` is a small (default max size 2, optionally 3), ordered collection of
packed `ContextItem`s proposed as jointly covering the components one `AnswerClaim`
requires. It is a *candidate*, produced by a deterministic constructor
(`review/evidence_set.py`), never a claim that the set is correct or complete in a
factual sense. A set is only ever built from **packed** items -- never omitted ones,
for the same reason single-passage linking is packed-only
(`docs/architecture.md`, "Pipeline lineage": omitted items were never available to
whatever produced the answer).

## 2. What counts as a claim component

Reuses `review/field_extraction.py::extract_fields` and
`core/enums.py::ComparisonFieldName` (17 fields) unchanged -- the task's "CLAIM
COMPONENTS" list is the same field taxonomy the single-passage engine already extracts
(entity, predicate, object/value, polarity, modality, population/scope, condition,
exception, temporal, version, frequency/duration, numeric value, comparator, unit,
jurisdiction, cross-reference). A `ClaimComponent` (new schema, §schema) wraps one
non-absent `ExtractedField` from the claim with two additional judgments this layer
needs that single-passage comparison doesn't: **requiredness** (is this component
load-bearing for the claim, or incidental -- see §4) and **dependencies** (does
satisfying this component depend on another, e.g. a cross-reference target). One
extraction pass, not a second extractor.

## 3. Complementary vs. redundant passages

Two packed items are **complementary** for a claim when, after comparing each
independently against the claim's components (reusing
`review/field_comparison.py::compare_field`), their *covered* (`MATCH`) component sets
are non-identical and their union covers more of the claim's required components than
either alone. Two items are **redundant** when one's covered-component set is a subset
of the other's (adds no new coverage) -- redundant items are recorded (never silently
dropped) but do not extend a set.

## 4. When the system must abstain rather than compose

Composition is refused (the result is `composite_unresolved`, never a guess) whenever:

- A **critical** required component (§requiredness below) remains uncovered by every
  member of every candidate set.
- Combining two members requires an **implicit join** -- inferring that two passages
  share an entity, time period, version, or jurisdiction merely because they discuss
  the same general topic, without an explicit, matching field value on both sides.
  "Do not infer that two documents about the same entity describe the same time
  period unless dates/versions match or are explicitly compatible" (task brief) is
  enforced structurally: cross-member compatibility uses the same `compare_field`
  four-state lattice as claim-to-passage comparison, so an unverifiable join is
  `UNKNOWN`, not assumed `MATCH`.
- A member's cross-reference target is not itself present in the packed set (§7).
- The candidate pool or set search exceeds its bound (§9) before a valid set is found.

**Requiredness**: a component is `critical` if the claim's own extraction marks it
non-optional -- concretely, `ENTITY` and `PREDICATE` are always critical (mirrors the
single-passage engine's structural-field rule), and any other component the claim
explicitly asserts (`extraction_status == EXTRACTED`) is critical unless it is a
`CROSS_REFERENCE` (informational, not itself a substantive claim component).

## 5. Evidence-set support vs. a single-passage support link

Direct single-passage support (`ClaimSupportCandidateStatus.DIRECT_SUPPORT_CANDIDATE`,
from `docs/claim-linking-improvement-plan.md`) is **always preferred when present** --
evidence-set construction is only attempted for a claim when no single packed item
reaches `direct_support_candidate` (Stage 5). This keeps the default path lightweight
(most claims never trigger set search at all) and matches the task's explicit rule
("direct single-passage support remains preferred when present"). An `EvidenceSet`'s
`relationship_status` reuses the same `ClaimSupportCandidateStatus` vocabulary,
extended with five additive, composite-specific members (§schema) -- never conflated
with the single-member statuses, and never written back onto the existing
`AnswerSupportEdge.candidate_support_status` (§schema explains why).

## 6. Propagating conflicts and qualifications across a set

A pairwise compatibility check (`review/evidence_set.py::_check_compatibility`) runs
`compare_field` between every pair of candidate-set members on entity, predicate,
version, temporal, jurisdiction, and population/scope -- the same four-state lattice,
applied member-to-member instead of claim-to-member. Any `MISMATCH` between two
members makes the set `composite_conflict_candidate`; a qualification-type mismatch
between a member and the claim (modality/scope narrower, a condition/exception the
claim omits) makes it `composite_qualification_required`, mirroring rules C/D from the
single-passage engine exactly, just evaluated over the union of members.

## 7. Provenance stays visible

`EvidenceSetMember` (§schema) always carries the packed item's `item_id`, its supplied
components (with each component's own source span into the excerpt), its individual
field comparisons against the claim, and a plain-language selection rationale. The
reviewer never sees only a final composite verdict -- `docs/review-loop-demo.md` and
the inspection report expose every member exactly as an individual candidate would be
shown, plus the set-level coverage/conflict/rationale summary.

## 8. Relationship to the registered multi-hop mechanism

`RET_MULTIHOP_SUPPORT_INCOMPLETE` (`data/registry/failure_modes.seed.yaml`,
`epistemic_status: manifest_conditioned_transfer`,
`default_activation_policy: disabled_by_default_or_research_mode`) is the existing
registry mechanism for "a query requires multiple support elements and retrieval
returns fewer than the full set." This milestone does not promote, activate, or edit
that mechanism, or add a new one. It *does* populate the existing, previously-unused
`QueryTrace.support_requirement` field (`schemas/trace.py::SupportRequirement`,
`is_multi_hop`/`required_support_item_ids`/`assessment_method`) when evidence-set
construction determines a claim needed more than one packed item -- this is exactly
the trace-level observable `RET_MULTIHOP_SUPPORT_INCOMPLETE`'s gate conditions already
expect to exist ("The trace records a support-set or dependency structure to compare
against"), so this layer makes that mechanism's existing gate *evaluable* against real
traces without changing the mechanism itself. Whether that mechanism should ever be
promoted remains a separate, deliberate registry-governance decision.

## 9. Performance constraints for evidence-set search

- Candidate pool = packed items only (already bounded by the token budget -- typically
  single digits), no additional retrieval.
- Set search only runs when no single-passage `direct_support_candidate` exists for the
  claim (§5) -- most claims skip this layer entirely.
- Default max set size 2; configurable; size 3 only ever attempted if 2-item search
  finds no valid set and the pool size allows it within the same combinatorial bound.
- `itertools.combinations` over the (already small) pool, bounded by max set size --
  never exhaustive search over all subset sizes, never beam search in this pass
  (documented as a future option if pool sizes grow; not needed at current pool sizes).
- `EvidenceSetConstructionMetrics` (new, mirrors `ProcessingMetrics`'s existing
  "companion object, never folded into the trace schema" convention) records
  candidate-pool size, sets considered, sets discarded (redundant/conflicting), and
  construction latency.
- No LLM or semantic-provider call in the default path.

## 10. Synthetic fixture and test strategy

14 fictional, domain-neutral (widget-certification) fixtures covering the task's
required scenarios (two complementary passages, rule+condition, rule+exception,
definition+requirement, cross-reference+target, two redundant passages, conflicting
values, version mismatch, population mismatch, missing second passage, 3-hop blocked
by max-set-size, implicit-join abstention, single-passage-preferred, and
qualified-only composite) live alongside the existing
`data/examples/real_trace_smoke/cases.example.json` cases as new smoke-test cases (not
a separate fixture format) so the smoke-test harness (`docs/real-trace-smoke-test-plan.md`)
exercises them the same way. 20 required test categories map to
`tests/unit/test_evidence_set.py` (unit-level, synthetic ExtractedField/ContextItem
inputs) and `tests/integration/test_multi_passage_smoke_cases.py` (fixture-level).

Actual delivery deviates from this section in two ways, both documented in §11 below:
the 14 fixtures are expressed as inline synthetic `ContextItem`/`AnswerClaim` pairs
inside `tests/unit/test_evidence_set.py` (16 tests covering categories 1-4, 6-17)
rather than as new `cases.example.json` entries -- iterating on the extraction/
comparison fixes below required much faster edit-run cycles than the smoke-test
harness's file-based workflow supports, and the resulting tests are exactly as
reusable for future regression coverage. Category 5 (cross-reference/definition
closure) is not implemented; see §11.

## 11. Implementation notes and tuning decisions

Building `review/evidence_set.py` against this plan's own §4 worked example (two
passages -- "Class III widgets must be inspected annually" / "This annual requirement
applies only to widgets operating in Zone A" -- composing into "Class III widgets in
Zone A must be inspected annually") surfaced several gaps the plan's design did not
anticipate, all fixed narrowly and documented at the call site:

- **Entity extraction absorbed a trailing scope phrase.** "Class III widgets in Zone
  A" was extracted whole as the entity, so it never matched a source's plain "Class
  III widgets." Fixed by stripping a trailing `in|for|under|within|operating in ...`
  phrase from the entity span (`field_extraction.py::_TRAILING_SCOPE_PHRASE_RE`) --
  POPULATION_SCOPE, not ENTITY, is responsible for that text.
- **"Applies to" was not recognized as a predicate anchor.** Entity/predicate
  extraction both key off the same "subject precedes the verb" anchor
  (`_find_verb_start`); a condition/applicability sentence commonly uses "applies to,"
  "requires," or "covers" rather than a modal or copula, and without recognizing these
  as anchors, both fields came back `ABSENT` for exactly the sentences this layer most
  needs to read (condition/exception/applicability passages).
- **Population/scope needed to be a set, and the set needed axes.** A claim commonly
  asserts more than one independent scope qualifier at once (a widget class *and* a
  zone); the original single-value extractor only ever kept the first match. Capturing
  all matches was necessary but not sufficient: comparing two flat string sets treats
  "one passage confirms the class, the other confirms the zone" (complementary) the
  same as "one passage says Class III, the other says Class II" (conflicting). Fixed by
  grouping scope tokens by axis (class/zone/region/district/area/general, inferred from
  the token's own prefix) before comparing -- a shared axis with disjoint values is a
  real conflict; an axis one side never mentions is an omission, not a conflict.
- **Claim-vs-source and member-vs-member scope comparison needed different rules.**
  `field_comparison.py::_compare_population_scope` (claim vs. one candidate) asks "does
  this source cover *every* axis the claim asserts" -- correctly conservative for
  single-passage direct-support gating, since it now prevents a passage that covers
  only one of several asserted axes from being misread as fully supporting the claim.
  `population_scope_conflict` (member vs. member, `evidence_set.py`) asks a narrower
  question -- "do these two sources disagree on a *shared* axis" -- so two passages
  addressing different axes are correctly read as complementary, not conflicting. Using
  the claim-vs-source function for member-vs-member checking (the original plan's
  implicit assumption) would have flagged every complementary pair as a conflict.
- **Component coverage had to be tracked per scope token, not per field.** Because a
  compound scope assertion is one `ExtractedField` but several independent facts,
  `extract_claim_components` decomposes POPULATION_SCOPE into one critical
  `ClaimComponent` per scope token (`COMP-N-population_scope-<slug>`); coverage for
  those components is computed directly from each member's own extracted scope tokens
  (set membership), not from the whole-field single-passage comparison outcome, which
  answers a different, coarser question (see above).
- **Predicate and numeric_value are excluded from member-vs-member compatibility.** A
  rule passage and a condition/exception/applicability passage legitimately use
  different verbs ("must be inspected" vs. "applies to") without conflicting -- that
  is the rule+condition composition case this layer exists to support, not a case to
  block, so PREDICATE was removed from the cross-member compatibility fields.
  NUMERIC_VALUE was excluded too: a bare number carries no unit of its own (a
  percentage in one passage and a year in another can collide purely by coincidence),
  so it is too unreliable a signal to gate composition on; FREQUENCY_DURATION (whose
  comparator is unit/kind-aware) is kept and does the real work for the "conflicting
  values" fixture.
- **An unresolved pronoun is not evidence of a different entity.** A condition passage
  commonly refers back to the rule anaphorically ("This annual requirement applies
  only to..."), which would otherwise register as an ENTITY mismatch against a second
  member naming the concrete entity, blocking a legitimate composition. This is the
  same honest-limitation category as the single-passage engine's smoke-004 pronoun-
  coreference case (`docs/claim-linking-improvement-plan.md`): the fix here does not
  attempt coreference resolution, it only stops treating an unresolved pronoun as
  *affirmative* evidence of a conflict for the member-compatibility check specifically
  (`_is_anaphoric_entity`) -- single-passage claim-vs-candidate entity matching is
  unchanged.
- **A member introducing an unstated condition/exception needed its own signal.** When
  the claim itself never mentions a condition/exception, that component is never added
  to `claim_components`, so a member's own "only if..."/"except..." clause was
  otherwise silently dropped instead of surfacing as a qualification. Fixed by
  `_member_introduced_qualifiers`, which checks each combo member's own CONDITION/
  EXCEPTION extraction directly (bypassing the component-coverage mechanism, since
  there is no corresponding claim component to attach it to) and downgrades an
  otherwise-full composite to `composite_qualification_required` when found.
- **Known, undelivered limitation: cross-reference/definition closure (category 5).**
  Stage 1's candidate pool is packed items only; resolving an explicit cross-reference
  ("as defined in Section 4") or a definitional dependency to a target passage *outside*
  the packed set was not implemented in this pass -- doing so safely requires a
  provenance-preserving lookup this milestone did not build. A claim whose composition
  depends on an unresolved cross-reference currently stays `composite_unresolved`
  (never silently assumed resolved), which is the conservative, correct behavior in the
  absence of that lookup -- but it means true cross-document definition closure is not
  yet exercised end-to-end.
- **"Prefer smallest size" broke the diagnostic size-3 search entirely (fixed
  2026-09-11, during `docs/evidence-set-real-corpus-diagnostics-plan.md`).** The
  original break condition stopped the size loop as soon as *any* non-conflicting,
  non-redundant combo was found at a size -- even an incomplete one -- so a caller
  passing `max_set_size=3` would never actually reach size-3 combinations whenever a
  merely-improving (but still incomplete) 2-item combo existed. Fixed by breaking only
  when the best combo found so far achieves full critical-component coverage. This has
  no effect on the default `max_set_size=2` (there is only one size to try either way)
  and was caught only by building the diagnostic size-3 feature and finding it
  produced identical output to the size-2 default on a case designed to need a third
  item -- see `docs/evidence-set-real-corpus-diagnostics-plan.md` §9.
- **Real corpus text is messier than the worked example.** Running the layer against
  the bundled `widget-certification-demo` corpus (`tests/integration/test_multi_passage_smoke_cases.py`)
  confirmed the mechanism works end-to-end on real (if synthetic) prose, but also that
  its regex-based OBJECT_VALUE/NUMERIC_VALUE extraction is noticeably less reliable on
  longer, more complex sentences than on the plan's clean worked example -- a genuinely
  complementary eligibility+threshold claim composed, but landed on
  `composite_conflict_candidate` rather than a clean `composite_support_candidate`,
  most likely from an extraction artifact rather than a real disagreement between the
  two source passages. This is recorded as a known limitation for the human-labeled
  pilot (see the final report), not silently smoothed over.
