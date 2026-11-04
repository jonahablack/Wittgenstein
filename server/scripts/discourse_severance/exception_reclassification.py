"""Reclassifies the 17 "Exception"-labeled sentences from the discourse-
severance experiments against Mann & Thompson's canonical RST CONDITION
and CONCESSION relation definitions (used verbatim below, as supplied by
the task that authorized this correction -- not this module's
paraphrase, and not relation_elicitation.py's looser five-way-classifier
gloss of "Exception").

Why this correction is needed: relation_elicitation.py's classifier
treats "Exception" as its own bucket ("a case where the nucleus does NOT
hold, or is exempted from applying"). But "Exception" is not one of
Mann & Thompson's canonical RST relations, and their own CONDITION
definition already covers restrictive/exempting conditions: "unless X",
"except when X", and "except that X" all state a satellite situation X
-- hypothetical relative to any given case -- on which the nucleus's
realization (here, which way it resolves) depends. This script re-checks
each "Exception" sentence against Mann & Thompson's CONDITION and
CONCESSION definitions and reclassifies it, or drops it if it fits
neither.

What this script does NOT do: it does NOT re-run corpus sampling,
relation elicitation, atomization, or severance judging for any of the
47 sentences already scored in discourse_severance_report.json --- every
severed/preserved verdict already in that file is reused EXACTLY as
computed, only re-grouped under corrected relation-type labels. The only
new LLM calls are:
  (1) one gpt-4o-mini reclassification call per Exception-labeled
      sentence (17 calls), and
  (2) ONLY IF the corrected Condition+Concession pool would otherwise
      fall below 30 sentences: a pre-authorized automated top-up, drawn
      from the elicitation step's already-labeled-but-unused Condition
      (and Concession, if short) sentences, run through the EXISTING
      atomization_conditions.py / severance_detection.py pipeline
      unmodified (real new verdicts for only the added sentences).

Usage
-----
    venv/bin/python server/scripts/discourse_severance/exception_reclassification.py
"""

import argparse
import datetime
import json
import os
import random
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SERVER_DIR = os.path.dirname(os.path.dirname(SCRIPT_DIR))
if SERVER_DIR not in sys.path:
    sys.path.insert(0, SERVER_DIR)

# Importing run_experiments runs its _load_server_env() at import time --
# same precedent as audit_severance.py -- so OPENAI_API_KEY is available
# to api_call.generate_response exactly as it is for the Flask app.
from scripts.discourse_severance import run_experiments  # noqa: E402,F401
from scripts.discourse_severance import atomization_conditions  # noqa: E402
from scripts.discourse_severance import severance_detection  # noqa: E402
from scripts.discourse_severance.audit_severance import short_id  # noqa: E402
from api_call import generate_response  # noqa: E402
from components.response_parsing import extract_json_from_response  # noqa: E402
from components.risk_triage import _contains_phrase  # noqa: E402

REPORT_PATH = os.path.join(SCRIPT_DIR, "discourse_severance_report.json")
ELICITATION_LOG = os.path.join(SCRIPT_DIR, "corpus_cache", "elicitation_log.jsonl")
OUTPUT_PATH = os.path.join(SCRIPT_DIR, "exception_reclassification.json")
RESULTS_MD_PATH = os.path.join(SCRIPT_DIR, "RESULTS.md")

DEFAULT_MODEL = "gpt-4o-mini"

# Lower bound on the combined Condition+Concession ("governing relations")
# pool, per task spec. Below this, an automated top-up is pre-authorized.
GOVERNING_POOL_MIN_N = 30

# Seed for the (possibly unneeded) top-up draw -- documented here for
# reproducibility, same precedent as audit_severance.py's MANUAL_AUDIT_SEED.
TOPUP_SEED = 20260811

# --- Mann & Thompson definitions, VERBATIM (per task instructions: build ---
# --- the reclassification prompt directly from these, not a paraphrase). ---

CONDITION_DEFINITION = (
    "CONDITION (Mann & Thompson): Constraints on the nucleus (N): none. "
    "Constraints on the satellite (S): S presents a hypothetical, future, "
    "or otherwise unrealized situation (relative to S's own situational "
    "context). Constraint on the N+S combination: realization of the "
    "situation presented in N depends on realization of the situation "
    "presented in S. Effect: the reader recognizes how N's realization "
    "depends on S's realization."
)

CONCESSION_DEFINITION = (
    "CONCESSION (Mann & Thompson): Constraints on N: the writer has "
    "positive regard for the situation in N. Constraints on S: the "
    "writer is not claiming the situation in S doesn't hold. Constraint "
    "on N+S: the writer acknowledges a potential or apparent "
    "incompatibility between N and S, but regards them as compatible, "
    "and recognizing that compatibility increases the reader's positive "
    "regard for N. Effect: reader's positive regard for N increases."
)

# Distinctive substring, parallel to this codebase's other PROMPT_MARKER
# constants (relation_elicitation.py, atomization_conditions.py,
# severance_detection.py), identifying this prompt if anyone stubs it later.
RECLASSIFICATION_PROMPT_MARKER = "re-examining a discourse-relation classification"


