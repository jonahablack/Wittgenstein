"""Generates the case-level and aggregate diagnostic summary from a completed
smoke-test run's inspection reports and (possibly human-filled-in) labels templates
-- docs/real-trace-smoke-test-plan.md, "Produce summary metrics".

Every diagnostic label counted here describes this pipeline's retrieval/linking/
provenance/interface behavior, never a factual-truth claim about the underlying
document's content. This is a small diagnostic pilot, not a statistically powered
benchmark -- no metric here is collapsed into a single score, and every count is
reported alongside its labeled/total denominator so a 0 is never misread as "observed
zero problems" when it may mean "not yet labeled."
"""

from __future__ import annotations

import json
from pathlib import Path

_CAVEATS = [
    "Diagnostic labels in this report describe this pipeline's retrieval/linking/"
    "provenance/interface behavior -- they are not factual-truth labels about the "
    "underlying document content.",
    "This is a small diagnostic pilot, not a statistically powered benchmark -- these "
    "counts must not be read as a generalizable rate or a confidence estimate.",
    "A count of 0 for a label may mean 'not observed' or 'not yet manually labeled' -- "
    "check each metric's labeled_count/total_count before treating a 0 as an absence.",
]

#: Proposition/provenance labels counted as a provenance failure for the summary
#: metric -- not asserted anywhere else; this grouping exists only to answer the
#: single "provenance failures" summary metric the task requires.
_PROVENANCE_FAILURE_LABELS = {"source_span_invalid", "extraction_uncertain", "dependency_missing"}
#: Review-interface labels counted as a problem for the summary metric.
_REVIEW_INTERFACE_PROBLEM_LABELS = {"unnecessary_alert", "missing_useful_warning", "unresolved"}


def _load_case_artifacts(output_dir: Path) -> list[tuple[dict, dict]]:
    """Returns (inspection_report, labels_template) pairs for every case with both
    files present in output_dir, matched by case_id.
    """

    pairs = []
    for inspection_path in sorted(output_dir.glob("*.inspection.json")):
        case_id = inspection_path.name[: -len(".inspection.json")]
        labels_path = output_dir / f"{case_id}.labels_template.json"
        if not labels_path.exists():
            continue
        pairs.append((json.loads(inspection_path.read_text()), json.loads(labels_path.read_text())))
    return pairs


def _tally_dict_labels(pairs: list[tuple[dict, dict]], labels_key: str, max_examples: int = 3) -> dict:
    """Tallies a `{item_id: label_or_None}`-shaped labels dict across every case."""

    total = 0
    labeled = 0
    by_label: dict[str, int] = {}
    examples: dict[str, list[dict]] = {}

    for inspection, labels in pairs:
        case_id = inspection["case_id"]
        for key, label in labels.get(labels_key, {}).items():
            total += 1
            if label is None:
                continue
            labeled += 1
            by_label[label] = by_label.get(label, 0) + 1
            bucket = examples.setdefault(label, [])
            if len(bucket) < max_examples:
                bucket.append({"case_id": case_id, "key": key})

    return {"total_count": total, "labeled_count": labeled, "by_label": by_label, "examples": examples}


def _tally_expected_evidence_locations(pairs: list[tuple[dict, dict]], max_examples: int = 5) -> dict:
    total = 0
    labeled = 0
    missed = 0
    found = 0
    missed_examples: list[dict] = []

    for inspection, labels in pairs:
        case_id = inspection["case_id"]
        for location, entry in labels.get("expected_evidence_location_labels", {}).items():
            total += 1
            label = entry.get("label") if isinstance(entry, dict) else None
            if label is None:
                continue
            labeled += 1
            if label == "evidence_candidate_missed":
                missed += 1
                if len(missed_examples) < max_examples:
                    missed_examples.append({"case_id": case_id, "expected_evidence_location": location})
            elif label == "evidence_candidate_found":
                found += 1

    return {
        "total_count": total,
        "labeled_count": labeled,
        "missed_count": missed,
        "found_count": found,
        "examples": missed_examples,
    }


