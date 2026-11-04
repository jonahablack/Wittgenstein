"""Live self-aware pipeline (docs/live-pipeline-plan.md). Probe tests use test-double
embedders whose behavior is known by construction (one that ignores "not", one that
reads only the first N words), so each check is tested against a known right answer
without downloading a model."""

from __future__ import annotations

import re
from pathlib import Path

import numpy as np
import pytest

from wittgenstein.core.enums import (
    CandidateFate,
    CheckOutcome,
    ConstraintKind,
    EmbedderFamily,
    EpistemicStatus,
    FlagDisposition,
    FlagKind,
    KPolicy,
    LiveEventType,
    PullInReason,
    RetrievalChannel,
)
from wittgenstein.live import phrases as P
from wittgenstein.live.characterize import characterize
from wittgenstein.live.corpus import LiveCorpus
from wittgenstein.live.coverage import Instruments
from wittgenstein.live.embedding import CachingEmbedder, EmbedderInfo, HashingEmbedder
from wittgenstein.live.flags import REGISTRY_LINKS, FlagCollector
from wittgenstein.live.pipelines import PipelineSpec, Remediation
from wittgenstein.live.probes import run_probes
from wittgenstein.live.query import analyze_query
from wittgenstein.live.retrieve import retrieve
from wittgenstein.live.runner import run_query
from wittgenstein.live.select import select
from wittgenstein.live.text_artifacts import classify_severance, find_satellite, modal_mismatch
from wittgenstein.live.verify import split_answer, verify_answer
from wittgenstein.schemas.trace import QueryTrace

REPO = Path(__file__).resolve().parents[2]
ASTERIA = REPO / "data" / "fixtures" / "asteria_manual" / "documents"
LIVE_SRC = REPO / "src" / "wittgenstein" / "live"


def _asteria(cid: str) -> LiveCorpus:
    return LiveCorpus(cid, {p.stem: p.read_text() for p in sorted(ASTERIA.glob("*.md"))})


class _PrefixEmbedder(HashingEmbedder):
    """Reads only the first `window` words -- a known input window by construction."""

    def __init__(self, window: int) -> None:
        super().__init__()
        self._window = window
        self.info = EmbedderInfo(
            "prefix-test", "prefix", EmbedderFamily.HASHING_TEST_ONLY, 256, None, "regex_words"
        )

    def embed(self, texts: list[str]) -> np.ndarray:
        return super().embed([" ".join(t.split()[: self._window]) for t in texts])


def _hashing(ignored: frozenset[str] = frozenset()) -> CachingEmbedder:
    e = HashingEmbedder(ignored_words=ignored)
    if ignored:
        e.info = EmbedderInfo(
            f"hashing-ignoring-{'-'.join(sorted(ignored))}",
            "hashing",
            EmbedderFamily.HASHING_TEST_ONLY,
            256,
            None,
            "regex_words",
        )
    return CachingEmbedder(e)


# --- phrase matching (ported edge cases) ---------------------------------------------


@pytest.mark.parametrize(
    ("text", "phrase"),
    [
        ("a nonprofit", "no"),
        ("a small unit", "all"),
        ("based in canada", "can"),
        ("the mayor said", "may"),
        ("a gift", "if"),
        ("nevertheless it held", "never"),
        ("notwithstanding that", "not"),
    ],
)
def test_phrase_matching_never_matches_inside_words(text: str, phrase: str) -> None:
    assert not P.contains_phrase(P.lower(text), phrase)


def test_no_less_than_idiom_is_not_negation_and_keeps_offsets() -> None:
    raw = "retain logs for no less than ninety days"
    low = P.lower(raw)
    assert len(low) == len(raw)
    assert not P.find_phrases(low, P.NEGATION_WORDS)


def test_no_bare_substring_checks_in_live_package() -> None:
    """The edge-case log's structural guarantee, carried over: phrase lists are never
    matched with a bare `in` against text."""
    bad = re.compile(r"\b(?:p|phrase|word|cue|t)\s+in\s+(?:text|low|lower_text|head|tail|last)\b")
    offenders = [
        f"{path.name}:{i}"
        for path in LIVE_SRC.rglob("*.py")
        for i, line in enumerate(path.read_text().splitlines(), 1)
        if bad.search(line) and "for " not in line.split(" in ")[0][-12:]
    ]
    assert offenders == []


# --- query analysis --------------------------------------------------------------------


def test_query_constraints_and_facets() -> None:
    a = analyze_query("Which Class R inspection units are not required to pass the Structural Load Assessment?")
    kinds = {(c.kind, c.span.text) for c in a.constraints}
    assert (ConstraintKind.IDENTIFIER, "Class R") in kinds
    assert (ConstraintKind.NEGATION, "not") in kinds
    assert [f.span.text for f in a.facets] == ["Class R inspection units", "Structural Load Assessment"]


def test_comparison_facet_splits_per_identifier_and_possessives_strip() -> None:
    a = analyze_query("Compare Class R and Class S units")
    assert [f.span.text for f in a.facets] == ["Class R", "Class S"]
    b = analyze_query("What was Elizabeth's opinion?")
    assert "elizabeth" in b.facets[0].terms