def build_reclassification_prompt(rec):
    return f"""{RECLASSIFICATION_PROMPT_MARKER} from an earlier pass of
this study. A sentence from a regulatory corpus (CFR) was originally run
through a five-way LLM classifier (Condition/Exception/Concession/
Elaboration/None) and labeled "Exception". "Exception" is that
classifier's own bucket, NOT one of Mann & Thompson's canonical RST
relations -- this task re-examines whether the sentence actually fits
Mann & Thompson's CONDITION relation, or, failing that, their CONCESSION
relation, using their definitions VERBATIM below (not a paraphrase, and
not a broader or looser reading than what is written):

{CONDITION_DEFINITION}

{CONCESSION_DEFINITION}

Scope note: restrictive/exempting phrasing such as "except when X",
"except that X", or "unless X" is, under the CONDITION definition above,
itself a form of Condition -- X is a hypothetical/unrealized situation
in S on which N's realization depends (here, on whether the excepted
case obtains in a given instance). Do not treat "except"/"unless"/
"only"-type phrasing as automatically disqualifying a sentence from
Condition just because an earlier pass called it "Exception" -- but
also do not stretch the definition to cover phrasing that is not
actually hypothetical/conditional at all (e.g. a plain definitional
carve-out of specific physical items, or a coordinated list with no
governing relation between its parts).

Sentence (ground truth -- judge against this, not just the possibly-
imperfect fields below): "{rec['sentence']}"
Nucleus (as originally elicited): {rec['nucleus']!r}
Satellite (as originally elicited): {rec['satellite']!r}
Connective (as originally elicited): {rec['connective']!r}

Decide, in this order of priority:
1. Does the satellite, read against the nucleus IN THE SENTENCE, fit the
   CONDITION definition above?
2. If not: does it instead fit the CONCESSION definition above?
3. If it fits NEITHER definition, it belongs to no canonical relation
   used in this study and should be dropped.

Output strict JSON with exactly these keys:
  "fits_condition": true or false -- apply the CONDITION definition's
    own N / S / N+S constraints to this specific sentence
  "condition_reasoning": one or two sentences justifying fits_condition
    by reference to those constraints
  "fits_concession": true or false -- apply the CONCESSION definition's
    own N / S / N+S constraints to this specific sentence (decide this
    independently of fits_condition, so both are on record)
  "concession_reasoning": one or two sentences justifying fits_concession
    by reference to those constraints
  "new_label": "Condition" if fits_condition is true; else "Concession"
    if fits_concession is true; else "Dropped"
  "reasoning": one or two sentences giving the overall justification for
    new_label -- if "Dropped", explain specifically why the sentence
    fits NEITHER definition

Return only valid JSON. Do not include Markdown code fences or
additional text.
"""


def reclassify_exception(rec, model=DEFAULT_MODEL):
    """One LLM call: re-judge a single "Exception"-labeled sentence
    against the verbatim Condition/Concession definitions. Raises
    RuntimeError on any call/parse/validation failure rather than
    silently defaulting a relation-type label -- same fail-loud
    philosophy as audit_severance.py's sub-clause judge calls.
    """
    prompt = build_reclassification_prompt(rec)
    response = generate_response(prompt, model=model)
    if not response or not hasattr(response, "content"):
        raise RuntimeError(
            f"Reclassification call failed for {short_id(rec)}: no model "
            "response. Refusing to silently default a relation-type label."
        )
    data = extract_json_from_response(response.content)
    if not data:
        raise RuntimeError(
            f"Reclassification call failed for {short_id(rec)}: "
            "unparseable JSON response."
        )
    new_label = data.get("new_label")
    if new_label not in ("Condition", "Concession", "Dropped"):
        raise RuntimeError(
            f"Reclassification call for {short_id(rec)} returned an "
            f"invalid new_label: {new_label!r}."
        )
    return {
        "fits_condition": bool(data.get("fits_condition")),
        "condition_reasoning": data.get("condition_reasoning", ""),
        "fits_concession": bool(data.get("fits_concession")),
        "concession_reasoning": data.get("concession_reasoning", ""),
        "new_label": new_label,
        "reasoning": data.get("reasoning", ""),
    }


# --- structural (non-LLM) grounding caveat ----------------------------------
#
# The reclassification LLM call is instructed to judge against the actual
# sentence text, not just the (possibly imperfect) elicited nucleus/
# satellite/connective fields. But relation_elicitation.py's original
# elicitation pass required its "connective" field to be a VERBATIM
# substring of the sentence and did not always deliver on that -- the
# 2026-08-07 audit (audit_addendum.json, a2_no_split) already documented
# this exact failure mode elsewhere in this dataset ("elicited connective
# absent from source"). Re-checking it here, per-sentence, for the 17
# reclassified sentences is a cheap, fully inspectable, non-LLM sanity
# check on how much weight to put on each individual new_label -- it does
# NOT override or filter any verdict; every one of the 17 keeps whatever
# new_label the reclassification call returned. This mirrors the project's
# established practice of reporting caveats ALONGSIDE headline numbers
# rather than silently acting on them (e.g. the manual Condition audit
# sheet was prepared but deliberately left for a human to fill in).


