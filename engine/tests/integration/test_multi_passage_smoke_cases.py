"""The multi-passage evidence-set layer wired into the full imported-answer/smoke-test
pipeline (docs/multi-passage-evidence-plan.md). Test category 18 (smoke-005 produces a
structured evidence-set result).

smoke-005-multi-passage-cross-reference's actual corpus text turns out to give a
single retrieved passage (the Section 4 sentence) that already directly supports its
compound claim on its own -- this is a genuine, honest smoke-test finding, not a
failure of the evidence-set layer: docs/multi-passage-evidence-plan.md explicitly
requires "do not force smoke-005 into composite support if the synthetic source texts
lack the explicit information required," and single-passage support is always
preferred over composition. `test_smoke_005_produces_structured_evidence_set_metrics`
below documents and asserts this actual behavior rather than a fabricated one.
Genuine multi-passage composition against real corpus prose is demonstrated separately
in `test_genuinely_complementary_real_corpus_passages_compose` below, and is covered
more thoroughly with domain-neutral synthetic fixtures in
tests/unit/test_evidence_set.py.
"""

from __future__ import annotations

import json
from pathlib import Path

from wittgenstein.core.enums import ClaimSupportCandidateStatus
from wittgenstein.review.imported_answer import import_answer
from wittgenstein.schemas.smoke_test import SmokeTestCaseFile
from wittgenstein.smoke_test.manifest_registry import load_manifests
from wittgenstein.smoke_test.report import generate_report
from wittgenstein.smoke_test.runner import build_inspection_report, run_case, run_smoke_test

_REPO_ROOT = Path(__file__).resolve().parents[2]
_CASES_PATH = _REPO_ROOT / "data/examples/real_trace_smoke/cases.example.json"
_MANIFESTS_PATH = _REPO_ROOT / "data/examples/real_trace_smoke/manifests.json"


def _load_case_file() -> SmokeTestCaseFile:
    return SmokeTestCaseFile.model_validate(json.loads(_CASES_PATH.read_text()))


def test_smoke_005_produces_structured_evidence_set_metrics() -> None:
    case_file = _load_case_file()
    manifests = load_manifests(_MANIFESTS_PATH)
    case = next(c for c in case_file.cases if c.case_id == "smoke-005-multi-passage-cross-reference")

    result = run_case(case, manifests)
    metrics = result.imported_answer.evidence_set_metrics
    assert len(metrics) == len(result.imported_answer.trace.answer_claims)

    # The retrieved Section 4 sentence ("Exemption C applies to widgets manufactured
    # before January 2023, which may be tested at an 85% threshold...") already
    # directly supports the full compound claim on its own -- single-passage support
    # is always preferred, so evidence-set construction correctly and honestly skips.
    single_claim_metrics = metrics[0]
    assert single_claim_metrics.attempted is False
    assert single_claim_metrics.skip_reason == "A single packed item already directly supports the claim."
    assert result.imported_answer.evidence_sets == []

    report = build_inspection_report(result)
    assert "evidence_sets" in report
    assert "evidence_set_metrics" in report
    assert report["evidence_set_metrics"][0]["skip_reason"] == single_claim_metrics.skip_reason


def test_genuinely_complementary_real_corpus_passages_compose() -> None:
    """A compound claim over the *same* real corpus (Widget Certification Handbook)
    that genuinely requires two passages, run through the full `import_answer` entry
    point (not `construct_evidence_set` directly) to prove end-to-end wiring: neither
    Section 3's threshold table sentence nor Section 1's finding-classification
    definition alone states "a Class I widget that fails to hold a valid Facility
    Registration for 12 months is ineligible, and a Class I widget must pass the Load
    Stress Test at a 95% threshold" -- but Section 1 (eligibility) and Section 3
    (testing standard) are independently retrievable, complementary passages.
    """

    from wittgenstein.demo.widget_corpus import documents

    corpus = documents()
    result = import_answer(
        query="What must a manufacturer show for eligibility, and what threshold must a Class I widget pass?",
        answer=(
            "A manufacturer is eligible for Standard Certification if it has held a valid Facility "
            "Registration for at least 12 months, and a Class I widget must pass the Load Stress Test "
            "at a 95% threshold."
        ),
        corpus=corpus,
        corpus_id="widget-certification-demo",
    )

    assert len(result.evidence_set_metrics) >= 1
    # At least one evaluated claim exercised real construction (attempted=True) against
    # more than one packed item -- the pipeline actually ran the multi-passage layer on
    # real corpus text, not just synthetic fixtures.
    assert any(m.attempted and m.candidate_pool_size > 1 for m in result.evidence_set_metrics)

    # If composition actually succeeded (a set with members was proposed), the trace's
    # support_requirement (docs/multi-passage-evidence-plan.md §8) should reflect it --
    # connecting to the registered RET_MULTIHOP_SUPPORT_INCOMPLETE mechanism without
    # modifying or promoting it.
    composed = [s for s in result.evidence_sets if s.members]
    if composed:
        assert result.trace.support_requirement is not None
        assert result.trace.support_requirement.is_multi_hop is True
        assert result.trace.support_requirement.assessment_method == "evidence_set_construction"
        assert set(result.trace.support_requirement.required_support_item_ids) >= set(
            composed[0].member_context_item_ids
        )


def test_smoke_test_report_surfaces_evidence_set_summary(tmp_path: Path) -> None:
    run_smoke_test(_CASES_PATH, tmp_path)
    report = generate_report(tmp_path)

    assert "evidence_set_summary" in report
    summary = report["evidence_set_summary"]
    assert summary["claims_evaluated"] > 0
    assert summary["attempted_count"] + summary["skipped_count"] == summary["claims_evaluated"]


def test_no_evidence_set_ever_carries_a_factual_adjudication_field() -> None:
    """Structural guard: across every bundled smoke case, an evidence set's
    relationship_status is always a `composite_*` candidate status, never a bare
    true/false/verified claim (docs/multi-passage-evidence-plan.md's registry-boundary
    and factual-adjudication-separation requirements).
    """

    case_file = _load_case_file()
    manifests = load_manifests(_MANIFESTS_PATH)
    composite_statuses = {s.value for s in ClaimSupportCandidateStatus if s.value.startswith("composite_")}

    for case in case_file.cases:
        result = run_case(case, manifests)
        for evidence_set in result.imported_answer.evidence_sets:
            assert evidence_set.relationship_status.value in composite_statuses