def _tally_review_interface_labels(pairs: list[tuple[dict, dict]], max_examples: int = 3) -> dict:
    total_cases_with_labels = 0
    by_label: dict[str, int] = {}
    examples: dict[str, list[str]] = {}

    for inspection, labels in pairs:
        case_id = inspection["case_id"]
        case_labels = labels.get("review_interface_labels", [])
        if case_labels:
            total_cases_with_labels += 1
        for label in case_labels:
            by_label[label] = by_label.get(label, 0) + 1
            bucket = examples.setdefault(label, [])
            if len(bucket) < max_examples:
                bucket.append(case_id)

    return {
        "total_cases": len(pairs),
        "cases_with_labels": total_cases_with_labels,
        "by_label": by_label,
        "examples": examples,
    }


def _corpus_document_profile(pairs: list[tuple[dict, dict]]) -> dict:
    profiles: dict[str, dict] = {}
    for inspection, _labels in pairs:
        profile = inspection.get("corpus_profile")
        if profile is None:
            continue
        corpus_id = profile.get("corpus_id")
        if corpus_id is None:
            continue
        entry = profiles.setdefault(corpus_id, {"case_count": 0, "document_count": None, "section_count": None})
        entry["case_count"] += 1
        entry["document_count"] = profile.get("document_count")
        entry["section_count"] = profile.get("section_count")
    return profiles


def _processing_latency(pairs: list[tuple[dict, dict]]) -> dict:
    per_case = {inspection["case_id"]: inspection["processing_time_seconds"] for inspection, _ in pairs}
    total = sum(per_case.values())
    return {
        "total_seconds": total,
        "mean_seconds": total / len(per_case) if per_case else None,
        "per_case_seconds": per_case,
    }


def _llm_calls_and_cache(pairs: list[tuple[dict, dict]]) -> dict:
    per_case_calls = {inspection["case_id"]: inspection["llm_call_count"] for inspection, _ in pairs}
    total_hits = sum(inspection["cache_statistics"]["cache_hits"] for inspection, _ in pairs)
    total_misses = sum(inspection["cache_statistics"]["cache_misses"] for inspection, _ in pairs)
    return {
        "total_llm_calls": sum(per_case_calls.values()),
        "per_case_llm_calls": per_case_calls,
        "total_cache_hits": total_hits,
        "total_cache_misses": total_misses,
    }


def _risk_event_usefulness(pairs: list[tuple[dict, dict]], review_interface: dict) -> dict:
    total_risk_events = sum(len(inspection.get("risk_events", [])) for inspection, _ in pairs)
    by_label = review_interface["by_label"]
    return {
        "total_risk_events": total_risk_events,
        "unnecessary_alert_count": by_label.get("unnecessary_alert", 0),
        "missing_useful_warning_count": by_label.get("missing_useful_warning", 0),
        "risk_explanation_understandable_count": by_label.get("risk_explanation_understandable", 0),
    }


def _bottleneck_signals(
    retrieval: dict,
    missed_evidence: dict,
    claim_linking: dict,
    proposition_provenance: dict,
    review_interface: dict,
    pairs: list[tuple[dict, dict]],
) -> dict:
    """Raw signal counts per docs/real-trace-smoke-test-plan.md's decision procedure
    (A-E). This function never decides which bottleneck is *dominant* -- that
    comparison, and whether it justifies dense retrieval, is a human judgment applied
    to these counts, exactly per that doc's explicit "do not automatically implement
    dense retrieval" instruction.
    """

    omitted_signal = sum(len(inspection.get("omitted_context_items") or []) for inspection, _ in pairs)
    provenance_failures = sum(
        count for label, count in proposition_provenance["by_label"].items() if label in _PROVENANCE_FAILURE_LABELS
    )
    spurious_or_missed_links = claim_linking["by_label"].get("spurious_support_link", 0) + claim_linking[
        "by_label"
    ].get("missed_support_link", 0)

    return {
        "A_retrieval_recall_bottleneck": {
            "signal": "expected_evidence_location_labels marked evidence_candidate_missed",
            "count": missed_evidence["missed_count"],
            "labeled_count": missed_evidence["labeled_count"],
        },
        "B_claim_linking_bottleneck": {
            "signal": "claim_linking_labels marked spurious_support_link or missed_support_link",
            "count": spurious_or_missed_links,
            "labeled_count": claim_linking["labeled_count"],
        },
        "C_proposition_bottleneck": {
            "signal": "proposition_provenance_labels marked source_span_invalid/extraction_uncertain/"
            "dependency_missing, or claim_linking_labels marked claim_split_problem",
            "count": provenance_failures + claim_linking["by_label"].get("claim_split_problem", 0),
            "labeled_count": proposition_provenance["labeled_count"],
        },
        "D_context_packing_bottleneck": {
            "signal": "omitted_context_items count across all cases (automatic, not manually labeled)",
            "count": omitted_signal,
            "labeled_count": len(pairs),  # always "labeled" -- this one is computed directly from the trace
        },
        "E_review_interface_bottleneck": {
            "signal": "review_interface_labels marked unnecessary_alert/missing_useful_warning/unresolved",
            "count": sum(review_interface["by_label"].get(label, 0) for label in _REVIEW_INTERFACE_PROBLEM_LABELS),
            "labeled_count": review_interface["cases_with_labels"],
        },
        "note": "Signal counts only -- dominance is a human judgment against "
        "docs/real-trace-smoke-test-plan.md §11, not decided automatically. Dense/hybrid "
        "retrieval should only be prioritized next if A is materially dominant.",
    }


