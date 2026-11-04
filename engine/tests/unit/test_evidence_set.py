"""The multi-passage evidence-set construction layer --
docs/multi-passage-evidence-plan.md. Covers required test categories 1-4, 6-17 (the
task's numbering is preserved in each test's docstring/name for traceability).

Categories not covered here:
- 5 (definition/cross-reference closure) and part of the Stage-1 candidate-pool
  design (pulling in explicit cross-reference targets beyond the packed-item pool) are
  a known, documented gap -- see docs/multi-passage-evidence-plan.md's "known
  limitations" note. The current candidate pool is packed items only.
- 18 (smoke-005 structured result) is exercised in
  tests/integration/test_real_trace_smoke_cases.py, not here.
- 19-20 (existing suites/345-test baseline remain green) are satisfied by the rest of
  this repository's test suite continuing to pass, not by a test in this file.

All fixtures are synthetic and domain-neutral (widgets/zones/classes), never real
clinical or legal material, per docs/multi-passage-evidence-plan.md.
"""

from __future__ import annotations

import inspect

from wittgenstein.core.enums import ClaimSupportCandidateStatus
from wittgenstein.review.claim_linking import compare_claim_to_candidate
from wittgenstein.review.evidence_set import EvidenceSetConstructionMetrics, construct_evidence_set
from wittgenstein.schemas.evidence_set import EvidenceSet
from wittgenstein.schemas.trace import AnswerClaim, ContextItem


def _build(claim_text: str, excerpts: list[str], *, max_set_size: int = 2):
    claim = AnswerClaim(claim_id="c1", text=claim_text)
    items = [
        ContextItem(item_id=f"item{i}", excerpt=excerpt, rank=i) for i, excerpt in enumerate(excerpts, start=1)
    ]
    comparisons = [compare_claim_to_candidate(claim, item) for item in items]
    evidence_set, metrics = construct_evidence_set(
        claim, items, comparisons, trace_id="t1", max_set_size=max_set_size
    )
    return claim, items, comparisons, evidence_set, metrics


# 1. Valid two-passage composite support: neither passage alone covers the claim's
# compound (class + zone) scope assertion; together they do.
def test_01_two_passage_composite_support() -> None:
    _, _, _, evidence_set, _ = _build(
        "Class III widgets in Zone A must be inspected annually.",
        [
            "Class III widgets must be inspected annually.",
            "This annual requirement applies only to widgets operating in Zone A.",
        ],
    )
    assert evidence_set is not None
    assert evidence_set.relationship_status == ClaimSupportCandidateStatus.COMPOSITE_SUPPORT_CANDIDATE
    assert set(evidence_set.member_context_item_ids) == {"item1", "item2"}
    assert evidence_set.unresolved_component_ids == []
    assert evidence_set.conflicts == []


# 2. Correct component coverage attribution: each member's own supplied_component_ids
# names exactly the components *it* contributes, not a merged/ambiguous union.
def test_02_component_coverage_attribution() -> None:
    _, _, _, evidence_set, _ = _build(
        "Class III widgets in Zone A must be inspected annually.",
        [
            "Class III widgets must be inspected annually.",
            "This annual requirement applies only to widgets operating in Zone A.",
        ],
    )
    assert evidence_set is not None
    by_id = {m.context_item_id: m for m in evidence_set.members}
    item1_scope_components = [cid for cid in by_id["item1"].supplied_component_ids if "population_scope" in cid]
    item2_scope_components = [cid for cid in by_id["item2"].supplied_component_ids if "population_scope" in cid]
    assert any("class" in cid for cid in item1_scope_components)
    assert not any("zone" in cid for cid in item1_scope_components)
    assert any("zone" in cid for cid in item2_scope_components)
    assert not any("class" in cid for cid in item2_scope_components)
    # Non-scope components (entity/predicate/...) come only from item1, which alone
    # already matches the claim's non-scope assertions.
    assert any(cid.endswith("-entity") for cid in by_id["item1"].supplied_component_ids)
    assert not any(cid.endswith("-entity") for cid in by_id["item2"].supplied_component_ids)


# 3. Rule + applicability condition -> composite_qualification_required.
def test_03_rule_and_condition_composition() -> None:
    _, _, _, evidence_set, _ = _build(
        "Class III widgets in Zone A must be tested.",
        [
            "Class III widgets must be tested.",
            "This requirement applies only to widgets operating in Zone A, "
            "provided that the widget is sold commercially.",
        ],
    )
    assert evidence_set is not None
    assert evidence_set.relationship_status == ClaimSupportCandidateStatus.COMPOSITE_QUALIFICATION_REQUIRED
    assert "condition" in evidence_set.explanation.lower()


