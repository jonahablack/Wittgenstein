"""The real-corpus diagnostic onboarding templates --
docs/real-corpus-diagnostic-runbook.md, docs/real-corpus-case-authoring-guide.md.
These tests check template/documentation validity only; they never alter diagnostic
behavior (review/evidence_set.py, review/cross_reference_diagnostics.py,
review/conflict_diagnostics.py, evidence_set_diagnostics/ are all untouched by this
milestone).
"""

from __future__ import annotations

import json
import re
import subprocess
from datetime import UTC, datetime
from pathlib import Path

import yaml
from wittgenstein.core.enums import (
    ConflictQualityDiagnosticLabel,
    CrossReferenceClosureDiagnosticLabel,
    EvidenceSetSizingDiagnosticLabel,
    ExtractionQualityDiagnosticLabel,
    ReviewerWorkflowDiagnosticLabel,
)
from wittgenstein.schemas.manifest import PipelineManifest
from wittgenstein.schemas.smoke_test import CorpusReference, SmokeTestCase

_REPO_ROOT = Path(__file__).resolve().parents[2]
_DIAG_DIR = _REPO_ROOT / "data/examples/evidence_set_diagnostics"
_CASE_TEMPLATE_PATH = _DIAG_DIR / "case-template.json"
_MANIFEST_TEMPLATE_PATH = _DIAG_DIR / "manifest-template.yaml"
_ANNOTATION_GUIDE_PATH = _DIAG_DIR / "annotation-guide.md"
_RUNBOOK_PATH = _REPO_ROOT / "docs/real-corpus-diagnostic-runbook.md"
_CASE_GUIDE_PATH = _REPO_ROOT / "docs/real-corpus-case-authoring-guide.md"

_REQUIRED_WORKSHEET_FIELDS = {
    "case_id",
    "corpus_id",
    "document_id",
    "document_version",
    "source_title",
    "source_url",
    "license_or_public_access_basis",
    "source_access_date",
    "source_hash",
    "local_source_path",
    "query",
    "user_stated_constraints",
    "unresolved_intent_fields",
    "answer",
    "answer_origin",
    "manifest_id",
    "expected_evidence_locations",
    "expected_structure_tags",
    "known_limitations",
    "annotation_status",
}

#: Source-provenance fields specifically -- docs/real-corpus-diagnostic-runbook.md
#: step 2 ("Record source provenance").
_PROVENANCE_FIELDS = {
    "source_title",
    "source_url",
    "license_or_public_access_basis",
    "source_access_date",
    "source_hash",
    "local_source_path",
}


# --- Template validity ------------------------------------------------------------


def test_case_template_is_valid_json_with_every_required_field() -> None:
    data = json.loads(_CASE_TEMPLATE_PATH.read_text())
    assert isinstance(data, dict)
    assert _REQUIRED_WORKSHEET_FIELDS.issubset(data.keys())


def test_manifest_template_is_valid_yaml() -> None:
    data = yaml.safe_load(_MANIFEST_TEMPLATE_PATH.read_text())
    assert isinstance(data, dict)
    for key in ("manifest_id", "system_name", "corpus_manifest", "ingestion_manifest", "packing_manifest"):
        assert key in data


def test_manifest_template_validates_as_pipeline_manifest_once_filled_in() -> None:
    """The template's placeholders must be real, fillable `PipelineManifest` fields --
    filling them with realistic values must produce a valid manifest, proving the
    template isn't documentation drift relative to the actual schema.
    """

    data = yaml.safe_load(_MANIFEST_TEMPLATE_PATH.read_text())
    data["manifest_id"] = "test-real-corpus-manifest"
    data["system_name"] = "test-diagnostic-pass"
    data["created_at"] = datetime.now(UTC).isoformat()
    data["corpus_manifest"]["corpus_id"] = "test-corpus"
    data["corpus_manifest"]["source_type"] = "plain_text"
    data["corpus_manifest"]["domain"] = "test_domain"

    manifest = PipelineManifest.model_validate(data)
    assert manifest.manifest_id == "test-real-corpus-manifest"
    assert "generation_manifest.generator_family" in manifest.missing_information


