"""Study config + pipeline-output loading and validation.

The config file format is documented in README.md alongside this module.
All validation errors raise ConfigError (a ValueError subclass) with a
message specific enough to fix the config without reading this code.

This module reads risk_tier / risk_flags off the pipeline's axiom records
verbatim -- no triage logic is ever computed here. The same applies to the
second corpus-sourcing path added alongside this comment:
arm_6_flagged_deferral in the FactoidWiki exp3 report is the shipped
risk_triage.py classifier's output, already computed once per record
against arm_1_no_elicitation's (pre-repair) propositions, and is read here
verbatim too -- and each repair arm's own judge.preserved verdict (see
EXP3_REPAIR_ARMS) is an already-computed ground truth from the
discourse-severance research, never recomputed here either.
"""

import json
import os

from .paths import default_config_path, document_data_path

# A single general-population cohort: FactoidWiki (general-domain Wikipedia
# paragraphs) has no natural population split the way the CFR-track's two
# CFR parts (clinical labeling text, OSHA safety text) had. Kept as a tuple
# of cohort names -- rather than hardcoding a bare string everywhere -- so
# a config still names its cohort explicitly and the field itself stays
# generic; adding a further cohort later is a matter of sourcing it from
# its own document/exp3-report entry in the study config, not a schema
# change here.
COHORTS = ("general",)
CONDITIONS = ("blind", "triaged", "opaque")
QUERY_CLASSIFICATIONS = ("clean", "compromised")

# exp3-sourced cohorts have no pipeline document_id (there is no per-cohort
# pipeline output file, just this one shared FactoidWiki exp3 report) --
# a stable stand-in so the export record's "document_id" field still means
# something. Unlike the CFR-track report, task8_factoidwiki_exp3_report.json
# has no per-record field that would split its records across more than one
# cohort (no CFR-style "part_label"; confirmed by reading the file) -- every
# record in it belongs to the single cohort below.
EXP3_DOCUMENT_IDS = {"general": "factoidwiki"}

# The three Experiment-3 arms that actually attempt automated repair of a
# severed discourse relation, pooled as this study's exp3-sourced item
# source. NOT arm_1_no_elicitation (raw, unrepaired, severed propositions --
# nobody deploys that; a real system either repairs or defers, so showing
# participants the pre-repair scaffolding was the wrong material for the
# study's real question: does risk-flagging + human deferral catch
# *automated repair* producing fluent-but-wrong output?). NOT
# arm_6_flagged_deferral (that's flagged deferral, not a repair attempt).
# NOT arm_5_parent_segment -- the CFR-track exp3_report.json's own
# summary/extension.numbering_key.calibration_field_scope established this
# same 3-arm scope as the arms that "can be wrong in a way that matters"
# (excluding the flagged-deferral arm as "a different kind of arm" and the
# parent-segment arm as a "ceiling/reality-check arm, not a competitive
# recovery arm"/one that "doesn't fail in the same sense"); this task reuses
# that established scope against the FactoidWiki report's own task-level arm
# numbering (arm_2/arm_3/arm_4 -- confirmed by reading the file; NOT the CFR
# file's condition_2/condition_3/condition_5 convention) rather than
# inventing a new one.
EXP3_REPAIR_ARMS = {
    "disco_rag": {
        "per_case_key": "arm_2_disco_rag",
        "label": "Disco-RAG (adapted)",
    },
    "custom_fallback": {
        "per_case_key": "arm_3_custom_fallback",
        "label": "Custom fallback rewriter",
    },
    "contextual_retrieval": {
        "per_case_key": "arm_4_contextual_retrieval",
        "label": "Contextual Retrieval (context injection)",
    },
}

# The only failure_type.category value the underlying research methodology
# has ever produced for these 3 arms in the checked-in FactoidWiki data
# (confirmed: every non-null failure_type.category across all 3 arms x 109
# records reads exactly this). load_exp3_cases raises ConfigError rather
# than silently mapping an unrecognized category onto "dangerous_failure" if
# a finer-grained failure taxonomy ever shows up here.
EXP3_KNOWN_FAILURE_CATEGORY = "dangerous_failure"

# Ground-truth vocabulary for exp3-sourced batch items. Deliberately
# distinct from the pipeline path's "seeded_error"/"clean" (see
# load_ground_truth) rather than overloading that vocabulary: exp3 items
# have no seeded/injected error, and the underlying judgment -- did this
# repair arm's automated recovery preserve the discourse relation (a
# Condition/Concession) that claim-splitting severed, or did it produce a
# fluent-but-wrong repair -- is a different kind of verdict than "did the
# pipeline seed an error into this claim".
EXP3_GROUND_TRUTH_LABELS = ("correct", "dangerous_failure")