# 4. Rule + exception -> composite_qualification_required.
def test_04_rule_and_exception_composition() -> None:
    _, _, _, evidence_set, _ = _build(
        "Class III widgets in Zone A must be tested.",
        [
            "Class III widgets must be tested.",
            "This requirement applies only to widgets operating in Zone A, "
            "except for widgets manufactured before 2020.",
        ],
    )
    assert evidence_set is not None
    assert evidence_set.relationship_status == ClaimSupportCandidateStatus.COMPOSITE_QUALIFICATION_REQUIRED
    assert "exception" in evidence_set.explanation.lower()


# 6. A required second passage is genuinely missing from the corpus -> unresolved,
# never a guessed/forced composite.
def test_06_missing_dependency_produces_unresolved() -> None:
    _, _, _, evidence_set, metrics = _build(
        "Class III widgets in Zone A must be inspected annually.",
        [
            "Class III widgets must be inspected annually.",
        ],
    )
    assert evidence_set is not None
    assert evidence_set.relationship_status == ClaimSupportCandidateStatus.COMPOSITE_UNRESOLVED
    assert evidence_set.members == []
    assert any("zone" in cid for cid in evidence_set.unresolved_component_ids)
    assert metrics.candidate_pool_size == 1


# 7. Two passages that say the same thing are not double-counted as independent
# support -- the redundant pair adds no coverage a single one of them didn't already
# have, so composition is (correctly) not found, and the gap stays unresolved.
def test_07_redundant_passages_not_independent_support() -> None:
    _, _, _, evidence_set, metrics = _build(
        "Class III widgets in Zone A must be inspected annually.",
        [
            "Class III widgets must be inspected annually.",
            "Class III widgets must be inspected annually.",
        ],
    )
    assert evidence_set is not None
    assert evidence_set.relationship_status == ClaimSupportCandidateStatus.COMPOSITE_UNRESOLVED
    assert evidence_set.members == []
    assert metrics.sets_discarded_redundant == 1


# 8. Two sources giving explicitly conflicting numeric/frequency values for what
# otherwise looks like the same requirement -> composite_conflict_candidate.
def test_08_conflicting_sources_produce_composite_conflict() -> None:
    _, _, _, evidence_set, metrics = _build(
        "Class III widgets in Zone A must be inspected annually.",
        [
            "Class III widgets must be inspected once every 12 months.",
            "Class III widgets operating in Zone A must be inspected once every 3 months.",
        ],
    )
    assert evidence_set is not None
    assert evidence_set.relationship_status == ClaimSupportCandidateStatus.COMPOSITE_CONFLICT_CANDIDATE
    assert evidence_set.conflicts
    assert metrics.sets_discarded_conflicting == 1


# 9. A version mismatch between two otherwise-complementary sources blocks
# composition -- never silently combined across incompatible versions.
def test_09_version_mismatch_blocks_composition() -> None:
    _, _, _, evidence_set, _ = _build(
        "Class III widgets in Zone A must be inspected annually.",
        [
            "Class III widgets must be inspected annually, per Program Year 2019.",
            "This annual inspection requirement applies only to widgets operating in "
            "Zone A, per Program Year 2023.",
        ],
    )
    assert evidence_set is not None
    assert evidence_set.relationship_status == ClaimSupportCandidateStatus.COMPOSITE_CONFLICT_CANDIDATE
    assert any(c.field_name.value == "version" for c in evidence_set.conflicts)


# 10. A population/scope mismatch on the same axis (both name a widget class, but
# different ones) blocks composition -- never inferred as compatible.
def test_10_population_mismatch_blocks_composition() -> None:
    _, _, _, evidence_set, _ = _build(
        "Class III widgets in Zone A must be inspected annually.",
        [
            "Class III widgets must be inspected annually.",
            "Class II widgets operating in Zone A must be inspected annually.",
        ],
    )
    assert evidence_set is not None
    assert evidence_set.relationship_status == ClaimSupportCandidateStatus.COMPOSITE_CONFLICT_CANDIDATE
    assert any(c.field_name.value == "population_scope" for c in evidence_set.conflicts)


# 11. An implicit join is never inferred: a passage that is merely topically nearby
# (same corpus, unrelated requirement) is not assembled into support just because it
# was packed alongside a relevant passage.
def test_11_implicit_join_stays_unresolved() -> None:
    _, _, _, evidence_set, _ = _build(
        "Class III widgets in Zone A must be inspected annually.",
        [
            "Class III widgets must be inspected annually.",
            "Widget maintenance logs must be retained for three years.",
        ],
    )
    assert evidence_set is not None
    assert evidence_set.relationship_status == ClaimSupportCandidateStatus.COMPOSITE_UNRESOLVED
    assert evidence_set.members == []


# 12. Bounded set size prevents uncontrolled search: the number of combinations tried
# never exceeds C(n, max_set_size), and no evidence set exceeds max_set_size members,
# regardless of pool size.
def test_12_bounded_search_never_exceeds_max_set_size() -> None:
    excerpts = [
        "Class III widgets must be inspected annually.",
        "This annual requirement applies only to widgets operating in Zone A.",
        "Widget maintenance logs must be retained for three years.",
        "Class III widgets must be labeled with a compliance sticker.",
        "Inspection records must be retained for five years.",
    ]
    claim = "Class III widgets in Zone A must be inspected annually."
    _, _, _, evidence_set, metrics = _build(claim, excerpts, max_set_size=2)
    assert metrics.sets_considered <= 10  # C(5, 2)
    if evidence_set is not None:
        assert len(evidence_set.member_context_item_ids) <= 2


