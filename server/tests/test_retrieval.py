"""Regression tests for query-scoped retrieval (components/retrieval.py)
and the POST /query endpoint.

Invariants pinned here:
  - BM25 relevance: a query term retrieves the claims containing it and
    excludes zero-score non-matches.
  - Query results are sorted risk-tier-first: Unformalized, High, Medium,
    Low; ties within a tier broken by BM25 score descending.
  - Risk triage runs ONLY on the retrieved subset, never the whole
    document.
  - /query validates documentId strictly as a UUID before it ever touches
    a path (traversal attempts -> 400), 404s on unknown ids, 400s on
    malformed bodies. /formalize's whole-document mode is unchanged.

No network calls: conftest's autouse fixture hard-fails any unmocked
generate_response, and nothing here consults an LLM at all.
"""

import importlib
import json
import os
import uuid

import pytest

from components import retrieval
from components.retrieval import query_document, retrieve_claims


def _ax(claim_index, english, formal="P(x)", **extra):
    ax = {
        "claim_index": claim_index,
        "segment_index": claim_index,
        "english": english,
        "formal": formal,
    }
    ax.update(extra)
    return ax


# ---------------------------------------------------------------------------
# BM25 relevance
# ---------------------------------------------------------------------------

def test_query_term_retrieves_matching_claims_only():
    axioms = [
        _ax(0, "The proposition is a picture of reality."),
        _ax(1, "Logic pervades the world."),
        _ax(2, "A picture is a model of reality."),
        _ax(3, "Ethics cannot be put into words."),
    ]
    results = retrieve_claims(axioms, "picture")
    retrieved_indices = {ax["claim_index"] for ax, _score in results}
    assert retrieved_indices == {0, 2}
    for _ax_dict, score in results:
        assert score > 0


def test_zero_score_non_matches_excluded_entirely():
    axioms = [
        _ax(0, "Logic pervades the world."),
        _ax(1, "Ethics cannot be put into words."),
    ]
    assert retrieve_claims(axioms, "quasar") == []


def test_top_k_limits_result_count():
    axioms = [_ax(i, f"claim number {i} mentions widget") for i in range(8)]
    results = retrieve_claims(axioms, "widget", top_k=3)
    assert len(results) == 3


def test_empty_query_and_empty_corpus_return_empty():
    axioms = [_ax(0, "Logic pervades the world.")]
    assert retrieve_claims(axioms, "") == []
    assert retrieve_claims(axioms, "   ") == []
    assert retrieve_claims([], "logic") == []


def test_matching_is_case_insensitive_and_token_based():
    axioms = [
        _ax(0, "Logic pervades the world."),
        _ax(1, "Logical atomism is a doctrine."),  # "logic" != "logical"
    ]
    results = retrieve_claims(axioms, "LOGIC")
    assert [ax["claim_index"] for ax, _ in results] == [0]


# ---------------------------------------------------------------------------
# risk-tier-first sorting
# ---------------------------------------------------------------------------

def _tiered_axioms():
    """Four axioms sharing the query token "widget", whose english/formal
    texts drive the rule-based detectors to one tier each:
      - Unformalized: no formal representation at all.
      - High (score 4): negation+connector (2) + strong modal in source
        with no modal in the formal string (2).
      - Medium (score 2): negation+connector only.
      - Low (score 0): no flags at all.
    """
    return [
        _ax(0, "The widget is reliable.", formal="Reliable(widget)"),          # Low
        _ax(1, "The widget must not fail and must not stall.",
            formal="the widget fails"),                                        # High
        _ax(2, "The widget is not broken and is not idle.",
            formal="the widget is not broken and is not idle"),                # Medium
        _ax(3, "The widget exists.", formal=None),                             # Unformalized
    ]


def test_results_sorted_risk_tier_first_unformalized_before_high():
    results = query_document(_tiered_axioms(), "widget", top_k=10)
    assert len(results) == 4
    tiers = [ax["risk_tier"] for ax in results]
    assert tiers == ["Unformalized", "High", "Medium", "Low"]
    # Unformalized strictly precedes High
    assert tiers.index("Unformalized") < tiers.index("High")


def test_ties_within_tier_broken_by_bm25_score_descending():
    # Same tier (Low: no detector fires), same token count, but claim 1
    # contains the query term twice -> higher BM25 score -> first.
    axioms = [
        _ax(0, "widget gadget gizmo", formal="A(x)"),
        _ax(1, "widget widget gizmo", formal="B(x)"),
    ]
    results = query_document(axioms, "widget", top_k=10)
    assert [ax["risk_tier"] for ax in results] == ["Low", "Low"]
    assert [ax["claim_index"] for ax in results] == [1, 0]


