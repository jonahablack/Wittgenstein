from __future__ import annotations

from fastapi import APIRouter
from pydantic import ValidationError

from wittgenstein.schemas.trace import QueryTrace
from wittgenstein.trace.validator import validate_trace

router = APIRouter(prefix="/traces", tags=["traces"])


@router.post("/validate")
def validate_trace_endpoint(payload: dict) -> dict:
    try:
        trace = QueryTrace.model_validate(payload)
    except ValidationError as exc:
        return {"valid": False, "errors": exc.errors()}
    problems = validate_trace(trace)
    return {"valid": not problems, "trace_id": trace.trace_id, "problems": problems}
