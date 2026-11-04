"""Post-hoc "severed-with-no-split" (A2) diagnostic, adapted for
NuggetIndex's TRIPLE-shaped output.

ADAPTATION DECISION (stated explicitly, as the task that created this
script required -- do not silently force the natural-language design
onto triples without this reasoning):

../no_split_diagnostic.py's and ../atomicrag_track/no_split_diagnostic.py's
"no-split" check is: join every atomized output unit back together,
normalize (lowercase, strip all non-alphanumeric characters, collapse
whitespace), and check whether that joined-and-normalized string is
identical or near-identical (difflib ratio >= 0.95) to the normalized
source paragraph. That check is well-defined for natural-language
propositions, which are meant to be readable prose lifted close to the
source's own wording.

NuggetIndex's atomic unit is a (subject, predicate, object) triple with a
normalized, often camelCase predicate (see ../triple_severance_judge.py's
module docstring for the full judge-design reasoning this diagnostic
reuses field-for-field). A triple extractor's job is COMPRESSION into a
structured, terse form -- "International treaties are not ratified in
the UK until a minister has laid a copy..." routinely becomes something
like `subject="International treaties", predicate="notRatifiedUntil",
object="a minister has laid a copy..."`. Rendered triples joined together
will almost NEVER closely reproduce the source paragraph's own prose,
REGARDLESS of whether the extractor actually decomposed the paragraph
into many independent facts or barely touched it -- the literal
join-and-compare-ratio metric is measuring "did the extractor preserve
verbatim wording," which is not what "no split occurred" means for a
chunker whose whole design is to never preserve verbatim wording. Applied
unmodified, it would report NuggetIndex as having ~0% no-split cases
(confirmed empirically below) regardless of whether a genuine
category-error artifact exists, which would be a false negative, not a
finding.

**So the check is adapted, not discarded, to test the same underlying
question in a way that fits the triple shape: "was there any atomization
boundary that actually separated the nucleus's content from the
satellite's qualifying content, or does one single triple still contain
both, unsegmented?"** Concretely (this is the exact framing raised when
this task was assigned: "no-split for triples might mean 'exactly one
triple was extracted, containing both the nucleus and satellite content
unsegmented'"):

  1. For each triple in a record, render it (`render_triple`, reused
     unmodified from ../triple_severance_judge.py) and compute keyword-
     overlap coverage of the elicited nucleus and satellite text against
     that one triple's rendered content, using `content_keywords`
     (imported, not reimplemented, from ../../corpus.py -- the SAME
     utility and the SAME >= 0.6 "both" threshold
     ../../audit_severance.py's `connective_attachment` already uses to
     decide whether one claim's content covers two different sub-clauses
     at once).
  2. "ANY no-split" = at least one triple in the record's triple set,
     BY ITSELF, covers both the nucleus (>=60% keyword overlap) and the
     satellite (>=60% keyword overlap) -- i.e. that single triple did not
     separate nucleus content from satellite content, regardless of how
     many OTHER triples were also extracted alongside it.
  3. "STRICT no-split" = the same, AND that triple is the ONLY triple
     extracted for the record (`n_nuggetindex_triples == 1`) -- the
     triple-shaped analog of the natural-language check's "single
     proposition reproducing the source" case: the extractor did not
     decompose the paragraph at all.

The literal join-based ratio metric (unmodified from ../no_split_
diagnostic.py, applied to the rendered triples joined together) is ALSO
computed and reported below, labeled clearly as a secondary,
not-the-adopted-primary-metric number -- for transparency, not because it
is treated as informative on its own (see finding below: it fires for
exactly 1/272 records, a subset of the adapted metric's 3/272, confirming
it under-counts here for the structural reason above, not because it is
wrong on any individual record).

Does NOT re-run extraction or the primary judge -- reads the already-
written logs/nuggetindex_govern_log.jsonl and writes a NEW, additive
results file (results/nuggetindex_no_split_diagnostic.json); it never
touches results/nuggetindex_severance_report.json.

Usage:
    venv/bin/python server/scripts/discourse_severance/factoidwiki_track/nuggetindex_track/no_split_diagnostic.py
"""

import difflib
import json
import os
import re
import sys
import unicodedata

TRACK_DIR = os.path.dirname(os.path.abspath(__file__))
FACTOIDWIKI_TRACK_DIR = os.path.dirname(TRACK_DIR)
DISCOURSE_SEVERANCE_DIR = os.path.dirname(FACTOIDWIKI_TRACK_DIR)
SCRIPTS_DIR = os.path.dirname(DISCOURSE_SEVERANCE_DIR)
SERVER_DIR = os.path.dirname(SCRIPTS_DIR)
if SERVER_DIR not in sys.path:
    sys.path.insert(0, SERVER_DIR)