#: Overlap ratio above which a (claim, candidate) pair counts as "topical" for the
#: automatic topical_candidate_rate metric -- deliberately the same threshold family
#: as review/claim_linking.py's pre-engine lexical scoring, just used here only as a
#: descriptive rate, never as a linking decision.
_TOPICAL_OVERLAP_THRESHOLD = 0.2


def _automatic_relationship_rates(pairs: list[tuple[dict, dict]]) -> dict:
    """Rates computed directly from `claim_evidence_comparisons` -- automatic, never
    requiring manual labeling (docs/real-trace-smoke-test-plan.md, "SMOKE-TEST
    REPORTING"). Distinct from, and never collapsed with, the manual
    `claim_linking_usefulness` metric above, which measures whether the *label* a
    human assigned was itself useful/spurious -- these rates only describe what the
    programmatic engine output, without asserting it was correct.
    """

    comparisons = [c for inspection, _labels in pairs for c in inspection.get("claim_evidence_comparisons", [])]
    total = len(comparisons)
    by_status: dict[str, int] = {}
    mismatch_type_counts: dict[str, int] = {}
    topical_count = 0
    for comparison in comparisons:
        status = comparison.get("relationship_status")
        by_status[status] = by_status.get(status, 0) + 1
        for mismatch_type in comparison.get("mismatch_types", []):
            mismatch_type_counts[mismatch_type] = mismatch_type_counts.get(mismatch_type, 0) + 1
        overlap = (comparison.get("lexical_features") or {}).get("overlap_ratio", 0.0)
        if overlap >= _TOPICAL_OVERLAP_THRESHOLD:
            topical_count += 1

    def _rate(status: str) -> float | None:
        return by_status.get(status, 0) / total if total else None

    return {
        "total_claim_candidate_comparisons": total,
        "topical_candidate_rate": topical_count / total if total else None,
        "direct_support_candidate_rate": _rate("direct_support_candidate"),
        "partial_support_candidate_rate": _rate("partial_support_candidate"),
        "qualification_required_rate": _rate("qualification_required"),
        "contradiction_candidate_rate": _rate("contradiction_candidate"),
        "conflict_candidate_rate": _rate("conflict_candidate"),
        "no_support_rate": _rate("no_support_edge_found"),
        "unresolved_rate": _rate("unresolved"),
        "structured_mismatch_types": mismatch_type_counts,
    }


