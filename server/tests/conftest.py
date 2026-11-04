"""Test bootstrap: make server/ importable exactly the way the app runs
(app.py does `from components.main import ...` with server/ as the root),
and hard-fail any test that would hit the real OpenAI API.

No test in this suite may ever perform a network call. Individual tests
monkeypatch `generate_response` on the specific component module under
test; the autouse fixture below is a belt-and-braces guard that replaces
api_call.generate_response itself with a function that raises, so an
unmocked path fails loudly instead of silently spending API credit.
"""

import os
import sys

import pytest

SERVER_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if SERVER_DIR not in sys.path:
    sys.path.insert(0, SERVER_DIR)


@pytest.fixture(autouse=True)
def _no_real_llm_calls(monkeypatch):
    """Any code path reaching the real generate_response is a test bug.

    The component modules import generate_response by value
    (`from api_call import generate_response`), so patching api_call alone
    would not intercept their calls -- patch each module's own reference.
    Test-level monkeypatch.setattr calls override these for the module
    actually under test.
    """
    import api_call
    from components import logic_formalization, response_parsing

    def _forbidden(*args, **kwargs):
        raise AssertionError(
            "Test attempted a real LLM call via generate_response; "
            "stub generate_response on the component module under test."
        )

    monkeypatch.setattr(api_call, "generate_response", _forbidden)
    monkeypatch.setattr(response_parsing, "generate_response", _forbidden)
    monkeypatch.setattr(logic_formalization, "generate_response", _forbidden)
    yield


@pytest.fixture(autouse=True)
def _fast_sleep(monkeypatch):
    """The extraction paths pace themselves with time.sleep between LLM
    calls; with a stubbed LLM that pacing is pure dead time in tests."""
    import time
    monkeypatch.setattr(time, "sleep", lambda *_: None)


class FakeResponse:
    """Minimal stand-in for the OpenAI message object the pipeline uses:
    the only attribute any component reads is `.content`."""

    def __init__(self, content):
        self.content = content
