"""Report generation over (possibly human-filled-in) labels templates
(docs/real-trace-smoke-test-plan.md, "Produce summary metrics"). Uses synthetic
inspection-report/labels-template fixtures rather than a full pipeline run, so these
tests exercise the tallying logic in isolation. Test categories 6, 7, 8, 9.
"""

from __future__ import annotations

import json
from pathlib import Path

from wittgenstein.smoke_test.report import generate_report


def _write_case(output_dir: Path, case_id: str, *, inspection: dict, labels: dict) -> None:
    base_inspection = {
        "case_id": case_id,
        "provenance_status": "synthetic_fictional",
        "processing_time_seconds": 0.1,
        "llm_call_count": 0,
        "cache_statistics": {"cache_hits": 0, "cache_misses": 1, "cache_hit_rate": 0.0},
        "corpus_profile": {"corpus_id": "test-corpus", "document_count": 2, "section_count": 5},
        "risk_events": [],
        "omitted_context_items": [],
    }
    base_inspection.update(inspection)
    base_labels = {
        "case_id": case_id,
        "retrieval_candidate_labels": {},
        "expected_evidence_location_labels": {},
        "claim_linking_labels": {},
        "proposition_provenance_labels": {},
        "review_interface_labels": [],
    }
    base_labels.update(labels)

    (output_dir / f"{case_id}.inspection.json").write_text(json.dumps(base_inspection))
    (output_dir / f"{case_id}.labels_template.json").write_text(json.dumps(base_labels))


def test_report_over_zero_cases_is_honest_about_emptiness(tmp_path: Path) -> None:
    report = generate_report(tmp_path)
    assert report["case_count"] == 0
    assert report["claim_linking_usefulness"]["labeled_count"] == 0
    assert report["missed_evidence_count"]["labeled_count"] == 0


def test_unlabeled_case_reports_zero_labeled_not_zero_observed(tmp_path: Path) -> None:
    _write_case(
        tmp_path,
        "case-1",
        inspection={},
        labels={"retrieval_candidate_labels": {"item-1": None, "item-2": None}},
    )
    report = generate_report(tmp_path)
    retrieval = report["retrieval_candidate_usefulness"]
    assert retrieval["total_count"] == 2
    assert retrieval["labeled_count"] == 0
    assert retrieval["by_label"] == {}


def test_claim_linking_diagnostics_tally_by_label_with_examples(tmp_path: Path) -> None:
    _write_case(
        tmp_path,
        "case-1",
        inspection={},
        labels={
            "claim_linking_labels": {
                "claim-1": "useful_support_link",
                "claim-2": "spurious_support_link",
                "claim-3": None,
            }
        },
    )
    report = generate_report(tmp_path)
    claim_linking = report["claim_linking_usefulness"]
    assert claim_linking["total_count"] == 3
    assert claim_linking["labeled_count"] == 2
    assert claim_linking["by_label"] == {"useful_support_link": 1, "spurious_support_link": 1}
    assert report["spurious_link_count"]["count"] == 1
    assert report["spurious_link_count"]["examples"][0]["case_id"] == "case-1"


def test_answer_claim_split_problems_counted_from_claim_linking_labels(tmp_path: Path) -> None:
    _write_case(
        tmp_path,
        "case-1",
        inspection={},
        labels={"claim_linking_labels": {"claim-1": "claim_split_problem"}},
    )
    report = generate_report(tmp_path)
    assert report["answer_claim_split_problems"]["count"] == 1


def test_missed_evidence_count_uses_expected_location_labels_not_retrieved_items(tmp_path: Path) -> None:
    """A missed location has no item_id -- this must be tallied from
    expected_evidence_location_labels, never from retrieval_candidate_labels (which
    is keyed only by items that WERE retrieved).
    """

    _write_case(
        tmp_path,
        "case-1",
        inspection={},
        labels={
            "expected_evidence_location_labels": {
                "Section 1": {"label": "evidence_candidate_found", "matched_item_id": "item-1"},
                "Section 2": {"label": "evidence_candidate_missed", "matched_item_id": None},
            }
        },
    )
    report = generate_report(tmp_path)
    missed = report["missed_evidence_count"]
    assert missed["missed_count"] == 1
    assert missed["found_count"] == 1
    assert missed["examples"][0]["expected_evidence_location"] == "Section 2"


def test_provenance_diagnostics_tally_failures_distinct_from_valid(tmp_path: Path) -> None:
    _write_case(
        tmp_path,
        "case-1",
        inspection={},
        labels={
            "proposition_provenance_labels": {
                "item-1": "source_span_valid",
                "item-2": "source_span_invalid",
                "item-3": "extraction_uncertain",
                "item-4": "dependency_missing",
                "item-5": "dependency_available",
            }
        },
    )
    report = generate_report(tmp_path)
    failures = report["provenance_failures"]
    assert failures["count"] == 3
    assert set(failures["by_label"]) == {"source_span_invalid", "extraction_uncertain", "dependency_missing"}
    assert "source_span_valid" not in failures["by_label"]
    assert "dependency_available" not in failures["by_label"]


