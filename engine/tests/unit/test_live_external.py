"""Checking an external pipeline's run (live/external.py, POST /live/check)."""

from __future__ import annotations

import io
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from wittgenstein.core.enums import CheckOutcome, EmbedderFamily, FlagKind
from wittgenstein.live.corpus import LiveCorpus
from wittgenstein.live.embedding import (
    CachingEmbedder,
    EmbedCallbackError,
    EmbedderInfo,
    HashingEmbedder,
    HttpEmbedder,
    embed_url_allowed,
)
from wittgenstein.live.external import ExternalCheckRequest, check_external

ASTERIA = Path(__file__).resolve().parents[2] / "data" / "fixtures" / "asteria_manual" / "documents"
RULE = (
    "A Class R inspection unit shall pass the Structural Load Assessment at a minimum clearance margin of 12 "
    "centimetres before deployment, provided that the unit has completed a conformity assessment under "
    "Definition D-05."
)
CLASS_S = (
    "A Class S inspection unit shall pass the Structural Load Assessment at a minimum clearance margin of 8 "
    "centimetres before deployment."
)
LEGACY = (
    "An inspection unit manufactured before 1 January 2025 is exempt from the clearance margin set out in "
    "Article 2, except where the unit has been substantially modified since its original manufacture date."
)


def _req(**kw) -> ExternalCheckRequest:  # noqa: ANN003
    base = {
        "query": "What clearance margin must a Class R inspection unit meet before deployment?",
        "candidates": [
            {"id": "c1", "text": RULE, "score": 0.82},
            {"id": "c2", "text": CLASS_S, "score": 0.80},
            {"id": "c3", "text": LEGACY, "score": 0.41},
        ],
        "context_ids": ["c1", "c2"],
        "answer": "A Class R unit must meet a minimum clearance margin of 15 centimetres. [1]",
        "pipeline": {"retriever": "dense", "embedding_model": "their-model"},
    }
    base.update(kw)
    return ExternalCheckRequest.model_validate(base)


def _by_kind(result: dict, kind: FlagKind) -> list[dict]:
    return [f for f in result["flags"] if f["kind"] == kind.value]


def _check(result: dict, kind: FlagKind) -> dict:
    return next(c for c in result["checks"] if c["kind"] == kind.value)


def test_trace_only_checks_the_answer_and_says_what_it_could_not_check() -> None:
    r = check_external(_req())
    assert r["access"]["level"] == "trace"
    # 15 cm is not what the cited passage says
    assert _by_kind(r, FlagKind.QUANTITY_MISMATCH)
    # the dropped "provided that ..." condition
    assert _by_kind(r, FlagKind.CONDITION_SATELLITE)
    # a top passage about Class S when the question asks about Class R
    assert _by_kind(r, FlagKind.NEAR_MISS)
    # document-wide and model-specific checks are reported as not possible, with a reason
    assert _check(r, FlagKind.WEAK_BEST_MATCH)["outcome"] == CheckOutcome.NOT_APPLICABLE.value
    neg = _check(r, FlagKind.EMBEDDER_TRUNCATION)
    assert neg["outcome"] == CheckOutcome.NOT_APPLICABLE.value and "embed_url" in neg["detail"]
    assert r["model_profile"]["measured_on"] == "the checker's own model"
    assert {e["fate"] for e in r["ledger"]} == {"selected", "not_reached"}


def test_document_access_enables_document_wide_checks() -> None:
    corpus = LiveCorpus("ext-doc", {p.stem: p.read_text() for p in sorted(ASTERIA.glob("*.md"))})
    r = check_external(_req(), corpus=corpus)
    assert r["access"]["level"] == "document"
    assert r["unmatched_candidates"] == []
    assert _check(r, FlagKind.WEAK_BEST_MATCH)["outcome"] != CheckOutcome.NOT_APPLICABLE.value
    # the rule cites Definition D-05 and Article 2; the external pipeline didn't follow them
    open_refs = [
        f
        for k in (FlagKind.DEFINITION_NOT_IN_CONTEXT, FlagKind.CROSS_REFERENCE_NOT_FOLLOWED)
        for f in _by_kind(r, k)
        if f["disposition"] == "needs_review"
    ]
    assert open_refs


def test_unmatched_candidates_are_reported_not_silently_dropped() -> None:
    corpus = LiveCorpus("ext-doc2", {p.stem: p.read_text() for p in sorted(ASTERIA.glob("*.md"))})
    req = _req(
        candidates=[
            {"id": "c1", "text": RULE},
            {"id": "zz", "text": "Completely unrelated text about penguins and their migration habits."},
        ],
        context_ids=["c1", "zz"],
    )
    r = check_external(req, corpus=corpus)
    assert r["unmatched_candidates"] == ["zz"]
    assert any("didn't match" in n for n in r["access"]["notes"])


