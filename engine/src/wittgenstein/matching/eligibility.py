"""Deterministic manifest-gate and trace-observable eligibility engine.

No LLM or embedding call anywhere in this module -- eligibility is decided purely by
typed field inspection. Every mechanism has an explicit evaluator function below;
there is no generic predicate interpreter, so "what this mechanism checks" is always
directly readable as Python, not hidden behind a rules DSL. Each EligibilityGateResult
references the matching ManifestGate/TraceTrigger predicate id from the registry seed
data so a reviewer can trace code back to the declared, documented predicate.

Aggregation semantics per EligibilityGateResult.status, read alongside its gate_kind:
- required_manifest / trace_observable: SATISFIED is good, VIOLATED blocks, UNKNOWN
  is insufficient information.
- disqualifying: SATISFIED blocks, VIOLATED (the disqualifying condition does not
  hold) is good, UNKNOWN is treated as insufficient information -- never assumed to
  not apply.
- strengthening: informational only; never blocks or contributes to insufficiency.

A definite block (any required predicate VIOLATED, or any disqualifying predicate
SATISFIED) always takes precedence over an unknown elsewhere: if the mechanism
structurally cannot apply, that is a conclusive answer even if some other field is
also unknown.
"""

from __future__ import annotations

from dataclasses import dataclass

from wittgenstein.core.enums import GateResultStatus
from wittgenstein.schemas.applicability import EligibilityGateResult, GateKind
from wittgenstein.schemas.manifest import PipelineManifest
from wittgenstein.schemas.trace import ContextItem, QueryTrace
from wittgenstein.trace.lineage import stages_fully_logged
from wittgenstein.trace.packing import has_identifiable_omission, identify_omissions


@dataclass
class EligibilityResult:
    gate_results: list[EligibilityGateResult]
    eligible: bool | None  # True / False / None (insufficient information)


def _result(gate_id: str, gate_kind: GateKind, status: GateResultStatus, reason: str) -> EligibilityGateResult:
    return EligibilityGateResult(gate_id=gate_id, gate_kind=gate_kind, status=status, reason=reason)


def _aggregate(gate_results: list[EligibilityGateResult]) -> bool | None:
    blocked = any(
        (
            r.gate_kind in (GateKind.REQUIRED_MANIFEST, GateKind.TRACE_OBSERVABLE)
            and r.status == GateResultStatus.VIOLATED
        )
        or (r.gate_kind == GateKind.DISQUALIFYING and r.status == GateResultStatus.SATISFIED)
        for r in gate_results
    )
    if blocked:
        return False
    unknown = any(
        r.gate_kind in (GateKind.REQUIRED_MANIFEST, GateKind.TRACE_OBSERVABLE, GateKind.DISQUALIFYING)
        and r.status == GateResultStatus.UNKNOWN_INSUFFICIENT_DATA
        for r in gate_results
    )
    if unknown:
        return None
    return True


def _items_with_known_relatedness(items: list[ContextItem] | None) -> list[ContextItem]:
    if not items:
        return []
    return [i for i in items if i.is_query_related is not None and i.is_answer_supporting is not None]


# ---------------------------------------------------------------------------------
# RET_HARD_DISTRACTOR
# ---------------------------------------------------------------------------------


