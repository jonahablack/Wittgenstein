"""WITTGENSTEIN_NLI=off: the meaning-level model is never loaded, and users are told the
checks are turned off (never shown as passed)."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from wittgenstein.api.app import app
from wittgenstein.live import nli


@pytest.fixture()
def off(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("WITTGENSTEIN_NLI", "off")


def test_model_is_not_loaded_and_the_reason_is_given(off) -> None:  # noqa: ANN001
    assert nli.disabled() and nli.model() is None
    assert nli.load_error() == nli.DISABLED_NOTE and "production" in nli.DISABLED_NOTE


def test_config_and_api_tell_the_user(off) -> None:  # noqa: ANN001
    c = TestClient(app)
    assert c.get("/live/config").json()["meaning_checks"] == {"enabled": False, "note": nli.DISABLED_NOTE}
    r = c.post(
        "/v1/check",
        json={
            "query": "What is the starting dose?",
            "candidates": [{"id": "a", "text": "The recommended starting dosage is 500 mg once daily."}],
            "answer": "Start at 500 mg once a day with dinner, as the label suggests. [1]",
        },
    ).json()
    assert nli.DISABLED_NOTE in r["access"]["notes"]
    meaning = [ck for ck in r["checks"] if ck["label"].endswith("(meaning-level)")]
    assert meaning and meaning[0]["outcome"] == "not_applicable" and meaning[0]["detail"] == nli.DISABLED_NOTE


def test_on_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("WITTGENSTEIN_NLI", raising=False)
    assert not nli.disabled()
    assert TestClient(app).get("/live/config").json()["meaning_checks"]["enabled"] is True