# --- characterization -------------------------------------------------------------------


def test_window_measurement_recovers_a_known_input_window() -> None:
    corpus = LiveCorpus("t-window", {"d": " ".join(f"word{i}" for i in range(3000)) + "."})
    prof = characterize(_PrefixEmbedder(200), corpus)
    assert prof.window.status == "saturated"
    assert 190 <= prof.window.effective_window_tokens <= 210


def test_no_window_reported_when_the_model_reads_everything() -> None:
    corpus = LiveCorpus("t-nowindow", {"d": " ".join(f"word{i}" for i in range(3000)) + "."})
    assert characterize(_hashing(), corpus).window.status == "no_saturation_observed"


def test_negation_baseline_is_zero_for_a_model_that_ignores_not() -> None:
    prof = characterize(_hashing(frozenset({"not"})), _asteria("t-neg"))
    assert prof.edit_shift_baselines["negation"].p90 == pytest.approx(0.0, abs=1e-6)
    assert prof.edit_shift_baselines["content_word"].p50 > 0.01


# --- probes -----------------------------------------------------------------------------


def _probe(corpus: LiveCorpus, query: str, emb: CachingEmbedder, spec: PipelineSpec) -> FlagCollector:
    units = corpus.units()
    a = analyze_query(query, units.bm25._idf)
    prof = characterize(emb, corpus)
    r = retrieve(spec, units, a, emb)
    out = FlagCollector("t")
    run_probes(spec, r, Instruments(units, a, emb, prof), emb, prof, out)
    return out


_DENSE = PipelineSpec(
    pipeline_id="t-dense",
    label="t",
    description="t",
    channels=[RetrievalChannel.DENSE],
    embedder="hashing-test",
    k=3,
)


def test_negation_probe_flags_a_model_that_ignores_not() -> None:
    corpus = _asteria("t-probe-neg")
    out = _probe(
        corpus, "Which units are not exempt from the clearance margin?", _hashing(frozenset({"not"})), _DENSE
    )
    assert any(f.kind == FlagKind.CONSTRAINT_INSENSITIVE and f.query_span.text == "not" for f in out.flags)


def test_negation_probe_passes_a_model_that_registers_not() -> None:
    corpus = _asteria("t-probe-neg2")
    out = _probe(corpus, "Which units are not exempt from the clearance margin?", _hashing(), _DENSE)
    assert not any(f.kind == FlagKind.CONSTRAINT_INSENSITIVE and f.query_span.text == "not" for f in out.flags)


def test_answerability_flags_a_question_the_document_never_mentions() -> None:
    corpus = _asteria("t-answerable")
    out = _probe(corpus, "What is the airspeed velocity of an unladen swallow?", _hashing(), _DENSE)
    assert any(f.kind == FlagKind.WEAK_BEST_MATCH for f in out.flags)
    out2 = _probe(corpus, "What clearance margin applies to Class S inspection units?", _hashing(), _DENSE)
    assert not any(f.kind == FlagKind.WEAK_BEST_MATCH for f in out2.flags)


def test_every_check_records_an_outcome_even_when_nothing_is_found() -> None:
    out = _probe(_asteria("t-checks"), "What clearance margin applies to Class S units?", _hashing(), _DENSE)
    assert {c.kind for c in out.checks} >= {
        FlagKind.WEAK_BEST_MATCH,
        FlagKind.CONSTRAINT_INSENSITIVE,
        FlagKind.DILUTION,
    }
    assert all(c.outcome in set(CheckOutcome) for c in out.checks)


# --- selection --------------------------------------------------------------------------

_AWARE = PipelineSpec(
    pipeline_id="t-aware",
    label="t",
    description="t",
    channels=[RetrievalChannel.LEXICAL, RetrievalChannel.DENSE],
    embedder="hashing-test",
    facet_queries=True,
    k_policy=KPolicy.ADAPTIVE,
    k=4,
    k_min=2,
    remediation=Remediation(),
)


def _select(spec: PipelineSpec, query: str, cid: str):  # noqa: ANN202
    corpus = _asteria(cid)
    emb = _hashing()
    units = corpus.units()
    a = analyze_query(query, units.bm25._idf)
    prof = characterize(emb, corpus)
    r = retrieve(spec, units, a, emb)
    inst = Instruments(units, a, emb, prof)
    return select(spec, r, inst, [], prof.pairwise_similarity.p90), r


def test_selection_is_deterministic_and_every_candidate_has_one_fate() -> None:
    q = "What clearance margin must a Class R inspection unit meet before deployment?"
    s1, r = _select(_AWARE, q, "t-det1")
    s2, _ = _select(_AWARE, q, "t-det2")
    assert [(e.unit_id, e.fate, e.reason) for e in s1.ledger.values()] == [
        (e.unit_id, e.fate, e.reason) for e in s2.ledger.values()
    ]
    assert {c.unit_id for c in r.pool} <= set(s1.ledger)
    assert all(isinstance(e.fate, CandidateFate) and e.reason for e in s1.ledger.values())


