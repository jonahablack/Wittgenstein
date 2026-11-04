"""NuggetIndex Experiment 3 (repair-arm reliability, reduced 3-arm scope):
fixed evaluation-set derivation.

SCOPE (decided upstream by the project owner, not re-litigated here --
see run_nuggetindex_exp3.py's SCOPE_NOTE for the full reasoning): only
THREE of the six arms ../../run_experiment_3.py runs for
FactoidWiki/Propositionizer are run for NuggetIndex here -- arm 1 (no
elicitation), arm 5 (parent-segment fallback), and arm 6 (flagged
deferral). This module only derives the eval set; it makes no arm-related
decisions itself.

EVAL SET: every ../logs/nuggetindex_govern_log.jsonl (272 records: 75
Condition + 197 Concession) case that is "severed" -- i.e. NuggetIndex's
own extracted triples do not preserve the identified Condition/Concession
relation, per triple_severance_judge.py's saved verdict -- BUNDLING-
CORRECTED per ../results/nuggetindex_nucleus_bundling_audit.json (the
audit already done for this chunker), not the raw severed set. Both
variants are implemented here (`bundling_corrected=True/False`); the
default and the one run_nuggetindex_exp3.py uses is the CORRECTED set,
and the report states this explicitly.

The correction is NOT simply "raw severed minus the audit's
future_eval_exclusion_list". The audit's bundled-nucleus subset (13
records) gets its verdict SWAPPED for the sub-clause-scoped triple
judge's verdict wherever the two differ (see audit_nucleus_bundling.py's
`adjusted_secondary_figures`), which nets out to THREE edits versus the
raw 206-case severed pool, not two:

  - EXCLUDED (originally severed under the full-nucleus judge, sub-clause
    judge says preserved): pool_index 1936, 4920 -- this pair IS the
    audit's own `future_eval_exclusion_list`.
  - INCLUDED (originally preserved/NOT severed under the full-nucleus
    judge, but the sub-clause judge says severed): pool_index 1840 --
    this is NOT in `future_eval_exclusion_list` (that list only names
    exclusions, i.e. flips in the other direction). Found instead by
    reading `verdict_change.subclause_preserved` across all 13 bundled
    records in the audit file -- pool_index 1840 is the only one that
    flips preserved(True) -> severed(False).

  206 - 2 + 1 = 205, matching nuggetindex_nucleus_bundling_audit.json's
  own `adjusted_secondary_figures.nuggetindex_overall.adjusted_severed`
  (205) and `.nuggetindex_by_relation_type` (Condition 60 unchanged,
  Concession 146 -> 145; 60 + 145 = 205). Asserted below at load time,
  never assumed -- a mismatch means the upstream logs changed and this
  eval set must not be silently built from different data.

For pool_index 1840, the "saved severance" verdict/reasoning carried into
this eval set (used as arm 1's judge output, and reused as arm 6's judge
output too -- see run_nuggetindex_exp3.py) is the SUB-CLAUSE judge's
verdict (`subclause_judge` in the audit file), not the original
full-nucleus `severance_nuggetindex` -- using the original here would
directly contradict why the case is included at all (it says
preserved=True). For every other included case -- including the other 11
bundled-but-unflipped records (their sub-clause and full-nucleus verdicts
agree) -- the original saved `severance_nuggetindex` verdict is carried
through unchanged, since it never conflicts with the correction.

This module never re-runs or recomputes any severance judge -- it only
filters/reads verdicts two upstream scripts (run_nuggetindex_experiment.py,
audit_nucleus_bundling.py) already computed and saved to disk.
"""

import json

from exp3_paths import BUNDLING_AUDIT_PATH, NUGGETINDEX_GOVERN_LOG, load_jsonl

EXPECTED_N_GOVERN_LOG_RECORDS = 272
EXPECTED_N_CONDITION_RAW = 60
EXPECTED_N_CONCESSION_RAW = 146
EXPECTED_N_RAW_SEVERED = 206

# The three bundling-audit edits versus the raw severed pool -- see module
# docstring. EXCLUDE = flips severed->preserved (== the audit's own
# future_eval_exclusion_list, verified against it at load time below).
# INCLUDE = the one flip in the other direction, preserved->severed, which
# the audit file does NOT enumerate as a named list (only found by reading
# verdict_change across all 13 bundled records).
BUNDLING_EXCLUDE_POOL_INDICES = {1936, 4920}
BUNDLING_INCLUDE_POOL_INDICES = {1840}

EXPECTED_N_CONDITION_CORRECTED = 60
EXPECTED_N_CONCESSION_CORRECTED = 145
EXPECTED_N_CORRECTED = 205


