"""Shared path/env helpers for nuggetindex_track/exp3/ scripts only.

Deliberately NOT named `env_utils.py`, unlike every other directory-level
helper in this project family (../env_utils.py, ../../env_utils.py) --
this directory sits one level below nuggetindex_track/, and adding
nuggetindex_track/ to sys.path (needed elsewhere in this package, see
arm6_flagged_deferral.py / run_nuggetindex_exp3.py, to import
triple_severance_judge.py) would put THAT directory's own env_utils.py on
sys.path too. Two same-named modules on sys.path at once is a real
shadowing hazard (whichever directory sys.path search hits first wins,
silently), not a hypothetical one, so this file uses a distinct name to
make the hazard structurally impossible rather than relying on import
order.
"""

import json
import os

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))          # .../nuggetindex_track/exp3
NUGGETINDEX_TRACK_DIR = os.path.dirname(SCRIPT_DIR)               # .../nuggetindex_track
FACTOIDWIKI_TRACK_DIR = os.path.dirname(NUGGETINDEX_TRACK_DIR)    # .../factoidwiki_track
DISCOURSE_SEVERANCE_DIR = os.path.dirname(FACTOIDWIKI_TRACK_DIR)  # .../discourse_severance
SCRIPTS_DIR = os.path.dirname(DISCOURSE_SEVERANCE_DIR)            # .../scripts
SERVER_DIR = os.path.dirname(SCRIPTS_DIR)                         # .../server

RESULTS_DIR = os.path.join(SCRIPT_DIR, "results")

# Read-only source data for this experiment (never written to from here):
NUGGETINDEX_GOVERN_LOG = os.path.join(NUGGETINDEX_TRACK_DIR, "logs", "nuggetindex_govern_log.jsonl")
BUNDLING_AUDIT_PATH = os.path.join(NUGGETINDEX_TRACK_DIR, "results", "nuggetindex_nucleus_bundling_audit.json")


def load_server_env():
    """Load server/.env into process env, without overriding any var
    already set. Duplicated verbatim (in behavior) from
    ../env_utils.py's load_server_env -- same reasoning as that
    docstring: a standalone script invocation needs this without relying
    on import order from elsewhere.
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
    os.makedirs(RESULTS_DIR, exist_ok=True)


def load_jsonl(path):
    records = []
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    return records
