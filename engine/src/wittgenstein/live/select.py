"""Coverage-aware adaptive top-k, remediation, and the decision ledger
(docs/live-pipeline-plan.md §6).

Every candidate ends with exactly one recorded fate and a plain-language reason. Fixed-k
pipelines go through the same code with the adaptive stopping rule off, so their
ledgers are directly comparable. Deterministic: same inputs, same ledger.

Constants are expressed relative to measured quantities -- relevance in z-score units of
this query's score distribution, redundancy relative to this model's measured typical
similarity between unrelated passages -- never as raw cosine thresholds.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

import numpy as np

from wittgenstein.core.enums import CandidateFate, FlagKind, KPolicy, PullInReason, QuestionType, RetrievalChannel
from wittgenstein.live import phrases as P
from wittgenstein.live.corpus import Unit, UnitSet
from wittgenstein.live.coverage import Instruments
from wittgenstein.live.flags import AwarenessFlag
from wittgenstein.live.pipelines import PipelineSpec
from wittgenstein.live.retrieve import Candidate, RetrievalResult

#: One newly covered question part is worth this many SD of relevance.
FACET_GAIN = 1.0
#: Penalty weight on similarity to already-selected passages above the model's typical.
REDUNDANCY_WEIGHT = 1.5
#: Above this share of the way from "typical" to "identical", a passage is a near-duplicate.
NEAR_DUPLICATE = 0.85
#: The relevance elbow is the largest drop between consecutive candidates; a drop smaller
#: than this (in SD) is not treated as an elbow at all.
MIN_ELBOW_GAP = 0.3
MAX_PULL_INS = 4

_REF_RE = re.compile(
    r"\b(Article|Section|Annex|Table|Definition|Clause|Appendix|Schedule|Chapter|Part|Paragraph)\s+"
    r"([A-Z]?[\dIVXLC]+(?:[.\-][\dA-Z]+)*|[A-Z](?:[.\-]\d+)*)",
)


@dataclass
class LedgerEntry:
    unit_id: str
    fate: CandidateFate
    reason: str
    channels: list[str]
    relevance_z: float
    fused_rank: int | None
    facets_covered: list[str]
    tokens: int
    order: int | None = None
    pull_in_reason: PullInReason | None = None
    pulled_in_for: str | None = None


@dataclass
class SelectionResult:
    selected: list[str]
    ledger: dict[str, LedgerEntry]
    budget: int
    tokens_used: int
    elbow_z: float | None
    coverable_facets: list[str]
    uncovered_facets: list[str]
    stop_reason: str
    pulled_in: list[str] = field(default_factory=list)


def _first_words(text: str, n: int = 4) -> str:
    return " ".join(P.lower(text).split()[:n])


def severed_opening(unit: Unit) -> str | None:
    """The dependent opener the passage starts with ("However,", "This", "Such ..."), if any."""
    head = _first_words(unit.text)
    for phrase in sorted(P.DEPENDENT_OPENERS, key=len, reverse=True):
        if head.startswith(phrase) and P.contains_phrase(head[: len(phrase) + 1], phrase):
            return phrase
    return None


def forward_pointer(unit: Unit) -> str | None:
    """Phrasing at the end of a passage announcing content it doesn't contain."""
    tail = P.lower(unit.text.rstrip())
    if tail.endswith(":"):
        return "a closing colon"
    last = tail[-80:]
    for phrase in P.FORWARD_POINTERS:
        if P.contains_phrase(last, phrase) and last.rstrip(" .").endswith(phrase):
            return phrase
    return None


_NUMBERED_REF_RE = re.compile(r"(?:\[see [^\]]{0,80}?)?(?<!\w)\(\s*(?P<num>\d{1,2}(?:\.\d{1,2})?)\s*\)\s*\]?")


def reference_targets(unit: Unit, units: UnitSet) -> list[tuple[str, list[str]]]:
    """(reference text, target unit ids) for each structural reference in the passage,
    resolved against section headings -- structural only, never semantic."""

    def heads(label: str, same_doc: bool) -> list[str]:
        return [
            u.unit_id
            for u in units.units
            if u.unit_id != unit.unit_id
            and (not same_doc or u.document_id == unit.document_id)
            and u.heading_context
            and any(
                line.lower().startswith(label) and (len(line) == len(label) or not line[len(label)].isalnum())
                for line in u.heading_context.splitlines()
            )
        ]

    out: list[tuple[str, list[str]]] = []
    seen: set[str] = set()
    for m in _REF_RE.finditer(unit.text):
        targets = heads(f"{m.group(1)} {m.group(2)}".lower(), same_doc=False)
        if targets:
            out.append((m.group(0), targets))
    # Numbered-section references as written in drug labels and many guidelines:
    # "[see Warnings and Precautions (5.1)]", "(5.1)". Bare numbers repeat across
    # documents, so these resolve within the citing document only.
    for m in _NUMBERED_REF_RE.finditer(unit.text):
        num = m.group("num")
        if num in seen:
            continue
        seen.add(num)
        targets = heads(num, same_doc=True)
        if targets:
            out.append((m.group(0).strip(), targets))
    return out


