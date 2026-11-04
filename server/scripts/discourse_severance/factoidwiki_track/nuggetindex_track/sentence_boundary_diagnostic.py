"""Sentence-boundary-spanning diagnostic, required by this task's brief:
"If a connective spans a sentence boundary in any severed case, flag
that specific case in your output."

Context for why this check exists at all even though
../nuggetindex_extractor_adapter.py's docstring already established (by
reading the real NuggetIndex source, not by assumption) that NuggetIndex
has NO built-in sentence-window context assembly, and that this
adapter's own call (`aextract(text=paragraph)`, whole paragraph, no
extra `context`) gives NuggetIndex exactly the same one-paragraph unit
every other chunker in this comparison sees -- so there is no
NuggetIndex-specific context-richness confound to explain away here. The
task brief asks for this check regardless, as a plain descriptive flag
on the DATA: does the elicited satellite/nucleus pair for a given source
paragraph happen to sit in two different sentences of that paragraph?
This is a property of the paragraph and the Stage-1/2 relation
elicitation (shared with every other chunker measured against the same
272+206 paragraphs), not a property of NuggetIndex's extractor -- but a
severed case where the connective's own clause is in a different
sentence from the nucleus it governs is a plausible, worth-flagging
contributor to severance for ANY chunker, NuggetIndex included, so it is
computed and reported here per instruction rather than left unexamined.

METHOD AND ITS LIMITS, STATED PLAINLY: sentences are split with a naive
regex (`(?<=[.!?])\\s+`) -- no abbreviation handling, no quote-aware
splitting. `nucleus`/`satellite` (as elicited by
../relation_classifier.py's Stage-1 call, logged in
../logs/task7_experiment_govern_log.jsonl) are located by exact
substring match against a sentence. When BOTH are found as exact
substrings of (possibly different) single sentences, boundary-spanning
is determined exactly. When either is NOT found as a verbatim substring
of any single sentence (e.g. the elicitation paraphrased whitespace, or
a nucleus/satellite genuinely spans what our naive splitter treats as
two sentences), this check honestly reports `determinable: False` rather
than guessing -- per this project's no-silent-fallback convention, an
inconclusive case is reported as inconclusive, not silently coerced to
True or False.
"""

import re

_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")


def split_sentences(paragraph):
    parts = _SENTENCE_SPLIT_RE.split((paragraph or "").strip())
    return [p for p in parts if p]


def _sentence_index_of(sentences, span):
    span = (span or "").strip()
    if not span:
        return None
    for i, s in enumerate(sentences):
        if span in s:
            return i
    return None


def check_boundary_spanning(paragraph, nucleus, satellite):
    """Returns {"determinable": bool, "spans_boundary": bool or None,
    "detail": str}. `spans_boundary` is None whenever `determinable` is
    False -- never a guessed True/False.
    """
    sentences = split_sentences(paragraph)
    nucleus_idx = _sentence_index_of(sentences, nucleus)
    satellite_idx = _sentence_index_of(sentences, satellite)
    if nucleus_idx is None or satellite_idx is None:
        return {
            "determinable": False,
            "spans_boundary": None,
            "detail": (
                "nucleus and/or satellite not found as an exact substring of a single "
                f"sentence out of {len(sentences)} naively-split sentences -- cannot "
                "determine sentence-boundary status via substring match."
            ),
        }
    return {
        "determinable": True,
        "spans_boundary": nucleus_idx != satellite_idx,
        "detail": (
            f"nucleus found in sentence index {nucleus_idx}, satellite in sentence "
            f"index {satellite_idx} (of {len(sentences)} sentences)."
        ),
    }


def flag_boundary_spanning_severed_cases(records, severed_key="severed"):
    """`records`: list of dicts each with at least `content`, `nucleus`,
    `satellite`, `pool_index`, and a boolean `severed_key`. Returns
    (flagged, summary) where `flagged` is the list of severed records
    whose boundary check is determinable AND spans_boundary is True.
    """
    flagged = []
    n_determinable = 0
    n_indeterminable_among_severed = 0
    for r in records:
        if not r.get(severed_key):
            continue
        chk = check_boundary_spanning(r["content"], r.get("nucleus"), r.get("satellite"))
        if chk["determinable"]:
            n_determinable += 1
            if chk["spans_boundary"]:
                flagged.append({
                    "pool_index": r["pool_index"],
                    "relation_type": r.get("relation_type"),
                    "connective": r.get("connective"),
                    "boundary_check": chk,
                })
        else:
            n_indeterminable_among_severed += 1

    summary = {
        "n_severed_cases_checked": sum(1 for r in records if r.get(severed_key)),
        "n_determinable": n_determinable,
        "n_indeterminable": n_indeterminable_among_severed,
        "n_flagged_boundary_spanning": len(flagged),
        "flagged_pool_indices": sorted(f["pool_index"] for f in flagged),
    }
    return flagged, summary