def _load_bundling_audit(path=BUNDLING_AUDIT_PATH):
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def _bundling_corrections(audit):
    """pool_index -> correction info, for exactly the 13 bundled records
    in the audit file. Every other (non-bundled) record is untouched by
    the correction.
    """
    corrections = {}
    for entry in audit["records"]:
        pi = entry["pool_index"]
        vc = entry["verdict_change"]
        corrections[pi] = {
            "subclause_preserved": vc["subclause_preserved"],
            "subclause_reasoning": entry["subclause_judge"]["reasoning"],
            "original_full_nucleus_preserved": vc["original_full_nucleus_preserved"],
            "changed": vc["changed"],
            "clarity": entry["clarity"],
            "governed_subclause": entry.get("governed_subclause"),
        }
    return corrections


def _verify_bundling_edit_sets(corrections):
    """Assert the two edit sets hard-coded above (EXCLUDE/INCLUDE) are
    exactly what the audit file itself contains, so a change to the
    audit's underlying LLM verdicts would fail loudly here rather than
    silently building an eval set that no longer matches the audit's own
    adjusted_secondary_figures.
    """
    exclude_found = {pi for pi, c in corrections.items()
                     if c["original_full_nucleus_preserved"] is False and c["subclause_preserved"] is True}
    include_found = {pi for pi, c in corrections.items()
                     if c["original_full_nucleus_preserved"] is True and c["subclause_preserved"] is False}
    if exclude_found != BUNDLING_EXCLUDE_POOL_INDICES:
        raise AssertionError(
            f"FATAL: bundling-audit severed->preserved flips changed. Expected "
            f"{BUNDLING_EXCLUDE_POOL_INDICES}, found {exclude_found} in {BUNDLING_AUDIT_PATH}."
        )
    if include_found != BUNDLING_INCLUDE_POOL_INDICES:
        raise AssertionError(
            f"FATAL: bundling-audit preserved->severed flips changed. Expected "
            f"{BUNDLING_INCLUDE_POOL_INDICES}, found {include_found} in {BUNDLING_AUDIT_PATH}."
        )


def _build_case(r, verdict, judge_variant, bundling_corrected_case):
    return {
        "pool_index": r["pool_index"],
        "relation_type": r["relation_type"],
        "title": r["title"],
        "section": r["section"],
        "content": r["content"],
        "relation": {
            "relation_type": r["relation_type"],
            "nucleus": r["nucleus"],
            "satellite": r["satellite"],
            "connective": r["connective"],
        },
        "nuggetindex_triples": r["nuggetindex_triples"],
        "nuggetindex_triples_rendered": r["nuggetindex_triples_rendered"],
        "n_nuggetindex_triples": r["n_nuggetindex_triples"],
        "nuggetindex_extraction_error": r["nuggetindex_extraction_error"],
        "saved_severance_nuggetindex": verdict,
        "judge_variant": judge_variant,
        "bundling_corrected_case": bundling_corrected_case,
    }


