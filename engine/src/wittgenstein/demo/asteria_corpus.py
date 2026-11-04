"""The fictional "Asteria Autonomous Systems Certification Manual" corpus --
docs/controlled-synthetic-corpus-plan.md. Unlike `widget_corpus.py`, this corpus's
Markdown text is not inlined in Python: it is read from the tracked files under
`data/fixtures/asteria_manual/documents/`, so the corpus content and its own
fixture-integrity tests never risk drifting apart. Fully fictional and
redistribution-safe -- see `data/fixtures/asteria_manual/README.md`.
"""

from __future__ import annotations

from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[3]
DOCUMENTS_DIR = _REPO_ROOT / "data/fixtures/asteria_manual/documents"

CORPUS_ID = "asteria-manual"


def documents() -> dict[str, str]:
    """`{source_document_id: text}` for every tracked `.md` file in the Asteria manual
    -- `source_document_id` is the filename stem, matching the corpus's own
    `article-<N>-...`/`annex-<roman>-...`/`d<N>-...` naming convention.
    """

    if not DOCUMENTS_DIR.is_dir():
        raise FileNotFoundError(
            f"Asteria manual documents directory not found: {DOCUMENTS_DIR}. This corpus is "
            "tracked by git -- if this path is missing, the repository checkout is incomplete."
        )
    result = {path.stem: path.read_text() for path in sorted(DOCUMENTS_DIR.glob("*.md"))}
    if not result:
        raise FileNotFoundError(f"No .md files found under {DOCUMENTS_DIR}.")
    return result
