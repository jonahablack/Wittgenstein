"""The bundled real-trace smoke-test example cases and the smoke-test runner itself
(docs/real-trace-smoke-test-plan.md). All cases here are `synthetic_fictional`
(the widget-certification demo corpus) -- no real or restricted document text is
read or required for this test file.
"""

from __future__ import annotations

import json
from pathlib import Path

from wittgenstein.core.enums import PilotCoverageLabel, ProvenanceStatus
from wittgenstein.schemas.smoke_test import SmokeTestCaseFile
from wittgenstein.smoke_test.corpus_registry import SmokeTestCorpusError, resolve_corpus
from wittgenstein.smoke_test.manifest_registry import load_manifests
from wittgenstein.smoke_test.runner import build_inspection_report, build_labels_template, run_case, run_smoke_test

_REPO_ROOT = Path(__file__).resolve().parents[2]
_CASES_PATH = _REPO_ROOT / "data/examples/real_trace_smoke/cases.example.json"
_MANIFESTS_PATH = _REPO_ROOT / "data/examples/real_trace_smoke/manifests.json"


def _load_case_file() -> SmokeTestCaseFile:
    return SmokeTestCaseFile.model_validate(json.loads(_CASES_PATH.read_text()))


def test_bundled_example_cases_file_is_valid_and_non_empty() -> None:
    case_file = _load_case_file()
    assert len(case_file.cases) >= 6
    assert len({c.case_id for c in case_file.cases}) == len(case_file.cases)  # unique ids


def test_bundled_example_cases_are_all_synthetic_fictional() -> None:
    """No real or restricted document text may ship in this repository -- every
    bundled example case's provenance must be synthetic_fictional.
    """

    case_file = _load_case_file()
    for case in case_file.cases:
        assert case.provenance_status == ProvenanceStatus.SYNTHETIC_FICTIONAL
        assert case.corpus.source_type == "bundled_synthetic_fixture"
        assert case.corpus.local_path is None


def test_bundled_example_cases_cover_every_required_pilot_variation() -> None:
    """The pilot must contain enough variation to expose problems -- every category
    docs/real-trace-smoke-test-plan.md requires must be exercised by at least one case.
    """

    case_file = _load_case_file()
    covered = {label for case in case_file.cases for label in case.pilot_coverage_labels}
    assert covered == set(PilotCoverageLabel)


def test_manifests_registry_loads_and_matches_case_references() -> None:
    manifests = load_manifests(_MANIFESTS_PATH)
    case_file = _load_case_file()
    for case in case_file.cases:
        assert case.pipeline_manifest_id in manifests


def test_resolve_corpus_for_bundled_fixture() -> None:
    case_file = _load_case_file()
    documents = resolve_corpus(case_file.cases[0].corpus)
    assert "certification-handbook" in documents
    assert "inspection-procedures" in documents


def test_resolve_corpus_rejects_unknown_bundled_fixture_id() -> None:
    from wittgenstein.schemas.smoke_test import CorpusReference

    ref = CorpusReference(corpus_id="not-a-real-fixture", source_type="bundled_synthetic_fixture")
    try:
        resolve_corpus(ref)
        raise AssertionError("expected SmokeTestCorpusError")
    except SmokeTestCorpusError:
        pass


def test_run_case_works_without_any_llm_call() -> None:
    case_file = _load_case_file()
    manifests = load_manifests(_MANIFESTS_PATH)
    case = case_file.cases[0]

    result = run_case(case, manifests)
    assert result.imported_answer.metrics.llm_call_count == 0
    assert result.imported_answer.llm_extractions == []


def test_run_case_produces_link_scores_for_every_claim() -> None:
    case_file = _load_case_file()
    manifests = load_manifests(_MANIFESTS_PATH)
    case = next(c for c in case_file.cases if c.case_id == "smoke-002-partial-multi-claim")

    result = run_case(case, manifests)
    assert len(result.link_scores) == len(result.imported_answer.trace.answer_claims)
    for claim in result.imported_answer.trace.answer_claims:
        assert claim.claim_id in result.link_scores


