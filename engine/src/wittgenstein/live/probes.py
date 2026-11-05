"""Embedding-awareness probes D1-D6 (docs/live-pipeline-plan.md §4).

Each probe measures one way the pipeline's search can diverge from what the user asked,
on this query, with this model, and records a check (passed / flagged / not applicable)
either way. Thresholds are relative to the model's own measured behavior
(live/characterize.py) or to this query's own score distribution -- never a universal
constant presented as a fact about embeddings.

Probes about the *pipeline's* behavior use the pipeline's own ranking; the checker's
instruments (live/coverage.py) only supply the comparison (e.g. what keyword search
would have found for a semantic-only pipeline). Dispositions here are provisional:
after selection, live/runner.py marks flags whose passages made it into the context
anyway as handled.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

import numpy as np

from wittgenstein.core.enums import (
    CheckOutcome,
    ConstraintKind,
    FlagDisposition,
    FlagKind,
    FlagOrigin,
    FlagSeverity,
)
from wittgenstein.live import phrases as P
from wittgenstein.live.characterize import EmbedderProfile, edit_sentence
from wittgenstein.live.corpus import Unit
from wittgenstein.live.coverage import Instruments
from wittgenstein.live.embedding import Embedder
from wittgenstein.live.flags import AwarenessFlag, FlagCollector, SourceRef
from wittgenstein.live.pipelines import PipelineSpec
from wittgenstein.live.retrieve import Candidate, RetrievalResult

#: A constraint whose removal moves the query vector less than this fraction of what
#: removing an ordinary content word moves it (this model's own measured median) is
#: "barely registered".
LOW_SENSITIVITY_RATIO = 0.5
MAX_LISTED = 3
#: "The document may not contain the answer" needs at least this share of the
#: question's key terms to be absent from the whole document.
ABSENT_TERM_SHARE = 0.5
_NO_DENSE = "This pipeline doesn't use meaning-based (embedding) search."
_NO_ACCESS = "Needs access to the pipeline's embedding model (pass embed_url) to measure."


def ref(unit: Unit, start: int | None = None, end: int | None = None, max_chars: int = 280) -> SourceRef:
    """A SourceRef for a whole unit, or a span inside it (offsets relative to unit text)."""
    s = 0 if start is None else start
    e = len(unit.text) if end is None else end
    quote = unit.text[s:e]
    if len(quote) > max_chars:
        quote = quote[: max_chars - 1].rstrip() + "…"
    return SourceRef(
        unit_id=unit.unit_id,
        document_id=unit.document_id,
        char_start=unit.char_start + s,
        char_end=unit.char_start + e,
        quote=quote,
    )


def _ablate(query: str, kind: ConstraintKind, start: int, end: int) -> str | None:
    if kind in {ConstraintKind.NEGATION, ConstraintKind.COMPARATOR}:
        return re.sub(r"\s{2,}", " ", (query[:start] + query[end:])).strip()
    if kind == ConstraintKind.IDENTIFIER:
        edited = edit_sentence(query[start:end], ConstraintKind.IDENTIFIER.value)
    elif kind in {ConstraintKind.NUMBER, ConstraintKind.DATE}:
        edited = edit_sentence(query[start:end], ConstraintKind.NUMBER.value)
    else:
        return None
    return None if edited is None else query[:start] + edited + query[end:]


@dataclass
class _Ctx:
    spec: PipelineSpec
    retrieval: RetrievalResult
    inst: Instruments
    embedder: Embedder | None
    profile: EmbedderProfile | None
    out: FlagCollector
    scope: str = "document"
    """"document" when the whole source is available; "retrieved passages" when only an
    external pipeline's candidates are."""

    def no_dense_reason(self) -> str:
        return _NO_ACCESS if self.spec.uses_dense else _NO_DENSE

    @property
    def k(self) -> int:
        return self.spec.k

    @property
    def top(self) -> list[Candidate]:
        """The pipeline's own top k, in its own order."""
        return self.retrieval.pool[: self.k]

    weak: bool = False
    """Set by the answerability check; later passage-level checks skip when the document
    may not cover the question at all."""

    def pipe_score(self, c: Candidate) -> float:
        if self.spec.uses_dense and not self.spec.uses_lexical:
            return c.dense_z or 0.0
        if self.spec.uses_lexical and not self.spec.uses_dense:
            return c.lexical_z or 0.0
        return c.relevance_z

    def check(
        self, kind: FlagKind, label: str, flags: list[AwarenessFlag] | None, detail: str, na: bool = False
    ) -> None:
        outcome = CheckOutcome.NOT_APPLICABLE if na else (CheckOutcome.FLAGGED if flags else CheckOutcome.PASSED)
        self.out.check(kind, label, outcome, detail, flags)