class ConfigError(ValueError):
    pass


def _read_json(path: str, what: str):
    if not os.path.isfile(path):
        raise ConfigError(f"{what} not found: {path}")
    try:
        with open(path, "r") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        raise ConfigError(f"{what} is not readable JSON ({path}): {e}")


def _validate_query(q, i, cohort):
    where = f"cohorts.{cohort}.queries[{i}]"
    if not isinstance(q, dict):
        raise ConfigError(f"{where} must be an object")
    for key in ("query_id", "query", "classification", "answer",
                "source_claim_indices"):
        if key not in q:
            raise ConfigError(f"{where} missing required key '{key}'")
    if q["classification"] not in QUERY_CLASSIFICATIONS:
        raise ConfigError(
            f"{where}.classification must be one of {QUERY_CLASSIFICATIONS}, "
            f"got {q['classification']!r}"
        )
    srcs = q["source_claim_indices"]
    if (not isinstance(srcs, list) or not srcs
            or not all(isinstance(c, int) and not isinstance(c, bool)
                       for c in srcs)):
        raise ConfigError(
            f"{where}.source_claim_indices must be a non-empty list of ints"
        )
    if q["classification"] == "compromised":
        weak = q.get("weak_source_claim_index")
        if not isinstance(weak, int) or isinstance(weak, bool):
            raise ConfigError(
                f"{where} is 'compromised' and must set an integer "
                "'weak_source_claim_index'"
            )
        if weak not in srcs:
            raise ConfigError(
                f"{where}.weak_source_claim_index ({weak}) must be one of "
                f"its source_claim_indices"
            )


def _normalize_documents(cohort_cfg, cohort, config_dir):
    """Accept either shorthand (document_id + ground_truth_file at the
    cohort level) or a 'documents' list; return a list of
    {document_id, ground_truth_file} with paths resolved."""
    if "documents" in cohort_cfg:
        docs = cohort_cfg["documents"]
        if not isinstance(docs, list) or not docs:
            raise ConfigError(
                f"cohorts.{cohort}.documents must be a non-empty list"
            )
    elif "document_id" in cohort_cfg:
        docs = [{
            "document_id": cohort_cfg["document_id"],
            "ground_truth_file": cohort_cfg.get("ground_truth_file"),
        }]
    else:
        raise ConfigError(
            f"cohorts.{cohort} must define 'document_id' (with "
            "'ground_truth_file') or a 'documents' list"
        )

    out = []
    for j, d in enumerate(docs):
        if not isinstance(d, dict) or not d.get("document_id"):
            raise ConfigError(
                f"cohorts.{cohort}.documents[{j}] must set 'document_id'"
            )
        gt = d.get("ground_truth_file")
        if not isinstance(gt, str) or not gt:
            raise ConfigError(
                f"cohorts.{cohort}.documents[{j}] must set "
                "'ground_truth_file' (path to seeded-error JSON)"
            )
        if not os.path.isabs(gt):
            gt = os.path.abspath(os.path.join(config_dir, gt))
        out.append({"document_id": str(d["document_id"]),
                    "ground_truth_file": gt})
    return out