def connective_grounding_caveat(rec):
    """Two structural checks against the ORIGINAL sentence text, reusing
    the exact machinery audit_severance.py's A2 step already uses
    elsewhere in this project (word-boundary-safe phrase matching,
    CONNECTIVE_WORDLIST):

      grounded_in_sentence: is the elicited "connective" actually a
        verbatim (case-insensitive) substring of the sentence? If False,
        the connective was hallucinated by the ORIGINAL elicitation call
        (a pre-existing data issue, not introduced by this script) and
        any reclassification reasoning that leans on it is reasoning
        about text that isn't really there.

      in_wordlist: is the elicited connective (or a phrase containing it)
        one of severance_detection.CONNECTIVE_WORDLIST's canonical
        Condition/Exception/Concession markers? If False, the fold-in
        rests on a broader "restrictive scope" reading (e.g. "only", "or",
        "in the case of", "to that which") rather than a canonical marker
        -- not necessarily wrong, but a looser application of the
        CONDITION definition than the clean "if"/"unless"/"except that"
        cases.
    """
    conn = (rec.get("connective") or "").strip().lower()
    if not conn:
        return {"grounded_in_sentence": False, "in_wordlist": False,
                "note": "no connective was elicited for this sentence."}
    grounded = _contains_phrase(rec["sentence"].lower(), conn)
    in_wordlist = any(_contains_phrase(conn, w) for w in severance_detection.CONNECTIVE_WORDLIST)
    notes = []
    if not grounded:
        notes.append(
            f'elicited connective {conn!r} is NOT a verbatim substring of the '
            "sentence -- carried over from the original relation_elicitation.py "
            "pass, not introduced by this reclassification."
        )
    if not in_wordlist:
        notes.append(
            f'elicited connective {conn!r} is outside CONNECTIVE_WORDLIST -- '
            "the fold-in rests on a broader restrictive-scope reading, not a "
            "canonical Condition/Exception marker."
        )
    return {
        "grounded_in_sentence": grounded,
        "in_wordlist": in_wordlist,
        "note": " ".join(notes) if notes else "no caveat.",
    }


# --- pre-authorized top-up (only runs if the governing pool is short) -------


def load_elicitation_log():
    with open(ELICITATION_LOG, encoding="utf-8") as fh:
        return [json.loads(line) for line in fh]


def build_unused_pool(elicited, relation_type, used_keys):
    """Already-labeled-but-unused sentences of `relation_type`: same
    completeness filter as run_experiments.select_samples (non-empty
    nucleus AND satellite), minus anything already spent in the saved
    47+45 sample. Sorted deterministically (part label, then sentence
    index) before any random draw, same precedent as
    audit_severance.py's manual-audit sample pool.
    """
    pool = [
        r for r in elicited
        if not r.get("_error")
        and r.get("relation_type") == relation_type
        and r.get("nucleus") and r.get("satellite")
        and (r["part_label"], r["sentence_index"]) not in used_keys
    ]
    return sorted(pool, key=lambda r: (r["part_label"], r["sentence_index"]))


def run_topup_pipeline(rec, model=None):
    """Runs the EXISTING, UNMODIFIED atomization (Condition A and B) and
    severance-judging pipeline on one top-up sentence, producing the same
    record shape as an experiment_1 record (plus an exp2-style
    "severance" alias for the Condition-A verdict) so it folds into the
    pools identically to every other record in this file.
    """
    relation = {
        "relation_type": rec["relation_type"],
        "nucleus": rec["nucleus"],
        "satellite": rec["satellite"],
        "connective": rec["connective"],
    }
    claims_a = atomization_conditions.run_condition_a(rec["sentence"])
    claims_b = atomization_conditions.run_condition_b(rec["sentence"], relation, model=model)
    severance_a = severance_detection.run_severance_checks(rec["sentence"], relation, claims_a, model=model)
    severance_b = severance_detection.run_severance_checks(rec["sentence"], relation, claims_b, model=model)
    return {
        **rec,
        "condition_a_claims": claims_a,
        "condition_b_claims": claims_b,
        "severance_a": severance_a,
        "severance_b": severance_b,
        "severance": severance_a,  # exp2-style alias (Condition-A-only field)
    }


