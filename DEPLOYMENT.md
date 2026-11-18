# Deployment

Wittgenstein deploys as **one web service**: the engine (`engine/`, FastAPI) serves the
built web app (`web/`) and the API from the same origin. The `Dockerfile` at the repo
root builds both; `render.yaml` deploys it on Render.

## Render

The `Wittgenstein` service (https://wittgenstein.onrender.com) runs on Render's Python
runtime with the build and start commands in `render.yaml`: it builds `web/`, installs the
engine with `uv`, downloads the models at build time (kept under `engine/.cache` so they
exist at runtime), and serves everything from the engine on `$PORT`. The public FDA label
samples are tracked in `engine/data/fixtures/fda_labels` (openFDA refused Render's builds). Every push to `Cosmos` redeploys.

Environment variables (set in the dashboard, never in the repo):
- `OPENAI_API_KEY` / `ANTHROPIC_API_KEY`: language-model answers in the app (without
  them, answers quote the document).
- `WITTGENSTEIN_API_KEYS`: comma-separated keys required by the public `/v1` API.
- `TYPESAFE_API_KEY`: TypeSafe's Jev, which makes the meaning-level checks here
  (`WITTGENSTEIN_NLI=jev`).

Notes:
- Memory: about 650-700 MB with all models loaded (measured in the Docker image), more
  than the Starter plan's 512 MB (Render killed it: "oomKilled, memoryLimit 512Mi"). So
  the meaning-level checks (contradiction and paraphrase) run on TypeSafe's hosted Jev
  model instead (`WITTGENSTEIN_NLI=jev`): no model in memory, peak 465 MB. The app and
  every /v1/check response tell users that the passages and answer sentences those checks
  compare are sent to TypeSafe. On the planted-error evaluation Jev matched the local
  model (0/240 false alarms, 332/340 errors flagged) and caught paraphrased contradictions
  the local model scored below its threshold. To run them locally instead, remove the
  variable on a plan with 1 GB or more; `WITTGENSTEIN_NLI=off` turns them off.
- The disk is not persistent: uploaded documents and saved runs reset on each deploy or
  restart. The built-in manual and the FDA label samples ship with the code.
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