def load_study_config(path=None) -> dict:
    """Load + validate the study config. Returns
    {"cohorts": {name: {"source_type": "pipeline", "documents": [...],
    "queries": [...]}}} for the original path, or {"source_type": "exp3",
    "exp3_report_file": <resolved path>, "queries": [...]} for a cohort
    sourced from exp3_report.json (see README.md for both shapes)."""
    path = path or default_config_path()
    raw = _read_json(path, "study config")
    if not isinstance(raw, dict) or not isinstance(raw.get("cohorts"), dict):
        raise ConfigError(f"study config must be an object with a 'cohorts' "
                          f"object ({path})")
    config_dir = os.path.dirname(os.path.abspath(path))
    cohorts = {}
    for cohort, cohort_cfg in raw["cohorts"].items():
        if cohort not in COHORTS:
            raise ConfigError(
                f"unknown cohort {cohort!r}; expected one of {COHORTS}"
            )
        if not isinstance(cohort_cfg, dict):
            raise ConfigError(f"cohorts.{cohort} must be an object")
        queries = cohort_cfg.get("queries", [])
        if not isinstance(queries, list):
            raise ConfigError(f"cohorts.{cohort}.queries must be a list")
        seen_qids = set()
        for i, q in enumerate(queries):
            _validate_query(q, i, cohort)
            qid = str(q["query_id"])
            if qid in seen_qids:
                raise ConfigError(
                    f"cohorts.{cohort} has duplicate query_id {qid!r}"
                )
            seen_qids.add(qid)

        has_exp3 = "exp3_report_file" in cohort_cfg
        has_pipeline = "document_id" in cohort_cfg or "documents" in cohort_cfg
        if has_exp3 and has_pipeline:
            raise ConfigError(
                f"cohorts.{cohort} sets both 'exp3_report_file' and a "
                "pipeline document source ('document_id'/'documents') -- "
                "pick one corpus-sourcing path"
            )
        if has_exp3:
            if queries:
                raise ConfigError(
                    f"cohorts.{cohort} is sourced from 'exp3_report_file' "
                    "and cannot also define 'queries' (not supported for "
                    "this corpus-sourcing path)"
                )
            exp3_path = cohort_cfg["exp3_report_file"]
            if not isinstance(exp3_path, str) or not exp3_path:
                raise ConfigError(
                    f"cohorts.{cohort}.exp3_report_file must be a "
                    "non-empty string path"
                )
            if not os.path.isabs(exp3_path):
                exp3_path = os.path.abspath(
                    os.path.join(config_dir, exp3_path))
            cohorts[cohort] = {
                "source_type": "exp3",
                "exp3_report_file": exp3_path,
                "queries": queries,
            }
        else:
            cohorts[cohort] = {
                "source_type": "pipeline",
                "documents": _normalize_documents(cohort_cfg, cohort,
                                                  config_dir),
                "queries": queries,
            }
    if not cohorts:
        raise ConfigError(f"study config defines no cohorts ({path})")
    return {"cohorts": cohorts}


def load_ground_truth(path: str) -> set:
    """Seeded-error claim indices. Accepts either
    {"seeded_error_claim_indices": [..]} or a bare list of ints."""
    raw = _read_json(path, "ground-truth file")
    if isinstance(raw, dict):
        raw = raw.get("seeded_error_claim_indices")
    if (not isinstance(raw, list)
            or not all(isinstance(c, int) and not isinstance(c, bool)
                       for c in raw)):
        raise ConfigError(
            f"ground-truth file must be a list of ints or "
            f'{{"seeded_error_claim_indices": [...]}} ({path})'
        )
    return set(raw)


def load_document_axioms(document_id: str) -> list:
    """Read the pipeline's final data for a document and return its axiom
    records untouched (risk_tier/risk_flags come straight from the
    pipeline). Every axiom must carry an integer claim_index."""
    path = document_data_path(document_id)
    raw = _read_json(path, f"pipeline output for document '{document_id}'")
    axioms = raw.get("axioms") if isinstance(raw, dict) else None
    if not isinstance(axioms, list) or not axioms:
        raise ConfigError(
            f"pipeline output for '{document_id}' has no 'axioms' ({path})"
        )
    for i, ax in enumerate(axioms):
        ci = ax.get("claim_index") if isinstance(ax, dict) else None
        if not isinstance(ci, int) or isinstance(ci, bool):
            raise ConfigError(
                f"axioms[{i}] in pipeline output for '{document_id}' lacks "
                f"an integer 'claim_index' -- regenerate with the current "
                f"pipeline ({path})"
            )
    return axioms