def test_case_template_worksheet_maps_onto_a_valid_smoke_test_case() -> None:
    """Applies the exact mapping documented in
    docs/real-corpus-case-authoring-guide.md (test-local conversion only, never
    shipped as pipeline code -- this milestone adds no new pipeline functionality) to
    confirm the documented mapping actually produces a valid `SmokeTestCase`.
    """

    filled = {
        "case_id": "real-001-eligibility-threshold",
        "corpus_id": "my-real-corpus",
        "document_id": "handbook",
        "document_version": "Rev. 3",
        "source_title": "Example Public Standards Document",
        "source_url": "https://example.org/standards.pdf",
        "license_or_public_access_basis": "CC-BY-4.0",
        "source_access_date": "2026-01-15",
        "source_hash": "0" * 64,
        "local_source_path": "local_corpora/my-real-corpus/handbook.txt",
        "query": "What is the eligibility threshold?",
        "user_stated_constraints": {"jurisdiction": "example"},
        "unresolved_intent_fields": ["effective_date"],
        "answer": "The threshold is 95%.",
        "answer_origin": "document_verbatim",
        "manifest_id": "my-real-corpus-manifest",
        "expected_evidence_locations": ["Handbook > Section 3"],
        "expected_structure_tags": ["structured_document", "temporal_or_version_information"],
        "known_limitations": "Re-typed excerpt, not the original PDF layout.",
        "annotation_status": "draft",
    }

    corpus = CorpusReference(
        corpus_id=filled["corpus_id"],
        source_type="local_path_excluded_from_git",
        local_path=filled["local_source_path"],
        document_hashes={filled["document_id"]: filled["source_hash"]},
        source_metadata={
            "source_title": filled["source_title"],
            "source_url": filled["source_url"],
            "license_or_public_access_basis": filled["license_or_public_access_basis"],
            "source_access_date": filled["source_access_date"],
        },
    )
    case = SmokeTestCase(
        case_id=filled["case_id"],
        corpus=corpus,
        document_version=filled["document_version"],
        query=filled["query"],
        query_constraints=filled["user_stated_constraints"],
        user_intent_notes=f"Unresolved intent fields: {', '.join(filled['unresolved_intent_fields'])}.",
        answer=filled["answer"],
        answer_source_method=filled["answer_origin"],
        pipeline_manifest_id=filled["manifest_id"],
        expected_evidence_locations=filled["expected_evidence_locations"],
        pilot_coverage_labels=filled["expected_structure_tags"],
        reviewer_notes=f"Known limitations: {filled['known_limitations']}",
        provenance_status="user_provided_license_confirmed",
    )
    assert case.corpus.document_hashes["handbook"] == "0" * 64
    assert case.corpus.source_metadata["license_or_public_access_basis"] == "CC-BY-4.0"


# --- Local corpus directory remains gitignored --------------------------------------


def test_local_corpora_directory_remains_gitignored() -> None:
    result = subprocess.run(
        ["git", "check-ignore", "-q", str(_DIAG_DIR / "local_corpora" / "any-real-document.txt")],
        cwd=_REPO_ROOT,
    )
    assert result.returncode == 0  # 0 means git-ignore matched -- excluded


def test_local_corpora_readme_is_not_gitignored() -> None:
    """The directory's own usage instructions (no source material) must still be
    trackable, or this deliverable file could never actually be committed.
    """

    result = subprocess.run(
        ["git", "check-ignore", "-q", str(_DIAG_DIR / "local_corpora" / "README.md")],
        cwd=_REPO_ROOT,
    )
    assert result.returncode == 1  # 1 means NOT ignored -- trackable


# --- Source provenance / controlled-perturbation provenance required ----------------


def test_case_template_requires_every_source_provenance_field() -> None:
    data = json.loads(_CASE_TEMPLATE_PATH.read_text())
    assert _PROVENANCE_FIELDS.issubset(data.keys())
    # Every provenance field starts out as an explicit placeholder or a documented
    # null -- never a silently plausible-looking fake value.
    for field_name in ("source_title", "license_or_public_access_basis", "source_access_date", "source_hash"):
        assert isinstance(data[field_name], str) and data[field_name].startswith("<REPLACE")


def test_case_authoring_guide_documents_every_provenance_field_mapping() -> None:
    guide_text = _CASE_GUIDE_PATH.read_text()
    for field_name in _PROVENANCE_FIELDS:
        assert f"`{field_name}`" in guide_text, f"{field_name} not documented in the case-authoring guide"


def test_case_template_and_guide_require_labeling_controlled_perturbations() -> None:
    template_text = _CASE_TEMPLATE_PATH.read_text()
    guide_text = _CASE_GUIDE_PATH.read_text()
    assert "controlled_perturbation_unsupported" in template_text
    assert "controlled_perturbation_contradicted" in template_text
    assert "controlled perturbation" in guide_text.lower()
    assert "fabricated" in guide_text.lower()


# --- Annotation templates accept only valid labels -----------------------------------


