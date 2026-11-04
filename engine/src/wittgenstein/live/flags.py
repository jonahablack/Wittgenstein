"""Awareness flags and check records (docs/live-pipeline-plan.md §§4-5, §8.1).

A flag is a *measured observation* about one run, phrased for a non-expert, with the
numbers behind it kept alongside. It never states that the answer is wrong. Flags whose
kind corresponds to a registry failure mechanism carry that mechanism's id and its
epistemic status *as read from the registry at runtime* -- never restated here -- so a
research hypothesis can never be rendered as an established failure.

Every check that runs is recorded (`CheckRecord`), including the ones that found
nothing: "checks passed" is part of what the user sees.
"""

from __future__ import annotations

import threading
from functools import lru_cache
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from wittgenstein.core.enums import (
    CheckOutcome,
    EpistemicStatus,
    FlagDisposition,
    FlagKind,
    FlagOrigin,
    FlagSeverity,
)
from wittgenstein.live.query import Span

#: Flag kind -> the registry mechanism it is an observable instance of. Embedding probes
#: have no entry on purpose: they are measurements of this run, not failure mechanisms
#: (plan §11 -- no new registry mechanisms in Phase 1).
REGISTRY_LINKS: dict[FlagKind, str] = {
    FlagKind.CONDITION_SATELLITE: "HYP_CONDITIONAL_APPLICABILITY_OMISSION",
    FlagKind.CONCESSION_SATELLITE: "HYP_EXCEPTION_CONCESSION_OMISSION",
    FlagKind.NEGATION_SCOPE: "HYP_NEGATION_TRANSFORMATION",
    FlagKind.BACKWARD_REFERENCE: "HYP_UNRESOLVED_CROSS_REFERENCE",
    FlagKind.CROSS_REFERENCE_NOT_FOLLOWED: "HYP_UNRESOLVED_CROSS_REFERENCE",
    FlagKind.UNRESOLVED_REFERENCE: "HYP_MISSING_ANAPHORIC_ANTECEDENT",
    FlagKind.SEVERED_CONTEXT: "HYP_MISSING_ANAPHORIC_ANTECEDENT",
    FlagKind.MODAL_STRENGTH_MISMATCH: "HYP_MODAL_STRENGTH_TRANSFORMATION",
    FlagKind.BUDGET_OMISSION: "PACK_OMISSION_OR_TRUNCATION",
    FlagKind.FACET_UNCOVERED: "RET_MULTIHOP_SUPPORT_INCOMPLETE",
    FlagKind.ENUMERATION_INCOMPLETE: "RET_MULTIHOP_SUPPORT_INCOMPLETE",
    FlagKind.NEAR_MISS: "RET_HARD_DISTRACTOR",
    FlagKind.ANSWER_SENTENCE_UNSUPPORTED: "GEN_UNSUPPORTED_DESPITE_CONTEXT",
    FlagKind.QUANTITY_MISMATCH: "HYP_THRESHOLD_UNIT_COMPARATOR_MISBINDING",
    FlagKind.POPULATION_QUALIFIER_DROPPED: "HYP_CONDITIONAL_APPLICABILITY_OMISSION",
}


class SourceRef(BaseModel):
    """An exact span of source text a flag concerns ("Show me" opens this)."""

    model_config = ConfigDict(extra="forbid")

    unit_id: str
    document_id: str
    char_start: int
    char_end: int
    quote: str


class RegistryLink(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mechanism_id: str
    canonical_name: str
    epistemic_status: EpistemicStatus


class AwarenessFlag(BaseModel):
    model_config = ConfigDict(extra="forbid")

    flag_id: str
    kind: FlagKind
    origin: FlagOrigin
    stage: str = Field(
        ..., description="query | embedding | retrieval | selection | packing | generation | answer"
    )
    severity: FlagSeverity
    disposition: FlagDisposition
    title: str = Field(..., description="Short, plain-language headline.")
    observation: str = Field(..., description="What was measured or matched -- a fact of this run.")
    why_it_matters: str = Field(..., description="Bounded language: what this *could* affect. Never causal.")
    action_taken: str | None = Field(default=None, description="What the pipeline already did about it.")
    what_to_check: str | None = Field(default=None, description="The one thing a person should look at, if any.")
    refs: list[SourceRef] = Field(default_factory=list)
    query_span: Span | None = None
    metrics: dict[str, Any] = Field(default_factory=dict)
    measurement: str = Field(
        ..., description="measured | inferred_from_rankings | pattern_match -- how the observation was obtained."
    )
    registry: RegistryLink | None = None
    pipeline_id: str | None = None


class CheckRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    check_id: str
    kind: FlagKind
    label: str
    outcome: CheckOutcome
    detail: str
    flag_ids: list[str] = Field(default_factory=list)


_REG_LOCK = threading.Lock()


@lru_cache(maxsize=1)
def _registry_links() -> dict[FlagKind, RegistryLink]:
    from wittgenstein.services.registry_service import get_registry

    with _REG_LOCK:
        registry = get_registry()
    out: dict[FlagKind, RegistryLink] = {}
    for kind, mech_id in REGISTRY_LINKS.items():
        mech = registry.mechanisms.get(mech_id)
        if mech is not None:
            out[kind] = RegistryLink(
                mechanism_id=mech_id,
                canonical_name=mech.canonical_name,
                epistemic_status=mech.epistemic_status,
            )
    return out


class FlagCollector:
    """Accumulates flags and check records for one pipeline run, assigning stable ids."""

    def __init__(self, pipeline_id: str | None = None) -> None:
        self.pipeline_id = pipeline_id
        self.flags: list[AwarenessFlag] = []
        self.checks: list[CheckRecord] = []

    def flag(self, kind: FlagKind, **fields: Any) -> AwarenessFlag:
        prefix = f"{self.pipeline_id}:" if self.pipeline_id else ""
        f = AwarenessFlag(
            flag_id=f"{prefix}flag{len(self.flags) + 1}",
            kind=kind,
            registry=_registry_links().get(kind),
            pipeline_id=self.pipeline_id,
            **fields,
        )
        self.flags.append(f)
        return f

    def check(
        self,
        kind: FlagKind,
        label: str,
        outcome: CheckOutcome,
        detail: str,
        flags: list[AwarenessFlag] | None = None,
    ) -> CheckRecord:
        prefix = f"{self.pipeline_id}:" if self.pipeline_id else ""
        rec = CheckRecord(
            check_id=f"{prefix}check{len(self.checks) + 1}",
            kind=kind,
            label=label,
            outcome=outcome,
            detail=detail,
            flag_ids=[f.flag_id for f in flags or []],
        )
        self.checks.append(rec)
        return rec