def _exp3_record_level_flags(r: dict, rid: str, path: str) -> list:
    """arm_6_flagged_deferral is computed once per RECORD (against
    arm_1_no_elicitation's pre-repair propositions + the original source
    paragraph), not per repair arm -- it represents what the shipped
    pipeline would have flagged BEFORE any repair was attempted, which is
    the actual point of the comparison. Flatten every
    per_proposition_flags[*] entry's flags into one case-level list, deduped
    by (type, reason) so a flag that fired on more than one pre-repair
    proposition isn't double-counted, preserving first-seen order. Every
    repair arm's case for this record shares this exact list.

    per_proposition_flags may legitimately be an empty list (none observed
    in the checked-in FactoidWiki data, but the CFR-track report had an
    analogous zero-proposition record, so this is still handled explicitly
    rather than assumed away) -- that just means the record-level flags
    list is empty, not malformed."""
    c4 = r.get("arm_6_flagged_deferral")
    per_prop = c4.get("per_proposition_flags") if isinstance(c4, dict) else None
    if not isinstance(per_prop, list):
        raise ConfigError(
            f"exp3 report record {rid!r} lacks a list "
            f"arm_6_flagged_deferral.per_proposition_flags ({path})"
        )
    flags = []
    seen = set()
    for j, pc in enumerate(per_prop):
        if (not isinstance(pc, dict) or not isinstance(pc.get("proposition"), str)
                or not isinstance(pc.get("flags"), list)):
            raise ConfigError(
                f"exp3 report record {rid!r} arm_6_flagged_deferral."
                f"per_proposition_flags[{j}] must be "
                f"{{'proposition': str, 'flags': [...]}} ({path})"
            )
        for k, fl in enumerate(pc["flags"]):
            if (not isinstance(fl, dict) or not isinstance(fl.get("type"), str)
                    or not isinstance(fl.get("reason"), str)):
                raise ConfigError(
                    f"exp3 report record {rid!r} arm_6_flagged_deferral."
                    f"per_proposition_flags[{j}].flags[{k}] must be "
                    f"{{'type': str, 'reason': str}} ({path})"
                )
            key = (fl["type"], fl["reason"])
            if key not in seen:
                seen.add(key)
                flags.append(fl)
    return flags


