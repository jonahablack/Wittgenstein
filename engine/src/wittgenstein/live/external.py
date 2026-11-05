"""Check an *external* RAG pipeline's run (docs/live-pipeline-plan.md §3.2).

An organization keeps its own retriever, chunker, embedding model and LLM. After a
query it sends what its pipeline already has -- the question, the ranked candidates,
which of them went into the prompt, and the answer -- and gets back the same checks,
flags, ledger and receipt the live pipeline produces for itself.

What can be checked depends on what is provided, and every check says so:

- **trace** (always): the candidates, context and answer as sent. Answer verification
  (support, doses/units, population qualifiers, conditions, certainty), text artifacts,
  near misses, facet coverage, redundancy and cutoff checks run on these alone.
- **+ document** (`corpus_id` of a document uploaded to this server): candidates are
  matched to the document's passages, so document-wide checks run too -- whether the
  document covers the question, what keyword or meaning search would have found that
  the pipeline didn't, severed context, unfollowed cross-references and definitions.
- **+ embeddings** (`embed_url` callback to the pipeline's own model, or an `Embedder`
  passed in from Python): the model itself is characterized and the embedding probes
  run against it (negation and constraint sensitivity, input window, dilution).
  Without it, those probes report "needs access", never a guess.

The answer is always verified against exactly the context text the caller sent, so a
caller whose chunks differ from this server's parsing is still checked on what its
model actually saw.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import asdict
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from wittgenstein.core.enums import (
    CandidateFate,
    CheckOutcome,
    FlagDisposition,
    FlagKind,
    KPolicy,
    RetrievalChannel,
)
from wittgenstein.ingestion.parser import split_sentences
from wittgenstein.live.characterize import get_profile
from wittgenstein.live.context_checks import check_context
from wittgenstein.live.corpus import STRUCTURAL, LiveCorpus, Unit, UnitSet
from wittgenstein.live.coverage import Instruments
from wittgenstein.live.embedding import DEFAULT_EMBEDDER, Embedder, get_embedder
from wittgenstein.live.flags import FlagCollector
from wittgenstein.live.gaps import run_gaps
from wittgenstein.live.generate import ContextPassage
from wittgenstein.live.pipelines import PipelineSpec, Remediation
from wittgenstein.live.probes import run_probes
from wittgenstein.live.query import analyze_query
from wittgenstein.live.retrieve import Candidate, RetrievalResult
from wittgenstein.live.select import LedgerEntry, SelectionResult
from wittgenstein.live.verify import verify_answer
from wittgenstein.trace.token_counting import default_counter

MAX_CANDIDATES = 500
MAX_CANDIDATE_CHARS = 20_000
_MATCH_MIN_CHARS = 40
_OVERLAP_MATCH = 0.6


class ExternalCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(..., min_length=1, max_length=200)
    text: str = Field(..., min_length=1, max_length=MAX_CANDIDATE_CHARS)
    score: float | None = Field(default=None, description="The retriever's own score, if any.")
    document_id: str | None = None
    location: str | None = Field(default=None, description='Human-readable place, e.g. "Section 5.1".')


class ExternalPipeline(BaseModel):
    """What the caller declares about its pipeline. Every field is optional and an
    omitted field is unknown -- never filled in with a typical value."""

    model_config = ConfigDict(extra="forbid")

    name: str | None = None
    retriever: str | None = Field(default=None, description="dense | lexical | hybrid")
    embedding_model: str | None = None
    chunking: str | None = None
    top_k: int | None = None
    token_budget: int | None = None
    llm: str | None = None


class ExternalCheckRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    query: str = Field(..., min_length=2, max_length=2000)
    candidates: list[ExternalCandidate] = Field(
        ..., min_length=1, max_length=MAX_CANDIDATES, description="What the retriever returned, best first."
    )
    context_ids: list[str] | None = Field(
        default=None,
        description="Candidate ids that went into the prompt, in prompt order. Answer citations [n] refer to "
        "this order (1-based). Defaults to all candidates in order.",
    )
    answer: str | None = Field(default=None, max_length=20_000)
    pipeline: ExternalPipeline = Field(default_factory=ExternalPipeline)
    corpus_id: str | None = Field(default=None, description="A document uploaded to this server, if any.")
    embed_url: str | None = Field(
        default=None, description='Callback to the pipeline\'s own embedding model: POST {"texts": [...]}.'
    )
    embed_headers: dict[str, str] | None = None
    generator_url: str | None = Field(
        default=None,
        description="Callback to the pipeline's own answer generator, for the counterfactual probe: "
        'POST {"question": str, "passages": [{"n": 1, "text": str}, ...]} -> {"answer": str}. '
        "Costs up to 2 extra generations.",
    )
    generator_headers: dict[str, str] | None = None

    @model_validator(mode="after")
    def _ids(self) -> ExternalCheckRequest:
        ids = [c.id for c in self.candidates]
        if len(set(ids)) != len(ids):
            raise ValueError("candidate ids must be unique")
        if self.context_ids is not None:
            unknown = [i for i in self.context_ids if i not in set(ids)]
            if unknown:
                raise ValueError(f"context_ids not among candidates: {unknown[:5]}")
        return self


def _norm(text: str) -> str:
    return " ".join(text.lower().split())


def _tokens(text: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", text.lower()))


class _CandidateSource:
    """The candidates themselves as the 'corpus' (trace-only access)."""

    def __init__(self, corpus_id: str, unit_set: UnitSet) -> None:
        self.corpus_id = corpus_id
        self._units = unit_set

    def units(self, chunker: str = STRUCTURAL) -> UnitSet:
        return self._units


def _synthetic_units(cands: list[ExternalCandidate]) -> list[Unit]:
    counter = default_counter()
    n = max(1, len(cands))
    return [
        Unit(
            unit_id=c.id,
            order=i,
            document_id=c.document_id or "retrieved",
            text=c.text,
            char_start=0,
            char_end=len(c.text),
            location=c.location or f"Candidate {c.id}",
            heading_context=None,
            segment_ids=[c.id],
            token_count=counter.count(c.text),
            position=i / n,
            sentences=split_sentences(c.text),
        )
        for i, c in enumerate(cands)
    ]


def _match(c: ExternalCandidate, units: UnitSet) -> list[str]:
    """Document units a candidate covers: exact containment either way (whitespace and
    case normalized), else the single unit sharing most of its words."""
    ct = _norm(c.text)
    covered = [
        u.unit_id
        for u in units.units
        if (len(u.text) >= _MATCH_MIN_CHARS and _norm(u.text) in ct)
        or (len(ct) >= _MATCH_MIN_CHARS and ct in _norm(u.text))
    ]
    if covered:
        return covered
    toks = _tokens(c.text)
    if not toks:
        return []
    best, share = None, 0.0
    for u in units.units:
        s = len(toks & _tokens(u.text)) / len(toks)
        if s > share:
            best, share = u.unit_id, s
    return [best] if best is not None and share >= _OVERLAP_MATCH else []


def check_external(
    req: ExternalCheckRequest,
    corpus: LiveCorpus | None = None,
    embedder: Embedder | None = None,
) -> dict[str, Any]:
    """Run every applicable check on an external pipeline's run. `corpus` and
    `embedder` widen access (see the module docstring)."""
    context_ids = req.context_ids if req.context_ids is not None else [c.id for c in req.candidates]
    by_id = {c.id: c for c in req.candidates}
    retriever = (req.pipeline.retriever or "").lower()
    channels = (
        [RetrievalChannel.LEXICAL, RetrievalChannel.DENSE]
        if retriever == "hybrid"
        else [RetrievalChannel.LEXICAL]
        if retriever in {"lexical", "bm25", "keyword"}
        else [RetrievalChannel.DENSE]
        if retriever in {"dense", "semantic", "vector"}
        else []
    )
    notes: list[str] = []
    if not channels:
        notes.append("Retriever type not declared; checks that depend on it treat it as unknown.")

    # --- units: the uploaded document, or the candidates themselves --------------------
    unmatched: list[str] = []
    cand_units: dict[str, list[str]] = {}
    if corpus is not None:
        units = corpus.units()
        for c in req.candidates:
            cand_units[c.id] = _match(c, units)
            if not cand_units[c.id]:
                unmatched.append(c.id)
        source: Any = corpus
        scope = "document"
        if unmatched:
            notes.append(
                f"{len(unmatched)} of {len(req.candidates)} candidates didn't match a passage of the document; "
                "they are checked as sent but left out of document-wide checks."
            )
    else:
        units = UnitSet("external", _synthetic_units(req.candidates))
        cand_units = {c.id: [c.id] for c in req.candidates}
        digest = hashlib.sha256("\n".join(c.text for c in req.candidates).encode()).hexdigest()[:16]
        source = _CandidateSource(f"external-{digest}", units)
        scope = "retrieved passages"

    # --- instruments: the caller's model when given, else the checker's own ------------
    inst_embedder = embedder or get_embedder(DEFAULT_EMBEDDER)
    profile = get_profile(inst_embedder, source)
    analysis = analyze_query(req.query, units.bm25._idf)
    inst = Instruments(units, analysis, inst_embedder, profile)
    if embedder is None and RetrievalChannel.DENSE in channels:
        notes.append(
            "Embedding probes need the pipeline's own model (embed_url); meaning-based comparisons use the "
            "checker's own model and are labeled as such."
        )

    # --- the caller's ranking as the candidate pool --------------------------------------
    pool: list[Candidate] = []
    seen: set[str] = set()
    for rank, c in enumerate(req.candidates, start=1):
        for uid in cand_units.get(c.id, []):
            if uid in seen:
                continue
            seen.add(uid)
            i = inst.pos[uid]
            pool.append(
                Candidate(
                    unit_id=uid,
                    channels=set(channels) or {RetrievalChannel.REMEDIATION},
                    lexical_rank=inst.lexical.rank_of(i),
                    lexical_score=float(inst.lexical.scores[i]),
                    lexical_z=inst.lexical.z(i),
                    dense_rank=inst.dense.rank_of(i) if inst.dense else None,
                    dense_sim=float(inst.dense.scores[i]) if inst.dense else None,
                    dense_z=inst.dense.z(i) if inst.dense else None,
                    fused_rank=rank,
                )
            )
    their_dense = embedder is not None and RetrievalChannel.DENSE in channels
    retrieval = RetrievalResult(
        pool=pool,
        by_id={pc.unit_id: pc for pc in pool},
        lexical=inst.lexical,
        dense=inst.dense if their_dense else None,
        query_vector=inst.query_vector if their_dense else None,
        facet_rankings={},
        timings_ms={},
    )
    selected = list(dict.fromkeys(uid for cid in context_ids for uid in cand_units.get(cid, [])))
    k = max(1, len(selected))
    spec = PipelineSpec.model_construct(
        pipeline_id="external",
        label=req.pipeline.name or "Your pipeline",
        description="An external RAG pipeline, checked from its own trace.",
        chunker=STRUCTURAL,
        channels=channels or [RetrievalChannel.DENSE],
        embedder=None,
        facet_queries=False,
        candidate_depth=len(req.candidates),
        k_policy=KPolicy.FIXED,
        k=k,
        k_min=1,
        k_max=k,
        token_budget=req.pipeline.token_budget or sum(units.by_id[u].token_count for u in selected) or 1,
        remediation=Remediation(severed_neighbor=False, cross_reference=False, definition=False),
    )

    out = FlagCollector("external")
    run_probes(spec, retrieval, inst, embedder if their_dense else None, profile, out, scope=scope)
    weak = any(f.kind == FlagKind.WEAK_BEST_MATCH for f in out.flags)

    # --- the caller's own selection as the ledger -------------------------------------------
    ledger: dict[str, LedgerEntry] = {}
    for pc in pool:
        used = pc.unit_id in selected
        ledger[pc.unit_id] = LedgerEntry(
            unit_id=pc.unit_id,
            fate=CandidateFate.SELECTED if used else CandidateFate.NOT_REACHED,
            reason="Put in the prompt by your pipeline."
            if used
            else "Retrieved by your pipeline but not put in the prompt.",
            channels=sorted(ch.value for ch in pc.channels),
            relevance_z=round(pc.relevance_z, 3),
            fused_rank=pc.fused_rank,
            facets_covered=sorted(inst.facets_covered(pc.unit_id)) if analysis.facets else [],
            tokens=units.by_id[pc.unit_id].token_count,
            order=selected.index(pc.unit_id) + 1 if used else None,
        )
    covered = {f for u in selected for f in inst.facets_covered(u)} if analysis.facets else set()
    coverable = sorted({f for pc in pool for f in inst.facets_covered(pc.unit_id)}) if analysis.facets else []
    sel = SelectionResult(
        selected=selected,
        ledger=ledger,
        budget=spec.token_budget,
        tokens_used=sum(units.by_id[u].token_count for u in selected),
        elbow_z=None,
        coverable_facets=coverable,
        uncovered_facets=[f for f in coverable if f not in covered],
        stop_reason="external pipeline",
    )
    run_gaps(spec, retrieval, inst, sel, out, weak, scope=scope)

    # --- answer verification on exactly the text the caller's model saw ---------------------
    sentences: list[dict[str, Any]] = []
    ctx_units = _synthetic_units([by_id[cid] for cid in context_ids])
    passages = [ContextPassage(i + 1, u) for i, u in enumerate(ctx_units)]
    check_context(passages, out)
    if req.answer:
        ctx_ids = set(context_ids)
        left_out = _synthetic_units([c for c in req.candidates if c.id not in ctx_ids])
        if corpus is not None:
            in_prompt_units = {u for cid in context_ids for u in cand_units.get(cid, [])}
            left_out += [u for u in units.units if u.unit_id not in in_prompt_units]
        verified, _, _ = verify_answer(
            req.answer,
            passages,
            UnitSet("external-context", ctx_units),
            out,
            question=req.query,
            others=left_out,
        )
        sentences = [asdict(s) for s in verified]
    else:
        notes.append("No answer was sent, so answer verification didn't run.")

    probes: list[dict[str, Any]] = []
    if req.generator_url and req.answer:
        from wittgenstein.live import counterfactual

        gen = _callback_generator(req.generator_url, req.generator_headers)
        probes = counterfactual.report(
            counterfactual.run_probes(req.query, [(p.n, p.unit.text) for p in passages], req.answer, gen),
            out,
        )
    elif req.generator_url:
        notes.append("A generator callback was given but no answer, so the counterfactual probe didn't run.")

    level = "document" if corpus is not None else "trace"
    if embedder is not None:
        level += "+embeddings"
    unit_to_candidates: dict[str, list[str]] = {}
    for cid, uids in cand_units.items():
        for u in uids:
            unit_to_candidates.setdefault(u, []).append(cid)
    if req.generator_url:
        level += "+generator"
    flags = [f.model_dump(mode="json") for f in out.flags]
    checks = [c.model_dump(mode="json") for c in out.checks]
    return {
        "access": {
            "level": level,
            "corpus_id": corpus.corpus_id if corpus is not None else None,
            "embedding_model": embedder.info.model_identifier if embedder is not None else None,
            "scope": scope,
            "notes": notes,
        },
        "receipt": {
            "candidates": len(req.candidates),
            "in_prompt": len(context_ids),
            "worth_a_look": sum(1 for f in out.flags if f.disposition == FlagDisposition.NEEDS_REVIEW),
            "checks_passed": sum(1 for c in out.checks if c.outcome == CheckOutcome.PASSED),
            "checks_run": sum(1 for c in out.checks if c.outcome != CheckOutcome.NOT_APPLICABLE),
            "checks_not_possible": sum(1 for c in out.checks if c.outcome == CheckOutcome.NOT_APPLICABLE),
        },
        "flags": flags,
        "checks": checks,
        "ledger": [
            {**{k: v for k, v in asdict(e).items() if k != "pull_in_reason"}, "fate": e.fate.value}
            for e in ledger.values()
        ],
        "summary": summarize(flags, sentences),
        "sentences": sentences,
        "counterfactual": probes,
        "unit_to_candidates": unit_to_candidates,
        "unmatched_candidates": unmatched,
        "model_profile": {
            "model": profile.model_identifier,
            "measured_window_tokens": profile.window.effective_window_tokens,
            "window_status": profile.window.status,
            "measured_on": "your model" if embedder is not None else "the checker's own model",
        },
    }


class GeneratorCallbackError(RuntimeError):
    pass


def _callback_generator(url: str, headers: dict[str, str] | None):  # noqa: ANN202
    """The caller's own generator, reached like an embedding callback (and under the same
    rule: this machine only, unless the server allows remote callbacks)."""
    import httpx

    from wittgenstein.live.embedding import embed_url_allowed

    if not embed_url_allowed(url):
        raise GeneratorCallbackError(
            "Generator callbacks must point at this machine (localhost) unless the server sets "
            "WITTGENSTEIN_ALLOW_REMOTE_EMBED=1."
        )

    def generate(question: str, passages: list[tuple[int, str]]) -> str:
        r = httpx.post(
            url,
            json={"question": question, "passages": [{"n": n, "text": t} for n, t in passages]},
            headers=dict(headers or {}),
            timeout=120.0,
        )
        r.raise_for_status()
        answer = r.json().get("answer")
        if not isinstance(answer, str):
            raise GeneratorCallbackError('The generator callback must return {"answer": "..."}.')
        return answer

    return generate


_SEVERITY_ORDER = {"warning": 0, "caution": 1, "info": 2}


def summarize(flags: list[dict[str, Any]], sentences: list[dict[str, Any]]) -> dict[str, Any]:
    """The decision an integrator needs first: does this answer need a person to look,
    and which sentences. (The full flags and checks follow it in the response.)"""
    review = [f for f in flags if f["disposition"] == "needs_review"]
    by_sentence: dict[str, list[dict[str, Any]]] = {}
    for f in review:
        sid = (f.get("metrics") or {}).get("sentence_id")
        if sid:
            by_sentence.setdefault(sid, []).append(f)
    worst = min((f["severity"] for f in review), key=lambda s: _SEVERITY_ORDER.get(s, 3), default=None)
    answer_side = [f for f in review if f.get("stage") in {"answer", "context"}]
    return {
        # The answer, or what reached the model, has something a person should look at.
        "needs_review": bool(answer_side),
        # The search may have missed evidence -- worth knowing even when the answer is fine.
        "retrieval_needs_review": any(f.get("stage") not in {"answer", "context"} for f in review),
        "worst_severity": worst,
        "answer_flags": sum(1 for f in review if f.get("stage") == "answer"),
        "context_flags": sum(1 for f in review if f.get("stage") == "context"),
        "retrieval_flags": sum(1 for f in review if f.get("stage") not in {"answer", "context"}),
        "sentences": [
            {
                "sentence_id": s["sentence_id"],
                "text": s["text"],
                "status": "review" if s["sentence_id"] in by_sentence else "ok",
                "support": s.get("support"),
                "checked_as": s.get("checked_as"),
                "flags": [
                    {"kind": f["kind"], "title": f["title"], "severity": f["severity"]}
                    for f in by_sentence.get(s["sentence_id"], [])
                ],
            }
            for s in sentences
        ],
    }


__all__ = [
    "ExternalCheckRequest",
    "ExternalCandidate",
    "ExternalPipeline",
    "GeneratorCallbackError",
    "check_external",
    "summarize",
]