def _d1_facets(c: _Ctx) -> None:
    label = "Every part of the question searched"
    a = c.inst.analysis
    if not a.is_multi_facet:
        c.check(FlagKind.FACET_DOMINANCE, label, None, "The question has one part.", na=True)
        return
    if c.weak:
        c.check(
            FlagKind.FACET_DOMINANCE, label, None, "Skipped: the document may not cover this question.", na=True
        )
        return
    raised = []
    top_ids = [x.unit_id for x in c.top]
    for f in a.facets:
        if any(c.inst.facet_coverage(uid, f.facet_id).covered for uid in top_ids):
            continue
        best = [uid for uid in c.inst.facet_best(f.facet_id) if c.inst.facet_coverage(uid, f.facet_id).covered]
        if not best:
            continue  # nothing matches this part even on its own: the answerability check's job
        b = c.inst.units.by_id[best[0]]
        cand = c.retrieval.by_id.get(b.unit_id)
        where = f"ranks #{cand.fused_rank}" if cand else "isn't among the candidates at all"
        handled = c.spec.facet_queries
        raised.append(
            c.out.flag(
                FlagKind.FACET_DOMINANCE,
                origin=FlagOrigin.PIPELINE,
                stage="retrieval",
                severity=FlagSeverity.CAUTION,
                disposition=FlagDisposition.HANDLED if handled else FlagDisposition.NEEDS_REVIEW,
                title=f"The search leaned away from “{f.span.text}”",
                observation=(
                    f"None of the top {c.k} results cover “{f.span.text}”. Searched on its own it has a clear "
                    f"match, which the whole-question search {where}."
                ),
                why_it_matters="A question with several parts is searched as one; one part can dominate and push "
                "the evidence for another out of view.",
                action_taken=f"Searched “{f.span.text}” separately and added its best matches to the candidates."
                if handled
                else None,
                what_to_check=None if handled else f"Whether the answer addresses “{f.span.text}” at all.",
                refs=[ref(b)],
                query_span=f.span,
                metrics={"facet_id": f.facet_id, "rank": cand.fused_rank if cand else None, "k": c.k},
                measurement="measured",
            )
        )
    c.check(
        FlagKind.FACET_DOMINANCE,
        label,
        raised,
        f"{len(a.facets)} parts; {len(raised)} not represented in the top {c.k}.",
    )