def derive_eval_set(bundling_corrected=True, govern_log_path=NUGGETINDEX_GOVERN_LOG,
                     audit_path=BUNDLING_AUDIT_PATH):
    """Returns (eval_records, derivation_meta).

    bundling_corrected=True (default, and what run_nuggetindex_exp3.py
    uses): apply the 3-edit bundling correction described in the module
    docstring -> 205 cases (60 Condition + 145 Concession).
    bundling_corrected=False: the RAW severed set, no correction -> 206
    cases (60 Condition + 146 Concession), for comparison only.
    """
    records = load_jsonl(govern_log_path)
    if len(records) != EXPECTED_N_GOVERN_LOG_RECORDS:
        raise AssertionError(
            f"FATAL: expected {EXPECTED_N_GOVERN_LOG_RECORDS} records in {govern_log_path}, "
            f"found {len(records)} -- source govern_log changed since this track's Task finished?"
        )

    raw_severed = [r for r in records if r["severance_nuggetindex"]["preserved"] is False]
    n_condition_raw = sum(1 for r in raw_severed if r["relation_type"] == "Condition")
    n_concession_raw = sum(1 for r in raw_severed if r["relation_type"] == "Concession")
    if (n_condition_raw != EXPECTED_N_CONDITION_RAW or n_concession_raw != EXPECTED_N_CONCESSION_RAW
            or len(raw_severed) != EXPECTED_N_RAW_SEVERED):
        raise AssertionError(
            f"FATAL: expected {EXPECTED_N_CONDITION_RAW} Condition + {EXPECTED_N_CONCESSION_RAW} "
            f"Concession raw-severed cases ({EXPECTED_N_RAW_SEVERED} total), found "
            f"{n_condition_raw} + {n_concession_raw} in {govern_log_path}."
        )

    if not bundling_corrected:
        eval_records = [
            _build_case(r, r["severance_nuggetindex"], "triple_severance_judge.llm_judge_triple_severance (original, uncorrected)",
                        bundling_corrected_case=False)
            for r in sorted(raw_severed, key=lambda rec: rec["pool_index"])
        ]
        derivation_meta = {
            "source_govern_log": govern_log_path,
            "source_bundling_audit": None,
            "eval_set_variant": "raw",
            "n_govern_log_records": len(records),
            "n_eval_set": len(eval_records),
            "n_condition": n_condition_raw,
            "n_concession": n_concession_raw,
            "derivation_note": (
                "RAW (bundling-UNcorrected) severed set: every nuggetindex_govern_log.jsonl "
                "record whose saved severance_nuggetindex.preserved is False. This is NOT the "
                "variant run_nuggetindex_exp3.py uses by default (see bundling_corrected=True) "
                "-- provided here only for explicit raw-vs-corrected comparison."
            ),
        }
        return eval_records, derivation_meta

    audit = _load_bundling_audit(audit_path)
    corrections = _bundling_corrections(audit)
    _verify_bundling_edit_sets(corrections)

    selected = []
    for r in records:
        pi = r["pool_index"]
        corr = corrections.get(pi)
        if corr is not None:
            preserved = corr["subclause_preserved"]
            reasoning = corr["subclause_reasoning"]
            judge_variant = ("triple_severance_judge.llm_judge_triple_severance_subclause "
                             "(bundling-audit correction)")
            was_corrected = corr["changed"]
        else:
            preserved = r["severance_nuggetindex"]["preserved"]
            reasoning = r["severance_nuggetindex"]["reasoning"]
            judge_variant = "triple_severance_judge.llm_judge_triple_severance (original, unbundled)"
            was_corrected = False
        if preserved is False:
            selected.append((r, {"preserved": preserved, "reasoning": reasoning}, judge_variant, was_corrected))

    n_condition = sum(1 for r, _, _, _ in selected if r["relation_type"] == "Condition")
    n_concession = sum(1 for r, _, _, _ in selected if r["relation_type"] == "Concession")
    if (n_condition != EXPECTED_N_CONDITION_CORRECTED or n_concession != EXPECTED_N_CONCESSION_CORRECTED
            or len(selected) != EXPECTED_N_CORRECTED):
        raise AssertionError(
            f"FATAL: expected bundling-corrected eval set of {EXPECTED_N_CONDITION_CORRECTED} "
            f"Condition + {EXPECTED_N_CONCESSION_CORRECTED} Concession ({EXPECTED_N_CORRECTED} total), "
            f"found {n_condition} + {n_concession} -- bundling audit or govern log changed?"
        )

    selected.sort(key=lambda tup: tup[0]["pool_index"])
    eval_records = [
        _build_case(r, verdict, judge_variant, bundling_corrected_case=was_corrected)
        for r, verdict, judge_variant, was_corrected in selected
    ]

    derivation_meta = {
        "source_govern_log": govern_log_path,
        "source_bundling_audit": audit_path,
        "eval_set_variant": "bundling_corrected",
        "n_govern_log_records": len(records),
        "n_raw_severed_under_nuggetindex_full_nucleus_judge": len(raw_severed),
        "bundling_correction_excluded_pool_indices": sorted(BUNDLING_EXCLUDE_POOL_INDICES),
        "bundling_correction_included_pool_indices": sorted(BUNDLING_INCLUDE_POOL_INDICES),
        "n_eval_set": len(eval_records),
        "n_condition": n_condition,
        "n_concession": n_concession,
        "derivation_note": (
            "BUNDLING-CORRECTED severed set (205 cases = 206 raw severed - 2 excluded "
            "[pool_index 1936, 4920: flip severed->preserved under the bundling audit's "
            "sub-clause-scoped triple judge] + 1 included [pool_index 1840: flips the other "
            "way, preserved->severed]). Verdicts for the 1 corrected-in case and the 2 "
            "excluded cases are NOT in nuggetindex_govern_log.jsonl's original "
            "severance_nuggetindex field -- they come from "
            "nuggetindex_nucleus_bundling_audit.json's subclause_judge instead (see this "
            "module's docstring). This is the eval-set variant run_nuggetindex_exp3.py uses "
            "by default."
        ),
    }
    return eval_records, derivation_meta
