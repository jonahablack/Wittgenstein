"""Model proxy (api/routes/proxy.py): requests pass through unchanged, streamed or not;
RAG requests are audited afterwards; others are not; API keys are never stored."""

from __future__ import annotations

import json

import httpx
import pytest
from fastapi.testclient import TestClient

from wittgenstein.api.app import app
from wittgenstein.api.routes import proxy
from wittgenstein.live import audit_log as audit_mod
from wittgenstein.live.prompt_parse import parse

A = (
    "The recommended starting dosage of metformin extended-release is 500 mg orally once daily with the "
    "evening meal."
)
B = "Increase the dose in increments of 500 mg weekly, up to a maximum of 2,000 mg once daily."
RAG = [
    {"role": "system", "content": "Answer only from the context. Cite [n]."},
    {
        "role": "user",
        "content": f"Context:\n[1] {A}\n[2] {B}\n\nQuestion: What is the maximum dose of metformin ER?",
    },
]
WRONG = "The maximum dose is 2,550 mg once daily. [2]"


def _sse(events: list[dict]) -> bytes:
    return b"".join(f"data: {json.dumps(e)}\n\n".encode() for e in events) + b"data: [DONE]\n\n"


@pytest.fixture()
def wire(monkeypatch: pytest.MonkeyPatch):
    seen: list[httpx.Request] = []

    def handler(req: httpx.Request) -> httpx.Response:
        seen.append(req)
        body = json.loads(req.content) if req.content else {}
        if req.url.path.endswith("/v1/models"):
            return httpx.Response(200, json={"data": [{"id": "m"}]})
        if req.url.host == "api.anthropic.com":
            if body.get("stream"):
                ev = [
                    {"type": "message_start"},
                    {
                        "type": "content_block_delta",
                        "delta": {"type": "text_delta", "text": "The maximum dose is "},
                    },
                    {"type": "content_block_delta", "delta": {"type": "text_delta", "text": "2,550 mg. [2]"}},
                ]
                return httpx.Response(200, content=_sse(ev), headers={"content-type": "text/event-stream"})
            return httpx.Response(200, json={"content": [{"type": "text", "text": WRONG}]})
        if body.get("stream"):
            parts = ["The maximum dose ", "is 2,550 mg ", "once daily. [2]"]
            ev = [{"choices": [{"delta": {"content": p}}]} for p in parts]
            return httpx.Response(200, content=_sse(ev), headers={"content-type": "text/event-stream"})
        return httpx.Response(200, json={"choices": [{"message": {"content": WRONG}}]})

    monkeypatch.setattr(proxy, "client_factory", lambda: httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    monkeypatch.setattr(proxy, "run_in_background", lambda fn: fn())
    monkeypatch.setattr(audit_mod, "_LOG", audit_mod.AuditLog())
    return TestClient(app), seen


@pytest.mark.parametrize("stream", [False, True])
def test_openai_request_passes_through_and_is_audited(wire, stream: bool) -> None:  # noqa: ANN001
    client, seen = wire
    r = client.post(
        "/proxy/openai/v1/chat/completions",
        json={"model": "gpt-x", "messages": RAG, "stream": stream},
        headers={"authorization": "Bearer sk-secret", "x-wittgenstein-source": "my-app"},
    )
    assert r.status_code == 200
    assert ("2,550" in r.text) and (("data:" in r.text) == stream)
    up = seen[-1]
    assert str(up.url) == "https://api.openai.com/v1/chat/completions"
    assert up.headers["authorization"] == "Bearer sk-secret"
    assert "x-wittgenstein-source" not in up.headers
    audits = client.get("/v1/audits").json()["audits"]
    assert len(audits) == 1 and audits[0]["source"] == "my-app" and audits[0]["needs_review"]
    full = client.get(f"/v1/audits/{audits[0]['audit_id']}").json()
    assert "sk-secret" not in json.dumps(full)
    assert full["request"]["query"] == "What is the maximum dose of metformin ER?"
    kinds = {f["kind"] for s in full["report"]["summary"]["sentences"] for f in s["flags"]}
    assert "quantity_mismatch" in kinds


@pytest.mark.parametrize("stream", [False, True])
def test_anthropic_messages_are_audited(wire, stream: bool) -> None:  # noqa: ANN001
    client, seen = wire
    r = client.post(
        "/proxy/anthropic/v1/messages",
        json={"model": "claude-x", "system": RAG[0]["content"], "messages": RAG[1:], "stream": stream},
        headers={"x-api-key": "sk-ant-secret", "anthropic-version": "2023-06-01"},
    )
    assert r.status_code == 200
    assert str(seen[-1].url) == "https://api.anthropic.com/v1/messages"
    assert seen[-1].headers["x-api-key"] == "sk-ant-secret"
    audits = client.get("/v1/audits").json()["audits"]
    assert len(audits) == 1 and audits[0]["needs_review"]


def test_non_rag_requests_are_not_audited(wire) -> None:  # noqa: ANN001
    client, _ = wire
    assert client.get("/proxy/openai/v1/models").json() == {"data": [{"id": "m"}]}
    r = client.post("/proxy/openai/v1/chat/completions", json={"messages": [{"role": "user", "content": "Hi!"}]})
    assert r.status_code == 200
    assert client.get("/v1/audits").json()["audits"] == []


def test_upstream_is_configurable(wire, monkeypatch: pytest.MonkeyPatch) -> None:  # noqa: ANN001
    client, seen = wire
    monkeypatch.setenv("WITTGENSTEIN_OPENAI_UPSTREAM", "http://localhost:11434/")
    client.post("/proxy/openai/v1/chat/completions", json={"messages": RAG})
    assert str(seen[-1].url) == "http://localhost:11434/v1/chat/completions"


@pytest.mark.parametrize(
    ("messages", "system", "question", "n"),
    [
        (RAG, None, "What is the maximum dose of metformin ER?", 2),
        (
            [{"role": "user", "content": "What is the starting dose?"}],
            f"Source 1: {A}\nSource 2: {B}",
            "What is the starting dose?",
            2,
        ),
        (
            [{"role": "user", "content": f"<document>{A}</document><document>{B}</document>\nWhat is the dose?"}],
            None,
            "What is the dose?",
            2,
        ),
        (
            [{"role": "user", "content": f"Context:\n{A}\n\n{B}\n\nWhat is the max dose?"}],
            None,
            "What is the max dose?",
            2,
        ),
        ([{"role": "user", "content": "Write a haiku about autumn."}], None, None, 0),
        ([{"role": "user", "content": "1. Be brief.\nWhat is 2+2?"}], None, None, 0),
    ],
)
def test_prompt_parse(messages: list, system: str | None, question: str | None, n: int) -> None:
    p = parse(messages, system)
    if question is None:
        assert p is None
    else:
        assert p is not None and p.question == question and len(p.passages) == n
