"""`wittgenstein watch` renders the feed in the terminal: the list, and for the selected
answer its sentences, what is worth a look, and what to check."""

from __future__ import annotations

from rich.console import Console

from wittgenstein.tui import _detail, _list

AUDITS = [
    {"audit_id": "a1", "created": "2026-11-05T17:59:28", "query": "What is the maximum dose?", "source": "my-app",
     "needs_review": True},
    {"audit_id": "a2", "created": "2026-11-05T17:59:20", "query": "What is the starting dose?", "source": "my-app",
     "needs_review": False},
]  # fmt: skip
FULL = {
    "request": {"query": "What is the maximum dose?", "answer": "The maximum dose is 2,550 mg. [1]"},
    "report": {
        "summary": {
            "sentences": [
                {"text": "The maximum dose is 2,550 mg.", "status": "review",
                 "flags": [{"title": "“2,550 mg” doesn't appear in the cited source"}]},
            ]
        },
        "receipt": {"candidates": 3, "in_prompt": 1, "checks_passed": 12, "checks_run": 14},
        "flags": [
            {"disposition": "needs_review", "title": "“2,550 mg” doesn't appear in the cited source",
             "observation": "The cited passage gives 2,000 mg.", "what_to_check": "Passage [1]."},
            {"disposition": "informational", "title": "More passages than this model reliably uses"},
        ],
    },
}  # fmt: skip


def _text(renderable) -> str:  # noqa: ANN001
    c = Console(width=100, record=True, color_system=None)
    c.print(renderable)
    return c.export_text()


def test_list_marks_what_needs_review() -> None:
    out = _text(_list(AUDITS, 0, 5))
    assert "⚠" in out and "✓" in out and "What is the maximum dose?" in out and "my-app" in out


def test_detail_shows_sentences_flags_and_what_to_check() -> None:
    out = _text(_detail(FULL))
    assert "The maximum dose is 2,550 mg." in out
    assert "Worth a look" in out and "Check: Passage [1]." in out
    assert "Good to know" in out and "More passages than this model reliably uses" in out
    assert "1 in the prompt" in out
