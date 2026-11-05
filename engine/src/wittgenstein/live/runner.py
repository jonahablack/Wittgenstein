"""Runs one question across one or more pipelines and emits the event stream
(docs/live-pipeline-plan.md §7). Pipelines run concurrently; each produces a valid
`QueryTrace` and `PipelineManifest`, a decision ledger, flags, check records, and a
verified answer.
"""

from __future__ import annotations

import dataclasses
import json
import threading
import time
import uuid
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from wittgenstein.core.enums import (
    CheckOutcome,
    FlagDisposition,
    FlagKind,
    FlagOrigin,
    FlagSeverity,
    LiveEventType,
    TraceStatus,
)
from wittgenstein.live import counterfactual
from wittgenstein.live.answer_source import check_answer_sources
from wittgenstein.live.characterize import EmbedderProfile, get_profile
from wittgenstein.live.context_checks import check_context
from wittgenstein.live.corpus import LiveCorpus, UnitSet
from wittgenstein.live.coverage import Instruments
from wittgenstein.live.embedding import DEFAULT_EMBEDDER, get_embedder
from wittgenstein.live.events import Emitter, LiveEvent, UnitPoint
from wittgenstein.live.flags import FlagCollector
from wittgenstein.live.gaps import run_gaps
from wittgenstein.live.generate import ContextPassage, ExtractiveProvider, ProviderError, get_provider
from wittgenstein.live.pipelines import DEFAULT_PIPELINE, PRESETS, PipelineSpec
from wittgenstein.live.probes import run_probes
from wittgenstein.live.query import QueryAnalysis, analyze_query
from wittgenstein.live.retrieve import retrieve
from wittgenstein.live.select import select
from wittgenstein.live.verify import verify_answer
from wittgenstein.schemas.trace import ContextConflict, ContextItem, QueryTrace
from wittgenstein.trace.packer import pack_context

#: Probe flags that become "handled" when their passage ends up in the context anyway.
_RECONCILABLE = {
    FlagKind.DILUTION,
    FlagKind.FACET_DOMINANCE,
    FlagKind.RETRIEVER_DISAGREEMENT,
    FlagKind.EMBEDDER_TRUNCATION,
}


@dataclass
class Receipt:
    """The one-line process summary under the answer (plan §8.1)."""

    passages_searched: int
    candidates_considered: int
    passages_used: int
    worth_a_look: int
    handled: int
    checks_passed: int
    checks_run: int
    retrieval_ms: float
    total_ms: float


@dataclass
class PipelineOutcome:
    pipeline_id: str
    receipt: Receipt
    answer: str
    provider: dict[str, Any]
    trace: dict[str, Any]
    manifest: dict[str, Any]
    flags: list[dict[str, Any]] = field(default_factory=list)
    checks: list[dict[str, Any]] = field(default_factory=list)
    ledger: list[dict[str, Any]] = field(default_factory=list)
    sentences: list[dict[str, Any]] = field(default_factory=list)


def _points(units: UnitSet) -> list[dict[str, Any]]:
    return [
        UnitPoint(
            unit_id=u.unit_id,
            document_id=u.document_id,
            position=round(u.position, 5),
            char_start=u.char_start,
            char_end=u.char_end,
            location=u.location,
            tokens=u.token_count,
            preview=u.text[:140],
        ).model_dump()
        for u in units.units
    ]


def _context_item(units: UnitSet, uid: str, rank: int, relevance: float | None = None) -> ContextItem:
    u = units.by_id[uid]
    return ContextItem(
        item_id=uid,
        source_document_id=u.document_id,
        segment_id=u.segment_ids[0],
        excerpt=u.text,
        rank=rank,
        relevance_score=relevance,
        token_count=u.token_count,
    )


