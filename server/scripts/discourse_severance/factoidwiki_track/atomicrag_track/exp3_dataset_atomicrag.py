"""AtomicRAG-track analog of ../exp3_dataset.py: fixed evaluation-set
derivation for AtomicRAG's own Experiment 3 (repair-arm reliability),
sourced from THIS track's own already-scored governing-relation log
(logs/atomicrag_govern_log.jsonl, 272 records: 75 Condition + 197
Concession, written by run_atomicrag_experiment.py) instead of the
Propositionizer track's ../logs/task7_experiment_govern_log.jsonl.

The eval set is EVERY governing (Condition/Concession) paragraph that
run_atomicrag_experiment.py already scored severed=True under AtomicRAG's
standard atomization. There is no Condition A/B split for this chunker --
AtomicRAG's OpenIE prompts have no relation-hint input slot (see
atomicrag_openie_adapter.py's "CONDITION B ... IS NOT POSSIBLE FOR THIS
CHUNKER" section) -- so "no elicitation" here just means "AtomicRAG's own
OpenIE output, unmodified", the direct analog of the Propositionizer
track's Condition A used by ../exp3_dataset.py. Per
results/atomicrag_experiment_1_2_report.json's `experiment_1.by_relation_type`:
29/75 Condition + 95/197 Concession were scored severed = 124 total.
`severance_atomicrag` verdicts are REUSED byte-for-byte from that
already-completed run -- this module never re-runs or recomputes
severance, only filters/reads what run_atomicrag_experiment.py already
scored (mirrors ../exp3_dataset.py's "reads directly, never recomputes"
design exactly).

EVAL-SET CONVENTION -- ORIGINAL (bundling-audit-UNCORRECTED) severed set
is used here, NOT the audit-corrected one, matching ../exp3_dataset.py's
own established precedent. This was checked, not assumed:
../exp3_dataset.py's 109-case Propositionizer eval set is built directly
from ../logs/task7_experiment_govern_log.jsonl's raw `severance_a.preserved`
field, asserted against the ORIGINAL primary report's counts
(../results/task7_experiment_1_2_report.json's by_relation_type,
13+96=109) -- with no reference anywhere in ../exp3_dataset.py or
../run_experiment_3.py to a bundling correction. Cross-checking file
provenance confirms why: ../run_experiment_3.py's own report
(../results/task8_factoidwiki_exp3_report.json) is dated 2026-08-12, TWO
DAYS BEFORE ../results/task7_nucleus_bundling_audit.json (dated
2026-08-14) was even produced -- so ../exp3_dataset.py's derivation could
not have incorporated that audit's correction even in principle, and
never has since (the audit script's own note is explicit that its
adjusted figures are "a sub-clause-scoped alternative reading reported
alongside" the primary numbers, "not a replacement" -- by design, not
merely by accident of timing). This module follows that exact,
established precedent: the 124-case eval set below is the ORIGINAL,
bundling-audit-UNCORRECTED severed set, not a smaller/adjusted one.

For completeness (documented, not hidden): the AtomicRAG-track's own
equivalent audit (results/atomicrag_nucleus_bundling_audit.json, same
audit date 2026-08-14) found that 5 of these 124 pool_indices (1936,
3263, 3360, 4707, 4920) would flip from severed to preserved under its
sub-clause-scoped judge -- see that file / README.md's "Exclusion list
for a future evaluation set" section. Consistent with the
Propositionizer-track precedent above, those 5 records are NOT excluded
from this Experiment 3 eval set; BUNDLING_AUDIT_FLIP_TO_PRESERVED_POOL_INDICES
below is carried only for documentation / a possible future adjusted
re-run, unapplied here.
"""

import json
import os

ATOMICRAG_TRACK_DIR = os.path.dirname(os.path.abspath(__file__))
GOVERN_LOG = os.path.join(ATOMICRAG_TRACK_DIR, "logs", "atomicrag_govern_log.jsonl")

# Documented in atomicrag_track/README.md / results/atomicrag_experiment_1_2_report.json
# ("by_relation_type" -> "severed_atomicrag"). Asserted, not assumed -- a mismatch means
# the upstream log changed and this eval set must not be silently built from different data.
EXPECTED_N_CONDITION_SEVERED = 29
EXPECTED_N_CONCESSION_SEVERED = 95
EXPECTED_N_TOTAL = 124

