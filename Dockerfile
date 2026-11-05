# Wittgenstein: the web app (web/) served by the engine (engine/) as one service.
# Used by render.yaml; also runs anywhere Docker does:
#   docker build -t wittgenstein . && docker run -p 10000:10000 wittgenstein

# --- the web interface --------------------------------------------------------------
FROM node:20-slim AS web
WORKDIR /web
COPY web/package.json web/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY web/ ./
RUN npm run build

# --- the engine ---------------------------------------------------------------------
FROM python:3.11-slim
# Data (sample documents, runs, the database, downloaded models) lives under /app/engine/data
# and ~/.wittgenstein inside the container. Render's disk is not persistent: uploads and
# saved runs reset on each deploy; the built-in documents don't.
ENV PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy
RUN pip install --no-cache-dir uv
WORKDIR /app/engine
COPY engine/pyproject.toml engine/uv.lock engine/README.md engine/PACKAGE_README.md ./
RUN uv sync --frozen --no-dev --no-install-project
COPY engine/ ./
RUN uv sync --frozen --no-dev
# The engine serves ../web/dist when it exists (api/app.py).
COPY --from=web /web/dist /app/web/dist
# Fetch the models once at build time, so the first request doesn't wait for downloads:
# the spaCy English model, the meaning-search embedder and the language-inference model.
RUN mkdir -p data && uv run --no-dev python -c "\
from wittgenstein.live.nlp import nlp; nlp(); \
from wittgenstein.live.embedding import get_embedder; get_embedder(); \
from wittgenstein.live import nli; assert nli.model() is not None, nli.load_error()"
# Public FDA label samples for the demo document list (best effort: needs openFDA at build time).
# The novel is left out of the hosted image: 2,200 passages for a demo, about 100 MB of memory.
RUN (uv run --no-dev python scripts/fetch_sample_corpora.py || echo "sample corpora not fetched; the built-in manual still works") \
    && rm -rf data/live_corpora/austen
EXPOSE 10000
CMD ["sh", "-c", "uv run --no-sync uvicorn wittgenstein.api.app:app --host 0.0.0.0 --port ${PORT:-10000}"]
