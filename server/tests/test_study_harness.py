"""Study harness tests.

Deliberately builds a bare Flask() and registers only study_bp -- it never
imports server/app.py, so these tests cannot couple to concurrent edits of
the main product routes. All filesystem state (pipeline outputs, ground
truth, study config, session storage) lives in a per-test tmp_path wired
in through DATA_DIR/STUDY_CONFIG, exactly the env contract the module
documents. No LLM is ever touched: query answers are pre-written config.
"""

import json
import os
import uuid

import pytest
from flask import Flask

from study_harness.routes import study_bp

CLINICAL_DOC = "doc-clinical"
LEGAL_DOC = "doc-legal"

# claim_index -> risk_tier for the clinical fixture document. Deliberately
# out of tier order by claim_index so sorting is observable.
CLINICAL_TIERS = {
    0: "Low",
    1: "High",
    2: "Medium",
    3: "Unformalized",
    4: "Low",
    5: "High",
}
# Triaged serve order: Unformalized, High, Medium, Low (claim_index ties).
CLINICAL_TRIAGED_ORDER = [3, 1, 5, 2, 0, 4]
CLINICAL_SEEDED = [1, 4]

LEGAL_TIERS = {10: "Medium", 11: "Low", 12: "High", 13: "Unformalized"}
LEGAL_SEEDED = [12]


def _axiom(claim_index, tier):
    return {
        "claim_index": claim_index,
        "segment_index": claim_index // 2,
        "english": f"Claim number {claim_index}.",
        "formal": f"P{claim_index}(x)",
        "id": f"ax{claim_index:04d}",
        "flag": "none",
        "risk_flags": (
            [] if tier == "Low"
            else [{"type": "test_flag", "reason": f"reason {claim_index}"}]
        ),
        "risk_tier": tier,
    }


@pytest.fixture
def study_env(tmp_path, monkeypatch):
    """Pipeline outputs + ground truth + study config in a temp DATA_DIR."""
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    outputs = tmp_path / "outputs"
    outputs.mkdir()

    for doc_id, tiers in ((CLINICAL_DOC, CLINICAL_TIERS),
                          (LEGAL_DOC, LEGAL_TIERS)):
        (outputs / f"{doc_id}_final_data.json").write_text(json.dumps({
            "axioms": [_axiom(ci, tier) for ci, tier in tiers.items()],
            "unformalized_count": sum(
                1 for t in tiers.values() if t == "Unformalized"),
        }))

    (tmp_path / "clinical_gt.json").write_text(
        json.dumps({"seeded_error_claim_indices": CLINICAL_SEEDED}))
    (tmp_path / "legal_gt.json").write_text(
        json.dumps({"seeded_error_claim_indices": LEGAL_SEEDED}))

    config = {
        "cohorts": {
            # A single general-population cohort (config.COHORTS) sourced
            # from two pipeline documents -- CLINICAL_DOC / LEGAL_DOC are
            # just document_id labels here, not separate cohorts (see
            # study_harness/README.md's single-cohort design). Each query's
            # explicit document_id scopes it to its own document within the
            # shared cohort (README's "documents" rule).
            "general": {
                "documents": [
                    {"document_id": CLINICAL_DOC,
                     "ground_truth_file": "clinical_gt.json"},
                    {"document_id": LEGAL_DOC,
                     "ground_truth_file": "legal_gt.json"},
                ],
                "queries": [
                    {
                        "query_id": "q1",
                        "query": "What does the protocol specify?",
                        "classification": "clean",
                        "answer": "The protocol specifies 5 mg twice daily.",
                        "source_claim_indices": [0, 2],
                        "document_id": CLINICAL_DOC,
                    },
                    {
                        "query_id": "q2",
                        "query": "Is the contraindication absolute?",
                        "classification": "compromised",
                        "answer": "No, it is only relative.",
                        "source_claim_indices": [1, 3, 5],
                        "weak_source_claim_index": 3,
                        "document_id": CLINICAL_DOC,
                    },
                    {
                        "query_id": "qL1",
                        "query": "Does the clause survive termination?",
                        "classification": "compromised",
                        "answer": "Yes, it survives indefinitely.",
                        "source_claim_indices": [10, 12],
                        "weak_source_claim_index": 12,
                        "document_id": LEGAL_DOC,
                    },
                ],
            },
        }
    }
    config_path = tmp_path / "study_config.json"
    config_path.write_text(json.dumps(config))
    monkeypatch.setenv("STUDY_CONFIG", str(config_path))
    return tmp_path


