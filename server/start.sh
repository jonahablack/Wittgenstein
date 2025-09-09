#!/usr/bin/env bash
set -e

# Download NLTK data (ok to keep, but build-time is faster)
python3 - <<'PY'
import nltk
try:
    nltk.data.find('tokenizers/punkt')
except LookupError:
    nltk.download('punkt')
PY

# Start Gunicorn; we're in Root Directory=server, so target is app:app
exec gunicorn app:app --bind 0.0.0.0:$PORT --workers 2 --timeout 300
