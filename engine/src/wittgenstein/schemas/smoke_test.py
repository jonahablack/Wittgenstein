"""The real-trace smoke-test case format -- docs/real-trace-smoke-test-plan.md.

A `SmokeTestCase` never embeds document text. `CorpusReference` stores only a corpus
id, a source-type tag, an optional git-excluded local path, document hashes, and
source metadata -- never raw content -- so this schema itself enforces the "store only
identifiers/hashes/metadata/paths, never restricted material" rule at the type level,
not just by convention.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, model_validator

from wittgenstein.core.enums import PilotCoverageLabel, ProvenanceStatus

#: A case whose corpus is one of the small, fully-fictional, redistribution-safe
#: fixtures already bundled with this repository (e.g. `demo/widget_corpus.py`) --
#: resolved by code, never by reading a local path.
SOURCE_TYPE_BUNDLED_SYNTHETIC_FIXTURE = "bundled_synthetic_fixture"
#: A case whose corpus text lives only at a local filesystem path excluded from git
#: (see .gitignore, "data/examples/real_trace_smoke/local_corpora/") -- never
#: committed, never redistributed by this repository.
SOURCE_TYPE_LOCAL_PATH_EXCLUDED_FROM_GIT = "local_path_excluded_from_git"

_VALID_SOURCE_TYPES = {SOURCE_TYPE_BUNDLED_SYNTHETIC_FIXTURE, SOURCE_TYPE_LOCAL_PATH_EXCLUDED_FROM_GIT}


class CorpusReference(BaseModel):
    model_config = ConfigDict(extra="forbid")

    corpus_id: str
    source_type: str = Field(..., description=f"One of: {', '.join(sorted(_VALID_SOURCE_TYPES))}.")
    local_path: str | None = Field(
        default=None,
        description="Required (and only meaningful) when source_type=local_path_excluded_from_git. "
        "Never committed as document text -- this field holds a path, not content.",
    )
    document_hashes: dict[str, str] = Field(
        default_factory=dict,
        description="source_document_id -> sha256 of its text, recorded so drift in a "
        "git-excluded local document can be detected even though the text itself is never committed.",
    )
    source_metadata: dict[str, str] = Field(
        default_factory=dict,
        description="e.g. title, publisher, license, access_date -- metadata only, never raw text.",
    )

    @model_validator(mode="after")
    def _source_type_and_local_path_consistent(self) -> CorpusReference:
        if self.source_type not in _VALID_SOURCE_TYPES:
            raise ValueError(f"CorpusReference {self.corpus_id}: unknown source_type {self.source_type!r}.")
        if self.source_type == SOURCE_TYPE_LOCAL_PATH_EXCLUDED_FROM_GIT and not self.local_path:
            raise ValueError(
                f"CorpusReference {self.corpus_id}: source_type=local_path_excluded_from_git requires local_path."
            )
        if self.source_type == SOURCE_TYPE_BUNDLED_SYNTHETIC_FIXTURE and self.local_path:
            raise ValueError(
                f"CorpusReference {self.corpus_id}: source_type=bundled_synthetic_fixture must not set local_path "
                "-- bundled fixtures are resolved by code, not by a filesystem path."
            )
        return self


class SmokeTestCase(BaseModel):
    """One real-trace smoke-test case. `expected_evidence_locations` is a researcher
    annotation used to diagnose retrieval/linking behavior -- never treated as
    universal factual ground truth (docs/real-trace-smoke-test-plan.md).
    """

    model_config = ConfigDict(extra="forbid")

    case_id: str
    corpus: CorpusReference
    document_version: str | None = None
    query: str
    query_constraints: dict[str, str] = Field(default_factory=dict)
    user_intent_notes: str | None = None
    answer: str
    answer_source_method: str = Field(
        ...,
        description='How the answer was obtained, e.g. "human_authored_for_pilot", '
        '"existing_production_trace", "manual_transcription_from_document".',
    )
    pipeline_manifest_id: str = Field(..., description="Looked up in the accompanying manifests registry.")
    expected_evidence_locations: list[str] = Field(
        default_factory=list,
        description="Researcher-annotated locations (e.g. 'Section 3 > Table 1') believed relevant -- a "
        "diagnostic aid for this smoke test, not a claim of universal factual ground truth.",
    )
    pilot_coverage_labels: list[PilotCoverageLabel] = Field(
        default_factory=list, description="Which required pilot-variation categories this case exercises."
    )
    reviewer_notes: str | None = None
    provenance_status: ProvenanceStatus


class SmokeTestCaseFile(BaseModel):
    """The top-level shape of a cases file (e.g. cases.example.json)."""

    model_config = ConfigDict(extra="forbid")

    cases: list[SmokeTestCase]