def _eval_ret_hard_distractor(manifest: PipelineManifest, trace: QueryTrace | None) -> EligibilityResult:
    results: list[EligibilityGateResult] = []

    max_items = manifest.selection_manifest.max_selected_items
    if max_items is None:
        results.append(
            _result(
                "MP_RET_HARD_DISTRACTOR_max_items",
                GateKind.REQUIRED_MANIFEST,
                GateResultStatus.UNKNOWN_INSUFFICIENT_DATA,
                "selection_manifest.max_selected_items is unknown.",
            )
        )
    elif max_items > 1:
        results.append(
            _result(
                "MP_RET_HARD_DISTRACTOR_max_items",
                GateKind.REQUIRED_MANIFEST,
                GateResultStatus.SATISFIED,
                f"selection_manifest.max_selected_items={max_items} > 1.",
            )
        )
    else:
        results.append(
            _result(
                "MP_RET_HARD_DISTRACTOR_max_items",
                GateKind.REQUIRED_MANIFEST,
                GateResultStatus.VIOLATED,
                f"selection_manifest.max_selected_items={max_items}; a distractor cannot coexist "
                "with the supporting passage in a single-item context.",
            )
        )

    if trace is None:
        results.append(
            _result(
                "TO_RET_HARD_DISTRACTOR_relatedness_known",
                GateKind.TRACE_OBSERVABLE,
                GateResultStatus.UNKNOWN_INSUFFICIENT_DATA,
                "No trace supplied; cannot assess query-relatedness/support status of packed items.",
            )
        )
    else:
        candidates = trace.packed_context_items if trace.packed_context_items else trace.selected_context_items
        known = _items_with_known_relatedness(candidates)
        if not known:
            results.append(
                _result(
                    "TO_RET_HARD_DISTRACTOR_relatedness_known",
                    GateKind.TRACE_OBSERVABLE,
                    GateResultStatus.UNKNOWN_INSUFFICIENT_DATA,
                    "No packed/selected item carries both is_query_related and is_answer_supporting judgments.",
                )
            )
        else:
            distractors = [i for i in known if i.is_query_related and not i.is_answer_supporting]
            if distractors:
                results.append(
                    _result(
                        "TO_RET_HARD_DISTRACTOR_relatedness_known",
                        GateKind.TRACE_OBSERVABLE,
                        GateResultStatus.SATISFIED,
                        f"{len(distractors)} packed/selected item(s) are query-related but not "
                        f"answer-supporting: {[i.item_id for i in distractors]}.",
                    )
                )
            else:
                results.append(
                    _result(
                        "TO_RET_HARD_DISTRACTOR_relatedness_known",
                        GateKind.TRACE_OBSERVABLE,
                        GateResultStatus.VIOLATED,
                        "No packed/selected item is both query-related and non-supporting in this trace.",
                    )
                )

    if manifest.reranking_manifest.reranking_enabled is False:
        results.append(
            _result(
                "MP_RET_HARD_DISTRACTOR_no_rerank",
                GateKind.STRENGTHENING,
                GateResultStatus.SATISFIED,
                "Reranking is disabled, which strengthens the plausibility of an unfiltered distractor.",
            )
        )

    return EligibilityResult(gate_results=results, eligible=_aggregate(results))


# ---------------------------------------------------------------------------------
# RET_MULTIHOP_SUPPORT_INCOMPLETE
# ---------------------------------------------------------------------------------


def _eval_ret_multihop_support_incomplete(
    manifest: PipelineManifest, trace: QueryTrace | None
) -> EligibilityResult:
    results: list[EligibilityGateResult] = []

    if trace is None or trace.support_requirement is None:
        results.append(
            _result(
                "TO_RET_MULTIHOP_support_requirement_known",
                GateKind.TRACE_OBSERVABLE,
                GateResultStatus.UNKNOWN_INSUFFICIENT_DATA,
                "No trace, or query has not been assessed for multi-hop support requirements.",
            )
        )
    elif not trace.support_requirement.is_multi_hop:
        results.append(
            _result(
                "TO_RET_MULTIHOP_support_requirement_known",
                GateKind.TRACE_OBSERVABLE,
                GateResultStatus.VIOLATED,
                "Query is assessed as single-span support; multi-hop mechanism does not apply.",
            )
        )
    else:
        results.append(
            _result(
                "TO_RET_MULTIHOP_support_requirement_known",
                GateKind.TRACE_OBSERVABLE,
                GateResultStatus.SATISFIED,
                f"Query assessed as multi-hop, requiring {trace.support_requirement.required_support_item_ids}.",
            )
        )

    if trace is None or trace.packed_context_items is None:
        results.append(
            _result(
                "TO_RET_MULTIHOP_packed_items_known",
                GateKind.TRACE_OBSERVABLE,
                GateResultStatus.UNKNOWN_INSUFFICIENT_DATA,
                "packed_context_items is not logged; cannot confirm whether required support is present.",
            )
        )
    elif trace.support_requirement is not None and trace.support_requirement.is_multi_hop:
        packed_ids = {i.item_id for i in trace.packed_context_items}
        missing = [rid for rid in trace.support_requirement.required_support_item_ids if rid not in packed_ids]
        if missing:
            results.append(
                _result(
                    "TO_RET_MULTIHOP_packed_items_known",
                    GateKind.TRACE_OBSERVABLE,
                    GateResultStatus.SATISFIED,
                    f"Required support item(s) absent from packed context: {missing}.",
                )
            )
        else:
            results.append(
                _result(
                    "TO_RET_MULTIHOP_packed_items_known",
                    GateKind.TRACE_OBSERVABLE,
                    GateResultStatus.VIOLATED,
                    "All required support items are present in the packed context.",
                )
            )
    else:
        results.append(
            _result(
                "TO_RET_MULTIHOP_packed_items_known",
                GateKind.TRACE_OBSERVABLE,
                GateResultStatus.VIOLATED,
                "Not applicable: query is not assessed as multi-hop.",
            )
        )

    return EligibilityResult(gate_results=results, eligible=_aggregate(results))