def _profile_summary(p: EmbedderProfile) -> dict[str, Any]:
    return {
        "embedder_id": p.embedder_id,
        "model_identifier": p.model_identifier,
        "family": p.family.value,
        "declared_window": p.declared_max_input_tokens,
        "measured_window": p.window.effective_window_tokens,
        "window_status": p.window.status,
        "negation_shift_vs_word": (
            round(p.edit_shift_baselines["negation"].p50 / p.edit_shift_baselines["content_word"].p50, 3)
            if "negation" in p.edit_shift_baselines and "content_word" in p.edit_shift_baselines
            else None
        ),
        "dilution_at_400_words": p.dilution_curve.get(400),
        "typical_unrelated_similarity": p.pairwise_similarity.p50 if p.pairwise_similarity else None,
        "insufficient_baselines": p.insufficient_baselines,
    }


class _Shared:
    """Per-run caches shared by pipeline threads: query analysis and field events per
    chunker, and model profiles per embedder."""

    def __init__(
        self, corpus: LiveCorpus, query: str, em: Emitter, counterfactual: bool = False, fit_context: bool = False
    ) -> None:
        self.corpus, self.query, self.em = corpus, query, em
        self.counterfactual = counterfactual
        self.fit_context = fit_context
        self._lock = threading.Lock()
        self._analysis: dict[str, QueryAnalysis] = {}
        self._fields: set[str] = set()
        self._profiles: dict[str, EmbedderProfile] = {}

    def analysis(self, units: UnitSet) -> QueryAnalysis:
        with self._lock:
            if units.chunker not in self._analysis:
                a = analyze_query(self.query, units.bm25._idf)
                self._analysis[units.chunker] = a
                if len(self._analysis) == 1:
                    self.em.emit(LiveEventType.QUERY_ANALYZED, analysis=a.model_dump(mode="json"))
            return self._analysis[units.chunker]

    def profile(self, name: str) -> EmbedderProfile:
        with self._lock:
            if name not in self._profiles:
                p = get_profile(get_embedder(name), self.corpus)
                self._profiles[name] = p
                self.em.emit(LiveEventType.MODEL_PROFILE, profile=_profile_summary(p))
            return self._profiles[name]

    def field_event(self, units: UnitSet, inst: Instruments) -> None:
        with self._lock:
            if units.chunker in self._fields:
                return
            self._fields.add(units.chunker)
        self.em.emit(
            LiveEventType.FIELD,
            chunker=units.chunker,
            units=_points(units),
            dense_z=[round(inst.dense.z(i), 2) for i in range(len(units.units))] if inst.dense else None,
            lexical_z=[round(inst.lexical.z(i), 2) for i in range(len(units.units))],
        )


