"""Answer verification: every answer sentence against the passages it cites.

- Support: the engine's conservative field-comparison linker
  (`review/claim_linking.py::link_claim_detailed`) -- a programmatic candidate status,
  never a verdict, so a sentence it cannot match is reported as "couldn't confirm",
  not "false".
- Certainty: the ported modal-strength check (live/text_artifacts.py).
- Conditions and exceptions: the ported satellite detectors. A condition or concession
  in the best-matching evidence sentence that the answer sentence drops or severs is
  flagged -- the most direct form of "the answer says more than the source".
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from wittgenstein.core.enums import (
    ClaimSupportCandidateStatus,
    FlagDisposition,
    FlagKind,
    FlagOrigin,
    FlagSeverity,
)
from wittgenstein.ingestion.parser import split_sentences
from wittgenstein.live import nli
from wittgenstein.live import phrases as P
from wittgenstein.live.corpus import UnitSet
from wittgenstein.live.flags import AwarenessFlag, FlagCollector
from wittgenstein.live.generate import ContextPassage
from wittgenstein.live.probes import ref
from wittgenstein.live.quantities import checkable, compare_focused, quantities
from wittgenstein.live.strength import find_strength, summarize
from wittgenstein.live.text_artifacts import classify_severance, modal_mismatch, modal_strength, passage_artifacts
from wittgenstein.retrieval.lexical import tokenize
from wittgenstein.review.claim_linking import link_claim_detailed
from wittgenstein.schemas.trace import AnswerClaim, AnswerSupportEdge, ContextItem

NLI_PREMISES = 3
_ATTRIBUTION = re.compile(
    r"^(?:according to|per|as (?:stated|noted|described) in|based on)\s+(?:the\s+)?"
    r"(?:label|labeling|document|source|sources|guideline|guidelines|passage|passages|text|"
    r"prescribing information)"
    r"\s*,\s*",
    re.IGNORECASE,
)
_CITE = re.compile(r"\[(\d+(?:\s*,\s*\d+)*)\]")
_UNSUPPORTED = {
    ClaimSupportCandidateStatus.NO_SUPPORT_EDGE_FOUND,
    ClaimSupportCandidateStatus.CONTRADICTION_CANDIDATE,
}
#: Linker outcomes a strong entailment judgment may resolve to "supported" (never a
#: field-level contradiction, which stays flagged).
_RESOLVABLE = {ClaimSupportCandidateStatus.NO_SUPPORT_EDGE_FOUND, ClaimSupportCandidateStatus.UNRESOLVED}
_QUALIFIED = {
    ClaimSupportCandidateStatus.PARTIAL_SUPPORT_CANDIDATE,
    ClaimSupportCandidateStatus.QUALIFICATION_REQUIRED,
    ClaimSupportCandidateStatus.CONFLICT_CANDIDATE,
}


@dataclass
class VerifiedSentence:
    sentence_id: str
    text: str
    cited: list[int]
    cited_unit_ids: list[str]
    support: str
    best_evidence_unit: str | None
    best_evidence_span: tuple[int, int] | None
    flag_ids: list[str] = field(default_factory=list)
    strength: str | None = None
    """Recommendation strength stated in the cited evidence, if any (e.g. "Class IIb ...")."""


def _overlap(a: str, b: str) -> float:
    ta, tb = set(tokenize(a)), set(tokenize(b))
    return len(ta & tb) / len(ta) if ta else 0.0


def _cite_chunks(answer: str) -> list[str]:
    """The answer cut right after each citation marker ("[3]", "[1, 2]"). Other square
    brackets in quoted text ("deep venous thrombosis [DVT]") are not cut points."""
    chunks, last = [], 0
    for m in _CITE.finditer(answer):
        chunks.append(answer[last : m.end()])
        last = m.end()
    chunks.append(answer[last:])
    return [c for c in chunks if c.strip()]


def split_answer(answer: str) -> list[tuple[str, list[int]]]:
    """Sentences with their citations. The text is first cut after each citation marker
    ("... for him. [1] To complete ..." -- a sentence splitter alone misses that
    boundary, because the marker sits between the full stop and the next capital);
    every sentence in a cut chunk shares that chunk's citations."""
    out = []
    for chunk in _cite_chunks(answer):
        cites = sorted({int(n) for m in _CITE.finditer(chunk) for n in m.group(1).split(",")})
        for s, _, _ in split_sentences(_CITE.sub("", chunk)):
            clean = s.strip()
            if clean:
                out.append((clean, cites))
    # A trailing citation split off as its own "sentence" belongs to the previous one.
    merged: list[tuple[str, list[int]]] = []
    for text, cites in out:
        if merged and len(text) <= 3:
            merged[-1] = (merged[-1][0], sorted(set(merged[-1][1]) | set(cites)))
        else:
            merged.append((text, cites))
    return merged