def perform_topup(n_short, used_keys, model=None):
    """Draws a deterministic top-up sample (Condition first, Concession
    if still short) from already-labeled-but-unused elicitation records,
    runs it through the existing pipeline for real verdicts, and returns
    (topup_records_by_relation, topup_meta).
    """
    elicited = load_elicitation_log()
    condition_pool = build_unused_pool(elicited, "Condition", used_keys)
    concession_pool = build_unused_pool(elicited, "Concession", used_keys)

    rng = random.Random(TOPUP_SEED)
    n_from_condition = min(n_short, len(condition_pool))
    condition_sample = rng.sample(condition_pool, n_from_condition) if n_from_condition else []
    remaining = n_short - len(condition_sample)
    n_from_concession = min(remaining, len(concession_pool)) if remaining > 0 else 0
    concession_sample = rng.sample(concession_pool, n_from_concession) if n_from_concession else []

    print(f"  Top-up: drawing {len(condition_sample)} from the "
          f"{len(condition_pool)}-sentence unused-Condition pool and "
          f"{len(concession_sample)} from the {len(concession_pool)}-"
          f"sentence unused-Concession pool (seed={TOPUP_SEED}).")

    condition_results = []
    for rec in condition_sample:
        print(f"    running existing pipeline on top-up {short_id(rec)} (Condition)...")
        condition_results.append(run_topup_pipeline(rec, model=model))

    concession_results = []
    for rec in concession_sample:
        print(f"    running existing pipeline on top-up {short_id(rec)} (Concession)...")
        concession_results.append(run_topup_pipeline(rec, model=model))

    meta = {
        "needed": True,
        "n_short": n_short,
        "seed": TOPUP_SEED,
        "condition_pool_size": len(condition_pool),
        "concession_pool_size": len(concession_pool),
        "n_drawn_from_condition": len(condition_sample),
        "n_drawn_from_concession": len(concession_sample),
        "drawn_ids": [short_id(r) for r in condition_sample + concession_sample],
        "records": [
            {
                "id": short_id(r),
                "part_label": r["part_label"],
                "sentence_index": r["sentence_index"],
                "sentence": r["sentence"],
                "relation_type": r["relation_type"],
                "severance_a_llm_judge_preserved": res["severance_a"]["llm_judge_preserved"],
                "severance_b_llm_judge_preserved": res["severance_b"]["llm_judge_preserved"],
            }
            for r, res in zip(condition_sample + concession_sample,
                               condition_results + concession_results)
        ],
    }
    return condition_results, concession_results, meta


# --- rate/statistics helpers (identical math to run_experiments.py, ---------
# --- applied to the corrected grouping -- no severance data is recomputed) --


def rate(preds):
    vals = [p for p in preds if p is not None]
    severed = sum(1 for p in vals if p is False)
    return {"n_scored": len(vals), "n_severed": severed,
            "severed_rate": severed / len(vals) if vals else None}


def severed_preserved_counts(recs, key="severance"):
    vals = [r[key]["llm_judge_preserved"] for r in recs]
    vals = [v for v in vals if v is not None]
    severed = sum(1 for v in vals if v is False)
    preserved = len(vals) - severed
    return severed, preserved


