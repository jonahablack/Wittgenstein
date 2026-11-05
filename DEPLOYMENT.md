# Deployment

Wittgenstein deploys as **one web service**: the engine (`engine/`, FastAPI) serves the
built web app (`web/`) and the API from the same origin. The `Dockerfile` at the repo
root builds both; `render.yaml` deploys it on Render.

## Render

The `Wittgenstein` service (https://wittgenstein.onrender.com) runs on Render's Python
runtime with the build and start commands in `render.yaml`: it builds `web/`, installs the
engine with `uv`, downloads the models at build time (kept under `engine/.cache` so they
exist at runtime), fetches the public FDA label samples, and serves everything from the
engine on `$PORT`. Every push to `Cosmos` redeploys.

Environment variables (set in the dashboard, never in the repo):
- `OPENAI_API_KEY` / `ANTHROPIC_API_KEY`: language-model answers in the app (without
  them, answers quote the document).
- `WITTGENSTEIN_API_KEYS`: comma-separated keys required by the public `/v1` API.

Notes:
- Memory: about 650-700 MB once the models are loaded (measured in the Docker image).
  The Starter plan's 512 MB may restart under load; a 2 GB plan holds it.
- The disk is not persistent: uploaded documents and saved runs reset on each deploy or
  restart. The built-in manual and the FDA label samples come back with every build.
- The model proxy (`/proxy/...`) and the audit feed (`/v1/audits`) accept only requests
  from the same machine; they're for the local install, not the hosted site.

## Anywhere else

```bash
docker build -t wittgenstein .
docker run -p 10000:10000 wittgenstein        # http://localhost:10000
```

## On a laptop, beside your own RAG app

```bash
pip install wittgenstein-rag
wittgenstein start
```

See `engine/docs/integration.md`.

The previous Flask app (`server/`, `client/`) is no longer deployed.
