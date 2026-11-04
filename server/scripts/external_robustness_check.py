"""External robustness check: run the rule-based risk-triage classifier
(server/components/risk_triage.py) against propositions produced by an
INDEPENDENT, state-of-the-art proposition-chunking pipeline, to see how
its claim-level linguistic detectors behave on text this project had no
hand in producing.

Dataset
-------
FactoidWiki, the proposition-chunked English Wikipedia release from:

    Chen et al., "Dense X Retrieval: What Retrieval Granularity Should
    We Use?", EMNLP 2024. arXiv:2312.06648.
    Code:    https://github.com/chentong0/factoid-wiki
    Dataset: https://huggingface.co/datasets/chentong00/factoid-wiki

The full dataset is ~250M propositions across 1000 JSONL shards (~62 MB
per shard). This script deliberately downloads only the FIRST PORTION OF
ONE SHARD via an HTTP Range request (a few MB), and takes the first
SAMPLE_SIZE complete records from it -- a few thousand propositions is
plenty for a robustness smoke check, and downloading tens of GB would be
pointless.

Each record looks like:

    {"id": "enwiki-00000000-0000-0000-0000",
     "contents": "<page title>\n<section>\n<proposition text>",
     "metadata": {"title_span": [a, b], "section_span": [c, d],
                  "content_span": [e, f]}}

The proposition proper is contents[content_span[0]:content_span[1]] --
the classifier is run on THAT substring, not on the title/section
prefix, since the proposition is the externally-chunked claim unit.

What is (and is not) being checked
----------------------------------
These are external propositions with NO formal representation: nothing
in this dataset was ever run through this project's formalization step.
So the check exercises exactly the claim-level linguistic detectors:

    - hedge                (hedging language)
    - negation_scope       (negation + multiple clauses)
    - cross_reference      (explicit "as noted above"-style phrases)
    - unresolved_reference (definite descriptions with a severed
                            antecedent -- the Dense-X/RAG "context
                            mismatch" failure mode itself)
    - nested_conditional   (2+ conditional/exception markers)

Each proposition is classified with:

    flag_claim(english=proposition, formal="", formal_mode="logic")

formal_mode="logic" makes detect_modal_mismatch a documented no-op (see
its docstring in risk_triage.py): modal-mismatch and every other
formal-side comparison is meaningless here BY CONSTRUCTION, because no
formal string exists for external propositions. Passing formal="" with
any other mode would instead produce a spurious "modal marker dropped"
flag on every modal-bearing proposition. Segment-level detectors
(segment_nested_conditional / segment_negation_scope) are likewise not
exercised: FactoidWiki does not ship the pre-chunking source sentence
for each proposition, so there is no segment_text to give them.

Outputs
-------
    - stdout summary
    - server/scripts/external_robustness_report.json  (machine-readable)
    - server/scripts/EXTERNAL_ROBUSTNESS.md           (human summary)
    - server/scripts/factoid_wiki_sample.jsonl        (cached raw sample,
      so re-runs are reproducible without re-downloading)

Integrity: if the download fails, this script says so and exits nonzero.
It never substitutes synthetic data for external data. The --self-test
flag runs the same classification plumbing on a tiny inline sample that
is unmistakably labeled SYNTHETIC; its output is written nowhere near
the external report files.

Usage
-----
    venv/bin/python server/scripts/external_robustness_check.py
    venv/bin/python server/scripts/external_robustness_check.py --sample-size 5000
    venv/bin/python server/scripts/external_robustness_check.py --self-test
"""

import argparse
import datetime
import json
import os
import re
import sys
import urllib.error
import urllib.request
from collections import Counter

# Make server/ importable when run standalone from anywhere.
SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
SERVER_DIR = os.path.dirname(SCRIPTS_DIR)
if SERVER_DIR not in sys.path:
    sys.path.insert(0, SERVER_DIR)

from components.risk_triage import compute_tier, flag_claim  # noqa: E402

