"""Task 6, Stage 1.5: free, deterministic, non-LLM pre-filter applied to
every Stage-1 (relation_classifier.py) Condition/Concession hit before it
is allowed to reach Stage 2's paid verification call.

WHY THIS EXISTS: task5b's spot-check (results/task5b_revised_precision_report.json,
"spot_check" key) documented a 5th failure mode not addressed by any prior
prompt revision -- the classifier sometimes reports a "connective" and/or
"satellite" string that does not actually appear anywhere in the source
paragraph at all (a HALLUCINATED span, e.g. pool_index 1108/1148 where the
stated connective "if" appears nowhere in the source text). That failure
mode is purely mechanical to detect -- it doesn't require any judgment
about discourse relations, just a string-containment check -- so catching
it here costs zero LLM calls, consistent with this project's established
practice elsewhere in discourse_severance/ of using cheap, fully
inspectable, non-LLM checks wherever a check does not actually require a
model's judgment (see exception_reclassification.py's
`connective_grounding_caveat` and severance_detection.py's rule-based
check, both of which independently arrived at the same
verbatim-substring-in-source idea for a related but distinct purpose).
This module is a fresh, self-contained implementation for this track (per
env_utils.py's docstring on why factoidwiki_track/ does not import its
siblings), not a reuse of that code.

SCOPE, DELIBERATELY NARROW: this filter checks only "connective" and
"satellite" groundedness, per the task brief -- NOT whether the satellite
correctly governs the specific nucleus the classifier paired it with
(misattachment). That is a semantic judgment ("do these two spans really
stand in a Condition/Concession relationship to EACH OTHER"), not a
mechanical one, so it is deliberately left to Stage 2's check 5 rather
than attempted here. "nucleus" groundedness IS additionally computed and
logged below (it's free), but purely as a DIAGNOSTIC field -- it is never
used to reject a candidate, so the pass/fail semantics stay exactly what
the task brief specified.

NEAR-VERBATIM, DEFINED PRECISELY (so this stays auditable rather than a
vague fuzzy-match): a snippet is "grounded" in the source paragraph if,
after (a) Unicode NFKC normalization, (b) folding curly quotes/dashes to
their plain-ASCII equivalents, (c) lowercasing, and (d) collapsing all
whitespace runs to a single space, the normalized snippet is a substring
of the normalized paragraph -- OR the same is true after additionally
stripping one layer of leading/trailing punctuation from the snippet
(handles a model tidying up a clause boundary, e.g. adding a period the
source doesn't have at that exact spot because the sentence continues).
Deliberately NOT fuzzy/edit-distance matching beyond that: allowing
arbitrary near-matches would let real hallucinations slip through, which
defeats the point of this filter.
"""

import re
import unicodedata

_QUOTE_DASH_MAP = str.maketrans({
    "‘": "'",   # left single quote
    "’": "'",   # right single quote / apostrophe
    "‚": "'",
    "‛": "'",
    "“": '"',   # left double quote
    "”": '"',   # right double quote
    "„": '"',
    "–": "-",   # en dash
    "—": "-",   # em dash
    "−": "-",   # minus sign
})

_BOUNDARY_PUNCT = " \t\n\r.,;:!?\"'()[]{}‘’“”-–—"


def normalize_text(s):
    """Case/whitespace/punctuation-shape normalization only -- never
    changes wording. See module docstring for the exact steps.
    """
    if s is None:
        return ""
    s = unicodedata.normalize("NFKC", str(s))
    s = s.translate(_QUOTE_DASH_MAP)
    s = s.lower()
    s = re.sub(r"\s+", " ", s)
    return s.strip()


def _strip_boundary_punct(s):
    return s.strip(_BOUNDARY_PUNCT)


def is_grounded(snippet, source_text):
    """True iff `snippet` (near-)verbatim-appears in `source_text`, per
    the normalization rules documented above. A None/empty/whitespace-only
    snippet is never grounded (fails safe -- a Condition/Concession hit is
    expected to always carry a real, non-null connective/satellite per
    relation_classifier.py's own output schema, so an empty one here is
    itself already an anomaly worth rejecting, not a pass-by-default).
    """
    if snippet is None:
        return False
    snippet = str(snippet).strip()
    if not snippet:
        return False

    norm_source = normalize_text(source_text)
    norm_snippet = normalize_text(snippet)
    if norm_snippet and norm_snippet in norm_source:
        return True

    trimmed_snippet = normalize_text(_strip_boundary_punct(snippet))
    if trimmed_snippet and trimmed_snippet in norm_source:
        return True

    return False


def prefilter_candidate(record):
    """`record` is one Stage-1 hit (a dict with at least "content",
    "connective", "satellite", "nucleus" keys -- the same shape
    run_relation_screening.py already logs). Returns the mechanical
    verdict as a dict, meant to be merged into the logged record, never
    replacing any Stage-1 field.
    """
    content = record["content"]
    connective = record.get("connective")
    satellite = record.get("satellite")
    nucleus = record.get("nucleus")

    connective_grounded = is_grounded(connective, content)
    satellite_grounded = is_grounded(satellite, content)
    nucleus_grounded_diagnostic_only = is_grounded(nucleus, content)

    passes_stage1_5 = connective_grounded and satellite_grounded

    reject_reasons = []
    if not connective_grounded:
        reject_reasons.append(
            f"connective {connective!r} not found verbatim/near-verbatim in the source paragraph "
            "(hallucinated connective)"
        )
    if not satellite_grounded:
        reject_reasons.append(
            f"satellite {satellite!r} not found verbatim/near-verbatim in the source paragraph "
            "(hallucinated satellite)"
        )

    return {
        "connective_grounded": connective_grounded,
        "satellite_grounded": satellite_grounded,
        "nucleus_grounded_diagnostic_only": nucleus_grounded_diagnostic_only,
        "passes_stage1_5": passes_stage1_5,
        "stage1_5_reject_reasons": reject_reasons,
    }
