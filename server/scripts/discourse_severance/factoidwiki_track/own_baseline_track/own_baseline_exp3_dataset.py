"""own_baseline_track Experiment 3 (repair reliability): fixed
evaluation-set derivation, mirroring ../exp3_dataset.py's design
(programmatic derivation from an already-saved log, asserted counts,
never resampled) but sourced from THIS track's own artifacts -- this
project's OWN minimal prompted baseline (own_baseline_adapter.
FRAMING_STATEMENT: "a minimal prompted baseline, included as one
additional tested system for the generality claim, not itself a claimed
contribution"), NOT Chen et al.'s Propositionizer.

The eval set is EVERY governing (Condition/Concession) paragraph that
this track's own run_own_baseline_experiment.py already scored
severed=True under its OWN Condition A output -- read directly from
logs/own_baseline_govern_log.jsonl (272 records: 75 Condition + 197
Concession). Per results/own_baseline_experiment_1_2_report.json's
experiment_1.by_relation_type ("severed_a"): 16/75 Condition + 91/197
Concession were scored severed under Condition A = 107 total. Severance
verdicts (severance_a) are REUSED byte-for-byte from that log -- this
module never re-runs or recomputes severance, only filters/reads what
run_own_baseline_experiment.py already scored.

VOCABULARY TRANSLATION (the one genuine adaptation needed here,
documented, not hidden): own_baseline_govern_log.jsonl records use this
track's own field name `condition_a_claims` (own_baseline_adapter.py's
output, matching atomization_conditions.py's own `{"claims": [...]}`
return shape -- see run_own_baseline_experiment.py's own "VOCABULARY
NOTE" docstring section, which deliberately keeps "claims", not
"propositions", to match the underlying function's own return key).
../run_experiment_3.py's reused arm-processing code (process_case,
_score_recovered, etc.) expects a `condition_a_propositions` key on each
eval record -- that is a parameter-contract name shared by every chunker
track's eval records (Propositionizer, and now this baseline), not a
claim about what the underlying chunker itself calls its own output.
This module copies `condition_a_claims` into the eval record's
`condition_a_propositions` key for that reason ONLY. own_baseline_track's
own reports/logs elsewhere keep saying "claims"; only this bridging dict
(fed into the shared, chunker-agnostic arm code) uses "propositions".

A SECOND, LEFTOVER field also lives in own_baseline_govern_log.jsonl:
`condition_a_propositions` (note: NOT the same as the bridging key this
module produces), inherited unchanged (via **rec) from
../logs/task7_experiment_govern_log.jsonl -- the PROPOSITIONIZER track's
OWN Condition-A output for these same source paragraphs, carried through
by run_own_baseline_experiment.py's `_process_govern_record` before that
function's own `condition_a_claims`/`severance_a` keys were added and
(for `severance_a`) overwrote the parent log's key of the same name.
Verified byte-identical to the parent Propositionizer log across all 272
records (spot-checked and diffed while building this module). THIS
MODULE DELIBERATELY DOES NOT READ THAT FIELD -- doing so would silently
substitute Chen et al.'s Propositionizer output for this track's own
baseline's output, exactly the mistake this eval-set derivation exists to
avoid. Only `condition_a_claims` (this track's own atomizer output) and
`severance_a` (this track's own judge verdict over that output) are read.

NUCLEUS-BUNDLING AUDIT STATUS (must be surfaced in every report this
eval set feeds): unlike AtomicRAG's exp3-equivalent severed-case pool
(bundling-corrected via ../atomicrag_track/audit_nucleus_bundling.py),
this baseline's severed-case pool has NOT yet had an equivalent bundling
audit applied -- that is separate, pending follow-up work, being done
independently. This eval set is the RAW Condition-A-severed set; a
future pass may need to exclude a small number of bundled-nucleus cases
the same way the audited tracks did.
"""

import json
import os

TRACK_DIR = os.path.dirname(os.path.abspath(__file__))  # .../own_baseline_track
LOGS_DIR = os.path.join(TRACK_DIR, "logs")

GOVERN_LOG = os.path.join(LOGS_DIR, "own_baseline_govern_log.jsonl")

# Documented in results/own_baseline_experiment_1_2_report.json's
# experiment_1.by_relation_type -> "severed_a". Asserted, not assumed -- a
# mismatch means the upstream log changed and this eval set must not be
# silently built from different data. (Analogous to ../exp3_dataset.py's
# EXPECTED_N_* constants for the Propositionizer track; numbers differ
# because this is a different chunker's own Condition-A output.)
EXPECTED_N_CONDITION_SEVERED = 16
EXPECTED_N_CONCESSION_SEVERED = 91
EXPECTED_N_TOTAL = 107