def fisher_and_chi2(governing_severed, governing_preserved, control_severed, control_preserved):
    from scipy.stats import fisher_exact, chi2_contingency
    table = [[governing_severed, governing_preserved], [control_severed, control_preserved]]
    odds_ratio, fisher_p = fisher_exact(table)
    result = {
        "fisher_exact_p_value": fisher_p,
        "fisher_odds_ratio": odds_ratio,
    }
    if all(sum(row) > 0 for row in table) and all(sum(col) > 0 for col in zip(*table)):
        chi2, chi2_p, dof, _ = chi2_contingency(table)
        result["chi2_p_value"] = chi2_p
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--model", type=str, default=DEFAULT_MODEL)
    args = parser.parse_args(argv)

    with open(REPORT_PATH, encoding="utf-8") as fh:
        report = json.load(fh)
    exp1_records = report["experiment_1"]["records"]
    exp2_records = report["experiment_2"]["records"]
    if len(exp1_records) != 47:
        raise RuntimeError(f"Expected 47 Experiment-1 records, found {len(exp1_records)}")
    if len(exp2_records) != 92:
        raise RuntimeError(f"Expected 92 Experiment-2 records, found {len(exp2_records)}")

    exception_records = [r for r in exp1_records if r["relation_type"] == "Exception"]
    if len(exception_records) != 17:
        raise RuntimeError(f"Expected 17 Exception records, found {len(exception_records)}")

    exp2_by_key = {(r["part_label"], r["sentence_index"]): r for r in exp2_records}

    # ---------------- Step 1+2: reclassify each Exception sentence -------
    print(f"=== Reclassifying {len(exception_records)} Exception-labeled sentences "
          f"against Mann & Thompson's Condition/Concession definitions ({args.model}) ===")
    reclass_records = []
    for rec in exception_records:
        verdict = reclassify_exception(rec, model=args.model)
        exp2_rec = exp2_by_key.get((rec["part_label"], rec["sentence_index"]))
        if exp2_rec is None:
            raise RuntimeError(f"Could not find matching Experiment-2 record for {short_id(rec)}")
        caveat = connective_grounding_caveat(rec)
        entry = {
            "id": short_id(rec),
            "part_label": rec["part_label"],
            "sentence_index": rec["sentence_index"],
            "sentence": rec["sentence"],
            "nucleus": rec["nucleus"],
            "satellite": rec["satellite"],
            "connective": rec["connective"],
            "original_label": "Exception",
            "new_label": verdict["new_label"],
            "fits_condition": verdict["fits_condition"],
            "condition_reasoning": verdict["condition_reasoning"],
            "fits_concession": verdict["fits_concession"],
            "concession_reasoning": verdict["concession_reasoning"],
            "reasoning": verdict["reasoning"],
            # Structural (non-LLM) grounding caveat -- reported alongside
            # new_label, does NOT override it. See connective_grounding_caveat.
            "grounding_caveat": caveat,
            # Already-computed verdicts, reused EXACTLY as saved -- no
            # atomization or severance-judging is re-run for these 17.
            "existing_severance_a_condition_a": rec["severance_a"],
            "existing_severance_b_condition_b": rec["severance_b"],
        }
        reclass_records.append(entry)
        flag = "  [CAVEAT]" if caveat["note"] != "no caveat." else ""
        print(f"  {entry['id']:22s} Exception -> {entry['new_label']:10s} "
              f"(fits_condition={verdict['fits_condition']}, "
              f"fits_concession={verdict['fits_concession']}): "
              f"{verdict['reasoning']}{flag}")

    n_to_condition = sum(1 for e in reclass_records if e["new_label"] == "Condition")
    n_to_concession = sum(1 for e in reclass_records if e["new_label"] == "Concession")
    n_dropped = sum(1 for e in reclass_records if e["new_label"] == "Dropped")
    assert n_to_condition + n_to_concession + n_dropped == 17
    print(f"\nReclassification tally: {n_to_condition} -> Condition, "
          f"{n_to_concession} -> Concession, {n_dropped} -> Dropped")

    flagged = [e for e in reclass_records if e["grounding_caveat"]["note"] != "no caveat."]
    print(f"\nStructural grounding caveats (informational only, does NOT change "
          f"any new_label above): {len(flagged)}/17 sentences flagged")
    for e in flagged:
        print(f"  [CAVEAT] {e['id']}: {e['grounding_caveat']['note']}")

    # ---------------- Step 3: recompute pools with corrected labels ------
    exp2_condition_orig = [r for r in exp2_records if r["relation_type"] == "Condition"]
    exp2_concession_orig = [r for r in exp2_records if r["relation_type"] == "Concession"]
    exp2_elaboration = [r for r in exp2_records if r["relation_type"] == "Elaboration"]
    exp2_exception_by_key = {
        (r["part_label"], r["sentence_index"]): r
        for r in exp2_records if r["relation_type"] == "Exception"
    }
    exp1_condition_orig = [r for r in exp1_records if r["relation_type"] == "Condition"]
    exp1_concession_orig = [r for r in exp1_records if r["relation_type"] == "Concession"]
    exp1_exception_by_key = {(r["part_label"], r["sentence_index"]): r for r in exception_records}

    folded_condition_ids = [e["id"] for e in reclass_records if e["new_label"] == "Condition"]
    folded_concession_ids = [e["id"] for e in reclass_records if e["new_label"] == "Concession"]
    dropped_ids = [e["id"] for e in reclass_records if e["new_label"] == "Dropped"]

    folded_to_condition_exp2 = [exp2_exception_by_key[(e["part_label"], e["sentence_index"])]
                                 for e in reclass_records if e["new_label"] == "Condition"]
    folded_to_concession_exp2 = [exp2_exception_by_key[(e["part_label"], e["sentence_index"])]
                                  for e in reclass_records if e["new_label"] == "Concession"]
    folded_to_condition_exp1 = [exp1_exception_by_key[(e["part_label"], e["sentence_index"])]
                                 for e in reclass_records if e["new_label"] == "Condition"]
    folded_to_concession_exp1 = [exp1_exception_by_key[(e["part_label"], e["sentence_index"])]
                                  for e in reclass_records if e["new_label"] == "Concession"]

    updated_condition_pool_exp2 = exp2_condition_orig + folded_to_condition_exp2
    updated_concession_pool_exp2 = exp2_concession_orig + folded_to_concession_exp2
    updated_condition_pool_exp1 = exp1_condition_orig + folded_to_condition_exp1
    updated_concession_pool_exp1 = exp1_concession_orig + folded_to_concession_exp1

    n_condition_new = len(updated_condition_pool_exp2)
    n_concession_new = len(updated_concession_pool_exp2)
    n_governing_new = n_condition_new + n_concession_new
    print(f"\nUpdated N: Condition={n_condition_new} (17 original + {n_to_condition} folded), "
          f"Concession={n_concession_new} (13 original + {n_to_concession} folded), "
          f"combined governing pool={n_governing_new}")

    # ---------------- Step 4: pre-authorized top-up, only if short -------
    used_keys = {(r["part_label"], r["sentence_index"]) for r in exp2_records}
    if n_governing_new < GOVERNING_POOL_MIN_N:
        n_short = GOVERNING_POOL_MIN_N - n_governing_new
        print(f"\n=== Governing pool ({n_governing_new}) is below the {GOVERNING_POOL_MIN_N} "
              f"floor -- running pre-authorized top-up for {n_short} more sentence(s) ===")
        topup_condition_results, topup_concession_results, topup_meta = perform_topup(
            n_short, used_keys, model=args.model)
        updated_condition_pool_exp2 += topup_condition_results
        updated_concession_pool_exp2 += topup_concession_results
        updated_condition_pool_exp1 += topup_condition_results
        updated_concession_pool_exp1 += topup_concession_results
        n_condition_new = len(updated_condition_pool_exp2)
        n_concession_new = len(updated_concession_pool_exp2)
        n_governing_new = n_condition_new + n_concession_new
        print(f"  Post-top-up N: Condition={n_condition_new}, Concession={n_concession_new}, "
              f"combined governing pool={n_governing_new}")
    else:
        topup_meta = {
            "needed": False,
            "note": (
                f"Combined Condition+Concession N after reclassification is "
                f"{n_governing_new} (>= {GOVERNING_POOL_MIN_N}), so no top-up was "
                "necessary. This floor is structural, not incidental: the "
                "original 17 Condition + 13 Concession sentences from "
                "Experiment 1/2 are untouched by this reclassification pass "
                "(only Exception sentences were re-examined; membership can "
                "only be ADDED to Condition/Concession via a folded Exception "
                "sentence, never removed) -- so the combined pool is bounded "
                f"below by 17 + 13 = {GOVERNING_POOL_MIN_N} (if every "
                "Exception sentence turned out to fit neither definition and "
                "was dropped) and can only be larger."
            ),
        }
        print(f"\nNo top-up needed: governing pool N={n_governing_new} >= {GOVERNING_POOL_MIN_N}.")

    governing_pool_exp2 = updated_condition_pool_exp2 + updated_concession_pool_exp2

    # ---------------- Step 3 (cont'd): recompute severance-rate stats ----
    gov_severed, gov_preserved = severed_preserved_counts(governing_pool_exp2, key="severance")
    ctrl_severed, ctrl_preserved = severed_preserved_counts(exp2_elaboration, key="severance")

    updated_statistical_test = {
        "governing_pool_n": gov_severed + gov_preserved,
        "governing_pool_severed": gov_severed,
        "governing_pool_severed_rate": (
            gov_severed / (gov_severed + gov_preserved) if (gov_severed + gov_preserved) else None
        ),
        "control_n": ctrl_severed + ctrl_preserved,
        "control_severed": ctrl_severed,
        "control_severed_rate": (
            ctrl_severed / (ctrl_severed + ctrl_preserved) if (ctrl_severed + ctrl_preserved) else None
        ),
        "test_note": (
            "Fisher's exact test on the 2x2 severed/preserved table, "
            "CORRECTED grouping: Condition+Concession (pooled, Exception "
            "folded in or dropped per the reclassification above) vs "
            "Elaboration control. Uses the ALREADY-COMPUTED per-sentence "
            "Condition-A LLM-judge severed/preserved verdicts from "
            "experiment_1/experiment_2 (plus real new verdicts for any "
            "top-up sentences) -- only the grouping changed, no severance "
            "judging was re-run for any originally-scored sentence."
        ),
    }
    updated_statistical_test.update(fisher_and_chi2(gov_severed, gov_preserved, ctrl_severed, ctrl_preserved))

    print("\n=== Corrected governing-relations vs Elaboration severance comparison ===")
    print(f"  Governing pool (Condition+Concession, corrected): "
          f"{gov_severed}/{gov_severed + gov_preserved} severed "
          f"({100 * gov_severed / (gov_severed + gov_preserved):.1f}%)")
    print(f"  Elaboration control: {ctrl_severed}/{ctrl_severed + ctrl_preserved} severed "
          f"({100 * ctrl_severed / (ctrl_severed + ctrl_preserved):.1f}%)")
    print(f"  Fisher's exact p-value: {updated_statistical_test['fisher_exact_p_value']:.6g} "
          f"(odds ratio {updated_statistical_test['fisher_odds_ratio']:.3f})")
    if "chi2_p_value" in updated_statistical_test:
        print(f"  Chi-square p-value: {updated_statistical_test['chi2_p_value']:.6g}")

    # ---------------- bonus: corrected Experiment-1-style A/B breakdown --
    updated_exp1_breakdown = {
        "Condition": {
            "n": len(updated_condition_pool_exp1),
            "llm_judge_severed_rate_a": rate([r["severance_a"]["llm_judge_preserved"] for r in updated_condition_pool_exp1]),
            "llm_judge_severed_rate_b": rate([r["severance_b"]["llm_judge_preserved"] for r in updated_condition_pool_exp1]),
        },
        "Concession": {
            "n": len(updated_concession_pool_exp1),
            "llm_judge_severed_rate_a": rate([r["severance_a"]["llm_judge_preserved"] for r in updated_concession_pool_exp1]),
            "llm_judge_severed_rate_b": rate([r["severance_b"]["llm_judge_preserved"] for r in updated_concession_pool_exp1]),
        },
    }

    # ---------------- write JSON output -----------------------------------
    output = {
        "run_date": datetime.date.today().isoformat(),
        "source_report": os.path.basename(REPORT_PATH),
        "note": (
            "Post-hoc RELATION-TYPE-LABEL correction of SAVED results. "
            "Original headline numbers in discourse_severance_report.json "
            "and RESULTS.md are untouched. No atomization or severance-"
            "judging was re-run for any of the 47 originally-scored "
            "sentences -- only the relation-type grouping changed, per "
            "Mann & Thompson's canonical Condition/Concession definitions."
        ),
        "theoretical_grounding": {
            "condition_definition": CONDITION_DEFINITION,
            "concession_definition": CONCESSION_DEFINITION,
            "source_note": (
                "Verbatim Mann & Thompson RST relation definitions, supplied "
                "by the task that authorized this correction (verified via "
                "live fetch of Mann & Thompson's foundational RST document)."
            ),
        },
        "reclassification": {
            "model": args.model,
            "n_exception_sentences": len(exception_records),
            "records": reclass_records,
            "summary": {
                "n_folded_to_condition": n_to_condition,
                "n_folded_to_concession": n_to_concession,
                "n_dropped": n_dropped,
                "folded_to_condition_ids": folded_condition_ids,
                "folded_to_concession_ids": folded_concession_ids,
                "dropped_ids": dropped_ids,
            },
            "data_quality_caveats": {
                "note": (
                    "Structural (non-LLM) checks, informational only -- they do "
                    "NOT override any new_label above. 'grounded_in_sentence' "
                    "checks whether the elicited connective is a verbatim "
                    "substring of the sentence (False = hallucinated by the "
                    "ORIGINAL relation_elicitation.py pass, not by this script). "
                    "'in_wordlist' checks whether the connective is one of "
                    "severance_detection.CONNECTIVE_WORDLIST's canonical "
                    "Condition/Exception/Concession markers (False = the fold-in "
                    "rests on a broader restrictive-scope reading, e.g. 'only', "
                    "'or', 'in the case of', 'to that which')."
                ),
                "n_flagged": len(flagged),
                "flagged_ids": [e["id"] for e in flagged],
                "flagged_detail": [
                    {"id": e["id"], "new_label": e["new_label"], "connective": e["connective"],
                     **e["grounding_caveat"]}
                    for e in flagged
                ],
            },
        },
        "updated_pools": {
            "condition_n_original": 17,
            "condition_n_updated": n_condition_new,
            "concession_n_original": 13,
            "concession_n_updated": n_concession_new,
            "governing_pool_definition_original": "Condition + Exception + Concession (pooled), N=47",
            "governing_pool_n_original": 47,
            "governing_pool_definition_updated": "Condition + Concession (pooled; Exception eliminated as a category -- folded in or dropped), N as below",
            "governing_pool_n_updated": n_governing_new,
            "elaboration_control_n": len(exp2_elaboration),
        },
        "updated_experiment_1_style_breakdown_llm_judge": updated_exp1_breakdown,
        "updated_experiment_2_style_statistical_test": updated_statistical_test,
        "topup": topup_meta,
    }
    with open(OUTPUT_PATH, "w", encoding="utf-8") as fh:
        json.dump(output, fh, indent=2, ensure_ascii=False)
    print(f"\nWrote {OUTPUT_PATH}")

    # ---------------- Step 5: append addendum section to RESULTS.md ------
    append_results_md(output, path=RESULTS_MD_PATH)
    print(f"Appended reclassification addendum to {RESULTS_MD_PATH}")
    return 0