def fit_to_generator(spec: PipelineSpec, sel: Any, info: Any, out: FlagCollector, trim: bool = False) -> None:
    """Give the answering model no more passages than it was measured to use reliably
    (live/generator_profile.py): trim (pipelines with fit_to_generator) or flag."""
    from wittgenstein.live import generator_profile as gp
    from wittgenstein.live.select import fit_to_capacity

    label = "The model is given no more passages than it reliably uses"
    if not info.uses_llm:
        out.check(FlagKind.CONTEXT_OVER_CAPACITY, label, CheckOutcome.NOT_APPLICABLE,
                  "The answer quotes the document; no model reads the passages.")  # fmt: skip
        return
    model = info.model_identifier or ""
    prof = gp.load(info.provider_id, model)
    if prof is None:
        out.check(
            FlagKind.CONTEXT_OVER_CAPACITY,
            label,
            CheckOutcome.NOT_APPLICABLE,
            f"Not measured for {model or info.provider_id}. Measure it with `wittgenstein measure-model "
            f"--provider {info.provider_id}` ({len(gp.probes()) * len(gp.SIZES)} generations); until then, "
            "how much context this model handles is unknown.",
        )
        return
    n, cap = len(sel.selected), prof.reliable_passages
    evidence = f"Measured on {model}: {prof.summary()}. Reliable size: {cap} passages ({prof.rule})." + (
        f" {prof.note}" if prof.note else ""
    )
    metrics = {
        "model": model,
        "reliable_passages": cap,
        "passages": n,
        "accuracy": prof.accuracy,
        "wrong_passage": prof.wrong_passage,
        "measured_at": prof.measured_at,
        "profile": str(gp.path_for(info.provider_id, model)),
    }
    if n <= cap:
        out.check(FlagKind.CONTEXT_OVER_CAPACITY, label, CheckOutcome.PASSED, f"{n} passages; {evidence}")
        return
    if spec.fit_to_generator or trim:
        removed = fit_to_capacity(
            sel,
            cap,
            f"Left out so the model gets no more than the {cap} passages it was measured to use reliably.",
        )
        f = out.flag(
            FlagKind.CONTEXT_OVER_CAPACITY,
            origin=FlagOrigin.PIPELINE,
            stage="select",
            severity=FlagSeverity.INFO,
            disposition=FlagDisposition.HANDLED,
            title=f"Context trimmed to the {cap} passages this model reliably uses",
            observation=f"{n} passages were chosen; with more than {cap}, this model was measured answering from "
            f"the wrong passage more often. {evidence}",
            why_it_matters="A small model given more text than it handles well picks the wrong passage: an answer "
            "built from a neighbouring rule, class or definition.",
            action_taken=f"Kept one passage for each part of the question, then the best-ranked, up to {cap}; "
            f"left out {len(removed)}.",
            what_to_check=None,
            refs=[],
            metrics={**metrics, "left_out": removed},
            measurement="measured",
        )
        out.check(FlagKind.CONTEXT_OVER_CAPACITY, label, CheckOutcome.PASSED,
                  f"Trimmed from {n} to {cap} passages. {evidence}", [f])  # fmt: skip
        return
    f = out.flag(
        FlagKind.CONTEXT_OVER_CAPACITY,
        origin=FlagOrigin.PIPELINE,
        stage="select",
        severity=FlagSeverity.INFO,
        disposition=FlagDisposition.INFORMATIONAL,
        title=f"More passages than this model reliably uses ({n}; measured reliable: {cap})",
        observation=evidence,
        why_it_matters="A small model given more text than it handles well picks the wrong passage: an answer "
        "built from a neighbouring rule, class or definition.",
        what_to_check=None,
        refs=[],
        metrics=metrics,
        measurement="measured",
    )
    out.check(FlagKind.CONTEXT_OVER_CAPACITY, label, CheckOutcome.FLAGGED, evidence, [f])