# ---------------------------------------------------------------------------------
# CTX_POSITION_SENSITIVE_USE
# ---------------------------------------------------------------------------------

#: Position-risk length threshold, in tokens. Documented, not silently hardcoded
#: elsewhere. See docs/manifest-spec.md for rationale.
POSITION_RISK_TOKEN_THRESHOLD = 4000


def _eval_ctx_position_sensitive_use(manifest: PipelineManifest, trace: QueryTrace | None) -> EligibilityResult:
    results: list[EligibilityGateResult] = []

    context_window = manifest.packing_manifest.context_window_tokens
    if context_window is None:
        results.append(
            _result(
                "MP_CTX_POSITION_context_window_known",
                GateKind.REQUIRED_MANIFEST,
                GateResultStatus.UNKNOWN_INSUFFICIENT_DATA,
                "packing_manifest.context_window_tokens is unknown.",
            )
        )
    else:
        results.append(
            _result(
                "MP_CTX_POSITION_context_window_known",
                GateKind.REQUIRED_MANIFEST,
                GateResultStatus.SATISFIED,
                f"packing_manifest.context_window_tokens={context_window} is known.",
            )
        )

    max_items = manifest.selection_manifest.max_selected_items
    if max_items == 1:
        results.append(
            _result(
                "MP_CTX_POSITION_single_item_cap",
                GateKind.DISQUALIFYING,
                GateResultStatus.SATISFIED,
                "selection_manifest.max_selected_items=1; the system never packs more than a single item.",
            )
        )
    elif max_items is None:
        results.append(
            _result(
                "MP_CTX_POSITION_single_item_cap",
                GateKind.DISQUALIFYING,
                GateResultStatus.UNKNOWN_INSUFFICIENT_DATA,
                "selection_manifest.max_selected_items is unknown.",
            )
        )
    else:
        results.append(
            _result(
                "MP_CTX_POSITION_single_item_cap",
                GateKind.DISQUALIFYING,
                GateResultStatus.VIOLATED,
                f"selection_manifest.max_selected_items={max_items} > 1; not disqualified.",
            )
        )

    if trace is None or trace.packed_context_items is None:
        results.append(
            _result(
                "TO_CTX_POSITION_packed_count",
                GateKind.TRACE_OBSERVABLE,
                GateResultStatus.UNKNOWN_INSUFFICIENT_DATA,
                "packed_context_items is not logged.",
            )
        )
    elif len(trace.packed_context_items) > 1:
        results.append(
            _result(
                "TO_CTX_POSITION_packed_count",
                GateKind.TRACE_OBSERVABLE,
                GateResultStatus.SATISFIED,
                f"{len(trace.packed_context_items)} items packed.",
            )
        )
    else:
        results.append(
            _result(
                "TO_CTX_POSITION_packed_count",
                GateKind.TRACE_OBSERVABLE,
                GateResultStatus.VIOLATED,
                f"Only {len(trace.packed_context_items)} item(s) packed in this trace.",
            )
        )

    if trace is None or not trace.prompt_token_spans:
        results.append(
            _result(
                "TO_CTX_POSITION_spans_known",
                GateKind.TRACE_OBSERVABLE,
                GateResultStatus.UNKNOWN_INSUFFICIENT_DATA,
                "prompt_token_spans is empty or trace missing; actual packed positions are not available.",
            )
        )
    else:
        results.append(
            _result(
                "TO_CTX_POSITION_spans_known",
                GateKind.TRACE_OBSERVABLE,
                GateResultStatus.SATISFIED,
                f"{len(trace.prompt_token_spans)} prompt_token_spans recorded.",
            )
        )

    if trace is None or trace.final_prompt_token_count is None:
        results.append(
            _result(
                "TO_CTX_POSITION_length_known",
                GateKind.TRACE_OBSERVABLE,
                GateResultStatus.UNKNOWN_INSUFFICIENT_DATA,
                "final_prompt_token_count is unknown.",
            )
        )
    elif trace.final_prompt_token_count >= POSITION_RISK_TOKEN_THRESHOLD:
        results.append(
            _result(
                "TO_CTX_POSITION_length_known",
                GateKind.TRACE_OBSERVABLE,
                GateResultStatus.SATISFIED,
                f"final_prompt_token_count={trace.final_prompt_token_count} >= threshold "
                f"{POSITION_RISK_TOKEN_THRESHOLD}.",
            )
        )
    else:
        results.append(
            _result(
                "TO_CTX_POSITION_length_known",
                GateKind.TRACE_OBSERVABLE,
                GateResultStatus.VIOLATED,
                f"final_prompt_token_count={trace.final_prompt_token_count} below threshold "
                f"{POSITION_RISK_TOKEN_THRESHOLD}.",
            )
        )

    if trace is None or not any(i.is_answer_supporting is not None for i in (trace.packed_context_items or [])):
        results.append(
            _result(
                "TO_CTX_POSITION_support_identifiable",
                GateKind.TRACE_OBSERVABLE,
                GateResultStatus.UNKNOWN_INSUFFICIENT_DATA,
                "No packed item carries an is_answer_supporting judgment.",
            )
        )
    else:
        results.append(
            _result(
                "TO_CTX_POSITION_support_identifiable",
                GateKind.TRACE_OBSERVABLE,
                GateResultStatus.SATISFIED,
                "At least one packed item has an is_answer_supporting judgment.",
            )
        )

    return EligibilityResult(gate_results=results, eligible=_aggregate(results))


