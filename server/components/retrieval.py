"""Query-scoped retrieval over a processed document's axioms.

SCOPE NOTE -- retrieval quality is deliberately NOT a contribution of
this work. BM25 is used here as a sufficient, standard, well-understood
baseline for lexical retrieval; it is not benchmarked against, tuned
relative to, or claimed to improve on any existing retrieval method.
The research contribution this module serves is the *triage* layer:
running risk-triage annotation on only the retrieved, query-relevant
subset of claims and surfacing them risk-tier-first. Any reasonable
retriever could be dropped in behind retrieve_claims() without changing
that contribution.

The BM25 implementation below is pure Python (Okapi BM25 with the
non-negative Lucene idf variant, ln(1 + (N - df + 0.5) / (df + 0.5))),
kept dependency-free so the venv needs no new packages. Documents are
the axioms' `english` fields; a claim with zero query-term overlap
scores exactly 0 and is excluded from results ("non-match").
"""

import math
import re

from components.risk_triage import annotate_axioms

# BM25 free parameters -- standard defaults from the literature, not tuned
# (see scope note above).
_K1 = 1.5
_B = 0.75

# risk-tier-first ordering for query results: unformalized claims are the
# most actionable ("formalization failed outright"), then descending risk.
# Unknown/missing tiers sort last rather than raising.
_TIER_ORDER = {"Unformalized": 0, "High": 1, "Medium": 2, "Low": 3}


def _tokenize(text):
    return re.findall(r"[a-z0-9]+", (text or "").lower())


def bm25_scores(doc_token_lists, query_tokens):
    """Okapi BM25 scores for one query against a small in-memory corpus.

    doc_token_lists: list of token lists (one per document).
    Returns a list of float scores, index-aligned with doc_token_lists.
    """
    n_docs = len(doc_token_lists)
    if n_docs == 0:
        return []

    avg_len = sum(len(toks) for toks in doc_token_lists) / n_docs

    # document frequency per query term (count each doc once)
    unique_query_terms = set(query_tokens)
    df = {
        term: sum(1 for toks in doc_token_lists if term in toks)
        for term in unique_query_terms
    }
    idf = {
        term: math.log(1.0 + (n_docs - df[term] + 0.5) / (df[term] + 0.5))
        for term in unique_query_terms
    }

    scores = []
    for toks in doc_token_lists:
        score = 0.0
        doc_len = len(toks)
        for term in unique_query_terms:
            tf = toks.count(term)
            if tf == 0:
                continue
            denom = tf + _K1 * (1.0 - _B + _B * (doc_len / avg_len if avg_len else 0.0))
            score += idf[term] * (tf * (_K1 + 1.0)) / denom
        scores.append(score)
    return scores


def retrieve_claims(axioms, query, top_k=10):
    """Top-k axioms by BM25 score of `query` against each axiom's `english`
    field. Axioms with zero score (no query-term overlap) are excluded --
    an empty result is a legitimate answer for an off-topic query.

    Returns a list of (axiom, score) pairs, best first. Axiom dicts are
    the caller's own objects, not copies.
    """
    query_tokens = _tokenize(query)
    if not axioms or not query_tokens:
        return []

    doc_token_lists = [_tokenize(ax.get("english", "")) for ax in axioms]
    scores = bm25_scores(doc_token_lists, query_tokens)

    scored = [(ax, s) for ax, s in zip(axioms, scores) if s > 0.0]
    scored.sort(key=lambda pair: pair[1], reverse=True)
    return scored[:top_k]


def query_document(axioms, query, top_k=10, mode="english", segment_lookup=None):
    """Query flow: retrieve, then risk-triage ONLY the retrieved subset,
    then sort risk-tier-first.

    Axioms loaded from a *_final_data.json were already annotated at
    formalize time (with the formalization mode that was actually used,
    which final_data.json does not record); those stored annotations are
    REUSED as-is. Only retrieved axioms missing a risk_tier are annotated
    here -- so triage work is always confined to (a subset of) the
    retrieved set, never the whole document, and an axiom annotated at
    formalize time under "logic" mode is never re-annotated under a
    different mode. Nothing outside the retrieved set is ever touched.

    Sort order: Unformalized, High, Medium, Low; ties within a tier are
    broken by BM25 score descending.

    Returns the sorted list of retrieved axiom dicts.
    """
    retrieved_pairs = retrieve_claims(axioms, query, top_k=top_k)
    retrieved = [ax for ax, _score in retrieved_pairs]

    # triage annotation runs on the retrieved subset only (and within it,
    # only on axioms that don't already carry a formalize-time annotation)
    unannotated = [ax for ax in retrieved if ax.get("risk_tier") is None]
    annotate_axioms(unannotated, mode=mode, segment_lookup=segment_lookup)

    score_by_id = {id(ax): score for ax, score in retrieved_pairs}
    retrieved.sort(
        key=lambda ax: (
            _TIER_ORDER.get(ax.get("risk_tier"), len(_TIER_ORDER)),
            -score_by_id[id(ax)],
        )
    )
    return retrieved