# 13. Deterministic set selection: identical inputs produce an identical member
# selection every time (packed_items' rank order drives combination order).
def test_13_deterministic_set_selection() -> None:
    claim_text = "Class III widgets in Zone A must be inspected annually."
    excerpts = [
        "Class III widgets must be inspected annually.",
        "This annual requirement applies only to widgets operating in Zone A.",
    ]
    _, _, _, first, _ = _build(claim_text, excerpts)
    _, _, _, second, _ = _build(claim_text, excerpts)
    assert first is not None and second is not None
    assert first.member_context_item_ids == second.member_context_item_ids


# 14. Single-passage direct support is always preferred: composition is skipped
# entirely when one packed item already directly supports the claim, even when a
# second, complementary-looking item is also present.
def test_14_direct_single_passage_preferred_over_composite() -> None:
    _, _, _, evidence_set, metrics = _build(
        "Class III widgets must be inspected annually.",
        [
            "Class III widgets must be inspected annually.",
            "This annual requirement applies only to widgets operating in Zone A.",
        ],
    )
    assert evidence_set is None
    assert metrics.attempted is False
    assert metrics.skip_reason == "A single packed item already directly supports the claim."


# 15. Only packed (model-visible) items are ever candidates -- an item never passed in
# `packed_items` can never appear as an evidence-set member, however relevant its text.
def test_15_only_packed_items_are_candidates() -> None:
    claim = AnswerClaim(claim_id="c1", text="Class III widgets in Zone A must be inspected annually.")
    packed = [
        ContextItem(item_id="packed-1", excerpt="Class III widgets must be inspected annually.", rank=1),
    ]
    omitted_but_relevant = ContextItem(
        item_id="omitted-1", excerpt="This annual requirement applies only to widgets operating in Zone A.", rank=2
    )
    comparisons = [compare_claim_to_candidate(claim, item) for item in packed]
    evidence_set, _ = construct_evidence_set(claim, packed, comparisons, trace_id="t1")
    assert evidence_set is not None
    assert "omitted-1" not in evidence_set.member_context_item_ids
    assert omitted_but_relevant.item_id not in evidence_set.member_context_item_ids


# 16. The evidence-set output is a candidate relationship, structurally distinct from
# a factual adjudication -- the schema carries no truth/adjudication field, and
# `relationship_status` is always one of the composite candidate statuses.
def test_16_evidence_set_output_distinct_from_factual_adjudication() -> None:
    schema_fields = set(EvidenceSet.model_fields.keys())
    assert "adjudication_outcome" not in schema_fields
    assert "is_true" not in schema_fields
    assert "verified" not in schema_fields

    _, _, _, evidence_set, _ = _build(
        "Class III widgets in Zone A must be inspected annually.",
        [
            "Class III widgets must be inspected annually.",
            "This annual requirement applies only to widgets operating in Zone A.",
        ],
    )
    assert evidence_set is not None
    assert evidence_set.relationship_status.value.startswith("composite_")
    prohibited_phrases = ["the answer is correct", "the answer is false", "these sources prove the answer"]
    assert not any(phrase in evidence_set.explanation.lower() for phrase in prohibited_phrases)


# 17. No LLM calls in baseline construction: `construct_evidence_set` takes no LLM
# client/cache parameters, and its metrics object carries no LLM-call accounting --
# unlike `ProcessingMetrics`, which does, because this path never needs one.
def test_17_no_llm_calls_in_baseline_construction() -> None:
    signature = inspect.signature(construct_evidence_set)
    assert "llm_client" not in signature.parameters
    assert "llm_cache" not in signature.parameters
    metrics_fields = set(EvidenceSetConstructionMetrics.__dataclass_fields__.keys())
    assert "llm_call_count" not in metrics_fields


# Optional semantic hook (docs/multi-passage-evidence-plan.md, "OPTIONAL SEMANTIC
# LAYER"): never called by `construct_evidence_set`, available for a future,
# explicitly opted-into caller only, and disabled (NullSemanticProvider) by default.
def test_semantic_hook_is_never_invoked_by_default_construction() -> None:
    signature = inspect.signature(construct_evidence_set)
    assert "provider" not in signature.parameters
    assert "semantic_provider" not in signature.parameters


def test_semantic_hook_reports_unavailable_without_a_provider() -> None:
    from wittgenstein.review.evidence_set import semantic_evidence_set_hint

    result = semantic_evidence_set_hint(
        "Class III widgets must be inspected annually.",
        "This annual requirement applies only to widgets operating in Zone A.",
    )
    assert result.outcome == "provider_unavailable"
    assert result.provider is None