def select(
    spec: PipelineSpec,
    retrieval: RetrievalResult,
    inst: Instruments,
    probe_flags: list[AwarenessFlag],
    pairwise_p90: float | None,
) -> SelectionResult:
    units = inst.units
    pool: list[Candidate] = list(retrieval.pool)
    ledger: dict[str, LedgerEntry] = {}
    budget = spec.token_budget

    def entry(c: Candidate, fate: CandidateFate, reason: str) -> LedgerEntry:
        u = units.by_id[c.unit_id]
        e = LedgerEntry(
            unit_id=c.unit_id,
            fate=fate,
            reason=reason,
            channels=sorted(ch.value for ch in c.channels),
            relevance_z=round(c.relevance_z, 3),
            fused_rank=c.fused_rank or None,
            facets_covered=sorted(inst.facets_covered(c.unit_id)) if inst.analysis.facets else [],
            tokens=u.token_count,
        )
        ledger[c.unit_id] = e
        return e

    vecs = units.vectors(inst.embedder) if inst.embedder is not None else None
    pos = inst.pos
    typical = pairwise_p90 if pairwise_p90 is not None else 0.5

    def redundancy(uid: str, chosen: list[str]) -> float:
        """0 = no more similar than unrelated passages typically are; 1 = identical."""
        if vecs is None or not chosen:
            return 0.0
        sims = vecs[[pos[x] for x in chosen]] @ vecs[pos[uid]]
        return max(0.0, (float(sims.max()) - typical) / max(1e-6, 1.0 - typical))

    selected: list[str] = []
    used = 0
    covered: set[str] = set()
    facet_ids = [f.facet_id for f in inst.analysis.facets]
    coverable = sorted({fid for c in pool for fid in inst.facets_covered(c.unit_id)}) if facet_ids else []

    def take(c: Candidate, reason: str) -> None:
        nonlocal used
        e = entry(c, CandidateFate.SELECTED, reason)
        e.order = len(selected) + 1
        selected.append(c.unit_id)
        used += units.by_id[c.unit_id].token_count
        covered.update(e.facets_covered)

    elbow_z: float | None = None
    stop_reason = ""

    if spec.k_policy == KPolicy.FIXED:
        for c in pool:
            tokens = units.by_id[c.unit_id].token_count
            if len(selected) >= spec.k:
                entry(c, CandidateFate.NOT_REACHED, f"Beyond this pipeline's fixed cutoff of {spec.k} results.")
            elif used + tokens > budget:
                entry(c, CandidateFate.OMITTED_BUDGET, f"Would exceed the {budget}-token evidence budget.")
            else:
                take(c, f"Ranked #{c.fused_rank} -- within the fixed top {spec.k}.")
        stop_reason = f"fixed top {spec.k}"
    else:
        # Probes may have found strong evidence the fused ranking under-placed (a buried
        # sentence, a facet's own best match); such units join the pool, marked as such.
        boosted: dict[str, str] = {}
        for f in probe_flags:
            if f.kind in {FlagKind.DILUTION, FlagKind.FACET_DOMINANCE} and f.refs:
                uid = f.refs[0].unit_id
                boosted.setdefault(uid, f.title)
                if uid not in retrieval.by_id:
                    extra = Candidate(unit_id=uid, channels={RetrievalChannel.REMEDIATION})
                    if inst.dense is not None:
                        extra.dense_z = inst.dense.z(pos[uid])
                    extra.lexical_z = inst.lexical.z(pos[uid])
                    pool.append(extra)

        ranked = sorted(pool, key=lambda c: (-c.relevance_z, c.fused_rank or 10**6, c.unit_id))
        zs = [c.relevance_z for c in ranked[: spec.k_max + 1]]
        gaps = [(zs[i] - zs[i + 1], i) for i in range(spec.k_min - 1, len(zs) - 1)]
        no_elbow = False
        if gaps and max(gaps)[0] >= MIN_ELBOW_GAP:
            elbow_z = zs[max(gaps)[1]]
        else:
            # Relevance declines smoothly: there is no natural cutoff to find, so fall
            # back to the configured estimate k (plus whatever uncovered question
            # parts still need), and say so in the ledger.
            no_elbow = True
            elbow_z = zs[min(spec.k, len(zs)) - 1] if zs else 0.0

        enum_terms = (
            (inst.analysis.enumeration_target or "").split()
            if inst.analysis.question_type == QuestionType.ENUMERATION
            else []
        )
        remaining = list(ranked)
        while remaining:
            if len(selected) >= spec.k_max:
                stop_reason = f"reached the maximum of {spec.k_max} passages"
                break

            def gain(c: Candidate) -> float:
                new = set(inst.facets_covered(c.unit_id)) - covered
                return c.relevance_z + FACET_GAIN * len(new) - REDUNDANCY_WEIGHT * redundancy(c.unit_id, selected)

            best = max(remaining, key=lambda c: (gain(c), -(c.fused_rank or 10**6)))
            remaining.remove(best)
            new_facets = set(inst.facets_covered(best.unit_id)) - covered
            red = redundancy(best.unit_id, selected)
            tokens = units.by_id[best.unit_id].token_count
            enum_hit = bool(enum_terms) and all(
                P.contains_phrase(inst.lower_text(pos[best.unit_id]), t) for t in enum_terms
            )
            if red >= NEAR_DUPLICATE:
                entry(best, CandidateFate.SKIPPED_REDUNDANT, "Nearly duplicates a passage already selected.")
                continue
            if used + tokens > budget:
                entry(best, CandidateFate.OMITTED_BUDGET, f"Relevant, but would exceed the {budget}-token budget.")
                continue
            above = elbow_z is None or best.relevance_z >= elbow_z
            needed = len(selected) < spec.k_min
            if not (above or new_facets or needed or enum_hit or best.unit_id in boosted):
                entry(
                    best,
                    CandidateFate.BELOW_ELBOW,
                    (
                        f"Relevance declines smoothly with no natural cutoff, so selection stopped at the default "
                        f"of {spec.k}; this one ({best.relevance_z:.1f} SD) adds no uncovered part of the "
                        "question."
                    )
                    if no_elbow
                    else (
                        f"Relevance ({best.relevance_z:.1f} SD) falls below the cutoff where scores drop off "
                        f"({elbow_z:.1f} SD), and it adds no uncovered part of the question."
                    ),
                )
                stop_reason = (
                    f"no natural cutoff; stopped at the default of {spec.k} once every coverable part was covered"
                    if no_elbow
                    else "relevance dropped off and every coverable part of the question is covered"
                )
                break
            if best.unit_id in boosted and not above:
                why = f"Included because a check found it: {boosted[best.unit_id]}."
            elif new_facets and not above:
                names = ", ".join(f"“{f.span.text}”" for f in inst.analysis.facets if f.facet_id in new_facets)
                why = f"Covers {names}, which nothing selected so far does."
            elif enum_hit and not above:
                why = "Another item matching what the question asks to list."
            elif needed and not above:
                why = f"Kept to reach the minimum of {spec.k_min} passages."
            else:
                why = f"Relevance {best.relevance_z:.1f} SD, above the drop-off point."
                if new_facets:
                    names = ", ".join(f"“{f.span.text}”" for f in inst.analysis.facets if f.facet_id in new_facets)
                    why += f" Also covers {names}."
            take(best, why)
        # Passages a check specifically recommended are evaluated even after relevance
        # has dropped off -- the check found something the scores miss.
        for c in [c for c in remaining if c.unit_id in boosted]:
            remaining.remove(c)
            if len(selected) >= spec.k_max:
                entry(c, CandidateFate.NOT_REACHED, "Recommended by a check, but the passage limit was reached.")
            elif used + units.by_id[c.unit_id].token_count > budget:
                entry(c, CandidateFate.OMITTED_BUDGET, "Recommended by a check, but the budget is full.")
            elif redundancy(c.unit_id, selected) >= NEAR_DUPLICATE:
                entry(c, CandidateFate.SKIPPED_REDUNDANT, "Nearly duplicates a passage already selected.")
            else:
                take(c, f"Included because a check found it: {boosted[c.unit_id]}.")
        for c in remaining:
            if c.unit_id in ledger:
                continue
            if elbow_z is not None and c.relevance_z < elbow_z and not stop_reason.startswith("reached"):
                entry(c, CandidateFate.BELOW_ELBOW, f"Relevance {c.relevance_z:.1f} SD, below the drop-off point.")
            else:
                entry(c, CandidateFate.NOT_REACHED, "Selection stopped before reaching it.")
        stop_reason = stop_reason or "every candidate was considered"

    # --- remediation --------------------------------------------------------------
    pulled: list[str] = []

    def pull(uid: str, reason: PullInReason, why: str, for_uid: str) -> bool:
        nonlocal used
        if uid in selected or len(pulled) >= MAX_PULL_INS:
            return False
        u = units.by_id[uid]
        cand = retrieval.by_id.get(uid)
        if cand is None:
            cand = Candidate(unit_id=uid, channels={RetrievalChannel.REMEDIATION})
            cand.lexical_z = inst.lexical.z(pos[uid])
            if inst.dense is not None:
                cand.dense_z = inst.dense.z(pos[uid])
        if used + u.token_count > budget:
            if uid not in ledger:
                entry(cand, CandidateFate.OMITTED_BUDGET, f"Needed context ({why}), but the budget is full.")
            return False
        e = entry(cand, CandidateFate.PULLED_IN, why)
        e.pull_in_reason, e.pulled_in_for, e.order = reason, for_uid, len(selected) + 1
        selected.append(uid)
        pulled.append(uid)
        used += u.token_count
        return True

    if spec.remediation.any:
        query_terms = set(inst.analysis.content_terms)
        for uid in list(selected):
            u = units.by_id[uid]
            if spec.remediation.severed_neighbor:
                opener = severed_opening(u)
                if opener and u.prev_id:
                    pull(
                        u.prev_id,
                        PullInReason.SEVERED_NEIGHBOR,
                        f"The passage before a selected one, which opens with “{opener}” and depends on it.",
                        uid,
                    )
                pointer = forward_pointer(u)
                if pointer and u.next_id:
                    pull(
                        u.next_id,
                        PullInReason.SEVERED_NEIGHBOR,
                        f"The passage after a selected one, which ends with {pointer!s} pointing ahead.",
                        uid,
                    )
            if spec.remediation.cross_reference:
                for ref_text, targets in reference_targets(u, units)[:2]:
                    if not any(t in selected for t in targets):
                        best_t = max(targets, key=lambda t: (inst.lexical.z(pos[t]), -pos[t]))
                        pull(best_t, PullInReason.CROSS_REFERENCE_TARGET, f"Referred to as “{ref_text}”.", uid)
            if spec.remediation.definition:
                low = inst.lower_text(pos[uid])
                for term, def_ids in units.definitions.items():
                    if uid in def_ids or any(d in selected for d in def_ids):
                        continue
                    if P.contains_phrase(low, term) and set(term.split()) & query_terms:
                        pull(
                            def_ids[0],
                            PullInReason.DEFINITION,
                            f"Defines “{term}”, used in a selected passage.",
                            uid,
                        )

    uncovered = [f for f in coverable if f not in covered]
    return SelectionResult(
        selected=selected,
        ledger=ledger,
        budget=budget,
        tokens_used=used,
        elbow_z=elbow_z,
        coverable_facets=coverable,
        uncovered_facets=uncovered,
        stop_reason=stop_reason,
        pulled_in=pulled,
    )