def test_stored_formalize_time_tiers_are_reused_not_recomputed():
    # An axiom already annotated at formalize time keeps its stored tier
    # even if re-running the detectors under a different mode would
    # disagree (final_data.json doesn't record the mode it was made with).
    axioms = [
        _ax(0, "Every widget must be tested.", formal="Widget(x) >> Tested(x)",
            risk_tier="Low", risk_flags=[]),
        _ax(1, "The widget is fine.", formal="Fine(widget)"),
    ]
    results = query_document(axioms, "widget", top_k=10)
    stored = next(ax for ax in results if ax["claim_index"] == 0)
    assert stored["risk_tier"] == "Low"
    assert stored["risk_flags"] == []


# ---------------------------------------------------------------------------
# triage runs only on the retrieved subset
# ---------------------------------------------------------------------------

def test_triage_annotates_exactly_the_retrieved_subset(monkeypatch):
    axioms = [
        _ax(0, "The widget is reliable."),
        _ax(1, "The widget is efficient."),
        _ax(2, "Ethics cannot be put into words."),
        _ax(3, "Logic pervades the world."),
        _ax(4, "A picture is a model of reality."),
    ]
    seen = []
    real_annotate = retrieval.annotate_axioms

    def counting_annotate(axs, **kwargs):
        seen.extend(axs)
        return real_annotate(axs, **kwargs)

    monkeypatch.setattr(retrieval, "annotate_axioms", counting_annotate)

    results = query_document(axioms, "widget", top_k=10)

    assert len(results) == 2
    assert len(seen) == len(results)  # annotated count == retrieved count
    assert {ax["claim_index"] for ax in seen} == {0, 1}
    # nothing outside the retrieved set was annotated
    for ax in axioms[2:]:
        assert "risk_tier" not in ax and "risk_flags" not in ax
    # everything returned carries a tier
    for ax in results:
        assert ax["risk_tier"] in ("High", "Medium", "Low", "Unformalized")


# ---------------------------------------------------------------------------
# POST /query endpoint
# ---------------------------------------------------------------------------

@pytest.fixture
def flask_app(monkeypatch, tmp_path):
    """app.py builds UPLOAD_DIR/OUTPUT_DIR from DATA_DIR at import time, so
    set DATA_DIR to a per-test tmp dir and (re)load the module fresh."""
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    import app as app_module
    importlib.reload(app_module)
    app_module.app.config["TESTING"] = True
    yield app_module


@pytest.fixture
def client(flask_app):
    return flask_app.app.test_client()


