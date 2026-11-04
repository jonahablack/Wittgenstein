"""In-memory registry repository: the loaded, validated bundle of registry records."""

from __future__ import annotations

from dataclasses import dataclass, field

from wittgenstein.schemas import (
    EvidenceRecord,
    FailureMechanism,
    ManifestGate,
    ReviewAction,
    TraceTrigger,
)


@dataclass
class Registry:
    mechanisms: dict[str, FailureMechanism] = field(default_factory=dict)
    evidence: dict[str, EvidenceRecord] = field(default_factory=dict)
    gates: dict[str, ManifestGate] = field(default_factory=dict)
    triggers: dict[str, TraceTrigger] = field(default_factory=dict)
    review_actions: dict[str, ReviewAction] = field(default_factory=dict)

    def mechanism(self, mechanism_id: str) -> FailureMechanism:
        try:
            return self.mechanisms[mechanism_id]
        except KeyError as exc:
            raise KeyError(f"Unknown failure mechanism id: {mechanism_id!r}") from exc

    def evidence_for_mechanism(self, mechanism_id: str) -> list[EvidenceRecord]:
        return [e for e in self.evidence.values() if e.failure_mechanism_id == mechanism_id]

    def gates_for_mechanism(self, mechanism_id: str) -> list[ManifestGate]:
        return [g for g in self.gates.values() if g.failure_mechanism_id == mechanism_id]

    def triggers_for_mechanism(self, mechanism_id: str) -> list[TraceTrigger]:
        return [t for t in self.triggers.values() if t.failure_mechanism_id == mechanism_id]

    def review_action(self, review_action_id: str) -> ReviewAction:
        try:
            return self.review_actions[review_action_id]
        except KeyError as exc:
            raise KeyError(f"Unknown review action id: {review_action_id!r}") from exc
