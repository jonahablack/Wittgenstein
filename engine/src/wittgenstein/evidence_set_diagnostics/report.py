"""Aggregates a completed real-corpus diagnostic run's per-case reports and
(possibly human-filled-in) labels templates into one summary --
docs/evidence-set-real-corpus-diagnostics-plan.md §10.

This module computes counts and rates only. It never classifies a dominant next
implementation bottleneck (decision rules A-E) -- that is a human judgment made only
after manual labels exist, recorded in a filled-in
docs/evidence-set-real-corpus-diagnostics-results.md, never inferred automatically
here from unlabeled counts.
"""

from __future__ import annotations

import json
from pathlib import Path

_CAVEATS = [
    "This pass diagnoses implementation bottlenecks on a small, deliberately sampled "
    "case set (docs/evidence-set-real-corpus-diagnostics-plan.md §5) -- it does not "
    "establish a performance claim or a representative rate.",
    "Diagnostic labels here describe this pipeline's extraction/conflict/cross-"
    "reference/sizing behavior -- they are not universal factual-truth labels about "
    "the underlying documents.",
    "A count of 0 for a label may mean 'not observed' or 'not yet manually labeled' -- "
    "check each metric's labeled_count/total_count before treating a 0 as an absence.",
    "This report never recommends a next implementation priority -- see "
    "docs/evidence-set-real-corpus-diagnostics-plan.md §10; that classification is "
    "made by a human after reading the manual labels this report aggregates.",
]


def _load_case_artifacts(output_dir: Path) -> list[tuple[dict, dict]]:
    pairs = []
    for report_path in sorted(output_dir.glob("*.diagnostic.json")):
        case_id = report_path.name[: -len(".diagnostic.json")]
        labels_path = output_dir / f"{case_id}.diagnostic_labels.json"
        if not labels_path.exists():
            continue
        pairs.append((json.loads(report_path.read_text()), json.loads(labels_path.read_text())))
    return pairs


def _tally_dict_labels(pairs: list[tuple[dict, dict]], labels_key: str) -> dict:
    total = 0
    labeled = 0
    by_label: dict[str, int] = {}
    for _report, labels in pairs:
        for label in (labels.get(labels_key) or {}).values():
            total += 1
            if label is not None:
                labeled += 1
                by_label[label] = by_label.get(label, 0) + 1
    return {"total_count": total, "labeled_count": labeled, "by_label": by_label}


def _cross_reference_target_states(pairs: list[tuple[dict, dict]]) -> dict:
    counts: dict[str, int] = {}
    by_reference_type: dict[str, int] = {}
    by_resolution_granularity: dict[str, int] = {}
    by_exact_target_status: dict[str, int] = {}
    warned_count = 0
    total = 0
    total_targets = 0
    for report, _labels in pairs:
        for markers in report.get("cross_reference_markers", {}).values():
            for marker in markers:
                total += 1
                counts[marker["target_state"]] = counts.get(marker["target_state"], 0) + 1
                reference_type = marker.get("reference_type", "unknown")
                by_reference_type[reference_type] = by_reference_type.get(reference_type, 0) + 1
                if marker.get("warning"):
                    warned_count += 1
                for target in marker.get("targets", []):
                    total_targets += 1
                    granularity = target.get("resolution_granularity", "unknown")
                    by_resolution_granularity[granularity] = by_resolution_granularity.get(granularity, 0) + 1
                    exactness = target.get("exact_target_status", "target_unknown")
                    by_exact_target_status[exactness] = by_exact_target_status.get(exactness, 0) + 1
    return {
        "total_markers": total,
        "by_target_state": counts,
        "by_reference_type": by_reference_type,
        "warned_count": warned_count,
        "total_targets": total_targets,
        "by_resolution_granularity": by_resolution_granularity,
        "by_exact_target_status": by_exact_target_status,
    }


def _conflict_diagnostics(pairs: list[tuple[dict, dict]]) -> dict:
    total = 0
    low_confidence_count = 0
    alternative_plausible_count = 0
    for report, _labels in pairs:
        for explanations in report.get("conflict_explanations", {}).values():
            for explanation in explanations:
                total += 1
                if explanation.get("rests_on_low_confidence_field"):
                    low_confidence_count += 1
                if explanation.get("alternative_non_conflict_classification_plausible"):
                    alternative_plausible_count += 1
    return {
        "total_conflicts_explained": total,
        "rests_on_low_confidence_field_count": low_confidence_count,
        "alternative_non_conflict_classification_plausible_count": alternative_plausible_count,
    }


def _tally_reviewer_workflow_labels(pairs: list[tuple[dict, dict]]) -> dict:
    total = 0
    by_label: dict[str, int] = {}
    for _report, labels in pairs:
        for label in labels.get("reviewer_workflow_labels") or []:
            total += 1
            by_label[label] = by_label.get(label, 0) + 1
    return {"total_count": total, "by_label": by_label}


def _size3_diagnostics(pairs: list[tuple[dict, dict]]) -> dict:
    entries = [d for report, _labels in pairs for d in report.get("size3_diagnostics", {}).values()]
    searches_run = [d for d in entries if d.get("size3_search_run")]
    return {
        "claims_diagnosed": len(entries),
        "size3_searches_actually_run": len(searches_run),
        "size3_resolved_count": sum(
            1 for d in searches_run if d.get("size3_relationship_status") == "composite_support_candidate"
        ),
        "mean_size3_combination_count": (
            sum(d.get("size3_combination_count", 0) for d in entries) / len(entries) if entries else None
        ),
        "max_size3_combination_count": max((d.get("size3_combination_count", 0) for d in entries), default=0),
    }


def generate_diagnostic_report(output_dir: Path) -> dict:
    pairs = _load_case_artifacts(output_dir)

    return {
        "case_count": len(pairs),
        "extraction_quality": _tally_dict_labels(pairs, "extraction_quality_labels"),
        "conflict_quality": _tally_dict_labels(pairs, "conflict_quality_labels"),
        "cross_reference_closure": _tally_dict_labels(pairs, "cross_reference_closure_labels"),
        "evidence_set_sizing": _tally_dict_labels(pairs, "evidence_set_sizing_labels"),
        "reviewer_workflow": _tally_reviewer_workflow_labels(pairs),
        "cross_reference_target_states": _cross_reference_target_states(pairs),
        "conflict_diagnostics": _conflict_diagnostics(pairs),
        "size3_diagnostics": _size3_diagnostics(pairs),
        "caveats": _CAVEATS,
    }