def test_conflict_case_does_not_yield_unsupported_direct_or_partial_support() -> None:
    """smoke-004-conflict-negation's answer ("A Temporary Variance does allow
    deviation...") directly contradicts the corpus ("it does not permit deviation...").
    The relevant source clause refers back to "Temporary Variance" only via the
    pronoun "it" -- resolving that reference is coreference resolution, which this
    milestone's regex/lexicon extraction deliberately does not attempt
    (docs/claim-linking-improvement-plan.md's programmatic-extraction scope). Without
    it, entity alignment to that specific clause cannot be established, so the
    conservative, honest outcome is `unresolved` -- not a silently wrong
    `direct_support_candidate`/`partial_support_candidate` for a claim that actually
    contradicts its source. (Before the field-comparison engine, this case was
    mislabeled under the old, now-retired `conflict_candidate`-for-single-source
    meaning; `conflict_candidate` is now reserved for genuine multi-source
    disagreement, per docs/claim-linking-improvement-plan.md rule E.)
    """

    from wittgenstein.core.enums import ClaimSupportCandidateStatus

    case_file = _load_case_file()
    manifests = load_manifests(_MANIFESTS_PATH)
    case = next(c for c in case_file.cases if c.case_id == "smoke-004-conflict-negation")

    result = run_case(case, manifests)
    statuses = {e.candidate_support_status for e in result.imported_answer.trace.answer_support_edges}
    assert statuses == {ClaimSupportCandidateStatus.UNRESOLVED}
    assert ClaimSupportCandidateStatus.DIRECT_SUPPORT_CANDIDATE not in statuses
    assert ClaimSupportCandidateStatus.PARTIAL_SUPPORT_CANDIDATE not in statuses


def test_inspection_report_contains_all_required_fields() -> None:
    case_file = _load_case_file()
    manifests = load_manifests(_MANIFESTS_PATH)
    result = run_case(case_file.cases[0], manifests)
    report = build_inspection_report(result)

    for key in (
        "retrieval_candidates",
        "selected_context_items",
        "packed_context_items",
        "omitted_context_items",
        "compressed_context_items",
        "answer_claims",
        "answer_support_edges",
        "link_scores",
        "risk_events",
        "provenance_status",
        "processing_time_seconds",
        "llm_call_count",
        "cache_statistics",
    ):
        assert key in report


def test_labels_template_has_empty_slots_for_every_artifact() -> None:
    case_file = _load_case_file()
    manifests = load_manifests(_MANIFESTS_PATH)
    result = run_case(case_file.cases[0], manifests)
    template = build_labels_template(result)

    retrieval_ids = {item.item_id for item in result.imported_answer.trace.retrieval_candidates or []}
    assert set(template["retrieval_candidate_labels"]) == retrieval_ids
    assert all(v is None for v in template["retrieval_candidate_labels"].values())
    assert all(v is None for v in template["claim_linking_labels"].values())
    expected_locations = set(result.case.expected_evidence_locations)
    assert set(template["expected_evidence_location_labels"]) == expected_locations
    assert all(
        entry["label"] is None and entry["matched_item_id"] is None
        for entry in template["expected_evidence_location_labels"].values()
    )
    assert template["allowed_values"]["retrieval_candidate_labels"]
    assert template["allowed_values"]["expected_evidence_location_labels"]
    assert template["allowed_values"]["claim_linking_labels"]
    assert template["allowed_values"]["proposition_provenance_labels"]
    assert template["allowed_values"]["review_interface_labels"]