def run_pipeline(spec: PipelineSpec, shared: _Shared, provider_name: str) -> PipelineOutcome:
    em, corpus, pid = shared.em, shared.corpus, spec.pipeline_id
    t0 = time.perf_counter()

    def stage(name: str, started: float, **summary: Any) -> None:
        em.emit(
            LiveEventType.STAGE, pid, stage=name, ms=round((time.perf_counter() - started) * 1000, 2), **summary
        )

    units = corpus.units(spec.chunker)
    analysis = shared.analysis(units)
    embedder = get_embedder(spec.embedder) if spec.embedder else None
    inst_name = spec.embedder or DEFAULT_EMBEDDER
    profile = shared.profile(inst_name)
    inst = Instruments(units, analysis, get_embedder(inst_name), profile)
    shared.field_event(units, inst)

    ts = time.perf_counter()
    retrieval = retrieve(spec, units, analysis, embedder)
    stage("retrieve", ts, pool=len(retrieval.pool), timings=retrieval.timings_ms)
    em.emit(
        LiveEventType.CANDIDATES,
        pid,
        items=[
            {
                "unit_id": c.unit_id,
                "channels": sorted(ch.value for ch in c.channels),
                "lexical_rank": c.lexical_rank,
                "dense_rank": c.dense_rank,
                "fused_rank": c.fused_rank,
                "relevance_z": round(c.relevance_z, 3),
                "facet_hits": c.facet_hits,
            }
            for c in retrieval.pool
        ],
    )
    retrieval_ms = (time.perf_counter() - t0) * 1000

    out = FlagCollector(pid)

    def flush(start_flags: int, start_checks: int) -> None:
        for f in out.flags[start_flags:]:
            em.emit(LiveEventType.FLAG, pid, flag=f.model_dump(mode="json"))
        for c in out.checks[start_checks:]:
            em.emit(LiveEventType.CHECK, pid, check=c.model_dump(mode="json"))

    ts = time.perf_counter()
    run_probes(spec, retrieval, inst, embedder, profile, out)
    weak = any(f.kind == FlagKind.WEAK_BEST_MATCH for f in out.flags)
    flush(0, 0)
    stage("probe", ts)

    ts = time.perf_counter()
    nf, nc = len(out.flags), len(out.checks)
    sel = select(
        spec,
        retrieval,
        inst,
        list(out.flags),
        profile.pairwise_similarity.p90 if profile.pairwise_similarity else None,
    )
    provider = get_provider(provider_name, inst) if provider_name != "extractive" else ExtractiveProvider(inst)
    # "Fit context to the model" applies to the self-aware pipeline; the baselines stay as configured.
    fit_to_generator(
        spec, sel, provider.info, out, trim=shared.fit_context and spec.pipeline_id == DEFAULT_PIPELINE
    )
    for e in sel.ledger.values():
        em.emit(LiveEventType.DECISION, pid, entry=_ledger_json(e))
    run_gaps(spec, retrieval, inst, sel, out, weak)
    chosen = set(sel.selected)
    for f in out.flags[:nf]:
        if not f.refs or f.disposition == FlagDisposition.HANDLED:
            continue
        uid = f.refs[0].unit_id
        if f.kind in _RECONCILABLE and uid in chosen:
            reason = sel.ledger[uid].reason
            f.action_taken = (
                "Added this passage to the evidence used for the answer."
                if reason.startswith("Included because a check found it")
                else f"It was used anyway: {reason[0].lower()}{reason[1:]}"
            )
        elif f.kind == FlagKind.NEAR_MISS and uid not in chosen:
            f.action_taken = "Left it out of the evidence used for the answer."
        else:
            continue
        f.disposition = FlagDisposition.HANDLED
        f.what_to_check = None
        em.emit(LiveEventType.FLAG_UPDATED, pid, flag=f.model_dump(mode="json"))
    flush(nf, nc)
    stage("select", ts, selected=len(sel.selected), pulled_in=len(sel.pulled_in), stop_reason=sel.stop_reason)

    ts = time.perf_counter()
    cand_items = [_context_item(units, c.unit_id, c.fused_rank, round(c.relevance_z, 4)) for c in retrieval.pool]
    sel_items = [_context_item(units, uid, i + 1) for i, uid in enumerate(sel.selected)]
    packed = pack_context(sel_items, spec.token_budget)
    passages = [ContextPassage(i + 1, units.by_id[it.item_id]) for i, it in enumerate(packed.packed_context_items)]
    em.emit(
        LiveEventType.CONTEXT_PACKED,
        pid,
        packed=[p.unit.unit_id for p in passages],
        omitted=[it.item_id for it in packed.omitted_context_items],
        tokens=packed.final_prompt_token_count,
        budget=spec.token_budget,
    )
    nf, nc = len(out.flags), len(out.checks)
    check_context(passages, out)
    flush(nf, nc)
    stage("pack", ts)

    ts = time.perf_counter()
    parts: list[str] = []
    if weak and not provider.info.uses_llm:
        # Quoting can't decline the way a model can, so it says so before quoting.
        lead = "The document doesn't appear to cover this question; the closest passages it has are quoted below. "
        parts.append(lead)
        em.emit(LiveEventType.ANSWER_DELTA, pid, text=lead)
    try:
        for chunk in provider.stream(analysis.query, passages):
            parts.append(chunk)
            em.emit(LiveEventType.ANSWER_DELTA, pid, text=chunk)
    except ProviderError as e:
        em.emit(LiveEventType.ERROR, pid, message=f"{e} Falling back to quoting the document.")
        provider = ExtractiveProvider(inst)
        parts = []
        for chunk in provider.stream(analysis.query, passages):
            parts.append(chunk)
            em.emit(LiveEventType.ANSWER_DELTA, pid, text=chunk)
    answer = "".join(parts)
    stage("generate", ts, provider=provider.info.provider_id)

    ts = time.perf_counter()
    nf, nc = len(out.flags), len(out.checks)
    in_prompt = {p.unit.unit_id for p in passages}
    sentences, claims, edges = verify_answer(
        answer,
        passages,
        units,
        out,
        question=analysis.query,
        others=[u for u in units.units if u.unit_id not in in_prompt],
    )
    check_answer_sources(analysis.query, answer, passages, out)
    by_n = {p.n: p.unit.unit_id for p in passages}
    for s in sentences:
        em.emit(
            LiveEventType.ANSWER_SENTENCE,
            pid,
            sentence={**asdict(s), "cited_unit_ids": [by_n.get(n) for n in s.cited]},
        )
    flush(nf, nc)
    stage("verify", ts)

    if shared.counterfactual and provider.info.uses_llm:
        # Does the model answer from the passages or from memory? Change a value the
        # answer took from a passage and ask again (live/counterfactual.py).
        ts = time.perf_counter()
        nf, nc = len(out.flags), len(out.checks)
        by_unit = {p.n: p.unit for p in passages}

        def regenerate(question: str, edited: list[tuple[int, str]]) -> str:
            ps = [ContextPassage(n, dataclasses.replace(by_unit[n], text=t)) for n, t in edited]
            return "".join(provider.stream(question, ps))

        counterfactual.report(
            counterfactual.run_probes(analysis.query, [(p.n, p.unit.text) for p in passages], answer, regenerate),
            out,
        )
        # And does the answer survive fewer passages (or another order)? (live/consistency.py)
        from wittgenstein.live import consistency
        from wittgenstein.live import generator_profile as gp

        prof = gp.load(provider.info.provider_id, provider.info.model_identifier)
        cap = prof.reliable_passages if prof else 3
        by_text = {p.unit.text: p.unit for p in passages}
        note = (
            f"This model was measured answering from the wrong passage more often with more than "
            f"{prof.reliable_passages} passages; it was given {len(passages)}."
            if prof and len(passages) > prof.reliable_passages
            else ""
        )
        consistency.report(
            consistency.run_context_probe(
                analysis.query,
                [(p.n, p.unit.text) for p in passages],
                answer,
                lambda q, ps: "".join(provider.stream(q, [ContextPassage(n, by_text[t]) for n, t in ps])),
                [[t.lower() for t in f.terms] for f in analysis.facets],
                cap,
            ),
            answer,
            out,
            note,
        )
        flush(nf, nc)
        stage("probe-generator", ts)

    manifest = spec.to_manifest(corpus.corpus_id, embedder.info if embedder else None)
    trace = QueryTrace(
        trace_id=f"{pid}:{uuid.uuid4().hex[:12]}",
        manifest_id=manifest.manifest_id,
        corpus_id=corpus.corpus_id,
        query=analysis.query,
        query_timestamp=datetime.now(UTC),
        retrieval_candidates=cand_items,
        reranked_candidates=None,
        selected_context_items=sel_items,
        packed_context_items=packed.packed_context_items,
        omitted_context_items=packed.omitted_context_items,
        compressed_context_items=[],
        final_prompt=packed.final_prompt,
        final_prompt_token_count=packed.final_prompt_token_count,
        final_prompt_evidence_budget=spec.token_budget,
        prompt_token_spans=packed.prompt_token_spans,
        generation_parameters={
            "provider": provider.info.provider_id,
            "model": provider.info.model_identifier or "",
        },
        answer=answer,
        answer_claims=claims,
        answer_support_edges=edges,
        context_conflicts=[
            ContextConflict(
                conflict_id=f.flag_id,
                context_item_ids=list(f.metrics["units"]),
                dimension=f.metrics["dimension"],
                description=f.observation,
            )
            for f in out.flags
            if f.kind == FlagKind.CONTEXT_CONFLICT
        ],
        trace_status=TraceStatus.COMPLETE,
    )
    receipt = Receipt(
        passages_searched=len(units.units),
        candidates_considered=len(sel.ledger),
        passages_used=len(passages),
        worth_a_look=sum(1 for f in out.flags if f.disposition == FlagDisposition.NEEDS_REVIEW),
        handled=sum(1 for f in out.flags if f.disposition == FlagDisposition.HANDLED),
        checks_passed=sum(1 for c in out.checks if c.outcome == CheckOutcome.PASSED),
        checks_run=sum(1 for c in out.checks if c.outcome != CheckOutcome.NOT_APPLICABLE),
        retrieval_ms=round(retrieval_ms, 1),
        total_ms=round((time.perf_counter() - t0) * 1000, 1),
    )
    outcome = PipelineOutcome(
        pipeline_id=pid,
        receipt=receipt,
        answer=answer,
        provider=asdict(provider.info),
        trace=trace.model_dump(mode="json"),
        manifest=manifest.model_dump(mode="json"),
        flags=[f.model_dump(mode="json") for f in out.flags],
        checks=[c.model_dump(mode="json") for c in out.checks],
        ledger=[_ledger_json(e) for e in sel.ledger.values()],
        sentences=[asdict(s) for s in sentences],
    )
    em.emit(LiveEventType.PIPELINE_COMPLETED, pid, receipt=asdict(receipt), provider=asdict(provider.info))
    return outcome