def load_exp3_cases(path: str, cohort: str) -> list:
    """Read task8_factoidwiki_exp3_report.json and return this cohort's
    (record, repair arm) cases, reshaped for session creation. Read-only
    reuse of already-computed research output -- this function never
    (re)computes a correct/dangerous_failure verdict and never (re)computes
    a risk flag; it only reads and validates. See EXP3_REPAIR_ARMS for which
    3 arms are pooled and why.

    Unlike the CFR-track exp3_report.json, this report has no per-record
    field splitting its records across more than one cohort (no
    CFR-style "part_label") -- every record belongs to the single cohort in
    COHORTS, so `cohort` is only used to build the stand-in document_id
    (EXP3_DOCUMENT_IDS) and error messages, not to filter records.

    One entry per (record, arm) pair -- a "case" -- for every arm in
    EXP3_REPAIR_ARMS that has usable output for that record (a repair arm
    with its 'error' field set, or an empty 'propositions' list, contributes
    no case for that record rather than crashing or fabricating one; not
    observed in the checked-in data, but handled explicitly since a repair
    attempt failing outright is a real possibility this corpus doesn't
    currently exercise).

    Each returned dict:
        {
          "record_id": str,             # "<EXP3_DOCUMENT_IDS[cohort]>:<pool_index>"
          "arm": str,                   # short key into EXP3_REPAIR_ARMS
          "pool_index": int,            # this record's index into the source govern log
          "claims": [str, ...],         # this arm's own <per_case_key>.propositions
          "flags": [{type,reason}, ...],  # record-level, arm-independent --
                                           # see _exp3_record_level_flags
          "ground_truth_label": "correct" | "dangerous_failure",
        }

    "ground_truth_label" is this arm's own already-computed
    <per_case_key>.bucket, read verbatim after two checks: it must be one of
    EXP3_GROUND_TRUTH_LABELS (any other bucket -- e.g. "detectable_failure"
    or "unscored", both defined by the report's bucket vocabulary but never
    produced for these 3 arms in the checked-in data -- raises ConfigError
    rather than silently displaying an unsupported label), and it must agree
    with that arm's own <per_case_key>.judge.preserved bool (preserved=True
    iff bucket=="correct"; a disagreement between the report's own two
    already-computed fields is a data integrity problem worth surfacing
    immediately, not silently resolving). When bucket=="dangerous_failure",
    <per_case_key>.failure_type.category must also equal
    EXP3_KNOWN_FAILURE_CATEGORY -- any other category raises ConfigError
    rather than silently folding an unrecognized failure mode into
    "dangerous_failure".

    Cases are returned sorted by (pool_index, record_id, arm order in
    EXP3_REPAIR_ARMS) for a deterministic base order -- callers apply their
    own condition-specific ordering (see sessions.py) on top of this.
    """
    raw = _read_json(path, "exp3 report")
    records = raw.get("records") if isinstance(raw, dict) else None
    if not isinstance(records, list) or not records:
        raise ConfigError(f"exp3 report has no 'records' ({path})")

    if cohort not in EXP3_DOCUMENT_IDS:
        raise ConfigError(
            f"cohort {cohort!r} has no stand-in document_id in "
            f"EXP3_DOCUMENT_IDS ({sorted(EXP3_DOCUMENT_IDS)})"
        )
    doc_id = EXP3_DOCUMENT_IDS[cohort]
    arm_rank = {key: idx for idx, key in enumerate(EXP3_REPAIR_ARMS)}

    out = []
    for i, r in enumerate(records):
        if not isinstance(r, dict):
            raise ConfigError(f"exp3 report records[{i}] must be an object ({path})")

        pool_index = r.get("pool_index")
        if not isinstance(pool_index, int) or isinstance(pool_index, bool):
            raise ConfigError(
                f"exp3 report records[{i}] lacks an integer 'pool_index' ({path})"
            )
        rid = f"{doc_id}:{pool_index}"

        case_flags = _exp3_record_level_flags(r, rid, path)

        for arm_key, arm_spec in EXP3_REPAIR_ARMS.items():
            per_case_key = arm_spec["per_case_key"]
            arm_data = r.get(per_case_key)
            if not isinstance(arm_data, dict):
                raise ConfigError(
                    f"exp3 report record {rid!r} lacks {per_case_key!r} "
                    f"({path})"
                )

            # Explicitly-anticipated edge case, not currently present in the
            # checked-in data (confirmed: zero 'error' set, zero empty
            # 'propositions' across all 3 arms x 109 records) -- a repair
            # arm that failed outright for this record has nothing for a
            # participant to review, so skip just this (record, arm) case
            # rather than fabricating an empty item or crashing the whole
            # cohort build.
            if arm_data.get("error"):
                continue
            propositions = arm_data.get("propositions")
            if not isinstance(propositions, list) or not propositions:
                continue
            if not all(isinstance(c, str) for c in propositions):
                raise ConfigError(
                    f"exp3 report record {rid!r} {per_case_key}.propositions "
                    f"must all be strings ({path})"
                )

            judge = arm_data.get("judge")
            if not isinstance(judge, dict) or not isinstance(judge.get("preserved"), bool):
                raise ConfigError(
                    f"exp3 report record {rid!r} lacks a boolean "
                    f"{per_case_key}.judge.preserved ({path})"
                )

            ground_truth_label = arm_data.get("bucket")
            if ground_truth_label not in EXP3_GROUND_TRUTH_LABELS:
                raise ConfigError(
                    f"exp3 report record {rid!r} {per_case_key}.bucket is "
                    f"{ground_truth_label!r}, expected one of "
                    f"{EXP3_GROUND_TRUTH_LABELS} -- this study's ground-truth "
                    "vocabulary (EXP3_GROUND_TRUTH_LABELS) doesn't know how "
                    "to display any other bucket; a new bucket needs an "
                    f"explicit decision, not a silent fold ({path})"
                )
            expected_label = "correct" if judge["preserved"] else "dangerous_failure"
            if ground_truth_label != expected_label:
                raise ConfigError(
                    f"exp3 report record {rid!r} {per_case_key} has "
                    f"judge.preserved={judge['preserved']} but bucket "
                    f"{ground_truth_label!r} (expected {expected_label!r}) -- "
                    f"these two already-computed fields disagree ({path})"
                )

            if ground_truth_label == "dangerous_failure":
                failure_type = arm_data.get("failure_type")
                category = (failure_type.get("category")
                           if isinstance(failure_type, dict) else None)
                if category != EXP3_KNOWN_FAILURE_CATEGORY:
                    raise ConfigError(
                        f"exp3 report record {rid!r} {per_case_key} has "
                        f"bucket='dangerous_failure' with failure_type."
                        f"category {category!r}, expected "
                        f"{EXP3_KNOWN_FAILURE_CATEGORY!r} ({path})"
                    )

            out.append({
                "record_id": rid,
                "arm": arm_key,
                "pool_index": pool_index,
                "claims": propositions,
                "flags": case_flags,
                "ground_truth_label": ground_truth_label,
            })

    if not out:
        raise ConfigError(
            f"exp3 report ({path}) has no usable (record, repair-arm) cases "
            f"for cohort {cohort!r} (expected at least one of "
            f"{list(EXP3_REPAIR_ARMS)} with non-empty propositions and no "
            "'error' per record)"
        )
    out.sort(key=lambda d: (d["pool_index"], d["record_id"],
                            arm_rank[d["arm"]]))
    return out
