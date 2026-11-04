"""Thin service wrapper around registry loading, used by both the CLI and the API so
neither has to know about YAML file layout directly.
"""

from __future__ import annotations

import os
from pathlib import Path

from wittgenstein.registry.loader import load_registry
from wittgenstein.registry.repository import Registry

DEFAULT_SEED_DIR = Path(__file__).resolve().parents[3] / "data" / "registry"


def default_seed_dir() -> Path:
    override = os.environ.get("WITTGENSTEIN_REGISTRY_SEED_DIR")
    return Path(override) if override else DEFAULT_SEED_DIR


def get_registry(seed_dir: Path | None = None) -> Registry:
    """Loads and validates the registry fresh each call.

    Deliberately not memoized at module scope: registry seed files are edited
    frequently during development, and a stale in-process cache silently serving old
    data would violate this project's no-silent-fallback convention. Callers that need
    caching (e.g. a long-lived API process) should cache at their own layer with an
    explicit invalidation story.
    """

    return load_registry(seed_dir or default_seed_dir())