def _store_document(flask_app, axioms):
    document_id = str(uuid.uuid4())
    path = os.path.join(flask_app.OUTPUT_DIR,
                        f"{document_id}_final_data.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"axioms": axioms, "unformalized_count": 0}, f)
    return document_id


def test_query_endpoint_happy_path(client, flask_app):
    document_id = _store_document(flask_app, _tiered_axioms())
    resp = client.post("/query", json={"documentId": document_id,
                                       "query": "widget"})
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["documentId"] == document_id
    assert body["query"] == "widget"
    tiers = [ax["risk_tier"] for ax in body["results"]]
    assert tiers == ["Unformalized", "High", "Medium", "Low"]


def test_query_endpoint_respects_top_k(client, flask_app):
    axioms = [_ax(i, f"claim {i} about widget") for i in range(6)]
    document_id = _store_document(flask_app, axioms)
    resp = client.post("/query", json={"documentId": document_id,
                                       "query": "widget", "topK": 2})
    assert resp.status_code == 200
    assert len(resp.get_json()["results"]) == 2


def test_query_endpoint_unknown_document_id_404(client):
    resp = client.post("/query", json={"documentId": str(uuid.uuid4()),
                                       "query": "widget"})
    assert resp.status_code == 404


@pytest.mark.parametrize("bad_id", [
    "../app",
    "..%2fapp",
    "..%2f..%2fserver%2fapp.py",
    "%2e%2e%2f",
    "..\\app",
    "/etc/passwd",
    "e5c122e2-58a1-4cbd-a09a-4d5f2a9b0f31/../../x",  # valid uuid prefix
    "not-a-uuid",
    "",
    123,
    None,
    ["e5c122e2-58a1-4cbd-a09a-4d5f2a9b0f31"],
])
def test_query_endpoint_rejects_invalid_document_id_400(client, bad_id):
    resp = client.post("/query", json={"documentId": bad_id,
                                       "query": "widget"})
    assert resp.status_code == 400


def test_query_endpoint_traversal_attempt_cannot_touch_files(client, flask_app):
    # Even with a real file sitting outside OUTPUT_DIR at the traversal
    # target, the request dies at validation with 400, not 404-after-probe.
    target = os.path.join(os.path.dirname(flask_app.OUTPUT_DIR),
                          "secret_final_data.json")
    with open(target, "w", encoding="utf-8") as f:
        json.dump({"axioms": [_ax(0, "secret widget")]}, f)
    resp = client.post("/query", json={"documentId": "../secret",
                                       "query": "widget"})
    assert resp.status_code == 400
    assert b"secret" not in resp.data


@pytest.mark.parametrize("body", [
    None,                                   # no JSON at all
    {},                                     # empty
    {"query": "widget"},                    # missing documentId
    {"documentId": None},                   # missing query
    {"documentId": None, "query": 5},       # non-string query
])
def test_query_endpoint_malformed_body_400(client, body):
    if body is None:
        resp = client.post("/query", data="not json",
                           content_type="text/plain")
    else:
        if body.get("documentId") is None and "documentId" in body:
            body["documentId"] = str(uuid.uuid4())
        resp = client.post("/query", json=body)
    assert resp.status_code == 400


@pytest.mark.parametrize("bad_top_k", ["abc", -1, 0, [5], {}])
def test_query_endpoint_invalid_top_k_400(client, flask_app, bad_top_k):
    document_id = _store_document(flask_app, [_ax(0, "widget")])
    resp = client.post("/query", json={"documentId": document_id,
                                       "query": "widget",
                                       "topK": bad_top_k})
    assert resp.status_code == 400


def test_formalize_returns_document_id_and_query_round_trips(
        client, flask_app, monkeypatch, tmp_path):
    """/formalize's response carries documentId (main.formalize_file's
    output_id), and that id immediately works against POST /query --
    while the whole-document response ("axioms": everything) is unchanged.
    """
    import re as _re
    from reportlab.lib.pagesizes import LETTER
    from reportlab.pdfgen import canvas
    from components import logic_formalization, response_parsing
    from conftest import FakeResponse

    sentences = ["The widget is reliable.", "Ethics cannot be put into words."]
    pdf_path = tmp_path / "doc.pdf"
    c = canvas.Canvas(str(pdf_path), pagesize=LETTER)
    y = 700
    for s in sentences:
        c.drawString(72, y, s)
        y -= 20
    c.save()

    def fake_extract(prompt, *args, **kwargs):
        seg_idx = int(_re.search(r"Segment index: (\d+)", prompt).group(1))
        sent = _re.search(r'Segment text: "(.*)"', prompt, _re.DOTALL).group(1).strip()
        return FakeResponse(json.dumps({"segment_index": seg_idx, "claims": [sent]}))

    def fake_formalize(prompt, *args, **kwargs):
        indices = [int(m) for m in _re.findall(r"\(claim_index (\d+)\)", prompt)]
        return FakeResponse(json.dumps(
            {"axioms": [{"claim_index": i, "formal": f"P{i}(x)"} for i in indices]}))

    monkeypatch.setattr(response_parsing, "generate_response", fake_extract)
    monkeypatch.setattr(logic_formalization, "generate_response", fake_formalize)

    # upload through the real endpoint so the file lands in UPLOAD_DIR
    with open(pdf_path, "rb") as f:
        up = client.post("/upload", data={"file": (f, "doc.pdf")},
                         content_type="multipart/form-data")
    assert up.status_code == 200

    resp = client.post("/formalize", json={"fileId": up.get_json()["fileId"],
                                           "formatType": "logic",
                                           "useParallel": False})
    assert resp.status_code == 200
    body = resp.get_json()
    document_id = body["documentId"]
    assert isinstance(document_id, str) and uuid.UUID(document_id)
    # whole-document (batch) mode unchanged: every axiom present
    assert len(body["axioms"]) == len(sentences)

    q = client.post("/query", json={"documentId": document_id,
                                    "query": "widget"})
    assert q.status_code == 200
    results = q.get_json()["results"]
    assert len(results) == 1
    assert "widget" in results[0]["english"].lower()
    assert results[0]["risk_tier"] in ("High", "Medium", "Low", "Unformalized")


def test_query_endpoint_response_contains_only_retrieved_claims(client, flask_app):
    axioms = [
        _ax(0, "The widget is reliable."),
        _ax(1, "Ethics cannot be put into words."),
    ]
    document_id = _store_document(flask_app, axioms)
    resp = client.post("/query", json={"documentId": document_id,
                                       "query": "widget"})
    assert resp.status_code == 200
    results = resp.get_json()["results"]
    assert [ax["claim_index"] for ax in results] == [0]
