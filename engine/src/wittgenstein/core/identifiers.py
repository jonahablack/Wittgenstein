"""ID generation and validation helpers, shared across schemas and the registry loader."""

from __future__ import annotations

import re
import uuid

_MECHANISM_ID_RE = re.compile(r"^[A-Z][A-Z0-9]*(?:_[A-Z0-9]+)+$")

#: Sentinel used throughout manifests/traces/envelopes to mean "this field was
#: considered and its value is genuinely not known" -- distinct from a field that was
#: simply omitted from the payload. Matching code must treat both the same way
#: (never infer a default), but the sentinel lets manifest authors be explicit.
UNKNOWN = "unknown"


def is_valid_mechanism_id(value: str) -> bool:
    """Mechanism IDs are SCREAMING_SNAKE_CASE, e.g. RET_HARD_DISTRACTOR."""

    return bool(_MECHANISM_ID_RE.match(value))


def new_evidence_id(mechanism_id: str) -> str:
    return f"EV-{mechanism_id}-{uuid.uuid4().hex[:8]}"


def new_assessment_id() -> str:
    return f"ASSESS-{uuid.uuid4().hex[:12]}"


def new_risk_event_id() -> str:
    return f"RISK-{uuid.uuid4().hex[:12]}"


def new_manifest_id(system_name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", system_name.lower()).strip("-")
    return f"MANIFEST-{slug}-{uuid.uuid4().hex[:8]}"


def new_trace_id() -> str:
    return f"TRACE-{uuid.uuid4().hex[:12]}"


def new_review_event_id() -> str:
    return f"REVIEW-{uuid.uuid4().hex[:12]}"