# Reused (not reimplemented), same utility + threshold
# ../../audit_severance.py's `connective_attachment` already relies on for
# "does this one claim's content cover two different things at once".
from scripts.discourse_severance.corpus import content_keywords  # noqa: E402

TRACK_DIR_LOCAL = os.path.dirname(os.path.abspath(__file__))
LOGS_DIR = os.path.join(TRACK_DIR_LOCAL, "logs")
RESULTS_DIR = os.path.join(TRACK_DIR_LOCAL, "results")
GOVERN_LOG = os.path.join(LOGS_DIR, "nuggetindex_govern_log.jsonl")
OUTPUT_PATH = os.path.join(RESULTS_DIR, "nuggetindex_no_split_diagnostic.json")

NO_SPLIT_RATIO_THRESHOLD = 0.95   # literal join-based metric, reported for transparency only
COVERAGE_THRESHOLD = 0.6          # matches ../../audit_severance.py connective_attachment's "both" threshold

EXPECTED_N = 272
EXPECTED_BY_RELATION = {"Condition": 75, "Concession": 197}


def _normalize(s):
    s = unicodedata.normalize("NFKC", s or "")
    s = s.lower()
    s = re.sub(r"[^a-z0-9]+", "", s)
    return s


def literal_join_ratio(paragraph, rendered_triples):
    """Secondary/informational only -- see module docstring. Unmodified
    logic from ../no_split_diagnostic.py's no_split_check, applied to the
    rendered triples joined together."""
    joined = " ".join(rendered_triples)
    ratio = difflib.SequenceMatcher(None, _normalize(paragraph), _normalize(joined)).ratio()
    return ratio


def triple_unsegmented_check(nucleus, satellite, triples, rendered_triples):
    """Adapted primary check -- see module docstring points 1-3. Returns
    the best (highest min-coverage) single triple achieving >= 0.6
    keyword-overlap coverage of BOTH nucleus and satellite, if any."""
    kw_nucleus = content_keywords(nucleus or "")
    kw_satellite = content_keywords(satellite or "")
    best = None
    for i, rendered in enumerate(rendered_triples):
        kw_triple = content_keywords(rendered)
        cov_nucleus = len(kw_triple & kw_nucleus) / len(kw_nucleus) if kw_nucleus else 0.0
        cov_satellite = len(kw_triple & kw_satellite) / len(kw_satellite) if kw_satellite else 0.0
        if cov_nucleus >= COVERAGE_THRESHOLD and cov_satellite >= COVERAGE_THRESHOLD:
            score = min(cov_nucleus, cov_satellite)
            if best is None or score > best["score"]:
                best = {
                    "triple_index": i,
                    "rendered": rendered,
                    "raw_triple": triples[i],
                    "coverage_nucleus": round(cov_nucleus, 3),
                    "coverage_satellite": round(cov_satellite, 3),
                    "score": score,
                }
    any_no_split = best is not None
    return {
        "any_no_split_unsegmented_triple": any_no_split,
        "unsegmented_triple_detail": (
            {k: v for k, v in best.items() if k != "score"} if best else None
        ),
    }


def load_records():
    with open(GOVERN_LOG, encoding="utf-8") as fh:
        recs = [json.loads(line) for line in fh]
    if len(recs) != EXPECTED_N:
        raise RuntimeError(
            f"Expected {EXPECTED_N} governing-relation records in {GOVERN_LOG}, "
            f"found {len(recs)} -- refusing to run the diagnostic against an "
            "unexpected sample."
        )
    counts = {}
    for r in recs:
        counts[r["relation_type"]] = counts.get(r["relation_type"], 0) + 1
    if counts != EXPECTED_BY_RELATION:
        raise RuntimeError(
            f"Expected relation-type counts {EXPECTED_BY_RELATION}, found "
            f"{counts} -- refusing to run the diagnostic against an unexpected sample."
        )
    return recs


