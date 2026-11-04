"""Shared helper (Task 7, full-scale run): compute the AUTHORITATIVE
Stage-2-confirmed pool_index sets for Condition and Concession, and the
available Elaboration raw-hit pool, across every log this track has
produced so far (Task 5, Task 5b, Task 6's main two-stage pipeline, and
the Concession check4-revision experiment). Used by both the full-scale
screening progress checks (Task 1) and the Experiment 1/2 sample builder
(Task 2), so the same non-obvious accounting rule below is applied
exactly once rather than re-derived (and risked getting wrong) in two
places.

WHY THIS EXISTS -- THE CONCESSION SPLIT: pool_index 1803-2802's Stage-2
verdicts in the main logs/task6_stage2_log.jsonl were computed under the
ORIGINAL check_4 wording, which mechanically rejected all 85 Concession
Stage-1.5 survivors in that range (confirmed=False for every one, by
construction -- see README.md and results/task6_two_stage_pipeline_report.json).
The validated, human-audited REVISED check_4 wording's verdicts for that
SAME range live only in the separate
logs/task6_stage2_concession_check4_revision_experiment.jsonl (57/85
confirmed there). From the full-scale run (2026-08) onward,
verification_classifier.verify_candidate's own default IS the revised
wording (see that module's docstring), so main-log Concession entries for
pool_index >= 2803 are directly produced under the SAME wording as the
revision-experiment log's pool_index <= 2802 entries -- the two sources
are methodologically comparable and safe to union by pool_index.
get_confirmed_concession() below does exactly that union, so nothing
downstream has to remember this split or risk silently using the
main log's all-zero original-wording Concession numbers instead of the
now-authoritative revised-wording ones.

Condition has no such split: check_4 is a Concession-specific failure mode
and essentially never fires for Condition candidates (2/48 triggered in
the validation batch). The task brief does not ask for Condition's
historical batch to be re-verified under the revised wording, so
get_confirmed_condition() just reads the main log directly, regardless of
which check_4 wording produced any given verdict (each record's own
"verification_prompt_version" field -- present from the full-scale run
onward, absent/None for the pre-promotion pool_index 1803-2802 records --
preserves which one, for anyone who wants to slice by it later).
"""

import json
import os

from env_utils import LOGS_DIR

STAGE1_LOG = os.path.join(LOGS_DIR, "task6_stage1_log.jsonl")
STAGE2_LOG = os.path.join(LOGS_DIR, "task6_stage2_log.jsonl")
CONCESSION_CHECK4_REVISION_LOG = os.path.join(
    LOGS_DIR, "task6_stage2_concession_check4_revision_experiment.jsonl"
)
TASK5_LOG = os.path.join(LOGS_DIR, "task5_screening_log.jsonl")
TASK5B_LOG = os.path.join(LOGS_DIR, "task5b_screening_log.jsonl")


def load_jsonl_by_pool_index(path):
    """De-dup by pool_index, keeping the LAST write -- same convention used
    everywhere else in this track (run_two_stage_pipeline._load_by_pool_index,
    spot_check_sample.load_stage2_log). Returns {} if the file doesn't exist
    yet (so callers don't need to special-case a not-yet-run stage).
    """
    if not os.path.exists(path):
        return {}
    records = []
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    by_index = {r["pool_index"]: r for r in records}
    return {k: by_index[k] for k in sorted(by_index)}


def get_confirmed_condition():
    """dict pool_index -> stage2_log record, for every Condition candidate
    the main pipeline log has ever confirmed (either check_4 wording --
    see module docstring for why Condition doesn't need the Concession
    union treatment).
    """
    stage2 = load_jsonl_by_pool_index(STAGE2_LOG)
    return {
        idx: r for idx, r in stage2.items()
        if r["relation_type"] == "Condition" and r["stage2"].get("confirmed")
    }


