"""One shared, lazily loaded spaCy pipeline (`en_core_web_sm`, NER and lemmatizer off).

Used for exactly two things: the clause well-formedness gate ported from risk_triage.py
(does a span have its own subject and finite verb?) and noun chunks for query facets.
spaCy is never asked to judge a discourse relation or an answer's correctness.
"""

from __future__ import annotations

import threading
from functools import lru_cache
from typing import Any

_LOCK = threading.Lock()
_CALL_LOCK = threading.Lock()
_NLP: Any = None

_SUBJECT_DEPS = {"nsubj", "nsubjpass", "expl"}


def nlp() -> Any:
    global _NLP
    with _LOCK:
        if _NLP is None:
            import spacy

            _NLP = spacy.load("en_core_web_sm", disable=["ner", "lemmatizer"])
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
