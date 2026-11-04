from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError
from wittgenstein.schemas.manifest import PipelineManifest, RetrievalManifest

NOW = datetime(2026, 9, 2, tzinfo=UTC)


def test_minimal_manifest_parses():
    manifest = PipelineManifest(manifest_id="M1", system_name="sys", system_version="0.1", created_at=NOW)
    assert manifest.retrieval_manifest.retriever_family is None


def test_unknown_fields_stay_none_not_defaulted():
    manifest = PipelineManifest(manifest_id="M1", system_name="sys", system_version="0.1", created_at=NOW)
    assert manifest.packing_manifest.context_window_tokens is None
    assert manifest.selection_manifest.max_selected_items is None
    assert manifest.reranking_manifest.reranking_enabled is None


def test_extra_fields_rejected():
    with pytest.raises(ValidationError):
        PipelineManifest(
            manifest_id="M1",
            system_name="sys",
            system_version="0.1",
            created_at=NOW,
            some_made_up_field="x",
        )


def test_extra_fields_rejected_in_section():
    with pytest.raises(ValidationError):
        RetrievalManifest(retriever_family="bm25", made_up_field=True)


def test_missing_information_field_defaults_empty_and_is_explicit():
    manifest = PipelineManifest(manifest_id="M1", system_name="sys", system_version="0.1", created_at=NOW)
    assert manifest.missing_information == []
    manifest2 = PipelineManifest(
        manifest_id="M1",
        system_name="sys",
        system_version="0.1",
        created_at=NOW,
        missing_information=["reranking_manifest.reranker_family"],
    )
    assert manifest2.missing_information == ["reranking_manifest.reranker_family"]
