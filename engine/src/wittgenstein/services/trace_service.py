"""Thin service wrapper around trace structural validation."""

from __future__ import annotations

from wittgenstein.schemas.trace import QueryTrace
from wittgenstein.trace.validator import validate_trace


def validate(trace: QueryTrace) -> list[str]:
    return validate_trace(trace)
