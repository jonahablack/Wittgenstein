"""Meaning-level contradiction and entailment between two sentences.

The rule-based checks compare fields (values, units, polarity words). They miss a
contradiction stated in different words -- the Air Canada case: the policy "does not
allow refunds for travel that has already happened"; the chatbot said a traveller who
"already travelled" could still submit the ticket for the reduced rate
(research/case-studies). A natural-language-inference (NLI) model reads meaning instead.

Model: `cross-encoder/nli-deberta-v3-xsmall` (Apache-2.0), run with ONNX Runtime (no
PyTorch), downloaded once on first use. Verdicts are probabilities from a model, so every
flag built on them is labeled as a model judgment, and the thresholds below are starting
values to be calibrated by the evaluation harness (engine/scripts/evaluate_checks.py),
not facts about the model.

Long answer sentences dilute: one that bundles several clauses ("If you need to travel
immediately or have already travelled ..., kindly do so within 90 days ...") can read as
neutral even when one of its claims contradicts the source. So each answer sentence is
also judged in *variants* -- one "or"-alternative dropped at a time, and long
comma-separated parts on their own -- and the strongest verdict is kept. Variants never
split a condition from what it governs; they only remove alternatives or keep a whole
part.
"""

from __future__ import annotations

import json
import os
import platform
import re
import threading
from dataclasses import dataclass

import numpy as np

#: Override with WITTGENSTEIN_NLI_MODEL (any cross-encoder NLI repo with ONNX exports,
#: e.g. cross-encoder/nli-deberta-v3-base: slower, more accurate).
REPO = os.environ.get("WITTGENSTEIN_NLI_MODEL", "cross-encoder/nli-deberta-v3-xsmall")
#: Starting thresholds; see the module docstring.
CONTRADICTION = 0.9
POSSIBLE_CONTRADICTION = 0.6
ENTAILMENT = 0.9
MAX_VARIANTS = 6

_LOCK = threading.Lock()
_MODEL: _Model | None = None
_LOAD_ERROR: str | None = None


@dataclass(frozen=True)
class Verdict:
    contradiction: float
    entailment: float
    neutral: float
    hypothesis: str
    """The variant of the answer sentence the verdict is for."""
    premise: str = ""
    """The source sentence it was judged against."""


class _Model:
    def __init__(self) -> None:
        import onnxruntime as ort
        from huggingface_hub import hf_hub_download
        from tokenizers import Tokenizer

        arm = platform.machine().lower() in {"arm64", "aarch64"}
        onnx_file = "onnx/model_qint8_arm64.onnx" if arm else "onnx/model.onnx"
        with open(hf_hub_download(REPO, "config.json")) as fh:
            cfg = json.load(fh)
        self._labels = {int(k): v for k, v in cfg["id2label"].items()}
        self._tok = Tokenizer.from_file(hf_hub_download(REPO, "tokenizer.json"))
        self._tok.enable_truncation(512)
        self._sess = ort.InferenceSession(hf_hub_download(REPO, onnx_file), providers=["CPUExecutionProvider"])
        self._inputs = {i.name for i in self._sess.get_inputs()}
        self._run_lock = threading.Lock()
        self.identifier = f"{REPO} ({onnx_file})"

    def probs(self, premise: str, hypothesis: str) -> dict[str, float]:
        enc = self._tok.encode(premise, hypothesis)
        feeds = {
            "input_ids": np.array([enc.ids], dtype=np.int64),
            "attention_mask": np.array([enc.attention_mask], dtype=np.int64),
        }
        if "token_type_ids" in self._inputs:
            feeds["token_type_ids"] = np.array([enc.type_ids], dtype=np.int64)
        with self._run_lock:
            logits = self._sess.run(None, feeds)[0][0]
        p = np.exp(logits - logits.max())
        p /= p.sum()
        return {self._labels[i]: float(x) for i, x in enumerate(p)}


def model() -> _Model | None:
    """The shared model, or None if it can't be loaded (e.g. offline on first use)."""
    global _MODEL, _LOAD_ERROR
    with _LOCK:
        if _MODEL is None and _LOAD_ERROR is None:
            try:
                _MODEL = _Model()
            except Exception as e:  # noqa: BLE001 -- reported as "unavailable", never as a passed check
                _LOAD_ERROR = f"{type(e).__name__}: {e}"
        return _MODEL


