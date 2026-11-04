"""Loads the small `{manifest_id: PipelineManifest}` registry a cases file's
`pipeline_manifest_id` fields are looked up against -- one PipelineManifest.model_validate
call per entry is the entirety of "validate the manifest" (step 2 of the smoke-test
CLI command), matching how `api/routes/manifests.py::validate_manifest` already treats
manifest validation as nothing more than successful schema construction.
"""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import ValidationError

from wittgenstein.schemas.manifest import PipelineManifest


class SmokeTestManifestError(ValueError):
    """Raised for a missing manifests file, an invalid manifest, or an unknown
    pipeline_manifest_id reference from a case.
    """


def load_manifests(path: Path) -> dict[str, PipelineManifest]:
    if not path.exists():
        raise SmokeTestManifestError(f"Manifests registry file does not exist: {path}")

    raw = json.loads(path.read_text())
    if not isinstance(raw, dict):
        raise SmokeTestManifestError(f"{path} must be a JSON object of {{manifest_id: PipelineManifest fields}}.")

    manifests: dict[str, PipelineManifest] = {}
    for manifest_id, payload in raw.items():
        try:
            manifest = PipelineManifest.model_validate(payload)
        except ValidationError as exc:
            raise SmokeTestManifestError(f"Manifest {manifest_id!r} in {path} failed validation: {exc}") from exc
        if manifest.manifest_id != manifest_id:
            raise SmokeTestManifestError(
                f"Manifest registry key {manifest_id!r} does not match its own manifest_id "
                f"{manifest.manifest_id!r} in {path}."
            )
        manifests[manifest_id] = manifest
    return manifests