BUNDLING_AUDIT_NOTE = (
    "This eval set is the RAW Condition-A-severed set from "
    "own_baseline_govern_log.jsonl / own_baseline_experiment_1_2_report.json. "
    "Unlike AtomicRAG's severed-case pool (bundling-corrected via "
    "../atomicrag_track/audit_nucleus_bundling.py), this baseline has NOT "
    "yet had an equivalent nucleus-bundling audit applied -- that is "
    "separate, pending follow-up work, being done independently. A future "
    "pass may need to exclude a small number of bundled-nucleus cases the "
    "same way the audited tracks did."
)

VOCABULARY_NOTE = (
    "Eval records carry this track's own Condition-A output "
    "(own_baseline_govern_log.jsonl's `condition_a_claims` field, this "
    "baseline's own atomized claims) under the key `condition_a_propositions` "
    "-- a parameter-contract name shared with every other chunker track's "
    "eval records so ../run_experiment_3.py's chunker-agnostic arm code "
    "(process_case, _score_recovered, etc.) can be reused unmodified. This "
    "is NOT Chen et al.'s Propositionizer output, which also happens to "
    "live (as leftover, unused data) in the same source log under the "
    "differently-named key `condition_a_propositions` -- see this module's "
    "own docstring for the byte-identity check that confirmed which field "
    "is which."
)


def load_govern_log(path=GOVERN_LOG):
    if not os.path.exists(path):
        raise FileNotFoundError(
            f"FATAL: {path} not found -- run "
            "own_baseline_track/run_own_baseline_experiment.py first "
            "(this Experiment 3 reuses its saved severance verdicts, it "
            "does not regenerate them)."
        )
    with open(path, encoding="utf-8") as fh:
        return [json.loads(line) for line in fh if line.strip()]


def derive_eval_set(path=GOVERN_LOG):
    """The fixed own-baseline Experiment 3 evaluation set (107 cases),
    derived programmatically and never resampled: every
    own_baseline_govern_log.jsonl record whose already-saved
    `severance_a.preserved` (THIS baseline's own Condition-A severance
    verdict, not the Propositionizer's) is False.

    Returns (eval_records, derivation_meta). Each eval record carries
    everything needed by every arm: the source paragraph (`content`), the
    Stage-1/2-elicited relation, this baseline's own Condition-A output
    under the bridging key `condition_a_propositions` (see VOCABULARY
    TRANSLATION above), and the saved severance verdict itself
    (`saved_severance_a`) for the baseline "no elicitation" arm.
    """
    records = load_govern_log(path)
    severed = [r for r in records if r["severance_a"]["preserved"] is False]

    n_condition = sum(1 for r in severed if r["relation_type"] == "Condition")
    n_concession = sum(1 for r in severed if r["relation_type"] == "Concession")
    if n_condition != EXPECTED_N_CONDITION_SEVERED or n_concession != EXPECTED_N_CONCESSION_SEVERED:
        raise AssertionError(
            f"FATAL: expected {EXPECTED_N_CONDITION_SEVERED} Condition + "
            f"{EXPECTED_N_CONCESSION_SEVERED} Concession severed-under-A cases "
            f"(per results/own_baseline_experiment_1_2_report.json's numbers), "
            f"found {n_condition} + {n_concession} in {path} -- source "
            "govern_log changed since the Experiment 1/2 run finished?"
        )
    if len(severed) != EXPECTED_N_TOTAL:
        raise AssertionError(
            f"FATAL: expected {EXPECTED_N_TOTAL} total severed-under-A cases, "
            f"found {len(severed)} in {path}."
        )

    eval_records = []
    for r in sorted(severed, key=lambda rec: rec["pool_index"]):
        eval_records.append({
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
            # Bridging key -- this baseline's OWN condition_a_claims, see
            # VOCABULARY TRANSLATION above. NOT the leftover Propositionizer
            # field of the (confusingly) same name in the source log.
            "condition_a_propositions": r["condition_a_claims"],
            "saved_severance_a": r["severance_a"],
        })

    derivation_meta = {
        "source_log": path,
        "chunker": "own_minimal_prompted_baseline",
        "n_govern_log_records": len(records),
        "n_severed_under_condition_a": len(severed),
        "n_condition_severed": n_condition,
        "n_concession_severed": n_concession,
        "vocabulary_note": VOCABULARY_NOTE,
        "bundling_audit_note": BUNDLING_AUDIT_NOTE,
        "derivation_note": (
            "Fixed evaluation set, derived programmatically, never resampled: "
            "every own_baseline_track/logs/own_baseline_govern_log.jsonl "
            "record whose already-saved severance_a.preserved (this "
            "baseline's OWN Condition-A judge verdict) is False. severance_a "
            "verdicts are reused byte-for-byte from "
            "run_own_baseline_experiment.py's run, not recomputed."
        ),
    }
    return eval_records, derivation_meta
