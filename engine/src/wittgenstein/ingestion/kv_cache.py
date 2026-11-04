"""One generic content-addressed key/value cache abstraction, shared by corpus-time
document/segment caching (`ingestion/corpus_index.py`), the Tier-3 LLM cache
(`proposition/llm_extraction.py`), and the optional semantic/NLI comparison cache
(`review/semantic_provider.py`) -- a single cache implementation, not two (or three)
that could drift (CLAUDE.md, "avoid two lists/tables describing the same category").
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Protocol


class KVCache(Protocol):
    def get(self, key: str) -> dict | None: ...

    def put(self, key: str, value: dict) -> None: ...

    def clear(self) -> None: ...


class MemoryKVCache:
    """In-process cache. Default choice: no disk I/O, deterministic, good for tests and
    the demo. Does not persist across process restarts -- use FileKVCache/SqliteKVCache
    for that.
    """

    def __init__(self) -> None:
        self._store: dict[str, dict] = {}

    def get(self, key: str) -> dict | None:
        return self._store.get(key)

    def put(self, key: str, value: dict) -> None:
        self._store[key] = value

    def clear(self) -> None:
        self._store.clear()


class FileKVCache:
    """One JSON file per key, under `directory`. Persists across process restarts.
    Suitable for a single-machine local-validation or demo deployment; a production
    deployment could swap in a different backend behind the same interface.
    """

    def __init__(self, directory: Path) -> None:
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)

    def _path_for(self, key: str) -> Path:
        return self.directory / f"{key}.json"

    def get(self, key: str) -> dict | None:
        path = self._path_for(key)
        if not path.exists():
            return None
        return json.loads(path.read_text())

    def put(self, key: str, value: dict) -> None:
        self._path_for(key).write_text(json.dumps(value))

    def clear(self) -> None:
        for path in self.directory.glob("*.json"):
            path.unlink()


class SqliteKVCache:
    """A local SQLite-backed cache -- one `cache_entries(key TEXT PRIMARY KEY, value
    TEXT)` table. Used by `review/semantic_provider.py` for optional semantic/NLI
    results (docs/claim-linking-improvement-plan.md §8): local-only by default (never a
    network cache), deterministic, and supports both a file path and `":memory:"` (test
    isolation -- each `SqliteKVCache(":memory:")` instance gets its own private
    in-memory database via its own dedicated connection, never shared across instances).
    Never stores credentials -- callers are responsible for not putting a credential in
    `value`, exactly as for the other two KVCache implementations.
    """

    def __init__(self, path: Path | str) -> None:
        self._path = str(path)
        if self._path != ":memory:":
            Path(self._path).parent.mkdir(parents=True, exist_ok=True)
        self._connection = sqlite3.connect(self._path)
        self._connection.execute("CREATE TABLE IF NOT EXISTS cache_entries (key TEXT PRIMARY KEY, value TEXT)")
        self._connection.commit()

    def get(self, key: str) -> dict | None:
        row = self._connection.execute("SELECT value FROM cache_entries WHERE key = ?", (key,)).fetchone()
        return json.loads(row[0]) if row else None

    def put(self, key: str, value: dict) -> None:
        self._connection.execute(
            "INSERT OR REPLACE INTO cache_entries (key, value) VALUES (?, ?)", (key, json.dumps(value))
        )
        self._connection.commit()

    def clear(self) -> None:
        self._connection.execute("DELETE FROM cache_entries")
        self._connection.commit()

    def close(self) -> None:
        self._connection.close()