# ---------------------------------------------------------------------------------
# REP_SEGMENTATION_GRANULARITY_MISMATCH
# ---------------------------------------------------------------------------------


def _eval_rep_segmentation_granularity_mismatch(
    manifest: PipelineManifest, trace: QueryTrace | None
) -> EligibilityResult:
    results: list[EligibilityGateResult] = []
    retrieval = manifest.retrieval_manifest

    if retrieval.chunking_method is None:
        results.append(
            _result(
                "MP_REP_SEG_chunking_known",
                GateKind.REQUIRED_MANIFEST,
                GateResultStatus.UNKNOWN_INSUFFICIENT_DATA,
                "retrieval_manifest.chunking_method is unknown.",
            )
        )
    else:
        results.append(
            _result(
                "MP_REP_SEG_chunking_known",
                GateKind.REQUIRED_MANIFEST,
                GateResultStatus.SATISFIED,
                f"retrieval_manifest.chunking_method={retrieval.chunking_method!r}.",
            )
        )

    if retrieval.retrieval_unit is None:
        results.append(
            _result(
                "MP_REP_SEG_retrieval_unit_known",
                GateKind.REQUIRED_MANIFEST,
                GateResultStatus.UNKNOWN_INSUFFICIENT_DATA,
                "retrieval_manifest.retrieval_unit is unknown.",
            )
        )
    else:
        results.append(
            _result(
                "MP_REP_SEG_retrieval_unit_known",
                GateKind.REQUIRED_MANIFEST,
                GateResultStatus.SATISFIED,
                f"retrieval_manifest.retrieval_unit={retrieval.retrieval_unit!r}.",
            )
        )

    if retrieval.retrieval_unit == "whole_document":
        results.append(
            _result(
                "MP_REP_SEG_whole_document_unit",
                GateKind.DISQUALIFYING,
                GateResultStatus.SATISFIED,
                "retrieval_unit=whole_document; no sub-document segmentation exists.",
            )
        )
    elif retrieval.retrieval_unit is None:
        results.append(
            _result(
                "MP_REP_SEG_whole_document_unit",
                GateKind.DISQUALIFYING,
                GateResultStatus.UNKNOWN_INSUFFICIENT_DATA,
                "retrieval_manifest.retrieval_unit is unknown.",
            )
        )
    else:
        results.append(
            _result(
                "MP_REP_SEG_whole_document_unit",
                GateKind.DISQUALIFYING,
                GateResultStatus.VIOLATED,
                f"retrieval_unit={retrieval.retrieval_unit!r} is sub-document; not disqualified.",
            )
        )

    if trace is None or not trace.segment_boundary_dependency_flags:
        results.append(
            _result(
                "TO_REP_SEG_boundary_flags",
                GateKind.TRACE_OBSERVABLE,
                GateResultStatus.UNKNOWN_INSUFFICIENT_DATA if trace is None else GateResultStatus.VIOLATED,
                "No trace supplied." if trace is None else "segment_boundary_dependency_flags is empty.",
            )
        )
    else:
        results.append(
            _result(
                "TO_REP_SEG_boundary_flags",
                GateKind.TRACE_OBSERVABLE,
                GateResultStatus.SATISFIED,
                f"{len(trace.segment_boundary_dependency_flags)} boundary-crossing flag(s): "
                f"{trace.segment_boundary_dependency_flags}.",
            )
        )

    return EligibilityResult(gate_results=results, eligible=_aggregate(results))


