from __future__ import annotations

from fastapi import APIRouter, HTTPException

from wittgenstein.registry.dossier import render_dossier
from wittgenstein.services.registry_service import get_registry

router = APIRouter(prefix="/registry", tags=["registry"])


@router.get("/mechanisms")
def list_mechanisms() -> list[dict]:
    registry = get_registry()
    return [m.model_dump(mode="json") for m in registry.mechanisms.values()]


@router.get("/mechanisms/{mechanism_id}")
def get_mechanism(mechanism_id: str) -> dict:
    registry = get_registry()
    try:
        return registry.mechanism(mechanism_id).model_dump(mode="json")
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/mechanisms/{mechanism_id}/dossier")
def get_dossier(mechanism_id: str) -> dict:
    registry = get_registry()
    try:
        markdown = render_dossier(registry, mechanism_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"mechanism_id": mechanism_id, "markdown": markdown}
