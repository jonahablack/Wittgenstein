from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from wittgenstein.api.routes import applicability, health, live, manifests, registry, review, traces
from wittgenstein.db.session import init_db


@asynccontextmanager
async def _lifespan(_app: FastAPI) -> AsyncIterator[None]:
    # Only the review-event table is actually written to by this app in this pass
    # (docs/review-loop-implementation-plan.md §8) -- create_all is idempotent and
    # cheap, so this simply ensures it exists before the first POST /review/events.
    init_db()
    # Live pipeline: load the tracked fixture and any local sample corpora, warming each
    # in a background thread so startup isn't blocked (live/store.py).
    from wittgenstein.live.store import corpora

    if not corpora.list():
        corpora.load_defaults()
    yield


app = FastAPI(
    title="Wittgenstein RAG Reliability",
    description=(
        "A versioned, evidence-graded registry of RAG failure mechanisms, plus deterministic "
        "manifest/trace matching. This API surfaces review cues for human verification -- it "
        "does not produce a hallucination score and does not replace human review."
    ),
    version="0.1.0",
    lifespan=_lifespan,
)

# Dev-only: the review screen (frontend/review.html) is a plain static file with no
# build tooling (docs/review-loop-implementation-plan.md §8), typically opened from a
# different origin (file:// or a bare `python -m http.server`) than this API. A
# production deployment should replace this with an explicit allowed-origin list.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(registry.router)
app.include_router(manifests.router)
app.include_router(traces.router)
app.include_router(applicability.router)
app.include_router(review.router)
app.include_router(live.router)

# The live web app (../web, `npm run build`), served from the same origin as the API when
# it has been built. Mounted last so every API route above takes precedence.
_WEB_DIST = Path(__file__).resolve().parents[4] / "web" / "dist"
if _WEB_DIST.is_dir():
    app.mount("/", StaticFiles(directory=_WEB_DIST, html=True), name="web")
