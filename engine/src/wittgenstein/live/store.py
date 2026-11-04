"""In-process corpus and run stores for the live API.

A corpus is warmed in a background thread as soon as it is added: parsed, cut into
units for every chunker the presets use, embedded, and characterized. So the first
question a user asks never pays that one-time cost (measured: ~2.7 s cold vs ~0.2 s
warm for four pipelines on a 770 KB novel).

Runs are kept in memory (most recent first, bounded) and written to
data/live_runs/<run_id>.json (gitignored) so they can be replayed.
"""

from __future__ import annotations

import io
import json
import re
import threading
from collections import OrderedDict
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from wittgenstein.live.characterize import get_profile
from wittgenstein.live.corpus import LiveCorpus
from wittgenstein.live.embedding import DEFAULT_EMBEDDER, get_embedder
from wittgenstein.live.pipelines import PRESETS
from wittgenstein.live.runner import RunResult, save_run

ENGINE_ROOT = Path(__file__).resolve().parents[3]
LIVE_CORPORA = ENGINE_ROOT / "data" / "live_corpora"
LIVE_RUNS = ENGINE_ROOT / "data" / "live_runs"
FIXTURE = ENGINE_ROOT / "data" / "fixtures" / "asteria_manual" / "documents"
_TEXT_SUFFIXES = {".txt", ".md", ".markdown"}
MAX_RUNS_IN_MEMORY = 50


def extract_text(filename: str, data: bytes) -> str:
    """Plain text from an uploaded file. PDFs go through pypdf page by page; anything
    else is decoded as UTF-8 (undecodable bytes replaced, never silently dropped)."""
    if filename.lower().endswith(".pdf"):
        from pypdf import PdfReader

        reader = PdfReader(io.BytesIO(data))
        return "\n\n".join((page.extract_text() or "").strip() for page in reader.pages).strip()
    return data.decode("utf-8", errors="replace")


def slug(text: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return s[:48] or "document"


@dataclass
class CorpusRecord:
    corpus_id: str
    title: str
    source: str  # fixture | sample | upload
    documents: dict[str, str]
    titles: dict[str, str]
    status: str = "loading"  # loading | ready | error
    error: str | None = None
    corpus: LiveCorpus | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    warm_ms: float | None = None

    def summary(self) -> dict[str, Any]:
        units = self.corpus.units() if self.corpus and self.status == "ready" else None
        prof = self.corpus.profile if self.corpus else None
        return {
            "corpus_id": self.corpus_id,
            "title": self.title,
            "source": self.source,
            "status": self.status,
            "error": self.error,
            "documents": [
                {"document_id": d, "title": self.titles.get(d, d), "chars": len(t)}
                for d, t in self.documents.items()
            ],
            "units": len(units.units) if units else None,
            "characters": sum(len(t) for t in self.documents.values()),
            "cross_reference_density": prof.cross_reference_density if prof else None,
            "table_density": prof.table_density if prof else None,
            "warm_ms": self.warm_ms,
        }


class CorpusStore:
    def __init__(self) -> None:
        self._records: dict[str, CorpusRecord] = {}
        self._lock = threading.Lock()

    def list(self) -> list[CorpusRecord]:
        with self._lock:
            return list(self._records.values())

    def get(self, corpus_id: str) -> CorpusRecord | None:
        with self._lock:
            return self._records.get(corpus_id)

    def add(
        self,
        title: str,
        documents: dict[str, str],
        source: str,
        corpus_id: str | None = None,
        titles: dict[str, str] | None = None,
        wait: bool = False,
    ) -> CorpusRecord:
        documents = {k: v for k, v in documents.items() if v.strip()}
        if not documents:
            raise ValueError("No readable text in the uploaded documents.")
        with self._lock:
            base = corpus_id or slug(title)
            cid, n = base, 2
            while cid in self._records:
                cid, n = f"{base}-{n}", n + 1
            rec = CorpusRecord(cid, title, source, documents, titles or {})
            self._records[cid] = rec
        t = threading.Thread(target=self._warm, args=(rec,), daemon=True, name=f"warm-{cid}")
        t.start()
        if wait:
            t.join()
        return rec

    def _warm(self, rec: CorpusRecord) -> None:
        import time

        t0 = time.perf_counter()
        try:
            corpus = LiveCorpus(rec.corpus_id, rec.documents, rec.titles)
            for spec in PRESETS.values():
                units = corpus.units(spec.chunker)
                name = spec.embedder or DEFAULT_EMBEDDER
                units.vectors(get_embedder(name))
                get_profile(get_embedder(name), corpus)
            from wittgenstein.live.nlp import nlp

            nlp()
            rec.corpus = corpus
            rec.status = "ready"
        except Exception as e:  # noqa: BLE001 -- surfaced to the UI as the corpus's error state
            rec.status, rec.error = "error", f"{type(e).__name__}: {e}"
        rec.warm_ms = round((time.perf_counter() - t0) * 1000, 1)

    def load_defaults(self) -> None:
        """The tracked Asteria fixture, plus every folder under data/live_corpora/
        (gitignored; e.g. fetched public-domain samples), one corpus per folder."""
        if FIXTURE.exists():
            docs = {p.stem: p.read_text() for p in sorted(FIXTURE.glob("*.md"))}
            self.add("Asteria certification manual (fictional)", docs, "fixture", corpus_id="asteria")
        if LIVE_CORPORA.exists():
            for folder in sorted(p for p in LIVE_CORPORA.iterdir() if p.is_dir()):
                meta_path = folder / "meta.json"
                meta = json.loads(meta_path.read_text()) if meta_path.exists() else {}
                sample: dict[str, str] = {}
                for f in sorted(folder.iterdir()):
                    if f.suffix.lower() in _TEXT_SUFFIXES or f.suffix.lower() == ".pdf":
                        sample[f.stem] = extract_text(f.name, f.read_bytes())
                if sample:
                    self.add(
                        meta.get("title", folder.name.replace("-", " ").title()), sample, "sample", folder.name
                    )


class RunStore:
    def __init__(self, directory: Path = LIVE_RUNS) -> None:
        self._runs: OrderedDict[str, dict[str, Any]] = OrderedDict()
        self._lock = threading.Lock()
        self._dir = directory

    def put(self, result: RunResult) -> None:
        path = save_run(result, self._dir)
        payload = json.loads(path.read_text())
        with self._lock:
            self._runs[result.run_id] = payload
            self._runs.move_to_end(result.run_id, last=False)
            while len(self._runs) > MAX_RUNS_IN_MEMORY:
                self._runs.popitem(last=True)

    def get(self, run_id: str) -> dict[str, Any] | None:
        if not re.fullmatch(r"[0-9a-f]{16}", run_id):
            return None
        with self._lock:
            if run_id in self._runs:
                return self._runs[run_id]
        path = self._dir / f"{run_id}.json"
        return json.loads(path.read_text()) if path.exists() else None


corpora = CorpusStore()
runs = RunStore()
