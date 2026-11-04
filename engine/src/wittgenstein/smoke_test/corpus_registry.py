"""Resolves a `CorpusReference` to actual document text -- the one place a
git-excluded local path is ever read (docs/real-trace-smoke-test-plan.md §2). Never
returns bundled-fixture text for a `local_path_excluded_from_git` reference or vice
versa; a hash mismatch against `CorpusReference.document_hashes` raises rather than
silently proceeding on drifted content.
"""

from __future__ import annotations

import json
from pathlib import Path

from wittgenstein.ingestion.content_hash import content_hash
from wittgenstein.schemas.smoke_test import (
    SOURCE_TYPE_BUNDLED_SYNTHETIC_FIXTURE,
    SOURCE_TYPE_LOCAL_PATH_EXCLUDED_FROM_GIT,
    CorpusReference,
)

_TEXT_SUFFIXES = {".md", ".txt"}


class SmokeTestCorpusError(ValueError):
    """Raised when a CorpusReference cannot be resolved -- e.g. an unknown bundled
    fixture id, a missing local path, or a document-hash mismatch. Never silently
    substituted with an empty or partial corpus.
    """


def _bundled_fixture(corpus_id: str) -> dict[str, str]:
    if corpus_id == "widget-certification-demo":
        from wittgenstein.demo.widget_corpus import documents

        return documents()
    if corpus_id == "asteria-manual":
        from wittgenstein.demo.asteria_corpus import documents

        return documents()
    raise SmokeTestCorpusError(
        f"Unknown bundled_synthetic_fixture corpus_id: {corpus_id!r}. Only "
        "'widget-certification-demo' and 'asteria-manual' are registered -- add a new bundled fixture "
        "module before referencing a different id."
    )


def _load_local_path(local_path: str) -> dict[str, str]:
    path = Path(local_path)
    if not path.exists():
        raise SmokeTestCorpusError(
            f"Local corpus path does not exist: {path}. This path is expected to be git-excluded "
            "(see .gitignore) and must be created locally before running the smoke test."
        )

    if path.is_file():
        if path.suffix != ".json":
            raise SmokeTestCorpusError(
                f"Local corpus file {path} is not .json -- a single-file corpus must be a "
                "{source_document_id: text} JSON object."
            )
        data = json.loads(path.read_text())
        if not isinstance(data, dict) or not all(isinstance(v, str) for v in data.values()):
            raise SmokeTestCorpusError(
                f"Local corpus file {path} must be a flat {{source_document_id: text}} object."
            )
        return data

    documents: dict[str, str] = {}
    for file_path in sorted(path.iterdir()):
        if file_path.suffix.lower() in _TEXT_SUFFIXES:
            documents[file_path.stem] = file_path.read_text()
    if not documents:
        raise SmokeTestCorpusError(
            f"Local corpus directory {path} contains no {sorted(_TEXT_SUFFIXES)} files -- nothing to ingest."
        )
    return documents


def resolve_corpus(ref: CorpusReference) -> dict[str, str]:
    if ref.source_type == SOURCE_TYPE_BUNDLED_SYNTHETIC_FIXTURE:
        documents = _bundled_fixture(ref.corpus_id)
    elif ref.source_type == SOURCE_TYPE_LOCAL_PATH_EXCLUDED_FROM_GIT:
        assert ref.local_path is not None  # guaranteed by CorpusReference's own validator
        documents = _load_local_path(ref.local_path)
    else:  # pragma: no cover -- CorpusReference's own validator already rejects this
        raise SmokeTestCorpusError(f"Unknown source_type: {ref.source_type!r}")

    for source_document_id, expected_hash in ref.document_hashes.items():
        actual_text = documents.get(source_document_id)
        if actual_text is None:
            raise SmokeTestCorpusError(
                f"CorpusReference {ref.corpus_id}: document_hashes references "
                f"{source_document_id!r}, which was not found in the resolved corpus."
            )
        actual_hash = content_hash(actual_text)
        if actual_hash != expected_hash:
            raise SmokeTestCorpusError(
                f"CorpusReference {ref.corpus_id}: document {source_document_id!r} content hash "
                f"{actual_hash} does not match recorded {expected_hash} -- the source document has drifted "
                "since this case was authored. Re-verify and update document_hashes deliberately, rather "
                "than silently proceeding on changed content."
            )

    return documents
