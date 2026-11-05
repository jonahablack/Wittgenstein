"""Evidence-gap signals G1-G7, run on the final selection (docs/live-pipeline-plan.md §5).

Each names the concrete missing piece and links to it when it exists. Remediations the
pipeline performed are reported here as *handled* flags ("we noticed X, so we did Y"),
so the user sees what the system already took care of, not only what is left.
"""

from __future__ import annotations

from collections.abc import Sequence

from wittgenstein.core.enums import (
    CandidateFate,
    FlagDisposition,
    FlagKind,
    FlagOrigin,
    FlagSeverity,
    KPolicy,
    PullInReason,
    QuestionType,
)
from wittgenstein.live import phrases as P
from wittgenstein.live.conflicts import find_conflicts
from wittgenstein.live.coverage import Instruments
from wittgenstein.live.flags import AwarenessFlag, FlagCollector
from wittgenstein.live.pipelines import PipelineSpec
from wittgenstein.live.probes import ref
from wittgenstein.live.retrieve import RetrievalResult
from wittgenstein.live.select import (
    NEAR_DUPLICATE,
    SelectionResult,
    forward_pointer,
    reference_targets,
    severed_opening,
)

#: A cut-off candidate this close (in SD) to the last selected one makes the cutoff arbitrary.
TIED_AT_CUTOFF = 0.15


