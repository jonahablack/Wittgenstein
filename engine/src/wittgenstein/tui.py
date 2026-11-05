"""`wittgenstein watch`: the live feed of checked answers, in the terminal.

The same feed the Pipeline view shows (GET /v1/audits), without a browser: each answer
from the user's RAG app, whether it's worth a look, and for the selected one, every
sentence, every flag, and what to check. Keys: up/down (or j/k) to select, q to quit.
Without a terminal (piped to a file, a CI log) it prints each new answer as a line
instead (`--plain`).
"""

from __future__ import annotations

import contextlib
import json
import os
import select
import sys
import threading
import time
import urllib.error
import urllib.request
from typing import Any

from rich.console import Console, Group
from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

POLL_SECONDS = 2.0


def _get(url: str, timeout: float = 5.0) -> Any:
    with urllib.request.urlopen(url, timeout=timeout) as r:
        return json.loads(r.read())


class _Keys:
    """Single keypresses without Enter (POSIX: cbreak mode; Windows: msvcrt)."""

    def __init__(self) -> None:
        self.pressed: list[str] = []
        self._stop = threading.Event()
        self._fd: int | None = None
        self._old: Any = None

    def __enter__(self) -> _Keys:
        if os.name != "nt":
            import termios
            import tty

            self._fd = sys.stdin.fileno()
            self._old = termios.tcgetattr(self._fd)
            tty.setcbreak(self._fd)
        threading.Thread(target=self._read, daemon=True).start()
        return self

    def __exit__(self, *exc: object) -> None:
        self._stop.set()
        if self._fd is not None:
            import termios

            termios.tcsetattr(self._fd, termios.TCSADRAIN, self._old)

    def _read(self) -> None:
        while not self._stop.is_set():
            if os.name == "nt":
                import msvcrt

                if msvcrt.kbhit():  # type: ignore[attr-defined]
                    ch = msvcrt.getwch()  # type: ignore[attr-defined]
                    if ch in ("\x00", "\xe0"):
                        ch = {"H": "up", "P": "down"}.get(msvcrt.getwch(), "")  # type: ignore[attr-defined]
                    self.pressed.append(ch)
                time.sleep(0.03)
                continue
            r, _, _ = select.select([sys.stdin], [], [], 0.1)
            if not r:
                continue
            ch = sys.stdin.read(1)
            if ch == "\x1b":
                seq = sys.stdin.read(2)
                ch = {"[A": "up", "[B": "down"}.get(seq, "")
            self.pressed.append(ch)


def _when(iso: str) -> str:
    return iso[11:19] if len(iso) >= 19 else iso


def _row_icon(a: dict[str, Any]) -> Text:
    return Text("⚠", style="bold yellow") if a.get("needs_review") else Text("✓", style="green")