def analyze(records):
    rows = []
    for r in records:
        triples = r["nuggetindex_triples"]
        rendered = r["nuggetindex_triples_rendered"]
        n = r["n_nuggetindex_triples"]
        unseg = triple_unsegmented_check(r["nucleus"], r["satellite"], triples, rendered)
        literal_ratio = literal_join_ratio(r["content"], rendered)
        any_no_split = unseg["any_no_split_unsegmented_triple"]
        strict_no_split = any_no_split and n == 1
        rows.append({
            "pool_index": r["pool_index"],
            "relation_type": r["relation_type"],
            "n_triples": n,
            "extraction_error": r["nuggetindex_extraction_error"],
            "any_no_split": any_no_split,
            "strict_no_split": strict_no_split,
            "unsegmented_triple_detail": unseg["unsegmented_triple_detail"],
            "literal_join_ratio": round(literal_ratio, 4),
            "literal_no_split_ratio_ge_0_95": literal_ratio >= NO_SPLIT_RATIO_THRESHOLD,
            "severed": r["severance_nuggetindex"]["preserved"] is False,
        })

    n_any = sum(1 for row in rows if row["any_no_split"])
    n_strict = sum(1 for row in rows if row["strict_no_split"])
    strict_yet_severed = [row for row in rows if row["strict_no_split"] and row["severed"]]
    any_yet_severed = [row for row in rows if row["any_no_split"] and row["severed"]]
    n_literal = sum(1 for row in rows if row["literal_no_split_ratio_ge_0_95"])
    n_zero_triples = sum(1 for row in rows if row["n_triples"] == 0)
    n_zero_triples_from_error = sum(
        1 for row in rows if row["n_triples"] == 0 and row["extraction_error"]
    )

    by_relation = {}
    for rt in EXPECTED_BY_RELATION:
        subset = [row for row in rows if row["relation_type"] == rt]
        by_relation[rt] = {
            "n_total": len(subset),
            "n_any_no_split": sum(1 for row in subset if row["any_no_split"]),
            "n_strict_no_split": sum(1 for row in subset if row["strict_no_split"]),
        }

    return {
        "condition": "NuggetIndex (single condition -- no Condition-B analog)",
        "n_total": len(rows),
        "n_no_split_any_unsegmented_triple": n_any,
        "n_strict_no_split_single_triple": n_strict,
        "n_strict_no_split_yet_scored_severed": len(strict_yet_severed),
        "strict_no_split_yet_severed_pool_indices": sorted(row["pool_index"] for row in strict_yet_severed),
        "n_any_no_split_yet_scored_severed": len(any_yet_severed),
        "any_no_split_yet_severed_pool_indices": sorted(row["pool_index"] for row in any_yet_severed),
        "n_literal_join_based_no_split_ratio_ge_0_95_INFORMATIONAL_ONLY": n_literal,
        "n_zero_triples_extracted": n_zero_triples,
        "n_zero_triples_extracted_from_extraction_error": n_zero_triples_from_error,
        "by_relation_type": by_relation,
        "rows_any_no_split_only": [row for row in rows if row["any_no_split"]],
    }


def main():
    records = load_records()
    result = analyze(records)

    diagnostic = {
        "audit_date": "2026-08-14",
        "source_log": os.path.basename(GOVERN_LOG),
        "note": (
            "ADAPTED for NuggetIndex's triple-shaped output -- see module docstring for "
            "the full adaptation reasoning (why the literal join-based ratio check from "
            "../no_split_diagnostic.py / ../atomicrag_track/no_split_diagnostic.py does "
            "not transfer, and what replaces it). Primary metric: "
            "'ANY no-split' = at least one single extracted triple, by itself, covers "
            f">= {COVERAGE_THRESHOLD} keyword-overlap of BOTH the nucleus and the "
            "satellite (content_keywords, imported unmodified from ../../corpus.py, "
            "same >= 0.6 threshold ../../audit_severance.py's connective_attachment "
            "already uses for its 'both' classification) -- i.e. that triple did not "
            "separate nucleus content from satellite content. 'STRICT no-split' "
            "additionally requires that triple be the ONLY one extracted "
            "(n_nuggetindex_triples == 1) -- no decomposition occurred at all. A STRICT "
            "no-split case scored severed=True is a judge/prompt category error, not an "
            "extraction failure -- nothing was actually split apart. Reported as a "
            "caveat on the headline severed rates in "
            "results/nuggetindex_severance_report.json, not a replacement for them."
        ),
        "coverage_threshold": COVERAGE_THRESHOLD,
        "literal_ratio_threshold_informational_only": NO_SPLIT_RATIO_THRESHOLD,
        "nuggetindex": result,
    }

    print(json.dumps({k: v for k, v in diagnostic.items() if k != "nuggetindex"}, indent=2))
    print(json.dumps({k: v for k, v in result.items() if k != "rows_any_no_split_only"}, indent=2))

    os.makedirs(RESULTS_DIR, exist_ok=True)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as fh:
        json.dump(diagnostic, fh, indent=2, ensure_ascii=False)
    print(f"\nWrote {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
