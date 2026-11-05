# Deployment

Wittgenstein deploys as **one web service**: the engine (`engine/`, FastAPI) serves the
built web app (`web/`) and the API from the same origin. The `Dockerfile` at the repo
root builds both; `render.yaml` deploys it on Render.

## Render

1. In the Render dashboard: **New → Blueprint**, pick this repository and the `Cosmos`
   branch. Render reads `render.yaml` and creates the `wittgenstein-cosmos` web service
   (Docker, free plan, health check `/live/config`).
2. Optional environment variables (set in the dashboard, never in the repo):
   - `ANTHROPIC_API_KEY` / `OPENAI_API_KEY`: language-model answers in the app
     (without them, answers quote the document).
   - `WITTGENSTEIN_API_KEYS`: comma-separated keys required by the public `/v1` API.
3. Every push to `Cosmos` redeploys (`autoDeploy: true`).

Notes:
- Memory: about 180 MB at peak for a three-pipeline run (measured locally), within the
  free plan's 512 MB.
- The disk is not persistent: uploaded documents and saved runs reset on each deploy or
  restart. The built-in manual and the public FDA label samples are baked into the image.
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
