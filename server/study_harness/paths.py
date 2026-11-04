"""Filesystem locations, resolved the same way server/app.py does.

DATA_DIR comes from the environment (persistent disk on Render) and
defaults to the repo base directory. Everything here is computed lazily,
at call time, so tests can point DATA_DIR at a temp directory without
import-order gymnastics.
"""

import os


def base_dir() -> str:
    """Repo root: server/study_harness/ -> server/ -> repo."""
    return os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))


def data_dir() -> str:
    return os.environ.get("DATA_DIR", base_dir())


def outputs_dir() -> str:
    """Where the pipeline writes {document_id}_final_data.json."""
    return os.path.join(data_dir(), "outputs")


def study_data_dir() -> str:
    """Session persistence root. Created on first use."""
    d = os.path.join(data_dir(), "study_data")
    os.makedirs(d, exist_ok=True)
    return d


def default_config_path() -> str:
    """Study config: STUDY_CONFIG env var, else DATA_DIR/study_config.json."""
    return os.environ.get(
        "STUDY_CONFIG", os.path.join(data_dir(), "study_config.json")
    )


def document_data_path(document_id: str) -> str:
    # basename() so a config/document_id can never traverse out of outputs/.
    return os.path.join(
        outputs_dir(), f"{os.path.basename(str(document_id))}_final_data.json"
    )