def _fmt_rate(rate_dict):
    if rate_dict is None or rate_dict.get("severed_rate") is None:
        return "n/a"
    return f"{rate_dict['n_severed']}/{rate_dict['n_scored']} ({100*rate_dict['severed_rate']:.1f}%)"


def append_results_md(output, path=RESULTS_MD_PATH):
    with open(path, encoding="utf-8") as fh:
        existing = fh.read()

    recl = output["reclassification"]
    pools = output["updated_pools"]
    st = output["updated_experiment_2_style_statistical_test"]
    exp1b = output["updated_experiment_1_style_breakdown_llm_judge"]
    topup = output["topup"]

    lines = [
        "",
        "---",
        "",
        f"# Exception reclassification addendum ({output['run_date']}): "
        "folding restrictive-condition sentences into Condition",
        "",
        "Post-hoc RELATION-TYPE-LABEL correction of the SAVED results "
        "above, run by "
        "`server/scripts/discourse_severance/exception_reclassification.py`. "
        "**All original numbers above (including the 2026-08-07 audit "
        "addendum) are untouched** -- this section re-groups the same "
        "already-computed per-sentence severed/preserved verdicts under "
        "corrected relation-type labels. Machine-readable results: "
        "`server/scripts/discourse_severance/exception_reclassification.json`.",
        "",
        "## Why",
        "",
        "`relation_elicitation.py`'s five-way classifier treats "
        "\"Exception\" as its own bucket (\"a case where the nucleus does "
        "NOT hold, or is exempted from applying\"). But Exception is not "
        "one of Mann & Thompson's canonical RST relations, and their own "
        "CONDITION definition already covers restrictive/exempting "
        "conditions -- \"unless X\", \"except when X\", \"except that X\" all "
        "state a satellite situation X on which the nucleus's realization "
        "depends. Every one of the 17 sentences originally labeled "
        "\"Exception\" (across both CFR parts) was re-judged against Mann "
        "& Thompson's CONDITION definition and, failing that, their "
        "CONCESSION definition, verbatim (both quoted below), using one "
        f"`{recl['model']}` call per sentence. No atomization or "
        "severance-judging was re-run for any of the 47 originally-scored "
        "sentences -- only the relation-type grouping changed.",
        "",
        "**Definitions used, verbatim** (per the task that authorized this "
        "correction; not a paraphrase):",
        "",
        "> " + output["theoretical_grounding"]["condition_definition"],
        "",
        "> " + output["theoretical_grounding"]["concession_definition"],
        "",
        "## Per-sentence reclassification (17 of 17 originally-\"Exception\" sentences)",
        "",
        "| ID | Original | New label | Caveat | Reasoning |",
        "|---|---|---|---|---|",
    ]
    dq = output["reclassification"]["data_quality_caveats"]
    flagged_ids = set(dq["flagged_ids"])
    for e in recl["records"]:
        reasoning = e["reasoning"].replace("|", "/").replace("\n", " ")
        caveat_mark = "**yes** (see below)" if e["id"] in flagged_ids else ""
        lines.append(f"| {e['id']} | Exception | **{e['new_label']}** | {caveat_mark} | {reasoning} |")

    lines += [
        "",
        f"- Folded into Condition: **{recl['summary']['n_folded_to_condition']}** "
        f"({', '.join(recl['summary']['folded_to_condition_ids']) or 'none'})",
        f"- Folded into Concession: **{recl['summary']['n_folded_to_concession']}** "
        f"({', '.join(recl['summary']['folded_to_concession_ids']) or 'none'})",
        f"- Dropped (fits neither Condition nor Concession): "
        f"**{recl['summary']['n_dropped']}** "
        f"({', '.join(recl['summary']['dropped_ids']) or 'none'})",
        "",
        "### Data-quality caveats (informational -- do NOT change any new_label above)",
        "",
        dq["note"],
        "",
        f"**{dq['n_flagged']}/17 sentences flagged:**",
        "",
    ]
    for d in dq["flagged_detail"]:
        lines.append(f"- **{d['id']}** (-> {d['new_label']}, connective {d['connective']!r}): {d['note']}")
    lines += [
        "",
        "## Updated pool sizes",
        "",
        "| Pool | Original N | Updated N |",
        "|---|---|---|",
        f"| Condition | {pools['condition_n_original']} | {pools['condition_n_updated']} |",
        f"| Concession | {pools['concession_n_original']} | {pools['concession_n_updated']} |",
        f"| Governing relations (pooled) | {pools['governing_pool_n_original']} "
        f"(Condition+Exception+Concession) | {pools['governing_pool_n_updated']} "
        "(Condition+Concession; Exception eliminated as a category) |",
        f"| Elaboration control (unchanged) | {pools['elaboration_control_n']} | "
        f"{pools['elaboration_control_n']} |",
        "",
        "## Top-up",
        "",
        (f"**Needed.** {topup.get('n_short', '?')} additional sentence(s) were "
         f"drawn (seed={topup.get('seed')}) from the already-labeled-but-"
         f"unused elicitation pool: {topup.get('n_drawn_from_condition', 0)} "
         f"from the {topup.get('condition_pool_size', '?')}-sentence unused-"
         f"Condition pool, {topup.get('n_drawn_from_concession', 0)} from the "
         f"{topup.get('concession_pool_size', '?')}-sentence unused-"
         f"Concession pool, run through the existing atomization + "
         f"severance-judging pipeline for real verdicts: "
         f"{', '.join(topup.get('drawn_ids', [])) or 'none'}."
         if topup.get("needed") else
         f"**Not needed.** {topup.get('note', '')}"),
        "",
        "## Corrected Experiment 1-style breakdown (LLM-judge, by corrected relation type)",
        "",
        "| Relation | N | Severed under A | Severed under B |",
        "|---|---|---|---|",
    ]
    for rt in ("Condition", "Concession"):
        d = exp1b[rt]
        lines.append(f"| {rt} | {d['n']} | {_fmt_rate(d['llm_judge_severed_rate_a'])} | "
                      f"{_fmt_rate(d['llm_judge_severed_rate_b'])} |")

    lines += [
        "",
        "## Corrected Experiment 2-style statistical test",
        "",
        "| | Original grouping (Condition+Exception+Concession) | "
        "Corrected grouping (Condition+Concession) |",
        "|---|---|---|",
        f"| Governing pool severed | 39/47 (83.0%) | {st['governing_pool_severed']}/"
        f"{st['governing_pool_n']} "
        f"({100*st['governing_pool_severed_rate']:.1f}%) |",
        f"| Elaboration control severed | 11/45 (24.4%) | {st['control_severed']}/"
        f"{st['control_n']} ({100*st['control_severed_rate']:.1f}%) |",
        f"| Fisher's exact p-value | 0.0000 (2.03e-08) | "
        f"{st['fisher_exact_p_value']:.6g} |",
    ]
    if "chi2_p_value" in st:
        lines.append(f"| Chi-square p-value | 0.0000 (5.79e-08) | {st['chi2_p_value']:.6g} |")
    lines += [
        "",
        f"- {st['test_note']}",
        "",
    ]

    with open(path, "w", encoding="utf-8") as fh:
        fh.write(existing.rstrip("\n") + "\n" + "\n".join(lines) + "\n")


if __name__ == "__main__":
    sys.exit(main())