def test_embedding_access_runs_probes_on_the_callers_model() -> None:
    inner = HashingEmbedder(ignored_words=frozenset({"not"}))
    inner.info = EmbedderInfo("external:t", "their-model", EmbedderFamily.EXTERNAL, 256, None, "regex_words")
    req = _req(query="Which inspection units are not exempt from the clearance margin?", answer=None)
    r = check_external(req, embedder=CachingEmbedder(inner))
    assert r["access"]["level"] == "trace+embeddings"
    assert r["model_profile"]["measured_on"] == "your model"
    flags = _by_kind(r, FlagKind.CONSTRAINT_INSENSITIVE)
    assert any(f["query_span"]["text"] == "not" for f in flags)


def test_request_validation() -> None:
    with pytest.raises(ValueError):
        _req(context_ids=["nope"])
    with pytest.raises(ValueError):
        _req(candidates=[{"id": "a", "text": "x"}, {"id": "a", "text": "y"}])


def test_embed_callback_guard_and_shape(monkeypatch: pytest.MonkeyPatch) -> None:
    assert not embed_url_allowed("https://example.com/embed")
    assert embed_url_allowed("http://localhost:9000/embed")
    monkeypatch.setenv("WITTGENSTEIN_ALLOW_REMOTE_EMBED", "1")
    assert embed_url_allowed("https://example.com/embed")
    monkeypatch.delenv("WITTGENSTEIN_ALLOW_REMOTE_EMBED")
    assert not embed_url_allowed("file:///etc/passwd")

    calls = []

    def fake_urlopen(req, timeout):  # noqa: ANN001, ANN202
        texts = json.loads(req.data)["texts"]
        calls.append(len(texts))
        return io.BytesIO(json.dumps({"embeddings": [[1.0, float(len(t)), 0.0] for t in texts]}).encode())

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    e = HttpEmbedder("http://127.0.0.1:9000/embed", "m")
    assert e.info.family == EmbedderFamily.EXTERNAL and e.info.max_input_tokens is None
    v = e.embed(["a", "bbb"])
    assert v.shape == (2, 3) and abs(float((v[0] ** 2).sum()) - 1.0) < 1e-5

    monkeypatch.setattr("urllib.request.urlopen", lambda req, timeout: io.BytesIO(b'{"oops": 1}'))
    with pytest.raises(EmbedCallbackError):
        HttpEmbedder("http://127.0.0.1:9000/embed")


def test_check_route() -> None:
    from wittgenstein.api.app import app

    client = TestClient(app)
    body = _req().model_dump(mode="json")
    res = client.post("/live/check", json=body)
    assert res.status_code == 200, res.text
    assert res.json()["access"]["level"] == "trace"
    remote = {**body, "embed_url": "https://example.com/embed"}
    assert client.post("/live/check", json=remote).status_code == 422


# --- Regressions from the 2026-11-04 verification audit ------------------------------


def test_uncovered_part_is_never_called_absent_when_the_document_has_it() -> None:
    """The audit found "No passage in the document clearly matches 'starting dose'"
    although the label states it twice: absence was judged from the top few passages
    by meaning only. The document has a definition of "registered operator"; a pipeline
    that didn't retrieve it must be told it was left out, never that it doesn't exist."""
    corpus = LiveCorpus("ext-audit1", {p.stem: p.read_text() for p in sorted(ASTERIA.glob("*.md"))})
    req = _req(
        query="What clearance margin applies to Class R units, and who counts as a registered operator?",
        candidates=[{"id": "c1", "text": RULE}, {"id": "c2", "text": CLASS_S}],
        context_ids=["c1", "c2"],
        answer=None,
    )
    r = check_external(req, corpus=corpus)
    flags = [f for f in _by_kind(r, FlagKind.FACET_UNCOVERED) if "registered operator" in f["title"]]
    assert flags, "the uncovered part should be flagged"
    assert all("was left out" in f["title"] for f in flags)
    assert not any("never mentioned" in f["observation"] or "No passage" in f["observation"] for f in flags)


def test_population_check_stands_down_when_the_citation_is_wrong() -> None:
    """The audit found a "dropped who this applies to" flag on a sentence whose cited
    passage was about something else entirely: the comparison used the wrong sentence."""
    req = _req(
        candidates=[{"id": "c1", "text": "In patients with eGFR below 30, the drug is contraindicated."}],
        context_ids=["c1"],
        answer="The starting dose is 850 mg once daily. [1]",
    )
    r = check_external(req)
    assert _by_kind(r, FlagKind.QUANTITY_MISMATCH)  # still flagged: useful either way
    assert not _by_kind(r, FlagKind.POPULATION_QUALIFIER_DROPPED)