# ---------------------------------------------------------------------------------
# PACK_OMISSION_OR_TRUNCATION
# ---------------------------------------------------------------------------------


def _eval_pack_omission_or_truncation(manifest: PipelineManifest, trace: QueryTrace | None) -> EligibilityResult:
    results: list[EligibilityGateResult] = []

    if trace is None or not stages_fully_logged(trace):
        results.append(
            _result(
                "TO_PACK_OMISSION_stages_logged",
                GateKind.TRACE_OBSERVABLE,
                GateResultStatus.UNKNOWN_INSUFFICIENT_DATA,
                "retrieval_candidates, selected_context_items, and packed_context_items are not all logged.",
            )
        )
        return EligibilityResult(gate_results=results, eligible=_aggregate(results))

    results.append(
        _result(
            "TO_PACK_OMISSION_stages_logged",
            GateKind.TRACE_OBSERVABLE,
            GateResultStatus.SATISFIED,
            "retrieval_candidates, selected_context_items, and packed_context_items are all logged.",
        )
    )

    if has_identifiable_omission(trace):
        omissions = identify_omissions(trace)
        results.append(
            _result(
                "TO_PACK_OMISSION_identifiable_gap",
                GateKind.TRACE_OBSERVABLE,
                GateResultStatus.SATISFIED,
                f"{len(omissions)} selected item(s) identifiably missing from packed context: "
                f"{[(o.item_id, o.reason) for o in omissions]}.",
            )
        )
    else:
        results.append(
            _result(
                "TO_PACK_OMISSION_identifiable_gap",
                GateKind.TRACE_OBSERVABLE,
                GateResultStatus.VIOLATED,
                "No identifiable selection-to-packing gap in this trace.",
            )
        )

    return EligibilityResult(gate_results=results, eligible=_aggregate(results))


# ---------------------------------------------------------------------------------
# GEN_CONTEXT_CONFLICT_UNRESOLVED
# ---------------------------------------------------------------------------------


def _eval_gen_context_conflict_unresolved(
    manifest: PipelineManifest, trace: QueryTrace | None
) -> EligibilityResult:
    results: list[EligibilityGateResult] = []

    max_items = manifest.selection_manifest.max_selected_items
    if max_items is None:
        results.append(
            _result(
                "MP_GEN_CONFLICT_max_items",
                GateKind.REQUIRED_MANIFEST,
                GateResultStatus.UNKNOWN_INSUFFICIENT_DATA,
                "selection_manifest.max_selected_items is unknown.",
            )
        )
    elif max_items > 1:
        results.append(
            _result(
                "MP_GEN_CONFLICT_max_items",
                GateKind.REQUIRED_MANIFEST,
                GateResultStatus.SATISFIED,
                f"selection_manifest.max_selected_items={max_items} > 1.",
            )
        )
    else:
        results.append(
            _result(
                "MP_GEN_CONFLICT_max_items",
                GateKind.REQUIRED_MANIFEST,
                GateResultStatus.VIOLATED,
                "Only a single item can ever be packed; a conflict needs >=2 sources present together.",
            )
        )

    if trace is None or not trace.context_conflicts:
        results.append(
            _result(
                "TO_GEN_CONFLICT_present",
                GateKind.TRACE_OBSERVABLE,
                GateResultStatus.UNKNOWN_INSUFFICIENT_DATA if trace is None else GateResultStatus.VIOLATED,
                "No trace supplied." if trace is None else "context_conflicts is empty.",
            )
        )
    else:
        results.append(
            _result(
                "TO_GEN_CONFLICT_present",
                GateKind.TRACE_OBSERVABLE,
                GateResultStatus.SATISFIED,
                f"{len(trace.context_conflicts)} context_conflicts recorded.",
            )
        )
        unresolved = [
            c for c in trace.context_conflicts if c.conflict_id not in trace.conflict_ids_addressed_in_answer
        ]
        if unresolved:
            results.append(
                _result(
                    "TO_GEN_CONFLICT_unaddressed",
                    GateKind.TRACE_OBSERVABLE,
                    GateResultStatus.SATISFIED,
                    f"{len(unresolved)} conflict(s) not addressed in the answer: "
                    f"{[(c.conflict_id, c.dimension) for c in unresolved]}.",
                )
            )
        else:
            results.append(
                _result(
                    "TO_GEN_CONFLICT_unaddressed",
                    GateKind.TRACE_OBSERVABLE,
                    GateResultStatus.VIOLATED,
                    "Every recorded conflict was addressed in the answer.",
                )
            )

    return EligibilityResult(gate_results=results, eligible=_aggregate(results))


