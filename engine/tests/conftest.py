from __future__ import annotations

import json
from pathlib import Path

import pytest
from wittgenstein.registry.loader import load_registry
from wittgenstein.registry.repository import Registry
from wittgenstein.schemas.manifest import PipelineManifest
from wittgenstein.schemas.trace import QueryTrace

REPO_ROOT = Path(__file__).resolve().parents[1]
SEED_DIR = REPO_ROOT / "data" / "registry"
EXAMPLES_DIR = REPO_ROOT / "data" / "examples"


@pytest.fixture(scope="session")
def registry() -> Registry:
    return load_registry(SEED_DIR)


def _load_manifest(name: str) -> PipelineManifest:
    return PipelineManifest.model_validate(json.loads((EXAMPLES_DIR / "manifests" / f"{name}.json").read_text()))


def _load_trace(name: str) -> QueryTrace:
    return QueryTrace.model_validate(json.loads((EXAMPLES_DIR / "traces" / f"{name}.json").read_text()))


@pytest.fixture
def example_pair():
    def _load(name: str) -> tuple[PipelineManifest, QueryTrace]:
        return _load_manifest(name), _load_trace(name)

    return _load