def redundancy_matrix(units: UnitSet, ids: list[str], vecs: np.ndarray, pos: dict[str, int]) -> np.ndarray:
    m = vecs[[pos[i] for i in ids]]
    return m @ m.T


def fit_to_capacity(sel: SelectionResult, cap: int, reason: str) -> list[str]:
    """Keep at most `cap` passages: first one passage for each part of the question that
    the selection covers (in selection order), then the rest in selection order. The
    rest are recorded as left out for the model's capacity. Returns the removed ids."""
    if len(sel.selected) <= cap:
        return []
    keep: list[str] = []
    for facet in sel.coverable_facets:
        if len(keep) >= cap:
            break
        uid = next((u for u in sel.selected if facet in sel.ledger[u].facets_covered), None)
        if uid is not None and uid not in keep:
            keep.append(uid)
    for u in sel.selected:
        if len(keep) >= cap:
            break
        if u not in keep:
            keep.append(u)
    removed = [u for u in sel.selected if u not in keep]
    sel.selected = [u for u in sel.selected if u in keep]
    sel.pulled_in = [u for u in sel.pulled_in if u in keep]
    for u in removed:
        e = sel.ledger[u]
        e.fate = CandidateFate.OMITTED_CAPACITY
        e.reason = reason
        e.order = None
    for i, u in enumerate(sel.selected):
        sel.ledger[u].order = i + 1
    sel.tokens_used = sum(sel.ledger[u].tokens for u in sel.selected)
    return removed
