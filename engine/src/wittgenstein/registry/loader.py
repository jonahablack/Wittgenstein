"""Load the registry seed YAML files into validated Pydantic models.

Fails loudly (raises) on any structural or cross-record integrity problem rather than
skipping bad records -- per this project's fail-fast research-integrity convention.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError

from wittgenstein.registry.repository import Registry
from wittgenstein.registry.validator import RegistrySeedIntegrityError, validate_registry
from wittgenstein.schemas import (
    EvidenceRecord,
    FailureMechanism,
    ManifestGate,
    ReviewAction,
    TraceTrigger,
)

SEED_FILES = {
    "mechanisms": "failure_modes.seed.yaml",
    "evidence": "evidence_records.seed.yaml",
    "gates": "manifest_gates.seed.yaml",
    "triggers": "trace_triggers.seed.yaml",
    "review_actions": "review_actions.seed.yaml",
}


class RegistryLoadError(Exception):
    """Raised when a seed YAML file fails to parse into its schema."""


def _read_yaml_list(path: Path, key: str) -> list[dict[str, Any]]:
    if not path.exists():
        raise RegistryLoadError(f"Missing required seed file: {path}")
    raw = yaml.safe_load(path.read_text()) or {}
    items = raw.get(key)
    if items is None:
        raise RegistryLoadError(f"{path}: expected top-level key {key!r}")
    return items


def load_registry(seed_dir: Path) -> Registry:
    seed_dir = Path(seed_dir)
    registry = Registry()
    errors: list[str] = []

    for raw in _read_yaml_list(seed_dir / SEED_FILES["mechanisms"], "mechanisms"):
        try:
            m = FailureMechanism.model_validate(raw)
            registry.mechanisms[m.id] = m
        except ValidationError as exc:
            errors.append(f"failure_modes.seed.yaml, id={raw.get('id')}: {exc}")

    for raw in _read_yaml_list(seed_dir / SEED_FILES["evidence"], "evidence_records"):
        try:
            e = EvidenceRecord.model_validate(raw)
            registry.evidence[e.id] = e
        except ValidationError as exc:
            errors.append(f"evidence_records.seed.yaml, id={raw.get('id')}: {exc}")

    for raw in _read_yaml_list(seed_dir / SEED_FILES["gates"], "manifest_gates"):
        try:
            g = ManifestGate.model_validate(raw)
            registry.gates[g.id] = g
        except ValidationError as exc:
            errors.append(f"manifest_gates.seed.yaml, id={raw.get('id')}: {exc}")

    for raw in _read_yaml_list(seed_dir / SEED_FILES["triggers"], "trace_triggers"):
        try:
            t = TraceTrigger.model_validate(raw)
            registry.triggers[t.id] = t
        except ValidationError as exc:
            errors.append(f"trace_triggers.seed.yaml, id={raw.get('id')}: {exc}")

    for raw in _read_yaml_list(seed_dir / SEED_FILES["review_actions"], "review_actions"):
        try:
            r = ReviewAction.model_validate(raw)
            registry.review_actions[r.id] = r
        except ValidationError as exc:
            errors.append(f"review_actions.seed.yaml, id={raw.get('id')}: {exc}")

    if errors:
        raise RegistryLoadError(
            "Failed to parse " + str(len(errors)) + " registry seed record(s):\n" + "\n".join(errors)
        )

    validate_registry(registry)  # raises RegistrySeedIntegrityError on cross-record problems
    return registry


__all__ = ["load_registry", "RegistryLoadError", "RegistrySeedIntegrityError"]