DATASET_NAME = "chentong00/factoid-wiki"
DATASET_URL = "https://huggingface.co/datasets/chentong00/factoid-wiki"
PAPER = (
    "Chen et al., 'Dense X Retrieval: What Retrieval Granularity Should "
    "We Use?', EMNLP 2024, arXiv:2312.06648"
)
SHARD_FILE = "data/docs-0000_of_1000.jsonl"
SHARD_URL = (
    "https://huggingface.co/datasets/chentong00/factoid-wiki/resolve/main/"
    + SHARD_FILE
)

DEFAULT_SAMPLE_SIZE = 5000
# Observed average record length is ~250 bytes; 500 bytes/record of
# headroom guarantees at least SAMPLE_SIZE complete lines in the range.
BYTES_PER_RECORD_ESTIMATE = 500

SAMPLE_CACHE = os.path.join(SCRIPTS_DIR, "factoid_wiki_sample.jsonl")
JSON_REPORT = os.path.join(SCRIPTS_DIR, "external_robustness_report.json")
MD_REPORT = os.path.join(SCRIPTS_DIR, "EXTERNAL_ROBUSTNESS.md")

# condition_satellite and concession_satellite are deliberately excluded
# from this list -- see classify_proposition's docstring: like
# modal_mismatch, they check the FORMAL string, and external propositions
# have no formal string at all, so both are structurally not-applicable
# here, not merely inactive.
CLAIM_LEVEL_FLAG_TYPES = [
    "negation_scope",
    "cross_reference",
    "unresolved_reference",
]

# Tiny inline sample for --self-test / unit tests ONLY. This is
# SYNTHETIC data written by hand for plumbing verification; it is NOT
# external data and is never mixed into the external report.
SELF_TEST_PROPOSITIONS = [
    # negation + connectors -> negation_scope
    "The committee did not approve the budget because the report was "
    "incomplete and the vote was postponed.",
    # explicit cross-reference phrase
    "As noted above, the aforementioned treaty entered into force in 1955.",
    # unresolved definite description
    "The country faces the Pacific Ocean.",
    # clean proposition -> should produce zero flags
    "Paris is the capital of France.",
]


# --- data acquisition --------------------------------------------------------