def test_fixed_k_selects_exactly_k() -> None:
    sel, _ = _select(_DENSE, "What clearance margin applies to Class S units?", "t-fixed")
    assert len(sel.selected) == 3
    assert all(e.fate == CandidateFate.NOT_REACHED for e in sel.ledger.values() if e.unit_id not in sel.selected)


def test_remediation_follows_cross_references_and_definitions() -> None:
    sel, _ = _select(
        _AWARE, "What clearance margin must a Class R inspection unit meet before deployment?", "t-rem"
    )
    reasons = {sel.ledger[u].pull_in_reason for u in sel.pulled_in}
    assert PullInReason.CROSS_REFERENCE_TARGET in reasons or PullInReason.DEFINITION in reasons
    assert all(sel.ledger[u].fate == CandidateFate.PULLED_IN for u in sel.pulled_in)


# --- text artifacts and verification --------------------------------------------------


def test_condition_satellite_needs_a_real_clause() -> None:
    assert find_satellite(
        P.lower("Units pass provided that the unit has completed an assessment."), P.CONDITION_CONNECTIVES
    )
    assert find_satellite(P.lower("Units pass, if applicable."), P.CONDITION_CONNECTIVES) is None


def test_severance_classification() -> None:
    clause, cue = "the unit has completed a conformity assessment", "provided that"
    assert classify_severance(clause, cue, "Units pass at 12 cm.") == "dropped"
    assert (
        classify_severance(clause, cue, "Units pass provided that the unit has completed a conformity assessment.")
        is None
    )
    assert classify_severance(clause, cue, "Units pass; a conformity assessment exists.") == "severed"


def test_modal_mismatch_flags_dropped_hedges_not_plain_restatement() -> None:
    assert modal_mismatch("Units may be exempt.", "Units are exempt.") == ("weak", None)
    assert modal_mismatch("Units must pass.", "Units pass.") is None
    assert modal_mismatch("Units may pass.", "Units must pass.") == ("weak", "strong")


def test_split_answer_attaches_citations_to_the_right_sentences() -> None:
    parts = split_answer("First claim here. [1] Second claim here. [2, 3] A third one [1].")
    assert parts == [("First claim here.", [1]), ("Second claim here.", [2, 3]), ("A third one .", [1])] or parts[
        :2
    ] == [("First claim here.", [1]), ("Second claim here.", [2, 3])]


def test_verification_flags_a_dropped_condition() -> None:
    from wittgenstein.live.generate import ContextPassage

    corpus = _asteria("t-verify")
    units = corpus.units()
    target = next(u for u in units.units if "provided that" in u.text)
    out = FlagCollector("t")
    verify_answer(
        "A Class R inspection unit shall pass the Structural Load Assessment at 12 centimetres. [1]",
        [ContextPassage(1, target)],
        units,
        out,
    )
    assert any(f.kind == FlagKind.CONDITION_SATELLITE for f in out.flags)


# --- registry linkage and end-to-end ---------------------------------------------------


def test_registry_linked_flags_carry_the_registry_status() -> None:
    from wittgenstein.services.registry_service import get_registry

    reg = get_registry()
    out = FlagCollector("t")
    for kind, mech in REGISTRY_LINKS.items():
        f = out.flag(
            kind,
            origin="text",
            stage="answer",
            severity="info",
            disposition="informational",
            title="t",
            observation="t",
            why_it_matters="t",
            measurement="pattern_match",
        )
        assert f.registry is not None and f.registry.epistemic_status == reg.mechanisms[mech].epistemic_status
    e = out.flag(
        FlagKind.CONSTRAINT_INSENSITIVE,
        origin="pipeline",
        stage="embedding",
        severity="info",
        disposition="informational",
        title="t",
        observation="t",
        why_it_matters="t",
        measurement="measured",
    )
    assert e.registry is None
    assert all(
        f.registry.epistemic_status != EpistemicStatus.EXTERNALLY_ESTABLISHED
        for f in out.flags
        if f.registry and f.kind.value.endswith("satellite")
    )


def test_end_to_end_run_produces_valid_traces_and_ordered_events() -> None:
    corpus = _asteria("t-e2e")
    specs = {"t-aware": _AWARE, "t-dense": _DENSE}
    events = []
    result = run_query(
        corpus,
        "What clearance margin must a Class R inspection unit meet before deployment?",
        ["t-aware", "t-dense"],
        sink=events.append,
        specs=specs,
    )
    assert [e.seq for e in events] == list(range(1, len(events) + 1))
    assert events[0].type == LiveEventType.RUN_STARTED and events[-1].type == LiveEventType.RUN_COMPLETED
    for o in result.outcomes.values():
        QueryTrace.model_validate(o.trace)
        assert o.answer
        assert o.receipt.passages_used >= 1
        assert {f["disposition"] for f in o.flags} <= {d.value for d in FlagDisposition}