def verify_answer(
    answer: str,
    passages: list[ContextPassage],
    units: UnitSet,
    out: FlagCollector,
) -> tuple[list[VerifiedSentence], list[AnswerClaim], list[AnswerSupportEdge]]:
    by_n = {p.n: p.unit for p in passages}
    items = {
        p.n: ContextItem(
            item_id=p.unit.unit_id,
            source_document_id=p.unit.document_id,
            segment_id=p.unit.segment_ids[0],
            excerpt=p.unit.text,
            rank=p.n,
            token_count=p.unit.token_count,
        )
        for p in passages
    }
    artifacts = {p.unit.unit_id: passage_artifacts(p.unit) for p in passages}
    results: list[VerifiedSentence] = []
    claims: list[AnswerClaim] = []
    edges: list[AnswerSupportEdge] = []
    unsupported: list[AwarenessFlag] = []
    modal_flags: list[AwarenessFlag] = []
    satellite_flags: list[AwarenessFlag] = []
    satellites_seen = 0
    quantity_flags: list[AwarenessFlag] = []
    population_flags: list[AwarenessFlag] = []
    quantities_seen = 0
    populations_seen = 0
    strength_flags: list[AwarenessFlag] = []
    strengths_seen = 0
    contradiction_flags: list[AwarenessFlag] = []
    nli_seen = 0

    for i, (shown, cites) in enumerate(split_answer(answer)):
        sid = f"s{i + 1}"
        # Attribution phrasing ("According to the label, ...") doesn't change what is
        # claimed; it is left out of every comparison but kept in what is shown.
        text = _ATTRIBUTION.sub("", shown, count=1)
        text = text[:1].upper() + text[1:] if text else shown
        cited_units = [by_n[n] for n in cites if n in by_n]
        pool = cited_units or [p.unit for p in passages]
        claim = AnswerClaim(claim_id=sid, text=text, extraction_method="programmatic_rule_based")
        edge, _ = link_claim_detailed(claim, [items[n] for n in cites if n in items] or list(items.values()))
        claims.append(claim)
        edges.append(edge)
        status = edge.candidate_support_status
        norm = " ".join(text.lower().split())
        verbatim = any(norm and norm in " ".join(u.text.lower().split()) for u in cited_units)
        if verbatim:
            # An exact quotation of the passage it cites is stated there by construction;
            # the linker may still pair it with a *different* sentence of that passage.
            status = ClaimSupportCandidateStatus.DIRECT_SUPPORT_CANDIDATE
            edge = edge.model_copy(update={"candidate_support_status": status})
            edges[-1] = edge  # the trace records the upgraded status, not the linker's
        # The evidence sentence this answer sentence most resembles (word overlap).
        best = max(
            ((u, s, s0, s1) for u in pool for s, s0, s1 in u.sentences),
            key=lambda t: _overlap(text, t[1]),
            default=None,
        )
        vs = VerifiedSentence(
            sentence_id=sid,
            text=shown,
            cited=cites,
            cited_unit_ids=[u.unit_id for u in cited_units],
            support="verbatim_quote" if verbatim else (status.value if status else "unresolved"),
            best_evidence_unit=best[0].unit_id if best else None,
            best_evidence_span=(best[2], best[3]) if best else None,
        )
        results.append(vs)
        if text.lower().startswith(("the document", "the passages", "the provided passages")):
            continue  # a statement about the sources themselves ("the passages don't say ...")

        # Meaning-level judgment (live/nli.py): catches a contradiction stated in other
        # words, and recognizes a faithful paraphrase the field comparison can't match.
        contradicted = False
        if not verbatim and passages:
            ranked = sorted(
                ((u, s, s0, s1) for u in pool for s, s0, s1 in u.sentences),
                key=lambda t: -_overlap(text, t[1]),
            )[:NLI_PREMISES]
            # Contradiction is judged against the sentence this one restates (the best
            # match), never against whichever other nearby sentence happens to conflict
            # with some fragment -- measured: that produced most false alarms. A sentence
            # some source sentence fully entails is never called contradicted.
            judged = nli.judge([ranked[0][1]], text) if ranked else None
            entail = nli.best_entailment([t[1] for t in ranked], text)
            if judged is not None and entail is not None:
                nli_seen += 1
                c, _ = judged
                e = entail
                if c.contradiction >= nli.POSSIBLE_CONTRADICTION and e.entailment < nli.ENTAILMENT:
                    contradicted = True
                    src_sent = next((t for t in ranked if t[1] == c.premise), ranked[0])
                    strong = c.contradiction >= nli.CONTRADICTION
                    f = out.flag(
                        FlagKind.ANSWER_CONTRADICTS_SOURCE,
                        origin=FlagOrigin.PIPELINE,
                        stage="answer",
                        severity=FlagSeverity.WARNING if strong else FlagSeverity.CAUTION,
                        disposition=FlagDisposition.NEEDS_REVIEW,
                        title="The answer may say the opposite of its source"
                        if strong
                        else "The answer may conflict with its source",
                        observation=f"The source says “{c.premise[:200]}”; the answer says "
                        f"“{c.hypothesis[:200]}”. A language-inference model reads these as contradictory "
                        f"(probability {c.contradiction:.2f}).",
                        why_it_matters="A contradiction in different words passes word-matching checks; the "
                        "answer may reverse what the source allows or requires.",
                        what_to_check="Whether the source permits what the answer says.",
                        refs=[ref(src_sent[0], src_sent[2], src_sent[3])],
                        metrics={
                            "sentence_id": sid,
                            "contradiction": round(c.contradiction, 3),
                            "entailment": round(e.entailment, 3),
                            "model": nli.REPO,
                        },
                        measurement="model_judgment",
                    )
                    contradiction_flags.append(f)
                    vs.flag_ids.append(f.flag_id)
                elif e.entailment >= nli.ENTAILMENT and status in _RESOLVABLE and cites:
                    # A faithful paraphrase: supported in meaning, though not word for word.
                    status = ClaimSupportCandidateStatus.DIRECT_SUPPORT_CANDIDATE
                    edge = edge.model_copy(update={"candidate_support_status": status})
                    edges[-1] = edge
                    vs.support = "entailed_paraphrase"

        if not contradicted and (status in _UNSUPPORTED or (not cites and passages)):
            f = out.flag(
                FlagKind.ANSWER_SENTENCE_UNSUPPORTED,
                origin=FlagOrigin.PIPELINE,
                stage="answer",
                severity=FlagSeverity.WARNING
                if status == ClaimSupportCandidateStatus.CONTRADICTION_CANDIDATE
                else FlagSeverity.CAUTION,
                disposition=FlagDisposition.NEEDS_REVIEW,
                title="An answer sentence couldn't be matched to its source"
                if status != ClaimSupportCandidateStatus.CONTRADICTION_CANDIDATE
                else "An answer sentence may conflict with its source",
                observation=(
                    f"“{text[:160]}” "
                    + (f"cites [{', '.join(map(str, cites))}], but " if cites else "has no citation, and ")
                    + (
                        "a value or condition in it differs from the passage."
                        if status == ClaimSupportCandidateStatus.CONTRADICTION_CANDIDATE
                        else "we couldn't find a passage that states it."
                    )
                ),
                why_it_matters="This part of the answer may come from the model rather than the document.",
                what_to_check="Whether the cited passage really says this.",
                refs=[ref(best[0], best[2], best[3])] if best else [],
                metrics={"sentence_id": sid, "support": vs.support},
                measurement="pattern_match",
            )
            unsupported.append(f)
            vs.flag_ids.append(f.flag_id)
        elif status in _QUALIFIED:
            vs.support = status.value  # shown in the UI as "partly matches", not flagged

        comparable = best is not None and status not in _UNSUPPORTED and bool(cites)
        if comparable and best is not None:
            mm = modal_mismatch(best[1], text)
            if mm is not None:
                src, ans = mm
                f = out.flag(
                    FlagKind.MODAL_STRENGTH_MISMATCH,
                    origin=FlagOrigin.TEXT,
                    stage="answer",
                    severity=FlagSeverity.CAUTION,
                    disposition=FlagDisposition.NEEDS_REVIEW,
                    title="The answer states this more (or less) firmly than the source",
                    observation=f"The source reads as {src} certainty; the answer reads as "
                    f"{ans + ' certainty' if ans else 'a plain statement of fact'}.",
                    why_it_matters="“May” becoming “must”, or a hedge disappearing, changes what the source "
                    "actually commits to.",
                    what_to_check="Whether the answer's wording matches the source's.",
                    refs=[ref(best[0], best[2], best[3])],
                    metrics={"sentence_id": sid, "source_tier": src, "answer_tier": ans},
                    measurement="pattern_match",
                )
                modal_flags.append(f)
                vs.flag_ids.append(f.flag_id)

            for art in artifacts.get(best[0].unit_id, []):
                if art.kind not in {FlagKind.CONDITION_SATELLITE, FlagKind.CONCESSION_SATELLITE} or not art.clause:
                    continue
                if art.sentence_start != best[2]:
                    continue
                satellites_seen += 1
                severance = classify_severance(art.clause, art.cue, text)
                if severance is None:
                    continue
                cond = art.kind == FlagKind.CONDITION_SATELLITE
                f = out.flag(
                    art.kind,
                    origin=FlagOrigin.TEXT,
                    stage="answer",
                    severity=FlagSeverity.WARNING,
                    disposition=FlagDisposition.NEEDS_REVIEW,
                    title="The answer may have dropped a condition"
                    if cond
                    else "The answer may have dropped an exception",
                    observation=f"The source says this holds “{art.cue} {art.clause}”; the answer "
                    + (
                        "doesn't mention that."
                        if severance == "dropped"
                        else "mentions it, but not as a condition."
                    ),
                    why_it_matters="Without it, the answer reads as applying "
                    + ("unconditionally." if cond else "without the exception the source acknowledges."),
                    what_to_check="Whether the condition applies to your situation.",
                    refs=[ref(best[0], art.sentence_start, art.sentence_end)],
                    metrics={"sentence_id": sid, "outcome": severance, "cue": art.cue},
                    measurement="pattern_match",
                )
                satellite_flags.append(f)
                vs.flag_ids.append(f.flag_id)

        # Doses, thresholds, durations: every checkable quantity in the sentence must be
        # stated in the passages it cites (value and unit).
        source_text = " ".join(u.text for u in pool)
        sentence_quantities = [q for q in quantities(text) if checkable(q)]
        quantities_seen += len(sentence_quantities)
        for q, problem, found in compare_focused(text, best[1] if best else "", source_text):
            f = out.flag(
                FlagKind.QUANTITY_MISMATCH,
                origin=FlagOrigin.PIPELINE,
                stage="answer",
                severity=FlagSeverity.WARNING,
                disposition=FlagDisposition.NEEDS_REVIEW,
                title=f"“{q.text}” isn't what the source says"
                if problem == "different_unit"
                else f"“{q.text}” doesn't appear in the cited source",
                observation=(
                    f"The answer says “{q.text}”; the cited passage has {found} — same number, different unit."
                    if problem == "different_unit" and found
                    else f"The answer says “{q.text}”, but no passage it cites states that value."
                ),
                why_it_matters="A dose, threshold or duration that isn't in the source may be misremembered, "
                "converted wrongly, or taken from somewhere else.",
                what_to_check=f"The exact value in the source, before relying on “{q.text}”.",
                refs=[ref(best[0], best[2], best[3])] if best else [],
                metrics={"sentence_id": sid, "value": q.value, "unit": q.unit, "problem": problem, "found": found},
                measurement="pattern_match",
            )
            quantity_flags.append(f)
            vs.flag_ids.append(f.flag_id)

        # Who the statement applies to: population qualifiers in the source sentence
        # must survive into the answer sentence.
        if comparable and best is not None:
            src_low, ans_low = P.lower(best[1]), P.lower(text)
            cues = [c for c in P.POPULATION_CUES if P.contains_word_prefix(src_low, c)]
            if cues:
                populations_seen += 1
                if not any(P.contains_word_prefix(ans_low, c) for c in cues):
                    f = out.flag(
                        FlagKind.POPULATION_QUALIFIER_DROPPED,
                        origin=FlagOrigin.TEXT,
                        stage="answer",
                        severity=FlagSeverity.WARNING,
                        disposition=FlagDisposition.NEEDS_REVIEW,
                        title="The answer may have dropped who this applies to",
                        observation=f"The source sentence is about {', '.join(f'“{c}”' for c in cues[:3])}; "
                        "the answer sentence doesn't say so.",
                        why_it_matters="A statement about a specific group (children, pregnancy, kidney "
                        "impairment, an age range) can read as applying to everyone.",
                        what_to_check="Whether the patient in question belongs to that group.",
                        refs=[ref(best[0], best[2], best[3])],
                        metrics={"sentence_id": sid, "cues": cues[:5]},
                        measurement="pattern_match",
                    )
                    population_flags.append(f)
                    vs.flag_ids.append(f.flag_id)

        # Recommendation strength: a weak/conditional recommendation, or one *against*,
        # must not become a plain rule (or the opposite) in the answer.
        if comparable and best is not None:
            labels = find_strength(best[1]) or find_strength(best[0].text)
            if labels:
                strengths_seen += 1
                vs.strength = summarize(labels)
                rec = next((x for x in labels if x.level != "evidence_only"), None)
                ans_low = P.lower(text)
                hedged = modal_strength(text) in {"weak", "medium"}
                negated = bool(P.find_phrases(ans_low, P.NEGATION_WORDS))
                mentions = any(
                    P.contains_phrase(ans_low, w) for w in ("weak", "conditional", "limited", "class", "grade")
                )
                overstated: str | None = None
                if rec is not None and rec.level == "against" and not negated:
                    overstated = f"The source recommends against this ({rec.text}); the answer doesn't say so."
                elif (
                    rec is not None
                    and rec.level in {"weak", "insufficient", "expert_opinion"}
                    and not (hedged or mentions)
                ):
                    overstated = (
                        f"The source rates this as a {rec.plain} ({rec.text}); the answer states it as settled."
                    )
                if overstated:
                    f = out.flag(
                        FlagKind.RECOMMENDATION_STRENGTH_DROPPED,
                        origin=FlagOrigin.TEXT,
                        stage="answer",
                        severity=FlagSeverity.WARNING if rec and rec.level == "against" else FlagSeverity.CAUTION,
                        disposition=FlagDisposition.NEEDS_REVIEW,
                        title="The answer may overstate the recommendation"
                        if not (rec and rec.level == "against")
                        else "The source recommends against this",
                        observation=overstated,
                        why_it_matters="Guidelines grade how firmly they recommend something; a weak or "
                        "conditional recommendation, or one against, read as a plain rule changes the advice.",
                        what_to_check="The recommendation's grade in the source.",
                        refs=[ref(best[0], best[2], best[3])],
                        metrics={
                            "sentence_id": sid,
                            "label": rec.text if rec else None,
                            "level": rec.level if rec else None,
                        },
                        measurement="pattern_match",
                    )
                    strength_flags.append(f)
                    vs.flag_ids.append(f.flag_id)

    from wittgenstein.core.enums import CheckOutcome

    def outcome(flags: list[AwarenessFlag]) -> CheckOutcome:
        return CheckOutcome.FLAGGED if flags else CheckOutcome.PASSED

    n = len(results)
    out.check(
        FlagKind.ANSWER_SENTENCE_UNSUPPORTED,
        "Every answer sentence traces to a source",
        outcome(unsupported) if n else CheckOutcome.NOT_APPLICABLE,
        f"{n - len(unsupported)}/{n} sentences matched to the passages they cite.",
        unsupported,
    )
    out.check(
        FlagKind.MODAL_STRENGTH_MISMATCH,
        "Certainty matches the source",
        outcome(modal_flags) if n else CheckOutcome.NOT_APPLICABLE,
        f"{len(modal_flags)} sentences state things more or less firmly than their source.",
        modal_flags,
    )
    out.check(
        FlagKind.CONDITION_SATELLITE,
        "Conditions and exceptions kept",
        outcome(satellite_flags) if satellites_seen else CheckOutcome.NOT_APPLICABLE,
        f"{satellites_seen} conditions/exceptions in the evidence used; {len(satellite_flags)} not carried into "
        "the answer."
        if satellites_seen
        else "The evidence the answer relies on contains no conditions or exceptions.",
        satellite_flags,
    )
    out.check(
        FlagKind.QUANTITY_MISMATCH,
        "Doses, numbers and units match the source",
        outcome(quantity_flags) if quantities_seen else CheckOutcome.NOT_APPLICABLE,
        f"{quantities_seen} doses/values/durations in the answer; {len(quantity_flags)} not found as stated in "
        "the cited passages."
        if quantities_seen
        else "The answer states no doses, thresholds or durations.",
        quantity_flags,
    )
    out.check(
        FlagKind.POPULATION_QUALIFIER_DROPPED,
        "Who it applies to is kept",
        outcome(population_flags) if populations_seen else CheckOutcome.NOT_APPLICABLE,
        f"{populations_seen} answer sentences rest on evidence about a specific patient group; "
        f"{len(population_flags)} don't say which group."
        if populations_seen
        else "The evidence used doesn't single out a patient group.",
        population_flags,
    )
    out.check(
        FlagKind.ANSWER_CONTRADICTS_SOURCE,
        "Answer doesn't contradict its sources (meaning-level)",
        outcome(contradiction_flags) if nli_seen else CheckOutcome.NOT_APPLICABLE,
        f"{nli_seen} sentences judged by a language-inference model; {len(contradiction_flags)} read as "
        "contradicting their source."
        if nli_seen
        else (
            f"The language-inference model is unavailable ({nli.load_error()})."
            if nli.load_error()
            else "No answer sentences needed a meaning-level check (all quoted verbatim)."
        ),
        contradiction_flags,
    )
    out.check(
        FlagKind.RECOMMENDATION_STRENGTH_DROPPED,
        "Recommendation strength carried over",
        outcome(strength_flags) if strengths_seen else CheckOutcome.NOT_APPLICABLE,
        f"{strengths_seen} answer sentences rest on graded recommendations; {len(strength_flags)} overstate them."
        if strengths_seen
        else "The evidence used carries no recommendation grades.",
        strength_flags,
    )
    return results, claims, edges