def _evidence_set_summary(pairs: list[tuple[dict, dict]]) -> dict:
    """Rates computed directly from `evidence_sets`/`evidence_set_metrics` -- automatic,
    never requiring manual labeling. `attempted_count`/`skipped_count` are disjoint and
    sum to the total claim count for which construction was invoked (once per claim);
    a case can `skip` construction (single-passage support already found, or the claim
    had no critical components) without that being a problem -- see
    docs/multi-passage-evidence-plan.md, "Do not force smoke-005 into composite support
    if the synthetic source texts lack the explicit information required."
    """

    metrics_entries = [m for inspection, _labels in pairs for m in inspection.get("evidence_set_metrics", [])]
    evidence_sets = [e for inspection, _labels in pairs for e in inspection.get("evidence_sets", [])]

    attempted = [m for m in metrics_entries if m.get("attempted")]
    skipped = [m for m in metrics_entries if not m.get("attempted")]
    by_status: dict[str, int] = {}
    for evidence_set in evidence_sets:
        status = evidence_set.get("relationship_status")
        by_status[status] = by_status.get(status, 0) + 1

    return {
        "claims_evaluated": len(metrics_entries),
        "attempted_count": len(attempted),
        "skipped_count": len(skipped),
        "skip_reasons": {
            reason: sum(1 for m in skipped if m.get("skip_reason") == reason)
            for reason in {m.get("skip_reason") for m in skipped if m.get("skip_reason")}
        },
        "relationship_status_counts": by_status,
        "mean_candidate_pool_size": (
            sum(m.get("candidate_pool_size", 0) for m in attempted) / len(attempted) if attempted else None
        ),
        "mean_sets_considered": (
            sum(m.get("sets_considered", 0) for m in attempted) / len(attempted) if attempted else None
        ),
        "mean_construction_latency_seconds": (
            sum(m.get("construction_latency_seconds", 0.0) for m in metrics_entries) / len(metrics_entries)
            if metrics_entries
            else None
        ),
    }


def generate_report(output_dir: Path) -> dict:
    pairs = _load_case_artifacts(output_dir)

    retrieval = _tally_dict_labels(pairs, "retrieval_candidate_labels")
    missed_evidence = _tally_expected_evidence_locations(pairs)
    claim_linking = _tally_dict_labels(pairs, "claim_linking_labels")
    proposition_provenance = _tally_dict_labels(pairs, "proposition_provenance_labels")
    review_interface = _tally_review_interface_labels(pairs)

    return {
        "case_count": len(pairs),
        "corpus_document_profile": _corpus_document_profile(pairs),
        "retrieval_candidate_usefulness": retrieval,
        "missed_evidence_count": missed_evidence,
        "claim_linking_usefulness": claim_linking,
        "spurious_link_count": {
            "count": claim_linking["by_label"].get("spurious_support_link", 0),
            "examples": claim_linking["examples"].get("spurious_support_link", []),
        },
        "answer_claim_split_problems": {
            "count": claim_linking["by_label"].get("claim_split_problem", 0),
            "examples": claim_linking["examples"].get("claim_split_problem", []),
        },
        "provenance_failures": {
            "count": sum(
                count
                for label, count in proposition_provenance["by_label"].items()
                if label in _PROVENANCE_FAILURE_LABELS
            ),
            "by_label": {
                label: count
                for label, count in proposition_provenance["by_label"].items()
                if label in _PROVENANCE_FAILURE_LABELS
            },
            "examples": {
                label: examples
                for label, examples in proposition_provenance["examples"].items()
                if label in _PROVENANCE_FAILURE_LABELS
            },
        },
        "risk_event_usefulness": _risk_event_usefulness(pairs, review_interface),
        "review_interface_problems": review_interface,
        "processing_latency": _processing_latency(pairs),
        "llm_calls_and_cache": _llm_calls_and_cache(pairs),
        "automatic_relationship_rates": _automatic_relationship_rates(pairs),
        "evidence_set_summary": _evidence_set_summary(pairs),
        "manual_support_link_usefulness_rate": (
            claim_linking["by_label"].get("useful_support_link", 0) / claim_linking["labeled_count"]
            if claim_linking["labeled_count"]
            else None
        ),
        "manual_spurious_link_rate": (
            claim_linking["by_label"].get("spurious_support_link", 0) / claim_linking["labeled_count"]
            if claim_linking["labeled_count"]
            else None
        ),
        "bottleneck_signals": _bottleneck_signals(
            retrieval, missed_evidence, claim_linking, proposition_provenance, review_interface, pairs
        ),
        "caveats": _CAVEATS,
    }