def _list(audits: list[dict[str, Any]], sel: int, height: int) -> Table:
    t = Table.grid(padding=(0, 1), expand=True)
    t.add_column(width=1)
    t.add_column(width=8, style="dim")
    t.add_column(ratio=1, no_wrap=True, overflow="ellipsis")
    t.add_column(width=18, style="dim", no_wrap=True, overflow="ellipsis")
    start = max(0, min(sel - height // 2, len(audits) - height))
    for i, a in enumerate(audits[start : start + height], start):
        q = Text(a.get("query") or "", style="reverse" if i == sel else "")
        t.add_row(_row_icon(a), _when(a.get("created", "")), q, a.get("source") or "")
    return t


def _detail(full: dict[str, Any] | None) -> Group:
    if not full:
        return Group(Text("Loading…", style="dim"))
    req, rep = full["request"], full["report"]
    parts: list[Any] = [Text.assemble(("Question  ", "dim"), req.get("query", ""))]
    sents = rep.get("summary", {}).get("sentences", [])
    if sents:
        parts.append(Text("Answer, sentence by sentence", style="dim"))
        for s in sents:
            ok = s.get("status") != "review"
            line = Text.assemble(("  ✓ " if ok else "  ⚠ ", "green" if ok else "yellow"), s.get("text", ""))
            parts.append(line)
            for f in s.get("flags", []):
                parts.append(Text(f"      {f.get('title', '')}", style="yellow"))
    else:
        parts.append(Text.assemble(("Answer  ", "dim"), req.get("answer") or "(none sent)"))
    rc = rep.get("receipt", {})
    parts.append(
        Text(
            f"{rc.get('candidates', '?')} retrieved · {rc.get('in_prompt', '?')} in the prompt · "
            f"{rc.get('checks_passed', '?')}/{rc.get('checks_run', '?')} checks passed",
            style="dim",
        )
    )
    look = [f for f in rep.get("flags", []) if f.get("disposition") == "needs_review"]
    note = [f for f in rep.get("flags", []) if f.get("disposition") == "informational"]
    if look:
        parts.append(Text("\nWorth a look", style="bold yellow"))
        for f in look:
            parts.append(Text.assemble(("  ⚠ ", "yellow"), (f.get("title", ""), "bold")))
            if f.get("observation"):
                parts.append(Text(f"    {f['observation']}", style=""))
            if f.get("what_to_check"):
                parts.append(Text.assemble(("    Check: ", "dim"), f["what_to_check"]))
    if note:
        parts.append(Text("\nGood to know", style="bold cyan"))
        for f in note:
            parts.append(Text.assemble(("  · ", "cyan"), f.get("title", "")))
    return Group(*parts)


def watch(base: str, plain: bool = False) -> None:
    console = Console()
    if plain or not sys.stdin.isatty() or not console.is_terminal:
        _watch_plain(base, console)
        return
    audits: list[dict[str, Any]] = []
    details: dict[str, dict[str, Any]] = {}
    sel = 0
    error: str | None = None
    last_poll = 0.0

    def render() -> Group:
        h = max(5, min(12, console.size.height // 3))
        n_look = sum(1 for a in audits if a.get("needs_review"))
        head = Text.assemble(
            ("Wittgenstein", "bold"),
            ("  ·  watching ", "dim"),
            (base, "cyan"),
            ("  ·  ", "dim"),
            (f"{len(audits)} answers", ""),
            ("  ·  ", "dim"),
            (f"{n_look} worth a look", "yellow" if n_look else "dim"),
        )
        if error:
            body: Any = Text(f"\nCan't reach the server: {error}", style="red")
        elif not audits:
            body = Text(
                "\nNo answers yet. Connect your RAG app:\n"
                f"  any language   base URL {base}/proxy/openai/v1  (or /proxy/anthropic)\n"
                "  Python         wittgenstein run python app.py\n",
                style="dim",
            )
        else:
            a = audits[sel]
            body = Group(
                Panel(_list(audits, sel, h), title="Answers", title_align="left", border_style="dim"),
                Panel(
                    _detail(details.get(a["audit_id"])), title="Selected", title_align="left", border_style="dim"
                ),
            )
        return Group(head, body, Text("↑/↓ select   q quit", style="dim"))

    with _Keys() as keys, Live(render(), console=console, screen=True, auto_refresh=False) as live:
        while True:
            now = time.time()
            if now - last_poll >= POLL_SECONDS:
                last_poll = now
                try:
                    new = _get(f"{base}/v1/audits")["audits"]
                    if audits and new and new[0]["audit_id"] != audits[0]["audit_id"] and sel > 0:
                        sel += sum(1 for x in new if x["audit_id"] not in {y["audit_id"] for y in audits})
                    audits = new
                    sel = min(sel, max(0, len(audits) - 1))
                    error = None
                except (OSError, ValueError) as e:
                    error = str(e)
            while keys.pressed:
                k = keys.pressed.pop(0)
                if k in ("q", "Q", "\x03"):
                    return
                if k in ("up", "k"):
                    sel = max(0, sel - 1)
                elif k in ("down", "j"):
                    sel = min(max(0, len(audits) - 1), sel + 1)
            if audits:
                aid = audits[sel]["audit_id"]
                if aid not in details:
                    with contextlib.suppress(OSError, ValueError):
                        details[aid] = _get(f"{base}/v1/audits/{aid}")
            live.update(render(), refresh=True)
            time.sleep(0.05)


def _watch_plain(base: str, console: Console) -> None:
    """One line per new answer, then its flags: for logs and pipes."""
    seen: set[str] = set()
    first = True
    while True:
        try:
            audits = _get(f"{base}/v1/audits")["audits"]
        except (OSError, ValueError, urllib.error.URLError) as e:
            console.print(f"can't reach {base}: {e}")
            time.sleep(POLL_SECONDS * 3)
            continue
        for a in reversed(audits):
            if a["audit_id"] in seen:
                continue
            seen.add(a["audit_id"])
            mark = "REVIEW" if a.get("needs_review") else "ok    "
            console.print(f"{_when(a.get('created', ''))} {mark} {a.get('query', '')}", highlight=False)
            if a.get("needs_review") and not first:
                with contextlib.suppress(OSError, ValueError):
                    full = _get(f"{base}/v1/audits/{a['audit_id']}")
                    for f in full["report"].get("flags", []):
                        if f.get("disposition") == "needs_review":
                            console.print(f"         - {f.get('title', '')}", highlight=False)
        first = False
        time.sleep(POLL_SECONDS)


__all__ = ["watch"]
