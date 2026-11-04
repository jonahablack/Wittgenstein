"""The real-corpus evidence-set diagnostic harness, end to end --
docs/evidence-set-real-corpus-diagnostics-plan.md. Runs against the bundled
`widget-certification-demo` fixture only (no real/restricted document text required
for this test file).
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from wittgenstein.evidence_set_diagnostics.report import generate_diagnostic_report
from wittgenstein.evidence_set_diagnostics.runner import (
    build_diagnostic_labels_template,
    build_diagnostic_report,
    run_diagnostic_case,
    run_evidence_set_diagnostics,
)
from wittgenstein.schemas.smoke_test import SmokeTestCaseFile
from wittgenstein.smoke_test.manifest_registry import load_manifests

_REPO_ROOT = Path(__file__).resolve().parents[2]
_CASES_PATH = _REPO_ROOT / "data/examples/evidence_set_diagnostics/cases.example.json"
_MANIFESTS_PATH = _REPO_ROOT / "data/examples/evidence_set_diagnostics/manifests.json"


def _load_case_file() -> SmokeTestCaseFile:
    return SmokeTestCaseFile.model_validate(json.loads(_CASES_PATH.read_text()))


def test_bundled_diagnostic_cases_file_is_valid() -> None:
    case_file = _load_case_file()
    assert len(case_file.cases) >= 2
    assert len({c.case_id for c in case_file.cases}) == len(case_file.cases)


def test_run_case_works_without_any_llm_call() -> None:
    case_file = _load_case_file()
    manifests = load_manifests(_MANIFESTS_PATH)
    case = case_file.cases[0]

    result = run_diagnostic_case(case, manifests)
    assert result.imported_answer.metrics.llm_call_count == 0
    assert result.imported_answer.llm_extractions == []


def test_diagnostic_report_contains_all_required_sections() -> None:
    case_file = _load_case_file()
    manifests = load_manifests(_MANIFESTS_PATH)
    case = next(c for c in case_file.cases if c.case_id == "diag-001-cross-reference-packed")

    result = run_diagnostic_case(case, manifests)
    report = build_diagnostic_report(result)
    for key in (
        "retrieval_candidates",
        "packed_context_items",
        "answer_claims",
        "claim_evidence_comparisons",
        "evidence_sets",
        "evidence_set_metrics",
        "cross_reference_markers",
        "conflict_explanations",
        "size3_diagnostics",
        "risk_events",
    ):
        assert key in report

    # This case's own known-good behavior (empirically verified while building this
    # harness): "Section 4" resolves to a packed segment (no warning), "Exemption C"
    # is body text, not a heading, so it cannot be location-matched.
    markers = [m for markers in report["cross_reference_markers"].values() for m in markers]
    assert any(m["marker_text"] == "Section 4" and m["target_state"] == "packed" for m in markers)
    assert any(m["marker_text"] == "Exemption C" and m["warning"] is not None for m in markers)


def test_diagnostic_conflict_case_produces_a_conflict_explanation() -> None:
    case_file = _load_case_file()
    manifests = load_manifests(_MANIFESTS_PATH)
    case = next(c for c in case_file.cases if c.case_id == "diag-002-compound-claim-real-corpus-conflict")

    result = run_diagnostic_case(case, manifests)
    assert result.conflict_explanations
    report = build_diagnostic_report(result)
    explanations = next(iter(report["conflict_explanations"].values()))
    explanation = explanations[0]
    for key in (
        "field_name",
        "member_a_context_item_id",
        "member_b_context_item_id",
        "member_a_span",
        "member_b_span",
        "extraction_method",
        "confidence",
        "rests_on_low_confidence_field",
        "alternative_non_conflict_classification_plausible",
    ):
        assert key in explanation


def test_diagnostic_labels_template_has_empty_slots() -> None:
    case_file = _load_case_file()
    manifests = load_manifests(_MANIFESTS_PATH)
    case = next(c for c in case_file.cases if c.case_id == "diag-001-cross-reference-packed")

    result = run_diagnostic_case(case, manifests)
    template = build_diagnostic_labels_template(result)
    assert all(v is None for v in template["extraction_quality_labels"].values())
    assert all(v is None for v in template["cross_reference_closure_labels"].values())
    assert template["allowed_values"]["extraction_quality_labels"]
    assert template["allowed_values"]["conflict_quality_labels"]
    assert template["allowed_values"]["cross_reference_closure_labels"]
    assert template["allowed_values"]["evidence_set_sizing_labels"]
    assert template["allowed_values"]["reviewer_workflow_labels"]


def test_size3_diagnostic_mode_is_opt_in() -> None:
    case_file = _load_case_file()
    manifests = load_manifests(_MANIFESTS_PATH)
    case = next(c for c in case_file.cases if c.case_id == "diag-002-compound-claim-real-corpus-conflict")

    default_result = run_diagnostic_case(case, manifests)
    for diagnostic in default_result.size3_diagnostics.values():
        assert diagnostic.size3_search_run is False

    size3_result = run_diagnostic_case(case, manifests, diagnostic_max_set_size=3)
    assert any(d.size3_search_run for d in size3_result.size3_diagnostics.values())


def test_normal_max_set_size_remains_2_regardless_of_diagnostic_flag() -> None:
    """The diagnostic flag must never change what `import_answer` itself constructs --
    only the *diagnostic* size-3 search it additionally runs.
    """

    case_file = _load_case_file()
    manifests = load_manifests(_MANIFESTS_PATH)
    case = next(c for c in case_file.cases if c.case_id == "diag-002-compound-claim-real-corpus-conflict")

    default_result = run_diagnostic_case(case, manifests)
    size3_result = run_diagnostic_case(case, manifests, diagnostic_max_set_size=3)
    assert [es.relationship_status for es in default_result.imported_answer.evidence_sets] == [
        es.relationship_status for es in size3_result.imported_answer.evidence_sets
    ]
    assert [es.member_context_item_ids for es in default_result.imported_answer.evidence_sets] == [
        es.member_context_item_ids for es in size3_result.imported_answer.evidence_sets
    ]


def test_deterministic_diagnostic_output() -> None:
    case_file = _load_case_file()
    manifests = load_manifests(_MANIFESTS_PATH)
    case = case_file.cases[0]

    first = build_diagnostic_report(run_diagnostic_case(case, manifests))
    second = build_diagnostic_report(run_diagnostic_case(case, manifests))
    first.pop("processing_time_seconds")
    second.pop("processing_time_seconds")
    for report in (first, second):
        for es in report["evidence_sets"]:
            es.pop("evidence_set_id", None)
        for metrics in report["evidence_set_metrics"]:
            metrics.pop("construction_latency_seconds", None)
        for comparison in report["claim_evidence_comparisons"]:
            comparison.pop("comparison_id", None)
        for event in report["risk_events"]:
            event.pop("risk_event_id", None)
        if report.get("corpus_profile"):
            report["corpus_profile"].pop("index_timestamp", None)
    assert first == second


def test_full_harness_run_and_report_via_temp_dir(tmp_path: Path) -> None:
    results = run_evidence_set_diagnostics(_CASES_PATH, tmp_path)
    assert len(results) == 2
    assert (tmp_path / "diag-001-cross-reference-packed.diagnostic.json").exists()
    assert (tmp_path / "diag-001-cross-reference-packed.diagnostic_labels.json").exists()

    report = generate_diagnostic_report(tmp_path)
    assert report["case_count"] == 2
    assert report["cross_reference_target_states"]["total_markers"] > 0
    assert report["conflict_diagnostics"]["total_conflicts_explained"] > 0
    assert "caveats" in report and report["caveats"]


def test_no_restricted_content_committed_under_local_corpora() -> None:
    local_corpora = _REPO_ROOT / "data/examples/evidence_set_diagnostics/local_corpora"
    result = subprocess.run(
        ["git", "check-ignore", "-q", str(local_corpora / "anything.txt")],
        cwd=_REPO_ROOT,
    )
    assert result.returncode == 0  # 0 means git-ignore matched -- the path would be excluded


def test_evidence_set_diagnose_cli_runs(tmp_path: Path) -> None:
    result = subprocess.run(
        [
            "uv",
            "run",
            "wittgenstein",
            "evidence-set",
            "diagnose",
            "--cases",
            str(_CASES_PATH),
            "--output-dir",
            str(tmp_path),
        ],
        cwd=_REPO_ROOT,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    assert (tmp_path / "summary.json").exists()
