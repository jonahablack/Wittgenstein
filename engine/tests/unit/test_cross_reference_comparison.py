"""Read-only baseline-vs-post-fix cross-reference comparison --
docs/eu-ai-act-cross-reference-annotation-protocol.md. Synthetic fixtures only (never
real EU AI Act text) -- this module never re-runs the pipeline, so these tests exercise
the comparison logic in isolation against hand-built `*.diagnostic.json` files.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from wittgenstein.evidence_set_diagnostics.cross_reference_comparison import (
    DISCLAIMER,
    generate_comparison_worksheet,
)

_REPO_ROOT = Path(__file__).resolve().parents[2]


def _write_diagnostic(directory: Path, case_id: str, *, markers: dict, extra: dict | None = None) -> None:
    payload = {
        "case_id": case_id,
        "processing_time_seconds": 0.05,
        "retrieval_candidates": [],
        "selected_context_items": [],
        "packed_context_items": [{"item_id": "i1", "segment_id": "seg-1"}],
        "omitted_context_items": [],
        "answer_claims": [{"claim_id": "c1", "text": "placeholder claim text"}],
        "answer_support_edges": [],
        "claim_evidence_comparisons": [],
        "evidence_sets": [],
        "evidence_set_metrics": [],
        "cross_reference_markers": markers,
        "conflict_explanations": {},
        "size3_diagnostics": {},
        "risk_events": [],
    }
    if extra:
        payload.update(extra)
    (directory / f"{case_id}.diagnostic.json").write_text(json.dumps(payload))


def _write_cases_file(path: Path, case_ids: list[str]) -> None:
    cases = [
        {
            "case_id": case_id,
            "corpus": {
                "corpus_id": "test-corpus",
                "source_type": "bundled_synthetic_fixture",
                "local_path": None,
                "document_hashes": {},
                "source_metadata": {},
            },
            "document_version": None,
            "query": f"query for {case_id}",
            "query_constraints": {},
            "user_intent_notes": None,
            "answer": "placeholder answer",
            "answer_source_method": "document_verbatim",
            "pipeline_manifest_id": "m1",
            "expected_evidence_locations": ["doc > Article 1"],
            "pilot_coverage_labels": [],
            "reviewer_notes": None,
            "provenance_status": "synthetic_fictional",
        }
        for case_id in case_ids
    ]
    path.write_text(json.dumps({"cases": cases}))


# --- Deterministic comparison generation -----------------------------------------


def test_comparison_generation_is_deterministic(tmp_path: Path) -> None:
    baseline = tmp_path / "baseline"
    post_fix = tmp_path / "post_fix"
    baseline.mkdir()
    post_fix.mkdir()
    cases_path = tmp_path / "cases.json"
    _write_cases_file(cases_path, ["case-1"])
    _write_diagnostic(baseline, "case-1", markers={})
    _write_diagnostic(
        post_fix, "case-1", markers={"c1": [{"marker_text": "Article 6", "target_state": "unknown"}]}
    )

    first = generate_comparison_worksheet(baseline, post_fix, cases_path)
    second = generate_comparison_worksheet(baseline, post_fix, cases_path)
    first.pop("generated_at")
    second.pop("generated_at")
    assert first == second


# --- Baseline/post-fix case matching -----------------------------------------------


def test_case_matching_reports_missing_case_ids_clearly(tmp_path: Path) -> None:
    baseline = tmp_path / "baseline"
    post_fix = tmp_path / "post_fix"
    baseline.mkdir()
    post_fix.mkdir()
    cases_path = tmp_path / "cases.json"
    _write_cases_file(cases_path, ["case-1", "case-2"])
    _write_diagnostic(baseline, "case-1", markers={})
    _write_diagnostic(post_fix, "case-1", markers={})
    _write_diagnostic(post_fix, "case-2", markers={})  # only in post-fix, not baseline

    worksheet = generate_comparison_worksheet(baseline, post_fix, cases_path)
    assert worksheet["case_ids"]["common"] == ["case-1"]
    assert worksheet["case_ids"]["post_fix_only"] == ["case-2"]
    assert worksheet["case_ids"]["baseline_only"] == []

    case2_entry = next(c for c in worksheet["cases"] if c["case_id"] == "case-2")
    assert case2_entry["present_in_baseline"] is False
    assert case2_entry["present_in_post_fix"] is True


def test_case_in_cases_file_but_missing_from_both_runs_is_reported(tmp_path: Path) -> None:
    baseline = tmp_path / "baseline"
    post_fix = tmp_path / "post_fix"
    baseline.mkdir()
    post_fix.mkdir()
    cases_path = tmp_path / "cases.json"
    _write_cases_file(cases_path, ["case-1", "case-orphan"])
    _write_diagnostic(baseline, "case-1", markers={})
    _write_diagnostic(post_fix, "case-1", markers={})

    worksheet = generate_comparison_worksheet(baseline, post_fix, cases_path)
    assert worksheet["case_ids"]["in_cases_file_only"] == ["case-orphan"]


# --- Newly detected marker computation ---------------------------------------------


def test_newly_detected_markers_computed_correctly(tmp_path: Path) -> None:
    baseline = tmp_path / "baseline"
    post_fix = tmp_path / "post_fix"
    baseline.mkdir()
    post_fix.mkdir()
    cases_path = tmp_path / "cases.json"
    _write_cases_file(cases_path, ["case-1"])
    _write_diagnostic(
        baseline, "case-1", markers={"c1": [{"marker_text": "Section 4", "target_state": "unknown"}]}
    )
    _write_diagnostic(
        post_fix,
        "case-1",
        markers={
            "c1": [
                {"marker_text": "Section 4", "target_state": "unknown"},
                {"marker_text": "Article 6(4)", "target_state": "unknown", "reference_type": "article"},
            ]
        },
    )

    worksheet = generate_comparison_worksheet(baseline, post_fix, cases_path)
    entry = worksheet["cases"][0]
    assert entry["markers_newly_detected"] == [{"marker_text": "Article 6(4)", "reference_type": "article"}]


def test_newly_detected_markers_ignore_reference_type_schema_gap(tmp_path: Path) -> None:
    """A baseline written before `reference_type` existed in the schema must not make
    an otherwise-unchanged marker look "new" -- matching is by marker_text only.
    """

    baseline = tmp_path / "baseline"
    post_fix = tmp_path / "post_fix"
    baseline.mkdir()
    post_fix.mkdir()
    cases_path = tmp_path / "cases.json"
    _write_cases_file(cases_path, ["case-1"])
    _write_diagnostic(
        baseline, "case-1", markers={"c1": [{"marker_text": "Section 4", "target_state": "unknown"}]}
    )  # no reference_type key at all -- pre-fix schema
    _write_diagnostic(
        post_fix,
        "case-1",
        markers={"c1": [{"marker_text": "Section 4", "target_state": "unknown", "reference_type": "section"}]},
    )

    worksheet = generate_comparison_worksheet(baseline, post_fix, cases_path)
    assert worksheet["cases"][0]["markers_newly_detected"] == []


def test_duplicate_marker_occurrences_within_a_case_are_deduplicated_with_count(tmp_path: Path) -> None:
    baseline = tmp_path / "baseline"
    post_fix = tmp_path / "post_fix"
    baseline.mkdir()
    post_fix.mkdir()
    cases_path = tmp_path / "cases.json"
    _write_cases_file(cases_path, ["case-1"])
    _write_diagnostic(baseline, "case-1", markers={})
    _write_diagnostic(
        post_fix,
        "case-1",
        markers={
            "c1": [{"marker_text": "Annex III", "target_state": "unknown", "reference_type": "annex"}],
            "c2": [{"marker_text": "Annex III", "target_state": "unknown", "reference_type": "annex"}],
            "c3": [{"marker_text": "Annex III", "target_state": "unknown", "reference_type": "annex"}],
        },
    )

    worksheet = generate_comparison_worksheet(baseline, post_fix, cases_path)
    entry = worksheet["cases"][0]
    assert len(entry["post_fix_markers"]) == 1
    assert entry["post_fix_markers"][0]["occurrence_count"] == 3
    assert entry["markers_newly_detected"] == [{"marker_text": "Annex III", "reference_type": "annex"}]


# --- Changed target-state computation ----------------------------------------------


def test_changed_target_state_computed_correctly(tmp_path: Path) -> None:
    baseline = tmp_path / "baseline"
    post_fix = tmp_path / "post_fix"
    baseline.mkdir()
    post_fix.mkdir()
    cases_path = tmp_path / "cases.json"
    _write_cases_file(cases_path, ["case-1"])
    _write_diagnostic(
        baseline, "case-1", markers={"c1": [{"marker_text": "Article 49(2)", "target_state": "unknown"}]}
    )
    _write_diagnostic(
        post_fix, "case-1", markers={"c1": [{"marker_text": "Article 49(2)", "target_state": "packed"}]}
    )

    worksheet = generate_comparison_worksheet(baseline, post_fix, cases_path)
    changed = worksheet["cases"][0]["target_states_changed"]
    assert len(changed) == 1
    assert changed[0]["baseline_target_state"] == "unknown"
    assert changed[0]["post_fix_target_state"] == "packed"


def test_unchanged_target_state_not_reported_as_changed(tmp_path: Path) -> None:
    baseline = tmp_path / "baseline"
    post_fix = tmp_path / "post_fix"
    baseline.mkdir()
    post_fix.mkdir()
    cases_path = tmp_path / "cases.json"
    _write_cases_file(cases_path, ["case-1"])
    _write_diagnostic(
        baseline, "case-1", markers={"c1": [{"marker_text": "Section 4", "target_state": "unknown"}]}
    )
    _write_diagnostic(
        post_fix, "case-1", markers={"c1": [{"marker_text": "Section 4", "target_state": "unknown"}]}
    )

    worksheet = generate_comparison_worksheet(baseline, post_fix, cases_path)
    assert worksheet["cases"][0]["target_states_changed"] == []


# --- No automatic human labels ------------------------------------------------------


def test_worksheet_contains_no_human_judgment_fields(tmp_path: Path) -> None:
    baseline = tmp_path / "baseline"
    post_fix = tmp_path / "post_fix"
    baseline.mkdir()
    post_fix.mkdir()
    cases_path = tmp_path / "cases.json"
    _write_cases_file(cases_path, ["case-1"])
    _write_diagnostic(baseline, "case-1", markers={})
    _write_diagnostic(
        post_fix, "case-1", markers={"c1": [{"marker_text": "Article 6", "target_state": "unknown"}]}
    )

    worksheet = generate_comparison_worksheet(baseline, post_fix, cases_path)

    def _collect_keys(value: object, keys: set[str]) -> None:
        if isinstance(value, dict):
            keys.update(value.keys())
            for v in value.values():
                _collect_keys(v, keys)
        elif isinstance(value, list):
            for v in value:
                _collect_keys(v, keys)

    all_keys: set[str] = set()
    _collect_keys(worksheet, all_keys)
    # Structural check: no dict key anywhere in the worksheet is itself a
    # human-judgment field -- the disclaimer's own cautionary prose is allowed to
    # *discuss* these concepts (that's the whole point of the warning), but no field
    # in the data structure may hold such a judgment, since none was ever made.
    forbidden_keys = {
        "usefulness",
        "necessity",
        "false_reassurance",
        "unnecessary_escalation",
        "reviewer_label",
        "legal_correctness",
        "target_needed_to_interpret_claim",
    }
    assert not (forbidden_keys & all_keys)
    assert worksheet["disclaimer"] == DISCLAIMER


# --- No pipeline modifications ------------------------------------------------------


def test_comparison_never_writes_to_input_directories(tmp_path: Path) -> None:
    baseline = tmp_path / "baseline"
    post_fix = tmp_path / "post_fix"
    baseline.mkdir()
    post_fix.mkdir()
    cases_path = tmp_path / "cases.json"
    _write_cases_file(cases_path, ["case-1"])
    _write_diagnostic(baseline, "case-1", markers={})
    _write_diagnostic(post_fix, "case-1", markers={})

    before_baseline = {p: p.read_text() for p in baseline.iterdir()}
    before_post_fix = {p: p.read_text() for p in post_fix.iterdir()}
    generate_comparison_worksheet(baseline, post_fix, cases_path)
    after_baseline = {p: p.read_text() for p in baseline.iterdir()}
    after_post_fix = {p: p.read_text() for p in post_fix.iterdir()}

    assert before_baseline == after_baseline
    assert before_post_fix == after_post_fix


def test_cli_refuses_to_write_worksheet_to_a_tracked_path(tmp_path: Path) -> None:
    """The CLI command must refuse to write the worksheet anywhere git could track --
    the worksheet can embed source-derived claim/answer text from the diagnose runs.
    """

    baseline = tmp_path / "baseline"
    post_fix = tmp_path / "post_fix"
    baseline.mkdir()
    post_fix.mkdir()
    cases_path = tmp_path / "cases.json"
    _write_cases_file(cases_path, ["case-1"])
    _write_diagnostic(baseline, "case-1", markers={})
    _write_diagnostic(post_fix, "case-1", markers={})

    tracked_output = _REPO_ROOT / "docs" / "should-not-be-written-by-a-test.json"
    result = subprocess.run(
        [
            "uv",
            "run",
            "wittgenstein",
            "evidence-set",
            "compare-cross-reference",
            "--baseline",
            str(baseline),
            "--post-fix",
            str(post_fix),
            "--cases",
            str(cases_path),
            "--output",
            str(tracked_output),
        ],
        cwd=_REPO_ROOT,
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0
    assert not tracked_output.exists()


def test_cli_writes_worksheet_to_a_gitignored_path(tmp_path: Path) -> None:
    baseline = tmp_path / "baseline"
    post_fix = tmp_path / "post_fix"
    baseline.mkdir()
    post_fix.mkdir()
    cases_path = tmp_path / "cases.json"
    _write_cases_file(cases_path, ["case-1"])
    _write_diagnostic(baseline, "case-1", markers={})
    _write_diagnostic(post_fix, "case-1", markers={})

    gitignored_output = (
        _REPO_ROOT
        / "data/examples/evidence_set_diagnostics/local_corpora/eu-ai-act-2024/output-after-article-xref"
        / "test-worksheet-tmp.json"
    )
    result = subprocess.run(
        [
            "uv",
            "run",
            "wittgenstein",
            "evidence-set",
            "compare-cross-reference",
            "--baseline",
            str(baseline),
            "--post-fix",
            str(post_fix),
            "--cases",
            str(cases_path),
            "--output",
            str(gitignored_output),
        ],
        cwd=_REPO_ROOT,
        capture_output=True,
        text=True,
    )
    try:
        assert result.returncode == 0, result.stderr
        assert gitignored_output.exists()
    finally:
        gitignored_output.unlink(missing_ok=True)