@pytest.fixture
def client(study_env):
    app = Flask(__name__)
    app.config["TESTING"] = True
    app.register_blueprint(study_bp)
    return app.test_client()


def _create(client, participant_id="P01", cohort="general",
            condition="blind", **extra):
    resp = client.post("/study/admin/sessions", json={
        "participant_id": participant_id,
        "cohort": cohort,
        "condition": condition,
        **extra,
    })
    return resp


def _decide(client, sid, item_id, decision="approved", confidence=3,
            **extra):
    return client.post(f"/study/sessions/{sid}/decisions", json={
        "item_id": item_id,
        "decision": decision,
        "confidence": confidence,
        **extra,
    })


# ---------------------------------------------------------------------------
# session creation

def test_session_creation_all_cohorts_and_conditions(client, study_env):
    # Single "general" cohort, two documents (see study_env's "documents"
    # list) selected via document_id -- there is no longer a second cohort
    # to iterate over.
    expected_counts = {CLINICAL_DOC: 6 + 2, LEGAL_DOC: 4 + 1}
    seen_ids = set()
    for doc_id in (CLINICAL_DOC, LEGAL_DOC):
        for condition in ("blind", "triaged"):
            resp = _create(client, participant_id=f"P-{doc_id}-{condition}",
                           cohort="general", condition=condition,
                           document_id=doc_id)
            assert resp.status_code == 201, resp.get_json()
            body = resp.get_json()
            assert body["cohort"] == "general"
            assert body["condition"] == condition
            assert body["participant_id"] == f"P-{doc_id}-{condition}"
            assert body["document_id"] == doc_id
            assert body["item_count"] == expected_counts[doc_id]
            sid = body["session_id"]
            uuid.UUID(sid)  # must be a real uuid
            assert sid not in seen_ids
            seen_ids.add(sid)
            # persisted on disk under study_data/, scoped by session_id
            assert os.path.isfile(
                str(study_env / "study_data" / f"{sid}.json"))


def test_session_creation_rejects_bad_input(client):
    assert _create(client, cohort="botany").status_code == 400
    assert _create(client, condition="occluded").status_code == 400
    assert _create(client, participant_id="  ").status_code == 400


def test_unknown_session_is_404(client):
    assert client.get("/study/sessions/nope/items").status_code == 404
    assert client.get("/study/sessions/nope/items/next").status_code == 404
    assert client.get("/study/sessions/nope/export").status_code == 404
    assert _decide(client, "nope", "claim_0").status_code == 404


# ---------------------------------------------------------------------------
# blind condition

def test_blind_strips_risk_fields_and_preserves_claim_index_order(client):
    sid = _create(client, condition="blind").get_json()["session_id"]
    resp = client.get(f"/study/sessions/{sid}/items")
    assert resp.status_code == 200

    raw = resp.get_data(as_text=True)
    assert "risk_tier" not in raw
    assert "risk_flags" not in raw
    assert "Unformalized" not in raw

    body = resp.get_json()
    batch = [it for it in body["items"] if it["item_type"] == "batch_claim"]
    assert [it["claim_index"] for it in batch] == [0, 1, 2, 3, 4, 5]

    # query sources are blinded too, and in claim_index order
    q2 = next(it for it in body["items"] if it["item_id"] == "query_q2")
    assert [s["claim_index"] for s in q2["sources"]] == [1, 3, 5]
    for s in q2["sources"]:
        assert "risk_tier" not in s and "risk_flags" not in s

    # substance still present for the task
    assert batch[0]["english"] == "Claim number 0."
    assert q2["answer"] == "No, it is only relative."

    # the single-item endpoint is blinded the same way
    nxt = client.get(f"/study/sessions/{sid}/items/next")
    assert "risk_tier" not in nxt.get_data(as_text=True)
    assert nxt.get_json()["item"]["item_id"] == "claim_0"


def test_participant_views_never_leak_ground_truth(client):
    for condition in ("blind", "triaged"):
        sid = _create(client, condition=condition).get_json()["session_id"]
        raw = client.get(
            f"/study/sessions/{sid}/items").get_data(as_text=True)
        assert "ground_truth_label" not in raw
        assert "seeded_error" not in raw
        assert "classification" not in raw
        assert "weak_source_claim_index" not in raw


# ---------------------------------------------------------------------------
# triaged condition