def _d2_constraints(c: _Ctx) -> None:
    label = "Exact conditions in the question registered"
    a = c.inst.analysis
    kinds = {
        ConstraintKind.NEGATION,
        ConstraintKind.NUMBER,
        ConstraintKind.IDENTIFIER,
        ConstraintKind.DATE,
        ConstraintKind.COMPARATOR,
    }
    constraints = [x for x in a.constraints if x.kind in kinds]
    den = c.retrieval.dense
    if not constraints:
        c.check(
            FlagKind.CONSTRAINT_INSENSITIVE,
            label,
            None,
            "No negation, number, date, identifier or comparison in the question.",
            na=True,
        )
        return
    if not c.spec.uses_dense or den is None or c.embedder is None or c.retrieval.query_vector is None:
        c.check(FlagKind.CONSTRAINT_INSENSITIVE, label, None, c.no_dense_reason(), na=True)
        return
    units = c.inst.units
    n = len(units.units)
    content = c.profile.edit_shift_baselines.get("content_word") if c.profile else None
    top = set(den.ranking[: c.k])
    raised, details = [], []
    for x in constraints:
        ablated = _ablate(a.query, x.kind, x.span.start, x.span.end)
        if not ablated or ablated == a.query:
            continue
        av = c.embedder.embed([ablated])[0]
        shift = float(1.0 - float(c.retrieval.query_vector @ av))
        changed = len(top - set(np.argsort(-(units.vectors(c.embedder) @ av), kind="stable")[: c.k].tolist()))
        ratio = shift / content.p50 if content and content.p50 > 0 else None
        details.append(
            f"“{x.span.text}”: {changed}/{c.k} top results change"
            + (f", shift {ratio:.0%} of an ordinary word" if ratio is not None else "")
        )
        # Ranking change alone is weak evidence when k is a large share of the corpus,
        # so the measured vector shift is required too whenever a baseline exists.
        if ratio is not None:
            blind = ratio < LOW_SENSITIVITY_RATIO and changed <= max(1, c.k // 5)
        else:
            blind = changed == 0 and n >= 5 * c.k
        if not blind:
            continue
        removed = x.kind in {ConstraintKind.NEGATION, ConstraintKind.COMPARATOR}
        raised.append(
            c.out.flag(
                FlagKind.CONSTRAINT_INSENSITIVE,
                origin=FlagOrigin.PIPELINE,
                stage="embedding",
                severity=FlagSeverity.CAUTION if x.kind == ConstraintKind.NEGATION else FlagSeverity.INFO,
                disposition=FlagDisposition.INFORMATIONAL,
                title=f"The meaning-based search barely registers “{x.span.text}”",
                observation=(
                    f"We re-ran the search with “{x.span.text}” {'removed' if removed else 'changed'}: "
                    f"{changed} of the top {c.k} results changed"
                    + (
                        f", and the question's vector moved only {ratio:.0%} as much as dropping an ordinary word "
                        "moves it for this model."
                        if ratio is not None
                        else "."
                    )
                ),
                why_it_matters="Passages are ranked almost as if this condition weren't in the question, so ones "
                "that meet it and ones that don't can rank the same.",
                what_to_check=f"That the cited passages actually satisfy “{x.span.text}”.",
                query_span=x.span,
                metrics={
                    "constraint_kind": x.kind.value,
                    "vector_shift": round(shift, 5),
                    "shift_vs_ordinary_word": None if ratio is None else round(ratio, 3),
                    "top_k_changed": changed,
                    "k": c.k,
                    "ablated_query": ablated,
                },
                measurement="measured",
            )
        )
    c.check(FlagKind.CONSTRAINT_INSENSITIVE, label, raised, "; ".join(details) or "Nothing probe-able.")


def _d3_truncation(c: _Ctx) -> None:
    label = "Long passages fully read by the model"
    w = c.profile.window if c.profile else None
    window = w.effective_window_tokens if w and w.status == "saturated" else None
    if not c.spec.uses_dense or c.embedder is None:
        c.check(FlagKind.EMBEDDER_TRUNCATION, label, None, c.no_dense_reason(), na=True)
        return
    if window is None:
        c.check(
            FlagKind.EMBEDDER_TRUNCATION,
            label,
            None,
            "No input limit was observed for this model on this document.",
            na=True,
        )
        return
    units = c.inst.units
    rare = c.inst.rare_terms() or c.inst.analysis.content_terms
    raised, long_count = [], 0
    for cand in c.retrieval.pool[: max(3 * c.k, 20)]:
        u = units.by_id[cand.unit_id]
        total = c.embedder.count_tokens(u.index_text)
        if total <= window:
            continue
        long_count += 1
        low = P.lower(u.text)
        hits = [m.start() for t in rare for m in P.boundary_pattern(t).finditer(low)]
        if not hits:
            continue
        first_tok = min(c.embedder.count_tokens(u.text[:h]) for h in hits)
        if first_tok < window:
            continue
        raised.append(
            c.out.flag(
                FlagKind.EMBEDDER_TRUNCATION,
                origin=FlagOrigin.PIPELINE,
                stage="embedding",
                severity=FlagSeverity.WARNING,
                disposition=FlagDisposition.NEEDS_REVIEW,
                title="The matching part of a passage was cut off before the model read it",
                observation=f"This passage is {total} tokens; the model reads about {window} (measured). Your "
                f"question's terms first appear at token {first_tok}.",
                why_it_matters="The meaning-based search never saw the part of this passage that matches your "
                "question, so its rank reflects only the beginning.",
                what_to_check="Whether the later part of this passage answers the question.",
                refs=[ref(u)],
                metrics={"passage_tokens": total, "window_tokens": window, "first_match_token": first_tok},
                measurement="measured",
            )
        )
    c.check(
        FlagKind.EMBEDDER_TRUNCATION,
        label,
        raised,
        f"{long_count} candidate passages exceed the model's measured ~{window}-token window; "
        f"{len(raised)} have their matching text past it.",
    )


def _d4_dilution(c: _Ctx) -> None:
    """Sentence-level comparison: a sentence outside the pipeline's top k is flagged only
    when it matches the question better than the best sentence of most passages the
    pipeline did use -- sentences compared with sentences, never with passage scores."""
    label = "Relevant sentences not buried in long passages"
    den, qv, emb = c.retrieval.dense, c.retrieval.query_vector, c.embedder
    if not c.spec.uses_dense or den is None or qv is None or emb is None:
        c.check(FlagKind.DILUTION, label, None, c.no_dense_reason(), na=True)
        return
    if c.weak:
        c.check(FlagKind.DILUTION, label, None, "Skipped: the document may not cover this question.", na=True)
        return
    units = c.inst.units
    pos = c.inst.pos

    def best_sentence(unit_id: str) -> tuple[int, float]:
        ss = units.sentence_vectors(emb, unit_id) @ qv
        if not len(ss):
            return 0, -1.0
        j = int(np.argmax(ss))
        return j, float(ss[j])

    used = [best_sentence(x.unit_id)[1] for x in c.top]
    if not used:
        c.check(FlagKind.DILUTION, label, None, "Nothing selected to compare against.", na=True)
        return
    top_ids = {x.unit_id for x in c.top}
    raised = []
    for i in den.ranking[: max(6 * c.k, 40)]:
        u = units.units[i]
        if u.unit_id in top_ids or len(u.sentences) < 3:
            continue
        j, sim = best_sentence(u.unit_id)
        beats = sum(1 for x in used if sim > x)
        if beats < max(1, (len(used) + 1) // 2):
            continue
        _, s0, s1 = u.sentences[j]
        raised.append(
            c.out.flag(
                FlagKind.DILUTION,
                origin=FlagOrigin.PIPELINE,
                stage="embedding",
                severity=FlagSeverity.CAUTION,
                disposition=FlagDisposition.NEEDS_REVIEW,
                title="A strongly matching sentence is buried in a long passage",
                observation=f"This sentence matches your question better than the best sentence in {beats} of the "
                f"{len(used)} passages used, but its passage as a whole ranks #{den.rank_of(pos[u.unit_id])}.",
                why_it_matters="A passage's vector averages all its sentences, so one relevant sentence among "
                "many can be ranked out of view.",
                what_to_check="Whether this sentence changes the answer.",
                refs=[ref(u, s0, s1)],
                metrics={"sentence_similarity": round(sim, 4), "beats_used_passages": beats, "used": len(used)},
                measurement="measured",
            )
        )
        if len(raised) >= MAX_LISTED:
            break
    c.check(
        FlagKind.DILUTION,
        label,
        raised,
        f"{len(raised)} sentences outside the top {c.k} beat the best sentence of most passages used.",
    )


def _d5_disagreement(c: _Ctx) -> None:
    label = "Keyword and meaning searches agree"
    inst = c.inst
    if inst.dense is None:
        c.check(FlagKind.RETRIEVER_DISAGREEMENT, label, None, "No embedding model available to compare.", na=True)
        return
    if c.spec.uses_dense and c.spec.uses_lexical:
        c.check(
            FlagKind.RETRIEVER_DISAGREEMENT,
            label,
            None,
            "Both kinds of search are part of this pipeline, so neither one's blind spot applies on its own.",
        )
        return
    if c.weak:
        c.check(
            FlagKind.RETRIEVER_DISAGREEMENT,
            label,
            None,
            "Skipped: the document may not cover this question.",
            na=True,
        )
        return
    units = inst.units
    in_pool = {x.unit_id: x for x in c.retrieval.pool}
    exact_spans = [
        P.lower(x.span.text)
        for x in inst.analysis.constraints
        if x.kind in {ConstraintKind.IDENTIFIER, ConstraintKind.QUOTED}
    ]
    rare = inst.rare_terms()
    raised = []
    if c.spec.uses_dense:
        # Semantic-only: what would keyword search have caught?
        for i in inst.lexical.ranking[: c.k]:
            if inst.lexical.scores[i] <= 0:
                break
            u = units.units[i]
            cand = in_pool.get(u.unit_id)
            if cand is not None and cand.fused_rank <= 3 * c.k:
                continue
            low = inst.lower_text(i)
            terms = [t for t in rare if P.contains_phrase(low, t)]
            exact = [s for s in exact_spans if P.contains_phrase(low, s)]
            if len(terms) < 2 and not exact:
                continue
            where = f"#{cand.fused_rank}" if cand else "outside the top candidates"
            shown = exact or terms
            raised.append(
                c.out.flag(
                    FlagKind.RETRIEVER_DISAGREEMENT,
                    origin=FlagOrigin.PIPELINE,
                    stage="retrieval",
                    severity=FlagSeverity.CAUTION,
                    disposition=FlagDisposition.NEEDS_REVIEW,
                    title="Keyword search finds a passage this pipeline ranks low",
                    observation=f"It contains “{'”, “'.join(shown[:3])}” from your question. Keyword search ranks "
                    f"it #{inst.lexical.rank_of(i)}; this pipeline's meaning-based search ranks it {where}.",
                    why_it_matters="Similarity search can underweight rare exact terms such as names, codes and "
                    "defined terms.",
                    what_to_check="Whether this passage belongs in the answer.",
                    refs=[ref(u)],
                    metrics={"keyword_rank": inst.lexical.rank_of(i), "terms": shown[:3]},
                    measurement="measured",
                )
            )
    else:
        # Keyword-only: what would meaning-based search have caught? (checker's model)
        null = c.profile.null_best_z_question if c.profile else None
        bar = null.p90 if null else 3.0
        for i in inst.dense.ranking[: c.k]:
            z = inst.dense.z(i)
            if z < bar:
                break
            u = units.units[i]
            cand = in_pool.get(u.unit_id)
            if cand is not None and cand.fused_rank <= 3 * c.k:
                continue
            where = f"#{cand.fused_rank}" if cand else "not at all (it shares no words with the question)"
            raised.append(
                c.out.flag(
                    FlagKind.RETRIEVER_DISAGREEMENT,
                    origin=FlagOrigin.PIPELINE,
                    stage="retrieval",
                    severity=FlagSeverity.CAUTION,
                    disposition=FlagDisposition.NEEDS_REVIEW,
                    title="Meaning-based search finds a passage keyword search misses",
                    observation=f"It is among the closest passages in meaning ({z:.1f} SD above typical, measured "
                    f"with the checker's own model) but keyword search ranks it {where}.",
                    why_it_matters="Keyword search only finds the words you used; a passage that says the same "
                    "thing in other words can be missed entirely.",
                    what_to_check="Whether this passage belongs in the answer.",
                    refs=[ref(u)],
                    metrics={"meaning_z": round(z, 2)},
                    measurement="measured",
                )
            )
    c.check(
        FlagKind.RETRIEVER_DISAGREEMENT,
        label,
        raised,
        f"{len(raised)} strong matches from the other kind of search ranked low by this pipeline.",
    )


def _d5_near_miss(c: _Ctx) -> None:
    label = "Top matches are about what you asked, not a close relative"
    idents = [x for x in c.inst.analysis.constraints if x.kind == ConstraintKind.IDENTIFIER]
    if not idents:
        c.check(FlagKind.NEAR_MISS, label, None, "No identifiers in the question.", na=True)
        return
    units = c.inst.units
    raised: list[AwarenessFlag] = []
    seen: set[str] = set()
    # One flag per (asked, look-alike) pair, listing every top passage about the look-alike.
    groups: dict[tuple[str, str], list[tuple[Any, Any, re.Match[str]]]] = {}
    spans: dict[str, Any] = {}
    for x in idents:
        head, _, tail = x.span.text.partition(" ")
        if not tail:
            continue
        sib = re.compile(rf"\b{re.escape(head)}\s+([A-Z]{{1,4}}|\d+(?:\.\d+)*)\b")
        exact = P.boundary_pattern(P.lower(x.span.text))
        for cand in c.top:
            u = units.by_id[cand.unit_id]
            if u.unit_id in seen or exact.search(P.lower(u.index_text)):
                continue
            m = next((m for m in sib.finditer(u.text) if m.group(1) != tail.split("(")[0]), None)
            if not m:
                continue
            seen.add(u.unit_id)
            groups.setdefault((x.span.text, m.group(0)), []).append((cand, u, m))
            spans[x.span.text] = x.span
    for (asked, found), hits in groups.items():
        where = "; ".join(f"#{cand.fused_rank} ({u.location})" for cand, u, _ in hits)
        raised.append(
            c.out.flag(
                FlagKind.NEAR_MISS,
                origin=FlagOrigin.TEXT_AND_PIPELINE,
                stage="retrieval",
                severity=FlagSeverity.WARNING,
                disposition=FlagDisposition.NEEDS_REVIEW,
                title=f"A top match is about “{found}”, not “{asked}”",
                observation=f"{len(hits)} top passage{'s' if len(hits) > 1 else ''} mention “{found}” and never "
                f"“{asked}”: ranked {where}.",
                why_it_matters="Search treats closely related identifiers as near-identical, so a passage "
                "about the wrong one can look like strong evidence.",
                what_to_check=f"That the answer doesn't apply what these say about {found} to {asked}.",
                refs=[ref(u, m.start(), m.end()) for _, u, m in hits],
                query_span=spans[asked],
                metrics={"asked": asked, "found": found, "ranks": [cand.fused_rank for cand, _, _ in hits]},
                measurement="pattern_match",
            )
        )
    c.check(FlagKind.NEAR_MISS, label, raised, f"{len(raised)} top passages name a sibling identifier instead.")


def _d6_answerable(c: _Ctx) -> None:
    label = "The document covers this question"
    inst = c.inst
    if c.scope != "document":
        c.check(
            FlagKind.WEAK_BEST_MATCH,
            label,
            None,
            "Needs the full source document (pass corpus_id); only the retrieved passages were provided.",
            na=True,
        )
        return
    terms = [t for t in inst.analysis.content_terms if len(t) > 2 and not t.isdigit()]
    if not terms:
        c.check(FlagKind.WEAK_BEST_MATCH, label, None, "No key terms to look for.", na=True)
        return
    absent = [t for t in terms if not inst.units.bm25._postings.get(t)]
    share = len(absent) / len(terms)
    null = c.profile.null_best_z_question if c.profile else None
    best_z = inst.dense.z(inst.dense.ranking[0]) if inst.dense is not None else None
    semantic_at_chance = best_z is not None and null is not None and best_z < null.p90
    weak = share >= ABSENT_TERM_SHARE and (semantic_at_chance or (best_z is None and share >= 0.75))
    flags = []
    if weak:
        flags.append(
            c.out.flag(
                FlagKind.WEAK_BEST_MATCH,
                origin=FlagOrigin.TEXT,
                stage="retrieval",
                severity=FlagSeverity.WARNING,
                disposition=FlagDisposition.NEEDS_REVIEW,
                title="The document may not cover this question",
                observation=f"“{'”, “'.join(absent[:5])}” never appear anywhere in the document"
                + (
                    f", and the closest passage in meaning ({best_z:.1f} SD) is no closer than unrelated "
                    f"questions typically get on this document (90th percentile {null.p90:.1f} SD)."
                    if best_z is not None and null is not None
                    else "."
                ),
                why_it_matters="Any answer may be assembled from loosely related text.",
                what_to_check="Whether this document is the right source for the question.",
                metrics={
                    "absent_terms": absent,
                    "absent_share": round(share, 2),
                    "best_meaning_z": None if best_z is None else round(best_z, 2),
                    "off_topic_p90": None if null is None else round(null.p90, 2),
                },
                measurement="measured",
            )
        )
    detail = (
        f"{len(terms) - len(absent)}/{len(terms)} key terms occur in the document"
        + (f" (missing: {', '.join(absent[:4])})" if absent else "")
        + (f"; best meaning match {best_z:.1f} SD vs off-topic {null.p90:.1f} SD." if best_z and null else ".")
    )
    c.weak = weak
    c.check(FlagKind.WEAK_BEST_MATCH, label, flags, detail)


def _d6_flat(c: _Ctx) -> None:
    label = "Top results clearly ordered"
    scores = [c.pipe_score(x) for x in c.top]
    if len(scores) < 2:
        c.check(FlagKind.FLAT_TOP, label, None, "Fewer than two results.", na=True)
        return
    spread = max(scores) - min(scores)
    flags = []
    if spread < 0.25:
        flags.append(
            c.out.flag(
                FlagKind.FLAT_TOP,
                origin=FlagOrigin.PIPELINE,
                stage="retrieval",
                severity=FlagSeverity.INFO,
                disposition=FlagDisposition.INFORMATIONAL,
                title="The top matches are practically tied",
                observation=f"This pipeline's top {c.k} are within {spread:.2f} SD of each other.",
                why_it_matters="Their order carries little information, so which ones make the cut is close to "
                "arbitrary.",
                metrics={"spread_z": round(spread, 3), "k": c.k},
                measurement="measured",
            )
        )
    c.check(FlagKind.FLAT_TOP, label, flags, f"Top {c.k} span {spread:.2f} SD.")


def run_probes(
    spec: PipelineSpec,
    retrieval: RetrievalResult,
    inst: Instruments,
    embedder: Embedder | None,
    profile: EmbedderProfile | None,
    out: FlagCollector,
    scope: str = "document",
) -> None:
    """`embedder` is the pipeline's own embedding model (None for keyword-only);
    `profile` is the characterization of whichever model the instruments use."""
    c = _Ctx(spec, retrieval, inst, embedder, profile, out, scope)
    _d6_answerable(c)
    _d1_facets(c)
    _d2_constraints(c)
    _d3_truncation(c)
    _d4_dilution(c)
    _d5_disagreement(c)
    _d5_near_miss(c)
    _d6_flat(c)