def run_gaps(
    spec: PipelineSpec,
    retrieval: RetrievalResult,
    inst: Instruments,
    sel: SelectionResult,
    out: FlagCollector,
    weak: bool,
    scope: str = "document",
) -> None:
    units = inst.units
    a = inst.analysis
    chosen = set(sel.selected)
    pulled_by: dict[str, list[tuple[str, PullInReason]]] = {}
    for uid in sel.pulled_in:
        e = sel.ledger[uid]
        if e.pulled_in_for and e.pull_in_reason:
            pulled_by.setdefault(e.pulled_in_for, []).append((uid, e.pull_in_reason))

    # --- G1 facet uncovered -----------------------------------------------------------
    label = "Every part of the question has evidence"
    if not a.facets:
        out.check(FlagKind.FACET_UNCOVERED, label, _na(), "No question parts identified.")
    elif weak:
        out.check(FlagKind.FACET_UNCOVERED, label, _na(), "Skipped: the document may not cover this question.")
    else:
        flags = []
        covered = {fid for uid in sel.selected for fid in inst.facets_covered(uid)}
        for f in a.facets:
            if f.facet_id in covered:
                continue
            absent = [t for t in f.terms if len(t) > 2 and not units.bm25._postings.get(t)]
            best = next(
                (
                    uid
                    for uid in inst.facet_best(f.facet_id, limit=10)
                    if inst.facet_coverage(uid, f.facet_id).covered
                ),
                None,
            )
            if best is None:
                # Before saying the source has nothing on this part, look at every
                # passage by its words too -- not just the top few by meaning.
                by_terms = [
                    u.unit_id for u in units.units if inst.facet_coverage(u.unit_id, f.facet_id).how == "terms"
                ]
                if by_terms:
                    best = max(by_terms, key=lambda uid: (inst.lexical.z(inst.pos[uid]), -inst.pos[uid]))
            if best is None:
                obs = (
                    f"“{f.span.text}” is never mentioned in the {scope}."
                    if absent and len(absent) == len([t for t in f.terms if len(t) > 2])
                    else f"No passage in the {scope} clearly matches “{f.span.text}”."
                )
                flags.append(
                    out.flag(
                        FlagKind.FACET_UNCOVERED,
                        origin=FlagOrigin.TEXT,
                        stage="selection",
                        severity=FlagSeverity.WARNING,
                        disposition=FlagDisposition.NEEDS_REVIEW,
                        title=f"No evidence for “{f.span.text}”",
                        observation=obs,
                        why_it_matters="This part of the question can't be answered from the document; an answer "
                        "that addresses it is not grounded in the source.",
                        what_to_check=f"Whether the answer says anything about “{f.span.text}”.",
                        query_span=f.span,
                        metrics={"facet_id": f.facet_id, "absent_terms": absent},
                        measurement="measured",
                    )
                )
            else:
                best_entry = sel.ledger.get(best)
                fate = best_entry.fate.value.replace("_", " ") if best_entry else "not retrieved"
                flags.append(
                    out.flag(
                        FlagKind.FACET_UNCOVERED,
                        origin=FlagOrigin.PIPELINE,
                        stage="selection",
                        severity=FlagSeverity.WARNING,
                        disposition=FlagDisposition.NEEDS_REVIEW,
                        title=f"Evidence for “{f.span.text}” was left out",
                        observation=f"None of the passages used cover “{f.span.text}”. This passage does, but "
                        f"wasn't used ({fate}).",
                        why_it_matters="The answer can only address this part of the question from general "
                        "knowledge, not from the document.",
                        what_to_check="Whether this passage changes the answer.",
                        refs=[ref(units.by_id[best])],
                        query_span=f.span,
                        metrics={"facet_id": f.facet_id, "fate": best_entry.fate.value if best_entry else None},
                        measurement="measured",
                    )
                )
        out.check(
            FlagKind.FACET_UNCOVERED,
            label,
            _outcome(flags),
            f"{len(a.facets) - len(flags)}/{len(a.facets)} parts have evidence in the passages used.",
            flags,
        )

    # --- G2 / G3 / G6: remediation targets, handled or not ------------------------------
    _remediation_family(
        out,
        FlagKind.SEVERED_CONTEXT,
        "Passages that depend on their neighbors came with them",
        sel,
        pulled_by,
        PullInReason.SEVERED_NEIGHBOR,
        [
            (uid, f"opens with “{op}”", units.by_id[uid].prev_id)
            for uid in sel.selected
            if (op := severed_opening(units.by_id[uid])) and units.by_id[uid].prev_id
        ]
        + [
            (uid, f"ends with {fp}", units.by_id[uid].next_id)
            for uid in sel.selected
            if (fp := forward_pointer(units.by_id[uid])) and units.by_id[uid].next_id
        ],
        units,
        chosen,
        spec.remediation.severed_neighbor,
    )
    xrefs = []
    for uid in sel.selected:
        for ref_text, targets in reference_targets(units.by_id[uid], units)[:2]:
            hit = next((t for t in targets if t in chosen), None)
            xrefs.append((uid, f"refers to “{ref_text}”", hit or targets[0]))
    _remediation_family(
        out,
        FlagKind.CROSS_REFERENCE_NOT_FOLLOWED,
        "Cross-references followed",
        sel,
        pulled_by,
        PullInReason.CROSS_REFERENCE_TARGET,
        xrefs,
        units,
        chosen,
        spec.remediation.cross_reference,
    )
    qterms = set(a.content_terms)
    defs = []
    for uid in sel.selected:
        low = inst.lower_text(inst.pos[uid])
        for term, def_ids in units.definitions.items():
            if uid in def_ids or not (set(term.split()) & qterms) or not P.contains_phrase(low, term):
                continue
            hit = next((d for d in def_ids if d in chosen), None)
            defs.append((uid, f"uses the defined term “{term}”", hit or def_ids[0]))
    _remediation_family(
        out,
        FlagKind.DEFINITION_NOT_IN_CONTEXT,
        "Definitions of key terms included",
        sel,
        pulled_by,
        PullInReason.DEFINITION,
        defs,
        units,
        chosen,
        spec.remediation.definition,
    )

    # --- G4 budget omission -------------------------------------------------------------
    omitted = [
        e
        for e in sel.ledger.values()
        if e.fate == CandidateFate.OMITTED_BUDGET and (sel.elbow_z is None or e.relevance_z >= sel.elbow_z)
    ]
    flags = []
    if omitted:
        top = sorted(omitted, key=lambda e: -e.relevance_z)[:3]
        flags.append(
            out.flag(
                FlagKind.BUDGET_OMISSION,
                origin=FlagOrigin.PIPELINE,
                stage="packing",
                severity=FlagSeverity.CAUTION,
                disposition=FlagDisposition.NEEDS_REVIEW,
                title=f"{len(omitted)} relevant passage{'s' if len(omitted) > 1 else ''} didn't fit",
                observation=f"The evidence budget ({sel.budget} tokens) was full; {len(omitted)} passage(s) as "
                "relevant as ones used were left out for space alone.",
                why_it_matters="Whatever they add is invisible to the answer.",
                what_to_check="Whether the left-out passages change the answer.",
                refs=[ref(units.by_id[e.unit_id]) for e in top],
                metrics={"budget": sel.budget, "used": sel.tokens_used, "omitted": len(omitted)},
                measurement="measured",
            )
        )
    out.check(
        FlagKind.BUDGET_OMISSION,
        "Nothing relevant dropped for space",
        _outcome(flags),
        f"{sel.tokens_used}/{sel.budget} tokens used; {len(omitted)} relevant passages omitted for space.",
        flags,
    )

    # --- G5 enumeration -------------------------------------------------------------------
    label = "Lists are complete"
    if a.question_type != QuestionType.ENUMERATION or not a.enumeration_target:
        out.check(FlagKind.ENUMERATION_INCOMPLETE, label, _na(), "The question doesn't ask for a list.")
    else:
        terms = a.enumeration_target.split()
        matching = [
            u.unit_id
            for i, u in enumerate(units.units)
            if all(P.contains_phrase(inst.lower_text(i), t) for t in terms)
        ]
        missing = [uid for uid in matching if uid not in chosen]
        flags = []
        if missing:
            flags.append(
                out.flag(
                    FlagKind.ENUMERATION_INCOMPLETE,
                    origin=FlagOrigin.PIPELINE,
                    stage="selection",
                    severity=FlagSeverity.WARNING,
                    disposition=FlagDisposition.NEEDS_REVIEW,
                    title=f"{len(missing)} more passages mention “{a.enumeration_target}”",
                    observation=f"{len(matching)} passages in the {scope} mention “{a.enumeration_target}”; "
                    f"{len(matching) - len(missing)} were used.",
                    why_it_matters="A list built from part of the matching passages may be incomplete.",
                    what_to_check="Whether the list in the answer is complete.",
                    refs=[ref(units.by_id[uid]) for uid in missing[:3]],
                    metrics={"matching": len(matching), "used": len(matching) - len(missing)},
                    measurement="pattern_match",
                )
            )
        out.check(
            FlagKind.ENUMERATION_INCOMPLETE,
            label,
            _outcome(flags),
            f"{len(matching)} passages match “{a.enumeration_target}”; {len(missing)} not used.",
            flags,
        )

    # --- G7 redundancy --------------------------------------------------------------------
    flags = []
    skipped = [e for e in sel.ledger.values() if e.fate == CandidateFate.SKIPPED_REDUNDANT]
    if skipped:
        flags.append(
            out.flag(
                FlagKind.REDUNDANCY,
                origin=FlagOrigin.TEXT,
                stage="selection",
                severity=FlagSeverity.INFO,
                disposition=FlagDisposition.HANDLED,
                title=f"Skipped {len(skipped)} near-duplicate passage{'s' if len(skipped) > 1 else ''}",
                observation="They repeat passages already selected almost word for word.",
                why_it_matters="Duplicates spend the evidence budget without adding anything.",
                action_taken="Left them out and used the space for other evidence.",
                refs=[ref(units.by_id[e.unit_id]) for e in skipped[:3]],
                metrics={"skipped": len(skipped)},
                measurement="measured",
            )
        )
    elif inst.embedder is not None and len(sel.selected) > 1:
        vecs = units.vectors(inst.embedder)
        typical = (
            inst.profile.pairwise_similarity.p90 if inst.profile and inst.profile.pairwise_similarity else 0.5
        )
        dups = []
        for i, x in enumerate(sel.selected):
            for y in sel.selected[i + 1 :]:
                sim = float(vecs[inst.pos[x]] @ vecs[inst.pos[y]])
                if (sim - typical) / max(1e-6, 1 - typical) >= NEAR_DUPLICATE:
                    dups.append((x, y))
        if dups:
            x, y = dups[0]
            flags.append(
                out.flag(
                    FlagKind.REDUNDANCY,
                    origin=FlagOrigin.PIPELINE,
                    stage="selection",
                    severity=FlagSeverity.INFO,
                    disposition=FlagDisposition.INFORMATIONAL,
                    title="Two passages used are near-duplicates",
                    observation=f"{len(dups)} pair(s) of selected passages say almost the same thing.",
                    why_it_matters="The space could have held other evidence.",
                    refs=[ref(units.by_id[x]), ref(units.by_id[y])],
                    metrics={"pairs": len(dups)},
                    measurement="measured",
                )
            )
    out.check(
        FlagKind.REDUNDANCY, "No duplicate evidence", _outcome(flags), f"{len(flags)} duplicate findings.", flags
    )

    # --- G8 conflicting evidence among the passages used -----------------------------------
    flags = []
    for cf in find_conflicts(units, sel.selected):
        ua, ub = units.by_id[cf.unit_a], units.by_id[cf.unit_b]
        what = "one says the opposite of the other" if cf.dimension == "polarity" else "they give different values"
        flags.append(
            out.flag(
                FlagKind.CONTEXT_CONFLICT,
                origin=FlagOrigin.TEXT,
                stage="selection",
                severity=FlagSeverity.WARNING,
                disposition=FlagDisposition.NEEDS_REVIEW,
                title="Two passages used disagree",
                observation=f"“{cf.sentence_a[0][:180]}” ({ua.location}) and “{cf.sentence_b[0][:180]}” "
                f"({ub.location}): {what}.",
                why_it_matters="An answer built from both may follow either one without saying so. Nothing in "
                "these passages says which applies (a different edition, patient group or situation may).",
                what_to_check="Which of the two applies to your case, and whether the answer says.",
                refs=[ref(ua, cf.sentence_a[1], cf.sentence_a[2]), ref(ub, cf.sentence_b[1], cf.sentence_b[2])],
                metrics={"units": [cf.unit_a, cf.unit_b], "dimension": cf.dimension, "fields": list(cf.fields)},
                measurement="pattern_match",
            )
        )
    out.check(
        FlagKind.CONTEXT_CONFLICT,
        "Passages used agree with each other",
        _outcome(flags) if len(sel.selected) > 1 else _na(),
        f"{len(flags)} conflicting pair(s) among {len(sel.selected)} passages used."
        if len(sel.selected) > 1
        else "Only one passage was used.",
        flags,
    )

    # --- D6b ambiguous cutoff (fixed-k only: adaptive selection decides at the elbow) -------
    label = "The cutoff falls at a natural break"
    if spec.k_policy != KPolicy.FIXED:
        out.check(FlagKind.AMBIGUOUS_CUTOFF, label, _na(), "Selection stopped where relevance drops off.")
        return
    last = [sel.ledger[u] for u in sel.selected]
    nxt = sorted(
        (e for e in sel.ledger.values() if e.fate == CandidateFate.NOT_REACHED and e.fused_rank),
        key=lambda e: e.fused_rank or 0,
    )
    flags = []
    if last and nxt:
        tail, first_out = last[-1], nxt[0]
        if first_out.relevance_z >= tail.relevance_z - TIED_AT_CUTOFF:
            used_facets = {fid for u in sel.selected for fid in inst.facets_covered(u)}
            adds = set(first_out.facets_covered) - used_facets
            flags.append(
                out.flag(
                    FlagKind.AMBIGUOUS_CUTOFF,
                    origin=FlagOrigin.PIPELINE,
                    stage="selection",
                    severity=FlagSeverity.CAUTION if adds else FlagSeverity.INFO,
                    disposition=FlagDisposition.NEEDS_REVIEW if adds else FlagDisposition.INFORMATIONAL,
                    title=(
                        f"Result #{first_out.fused_rank} was cut but scores higher than #{tail.fused_rank}"
                        if first_out.relevance_z > tail.relevance_z + TIED_AT_CUTOFF
                        else f"Result #{first_out.fused_rank} was cut but is as relevant as #{tail.fused_rank}"
                    ),
                    observation=f"#{tail.fused_rank} scored {tail.relevance_z:.2f} SD and was used; "
                    f"#{first_out.fused_rank} scored {first_out.relevance_z:.2f} SD and was cut by the fixed "
                    f"top-{spec.k} rule.",
                    why_it_matters="Where the cutoff falls is close to arbitrary here.",
                    what_to_check="Whether the cut passage changes the answer." if adds else None,
                    refs=[ref(units.by_id[first_out.unit_id])],
                    metrics={
                        "last_used_z": tail.relevance_z,
                        "first_cut_z": first_out.relevance_z,
                        "adds_uncovered_parts": sorted(adds),
                    },
                    measurement="measured",
                )
            )
    out.check(FlagKind.AMBIGUOUS_CUTOFF, label, _outcome(flags), f"Fixed top {spec.k}.", flags)


