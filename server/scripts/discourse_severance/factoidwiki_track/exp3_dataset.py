"""Task 8 (Experiment 3, repair reliability): fixed 109-case evaluation-set
derivation for FactoidWiki's Experiment 3, mirroring
../exp3_recovery_comparison/run_exp3.py's `derive_eval_set` design
(programmatic derivation from an already-saved report, asserted counts,
never resampled) but sourced from THIS track's own artifacts.

The eval set is EVERY governing (Condition/Concession) paragraph that
Experiment 1/2 already scored severed=True under Condition A (the real
Chen et al. Propositionizer output) -- read directly from
`logs/task7_experiment_govern_log.jsonl` (272 records: 75 Condition + 197
Concession). Per README.md's Task 7 section and
`results/task7_experiment_1_2_report.json`'s `experiment_1.by_relation_type`:
13/75 Condition + 96/197 Concession were scored severed under Condition A =
109 total. Severance verdicts (`severance_a`) are REUSED byte-for-byte from
that log -- this module never re-runs or recomputes severance, only
filters/reads what Task 7 already scored.
"""

import json
import os

from env_utils import LOGS_DIR

GOVERN_LOG = os.path.join(LOGS_DIR, "task7_experiment_govern_log.jsonl")

# Documented in README.md's Task 7 section / results/task7_experiment_1_2_report.json
# ("by_relation_type" -> "severed_a"). Asserted, not assumed -- a mismatch means the
# upstream log changed and this eval set must not be silently built from different data.
EXPECTED_N_CONDITION_SEVERED = 13
EXPECTED_N_CONCESSION_SEVERED = 96
EXPECTED_N_TOTAL = 109


def load_govern_log(path=GOVERN_LOG):
    if not os.path.exists(path):
        raise FileNotFoundError(
            f"FATAL: {path} not found -- run run_experiment_1_2.py first "
            "(Experiment 3 reuses its saved severance verdicts, it does not "
            "regenerate them)."
        )
    with open(path, encoding="utf-8") as fh:
        return [json.loads(line) for line in fh if line.strip()]


def derive_eval_set(path=GOVERN_LOG):
    """The fixed Experiment 3 evaluation set (109 cases), derived
    programmatically and never resampled: every govern_log record whose
    already-saved `severance_a.preserved` is False.

    Returns (eval_records, derivation_meta). Each eval record carries
    everything needed by every arm: the source paragraph (`content`), the
    Stage-1/2-elicited relation, Condition-A's real Propositionizer output
    (`condition_a_propositions`), and the saved severance verdict itself
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
            f"(per README.md's Task 7 numbers), found {n_condition} + {n_concession} "
            f"in {path} -- source govern_log changed since Task 7 finished?"
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
            "condition_a_propositions": r["condition_a_propositions"],
            "saved_severance_a": r["severance_a"],
        })

    derivation_meta = {
        "source_log": path,
        "n_govern_log_records": len(records),
        "n_severed_under_condition_a": len(severed),
        "n_condition_severed": n_condition,
        "n_concession_severed": n_concession,
        "derivation_note": (
            "Fixed evaluation set, derived programmatically, never resampled: "
            "every logs/task7_experiment_govern_log.jsonl record whose already-"
            "saved severance_a.preserved is False. severance_a verdicts are "
            "reused byte-for-byte from Experiment 1/2's run, not recomputed."
        ),
    }
    return eval_records, derivation_meta
