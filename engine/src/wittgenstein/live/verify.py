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
from wittgenstein.live.claims import abstains, drug_names, reconstruct, referent_conflict
from wittgenstein.live.corpus import Unit, UnitSet
from wittgenstein.live.flags import AwarenessFlag, FlagCollector
from wittgenstein.live.generate import ContextPassage
from wittgenstein.live.probes import ref
from wittgenstein.live.quantities import (
    canonical,
    checkable,
    compare_focused,
    compare_frequency,
    present,
    quantities,
)
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
#: A section number used as a citation ("[7.3]"): the model cited the document's own
#: numbering instead of the passage list (seen with a small open model).
_SECTION_CITE = re.compile(r"\[(\d+\.\d+(?:\.\d+)*)\]")
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
    checked_as: str | None = None
    """The claim actually checked, when the sentence alone isn't one ("Yes." -> the
    question's statement, affirmed); see live/claims.py."""


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


_QUESTION_TERM_STOP = {
    "what", "which", "when", "where", "whom", "whose", "should", "could", "would", "does", "patient", "patients",
    "there", "their", "about", "with", "from", "that", "this", "have", "after", "before", "than", "into",
    "being", "used", "recommended", "much", "many", "long", "often", "need", "needs", "make",
}  # fmt: skip


def _question_terms(question: str) -> list[str]:
    toks = [t for t in tokenize(question) if len(t) >= 4 and not t.isdigit() and t not in _QUESTION_TERM_STOP]
    return list(dict.fromkeys(toks))


def _term_in(low: str, term: str) -> bool:
    if P.contains_word_prefix(low, term) or P.contains_word_prefix(low, term[:-1] if len(term) > 5 else term):
        return True
    return any(P.contains_word_prefix(low, alt) for alt in P.CLINICAL_SYNONYMS.get(term, ()))