# ---------------------------------------------------------------------------------
# GEN_UNSUPPORTED_DESPITE_CONTEXT
# ---------------------------------------------------------------------------------


def _eval_gen_unsupported_despite_context(
    manifest: PipelineManifest, trace: QueryTrace | None
) -> EligibilityResult:
    results: list[EligibilityGateResult] = []

    if trace is None or trace.packed_context_items is None:
        results.append(
            _result(
                "TO_GEN_UNSUPPORTED_supporting_material_packed",
                GateKind.TRACE_OBSERVABLE,
                GateResultStatus.UNKNOWN_INSUFFICIENT_DATA,
                "packed_context_items is not logged.",
            )
        )
    else:
        supporting = [i for i in trace.packed_context_items if i.is_answer_supporting is True]
        if supporting:
            results.append(
                _result(
                    "TO_GEN_UNSUPPORTED_supporting_material_packed",
                    GateKind.TRACE_OBSERVABLE,
                    GateResultStatus.SATISFIED,
                    f"{len(supporting)} packed item(s) assessed as answer-supporting.",
                )
            )
        else:
            results.append(
                _result(
                    "TO_GEN_UNSUPPORTED_supporting_material_packed",
                    GateKind.TRACE_OBSERVABLE,
                    GateResultStatus.VIOLATED,
                    "No packed item is assessed as answer-supporting in this trace.",
                )
            )

    if trace is None or not trace.answer_claims:
        results.append(
            _result(
                "TO_GEN_UNSUPPORTED_claim_without_support",
                GateKind.TRACE_OBSERVABLE,
                GateResultStatus.UNKNOWN_INSUFFICIENT_DATA,
                "No answer_claims recorded.",
            )
        )
    else:
        supported_claim_ids = {e.claim_id for e in trace.answer_support_edges if e.support_status == "supported"}
        unsupported = [c for c in trace.answer_claims if c.claim_id not in supported_claim_ids]
        if unsupported:
            results.append(
                _result(
                    "TO_GEN_UNSUPPORTED_claim_without_support",
                    GateKind.TRACE_OBSERVABLE,
                    GateResultStatus.SATISFIED,
                    f"{len(unsupported)} answer claim(s) lack a supported edge: "
                    f"{[c.claim_id for c in unsupported]}.",
                )
            )
        else:
            results.append(
                _result(
                    "TO_GEN_UNSUPPORTED_claim_without_support",
                    GateKind.TRACE_OBSERVABLE,
                    GateResultStatus.VIOLATED,
                    "Every answer claim has a supported edge.",
                )
            )

    return EligibilityResult(gate_results=results, eligible=_aggregate(results))


MECHANISM_EVALUATORS = {
    "RET_HARD_DISTRACTOR": _eval_ret_hard_distractor,
    "RET_MULTIHOP_SUPPORT_INCOMPLETE": _eval_ret_multihop_support_incomplete,
    "CTX_POSITION_SENSITIVE_USE": _eval_ctx_position_sensitive_use,
    "REP_SEGMENTATION_GRANULARITY_MISMATCH": _eval_rep_segmentation_granularity_mismatch,
    "PACK_OMISSION_OR_TRUNCATION": _eval_pack_omission_or_truncation,
    "GEN_CONTEXT_CONFLICT_UNRESOLVED": _eval_gen_context_conflict_unresolved,
    "GEN_UNSUPPORTED_DESPITE_CONTEXT": _eval_gen_unsupported_despite_context,
}


def evaluate_eligibility(
    mechanism_id: str, manifest: PipelineManifest, trace: QueryTrace | None
) -> EligibilityResult:
    evaluator = MECHANISM_EVALUATORS.get(mechanism_id)
    if evaluator is None:
        raise NotImplementedError(
            f"No deterministic eligibility evaluator implemented for {mechanism_id!r} "
            "(likely a disabled research-hypothesis mechanism, which is not evaluated by design)."
        )
    return evaluator(manifest, trace)
