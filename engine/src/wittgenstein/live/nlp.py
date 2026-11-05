"""One shared, lazily loaded spaCy pipeline (`en_core_web_sm`, NER and lemmatizer off).

Used for exactly two things: the clause well-formedness gate ported from risk_triage.py
(does a span have its own subject and finite verb?) and noun chunks for query facets.
spaCy is never asked to judge a discourse relation or an answer's correctness.
"""

from __future__ import annotations

import os
import shutil
import tempfile
import threading
import urllib.request
import zipfile
from functools import lru_cache
from pathlib import Path
from typing import Any

_LOCK = threading.Lock()
_CALL_LOCK = threading.Lock()
_NLP: Any = None

_SUBJECT_DEPS = {"nsubj", "nsubjpass", "expl"}
_MODEL = "en_core_web_sm-3.8.0"
_MODEL_URL = f"https://github.com/explosion/spacy-models/releases/download/{_MODEL}/{_MODEL}-py3-none-any.whl"


def _fetched_model() -> Path:
    """The spaCy model unpacked under ~/.wittgenstein/models (or WITTGENSTEIN_HOME),
    downloaded on first use. Unpacked rather than pip-installed, so it works in any
    environment (pip, uv, pipx, conda) without touching it."""
    home = Path(os.environ.get("WITTGENSTEIN_HOME", "~/.wittgenstein")).expanduser()
    dest = home / "models" / _MODEL
    if (dest / "config.cfg").exists():
        return dest
    prefix = f"en_core_web_sm/{_MODEL}/"
    with tempfile.TemporaryDirectory() as tmp:
        wheel = Path(tmp) / "model.whl"
        urllib.request.urlretrieve(_MODEL_URL, wheel)  # noqa: S310 -- fixed https URL
        staging = Path(tmp) / "unpacked"
        with zipfile.ZipFile(wheel) as z:
            for name in z.namelist():
                if name.startswith(prefix) and not name.endswith("/"):
                    target = staging / name[len(prefix) :]
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_bytes(z.read(name))
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(staging), dest)
    return dest


def nlp() -> Any:
    global _NLP
    with _LOCK:
        if _NLP is None:
            import spacy

            try:
                _NLP = spacy.load("en_core_web_sm", disable=["ner", "lemmatizer"])
            except OSError:
                # Installed from PyPI, which can't carry the model as a dependency:
                # fetch it once (about 12 MB) into the user's folder and load it there.
                _NLP = spacy.load(_fetched_model(), disable=["ner", "lemmatizer"])
        return _NLP


@lru_cache(maxsize=8192)
def has_subject_and_finite_verb(text: str) -> bool:
    """True if `text` has its own subject and finite verb, i.e. is an independently
    well-formed clause ("the parties agree otherwise in writing"), not a bare phrase
    ("if applicable", "except for good cause"). Modal auxiliaries count as finite."""
    text = (text or "").strip()
    if not text:
        return False
    pipeline = nlp()
    with _CALL_LOCK:  # pipelines run in worker threads; spaCy calls are serialized
        doc = pipeline(text)
    has_subject = any(tok.dep_ in _SUBJECT_DEPS for tok in doc)
    has_finite = any("Fin" in tok.morph.get("VerbForm") for tok in doc)
    return has_subject and has_finite