def _label_names_in_markdown_table(markdown_text: str, section_header: str) -> set[str]:
    """Extracts every `backtick_label` appearing in the first markdown table after
    `section_header`, stopping at the next `## ` heading.
    """

    start = markdown_text.index(section_header)
    next_header = markdown_text.find("\n## ", start + 1)
    section = markdown_text[start : next_header if next_header != -1 else len(markdown_text)]
    return set(re.findall(r"\|\s*`([a-z0-9_]+)`\s*\|", section))


def test_annotation_guide_defines_exactly_the_extraction_quality_labels() -> None:
    guide_text = _ANNOTATION_GUIDE_PATH.read_text()
    documented = _label_names_in_markdown_table(guide_text, "## A. Extraction quality")
    expected = {label.value for label in ExtractionQualityDiagnosticLabel}
    assert documented == expected


def test_annotation_guide_defines_exactly_the_conflict_quality_labels() -> None:
    guide_text = _ANNOTATION_GUIDE_PATH.read_text()
    documented = _label_names_in_markdown_table(guide_text, "## B. Conflict quality")
    expected = {label.value for label in ConflictQualityDiagnosticLabel}
    assert documented == expected


def test_annotation_guide_defines_exactly_the_cross_reference_closure_labels() -> None:
    guide_text = _ANNOTATION_GUIDE_PATH.read_text()
    documented = _label_names_in_markdown_table(guide_text, "## C. Cross-reference and definition closure")
    expected = {label.value for label in CrossReferenceClosureDiagnosticLabel}
    assert documented == expected


def test_annotation_guide_defines_exactly_the_evidence_set_sizing_labels() -> None:
    guide_text = _ANNOTATION_GUIDE_PATH.read_text()
    documented = _label_names_in_markdown_table(guide_text, "## D. Evidence-set sizing")
    expected = {label.value for label in EvidenceSetSizingDiagnosticLabel}
    assert documented == expected


def test_annotation_guide_defines_exactly_the_reviewer_workflow_labels() -> None:
    guide_text = _ANNOTATION_GUIDE_PATH.read_text()
    documented = _label_names_in_markdown_table(guide_text, "## E. Reviewer/workflow value")
    expected = {label.value for label in ReviewerWorkflowDiagnosticLabel}
    assert documented == expected


# --- No external source material embedded in fixtures --------------------------------


def test_case_template_contains_only_placeholder_content() -> None:
    data = json.loads(_CASE_TEMPLATE_PATH.read_text())
    for field_name in ("query", "answer", "source_title", "case_id"):
        assert str(data[field_name]).startswith("<REPLACE"), field_name
    # No field is suspiciously long (a real document excerpt accidentally pasted in) --
    # except the worksheet's own `_comment`, which is instructional text, not case data.
    for key, value in data.items():
        if key != "_comment" and isinstance(value, str):
            assert len(value) < 300, "case-template.json should contain no long embedded text"


def test_manifest_template_contains_no_embedded_document_text() -> None:
    text = _MANIFEST_TEMPLATE_PATH.read_text()
    # A manifest describes pipeline configuration, never document content -- no line
    # should run long enough to plausibly be a pasted excerpt.
    for line in text.splitlines():
        assert len(line) < 200


# --- Documentation command examples match the implemented CLI ------------------------


def test_runbook_cli_commands_reference_real_commands() -> None:
    runbook_text = _RUNBOOK_PATH.read_text()
    for command in (
        "wittgenstein evidence-set diagnose",
        "wittgenstein evidence-set report",
        "wittgenstein manifest validate",
    ):
        assert command in runbook_text


def test_evidence_set_diagnose_help_matches_runbook_flags() -> None:
    result = subprocess.run(
        ["uv", "run", "wittgenstein", "evidence-set", "diagnose", "--help"],
        cwd=_REPO_ROOT,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert "--cases" in result.stdout
    assert "--output-dir" in result.stdout
    assert "--diagnostic-max-set-size" in result.stdout


def test_manifest_template_validate_command_succeeds(tmp_path: Path) -> None:
    """Runs the runbook's exact step-4 validate command against a filled-in copy of
    the template.
    """

    data = yaml.safe_load(_MANIFEST_TEMPLATE_PATH.read_text())
    data["manifest_id"] = "test-real-corpus-manifest"
    data["system_name"] = "test-diagnostic-pass"
    data["created_at"] = datetime.now(UTC).isoformat()
    data["corpus_manifest"]["corpus_id"] = "test-corpus"
    data["corpus_manifest"]["source_type"] = "plain_text"
    data["corpus_manifest"]["domain"] = "test_domain"
    filled_path = tmp_path / "manifest.yaml"
    filled_path.write_text(yaml.safe_dump(data))

    result = subprocess.run(
        ["uv", "run", "wittgenstein", "manifest", "validate", str(filled_path)],
        cwd=_REPO_ROOT,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
