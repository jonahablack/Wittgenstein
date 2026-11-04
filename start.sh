#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SERVER_DIR="$ROOT_DIR/server"
CLIENT_DIR="$ROOT_DIR/client"
VENV_PY="$ROOT_DIR/venv/bin/python"
PORT="${PORT:-3000}"

if [ ! -x "$VENV_PY" ]; then
  echo "error: venv python not found at $VENV_PY" >&2
  exit 1
fi

# Always invoke the venv's python by absolute path rather than relying on
# `source venv/bin/activate`: this venv was created at a different path
# before the project moved, so activate's baked-in VIRTUAL_ENV is stale and
# an activated shell's `python3` silently falls through to system Python,
# missing installed deps (nltk, etc.) with no obvious error as to why.
if lsof -tiTCP:"$PORT" -sTCP:LISTEN >/dev/null 2>&1; then
  echo "Port $PORT is in use, stopping the existing process..."
  kill "$(lsof -tiTCP:"$PORT" -sTCP:LISTEN)"
  sleep 1
fi

echo "Building client..."
npm --prefix "$CLIENT_DIR" run build

echo "Loading server/.env..."
set -a
# shellcheck disable=SC1090
source "$SERVER_DIR/.env"
set +a

echo "Starting server on http://127.0.0.1:$PORT ..."
cd "$SERVER_DIR"
exec "$VENV_PY" app.py
