"""Applicability assessment and risk-event derivation endpoints.

/risk-events/derive is the one endpoint the task's spec holds to the highest bar: it
must return only applicable/partially-applicable mechanisms by default, explain every
gate and unknown field, return allowed claim language, distinguish observed trace
condition from causal explanation, and never return a generic numerical
"hallucination probability" -- there is no such field anywhere in this module.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from wittgenstein.matching.eligibility import MECHANISM_EVALUATORS
from wittgenstein.schemas.manifest import PipelineManifest
from wittgenstein.schemas.trace import QueryTrace
from wittgenstein.services.applicability_service import assess_mechanism, derive_risk_events
from wittgenstein.services.registry_service import get_registry

router = APIRouter(tags=["applicability"])


class AssessRequest(BaseModel):
    manifest: dict
    trace: dict | None = None
    mechanism_id: str | None = None


class RiskEventsRequest(BaseModel):
    manifest: dict
    trace: dict
    include_non_applicable_for_audit: bool = False


@router.post("/applicability/assess")
def assess(request: AssessRequest) -> dict:
    registry = get_registry()
    manifest = PipelineManifest.model_validate(request.manifest)
    trace = QueryTrace.model_validate(request.trace) if request.trace is not None else None

    mechanism_ids = [request.mechanism_id] if request.mechanism_id else list(MECHANISM_EVALUATORS)
    for mid in mechanism_ids:
        if mid not in registry.mechanisms:
            raise HTTPException(status_code=404, detail=f"Unknown mechanism id: {mid}")

    assessments = [assess_mechanism(registry, mid, manifest, trace) for mid in mechanism_ids]
    return {"assessments": [a.model_dump(mode="json") for a in assessments]}


@router.post("/risk-events/derive")
def derive(request: RiskEventsRequest) -> dict:
    registry = get_registry()
    manifest = PipelineManifest.model_validate(request.manifest)
    trace = QueryTrace.model_validate(request.trace)

    result = derive_risk_events(
        registry,
        manifest,
        trace,
        include_disabled_for_audit=request.include_non_applicable_for_audit,
    )

    response = {
        "risk_events": [r.model_dump(mode="json") for r in result.risk_events],
        "applicable_assessments": [a.model_dump(mode="json") for a in result.applicable],
    }
    if request.include_non_applicable_for_audit:
        response["audited_non_applicable_assessments"] = [
            a.model_dump(mode="json") for a in result.audited_non_applicable
        ]
    return response