def _covering(terms: list[str], units: list[Unit]) -> tuple[Unit, str, int, int, list[str]] | None:
    """The source sentence that covers the most of the question's terms, if it covers
    at least two and at least half of them."""
    if len(terms) < 2:
        return None
    best: tuple[Unit, str, int, int, list[str]] | None = None
    for u in units:
        for s, s0, s1 in u.sentences:
            low = P.lower(s)
            hit = [t for t in terms if _term_in(low, t)]
            if best is None or len(hit) > len(best[4]):
                best = (u, s, s0, s1, hit)
    if best is None or len(best[4]) < max(2, -(-2 * len(terms) // 3)):
        return None
    return best


def _abstained_object(sentence: str) -> str:
    from wittgenstein.live.claims import _ABSTAIN

    m = _ABSTAIN.search(sentence)
    return sentence[m.end() :] if m else ""


def _doc_name(document_id: str) -> str:
    return " ".join(re.sub(r"[-_]+", " ", document_id.lower()).split())


def _asked_documents(question: str, doc_names: set[str]) -> set[str]:
    """Documents the question names ("... of atorvastatin ..." -> the atorvastatin label),
    when the corpus's document names are words a question would use."""
    low = P.lower(question)
    return {d for d in doc_names if len(_doc_name(d)) >= 4 and P.contains_phrase(low, _doc_name(d))}


def _quantity_referents(claim: str, pool: list[Unit]) -> list[tuple[str, str, str, Unit, int, int]]:
    """(value text, what the source attaches it to, what the claim says, unit, span) for
    each answer value that the cited passages state *only* for a different variant
    (red-team case M1: the immediate-release maximum given as the extended-release one)."""
    out = []
    for q in quantities(claim):
        if not checkable(q) or q.unit is None:
            continue
        cq = canonical(q.value, q.unit)
        homes = []
        for u in pool:
            for s, s0, s1 in u.sentences:
                for sq in quantities(s):
                    same = sq.value == q.value and sq.unit == q.unit
                    if not same and cq is not None:
                        cs = canonical(sq.value, sq.unit)
                        same = cs is not None and cs[0] == cq[0] and abs(cs[1] - cq[1]) < 1e-6 * max(1.0, cq[1])
                    if same:
                        homes.append((u, s, s0, s1, sq.start))
        if not homes:
            continue
        conflicts = [(h, referent_conflict(claim, h[1], h[4])) for h in homes]
        if all(c is not None for _, c in conflicts):
            (u, _s, s0, s1, _), c = conflicts[0]
            assert c is not None
            out.append((q.text, c[0], c[1], u, s0, s1))
    return out


_CLAUSE_JOIN = re.compile(r",\s*(?=(?:because|since|as|and|but|which|while|so)\b)|;\s*", re.IGNORECASE)


def _clausewise_modal(text: str, best: str, pool: list[Unit]) -> tuple[str, str | None] | None:
    """Modal force compared clause by clause: a sentence that joins two source sentences
    ("... should be stopped, because ... can injure ...") is compared part by part with
    the source sentence each part restates (red-team control C4), so neither part's
    modal excuses or condemns the other."""
    parts = [c.strip() for c in _CLAUSE_JOIN.split(text) if len(c.split()) >= 4]
    if len(parts) < 2:
        return modal_mismatch(best, text)
    # Source clauses, split the same way (a clause compared with a whole sentence would
    # pick up the modals of that sentence's other clauses).
    sents = [c.strip() for u in pool for s, _, _ in u.sentences for c in _CLAUSE_JOIN.split(s) if c.strip()]
    for part in parts:
        src = max(sents, key=lambda s: _overlap(part, s), default=best)
        mm = modal_mismatch(src, part)
        if mm is not None:
            return mm
    return None


def _align_units(text: str, source: str) -> str:
    """`text` with each amount that the source states in other units rewritten the way
    the source writes it."""
    src = quantities(source)
    out, shift = text, 0
    for q in quantities(text):
        if q.range_with is not None:
            continue
        cq = canonical(q.value, q.unit)
        if cq is None:
            continue
        for sq in src:
            cs = canonical(sq.value, sq.unit)
            same = cs is not None and cs[0] == cq[0] and abs(cs[1] - cq[1]) < 1e-6 * max(1.0, cq[1])
            if sq.range_with is None and same and sq.unit != q.unit:
                a, b = q.start + shift, q.end + shift
                out = out[:a] + sq.text + out[b:]
                shift += len(sq.text) - (q.end - q.start)
                break
    return out


def verify_answer(
    answer: str,
    passages: list[ContextPassage],
    units: UnitSet,
    out: FlagCollector,
    question: str = "",
    others: list[Unit] | None = None,
) -> tuple[list[VerifiedSentence], list[AnswerClaim], list[AnswerSupportEdge]]:
    """`question` lets terse answers ("Yes.", "2,550 mg.") be checked as the claims they
    make, and keeps the patient's own values (weight, eGFR) from being read as claims
    about the source. `others` are passages that did not reach the model (retrieved but
    left out, or the rest of the document), searched when the answer says the sources
    don't cover the question."""
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
    citation_flags: list[AwarenessFlag] = []
    abstention_flags: list[AwarenessFlag] = []
    abstentions_seen = 0
    grounding_flags: list[AwarenessFlag] = []
    q_terms = _question_terms(question) if question else []
    doc_names = {p.unit.document_id for p in passages} | {u.document_id for u in others or []}
    doc_names.discard("retrieved")

    for i, (shown, cites) in enumerate(split_answer(answer)):
        sid = f"s{i + 1}"
        # Attribution phrasing ("According to the label, ...") doesn't change what is
        # claimed; it is left out of every comparison but kept in what is shown.
        text = _ATTRIBUTION.sub("", shown, count=1)
        text = text[:1].upper() + text[1:] if text else shown
        section_cites = _SECTION_CITE.findall(text)
        if section_cites:
            text = _SECTION_CITE.sub("", text).strip()
            f = out.flag(
                FlagKind.CITATION_OUT_OF_RANGE,
                origin=FlagOrigin.PIPELINE,
                stage="answer",
                severity=FlagSeverity.CAUTION,
                disposition=FlagDisposition.NEEDS_REVIEW,
                title=f"The answer cites “[{section_cites[0]}]”, a section number, not a passage",
                observation=f"“{shown[:140]}” points at the document's own section {section_cites[0]} instead of "
                "one of the numbered passages it was given.",
                why_it_matters="The citation can't be traced to the evidence the model saw.",
                what_to_check=f"Whether section {section_cites[0]} was among the passages, and whether it says "
                "this.",
                refs=[],
                metrics={"sentence_id": sid, "sections": section_cites},
                measurement="pattern_match",
            )
            citation_flags.append(f)
        recon = reconstruct(question, text) if question else None
        if recon:
            text = recon
        missing = [n for n in cites if n not in by_n]
        if missing and passages:
            f = out.flag(
                FlagKind.CITATION_OUT_OF_RANGE,
                origin=FlagOrigin.PIPELINE,
                stage="answer",
                severity=FlagSeverity.WARNING,
                disposition=FlagDisposition.NEEDS_REVIEW,
                title="The answer cites a passage that wasn't in the prompt",
                observation=f"“{shown[:140]}” cites [{', '.join(map(str, missing))}], but the prompt had passages "
                f"1–{len(passages)}.",
                why_it_matters="The citation can't be checked, and points at nothing the model saw; the "
                "statement may come from the model's memory, or the numbering is off somewhere in the pipeline.",
                what_to_check="How the pipeline numbers passages, and whether the statement is in any of them.",
                refs=[],
                metrics={"sentence_id": sid, "missing": missing, "passages": len(passages)},
                measurement="measured",
            )
            citation_flags.append(f)
        cited_units = [by_n[n] for n in cites if n in by_n]
        pool = cited_units or [p.unit for p in passages]
        # The field comparison sees amounts as the source writes them ("2 g" -> "2,000 mg").
        claim = AnswerClaim(
            claim_id=sid,
            text=_align_units(text, " ".join(u.text for u in pool)),
            extraction_method="programmatic_rule_based",
        )
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
            checked_as=recon,
        )
        results.append(vs)
        if abstains(text):
            # "The passages don't say ...": a claim about the sources. It's wrong when a
            # passage covers the question -- in the prompt (the model missed it), or only
            # elsewhere (it never reached the model: a retrieval or packing gap).
            abstentions_seen += 1
            # What the sentence says is missing ("do not mention grapefruit juice"), when it
            # names it; otherwise the question's terms.
            obj_terms = _question_terms(_abstained_object(text))
            terms = obj_terms if len(obj_terms) >= 2 else q_terms
            in_prompt = _covering(terms, [p.unit for p in passages])
            elsewhere = None if in_prompt else _covering(terms, list(others or []))
            hit = in_prompt or elsewhere
            if hit is not None:
                u, s_text, s0, s1, terms_hit = hit
                n_in = next((p.n for p in passages if p.unit.unit_id == u.unit_id), None)
                f = out.flag(
                    FlagKind.FALSE_ABSTENTION,
                    origin=FlagOrigin.PIPELINE,
                    stage="answer",
                    severity=FlagSeverity.WARNING if in_prompt else FlagSeverity.CAUTION,
                    disposition=FlagDisposition.NEEDS_REVIEW,
                    title="The answer says the sources don't cover this, but one may"
                    if in_prompt
                    else "The answer says this isn't covered; the document may cover it",
                    observation=(
                        f"Passage [{n_in}], which the model saw, says “{s_text[:220]}”."
                        if in_prompt
                        else f"A passage that didn't reach the model says “{s_text[:220]}”."
                    ),
                    why_it_matters="A false “not stated” hides an answer the source gives. "
                    + (
                        "Here the passage was in the prompt, so the model overlooked it."
                        if in_prompt
                        else "Here the passage never reached the model, so the gap is in retrieval or packing, "
                        "not in the model."
                    ),
                    what_to_check="Whether that passage answers the question.",
                    refs=[ref(u, s0, s1)],
                    metrics={"sentence_id": sid, "terms_matched": terms_hit, "in_prompt": bool(in_prompt)},
                    measurement="pattern_match",
                )
                abstention_flags.append(f)
                vs.flag_ids.append(f.flag_id)
            continue
        if text.lower().startswith(("the document", "the passages", "the provided passages")):
            continue  # another statement about the sources themselves

        # Cited the wrong passage? When the cited passage doesn't state it but another
        # passage in the prompt plainly does, the problem is the citation, not the claim.
        if (
            cited_units
            and not verbatim
            and status in _UNSUPPORTED | _RESOLVABLE
            and len(passages) > len(cited_units)
        ):
            cited_best = max((_overlap(text, s0) for u in cited_units for s0, _, _ in u.sentences), default=0.0)
            alt = max(
                (
                    (p, s, a, b)
                    for p in passages
                    if p.unit.unit_id not in {u.unit_id for u in cited_units}
                    for s, a, b in p.unit.sentences
                ),
                key=lambda t: _overlap(text, t[1]),
                default=None,
            )
            if alt is not None and _overlap(text, alt[1]) >= 0.7 and _overlap(text, alt[1]) >= cited_best + 0.25:
                p_alt = alt[0]
                f = out.flag(
                    FlagKind.CITATION_MISATTRIBUTED,
                    origin=FlagOrigin.PIPELINE,
                    stage="answer",
                    severity=FlagSeverity.CAUTION,
                    disposition=FlagDisposition.NEEDS_REVIEW,
                    title="This sentence cites the wrong passage",
                    observation=f"“{shown[:140]}” cites [{', '.join(map(str, cites))}], but it's passage "
                    f"[{p_alt.n}] that says this.",
                    why_it_matters="A reader who checks the citation finds nothing, and may distrust a correct "
                    "statement -- or trust a citation that never supported it.",
                    what_to_check=f"Passage [{p_alt.n}].",
                    refs=[ref(p_alt.unit, alt[2], alt[3])],
                    metrics={"sentence_id": sid, "cited": cites, "supported_by": p_alt.n},
                    measurement="pattern_match",
                )
                citation_flags.append(f)
                vs.flag_ids.append(f.flag_id)
                # Check the rest against the passage that actually states it.
                pool = [p_alt.unit]
                cited_units = [p_alt.unit]
                best = (p_alt.unit, alt[1], alt[2], alt[3])
                vs.best_evidence_unit, vs.best_evidence_span = p_alt.unit.unit_id, (alt[2], alt[3])
                edge, _ = link_claim_detailed(claim, [items[p_alt.n]])
                edges[-1] = edge
                status = edge.candidate_support_status
                vs.support = status.value if status else "unresolved"

        # Grounding the field comparison and the language model can both miss
        # (measured: the NLI model reads all three as *entailed*, 0.89-0.99).
        source_text = " ".join(u.text for u in pool)
        hard_issue = False
        for value, theirs, mine, u_ref, r0, r1 in _quantity_referents(text, pool):
            hard_issue = True
            f = out.flag(
                FlagKind.QUANTITY_REFERENT,
                origin=FlagOrigin.TEXT,
                stage="answer",
                severity=FlagSeverity.WARNING,
                disposition=FlagDisposition.NEEDS_REVIEW,
                title=f"“{value}” belongs to {theirs}, not {mine}",
                observation=f"The source states “{value}” for {theirs}; the answer gives it for {mine}.",
                why_it_matters="The number is real but describes something else -- a different formulation, "
                "route, phase or severity. Word and number matching can't see this.",
                what_to_check=f"The value the source gives for {mine}.",
                refs=[ref(u_ref, r0, r1)],
                metrics={"sentence_id": sid, "value": value, "source_referent": theirs, "answer_referent": mine},
                measurement="pattern_match",
            )
            grounding_flags.append(f)
            vs.flag_ids.append(f.flag_id)
        # Drugs the question names are the subject, not a claim; label passages rarely
        # repeat the drug's name ("Renal impairment patients ... should NOT receive").
        q_drugs = drug_names(question)
        unknown_drugs = sorted(drug_names(text) - drug_names(source_text) - q_drugs)
        asked = _asked_documents(question, doc_names)
        pool_docs = {u.document_id for u in pool}
        if cites and asked and not (pool_docs & asked):
            # A passage from *another* document than the one asked about (red-team case
            # P4; and a real one: atorvastatin "contraindicated in pregnancy", cited to
            # the warfarin label's contraindication).
            theirs_d = ", ".join(sorted(pool_docs)[:2])
            mine_d = ", ".join(sorted(asked)[:2])
            f = out.flag(
                FlagKind.ENTITY_NOT_IN_SOURCE,
                origin=FlagOrigin.PIPELINE,
                stage="answer",
                severity=FlagSeverity.WARNING,
                disposition=FlagDisposition.NEEDS_REVIEW,
                title=f"The cited passage is from the {theirs_d} document, not {mine_d}",
                observation=f"The question asks about {mine_d}; “{shown[:140]}” cites a passage from {theirs_d}.",
                why_it_matters="Retrieval over many documents can hand the model another document's passage; the "
                "model then states that document's dose or warning as if it applied to this one.",
                what_to_check=f"What the {mine_d} document says.",
                refs=[ref(best[0], best[2], best[3])] if best else [],
                metrics={"sentence_id": sid, "cited_documents": sorted(pool_docs), "asked": sorted(asked)},
                measurement="pattern_match",
            )
            grounding_flags.append(f)
            vs.flag_ids.append(f.flag_id)
            hard_issue = True
        if unknown_drugs and pool:
            hard_issue = True
            f = out.flag(
                FlagKind.ENTITY_NOT_IN_SOURCE,
                origin=FlagOrigin.TEXT,
                stage="answer",
                severity=FlagSeverity.WARNING,
                disposition=FlagDisposition.NEEDS_REVIEW,
                title=f"The answer names {', '.join(f'“{d}”' for d in unknown_drugs[:3])}; its source doesn't",
                observation=f"“{shown[:160]}” mentions {', '.join(unknown_drugs[:3])}, which no passage it cites "
                "names.",
                why_it_matters="A drug swapped for a similar one (erythromycin for clarithromycin) keeps every "
                "number and word around it intact, so the sentence still looks sourced.",
                what_to_check="Which drugs the source actually names.",
                refs=[ref(best[0], best[2], best[3])] if best else [],
                metrics={"sentence_id": sid, "names": unknown_drugs[:5]},
                measurement="pattern_match",
            )
            grounding_flags.append(f)
            vs.flag_ids.append(f.flag_id)
        qty_problems = compare_focused(text, best[1] if best else "", source_text, given=question)
        # A value that appears somewhere in the passages but not in the very sentence the
        # answer restates (a real case: "40 mg once daily" for "do not exceed ... 20 mg
        # once daily" -- 40 mg is elsewhere in the context).
        if best is not None and _overlap(text, best[1]) >= 0.5:
            focus_q = quantities(best[1])
            given_q = quantities(question) if question else []
            flagged_vals = {(q.value, q.unit) for q, _, _ in qty_problems}
            for q in quantities(text):
                if not checkable(q) or q.unit is None or q.range_with is not None:
                    continue
                if (q.value, q.unit) in flagged_vals or present(q, given_q) or present(q, focus_q):
                    continue
                cq = canonical(q.value, q.unit)
                rivals = [
                    fq
                    for fq in focus_q
                    if fq.unit == q.unit
                    or (cq is not None and (canonical(fq.value, fq.unit) or ("", 0.0))[0] == cq[0])
                ]
                if rivals:
                    qty_problems.append((q, "differs_from_restated", rivals[0].text))
                    flagged_vals.add((q.value, q.unit))
        freq_problems = compare_frequency(text, best[1] if best else "", source_text)
        if any(pr != "derived" for _, pr, _ in qty_problems) or freq_problems:
            hard_issue = True

        # Meaning-level judgment (live/nli.py): catches a contradiction stated in other
        # words, and recognizes a faithful paraphrase the field comparison can't match.
        contradicted = False
        entail_score = 0.0
        if not verbatim and passages:
            ranked = sorted(
                ((u, s, s0, s1) for u in pool for s, s0, s1 in u.sentences),
                key=lambda t: -_overlap(text, t[1]),
            )[:NLI_PREMISES]
            # Contradiction is judged against the sentence this one restates (the best
            # match), never against whichever other nearby sentence happens to conflict
            # with some fragment -- measured: that produced most false alarms. A sentence
            # some source sentence fully entails is never called contradicted.
            # Equal amounts in other units ("2 g" for "2,000 mg") read as different numbers
            # to the inference model; state them as the source does first (control C7).
            hyp = _align_units(text, " ".join(t[1] for t in ranked))
            # An uncited sentence is judged only against a passage sentence it clearly
            # restates: otherwise its "best match" may be about something else entirely
            # (a real false alarm: "not indicated for viral infections" read against a
            # warfarin sentence on viral diseases from blood products).
            judgeable = bool(ranked) and (bool(cites) or _overlap(text, ranked[0][1]) >= 0.5)
            judged = nli.judge([ranked[0][1]], hyp) if judgeable else None
            # Entailment may rest on a whole (short) passage: a faithful paraphrase often
            # joins two source sentences into one (red-team control C4).
            whole = [u.text for u in pool if len(u.text) <= 1500]
            premises = [t[1] for t in ranked] + whole
            entail = nli.best_entailment(premises, hyp)
            if recon and entail is not None:
                # A rebuilt claim adds the question's subject, which a passage may leave
                # implicit; it may reveal a contradiction but never hide support.
                plain = _ATTRIBUTION.sub("", shown, count=1)
                plain_v = nli.best_entailment(premises, _align_units(plain, " ".join(premises)))
                if plain_v is not None and plain_v.entailment > entail.entailment:
                    entail = plain_v
            if entail is not None:
                entail_score = entail.entailment
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
                elif e.entailment >= nli.ENTAILMENT and status in _RESOLVABLE and cites and not hard_issue:
                    # A faithful paraphrase: supported in meaning, though not word for word.
                    status = ClaimSupportCandidateStatus.DIRECT_SUPPORT_CANDIDATE
                    edge = edge.model_copy(update={"candidate_support_status": status})
                    edges[-1] = edge
                    vs.support = "entailed_paraphrase"

        stated_in: ContextPassage | None = None
        if not cites and passages and not contradicted and not hard_issue:
            # Uncited, but stated: verbatim in a passage, or fully entailed by one.
            stated_in = next((p for p in passages if norm and norm in " ".join(p.unit.text.lower().split())), None)
            if stated_in is None and entail_score >= nli.ENTAILMENT and best is not None:
                stated_in = next((p for p in passages if p.unit.unit_id == best[0].unit_id), None)
        asked_here = _asked_documents(question, doc_names) if question else set()
        if stated_in is not None and asked_here and stated_in.unit.document_id not in asked_here:
            # Stated -- but in another document than the one asked about (a real case:
            # "2,000 mg once daily with the evening meal", metformin's maximum, given as
            # atorvastatin's). Not a missing citation: the wrong subject.
            f = out.flag(
                FlagKind.ENTITY_NOT_IN_SOURCE,
                origin=FlagOrigin.PIPELINE,
                stage="answer",
                severity=FlagSeverity.WARNING,
                disposition=FlagDisposition.NEEDS_REVIEW,
                title=f"This comes from the {stated_in.unit.document_id} document, not "
                f"{', '.join(sorted(asked_here))}",
                observation=f"“{shown[:140]}” matches passage [{stated_in.n}], from {stated_in.unit.document_id}; "
                f"the question asks about {', '.join(sorted(asked_here))}.",
                why_it_matters="A true statement about another drug is a wrong answer about this one.",
                what_to_check=f"What the {', '.join(sorted(asked_here))} document says.",
                refs=[ref(best[0], best[2], best[3])] if best else [],
                metrics={
                    "sentence_id": sid,
                    "stated_in_document": stated_in.unit.document_id,
                    "asked": sorted(asked_here),
                },
                measurement="pattern_match",
            )
            grounding_flags.append(f)
            vs.flag_ids.append(f.flag_id)
            vs.support = "stated_in_other_document"
        elif stated_in is not None:
            vs.support = "stated_but_uncited"
            f = out.flag(
                FlagKind.CITATION_MISSING,
                origin=FlagOrigin.PIPELINE,
                stage="answer",
                severity=FlagSeverity.CAUTION,
                disposition=FlagDisposition.NEEDS_REVIEW,
                title="A sentence from the sources has no citation",
                observation=f"“{shown[:140]}” isn't cited, but passage [{stated_in.n}] states it.",
                why_it_matters="Without the citation a reader can't check it; the statement itself matches the "
                "source.",
                what_to_check=f"Passage [{stated_in.n}].",
                refs=[ref(best[0], best[2], best[3])] if best else [],
                metrics={"sentence_id": sid, "stated_in": stated_in.n},
                measurement="pattern_match",
            )
            citation_flags.append(f)
            vs.flag_ids.append(f.flag_id)
        elif not contradicted and (status in _UNSUPPORTED or (not cites and passages)):
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
            mm = _clausewise_modal(text, best[1], pool)
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
        # stated in the passages it cites (value and unit; equal amounts in other units
        # count; ranges as ranges). Values from the question are the patient's, not claims.
        sentence_quantities = [q for q in quantities(text) if checkable(q)]
        quantities_seen += len(sentence_quantities)
        for q, problem, found in qty_problems:
            if problem == "derived":
                f = out.flag(
                    FlagKind.DERIVED_VALUE,
                    origin=FlagOrigin.PIPELINE,
                    stage="answer",
                    severity=FlagSeverity.INFO,
                    disposition=FlagDisposition.INFORMATIONAL,
                    title=f"“{q.text}” is calculated, not quoted",
                    observation=f"The source doesn't state “{q.text}”; it matches {found}.",
                    why_it_matters="A worked-out dose is only as right as the arithmetic and the rounding.",
                    what_to_check="The calculation, and whether the result should be rounded to an available "
                    "strength.",
                    refs=[ref(best[0], best[2], best[3])] if best else [],
                    metrics={"sentence_id": sid, "value": q.value, "unit": q.unit, "calculation": found},
                    measurement="measured",
                )
                vs.flag_ids.append(f.flag_id)
                continue
            if problem == "differs_from_restated":
                title = f"“{q.text}” isn't the value in the sentence it restates"
                observation = f"The answer says “{q.text}”; the source sentence it restates says “{found}”."
            elif problem == "range_differs":
                title = f"“{q.text}” isn't the range the source gives"
                observation = f"The answer gives “{q.text}”; the source's range is “{found}”."
            elif problem == "different_unit":
                title = f"“{q.text}” isn't what the source says"
                observation = (
                    f"The answer says “{q.text}”; the cited passage has {found} — same number, different unit."
                    if found
                    else f"The answer says “{q.text}”, but the cited passage gives that number another unit."
                )
            else:
                title = f"“{q.text}” doesn't appear in the cited source"
                observation = f"The answer says “{q.text}”, but no passage it cites states that value."
            f = out.flag(
                FlagKind.QUANTITY_MISMATCH,
                origin=FlagOrigin.PIPELINE,
                stage="answer",
                severity=FlagSeverity.WARNING,
                disposition=FlagDisposition.NEEDS_REVIEW,
                title=title,
                observation=observation,
                why_it_matters="A dose, threshold or duration that isn't in the source may be misremembered, "
                "converted wrongly, or taken from somewhere else.",
                what_to_check=f"The exact value in the source, before relying on “{q.text}”.",
                refs=[ref(best[0], best[2], best[3])] if best else [],
                metrics={"sentence_id": sid, "value": q.value, "unit": q.unit, "problem": problem, "found": found},
                measurement="pattern_match",
            )
            quantity_flags.append(f)
            vs.flag_ids.append(f.flag_id)
        for fq, src_freq in freq_problems:
            f = out.flag(
                FlagKind.QUANTITY_MISMATCH,
                origin=FlagOrigin.PIPELINE,
                stage="answer",
                severity=FlagSeverity.WARNING,
                disposition=FlagDisposition.NEEDS_REVIEW,
                title=f"“{fq.text}” isn't how often the source says",
                observation=f"The answer says “{fq.text}”; the source sentence says “{src_freq[0].text}”.",
                why_it_matters="Dosing frequency changes the total daily dose.",
                what_to_check="How often the source says to give it.",
                refs=[ref(best[0], best[2], best[3])] if best else [],
                metrics={
                    "sentence_id": sid,
                    "problem": "frequency",
                    "answer": fq.text,
                    "source": src_freq[0].text,
                },
                measurement="pattern_match",
            )
            quantity_flags.append(f)
            vs.flag_ids.append(f.flag_id)

        # Who the statement applies to: population qualifiers in the source sentence
        # must survive into the answer sentence.
        if comparable and best is not None:
            src_low, ans_low = P.lower(best[1]), P.lower(text)
            cues = [c for c in P.POPULATION_CUES if P.contains_word_prefix(src_low, c)]
            specific = [c for c in cues if c not in P.GENERIC_POPULATION_CUES]
            if cues:
                populations_seen += 1
                # Keeping only a generic cue ("adults") while dropping the specific group
                # ("geriatric", "cardiac disease") still generalizes the statement.
                ans_groups = {
                    P.POPULATION_GROUPS.get(c, c) for c in P.POPULATION_CUES if P.contains_word_prefix(ans_low, c)
                }
                kept = [c for c in (specific or cues) if P.POPULATION_GROUPS.get(c, c) in ans_groups]
                if specific:
                    cues = specific
                if not kept:
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
    content = [r for r in results if r.checked_as or len(tokenize(_CITE.sub("", r.text))) >= 2]
    if passages and not content:
        f = out.flag(
            FlagKind.ANSWER_EMPTY,
            origin=FlagOrigin.PIPELINE,
            stage="answer",
            severity=FlagSeverity.WARNING,
            disposition=FlagDisposition.NEEDS_REVIEW,
            title="The answer has no content to check",
            observation=f"The model's whole answer was “{answer.strip()[:80]}”.",
            why_it_matters="A bare citation or fragment passes every sentence-level check by having no "
            "sentences; it answers nothing.",
            what_to_check="The generator's output and prompt format.",
            refs=[],
            metrics={"answer": answer.strip()[:200]},
            measurement="measured",
        )
        citation_flags.append(f)
    elif question and content and not any(abstains(r.text) for r in results):
        claims_text = " ".join(r.checked_as or r.text for r in results)
        ans_low = P.lower(claims_text)
        q_docs = _asked_documents(question, doc_names)
        a_docs = _asked_documents(claims_text, doc_names)
        covered = [t for t in q_terms if _term_in(ans_low, t)]
        off_doc = bool(q_docs and a_docs and not (q_docs & a_docs))
        if off_doc or (len(q_terms) >= 3 and len(covered) * 3 < len(q_terms)):
            missing_t = [t for t in q_terms if t not in covered]
            f = out.flag(
                FlagKind.ANSWER_OFF_QUESTION,
                origin=FlagOrigin.PIPELINE,
                stage="answer",
                severity=FlagSeverity.WARNING if off_doc else FlagSeverity.CAUTION,
                disposition=FlagDisposition.NEEDS_REVIEW,
                title=f"The answer is about {', '.join(sorted(a_docs))}; the question asks about "
                f"{', '.join(sorted(q_docs))}"
                if off_doc
                else "The answer may not address the question",
                observation=(
                    f"The question names {', '.join(sorted(q_docs))}; the answer names only "
                    f"{', '.join(sorted(a_docs))}."
                    if off_doc
                    else f"The answer doesn't mention {', '.join(f'“{t}”' for t in missing_t[:4])} from the "
                    "question."
                ),
                why_it_matters="A fluent answer to a nearby question -- another drug, another situation -- passes "
                "sentence checks, because each sentence may be true of its source.",
                what_to_check="Whether the answer answers what was asked.",
                refs=[],
                metrics={"question_terms": q_terms, "covered": covered, "off_document": off_doc},
                measurement="pattern_match",
            )
            citation_flags.append(f)
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
        FlagKind.CITATION_MISATTRIBUTED,
        "Citations point at passages the model saw, and the right ones",
        outcome(citation_flags) if n else CheckOutcome.NOT_APPLICABLE,
        f"{len(citation_flags)} citation problems in {n} sentences.",
        citation_flags,
    )
    out.check(
        FlagKind.FALSE_ABSTENTION,
        "“Not stated” is really not stated",
        outcome(abstention_flags) if abstentions_seen else CheckOutcome.NOT_APPLICABLE,
        f"{abstentions_seen} sentences say the sources don't cover something; {len(abstention_flags)} may be "
        "covered after all."
        if abstentions_seen
        else "The answer doesn't say anything is missing from the sources.",
        abstention_flags,
    )
    out.check(
        FlagKind.QUANTITY_REFERENT,
        "Numbers and drugs belong to what the answer says they do",
        outcome(grounding_flags) if n else CheckOutcome.NOT_APPLICABLE,
        f"{len(grounding_flags)} values or drug names attached to the wrong thing, or absent from the source.",
        grounding_flags,
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
