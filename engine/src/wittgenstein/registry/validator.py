"""Cross-record registry integrity rules.

These are the checks that cannot be expressed on a single Pydantic model in isolation
because they require looking across records (e.g. "does this mechanism have at least
one qualifying linked evidence record"). Collects every problem before raising, so a
single run surfaces the full list rather than stopping at the first.
"""

from __future__ import annotations

from wittgenstein.core.enums import (
    ESTABLISHED_GRADE_FLOOR,
    ActivationPolicy,
    EpistemicStatus,
    EvidenceDirection,
    EvidenceGrade,
    PeerReviewStatus,
)
from wittgenstein.registry.repository import Registry


class RegistrySeedIntegrityError(Exception):
    def __init__(self, problems: list[str]):
        self.problems = problems
        super().__init__(
            f"{len(problems)} registry integrity problem(s):\n" + "\n".join(f"- {p}" for p in problems)
        )


def validate_registry(registry: Registry) -> None:
    problems: list[str] = []
    problems += _check_dangling_references(registry)
    problems += _check_established_status_requires_a_grade_evidence(registry)
    problems += _check_activation_requires_verified_evidence(registry)
    problems += _check_no_duplicate_ids(registry)
    if problems:
        raise RegistrySeedIntegrityError(problems)


def _check_no_duplicate_ids(registry: Registry) -> list[str]:
    # dict keys already dedupe by id; detect same id used across the *union* of raw
    # loads would require raw lists, so this only guards internal consistency of ids.
    problems: list[str] = []
    for mechanism_id, mechanism in registry.mechanisms.items():
        if mechanism.id != mechanism_id:
            problems.append(f"Mechanism keyed as {mechanism_id!r} but id field is {mechanism.id!r}.")
    return problems


def _check_dangling_references(registry: Registry) -> list[str]:
    problems: list[str] = []
    for evidence in registry.evidence.values():
        if evidence.failure_mechanism_id not in registry.mechanisms:
            problems.append(
                f"EvidenceRecord {evidence.id} references unknown "
                f"failure_mechanism_id {evidence.failure_mechanism_id!r}."
            )
    for gate in registry.gates.values():
        if gate.failure_mechanism_id not in registry.mechanisms:
            problems.append(
                f"ManifestGate {gate.id} references unknown failure_mechanism_id {gate.failure_mechanism_id!r}."
            )
    for trigger in registry.triggers.values():
        if trigger.failure_mechanism_id not in registry.mechanisms:
            problems.append(
                f"TraceTrigger {trigger.id} references unknown "
                f"failure_mechanism_id {trigger.failure_mechanism_id!r}."
            )
    return problems


def _check_established_status_requires_a_grade_evidence(registry: Registry) -> list[str]:
    """A mechanism cannot claim externally_established without qualifying evidence meeting
    the two-path evidence-threshold rule (docs/evidence-grading.md, "Evidence thresholds"):

    1. Evidence must be peer-reviewed, A1 or A2 grade (as before) -- this alone is no
       longer sufficient.
    2. Evidence must be RAG-native (`experimental_envelope.rag_presence is True`). A study
       conducted in a non-RAG setting (e.g. plain long-context QA) can never by itself
       support externally_established, however strong its grade -- it transfers only via
       manifest_conditioned_transfer. This is the "directly_rag_established vs.
       manifest_conditioned_transfer vs. untransferred" distinction from the same doc,
       enforced here rather than left to convention (CTX_POSITION_SENSITIVE_USE / "Lost in
       the Middle" was already seeded correctly by hand; this makes it a hard rule).
    3. Evidence must have `direction=supports` -- a record that refutes or is mixed/null on
       the claim cannot itself ground establishment.
    4. Among evidence meeting 1-3, either (a) at least one is graded A1 ("one closely
       matched A1 study with strong evidence"), or (b) at least two independent qualifying
       records exist ("at least two independent, broadly consistent A1/A2 studies"). A
       single A2-only record is no longer sufficient on its own -- a single narrow
       benchmark must not be presented as a universal law.
    """

    problems: list[str] = []
    for mechanism in registry.mechanisms.values():
        if mechanism.epistemic_status != EpistemicStatus.EXTERNALLY_ESTABLISHED:
            continue
        linked = registry.evidence_for_mechanism(mechanism.id)
        graded = [
            e
            for e in linked
            if e.peer_review_status == PeerReviewStatus.PEER_REVIEWED
            and e.evidence_grade in ESTABLISHED_GRADE_FLOOR
        ]
        if not graded:
            problems.append(
                f"{mechanism.id}: epistemic_status=externally_established requires at least one "
                "peer-reviewed evidence record graded A1 or A2; none found among "
                f"{[e.id for e in linked]}."
            )
            continue
        qualifying = [
            e
            for e in graded
            if e.experimental_envelope.rag_presence is True and e.direction == EvidenceDirection.SUPPORTS
        ]
        if not qualifying:
            problems.append(
                f"{mechanism.id}: epistemic_status=externally_established requires at least one "
                "A1/A2 peer-reviewed evidence record that is RAG-native "
                "(experimental_envelope.rag_presence=True) and direction=supports; the "
                f"linked A1/A2 record(s) {[e.id for e in graded]} do not qualify (non-RAG "
                "evidence establishes at most manifest_conditioned_transfer, per "
                "docs/evidence-grading.md)."
            )
            continue
        has_a1 = any(e.evidence_grade == EvidenceGrade.A1_DIRECT_CAUSAL_PEER_REVIEWED for e in qualifying)
        if not (has_a1 or len(qualifying) >= 2):
            problems.append(
                f"{mechanism.id}: epistemic_status=externally_established requires either one "
                "closely-matched A1 study or at least two independent, broadly consistent A1/A2 "
                f"studies; only {[e.id for e in qualifying]} qualifies (single A2-grade record). "
                "A single narrow benchmark must not be presented as a universal law -- see "
                "docs/evidence-grading.md."
            )
    return problems


def _check_activation_requires_verified_evidence(registry: Registry) -> list[str]:
    """Production/default activation cannot occur while a mechanism's supporting evidence
    has TODO or unverified primary-source fields.

    Scoped to mechanisms whose activation claim actually rests on external written
    evidence (externally_established, manifest_conditioned_transfer). A
    trace_integrity_condition mechanism's core function is reporting a directly
    observable trace fact (e.g. "a selected item was omitted before packing") and does
    not require external literature to be enabled -- it is prevented from making a
    *causal* claim without evidence at the RiskEvent level instead (see
    RiskEvent._causal_claim_requires_support).
    """

    problems: list[str] = []
    non_activatable_policies = {
        ActivationPolicy.DISABLED_BY_DEFAULT_OR_RESEARCH_MODE,
        ActivationPolicy.RETIRED,
    }
    evidence_dependent_statuses = {
        EpistemicStatus.EXTERNALLY_ESTABLISHED,
        EpistemicStatus.MANIFEST_CONDITIONED_TRANSFER,
    }
    for mechanism in registry.mechanisms.values():
        if mechanism.default_activation_policy in non_activatable_policies:
            continue
        if mechanism.epistemic_status not in evidence_dependent_statuses:
            continue
        linked = registry.evidence_for_mechanism(mechanism.id)
        unverified = [e.id for e in linked if e.is_unverified_or_incomplete()]
        if unverified:
            problems.append(
                f"{mechanism.id}: default_activation_policy="
                f"{mechanism.default_activation_policy.value} but linked evidence record(s) "
                f"{unverified} are unverified or contain TODO fields. Set "
                "default_activation_policy=disabled_by_default_or_research_mode until "
                "primary-source verification is complete."
            )
    return problems