def test_claim_evidence_annotation_template_has_required_fields_and_empty_reviewer_slots() -> None:
    """The manual annotation template for real/licensed runs
    (docs/claim-linking-improvement-plan.md, "SMOKE-TEST REPORTING") -- one entry per
    (claim, candidate) comparison, with the read-only fields pre-filled and every
    reviewer-facing slot empty.
    """

    case_file = _load_case_file()
    manifests = load_manifests(_MANIFESTS_PATH)
    result = run_case(case_file.cases[0], manifests)
    template = build_labels_template(result)

    annotations = template["claim_evidence_annotations"]
    assert len(annotations) == len(result.imported_answer.claim_evidence_comparisons)
    for entry in annotations.values():
        for key in (
            "answer_claim",
            "candidate_passage",
            "field_comparison_vector",
            "candidate_relationship",
            "reviewer_label",
            "reviewer_confidence",
            "reviewer_rationale",
            "unresolved_reason",
            "notes",
        ):
            assert key in entry
        assert entry["answer_claim"] is not None
        assert entry["candidate_passage"] is not None
        assert entry["candidate_relationship"] is not None
        assert entry["field_comparison_vector"]
        assert entry["reviewer_label"] is None
        assert entry["reviewer_confidence"] is None
        assert entry["reviewer_rationale"] is None
        assert entry["unresolved_reason"] is None
        assert entry["notes"] is None


def test_run_smoke_test_writes_a_report_and_labels_file_per_case(tmp_path: Path) -> None:
    output_dir = tmp_path / "out"
    results = run_smoke_test(_CASES_PATH, output_dir)

    case_file = _load_case_file()
    assert len(results) == len(case_file.cases)
    for case in case_file.cases:
        assert (output_dir / f"{case.case_id}.inspection.json").exists()
        assert (output_dir / f"{case.case_id}.labels_template.json").exists()
    assert (output_dir / "summary.json").exists()

    summary = json.loads((output_dir / "summary.json").read_text())
    assert summary["case_count"] == len(case_file.cases)
    assert summary["enhanced"] is False
    assert summary["total_llm_call_count"] == 0


def test_run_smoke_test_enhanced_mode_makes_llm_calls_without_real_credentials(tmp_path: Path) -> None:
    """--enhanced must work without any provider credentials configured (falls back to
    the deterministic offline DemoLLMClient) -- never a hard requirement on a live API.
    """

    output_dir = tmp_path / "out_enhanced"
    results = run_smoke_test(_CASES_PATH, output_dir, enhanced=True)
    total_calls = sum(r.imported_answer.metrics.llm_call_count for r in results)
    assert total_calls > 0


# --- Case validity (test category 1) --------------------------------------------


def test_valid_case_constructs_successfully() -> None:
    from wittgenstein.schemas.smoke_test import CorpusReference, SmokeTestCase

    case = SmokeTestCase(
        case_id="valid-1",
        corpus=CorpusReference(corpus_id="widget-certification-demo", source_type="bundled_synthetic_fixture"),
        query="q",
        answer="a",
        answer_source_method="human_authored_for_pilot",
        pipeline_manifest_id="widget-certification-demo-manifest",
        provenance_status="synthetic_fictional",
    )
    assert case.case_id == "valid-1"


def test_invalid_case_local_path_without_source_type_local_path_rejected() -> None:
    from pydantic import ValidationError
    from wittgenstein.schemas.smoke_test import CorpusReference

    try:
        CorpusReference(
            corpus_id="c1", source_type="bundled_synthetic_fixture", local_path="/tmp/should-not-be-set"
        )
        raise AssertionError("expected ValidationError")
    except ValidationError:
        pass


def test_invalid_case_missing_local_path_for_local_source_type_rejected() -> None:
    from pydantic import ValidationError
    from wittgenstein.schemas.smoke_test import CorpusReference

    try:
        CorpusReference(corpus_id="c1", source_type="local_path_excluded_from_git")
        raise AssertionError("expected ValidationError")
    except ValidationError:
        pass


def test_invalid_case_unknown_source_type_rejected() -> None:
    from pydantic import ValidationError
    from wittgenstein.schemas.smoke_test import CorpusReference

    try:
        CorpusReference(corpus_id="c1", source_type="downloaded_from_the_internet")
        raise AssertionError("expected ValidationError")
    except ValidationError:
        pass