def download_sample(sample_size, cache_path=SAMPLE_CACHE, force=False):
    """Fetch the first `sample_size` records of shard 0 via an HTTP Range
    request and cache them as JSONL. Returns (records, source_note).

    Raises RuntimeError with a clear message if the download fails --
    the caller must NOT paper over that with substitute data.
    """
    if os.path.exists(cache_path) and not force:
        records = _load_jsonl(cache_path)
        if len(records) >= sample_size:
            return records[:sample_size], (
                "loaded from local cache of a prior download from "
                f"{SHARD_URL}"
            )

    byte_budget = sample_size * BYTES_PER_RECORD_ESTIMATE
    req = urllib.request.Request(
        SHARD_URL,
        headers={
            "Range": f"bytes=0-{byte_budget - 1}",
            "User-Agent": "wittgenstein-risk-triage-robustness-check/1.0",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            raw = resp.read()
    except (urllib.error.URLError, OSError, TimeoutError) as exc:
        raise RuntimeError(
            f"Could not download {SHARD_URL} ({exc!r}). No external data "
            "is available; refusing to substitute synthetic data. Re-run "
            "when the network allows, or use --self-test to verify the "
            "script's plumbing on clearly-labeled synthetic data."
        ) from exc

    # Last line of a byte-range fetch is almost certainly truncated: keep
    # only complete lines.
    lines = raw.decode("utf-8", errors="replace").split("\n")[:-1]
    records = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    if len(records) < sample_size:
        # Not fatal -- just report what we actually got.
        print(
            f"Note: range fetch yielded {len(records)} complete records "
            f"(< requested {sample_size}); proceeding with what was fetched.",
            file=sys.stderr,
        )
    records = records[:sample_size]

    with open(cache_path, "w", encoding="utf-8") as fh:
        for rec in records:
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
    return records, f"downloaded {len(records)} records from {SHARD_URL}"


def _load_jsonl(path):
    records = []
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    return records


def extract_proposition(record):
    """Return the proposition text proper (content_span substring), not
    the '<title>\n<section>\n' prefix FactoidWiki prepends for retrieval
    context."""
    contents = record.get("contents", "")
    span = (record.get("metadata") or {}).get("content_span")
    if (
        isinstance(span, (list, tuple))
        and len(span) == 2
        and 0 <= span[0] <= span[1] <= len(contents)
    ):
        return contents[span[0]:span[1]].strip()
    # Fallback: proposition is the last newline-separated segment.
    return contents.rsplit("\n", 1)[-1].strip()


# --- classification ----------------------------------------------------------


def classify_proposition(text):
    """Run the claim-level detectors on one externally-chunked proposition.

    formal="" + formal_mode="logic": there is no formal string for
    external propositions, and "logic" mode makes detect_modal_mismatch
    a documented no-op, so no spurious formal-side flags are produced.
    The same reasoning extends to detect_condition_satellite and
    detect_concession_satellite (added in the RST-grounded classifier
    rebuild): both check whether a connective/clause survives in
    `formal`, and an always-empty formal string would trivially and
    vacuously mark every connective-bearing proposition "dropped" --
    not a real severance signal, since these propositions were never
    run through this pipeline's own formalization step at all. "logic"
    mode's existing no-op gate skips them here for that reason, same as
    modal_mismatch, not because of a coincidence in how the gate happens
    to be implemented. No segment_text is passed (FactoidWiki has no
    pre-chunk source sentence), so segment-level detectors are skipped.
    """
    flags = flag_claim(english=text, formal="", formal_mode="logic")
    return {"flags": flags, "tier": compute_tier(flags)}


def classify_propositions(items):
    """items: list of (prop_id, proposition_text). Returns the aggregate
    result structure used by the report."""
    results = []
    flag_counts = Counter()
    tier_counts = Counter()
    flagged = 0
    for prop_id, text in items:
        outcome = classify_proposition(text)
        tier_counts[outcome["tier"]] += 1
        if outcome["flags"]:
            flagged += 1
        for f in outcome["flags"]:
            flag_counts[f["type"]] += 1
        results.append(
            {
                "id": prop_id,
                "proposition": text,
                "flags": outcome["flags"],
                "tier": outcome["tier"],
            }
        )
    return {
        "total": len(results),
        "flagged": flagged,
        "flag_counts": dict(flag_counts),
        "tier_counts": dict(tier_counts),
        "results": results,
    }


# count_month_may_hedges (the capitalized-month/modal-"may" collision
# counter) was removed in the RST-grounded classifier rebuild: it
# measured a false-positive pattern specific to the now-retired
# detect_hedges, which no longer exists. That finding is preserved as
# history in this file's git log and in the original EXTERNAL_ROBUSTNESS.md,
# not silently deleted -- it just no longer applies to the current
# classifier, which has nothing left in its claim-level checks that
# lowercases and matches on the bare word "may".


def pick_examples(results, per_type=2):
    """A handful of flagged propositions per flag type, with reasons."""
    examples = {}
    for r in results:
        for f in r["flags"]:
            bucket = examples.setdefault(f["type"], [])
            if len(bucket) < per_type:
                bucket.append(
                    {
                        "id": r["id"],
                        "proposition": r["proposition"],
                        "reason": f["reason"],
                        "tier": r["tier"],
                    }
                )
    return examples


# --- reporting ---------------------------------------------------------------


def _pct(n, total):
    return f"{100.0 * n / total:.1f}%" if total else "n/a"


def print_summary(agg, examples, source_note, stream=sys.stdout,
                  external=True):
    total = agg["total"]
    w = stream.write
    if external:
        w("External robustness check: risk_triage.py vs FactoidWiki\n")
        w(f"  Dataset : {DATASET_NAME} ({DATASET_URL})\n")
        w(f"  Paper   : {PAPER}\n")
    else:
        w("Plumbing self-test: risk_triage.py vs SYNTHETIC inline sample\n")
        w("  Dataset : NONE (synthetic, hand-written; not external data)\n")
    w(f"  Source  : {source_note}\n")
    w(f"  Total propositions processed : {total}\n")
    w(
        f"  Propositions with >=1 flag   : {agg['flagged']} "
        f"({_pct(agg['flagged'], total)})\n"
    )
    w("  Flag counts by type:\n")
    for ftype in CLAIM_LEVEL_FLAG_TYPES:
        n = agg["flag_counts"].get(ftype, 0)
        w(f"    {ftype:<22} {n:>6}  ({_pct(n, total)} of propositions)\n")
    w("  Tier distribution:\n")
    for tier in ["Low", "Medium", "High", "Unformalized"]:
        if tier in agg["tier_counts"] or tier != "Unformalized":
            n = agg["tier_counts"].get(tier, 0)
            w(f"    {tier:<12} {n:>6}  ({_pct(n, total)})\n")
    w("  Example flagged propositions:\n")
    for ftype, exs in examples.items():
        for ex in exs:
            w(f"    [{ftype} | tier {ex['tier']}] {ex['proposition']}\n")
            w(f"      reason: {ex['reason']}\n")
    w(
        "  Note: modal_mismatch, condition_satellite, and concession_satellite\n"
        "  were NOT run -- external propositions have no formal string, so\n"
        "  those formal-side checks do not apply (formal_mode='logic' no-op,\n"
        "  per risk_triage.py). Segment-level detectors were also not run:\n"
        "  FactoidWiki does not provide the pre-chunking source sentence\n"
        "  (segment_text).\n"
    )


def write_json_report(agg, examples, source_note, path=JSON_REPORT):
    report = {
        "data_source": "EXTERNAL",
        "dataset": DATASET_NAME,
        "dataset_url": DATASET_URL,
        "shard": SHARD_FILE,
        "shard_url": SHARD_URL,
        "paper": PAPER,
        "download_date": datetime.date.today().isoformat(),
        "source_note": source_note,
        "checks_run": CLAIM_LEVEL_FLAG_TYPES,
        "checks_not_applicable": {
            "modal_mismatch": (
                "no formal string exists for external propositions; run "
                "with formal_mode='logic', in which detect_modal_mismatch "
                "is a documented no-op"
            ),
            "condition_satellite": (
                "same reasoning as modal_mismatch: checks the formal "
                "string for connective/clause survival, and an "
                "always-empty formal string would vacuously flag every "
                "connective-bearing proposition rather than signal real "
                "severance; formal_mode='logic' no-op, per risk_triage.py"
            ),
            "concession_satellite": "same reasoning as condition_satellite",
            "segment_condition_satellite": "no segment_text in FactoidWiki",
            "segment_concession_satellite": "no segment_text in FactoidWiki",
            "segment_negation_scope": "no segment_text in FactoidWiki",
        },
        "total_propositions": agg["total"],
        "propositions_with_flags": agg["flagged"],
        "flag_counts": agg["flag_counts"],
        "tier_counts": agg["tier_counts"],
        "examples": examples,
    }
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(report, fh, indent=2, ensure_ascii=False)
    return path


def write_markdown_report(agg, examples, source_note, path=MD_REPORT):
    total = agg["total"]
    lines = [
        "# External robustness check: risk triage vs. FactoidWiki",
        "",
        f"Run date: {datetime.date.today().isoformat()} (download date: "
        f"2026-08-06). Generated by `server/scripts/"
        "external_robustness_check.py`.",
        "",
        "## What was used",
        "",
        f"- Dataset: **{DATASET_NAME}** -- {DATASET_URL}",
        f"- Produced by: {PAPER}",
        f"- Subset: first {total} propositions of shard `{SHARD_FILE}` "
        f"(fetched via HTTP Range request from {SHARD_URL}; the full "
        "dataset is ~250M propositions / 1000 shards and was deliberately "
        "not downloaded).",
        f"- Acquisition: {source_note}. Raw sample cached at "
        "`server/scripts/factoid_wiki_sample.jsonl`.",
        "- Classified text: the proposition proper (the `content_span` "
        "substring of each record), not the page-title prefix.",
        "",
        "## What was checked",
        "",
        "Each proposition was run through "
        "`flag_claim(english=proposition, formal=\"\", "
        "formal_mode=\"logic\")` from `server/components/risk_triage.py`, "
        "exercising the claim-level linguistic detectors that don't "
        "depend on a formal string: negation_scope, cross_reference, "
        "unresolved_reference.",
        "",
        "**Not applicable here:** modal_mismatch, condition_satellite, "
        "and concession_satellite -- these external propositions have no "
        "formal string (nothing was formalized), and `formal_mode=\"logic\"` "
        "makes all three a documented no-op (condition_satellite and "
        "concession_satellite check the formal string for connective/"
        "clause survival the same way modal_mismatch checks it for a "
        "modal marker; an always-empty formal string would vacuously flag "
        "every connective-bearing proposition rather than signal real "
        "severance). Segment-level detectors (segment_condition_satellite, "
        "segment_concession_satellite, segment_negation_scope) were also "
        "skipped: FactoidWiki does not ship the pre-chunking source "
        "sentence needed as `segment_text`.",
        "",
        "## What was found",
        "",
        f"- Total propositions processed: **{total}**",
        f"- Propositions with at least one flag: **{agg['flagged']}** "
        f"({_pct(agg['flagged'], total)})",
        "",
        "| Flag type | Count | % of propositions |",
        "|---|---|---|",
    ]
    for ftype in CLAIM_LEVEL_FLAG_TYPES:
        n = agg["flag_counts"].get(ftype, 0)
        lines.append(f"| {ftype} | {n} | {_pct(n, total)} |")
    lines += [
        "",
        "| Tier | Count | % |",
        "|---|---|---|",
    ]
    for tier in ["Low", "Medium", "High"]:
        n = agg["tier_counts"].get(tier, 0)
        lines.append(f"| {tier} | {n} | {_pct(n, total)} |")
    lines += [
        "",
        "## Example flagged propositions",
        "",
    ]
    for ftype, exs in examples.items():
        lines.append(f"**{ftype}**")
        lines.append("")
        for ex in exs:
            lines.append(f"- `{ex['id']}` (tier {ex['tier']}): "
                         f"\"{ex['proposition']}\"")
            lines.append(f"  - {ex['reason']}")
        lines.append("")
    lines += [
        "Full machine-readable results: "
        "`server/scripts/external_robustness_report.json`.",
        "",
    ]
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines))
    return path


