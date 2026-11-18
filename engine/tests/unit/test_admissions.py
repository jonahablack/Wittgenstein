"""Admissions review: an AI summary checked against the (synthetic) application."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from wittgenstein.admissions import check_summary, sections
from wittgenstein.api.app import app
from wittgenstein.live import nli

FIX = Path(__file__).resolve().parents[2] / "data" / "fixtures" / "admissions_synthetic"
SPEC = json.loads((FIX / "summaries.json").read_text())["applicants"]


@pytest.fixture(autouse=True)
def no_model(monkeypatch):  # noqa: ANN001, ANN201
    # The admissions checks are rule-based; keep the meaning-level model out of unit tests.
    monkeypatch.setenv("WITTGENSTEIN_NLI", "off")


def run(aid: str, summary: str | None = None) -> dict:
    docs = {p.name: p.read_text() for p in sorted((FIX / aid).glob("*.md"))}
    refs = [r for r, _ in sections(docs)]
    cited = [next(r for r in refs if r == c or r.startswith(c)) for c in SPEC[aid]["passages"]]
    return check_summary(docs, summary or SPEC[aid]["summary"], cited)


def kinds(result: dict) -> list[str]:
    return [f["kind"] for f in result["flags"] if f["disposition"] == "needs_review"]


def test_inferred_ethnicity_goes_to_a_person() -> None:
    r = run("applicant-0582")
    f = next(f for f in r["flags"] if f["kind"] == "protected_characteristic")
    assert f["disposition"] == "needs_review" and f["metrics"]["stated_in_file"] is False
    assert "inferred" in f["observation"]


def test_first_generation_is_not_a_protected_characteristic_flag() -> None:
    r = run("applicant-0582", "The applicant is a first-generation college student [4].")
    assert "protected_characteristic" not in kinds(r)


def test_file_disagreeing_with_itself_is_surfaced() -> None:
    f = next(f for f in run("applicant-0733")["flags"] if f["kind"] == "source_figures_disagree")
    assert "800 hours in the experiences entry" in f["observation"]
    assert "2,000 hours in the secondary essay" in f["observation"]


def test_setback_without_the_files_explanation_is_surfaced() -> None:
    f = next(f for f in run("applicant-0417")["flags"] if f["kind"] == "context_omitted")
    assert "diagnosed" in f["observation"]


def test_explained_setback_is_not_flagged() -> None:
    s = "Their GPA fell to 3.10 in junior year while they cared for their mother during chemotherapy [3]."
    assert "context_omitted" not in kinds(run("applicant-0417", s))


def test_inflated_hours_are_caught_and_search_checks_are_skipped() -> None:
    r = run("applicant-0417")
    assert "quantity_mismatch" in kinds(r)
    assert not {"facet_uncovered", "facet_dominance"} & set(kinds(r))
    # The applicant number is the file's label, not a claim to verify.
    assert not any("0417" in f["title"] for f in r["flags"])


def test_nothing_is_scored_or_decided() -> None:
    r = run("applicant-0733")
    assert not {"score", "rank", "recommendation"} & set(r)
    assert any("No score" in s for s in r["admissions"]["not_done"])


def test_endpoint() -> None:
    docs = {p.name: p.read_text() for p in sorted((FIX / "applicant-0733").glob("*.md"))}
    c = TestClient(app)
    ok = c.post(
        "/live/admissions/check",
        json={
            "documents": docs,
            "summary": SPEC["applicant-0733"]["summary"],
            "citations": SPEC["applicant-0733"]["passages"],
        },
    )
    assert ok.status_code == 200 and "source_figures_disagree" in kinds(ok.json())
    bad = c.post("/live/admissions/check", json={"documents": docs, "summary": "x [1].", "citations": ["nope.md"]})
    assert bad.status_code == 422
    assert nli.disabled()
