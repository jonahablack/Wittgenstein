"""wittgenstein.monitor: framework hooks report each answer, with its retrieval and
prompt context, to the audit feed (POST /v1/audits), and the feed records it."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from wittgenstein.api.app import app
from wittgenstein.live import audit_log as audit_mod
from wittgenstein.monitor import _client

PASSAGES = [
    "The recommended starting dosage of metformin hydrochloride extended-release is 500 mg orally once daily "
    "with the evening meal.",
    "Increase the dose in increments of 500 mg weekly, up to a maximum of 2,000 mg once daily.",
    "Warfarin is contraindicated in pregnancy except in women with mechanical heart valves.",
]


@pytest.fixture()
def feed(monkeypatch: pytest.MonkeyPatch):
    """Route the monitor's reports through the real API, synchronously."""
    client = TestClient(app)
    monkeypatch.setattr(audit_mod, "_LOG", audit_mod.AuditLog())
    sent: list[dict] = []
    statuses: list[tuple[int, str]] = []

    def post(body: dict) -> dict:
        sent.append(body)
        r = client.post("/v1/audits", json=body)
        statuses.append((r.status_code, r.text[:300]))
        r.raise_for_status()
        return r.json()

    monkeypatch.setattr(_client, "_post", post)
    yield client, sent
    assert all(code == 200 for code, _ in statuses), statuses


def test_context_order_follows_the_prompt() -> None:
    prompt = f"Context:\n[1] {PASSAGES[2]}\n[2] {PASSAGES[0]}\nQuestion: ..."
    assert _client.context_order(PASSAGES, prompt) == [2, 0]


def test_record_is_checked_and_listed(feed) -> None:  # noqa: ANN001
    client, sent = feed
    _client.record(
        "What is the maximum dose of metformin extended-release?",
        PASSAGES,
        "The maximum dose is 2,550 mg per day. [1]",
        prompt=f"[1] {PASSAGES[1]}\nQuestion: ...",
        source="test",
    )
    assert _client.flush(30)
    assert sent[0]["context_ids"] == ["p2"]
    listed = client.get("/v1/audits").json()["audits"]
    assert len(listed) == 1 and listed[0]["source"] == "test" and listed[0]["needs_review"]
    full = client.get(f"/v1/audits/{listed[0]['audit_id']}").json()
    kinds = {f["kind"] for s in full["report"]["summary"]["sentences"] for f in s["flags"]}
    assert "quantity_mismatch" in kinds
    assert client.delete("/v1/audits").json() == {"cleared": True}
    assert client.get("/v1/audits").json()["audits"] == []


def test_record_never_raises_when_server_is_down(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(_client._settings, "url", "http://127.0.0.1:9")
    _client.record("A question?", PASSAGES, "An answer.")
    assert _client.flush(30)


def test_langchain_pipeline_is_audited_without_changes(feed) -> None:  # noqa: ANN001
    pytest.importorskip("langchain_core")
    from langchain_core.documents import Document
    from langchain_core.language_models.fake_chat_models import FakeListChatModel
    from langchain_core.prompts import ChatPromptTemplate
    from langchain_core.retrievers import BaseRetriever
    from langchain_core.runnables import RunnablePassthrough

    from wittgenstein.monitor import langchain as lc

    class Retriever(BaseRetriever):
        def _get_relevant_documents(self, query: str, *, run_manager=None):  # noqa: ANN001,ANN202
            return [Document(page_content=t, id=f"doc{i}") for i, t in enumerate(PASSAGES)]

    lc.install()
    _, sent = feed
    prompt = ChatPromptTemplate.from_template("Answer from the context.\n{context}\nQuestion: {question}")
    llm = FakeListChatModel(responses=["The starting dose is 850 mg once daily. [1]"])

    def fmt(docs):  # noqa: ANN001,ANN202 -- the pipeline keeps only the first passage
        return f"[1] {docs[0].page_content}"

    chain = {"context": Retriever() | fmt, "question": RunnablePassthrough()} | prompt | llm
    chain.invoke("What is the starting dose of metformin extended-release?")
    assert _client.flush(30)
    assert len(sent) == 1
    body = sent[0]
    assert body["query"] == "What is the starting dose of metformin extended-release?"
    assert [c["id"] for c in body["candidates"]] == ["doc0", "doc1", "doc2"]
    assert body["context_ids"] == ["doc0"]  # inferred from the prompt
    assert body["answer"].startswith("The starting dose is 850 mg")


def test_llamaindex_query_engine_is_audited(feed) -> None:  # noqa: ANN001
    pytest.importorskip("llama_index.core")
    from llama_index.core import Document, Settings, VectorStoreIndex
    from llama_index.core.embeddings import MockEmbedding
    from llama_index.core.llms import MockLLM

    from wittgenstein.monitor import llamaindex as li

    li.install()
    _, sent = feed
    Settings.llm = MockLLM(max_tokens=8)
    Settings.embed_model = MockEmbedding(embed_dim=8)
    index = VectorStoreIndex.from_documents([Document(text=t) for t in PASSAGES])
    index.as_query_engine(similarity_top_k=2).query("What is the starting dose of metformin?")
    assert _client.flush(30)
    assert len(sent) == 1
    body = sent[0]
    assert body["query"] == "What is the starting dose of metformin?"
    assert len(body["context_ids"]) == 2
    assert body["pipeline"] == {"name": "llamaindex"}
