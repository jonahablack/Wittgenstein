"""Shared path/env helpers for the nuggetindex_track scripts.

Kept local to this subdirectory, same convention ../env_utils.py already
established for factoidwiki_track/ itself: self-contained, safely
deletable/movable as a unit, no imports of sibling scripts' Python
modules. The ONE exception, explicitly instructed by the task that
created this track, is READING (never writing/modifying) two of
factoidwiki_track/'s own log files as this track's source-paragraph
corpus -- see GOVERN_SOURCE_LOG / ELABORATION_SOURCE_LOG below. That is
plain file I/O (open().read()), not a Python import of ../*.py, so it
does not violate the no-sibling-imports convention; it is the same
"tracks can read each other's data for comparison, but not modify" rule
this project already uses between top-level tracks.
"""

import json
import os

TRACK_DIR = os.path.dirname(os.path.abspath(__file__))                 # .../factoidwiki_track/nuggetindex_track
FACTOIDWIKI_TRACK_DIR = os.path.dirname(TRACK_DIR)                     # .../factoidwiki_track
DISCOURSE_SEVERANCE_DIR = os.path.dirname(FACTOIDWIKI_TRACK_DIR)       # .../discourse_severance
SCRIPTS_DIR = os.path.dirname(DISCOURSE_SEVERANCE_DIR)                 # .../scripts
SERVER_DIR = os.path.dirname(SCRIPTS_DIR)                              # .../server

# This track's own output locations -- never written to by any other track.
RESULTS_DIR = os.path.join(TRACK_DIR, "results")
LOGS_DIR = os.path.join(TRACK_DIR, "logs")

# factoidwiki_track/'s Task 7 output logs -- the SAME 272 governing-relation
# (Condition/Concession) and 206 Elaboration-control source paragraphs Task 7
# already screened, Stage-2-confirmed, and scored under Condition A/B. Every
# other chunker in this comparison (Propositionizer, the gpt-4o-mini
# relation-aware atomizer, and -- per a separate, methodologically distinct
# integration -- AtomicRAG) is measured against this same fixed set, so
# NuggetIndex is too, for a fair comparison. READ-ONLY: this track never
# writes to these paths.
GOVERN_SOURCE_LOG = os.path.join(FACTOIDWIKI_TRACK_DIR, "logs", "task7_experiment_govern_log.jsonl")
ELABORATION_SOURCE_LOG = os.path.join(FACTOIDWIKI_TRACK_DIR, "logs", "task7_experiment_elaboration_log.jsonl")


def load_server_env():
    """Load server/.env into process env, without overriding any var
    already set in the real environment.

    Duplicated verbatim (in behavior) from ../env_utils.py's
    load_server_env, which itself duplicates discourse_severance/
    run_experiments.py's `_load_server_env` -- see that docstring for why
    this reproduction (rather than an import) is needed for a standalone
    script invocation.
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
    for d in (RESULTS_DIR, LOGS_DIR):
        os.makedirs(d, exist_ok=True)


def load_jsonl(path):
    records = []
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    return records