def load_error() -> str | None:
    return _LOAD_ERROR


_QUALIFIER = re.compile(
    r"(?i)(?:if|when|whenever|unless|provided|in|for|among|during|after|before|once|until|while|where|with|"
    r"without|except|in patients|in adults|in children)\b"
)
_KEEP_SUBJECT = {"you", "i", "we", "they", "he", "she", "it", "patients", "the", "a", "an", "if", "when", "unless"}
_OR_LEFT = re.compile(r"\b(?:\w+\s+){0,4}\w+\s+or\s+")
_OR_RIGHT = re.compile(r"\s+or\s+(?:\w+\s+){0,4}?\w+(?=\s+and\b|\s*,|\s*\.|$)")


def variants(sentence: str) -> list[str]:
    out = [sentence.strip()]
    for pattern in (_OR_LEFT, _OR_RIGHT):
        for m in pattern.finditer(sentence):
            start = m.start()
            if pattern is _OR_LEFT:
                # Keep a leading subject or article: drop "need to travel immediately or",
                # not "you need to travel immediately or".
                first = re.match(r"\w+\s+", sentence[start:])
                if first and first.group(0).strip().lower() in _KEEP_SUBJECT:
                    start += first.end()
            v = re.sub(
                r"\s{2,}", " ", sentence[:start] + (" " if pattern is _OR_RIGHT else "") + sentence[m.end() :]
            )
            out.append(v.strip())
    parts = re.split(r",\s+|;\s+", sentence)
    # A later part never stands alone when the first part qualifies it ("In pediatric
    # patients, the dose is ..."; "If X, do Y"): cutting it loose would change what it
    # says. The qualifying first part itself may stand alone (it keeps its condition).
    qualified = bool(_QUALIFIER.match(parts[0].strip())) if parts else False
    for i, part in enumerate(parts):
        if len(part.split()) >= 5 and (i == 0 or not qualified):
            out.append(part.strip().rstrip(".") + ".")
    seen: list[str] = []
    for v in out:
        if v and v not in seen:
            seen.append(v)
    return seen[:MAX_VARIANTS]


def judge(premises: list[str], sentence: str) -> tuple[Verdict, Verdict] | None:
    """(strongest contradiction, strongest entailment) against any premise. Contradiction
    is the maximum over the sentence *and its variants* (if any part contradicts the
    source, the sentence does); entailment is judged on the *whole* sentence only (one
    supported part doesn't make the sentence supported). None if the model is
    unavailable."""
    m = model()
    if m is None or not premises:
        return None
    best_c: Verdict | None = None
    best_e: Verdict | None = None
    whole = sentence.strip()
    for premise in premises:
        for h in variants(sentence):
            p = m.probs(premise, h)
            v = Verdict(p.get("contradiction", 0.0), p.get("entailment", 0.0), p.get("neutral", 0.0), h, premise)
            if best_c is None or v.contradiction > best_c.contradiction:
                best_c = v
            if h == whole and (best_e is None or v.entailment > best_e.entailment):
                best_e = v
    assert best_c is not None and best_e is not None
    return best_c, best_e


def best_entailment(premises: list[str], sentence: str) -> Verdict | None:
    """The strongest entailment of the *whole* sentence by any premise."""
    m = model()
    if m is None or not premises:
        return None
    best: Verdict | None = None
    for premise in premises:
        p = m.probs(premise, sentence.strip())
        v = Verdict(
            p.get("contradiction", 0.0), p.get("entailment", 0.0), p.get("neutral", 0.0), sentence, premise
        )
        if best is None or v.entailment > best.entailment:
            best = v
    return best


def pair(premise: str, hypothesis: str) -> Verdict | None:
    m = model()
    if m is None:
        return None
    p = m.probs(premise, hypothesis)
    return Verdict(p.get("contradiction", 0.0), p.get("entailment", 0.0), p.get("neutral", 0.0), hypothesis)
