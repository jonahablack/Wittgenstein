"""Integration API additions: /v1 paths, batch, optional API keys, the summary block,
and the generator callback for the counterfactual probe."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from wittgenstein.api.app import app
from wittgenstein.live import external

PASSAGE = (
    "Increase the dosage in increments of 500 mg weekly, up to a maximum of 2,000 mg once daily with the "
    "evening meal."
)
REQ = {
    "query": "What is the maximum daily dose of metformin extended-release?",
    "candidates": [{"id": "a", "text": PASSAGE}],
    "answer": "The maximum is 2,000 mg once daily with the evening meal. [1]",
}


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.delenv("WITTGENSTEIN_API_KEYS", raising=False)
    return TestClient(app)


def test_v1_check_has_summary(client: TestClient) -> None:
    r = client.post("/v1/check", json=REQ)
    assert r.status_code == 200
    body = r.json()
    assert body["api_version"]
    assert body["summary"]["needs_review"] is False
    assert [s["status"] for s in body["summary"]["sentences"]] == ["ok"]


def test_summary_flags_bad_answer(client: TestClient) -> None:
    bad = {**REQ, "answer": "The maximum is 2,550 mg twice daily. [1]"}
    s = client.post("/v1/check", json=bad).json()["summary"]
    assert s["needs_review"] is True and s["worst_severity"] == "warning"
    assert s["sentences"][0]["status"] == "review"


def test_batch_isolates_failures(client: TestClient) -> None:
    items = [REQ, {**REQ, "answer": "[1]"}, {**REQ, "corpus_id": "no-such-corpus"}]
    body = client.post("/live/check/batch", json={"items": items}).json()
    assert body["errors"] == 1 and body["needs_review"] == 1
    assert body["results"][2]["error"]["status"] == 404
    kinds = {f["kind"] for f in body["results"][1]["flags"]}
    assert "answer_empty" in kinds


def test_api_keys(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("WITTGENSTEIN_API_KEYS", "k1, k2")
    assert client.post("/v1/check", json=REQ).status_code == 401
    assert client.post("/v1/check", json=REQ, headers={"X-API-Key": "k2"}).status_code == 200
    assert client.post("/v1/check", json=REQ, headers={"Authorization": "Bearer k1"}).status_code == 200
    assert client.post("/v1/check", json=REQ, headers={"Authorization": "Bearer nope"}).status_code == 401


def test_generator_callback_must_be_local(client: TestClient) -> None:
    r = client.post("/v1/check", json={**REQ, "generator_url": "http://example.com/generate"})
    assert r.status_code == 422


def test_counterfactual_via_callback(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    def memory_model(_url: str, _headers: object):  # noqa: ANN202
        return lambda _q, _ps: REQ["answer"]

    monkeypatch.setattr(external, "_callback_generator", memory_model)
    body = client.post("/v1/check", json={**REQ, "generator_url": "http://127.0.0.1:9/generate"}).json()
    assert body["access"]["level"].endswith("+generator")
    assert body["counterfactual"][0]["outcome"] == "ignores_context"
    assert any(f["kind"] == "context_ignored" for f in body["flags"])
