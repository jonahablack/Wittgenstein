"""The TypeSafe Jev backend for meaning-level checks, against a fake TypeSafe server."""

from __future__ import annotations

import json

import httpx
import pytest

from wittgenstein.live import nli


@pytest.fixture
def jev(monkeypatch):  # noqa: ANN001, ANN201
    monkeypatch.setenv("WITTGENSTEIN_NLI", "jev")
    monkeypatch.setenv("TYPESAFE_API_KEY", "test-key")
    monkeypatch.setattr(nli, "_MODEL", None)
    monkeypatch.setattr(nli, "_LOAD_ERROR", None)
    calls: list[dict] = []
    replies: list[int] = []  # status codes to return first (then 200)

    def handler(req: httpx.Request) -> httpx.Response:
        assert req.headers["authorization"] == "Bearer test-key"
        body = json.loads(req.content)
        calls.append(body)
        if replies:
            return httpx.Response(replies.pop(0), headers={"retry-after": "0"})
        answers = {}
        for name, q in body["questions"].items():
            assert q["type"] == "choice"
            assert list(q["criteria"]) == ["neutral", "entailment", "contradiction"]  # "no verdict" first
            bad = "not" in q["instructions"]["statement"]
            p = {"neutral": 0.0, "entailment": 0.0 if bad else 1.0, "contradiction": 1.0 if bad else 0.0}
            answers[name] = {"type": "choice", "choice": max(p, key=p.get), "confidence": 1.0, "probabilities": p}
        return httpx.Response(200, json={"model": "jev-1.14.0", "answers": answers, "usage": {}})

    m = nli.model()
    assert isinstance(m, nli._JevModel)
    m._client = httpx.Client(transport=httpx.MockTransport(handler), headers=m._client.headers)
    return calls, replies


def test_one_request_per_sentence_and_verdicts(jev) -> None:  # noqa: ANN001
    calls, _ = jev
    c, e = nli.judge(["Refunds are allowed.", "Contact support first."], "Refunds are not allowed.")
    assert len(calls) == 1  # every (passage, variant) pair in one request
    assert c.contradiction == 1.0 and e.entailment == 0.0
    assert nli.identifier() == "TypeSafe Jev (jev-1.14.0)"


def test_cached_pairs_are_not_asked_again(jev) -> None:  # noqa: ANN001
    calls, _ = jev
    nli.pair("Refunds are allowed.", "Refunds are allowed.")
    nli.pair("Refunds are allowed.", "Refunds are allowed.")
    assert len(calls) == 1


def test_rate_limit_is_retried(jev) -> None:  # noqa: ANN001
    calls, replies = jev
    replies.append(429)
    v = nli.pair("Refunds are allowed.", "Refunds are allowed.")
    assert v is not None and v.entailment == 1.0 and len(calls) == 2


def test_unreachable_is_unavailable_not_passed(jev) -> None:  # noqa: ANN001
    _, replies = jev
    replies.extend([500, 500, 500])
    assert nli.judge(["Refunds are allowed."], "Refunds are allowed.") is None
    assert "couldn't reach" in (nli.load_error() or "")


def test_users_are_told_documents_go_to_typesafe(jev) -> None:  # noqa: ANN001
    st = nli.status()
    assert st["enabled"] is True and st["backend"] == "jev" and "TypeSafe" in str(st["note"])


def test_missing_key_is_reported(monkeypatch) -> None:  # noqa: ANN001
    monkeypatch.setenv("WITTGENSTEIN_NLI", "jev")
    monkeypatch.delenv("TYPESAFE_API_KEY", raising=False)
    monkeypatch.setattr(nli, "_MODEL", None)
    monkeypatch.setattr(nli, "_LOAD_ERROR", None)
    assert nli.model() is None
    assert "TYPESAFE_API_KEY" in (nli.load_error() or "")
