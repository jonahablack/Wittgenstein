from __future__ import annotations

from fastapi import APIRouter
from pydantic import ValidationError

from wittgenstein.schemas.manifest import PipelineManifest

router = APIRouter(prefix="/manifests", tags=["manifests"])


@router.post("/validate")
def validate_manifest(payload: dict) -> dict:
    try:
        manifest = PipelineManifest.model_validate(payload)
    except ValidationError as exc:
        return {"valid": False, "errors": exc.errors()}
    return {"valid": True, "manifest_id": manifest.manifest_id}