def _ledger_json(e: Any) -> dict[str, Any]:
    d = asdict(e)
    d["fate"] = e.fate.value
    d["pull_in_reason"] = e.pull_in_reason.value if e.pull_in_reason else None
    return d


@dataclass
class RunResult:
    run_id: str
    query: str
    corpus_id: str
    outcomes: dict[str, PipelineOutcome]
    events: list[LiveEvent]


def run_query(
    corpus: LiveCorpus,
    query: str,
    pipeline_ids: list[str] | None = None,
    provider: str = "extractive",
    sink: Callable[[LiveEvent], None] | None = None,
    specs: dict[str, PipelineSpec] | None = None,
    counterfactual: bool = False,
    fit_context: bool = False,
) -> RunResult:
    specs = specs or PRESETS
    pipeline_ids = pipeline_ids or ["aware"]
    unknown = [p for p in pipeline_ids if p not in specs]
    if unknown:
        raise ValueError(f"Unknown pipeline(s): {unknown}")
    run_id = uuid.uuid4().hex[:16]
    em = Emitter(sink or (lambda _e: None))
    em.emit(
        LiveEventType.RUN_STARTED,
        run_id=run_id,
        query=query,
        corpus_id=corpus.corpus_id,
        provider=provider,
        pipelines=[
            {"pipeline_id": p, "label": specs[p].label, "description": specs[p].description} for p in pipeline_ids
        ],
    )
    shared = _Shared(corpus, query, em, counterfactual, fit_context)
    outcomes: dict[str, PipelineOutcome] = {}
    try:
        with ThreadPoolExecutor(max_workers=max(1, len(pipeline_ids))) as pool:
            futures = {p: pool.submit(run_pipeline, specs[p], shared, provider) for p in pipeline_ids}
            for p, fut in futures.items():
                outcomes[p] = fut.result()
    except Exception as e:  # surfaced on the stream, then re-raised for the caller
        em.emit(LiveEventType.ERROR, message=f"Run failed: {type(e).__name__}: {e}")
        raise
    em.emit(LiveEventType.RUN_COMPLETED, run_id=run_id)
    return RunResult(run_id, query, corpus.corpus_id, outcomes, em.events)


def save_run(result: RunResult, directory: Path) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{result.run_id}.json"
    payload = {
        "run_id": result.run_id,
        "query": result.query,
        "corpus_id": result.corpus_id,
        "outcomes": {k: asdict(v) for k, v in result.outcomes.items()},
        "events": [e.model_dump(mode="json") for e in result.events],
    }
    path.write_text(json.dumps(payload))
    return path