def test_invalid_case_missing_required_field_rejected() -> None:
    from pydantic import ValidationError
    from wittgenstein.schemas.smoke_test import CorpusReference, SmokeTestCase

    try:
        SmokeTestCase(
            case_id="missing-answer",
            corpus=CorpusReference(corpus_id="widget-certification-demo", source_type="bundled_synthetic_fixture"),
            query="q",
            # answer omitted
            answer_source_method="human_authored_for_pilot",
            pipeline_manifest_id="widget-certification-demo-manifest",
            provenance_status="synthetic_fictional",
        )
        raise AssertionError("expected ValidationError")
    except ValidationError:
        pass


# --- Restricted corpus paths never committed (test category 2) ------------------


def test_gitignore_excludes_local_corpora_and_output_directories() -> None:
    gitignore_text = (_REPO_ROOT / ".gitignore").read_text()
    assert "real_trace_smoke/local_corpora/" in gitignore_text
    assert "real_trace_smoke/output/" in gitignore_text


def test_bundled_cases_file_contains_no_local_path_references() -> None:
    """The committed cases.example.json must never reference a local, git-excluded
    path -- only bundled_synthetic_fixture corpora may ship in this repository.
    """

    case_file = _load_case_file()
    for case in case_file.cases:
        assert case.corpus.source_type != "local_path_excluded_from_git"
        assert case.corpus.local_path is None


def test_local_corpora_directory_has_no_tracked_files() -> None:
    """Even if someone later drops real documents under local_corpora/ locally, this
    test guards against any file there ever being accidentally committed by confirming
    the directory (if present) is excluded, not merely empty right now.
    """

    import subprocess

    result = subprocess.run(
        [
            "git",
            "check-ignore",
            "-q",
            str(_REPO_ROOT / "data/examples/real_trace_smoke/local_corpora/anything.txt"),
        ],
        cwd=_REPO_ROOT,
    )
    assert result.returncode == 0  # 0 means git-ignore matched -- the path would be excluded


# --- Determinism (test category 10) ----------------------------------------------


def _normalize_for_determinism_comparison(report: dict) -> dict:
    """Strips fields expected to legitimately vary run-to-run (wall-clock timing,
    risk_event_id -- minted fresh via uuid4 by
    `services/applicability_service.py::new_risk_event_id` on every derivation --
    comparison_id -- minted fresh via uuid4 by
    `review/claim_linking.py::compare_claim_to_candidate` -- evidence_set_id -- minted
    fresh via uuid4 by `review/evidence_set.py::construct_evidence_set` -- and
    corpus_profile.index_timestamp, stamped fresh by each `index_corpus` call) so this
    comparison is about substantive pipeline output -- retrieval ranks, claims, links,
    and risk-event *content* -- not incidental identifiers or timing.
    """

    report = dict(report)
    report.pop("processing_time_seconds", None)
    report["risk_events"] = [
        {k: v for k, v in event.items() if k != "risk_event_id"} for event in report["risk_events"]
    ]
    report["claim_evidence_comparisons"] = [
        {k: v for k, v in comparison.items() if k != "comparison_id"}
        for comparison in report["claim_evidence_comparisons"]
    ]
    report["evidence_sets"] = [
        {k: v for k, v in evidence_set.items() if k != "evidence_set_id"}
        for evidence_set in report["evidence_sets"]
    ]
    report["evidence_set_metrics"] = [
        {k: v for k, v in metrics.items() if k != "construction_latency_seconds"}
        for metrics in report["evidence_set_metrics"]
    ]
    if report.get("corpus_profile"):
        report["corpus_profile"] = {k: v for k, v in report["corpus_profile"].items() if k != "index_timestamp"}
    return report


def test_smoke_test_run_case_is_deterministic_across_repeated_runs() -> None:
    case_file = _load_case_file()
    manifests = load_manifests(_MANIFESTS_PATH)
    case = next(c for c in case_file.cases if c.case_id == "smoke-004-conflict-negation")

    first = run_case(case, manifests)
    second = run_case(case, manifests)

    first_report = _normalize_for_determinism_comparison(build_inspection_report(first))
    second_report = _normalize_for_determinism_comparison(build_inspection_report(second))

    assert first_report == second_report
