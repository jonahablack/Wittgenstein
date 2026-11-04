"""Shared path/env helpers for the factoidwiki_track pilot scripts.

Kept local to this subdirectory on purpose: per the task that created
this track, discourse_severance/ files OUTSIDE factoidwiki_track/ must
not be touched, and this track's scripts should not import from its
siblings (run_experiments.py, relation_elicitation.py, etc.) so it stays
self-contained and safely deletable/movable as a unit. Where behavior
needs to match a sibling script exactly (e.g. env loading), the logic is
duplicated here rather than imported.
"""

import os

TRACK_DIR = os.path.dirname(os.path.abspath(__file__))
DISCOURSE_SEVERANCE_DIR = os.path.dirname(TRACK_DIR)
SCRIPTS_DIR = os.path.dirname(DISCOURSE_SEVERANCE_DIR)
SERVER_DIR = os.path.dirname(SCRIPTS_DIR)

DATA_CACHE_DIR = os.path.join(TRACK_DIR, "data_cache")
RESULTS_DIR = os.path.join(TRACK_DIR, "results")
LOGS_DIR = os.path.join(TRACK_DIR, "logs")


def load_server_env():
    """Load server/.env into process env, without overriding any var
    already set in the real environment.

    Duplicated verbatim (in behavior) from
    discourse_severance/run_experiments.py's `_load_server_env`: this
    project's dev/prod entry point (start.sh) sources server/.env via
    `source ... ; set -a`, which is not in effect for a standalone script
    invocation like these pilot scripts. This reproduces that loading so
    OPENAI_API_KEY is available the same way it is for the Flask app.
    """
    env_path = os.path.join(SERVER_DIR, ".env")
    if not os.path.exists(env_path):
        return
    with open(env_path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key, value = key.strip(), value.strip()
            if key and value and key not in os.environ:
                os.environ[key] = value


def ensure_dirs():
    for d in (DATA_CACHE_DIR, RESULTS_DIR, LOGS_DIR):
        os.makedirs(d, exist_ok=True)