def _na():  # noqa: ANN202
    from wittgenstein.core.enums import CheckOutcome

    return CheckOutcome.NOT_APPLICABLE


def _outcome(flags: list[AwarenessFlag]):  # noqa: ANN202
    from wittgenstein.core.enums import CheckOutcome

    return CheckOutcome.FLAGGED if flags else CheckOutcome.PASSED


_FAMILY_TEXT = {
    FlagKind.SEVERED_CONTEXT: (
        "A passage used depends on text next to it",
        "Its meaning depends on the neighboring passage, which the chunking separated from it.",
        "Included the neighboring passage too.",
    ),
    FlagKind.CROSS_REFERENCE_NOT_FOLLOWED: (
        "A passage used points to another section",
        "Its meaning may depend on the section it refers to.",
        "Included the referenced section too.",
    ),
    FlagKind.DEFINITION_NOT_IN_CONTEXT: (
        "A passage used relies on a defined term",
        "The document defines this term elsewhere; the definition can narrow or change what the passage says.",
        "Included the definition too.",
    ),
}


def _remediation_family(
    out: FlagCollector,
    kind: FlagKind,
    label: str,
    sel: SelectionResult,
    pulled_by: dict[str, list[tuple[str, PullInReason]]],
    reason: PullInReason,
    items: Sequence[tuple[str, str, str | None]],
    units,  # noqa: ANN001 -- UnitSet
    chosen: set[str],
    enabled: bool,
) -> None:
    title, why, action = _FAMILY_TEXT[kind]
    flags = []
    seen: set[tuple[str, str]] = set()
    for uid, what, target in items:
        if target is None or (uid, target) in seen or target == uid:
            continue
        seen.add((uid, target))
        u = units.by_id[uid]
        handled_now = any(t == target and r == reason for t, r in pulled_by.get(uid, []))
        already = target in chosen and not handled_now
        if already:
            continue  # the neighbor/target was selected on its own merits: nothing to report
        refs = [ref(u), ref(units.by_id[target])]
        if handled_now:
            flags.append(
                out.flag(
                    kind,
                    origin=FlagOrigin.TEXT_AND_PIPELINE,
                    stage="selection",
                    severity=FlagSeverity.INFO,
                    disposition=FlagDisposition.HANDLED,
                    title=title,
                    observation=f"This passage {what}.",
                    why_it_matters=why,
                    action_taken=action,
                    refs=refs,
                    measurement="pattern_match",
                )
            )
        else:
            e = sel.ledger.get(target)
            note = (
                " The pipeline tried to include it, but the evidence budget was full."
                if e and e.fate == CandidateFate.OMITTED_BUDGET
                else ("" if enabled else " This pipeline doesn't follow up on this automatically.")
            )
            flags.append(
                out.flag(
                    kind,
                    origin=FlagOrigin.TEXT_AND_PIPELINE,
                    stage="selection",
                    severity=FlagSeverity.CAUTION,
                    disposition=FlagDisposition.NEEDS_REVIEW,
                    title=title,
                    observation=f"This passage {what}, which was not included.{note}",
                    why_it_matters=why,
                    what_to_check="Whether the missing text changes what this passage means for the answer.",
                    refs=refs,
                    measurement="pattern_match",
                )
            )
    open_ = sum(1 for f in flags if f.disposition == FlagDisposition.NEEDS_REVIEW)
    from wittgenstein.core.enums import CheckOutcome

    outcome = CheckOutcome.FLAGGED if open_ else CheckOutcome.PASSED
    out.check(
        kind,
        label,
        outcome,
        f"{len(flags)} found; {len(flags) - open_} handled automatically, {open_} open.",
        flags,
    )