def get_confirmed_concession():
    """dict pool_index -> record, UNION of:
      (a) main stage2_log Concession entries with confirmed=True (in
          practice, only pool_index >= 2803, verified under the now-default
          revised check_4 wording -- pool_index 1803-2802 are all
          confirmed=False in this log, per the original-wording run), and
      (b) the check4-revision-experiment log's confirmed=True entries
          (pool_index 1803-2802, re-verified under the revised wording).

    NORMALIZED SHAPE: (b)'s source records carry their verdict under a
    "stage2_check4_revision" key (see run_check4_revision_experiment.py),
    not "stage2" -- because that experiment log predates this promotion and
    was never meant to be read as if it were a main-pipeline log. Every
    record returned by this function is re-keyed to carry a "stage2" key
    uniformly (for (b), a copy of "stage2_check4_revision", with
    "verification_prompt_version" defaulted to "check4_revision" if not
    already present -- that experiment log was written before this
    promotion added the field, but every record in it was, by construction,
    produced with the revised wording), so nothing downstream needs to know
    which of the two source files a given confirmed Concession came from.

    A conflicting pool_index (present with different confirmed values in
    both sources) would indicate something unexpected happened -- asserted
    against explicitly rather than silently preferring one source, per this
    repo's no-silent-failures convention.
    """
    stage2 = load_jsonl_by_pool_index(STAGE2_LOG)
    main_confirmed = {
        idx: r for idx, r in stage2.items()
        if r["relation_type"] == "Concession" and r["stage2"].get("confirmed")
    }

    revision_log = load_jsonl_by_pool_index(CONCESSION_CHECK4_REVISION_LOG)
    revision_confirmed_raw = {
        idx: r for idx, r in revision_log.items()
        if r.get("relation_type") == "Concession" and r["stage2_check4_revision"].get("confirmed")
    }

    overlap = set(main_confirmed) & set(revision_confirmed_raw)
    for idx in overlap:
        main_says = bool(main_confirmed[idx]["stage2"].get("confirmed"))
        revision_says = bool(revision_confirmed_raw[idx]["stage2_check4_revision"].get("confirmed"))
        if main_says != revision_says:
            raise AssertionError(
                f"FATAL: pool_index {idx} has CONFLICTING Concession confirmed verdicts "
                f"between {STAGE2_LOG} (confirmed={main_says}) and "
                f"{CONCESSION_CHECK4_REVISION_LOG} (confirmed={revision_says}) -- "
                "investigate before trusting either source."
            )

    revision_confirmed = {}
    for idx, r in revision_confirmed_raw.items():
        verdict = dict(r["stage2_check4_revision"])
        verdict.setdefault("verification_prompt_version", "check4_revision")
        revision_confirmed[idx] = {**r, "stage2": verdict}

    merged = dict(main_confirmed)
    merged.update(revision_confirmed)
    return merged


def get_elaboration_pool():
    """dict pool_index -> record, every Stage-1 Elaboration hit across all
    three screening logs this track has produced (Task 5, Task 5b, Task 6's
    Stage 1). Elaboration is not a Stage-1.5/Stage-2 candidate relation
    (see run_two_stage_pipeline.CANDIDATE_RELATION_TYPES) and never was in
    the parent discourse_severance/ track either (relation_elicitation's
    Elaboration control was likewise Condition-A/Stage-1-only) -- so
    "available Elaboration paragraphs" means Stage-1 raw hits, full stop.
    A diagnostic-only "stage1_5_would_pass" field is attached using the
    SAME free grounding check candidate_prefilter.py applies to Condition/
    Concession, so a downstream sampler can optionally prefer
    better-grounded nucleus/satellite/connective spans without spending any
    LLM calls -- purely a data-quality signal, never a hard requirement,
    since the parent track never applied this filter to its own Elaboration
    control either.
    """
    from candidate_prefilter import prefilter_candidate

    combined = {}
    for path in (TASK5_LOG, TASK5B_LOG, STAGE1_LOG):
        for idx, r in load_jsonl_by_pool_index(path).items():
            if r.get("_error") or r.get("relation_type") != "Elaboration":
                continue
            combined[idx] = r

    for idx, r in combined.items():
        verdict = prefilter_candidate(r)
        combined[idx] = {**r, "stage1_5_diagnostic": verdict}

    return combined


def summarize(target=50, comfortable_target=65):
    condition = get_confirmed_condition()
    concession = get_confirmed_concession()
    elaboration = get_elaboration_pool()
    stage1_all = load_jsonl_by_pool_index(STAGE1_LOG)
    n_fresh_screened = sum(1 for idx in stage1_all if idx >= 2803)
    return {
        "n_task6_stage1_screened_total": len(stage1_all),
        "n_fresh_screened_since_2803": n_fresh_screened,
        "confirmed_condition_n": len(condition),
        "confirmed_condition_indices": sorted(condition),
        "confirmed_concession_n": len(concession),
        "confirmed_concession_indices": sorted(concession),
        "elaboration_available_n": len(elaboration),
        "condition_meets_target": len(condition) >= target,
        "concession_meets_target": len(concession) >= target,
        "condition_meets_comfortable_target": len(condition) >= comfortable_target,
        "concession_meets_comfortable_target": len(concession) >= comfortable_target,
    }


if __name__ == "__main__":
    print(json.dumps(summarize(), indent=2))
