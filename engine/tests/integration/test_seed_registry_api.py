from __future__ import annotations

from fastapi.testclient import TestClient
from wittgenstein.api.app import app

client = TestClient(app)


def test_health():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_list_mechanisms():
    response = client.get("/registry/mechanisms")
    assert response.status_code == 200
    body = response.json()
    assert len(body) == 18
    assert any(m["id"] == "RET_HARD_DISTRACTOR" for m in body)


def test_get_mechanism():
    response = client.get("/registry/mechanisms/RET_HARD_DISTRACTOR")
    assert response.status_code == 200
    # manifest_conditioned_transfer, not externally_established: only one A2-grade record
    # is linked, and the two-path evidence-threshold rule requires either one A1 study or
    # >=2 independent A1/A2 studies -- see docs/evidence-grading.md ("Evidence thresholds").
    assert response.json()["epistemic_status"] == "manifest_conditioned_transfer"


def test_get_unknown_mechanism_404():
    response = client.get("/registry/mechanisms/NOT_A_REAL_MECHANISM")
    assert response.status_code == 404


def test_get_dossier():
    response = client.get("/registry/mechanisms/PACK_OMISSION_OR_TRUNCATION/dossier")
    assert response.status_code == 200
    body = response.json()
    assert "Open evidence gaps" in body["markdown"]


def test_manifest_validate_endpoint_accepts_minimal_manifest():
    response = client.post(
        "/manifests/validate",
        json={
            "manifest_id": "M1",
            "system_name": "sys",
            "system_version": "0.1",
            "created_at": "2026-09-02T00:00:00Z",
        },
    )
    assert response.status_code == 200
    assert response.json()["valid"] is True


def test_manifest_validate_endpoint_rejects_bad_payload():
    response = client.post("/manifests/validate", json={"manifest_id": "M1"})
    assert response.status_code == 200
    assert response.json()["valid"] is False


def test_trace_validate_endpoint():
    response = client.post(
        "/traces/validate",
        json={
            "trace_id": "T1",
            "manifest_id": "M1",
            "query": "q",
            "query_timestamp": "2026-09-02T00:00:00Z",
            "trace_status": "complete",
        },
    )
    assert response.status_code == 200
    assert response.json()["valid"] is True