def test_triaged_includes_tiers_and_sorts_unformalized_high_first(client):
    sid = _create(client, condition="triaged").get_json()["session_id"]
    body = client.get(f"/study/sessions/{sid}/items").get_json()

    batch = [it for it in body["items"] if it["item_type"] == "batch_claim"]
    assert [it["claim_index"] for it in batch] == CLINICAL_TRIAGED_ORDER
    # tiers/flags pass through from the pipeline verbatim
    assert batch[0]["risk_tier"] == "Unformalized"
    assert batch[1]["risk_tier"] == "High"
    for it in batch:
        assert it["risk_tier"] == CLINICAL_TIERS[it["claim_index"]]
        assert "risk_flags" in it

    # query sources risk-tiered and sorted the same way
    q2 = next(it for it in body["items"] if it["item_id"] == "query_q2")
    assert [s["claim_index"] for s in q2["sources"]] == [3, 1, 5]
    assert [s["risk_tier"] for s in q2["sources"]] == \
        ["Unformalized", "High", "High"]

    # queries always follow the batch
    assert [it["item_type"] for it in body["items"]] == \
        ["batch_claim"] * 6 + ["query_verification"] * 2

    # next-item follows triaged order
    nxt = client.get(f"/study/sessions/{sid}/items/next").get_json()
    assert nxt["item"]["item_id"] == "claim_3"


# ---------------------------------------------------------------------------
# decisions and timing

def test_decision_recording_with_timestamps(client):
    sid = _create(client, condition="blind").get_json()["session_id"]
    nxt = client.get(f"/study/sessions/{sid}/items/next").get_json()
    item_id = nxt["item"]["item_id"]
    assert item_id == "claim_0"

    resp = _decide(client, sid, item_id, decision="rejected", confidence=5)
    assert resp.status_code == 201, resp.get_json()
    body = resp.get_json()
    assert body["decision"] == "rejected"
    assert body["confidence"] == 5
    assert body["time_to_decision"] > 0

    stored = client.get(f"/study/admin/sessions/{sid}").get_json()
    it = next(i for i in stored["items"] if i["item_id"] == item_id)
    assert it["first_viewed_at"] is not None
    assert it["decided_at"] > it["first_viewed_at"]
    assert it["time_to_decision"] == \
        pytest.approx(it["decided_at"] - it["first_viewed_at"])

    # next now advances past the decided item
    nxt2 = client.get(f"/study/sessions/{sid}/items/next").get_json()
    assert nxt2["item"]["item_id"] == "claim_1"


def test_decision_requires_prior_view(client):
    sid = _create(client).get_json()["session_id"]
    resp = _decide(client, sid, "claim_2")
    assert resp.status_code == 409


def test_duplicate_decision_conflicts(client):
    sid = _create(client).get_json()["session_id"]
    client.get(f"/study/sessions/{sid}/items")
    assert _decide(client, sid, "claim_0").status_code == 201
    assert _decide(client, sid, "claim_0").status_code == 409


def test_invalid_decision_and_confidence_rejected(client):
    sid = _create(client).get_json()["session_id"]
    client.get(f"/study/sessions/{sid}/items")
    assert _decide(client, sid, "claim_0",
                   decision="maybe").status_code == 400
    for bad_conf in (0, 6, "3", 3.5, True, None):
        assert _decide(client, sid, "claim_0",
                       confidence=bad_conf).status_code == 400
    assert _decide(client, sid, "no_such_item").status_code == 404


# ---------------------------------------------------------------------------
# weak-source identification

def test_weak_source_required_only_when_flagging_query_items(client):
    sid = _create(client, condition="triaged").get_json()["session_id"]
    client.get(f"/study/sessions/{sid}/items")

    # flagged query item without identified_weak_source -> 400
    resp = _decide(client, sid, "query_q2", decision="flagged")
    assert resp.status_code == 400
    assert "identified_weak_source" in resp.get_json()["error"]

    # must be one of the item's own sources
    assert _decide(client, sid, "query_q2", decision="flagged",
                   identified_weak_source=99).status_code == 400

    # valid identification is recorded
    resp = _decide(client, sid, "query_q2", decision="flagged",
                   confidence=2, identified_weak_source=3)
    assert resp.status_code == 201
    assert resp.get_json()["identified_weak_source"] == 3

    # approving a query item needs no weak source
    assert _decide(client, sid, "query_q1").status_code == 201

    # flagging a *batch* item needs no weak source
    assert _decide(client, sid, "claim_3",
                   decision="flagged").status_code == 201


# ---------------------------------------------------------------------------
# export

