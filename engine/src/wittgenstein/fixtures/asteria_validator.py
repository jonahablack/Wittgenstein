"""Fixture-integrity validation for the Asteria controlled synthetic corpus --
docs/controlled-synthetic-corpus-plan.md §14. Runs every executable case through the
real, unmodified pipeline (`review.imported_answer.import_answer`, zero LLM calls) and
checks the result against each case's hand-recorded `expected/<case_id>.expected.json`
ground truth. Never mutates the corpus, registry, or activation policies, and never
makes the review UI display an answer as objectively true or false -- this validator
only ever asserts things about *this codebase's own deterministic output*.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from wittgenstein.core.enums import ClaimSupportCandidateStatus
from wittgenstein.ingestion.corpus_index import index_corpus
from wittgenstein.review.cross_reference_diagnostics import detect_cross_reference_markers
from wittgenstein.review.imported_answer import import_answer
from wittgenstein.schemas.smoke_test import SmokeTestCase, SmokeTestCaseFile
from wittgenstein.smoke_test.corpus_registry import resolve_corpus
from wittgenstein.smoke_test.manifest_registry import load_manifests

#: Manifests deliberately excluded from execution -- representable-but-not-executable
#: configurations (docs/controlled-synthetic-corpus-plan.md §11). Schema validation
#: only; never run through import_answer, here or anywhere else in this milestone.
_NON_EXECUTABLE_MANIFEST_IDS = frozenset({"asteria-p3-parent-context"})


@dataclass
class ValidationIssue:
    check: str
    message: str
    case_id: str | None = None


@dataclass
class ValidationReport:
    case_count: int = 0
    issues: list[ValidationIssue] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.issues

    def add(self, check: str, message: str, case_id: str | None = None) -> None:
        self.issues.append(ValidationIssue(check=check, message=message, case_id=case_id))


def _load_expected(expected_dir: Path, case_id: str) -> dict | None:
    path = expected_dir / f"{case_id}.expected.json"
    if not path.exists():
        return None
    return json.loads(path.read_text())


def _relationship_for_segment(result, segment_id: str) -> ClaimSupportCandidateStatus | None:
    """The strongest (most-supportive) relationship_status found for any
    (claim, context_item) pair whose context_item resolves to `segment_id` --
    a distractor is checked against its *best* outcome, so a validator that misses a
    genuine accidental match never passes by only looking at one claim fragment.
    """

    item_ids = {
        item.item_id for item in (result.trace.packed_context_items or []) if item.segment_id == segment_id
    }
    statuses = [c.relationship_status for c in result.claim_evidence_comparisons if c.context_item_id in item_ids]
    if not statuses:
        return None
    # DIRECT_SUPPORT_CANDIDATE is the one outcome a distractor must never reach --
    # prioritize surfacing it if present, otherwise report the first observed status.
    for status in statuses:
        if status == ClaimSupportCandidateStatus.DIRECT_SUPPORT_CANDIDATE:
            return status
    return statuses[0]


def _check_no_real_source_provenance(fixture_dir: Path, report: ValidationReport) -> None:
    forbidden_keys = {"source_url", "publisher", "access_date", "license"}
    for path in sorted(fixture_dir.rglob("*.json")):
        try:
            data = json.loads(path.read_text())
        except (json.JSONDecodeError, UnicodeDecodeError):
            continue
        if not isinstance(data, dict):
            continue
        found = forbidden_keys & set(data.keys())
        if found:
            report.add(
                "no_real_source_provenance",
                f"{path.relative_to(fixture_dir)} carries real-source-provenance-style key(s) "
                f"{sorted(found)} -- this fixture is fictional and must never claim an external source.",
            )


def _check_no_registry_vocabulary_collision(fixture_dir: Path, report: ValidationReport) -> None:
    collision_keys = {"epistemic_status", "evidence_grade", "activation_policy"}
    for path in sorted((fixture_dir / "expected").glob("*.expected.json")):
        data = json.loads(path.read_text())
        found = collision_keys & set(data.keys())
        if found:
            report.add(
                "no_registry_vocabulary_collision",
                f"{path.name} sets key(s) {sorted(found)}, which name real registry/EpistemicStatus/"
                "ActivationPolicy vocabulary -- a fixture expectation file must never appear to set one.",
            )


def _check_perturbation_provenance(expected: dict, case_id: str, report: ValidationReport) -> None:
    if not expected.get("controlled_perturbation"):
        return
    required = {
        "source_supported_answer",
        "perturbed_answer",
        "perturbation_type",
        "changed_claim_component",
        "expected_claim_linking_status",
        "expected_reviewer_action",
    }
    missing = required - set(expected.keys())
    if missing:
        report.add(
            "perturbation_provenance_complete",
            f"controlled_perturbation=true but missing required field(s): {sorted(missing)}.",
            case_id=case_id,
        )


def _check_cross_reference_expectation(
    result, corpus_index, expected: dict, case_id: str, report: ValidationReport
) -> None:
    cross_ref = expected.get("expected_cross_reference")
    if not cross_ref:
        return
    marker_text = cross_ref.get("marker_text")
    found = False
    for claim in result.trace.answer_claims:
        for marker in detect_cross_reference_markers(claim, corpus_index, result.trace):
            if marker.marker_text != marker_text:
                continue
            found = True
            expected_state = cross_ref.get("expected_coarse_target_state")
            if expected_state and marker.target_state.value != expected_state:
                report.add(
                    "cross_reference_expectation",
                    f"marker {marker_text!r}: expected coarse target state {expected_state!r}, "
                    f"observed {marker.target_state.value!r}.",
                    case_id=case_id,
                )
            for target in marker.targets:
                expected_granularity = cross_ref.get("expected_resolution_granularity")
                if expected_granularity and target.resolution_granularity.value != expected_granularity:
                    report.add(
                        "cross_reference_expectation",
                        f"marker {marker_text!r} target {target.target_identifier!r}: expected "
                        f"resolution_granularity {expected_granularity!r}, observed "
                        f"{target.resolution_granularity.value!r}.",
                        case_id=case_id,
                    )
                expected_exactness = cross_ref.get("expected_exact_target_status")
                if expected_exactness and target.exact_target_status.value != expected_exactness:
                    report.add(
                        "cross_reference_expectation",
                        f"marker {marker_text!r} target {target.target_identifier!r}: expected "
                        f"exact_target_status {expected_exactness!r}, observed "
                        f"{target.exact_target_status.value!r}.",
                        case_id=case_id,
                    )
    if not found:
        report.add(
            "cross_reference_expectation",
            f"expected_cross_reference names marker {marker_text!r}, but no such marker was detected "
            "on any answer claim for this case.",
            case_id=case_id,
        )


def _run_and_check_case(
    case: SmokeTestCase, manifests: dict, expected_dir: Path, report: ValidationReport
) -> None:
    manifest = manifests[case.pipeline_manifest_id]
    corpus_text = resolve_corpus(case.corpus)
    top_k = manifest.retrieval_manifest.candidate_depth or 5
    token_budget = manifest.packing_manifest.evidence_budget_tokens or 300
    result = import_answer(
        case.query,
        case.answer,
        corpus=corpus_text,
        corpus_id=case.corpus.corpus_id,
        manifest=manifest,
        top_k=top_k,
        token_budget=token_budget,
    )

    if result.llm_extractions:
        report.add(
            "no_llm_baseline",
            f"llm_extractions is non-empty ({len(result.llm_extractions)}) -- the default fixture "
            "execution must invoke zero LLM calls.",
            case_id=case.case_id,
        )

    expected = _load_expected(expected_dir, case.case_id)
    if expected is None:
        report.add("expected_file_present", "no expected/<case_id>.expected.json found.", case_id=case.case_id)
        return

    _check_perturbation_provenance(expected, case.case_id, report)

    for segment_id in expected.get("distractor_locations", []):
        status = _relationship_for_segment(result, segment_id)
        if status == ClaimSupportCandidateStatus.DIRECT_SUPPORT_CANDIDATE:
            report.add(
                "distractor_does_not_satisfy_claim",
                f"distractor segment {segment_id!r} reached direct_support_candidate -- a distractor "
                "must never accidentally satisfy the claim it is designed to fail to support.",
                case_id=case.case_id,
            )

    corpus_index = index_corpus(corpus_text, case.corpus.corpus_id)
    _check_cross_reference_expectation(result, corpus_index, expected, case.case_id, report)


def validate_asteria_fixture(fixture_dir: Path) -> ValidationReport:
    """Run every executable case's fixture-integrity checks. `fixture_dir` is the
    `data/fixtures/asteria_manual` directory.
    """

    report = ValidationReport()

    cases_path = fixture_dir / "cases" / "cases.json"
    manifests_path = fixture_dir / "manifests.json"
    expected_dir = fixture_dir / "expected"

    case_file = SmokeTestCaseFile.model_validate(json.loads(cases_path.read_text()))
    manifests = load_manifests(manifests_path)
    report.case_count = len(case_file.cases)

    seen_case_ids: set[str] = set()
    for case in case_file.cases:
        if case.case_id in seen_case_ids:
            report.add("unique_case_ids", f"duplicate case_id {case.case_id!r}.", case_id=case.case_id)
        seen_case_ids.add(case.case_id)

        if case.pipeline_manifest_id not in manifests:
            report.add(
                "manifest_reference_resolves",
                f"pipeline_manifest_id {case.pipeline_manifest_id!r} not found in manifests.json.",
                case_id=case.case_id,
            )
            continue
        if case.pipeline_manifest_id in _NON_EXECUTABLE_MANIFEST_IDS:
            continue  # representable-but-not-executable -- schema validation only

        _run_and_check_case(case, manifests, expected_dir, report)

    _check_no_real_source_provenance(fixture_dir, report)
    _check_no_registry_vocabulary_collision(fixture_dir, report)

    return report