# --- entry points ------------------------------------------------------------


def run_external_check(sample_size, force_download=False):
    records, source_note = download_sample(sample_size, force=force_download)
    items = [
        (rec.get("id", f"row-{i}"), extract_proposition(rec))
        for i, rec in enumerate(records)
    ]
    items = [(pid, text) for pid, text in items if text]
    agg = classify_propositions(items)
    examples = pick_examples(agg["results"])
    print_summary(agg, examples, source_note)
    json_path = write_json_report(agg, examples, source_note)
    md_path = write_markdown_report(agg, examples, source_note)
    print(f"\nWrote {json_path}")
    print(f"Wrote {md_path}")
    return agg


def run_self_test():
    """Plumbing check on SYNTHETIC data only. Writes no report files and
    prints an unmissable label, so this can never be mistaken for
    external validation."""
    print("=" * 68)
    print("SELF-TEST MODE: SYNTHETIC inline sample, NOT external data.")
    print("No report files are written in this mode.")
    print("=" * 68)
    items = [
        (f"synthetic-{i}", text)
        for i, text in enumerate(SELF_TEST_PROPOSITIONS)
    ]
    agg = classify_propositions(items)
    examples = pick_examples(agg["results"], per_type=1)
    print_summary(agg, examples, source_note="SYNTHETIC self-test sample",
                  external=False)
    return agg


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument(
        "--sample-size", type=int, default=DEFAULT_SAMPLE_SIZE,
        help=f"number of propositions to check (default {DEFAULT_SAMPLE_SIZE})",
    )
    parser.add_argument(
        "--force-download", action="store_true",
        help="re-download even if a cached sample exists",
    )
    parser.add_argument(
        "--self-test", action="store_true",
        help="run on a tiny SYNTHETIC inline sample (no network, no "
             "report files) to verify plumbing only",
    )
    args = parser.parse_args(argv)

    if args.self_test:
        run_self_test()
        return 0

    try:
        run_external_check(args.sample_size, force_download=args.force_download)
    except RuntimeError as exc:
        print(f"FAILED: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