EXPORT_TOP_KEYS = {"participant_id", "cohort", "condition", "document_id",
                   "items"}
EXPORT_ITEM_KEYS = {"item_id", "item_type", "decision", "confidence",
                    "time_to_decision", "ground_truth_label",
                    "identified_weak_source"}


def test_export_record_shape_and_ground_truth_labels(client, study_env):
    sid = _create(client, participant_id="P42",
                  condition="blind").get_json()["session_id"]
    items = client.get(f"/study/sessions/{sid}/items").get_json()["items"]
    for it in items:
        weak = ({"identified_weak_source": 1}
                if it["item_id"] == "query_q2" else {})
        assert _decide(client, sid, it["item_id"],
                       decision="flagged" if it["item_id"] == "query_q2"
                       else "approved",
                       confidence=4, **weak).status_code == 201

    resp = client.get(f"/study/sessions/{sid}/export")
    assert resp.status_code == 200
    record = resp.get_json()

    assert set(record.keys()) == EXPORT_TOP_KEYS
    assert record["participant_id"] == "P42"
    assert record["cohort"] == "general"
    assert record["condition"] == "blind"
    assert record["document_id"] == CLINICAL_DOC
    assert len(record["items"]) == 8

    labels = {}
    for item in record["items"]:
        assert set(item.keys()) == EXPORT_ITEM_KEYS
        assert item["decision"] in ("approved", "flagged")
        assert item["confidence"] == 4
        assert item["time_to_decision"] > 0
        assert item["item_type"] in ("batch_claim", "query_verification")
        labels[item["item_id"]] = item["ground_truth_label"]

    for ci in range(6):
        expected = "seeded_error" if ci in CLINICAL_SEEDED else "clean"
        assert labels[f"claim_{ci}"] == expected
    assert labels["query_q1"] == "clean"
    assert labels["query_q2"] == "compromised"
    q2 = next(i for i in record["items"] if i["item_id"] == "query_q2")
    assert q2["identified_weak_source"] == 1
    assert q2["item_type"] == "query_verification"

    # export persisted, scoped by session_id
    export_path = study_env / "study_data" / "exports" / f"{sid}_export.json"
    assert export_path.is_file()
    assert json.loads(export_path.read_text()) == record


def test_export_includes_undecided_items_with_null_fields(client):
    sid = _create(client).get_json()["session_id"]
    record = client.get(f"/study/sessions/{sid}/export").get_json()
    assert len(record["items"]) == 8
    for item in record["items"]:
        assert set(item.keys()) == EXPORT_ITEM_KEYS
        assert item["decision"] is None
        assert item["confidence"] is None
        assert item["time_to_decision"] is None
        assert item["ground_truth_label"] is not None


# ---------------------------------------------------------------------------
# concurrency / isolation

def test_concurrent_sessions_do_not_collide_on_disk(client, study_env):
    # Same cohort, two different documents within it (see study_env) --
    # concurrent sessions can still target different documents.
    sid_a = _create(client, participant_id="PA",
                    condition="blind").get_json()["session_id"]
    sid_b = _create(client, participant_id="PB", condition="triaged",
                    document_id=LEGAL_DOC).get_json()["session_id"]
    assert sid_a != sid_b

    # interleave activity across the two sessions
    client.get(f"/study/sessions/{sid_a}/items")
    client.get(f"/study/sessions/{sid_b}/items")
    assert _decide(client, sid_a, "claim_0",
                   decision="approved").status_code == 201
    assert _decide(client, sid_b, "claim_12",
                   decision="rejected").status_code == 201
    assert _decide(client, sid_a, "claim_1",
                   decision="flagged").status_code == 201

    files = {f for f in os.listdir(str(study_env / "study_data"))
             if f.endswith(".json")}
    assert files == {f"{sid_a}.json", f"{sid_b}.json"}

    export_a = client.get(f"/study/sessions/{sid_a}/export").get_json()
    export_b = client.get(f"/study/sessions/{sid_b}/export").get_json()
    assert export_a["participant_id"] == "PA"
    assert export_b["participant_id"] == "PB"
    assert len(export_a["items"]) == 8
    assert len(export_b["items"]) == 5

    decided_a = {i["item_id"]: i["decision"] for i in export_a["items"]
                 if i["decision"]}
    decided_b = {i["item_id"]: i["decision"] for i in export_b["items"]
                 if i["decision"]}
    assert decided_a == {"claim_0": "approved", "claim_1": "flagged"}
    assert decided_b == {"claim_12": "rejected"}