# Documentation only, NOT applied to eval-set derivation below -- see module
# docstring's EVAL-SET CONVENTION section. Source:
# results/atomicrag_nucleus_bundling_audit.json / README.md's
# "Exclusion list for a future evaluation set".
BUNDLING_AUDIT_FLIP_TO_PRESERVED_POOL_INDICES = [1936, 3263, 3360, 4707, 4920]


def load_govern_log(path=GOVERN_LOG):
    if not os.path.exists(path):
        raise FileNotFoundError(
            f"FATAL: {path} not found -- run run_atomicrag_experiment.py first "
            "(this Experiment 3 reuses its saved severance_atomicrag verdicts, "
            "it does not regenerate them)."
        )
    with open(path, encoding="utf-8") as fh:
        return [json.loads(line) for line in fh if line.strip()]


def derive_eval_set(path=GOVERN_LOG):
    """The fixed AtomicRAG-track Experiment 3 evaluation set (124 cases),
    derived programmatically and never resampled: every
    logs/atomicrag_govern_log.jsonl record whose already-saved
    `severance_atomicrag.preserved` is False.

    Returns (eval_records, derivation_meta). Each eval record carries
    everything needed by every arm: the source paragraph (`content`), the
    Stage-1/2-elicited relation (verbatim-copied from the same source
    govern log every chunker's own log derives from), AtomicRAG's real
    OpenIE knowledge-fragment output (`atomicrag_propositions`), and the
    saved severance verdict itself (`saved_severance_atomicrag`) for the
    baseline "no elicitation" arm.
    """
    records = load_govern_log(path)
    severed = [r for r in records if r["severance_atomicrag"]["preserved"] is False]

    n_condition = sum(1 for r in severed if r["relation_type"] == "Condition")
    n_concession = sum(1 for r in severed if r["relation_type"] == "Concession")
    if n_condition != EXPECTED_N_CONDITION_SEVERED or n_concession != EXPECTED_N_CONCESSION_SEVERED:
        raise AssertionError(
            f"FATAL: expected {EXPECTED_N_CONDITION_SEVERED} Condition + "
            f"{EXPECTED_N_CONCESSION_SEVERED} Concession severed-under-AtomicRAG cases "
            f"(per README.md / results/atomicrag_experiment_1_2_report.json), found "
            f"{n_condition} + {n_concession} in {path} -- source govern_log changed "
            "since run_atomicrag_experiment.py finished?"
        )
    if len(severed) != EXPECTED_N_TOTAL:
        raise AssertionError(
            f"FATAL: expected {EXPECTED_N_TOTAL} total severed-under-AtomicRAG cases, "
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
            "atomicrag_propositions": r["atomicrag_propositions"],
            "saved_severance_atomicrag": r["severance_atomicrag"],
        })

    derivation_meta = {
        "source_log": path,
        "n_govern_log_records": len(records),
        "n_severed_under_atomicrag": len(severed),
        "n_condition_severed": n_condition,
        "n_concession_severed": n_concession,
        "bundling_audit_correction_applied": False,
        "bundling_audit_note": (
            "Matches ../exp3_dataset.py's established precedent (see module "
            "docstring): the ORIGINAL, bundling-audit-UNCORRECTED severed set is "
            "used, not the sub-clause-scoped adjusted reading. 5 of these 124 "
            "pool_indices (see BUNDLING_AUDIT_FLIP_TO_PRESERVED_POOL_INDICES) would "
            "flip to preserved under results/atomicrag_nucleus_bundling_audit.json's "
            "sub-clause judge; not excluded here."
        ),
        "bundling_audit_flip_to_preserved_pool_indices": BUNDLING_AUDIT_FLIP_TO_PRESERVED_POOL_INDICES,
        "derivation_note": (
            "Fixed evaluation set, derived programmatically, never resampled: "
            "every logs/atomicrag_govern_log.jsonl record whose already-saved "
            "severance_atomicrag.preserved is False. severance_atomicrag verdicts "
            "are reused byte-for-byte from run_atomicrag_experiment.py's run, not "
            "recomputed."
        ),
    }
    return eval_records, derivation_meta
