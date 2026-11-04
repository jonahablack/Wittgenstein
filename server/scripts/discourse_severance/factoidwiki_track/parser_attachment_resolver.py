"""PART 0c (finalized): spaCy dependency-based marker-clause resolver.

Given a single proposition/sentence and a Condition/Concession marker
token in it, return the text span the marker grammatically governs --
its own "clause" -- for comparison against the ground-truth
nucleus/satellite text. This is the intra-proposition attachment
resolution component of the parser+NLI pipeline (Part 1's design).

Priority order, found by hand-checking against 16 real cases including
the pool 4117 reversal (a case that broke all four LLM-judge
iterations) and the pool 3278/4200 misattachment negative controls:

  1. marker.dep_ == "prep" (e.g. "despite X"): use the marker's OWN
     subtree. This is correct regardless of what the marker's head is
     attached to -- a bare prepositional phrase always projects its own
     clean span. Checked first because it dominates case 3 below when
     both would otherwise apply (pool 4200's "despite" sits inside a
     ccomp clause; using the ccomp head's subtree there overshoots into
     the surrounding clause -- the marker's own subtree does not).
  2. marker.dep_ == "mark" (e.g. "although X", "if X"): use the marker's
     HEAD's subtree -- mark children have no subtree of their own, and
     their head IS the embedded clause's own verb, so head.subtree
     cleanly bounds just that clause.
  3. marker.head.dep_ in ("advcl", "ccomp", "relcl") AND the marker is
     the first token of that subtree (i.e. the marker sits right at the
     left edge of an embedded clause, common for advmod-tagged
     subordinators like "When" that spaCy doesn't tag "mark"): use
     head.subtree, same reasoning as (2).
  4. Otherwise (advmod/cc markers like "however"/"but"/"rather" attached
     directly to a ROOT verb, no separate embedded clause structure):
     positional fallback -- the marker token onward to the end of its
     enclosing sentence. These markers work by LINEAR position, not by
     projecting their own syntactic subtree.

MULTI-WORD CONNECTIVES: find_marker_hits (pipeline_part0d.py) detects
these via substring search over raw text, which does not tell you which
spaCy TOKEN to anchor on -- spaCy tokenizes "only if" as two separate
tokens, so a naive exact-token-text match against the whole phrase can
never succeed. Verified individually against real parsed text (not
assumed to generalize from one case) which single token within each
multi-word phrase actually carries the attachment:

  - "only if", "provided that", "as long as", "even though", "even if":
    anchor on the LAST word. Each one's last word ("if"/"that"/"as"/
    "though"/"if") independently carries dep_ == "mark" with its head
    being the embedded clause's own verb -- same shape as single-word
    "if"/"though", so priority rule 2 above applies unchanged once
    anchored there. ("provided" and the first "as"/"long" in "as long
    as" attach elsewhere in the tree -- e.g. "provided" as a bare `prep`
    on the MAIN clause verb -- but the trailing subordinator is what
    actually bounds the clause, confirmed per-phrase, not assumed.)
  - "in spite of", "in the event of": anchor on the FIRST word instead.
    Both are structurally prepositional phrases parallel to single-word
    "despite" -- "In" carries dep_ == "prep" with its head being the
    MAIN clause verb; the trailing "of" attaches to the phrase's own
    object noun ("spite"/"event"), not the clause, so anchoring there
    would be wrong. Priority rule 1 applies once anchored on "In".
"""

import spacy

nlp = spacy.load("en_core_web_sm")

_MULTIWORD_FIRST_TOKEN_ANCHOR = {"in spite of", "in the event of", "in the event"}


def _find_anchor_token(doc, connective):
    """Single token for single-word connectives. For multi-word ones,
    find the matching consecutive token span and return the correct
    anchor word within it -- last word by default, first word for the
    two verified prepositional-phrase exceptions (see module docstring).
    """
    conn_lower = connective.strip(",").lower()
    words = conn_lower.split()
    if len(words) == 1:
        return next((t for t in doc if t.text.lower() == conn_lower), None)

    for i in range(len(doc) - len(words) + 1):
        if all(doc[i + j].text.lower() == words[j] for j in range(len(words))):
            span = doc[i:i + len(words)]
            return span[0] if conn_lower in _MULTIWORD_FIRST_TOKEN_ANCHOR else span[-1]
    return None


def resolve_marker_clause(text, connective):
    """Returns (clause_text, dep_used, rule_used) or (None, None, None)
    if the connective token (or, for multi-word connectives, the full
    token span) isn't found in the parsed text.
    """
    doc = nlp(text)
    tok = _find_anchor_token(doc, connective)
    if tok is None:
        return None, None, None

    if tok.dep_ == "prep":
        span = sorted(tok.subtree, key=lambda t: t.i)
        return " ".join(t.text for t in span), tok.dep_, "prep-own-subtree"

    if tok.dep_ == "mark":
        head = tok.head
        span = sorted(head.subtree, key=lambda t: t.i)
        return " ".join(t.text for t in span), tok.dep_, "mark-head-subtree"

    head = tok.head
    if head.dep_ in ("advcl", "ccomp", "relcl"):
        head_subtree = sorted(head.subtree, key=lambda t: t.i)
        if head_subtree and head_subtree[0].i == tok.i:
            return " ".join(t.text for t in head_subtree), tok.dep_, "leading-edge-head-subtree"

    sent_tokens = [t for t in tok.sent if t.i >= tok.i]
    return " ".join(t.text for t in sent_tokens), tok.dep_, "positional-fallback"
