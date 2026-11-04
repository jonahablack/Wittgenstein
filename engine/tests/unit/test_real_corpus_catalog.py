"""The three real-corpus onboarding slices --
docs/corpus-selection-rationale.md, data/examples/evidence_set_diagnostics/corpus-catalog.yaml.
These tests check catalog/documentation validity only; no source/pipeline behavior is
touched by this milestone.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

import yaml

_REPO_ROOT = Path(__file__).resolve().parents[2]
_DIAG_DIR = _REPO_ROOT / "data/examples/evidence_set_diagnostics"
_CATALOG_PATH = _DIAG_DIR / "corpus-catalog.yaml"

_REQUIRED_CATALOG_FIELDS = {
    "corpus_id",
    "corpus_type",
    "domain",
    "official_source_urls",
    "source_format_options",
    "version_or_effective_date",
    "public_access_or_license_note",
    "initial_slice",
    "structural_features",
    "intended_failure_or_trace_conditions",
    "diagnostic_question_types",
    "local_storage_path",
    "raw_content_committed",
    "source_provenance_required",
    "medical_or_legal_advice_warning",
    "status",
}

_EXPECTED_CORPUS_IDS = {"eu-ai-act-2024", "hipaa-privacy-rule", "ada-standards-2026"}

#: Every required §7 metadata concept from docs/real-corpus-diagnostic-runbook.md
#: step 2, checked against each corpus README's own "Required local metadata" section.
_REQUIRED_README_METADATA_CONCEPTS = (
    "source title",
    "source url",
    "access date",
    "publisher",
    "version",
    "local file name",
    "sha-256",
    "license",
    "extraction",
    "section",
)


def _load_catalog() -> list[dict]:
    data = yaml.safe_load(_CATALOG_PATH.read_text())
    return data["corpora"]


def _corpus_readme_paths() -> dict[str, Path]:
    return {corpus_id: _DIAG_DIR / corpus_id / "README.md" for corpus_id in _EXPECTED_CORPUS_IDS}


def _normalized_whitespace(text: str) -> str:
    """Collapses markdown line-wrapping so a multi-word phrase check isn't broken by
    an incidental line break in the middle of a sentence.
    """

    return re.sub(r"\s+", " ", text)


# --- Corpus-catalog validity ---------------------------------------------------------


def test_catalog_lists_exactly_the_three_expected_corpora() -> None:
    entries = _load_catalog()
    assert {entry["corpus_id"] for entry in entries} == _EXPECTED_CORPUS_IDS


def test_every_catalog_entry_has_every_required_field() -> None:
    for entry in _load_catalog():
        missing = _REQUIRED_CATALOG_FIELDS - entry.keys()
        assert not missing, f"{entry.get('corpus_id')} missing fields: {missing}"


def test_every_catalog_entry_has_safe_default_flags() -> None:
    for entry in _load_catalog():
        assert entry["raw_content_committed"] is False, entry["corpus_id"]
        assert entry["source_provenance_required"] is True, entry["corpus_id"]
        assert entry["status"] == "onboarding_required", entry["corpus_id"]


def test_every_catalog_entry_has_at_least_one_official_source_url() -> None:
    for entry in _load_catalog():
        urls = entry["official_source_urls"]
        assert isinstance(urls, list) and urls
        for url in urls:
            assert url.startswith("https://"), entry["corpus_id"]


def test_every_catalog_entry_local_storage_path_matches_local_corpora_convention() -> None:
    for entry in _load_catalog():
        expected = f"data/examples/evidence_set_diagnostics/local_corpora/{entry['corpus_id']}/"
        assert entry["local_storage_path"] == expected


def test_every_catalog_entry_carries_a_medical_or_legal_advice_warning() -> None:
    for entry in _load_catalog():
        warning = entry["medical_or_legal_advice_warning"].lower()
        assert "software" in warning or "diagnostic" in warning
        assert "advice" in warning


# --- Required corpus README fields ----------------------------------------------------


def test_every_corpus_has_a_readme() -> None:
    for corpus_id, path in _corpus_readme_paths().items():
        assert path.exists(), corpus_id


def test_every_corpus_readme_has_all_eleven_required_sections() -> None:
    required_headers = [
        "## 1. Corpus ID",
        "## 2. Purpose in the diagnostic matrix",
        "## 3. Official source URL(s)",
        "## 4. Access date placeholder",
        "## 5. License/public-access or source-use note",
        "## 6. Required local directory",
        "## 7. Required local metadata",
        "## 8. Initial slice specification",
        "## 9. Recommended diagnostic-case categories",
        "## 10. Warning",
        "## 11. Raw material statement",
    ]
    for corpus_id, path in _corpus_readme_paths().items():
        text = path.read_text()
        for header in required_headers:
            assert header in text, f"{corpus_id} missing section: {header}"


def test_every_corpus_readme_documents_all_required_metadata_concepts() -> None:
    for corpus_id, path in _corpus_readme_paths().items():
        section_text = path.read_text().lower()
        for concept in _REQUIRED_README_METADATA_CONCEPTS:
            assert concept in section_text, f"{corpus_id} README missing metadata concept: {concept}"


# --- Research-only / non-advice warning present ---------------------------------------


def test_every_corpus_readme_states_research_only_non_advice_warning() -> None:
    for corpus_id, path in _corpus_readme_paths().items():
        text = path.read_text().lower()
        assert "software evaluation only" in text, corpus_id
        assert "advice" in text, corpus_id


def test_ada_readme_specifically_warns_against_medical_advice() -> None:
    text = (_DIAG_DIR / "ada-standards-2026" / "README.md").read_text().lower()
    assert "medical advice" in text
    assert "clinical recommendation" in text


def test_eu_ai_act_and_hipaa_readmes_specifically_warn_against_legal_advice() -> None:
    for corpus_id in ("eu-ai-act-2024", "hipaa-privacy-rule"):
        text = _normalized_whitespace((_DIAG_DIR / corpus_id / "README.md").read_text().lower())
        assert "legal advice" in text


# --- Source provenance fields required -------------------------------------------------


def test_every_corpus_readme_requires_source_hash() -> None:
    for corpus_id, path in _corpus_readme_paths().items():
        text = path.read_text()
        assert "SHA-256" in text, corpus_id
        assert "content_hash" in text, corpus_id  # points at the exact runbook command


def test_every_corpus_readme_requires_local_directory_under_local_corpora() -> None:
    for corpus_id, path in _corpus_readme_paths().items():
        text = path.read_text()
        assert f"local_corpora/{corpus_id}/" in text


# --- Local storage paths remain gitignored ---------------------------------------------


def test_every_corpus_local_storage_path_is_gitignored() -> None:
    for entry in _load_catalog():
        result = subprocess.run(
            ["git", "check-ignore", "-q", str(_REPO_ROOT / entry["local_storage_path"] / "any-file.txt")],
            cwd=_REPO_ROOT,
        )
        assert result.returncode == 0, f"{entry['corpus_id']} local_storage_path is not gitignored"


# --- No raw source material present in repository fixtures -----------------------------


def test_no_local_corpora_subdirectory_is_tracked_by_git() -> None:
    """A local corpus subdirectory may legitimately exist on disk once someone runs a
    real diagnostic pilot (docs/eu-ai-act-pilot-run-summary.md) -- the actual safety
    invariant is that git never tracks it, not that it never exists. `git ls-files`
    lists only files git already knows about; a gitignored, never-`git add`-ed
    directory reports nothing, which is what this asserts.
    """

    for corpus_id in _EXPECTED_CORPUS_IDS:
        result = subprocess.run(
            ["git", "ls-files", "--error-unmatch", f"local_corpora/{corpus_id}"],
            cwd=_DIAG_DIR,
            capture_output=True,
        )
        assert result.returncode != 0, f"{corpus_id} has tracked files under local_corpora/"


def test_new_onboarding_files_contain_no_long_embedded_text_blocks() -> None:
    """A crude but effective proxy for 'no raw source material was pasted in': no
    line in the new onboarding docs/catalog is implausibly long for hand-written
    guidance prose.
    """

    paths = [
        _CATALOG_PATH,
        _REPO_ROOT / "docs/corpus-selection-rationale.md",
        _DIAG_DIR / "case-sets/README.md",
        *(_DIAG_DIR / corpus_id / "README.md" for corpus_id in _EXPECTED_CORPUS_IDS),
    ]
    for path in paths:
        for line in path.read_text().splitlines():
            assert len(line) < 500, f"{path}: suspiciously long line ({len(line)} chars)"


# --- Suggested case sets do not fabricate document claims -------------------------------


def test_case_sets_readme_never_asserts_a_concrete_document_claim() -> None:
    text = (_DIAG_DIR / "case-sets/README.md").read_text()
    # No sentence should read like "Article 6 requires ..." / "Section 164.508 states
    # ..." -- a fabricated legal/clinical claim presented as fact. Only structural
    # *shapes* and explicit warnings against fabrication are allowed.
    fabricated_claim_pattern = re.compile(
        r"(Article\s+\d+|§\s?\d+\.\d+|Section\s+\d+)\s+(requires|states|provides|mandates)",
        re.IGNORECASE,
    )
    assert not fabricated_claim_pattern.search(_normalized_whitespace(text))
    assert "never a plausible-sounding legal or clinical claim invented" in _normalized_whitespace(text)


def test_case_sets_readme_states_case_shapes_are_not_answers() -> None:
    text = (_DIAG_DIR / "case-sets/README.md").read_text().lower()
    assert "shapes" in text
    assert "never fabricated" in text or "not pre-written answers" in text
