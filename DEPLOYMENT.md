# Deployment Guide

This guide covers deploying Wittgenstein to Render as a **single web service**.
There is no separate frontend deployment: Flask (`server/app.py`) builds and
serves the Vite client directly (`client/dist`), and also exposes the API
routes (`/upload`, `/formalize`, `/review`, `/reviews`, etc.) on the same
origin.

## Architecture

- **One Render web service**, Python runtime, running `server/app.py` via Gunicorn.
- Build step installs Python deps and builds the client (`npm run build` → `client/dist`).
- Flask serves `client/dist` as static files and handles API requests — no CORS
  split, no separate frontend URL to keep in sync.

## Prerequisites

1. GitHub repository with your code.
2. Render account (free tier is enough for this demo).
3. OpenAI API key.

## Deploying with `render.yaml`

A `render.yaml` blueprint is committed at the repo root. In the Render
dashboard, choose **New → Blueprint**, point it at this repository, and
Render will read `render.yaml` and provision the service automatically.

It defines:

```yaml
buildCommand: pip install -r server/requirements.txt && cd client && npm install && npm run build
startCommand: cd server && gunicorn app:app --bind 0.0.0.0:$PORT --workers 2 --timeout 300
```

After the blueprint creates the service, set the required environment
variable (Render won't have a value for this since it's marked `sync: false`):

- `OPENAI_API_KEY` — your OpenAI API key.

`PORT` is set automatically by Render; `server/app.py` reads it via
`os.environ.get("PORT", 3000)` and binds to `0.0.0.0`.

**Note:** the build command assumes Node/npm is available in Render's Python
build image to run `npm run build`. Check the first deploy's build logs to
confirm this works in practice — if Render's native Python environment
doesn't include Node, switch the service to a Docker-based build instead.

## Manual setup (without the blueprint)

If you'd rather configure the service by hand instead of using
`render.yaml`:

1. **New → Web Service**, connect the repo.
2. **Runtime**: Python 3.
3. **Build Command**: `pip install -r server/requirements.txt && cd client && npm install && npm run build`
4. **Start Command**: `cd server && gunicorn app:app --bind 0.0.0.0:$PORT --workers 2 --timeout 300`
5. **Environment**: add `OPENAI_API_KEY`.

## Persistent storage (optional)

Uploads, generated PDFs, and the reviewer decision log (`outputs/reviews.json`)
are written under `DATA_DIR` (defaults to the repo root if unset). Render's free
tier has an ephemeral filesystem — anything written during a session is lost
on redeploy/restart. For a live demo this is usually fine; if you want
review decisions to persist across restarts, attach a Render Disk and set
`DATA_DIR` to its mount path.

## Local development

```bash
cd server
pip install -r requirements.txt
cp .env.example .env   # fill in OPENAI_API_KEY
python app.py          # serves on :3000, or PORT if set

cd ../client
npm install
npm run build           # or `npm run dev` for hot-reload against the Flask API
```

## Troubleshooting

- **Build fails on `npm run build`**: confirm Node is available in the build
  environment (see note above).
- **API key errors**: verify `OPENAI_API_KEY` is set in the Render service's
  Environment tab, not just locally.
- **Blank page after deploy**: check `/__debug` for `CLIENT_DIR` /
  `exists_index` — confirms whether the client build actually landed where
  Flask expects it.