def test_risk_event_diagnostics_combine_automatic_count_and_manual_labels(tmp_path: Path) -> None:
    _write_case(
        tmp_path,
        "case-1",
        inspection={"risk_events": [{"risk_event_id": "RISK-1"}, {"risk_event_id": "RISK-2"}]},
        labels={"review_interface_labels": ["unnecessary_alert", "risk_explanation_understandable"]},
    )
    report = generate_report(tmp_path)
    risk_usefulness = report["risk_event_usefulness"]
    assert risk_usefulness["total_risk_events"] == 2  # automatic, from the trace -- never requires labeling
    assert risk_usefulness["unnecessary_alert_count"] == 1
    assert risk_usefulness["risk_explanation_understandable_count"] == 1
    assert risk_usefulness["missing_useful_warning_count"] == 0


def test_review_interface_problems_tallied_per_case_list(tmp_path: Path) -> None:
    _write_case(tmp_path, "case-1", inspection={}, labels={"review_interface_labels": ["evidence_easy_to_locate"]})
    _write_case(tmp_path, "case-2", inspection={}, labels={"review_interface_labels": []})
    report = generate_report(tmp_path)
    interface = report["review_interface_problems"]
    assert interface["total_cases"] == 2
    assert interface["cases_with_labels"] == 1
    assert interface["by_label"] == {"evidence_easy_to_locate": 1}


def test_corpus_document_profile_aggregates_across_cases(tmp_path: Path) -> None:
    _write_case(tmp_path, "case-1", inspection={}, labels={})
    _write_case(tmp_path, "case-2", inspection={}, labels={})
    report = generate_report(tmp_path)
    profile = report["corpus_document_profile"]["test-corpus"]
    assert profile["case_count"] == 2
    assert profile["document_count"] == 2


def test_processing_latency_and_llm_cache_metrics_reported_per_case(tmp_path: Path) -> None:
    _write_case(
        tmp_path,
        "case-1",
        inspection={
            "processing_time_seconds": 0.5,
            "llm_call_count": 2,
            "cache_statistics": {"cache_hits": 3, "cache_misses": 1, "cache_hit_rate": 0.75},
        },
        labels={},
    )
    report = generate_report(tmp_path)
    assert report["processing_latency"]["total_seconds"] == 0.5
    assert report["processing_latency"]["per_case_seconds"] == {"case-1": 0.5}
    assert report["llm_calls_and_cache"]["total_llm_calls"] == 2
    assert report["llm_calls_and_cache"]["total_cache_hits"] == 3
    assert report["llm_calls_and_cache"]["total_cache_misses"] == 1


def test_bottleneck_signals_never_declare_a_dominant_bottleneck_automatically(tmp_path: Path) -> None:
    """The report only ever surfaces raw signal counts -- it must never itself assert
    which bottleneck is dominant or that dense retrieval is justified.
    """

    _write_case(
        tmp_path,
        "case-1",
        inspection={},
        labels={
            "expected_evidence_location_labels": {
                "loc": {"label": "evidence_candidate_missed", "matched_item_id": None}
            }
        },
    )
    report = generate_report(tmp_path)
    signals = report["bottleneck_signals"]
    assert signals["A_retrieval_recall_bottleneck"]["count"] == 1
    assert "dominant" not in json.dumps(signals).lower() or "not decided automatically" in signals["note"]
    assert "justified" not in json.dumps(signals).lower()


def test_report_always_carries_the_non_factual_truth_and_non_generalization_caveats(tmp_path: Path) -> None:
    _write_case(tmp_path, "case-1", inspection={}, labels={})
    report = generate_report(tmp_path)
    caveats_text = " ".join(report["caveats"]).lower()
    assert "not factual-truth" in caveats_text
    assert "not a statistically powered" in caveats_text


def test_automatic_relationship_rates_computed_from_claim_evidence_comparisons(tmp_path: Path) -> None:
    """These rates are automatic (from candidate_support_status/relationship_status),
    never requiring manual labeling -- docs/real-trace-smoke-test-plan.md, "SMOKE-TEST
    REPORTING".
    """

    _write_case(
        tmp_path,
        "case-1",
        inspection={
            "claim_evidence_comparisons": [
                {
                    "relationship_status": "direct_support_candidate",
                    "mismatch_types": [],
                    "lexical_features": {"overlap_ratio": 0.9},
                },
                {
                    "relationship_status": "contradiction_candidate",
                    "mismatch_types": ["frequency_mismatch"],
                    "lexical_features": {"overlap_ratio": 0.8},
                },
                {
                    "relationship_status": "no_support_edge_found",
                    "mismatch_types": [],
                    "lexical_features": {"overlap_ratio": 0.0},
                },
            ]
        },
        labels={},
    )
    report = generate_report(tmp_path)
    rates = report["automatic_relationship_rates"]
    assert rates["total_claim_candidate_comparisons"] == 3
    assert rates["direct_support_candidate_rate"] == 1 / 3
    assert rates["contradiction_candidate_rate"] == 1 / 3
    assert rates["no_support_rate"] == 1 / 3
    assert rates["structured_mismatch_types"] == {"frequency_mismatch": 1}
    assert rates["topical_candidate_rate"] == 2 / 3  # two of three have overlap_ratio >= 0.2


def test_automatic_relationship_rates_are_none_when_no_comparisons_present(tmp_path: Path) -> None:
    _write_case(tmp_path, "case-1", inspection={}, labels={})
    report = generate_report(tmp_path)
    rates = report["automatic_relationship_rates"]
    assert rates["total_claim_candidate_comparisons"] == 0
    assert rates["direct_support_candidate_rate"] is None
