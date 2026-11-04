"""The live event stream (docs/live-pipeline-plan.md §7).

Each event is one JSON object: a sequence number, milliseconds since the run started,
a type, the pipeline it belongs to (if any), and a type-specific payload. Payload
models are Pydantic, and their JSON Schema is exported for the frontend's generated
TypeScript types (scripts/export_live_schema.py).
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from wittgenstein.core.enums import LiveEventType


class LiveEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    seq: int
    t_ms: float
    type: LiveEventType
    pipeline_id: str | None = None
    data: dict[str, Any] = Field(default_factory=dict)


class UnitPoint(BaseModel):
    """One retrieval unit as the evidence field draws it."""

    model_config = ConfigDict(extra="forbid")

    unit_id: str
    document_id: str
    position: float
    location: str
    tokens: int
    preview: str


class Emitter:
    """Thread-safe event sink with run-relative timestamps. Pipelines run concurrently,
    so `emit` may be called from worker threads; sequence numbers stay total-ordered."""

    def __init__(self, sink: Callable[[LiveEvent], None]) -> None:
        self._sink = sink
        self._lock = threading.Lock()
        self._seq = 0
        self._t0 = time.perf_counter()
        self.events: list[LiveEvent] = []

    def emit(self, type_: LiveEventType, pipeline_id: str | None = None, **data: Any) -> LiveEvent:
        with self._lock:
            self._seq += 1
            ev = LiveEvent(
                seq=self._seq,
                t_ms=round((time.perf_counter() - self._t0) * 1000, 2),
                type=type_,
                pipeline_id=pipeline_id,
                data=data,
            )
            self.events.append(ev)
            self._sink(ev)  # inside the lock: delivery order == sequence order
        return ev
