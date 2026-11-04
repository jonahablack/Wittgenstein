"""Tests for the exp3-report corpus-sourcing path and the `opaque`
condition (see study_harness/README.md's "exp3-sourced cohorts" section for
the format this exercises).

Item source: task8_factoidwiki_exp3_report.json's 3 pooled automated-repair
arms (config.EXP3_REPAIR_ARMS -- arm_2_disco_rag, arm_3_custom_fallback,
arm_4_contextual_retrieval), NOT the raw, unrepaired arm_1_no_elicitation
propositions. One "case" is a (record, repair arm) pair; ground truth is
"correct" / "dangerous_failure" (config.EXP3_GROUND_TRUTH_LABELS), read
verbatim from that arm's own already-computed "bucket" field (cross-checked
against judge.preserved and, for a dangerous_failure bucket,
failure_type.category).

There is a single general-population cohort (config.COHORTS == ("general",))
-- FactoidWiki has no per-record field splitting records across more than
one cohort the way the CFR-track report's part_label did, so every record
in the report belongs to it.

Uses a small synthetic task8_factoidwiki_exp3_report.json-shaped fixture
(same shape as the real server/scripts/discourse_severance/factoidwiki_track/
results/task8_factoidwiki_exp3_report.json, confirmed by reading that file)
rather than the real file, so case counts / flag placement / bucket values
are fully controlled and the assertions below don't depend on the real
research data ever changing. The fixture only includes the record/arm keys
config.py actually reads (pool_index, arm_2/3/4, arm_6_flagged_deferral) --
arm_1_no_elicitation and arm_5_parent_segment exist in the real file but are
never read by this harness (see config.EXP3_REPAIR_ARMS), so they are
omitted here rather than padding every record with unused fields.
Integration tests at the bottom exercise the real, checked-in file to
confirm this harness still parses production data (their assertions only
pin down what was independently confirmed by reading
task8_factoidwiki_exp3_report.json directly: total case/claim counts and
the ground-truth distribution).

Deliberately a separate file from test_study_harness.py -- that file's
tests are untouched, and this one never imports its fixtures, so neither
can accidentally couple to the other.
"""

import json
import os

import pytest
from flask import Flask

from study_harness import config as cfg
from study_harness.routes import study_bp

REAL_EXP3_REPORT = os.path.abspath(os.path.join(
    os.path.dirname(__file__), "..", "scripts", "discourse_severance",
    "factoidwiki_track", "results", "task8_factoidwiki_exp3_report.json"))

GENERAL_DOC_ID = "factoidwiki"  # config.EXP3_DOCUMENT_IDS["general"]


def _flags(*types):
    return [{"type": t, "reason": f"reason for {t}"} for t in types]


def _arm(propositions, preserved, failure_category="dangerous_failure",
        error=None):
    """One repair arm's per-case data (arm_2/3/4's shape, confirmed by
    reading task8_factoidwiki_exp3_report.json directly): 'propositions',
    'judge.preserved', an already-computed 'bucket' ('correct' iff
    preserved), and -- only when bucket is 'dangerous_failure' --
    'failure_type.category' (null when preserved, matching the real file)."""
    bucket = "correct" if preserved else "dangerous_failure"
    return {
        "propositions": propositions,
        "error": error,
        "judge": {"preserved": preserved, "reasoning": "..."},
        "bucket": bucket,
        "failure_type": (None if preserved
                         else {"category": failure_category, "reasoning": "..."}),
    }


def _arm6_flagged_deferral(pre_repair_propositions, flags_per_proposition):
    """arm_6_flagged_deferral's shape (confirmed by reading the real file):
    per_proposition_flags computed against arm_1_no_elicitation's own
    propositions -- deliberately independent of any repair arm's own
    proposition count, matching the real file where e.g.
    arm_4_contextual_retrieval routinely has a different proposition count
    than arm_1."""
    any_fired = any(flags_per_proposition)
    fired_types = sorted({fl["type"] for flist in flags_per_proposition
                          for fl in flist})
    return {
        "per_proposition_flags": [
            {"proposition": p, "flags": f}
            for p, f in zip(pre_repair_propositions, flags_per_proposition)
        ],
        "flag_types_fired": fired_types,
        "segment_flag_fired": False,
        "segment_flag_types": [],
        "claim_level_flag_fired": any_fired,
        "claim_level_flag_types": fired_types,
        "any_flag_fired": any_fired,
    }


def _record(pool_index, pre_repair_propositions, flags_per_proposition,
           disco_rag, custom_fallback, contextual_retrieval,
           relation_type="Concession"):
    """A task8_factoidwiki_exp3_report.json-shaped record, restricted to the
    keys config.py actually reads plus relation_type for shape-realism."""
    return {
        "pool_index": pool_index,
        "relation_type": relation_type,
        "arm_2_disco_rag": disco_rag,
        "arm_3_custom_fallback": custom_fallback,
        "arm_4_contextual_retrieval": contextual_retrieval,
        "arm_6_flagged_deferral": _arm6_flagged_deferral(
            pre_repair_propositions, flags_per_proposition),
    }


# 5 records, sorted by pool_index: 5, 10, 20, 50, 75.
#
# pool_index 5  -- no record-level flag; all 3 arms produce cases, all
#   "correct" -- a clean baseline record with no skips and no flags.
# pool_index 10 -- no record-level flag; all 3 arms produce cases, with
#   different ground truth per arm (disco_rag "correct", the other two
#   "dangerous_failure") -- exercises per-arm ground truth divergence on
#   one record.
# pool_index 20 -- HAS a record-level flag; all 3 arms produce cases, all
#   "dangerous_failure" -- exercises the flagged-first triaged sort.
# pool_index 50 -- HAS a record-level flag; its arm_4_contextual_retrieval
#   arm has 'error' set (a repair failure) -- exercises the "skip this
#   (record, arm) case" path for an outright failure.
# pool_index 75 -- no flag; its arm_2_disco_rag arm has an empty
#   'propositions' list -- exercises the other skip path (empty
#   propositions, no 'error').
RECORDS = [
    _record(5, ["preL1"], [[]],
           disco_rag=_arm(["L1", "L2"], preserved=True),
           custom_fallback=_arm(["L3"], preserved=True),
           contextual_retrieval=_arm(["L4"], preserved=True)),
    _record(10, ["pre1", "pre2"], [[], []],
           disco_rag=_arm(["D1", "D2"], preserved=True),
           custom_fallback=_arm(["C1"], preserved=False),
           contextual_retrieval=_arm(["R1", "R2", "R3"], preserved=False)),
    _record(20, ["preL2"], [_flags("cross_reference")],
           disco_rag=_arm(["L5"], preserved=False),
           custom_fallback=_arm(["L6", "L7"], preserved=False),
           contextual_retrieval=_arm(["L8"], preserved=False)),
    _record(50, ["pre3"], [_flags("segment_concession_satellite")],
           disco_rag=_arm(["D3"], preserved=True),
           custom_fallback=_arm(["C2", "C3"], preserved=True),
           contextual_retrieval=_arm([], preserved=False,
                                     error="repair failed")),
    _record(75, ["pre4"], [[]],
           disco_rag=_arm([], preserved=False),
           custom_fallback=_arm(["C4"], preserved=True),
           contextual_retrieval=_arm(["R4", "R5"], preserved=False)),
]

# Case order (pool_index, record_id, arm order disco_rag/custom_fallback/
# contextual_retrieval), skipping pool_index 50's errored
# contextual_retrieval and pool_index 75's empty-propositions disco_rag:
#   case                                       claim_index   ground_truth    flagged
#   (5,  disco_rag)          L1, L2            0, 1          correct         no
#   (5,  custom_fallback)    L3                2             correct         no
#   (5,  contextual_retr.)   L4                3             correct         no
#   (10, disco_rag)          D1, D2            4, 5          correct         no
#   (10, custom_fallback)    C1                6             dangerous_fail  no
#   (10, contextual_retr.)   R1, R2, R3        7, 8, 9        dangerous_fail  no
#   (20, disco_rag)          L5                10            dangerous_fail  YES
#   (20, custom_fallback)    L6, L7            11, 12        dangerous_fail  YES
#   (20, contextual_retr.)   L8                13            dangerous_fail  YES
#   (50, disco_rag)          D3                14            correct         YES
#   (50, custom_fallback)    C2, C3            15, 16        correct         YES
#   (75, custom_fallback)    C4                17            correct         no
#   (75, contextual_retr.)   R4, R5            18, 19        dangerous_fail  no
CLAIM_COUNT = 20
OPAQUE_COUNT = 13
FLAGGED_CLAIM_INDICES = [10, 11, 12, 13, 14, 15, 16]
UNFLAGGED_CLAIM_INDICES = [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 17, 18, 19]
TRIAGED_ORDER = FLAGGED_CLAIM_INDICES + UNFLAGGED_CLAIM_INDICES
GROUND_TRUTH_BY_CLAIM = {
    0: "correct", 1: "correct",
    2: "correct",
    3: "correct",
    4: "correct", 5: "correct",
    6: "dangerous_failure",
    7: "dangerous_failure", 8: "dangerous_failure", 9: "dangerous_failure",
    10: "dangerous_failure",
    11: "dangerous_failure", 12: "dangerous_failure",
    13: "dangerous_failure",
    14: "correct",
    15: "correct", 16: "correct",
    17: "correct",
    18: "dangerous_failure", 19: "dangerous_failure",
}


@pytest.fixture
def exp3_env(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))

    exp3_report = {
        "run_date": "2026-08-12",
        "experiment": "task8_factoidwiki_exp3_repair_reliability",
        "records": RECORDS,
    }
    exp3_path = tmp_path / "exp3_report.json"
    exp3_path.write_text(json.dumps(exp3_report))

    config = {
        "cohorts": {
            "general": {"exp3_report_file": str(exp3_path)},
        }
    }
    config_path = tmp_path / "study_config.json"
    config_path.write_text(json.dumps(config))
    monkeypatch.setenv("STUDY_CONFIG", str(config_path))
    return tmp_path


@pytest.fixture
def client(exp3_env):
    app = Flask(__name__)
    app.config["TESTING"] = True
    app.register_blueprint(study_bp)
    return app.test_client()


def _create(client, participant_id="P01", cohort="general",
           condition="blind", **extra):
    resp = client.post("/study/admin/sessions", json={
        "participant_id": participant_id,
        "cohort": cohort,
        "condition": condition,
        **extra,
    })
    return resp


def _decide(client, sid, item_id, decision="approved", confidence=3, **extra):
    return client.post(f"/study/sessions/{sid}/decisions", json={
        "item_id": item_id,
        "decision": decision,
        "confidence": confidence,
        **extra,
    })


def _find_key(obj, key):
    """Recursively search a decoded JSON structure for a dict key, for
    asserting a server-internal-only field never reaches a participant
    response (a raw-substring check isn't reliable since 'arm' could
    appear as a JSON value or inside another word)."""
    if isinstance(obj, dict):
        if key in obj:
            return True
        return any(_find_key(v, key) for v in obj.values())
    if isinstance(obj, list):
        return any(_find_key(v, key) for v in obj)
    return False


def _write_tmp_exp3_report():
    import tempfile
    fd, path = tempfile.mkstemp(suffix=".json")
    with os.fdopen(fd, "w") as f:
        json.dump({"records": RECORDS}, f)
    return path


# ---------------------------------------------------------------------------
# cohort schema

def test_single_general_cohort():
    assert cfg.COHORTS == ("general",)


def test_opaque_is_a_valid_condition_alongside_blind_and_triaged():
    assert cfg.CONDITIONS == ("blind", "triaged", "opaque")


# ---------------------------------------------------------------------------
# session creation / item counts

def test_session_creation_opaque_vs_claim_conditions_item_counts(client):
    # blind/triaged: one item per underlying claim (within a (record, arm)
    # case), opaque: one item per case.
    for condition, count in (("blind", CLAIM_COUNT), ("triaged", CLAIM_COUNT),
                             ("opaque", OPAQUE_COUNT)):
        resp = _create(client, condition=condition)
        assert resp.status_code == 201, resp.get_json()
        body = resp.get_json()
        assert body["item_count"] == count
        assert body["cohort"] == "general"
        assert body["document_id"] == GENERAL_DOC_ID


def test_document_id_cannot_be_overridden_for_an_exp3_cohort(client):
    resp = _create(client, document_id="something-else")
    assert resp.status_code == 400


# ---------------------------------------------------------------------------
# opaque rendering + skip behavior

def test_opaque_view_has_one_collapsed_passage_per_case_no_claim_breakdown(client):
    sid = _create(client, condition="opaque").get_json()["session_id"]
    resp = client.get(f"/study/sessions/{sid}/items")
    assert resp.status_code == 200
    body = resp.get_json()

    assert not _find_key(body, "risk_tier")
    assert not _find_key(body, "risk_flags")
    assert not _find_key(body, "ground_truth_label")
    assert not _find_key(body, "arm")

    items = body["items"]
    assert len(items) == OPAQUE_COUNT
    for it in items:
        assert it["item_type"] == "batch_passage"
        assert set(it.keys()) == {"item_id", "item_type", "passage"}
        assert isinstance(it["passage"], str)

    passages = {it["item_id"]: it["passage"] for it in items}
    assert passages["case_factoidwiki:5__disco_rag"] == "L1 L2"
    assert passages["case_factoidwiki:5__custom_fallback"] == "L3"
    assert passages["case_factoidwiki:5__contextual_retrieval"] == "L4"
    assert passages["case_factoidwiki:10__disco_rag"] == "D1 D2"
    assert passages["case_factoidwiki:10__custom_fallback"] == "C1"
    assert passages["case_factoidwiki:10__contextual_retrieval"] == "R1 R2 R3"
    assert passages["case_factoidwiki:50__disco_rag"] == "D3"
    assert passages["case_factoidwiki:50__custom_fallback"] == "C2 C3"
    assert passages["case_factoidwiki:75__custom_fallback"] == "C4"
    assert passages["case_factoidwiki:75__contextual_retrieval"] == "R4 R5"

    # skipped (record, arm) cases never appear at all
    assert "case_factoidwiki:50__contextual_retrieval" not in passages
    assert "case_factoidwiki:75__disco_rag" not in passages

    # one decision point per case
    nxt = client.get(f"/study/sessions/{sid}/items/next").get_json()
    first_item_id = nxt["item"]["item_id"]
    assert _decide(client, sid, first_item_id).status_code == 201


def test_repair_arm_error_and_empty_claims_are_skipped_not_crashed():
    json_path = _write_tmp_exp3_report()
    cases = cfg.load_exp3_cases(json_path, "general")
    keys = {(c["record_id"], c["arm"]) for c in cases}
    assert ("factoidwiki:50", "contextual_retrieval") not in keys
    assert ("factoidwiki:75", "disco_rag") not in keys
    assert len(cases) == OPAQUE_COUNT
    os.remove(json_path)


# ---------------------------------------------------------------------------
# blind / triaged on the exp3 corpus

def test_blind_exp3_shows_individual_claims_no_flags_fixed_order(client):
    sid = _create(client, condition="blind").get_json()["session_id"]
    resp = client.get(f"/study/sessions/{sid}/items")
    body = resp.get_json()
    assert not _find_key(body, "risk_flags")
    assert not _find_key(body, "ground_truth_label")
    assert not _find_key(body, "arm")

    batch = [it for it in body["items"] if it["item_type"] == "batch_claim"]
    assert len(batch) == CLAIM_COUNT
    assert [it["claim_index"] for it in batch] == list(range(CLAIM_COUNT))
    assert [it["english"] for it in batch] == [
        "L1", "L2", "L3", "L4", "D1", "D2", "C1", "R1", "R2", "R3",
        "L5", "L6", "L7", "L8", "D3", "C2", "C3", "C4", "R4", "R5",
    ]
    for it in batch:
        assert "risk_flags" not in it
        assert "risk_tier" not in it


def test_triaged_exp3_shows_flags_and_sorts_flagged_claims_first(client):
    sid = _create(client, condition="triaged").get_json()["session_id"]
    body = client.get(f"/study/sessions/{sid}/items").get_json()
    batch = [it for it in body["items"] if it["item_type"] == "batch_claim"]

    assert [it["claim_index"] for it in batch] == TRIAGED_ORDER
    for it in batch:
        if it["claim_index"] in (10, 11, 12, 13):
            assert it["risk_flags"] == _flags("cross_reference")
        elif it["claim_index"] in (14, 15, 16):
            assert it["risk_flags"] == _flags("segment_concession_satellite")
        else:
            assert it["risk_flags"] == []

    nxt = client.get(f"/study/sessions/{sid}/items/next").get_json()
    assert nxt["item"]["claim_index"] == TRIAGED_ORDER[0]


# ---------------------------------------------------------------------------
# ground truth vocabulary

def test_ground_truth_labels_are_correct_and_dangerous_failure(client):
    assert cfg.EXP3_GROUND_TRUTH_LABELS == ("correct", "dangerous_failure")

    sid = _create(client, condition="blind").get_json()["session_id"]
    stored = client.get(f"/study/admin/sessions/{sid}").get_json()
    labels_by_claim = {it["claim_index"]: it["ground_truth_label"]
                      for it in stored["items"]
                      if it["item_type"] == "batch_claim"}
    assert labels_by_claim == GROUND_TRUTH_BY_CLAIM
    assert set(labels_by_claim.values()) <= set(cfg.EXP3_GROUND_TRUTH_LABELS)

    # old CFR-track / pipeline-path vocabulary never leaks into this
    # corpus's labels
    assert "severed" not in labels_by_claim.values()
    assert "preserved" not in labels_by_claim.values()
    assert "seeded_error" not in labels_by_claim.values()
    assert "clean" not in labels_by_claim.values()

    opaque_sid = _create(client, condition="opaque").get_json()["session_id"]
    opaque_stored = client.get(
        f"/study/admin/sessions/{opaque_sid}").get_json()
    opaque_labels = {it["item_id"]: it["ground_truth_label"]
                    for it in opaque_stored["items"]}
    assert opaque_labels["case_factoidwiki:10__disco_rag"] == "correct"
    assert opaque_labels["case_factoidwiki:10__custom_fallback"] == "dangerous_failure"
    assert opaque_labels["case_factoidwiki:50__disco_rag"] == "correct"
    assert opaque_labels["case_factoidwiki:75__contextual_retrieval"] == "dangerous_failure"


# ---------------------------------------------------------------------------
# case-level sharing: claims within one case share flags + ground truth;
# arm_6_flagged_deferral-derived flags are identical across a record's arms

def test_claims_within_one_case_share_flags_and_ground_truth(client):
    sid = _create(client, condition="triaged").get_json()["session_id"]
    stored = client.get(f"/study/admin/sessions/{sid}").get_json()
    by_claim = {it["claim_index"]: it for it in stored["items"]
               if it["item_type"] == "batch_claim"}

    # (10, contextual_retrieval) case = claims 7, 8, 9: 3 claims, one case.
    for ci in (7, 8, 9):
        assert by_claim[ci]["ground_truth_label"] == "dangerous_failure"
        assert by_claim[ci]["payload"]["risk_flags"] == []
        assert by_claim[ci]["arm"] == "contextual_retrieval"

    # (20, custom_fallback) case = claims 11, 12: both share the
    # record-level flag AND the same ground truth.
    for ci in (11, 12):
        assert by_claim[ci]["ground_truth_label"] == "dangerous_failure"
        assert by_claim[ci]["payload"]["risk_flags"] == _flags("cross_reference")
        assert by_claim[ci]["arm"] == "custom_fallback"


def test_arm6_flagged_deferral_flags_are_identical_across_a_records_arms(client):
    sid = _create(client, condition="triaged").get_json()["session_id"]
    stored = client.get(f"/study/admin/sessions/{sid}").get_json()
    by_claim = {it["claim_index"]: it for it in stored["items"]
               if it["item_type"] == "batch_claim"}

    # record pool_index=20's 3 surviving arms (disco_rag: claim 10;
    # custom_fallback: claims 11, 12; contextual_retrieval: claim 13) are
    # computed against the SAME arm_6_flagged_deferral (record-level,
    # pre-repair) -- so their flags lists must be identical even though the
    # arms themselves disagree on nothing else here.
    assert (by_claim[10]["payload"]["risk_flags"]
           == by_claim[11]["payload"]["risk_flags"]
           == by_claim[12]["payload"]["risk_flags"]
           == by_claim[13]["payload"]["risk_flags"]
           == _flags("cross_reference"))


# ---------------------------------------------------------------------------
# arm passthrough (export only, never participant-facing)

def test_arm_never_reaches_participant_view(client):
    sid = _create(client, condition="triaged").get_json()["session_id"]
    items_body = client.get(f"/study/sessions/{sid}/items").get_json()
    assert not _find_key(items_body, "arm")

    # /items/next, one item at a time, same invariant
    for _ in range(CLAIM_COUNT):
        nxt_body = client.get(f"/study/sessions/{sid}/items/next").get_json()
        assert not _find_key(nxt_body, "arm")
        item_id = nxt_body["item"]["item_id"]
        assert _decide(client, sid, item_id).status_code == 201


def test_arm_passes_through_to_export(client):
    sid = _create(client, condition="triaged").get_json()["session_id"]
    items = client.get(f"/study/sessions/{sid}/items").get_json()["items"]
    for it in items:
        assert _decide(client, sid, it["item_id"]).status_code == 201

    record = client.get(f"/study/sessions/{sid}/export").get_json()
    arm_by_claim = {it["item_id"]: it["arm"] for it in record["items"]}
    assert arm_by_claim["claim_0"] == "disco_rag"
    assert arm_by_claim["claim_2"] == "custom_fallback"
    assert arm_by_claim["claim_3"] == "contextual_retrieval"


def test_arm_absent_from_pipeline_sourced_export(tmp_path, monkeypatch):
    """The original corpus-sourcing path's export shape is byte-for-byte
    unchanged: arm is additive and only appears for exp3 items."""
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    outputs = tmp_path / "outputs"
    outputs.mkdir()
    (outputs / "doc-p_final_data.json").write_text(json.dumps({
        "axioms": [{
            "claim_index": 0, "segment_index": 0, "english": "Claim.",
            "formal": "P(x)", "id": "ax0", "flag": "none",
            "risk_flags": [], "risk_tier": "Low",
        }],
    }))
    (tmp_path / "gt.json").write_text(json.dumps({"seeded_error_claim_indices": []}))
    config = {"cohorts": {"general": {"document_id": "doc-p",
                                      "ground_truth_file": "gt.json"}}}
    config_path = tmp_path / "study_config.json"
    config_path.write_text(json.dumps(config))
    monkeypatch.setenv("STUDY_CONFIG", str(config_path))

    app = Flask(__name__)
    app.config["TESTING"] = True
    app.register_blueprint(study_bp)
    pipeline_client = app.test_client()

    sid = _create(pipeline_client, condition="blind").get_json()["session_id"]
    record = pipeline_client.get(f"/study/sessions/{sid}/export").get_json()
    for it in record["items"]:
        assert "arm" not in it


# ---------------------------------------------------------------------------
# end-to-end decisions + export, all three conditions

@pytest.mark.parametrize("condition", ["blind", "triaged", "opaque"])
def test_decisions_and_export_end_to_end(client, condition):
    sid = _create(client, participant_id="P-e2e",
                 condition=condition).get_json()["session_id"]
    items = client.get(f"/study/sessions/{sid}/items").get_json()["items"]
    assert len(items) > 0

    for it in items:
        resp = _decide(client, sid, it["item_id"], decision="approved",
                       confidence=4)
        assert resp.status_code == 201, resp.get_json()

    record = client.get(f"/study/sessions/{sid}/export").get_json()
    assert record["participant_id"] == "P-e2e"
    assert record["cohort"] == "general"
    assert record["condition"] == condition
    assert record["document_id"] == GENERAL_DOC_ID
    assert len(record["items"]) == len(items)
    for it in record["items"]:
        assert it["decision"] == "approved"
        assert it["confidence"] == 4
        assert it["time_to_decision"] > 0
        assert it["ground_truth_label"] in cfg.EXP3_GROUND_TRUTH_LABELS
        assert it["arm"] in cfg.EXP3_REPAIR_ARMS


# ---------------------------------------------------------------------------
# config validation for the exp3-sourcing path

def test_exp3_and_pipeline_sources_are_mutually_exclusive(tmp_path):
    config = {"cohorts": {"general": {
        "exp3_report_file": REAL_EXP3_REPORT,
        "document_id": "x",
        "ground_truth_file": "g.json",
    }}}
    path = tmp_path / "study_config.json"
    path.write_text(json.dumps(config))
    with pytest.raises(cfg.ConfigError, match="both"):
        cfg.load_study_config(str(path))


def test_exp3_cohort_rejects_queries(tmp_path):
    config = {"cohorts": {"general": {
        "exp3_report_file": REAL_EXP3_REPORT,
        "queries": [{"query_id": "q1", "query": "x", "classification": "clean",
                    "answer": "y", "source_claim_indices": [0]}],
    }}}
    path = tmp_path / "study_config.json"
    path.write_text(json.dumps(config))
    with pytest.raises(cfg.ConfigError, match="queries"):
        cfg.load_study_config(str(path))


def test_load_exp3_cases_rejects_unknown_cohort(tmp_path):
    path = tmp_path / "report.json"
    path.write_text(json.dumps({"records": RECORDS}))
    with pytest.raises(cfg.ConfigError, match="EXP3_DOCUMENT_IDS"):
        cfg.load_exp3_cases(str(path), "not_a_real_cohort")


def test_load_exp3_cases_rejects_missing_pool_index(tmp_path):
    bad_record = _record(5, [], [], disco_rag=_arm(["c"], preserved=True),
                         custom_fallback=_arm(["c"], preserved=True),
                         contextual_retrieval=_arm(["c"], preserved=True))
    del bad_record["pool_index"]
    path = tmp_path / "bad.json"
    path.write_text(json.dumps({"records": [bad_record]}))
    with pytest.raises(cfg.ConfigError, match="pool_index"):
        cfg.load_exp3_cases(str(path), "general")


def test_load_exp3_cases_rejects_unknown_bucket(tmp_path):
    bad_record = _record(5, ["pre"], [[]],
                         disco_rag=_arm(["c1"], preserved=True),
                         custom_fallback=_arm(["c2"], preserved=True),
                         contextual_retrieval=_arm(["c3"], preserved=True))
    bad_record["arm_2_disco_rag"]["bucket"] = "unscored"
    path = tmp_path / "bad.json"
    path.write_text(json.dumps({"records": [bad_record]}))
    with pytest.raises(cfg.ConfigError, match="bucket"):
        cfg.load_exp3_cases(str(path), "general")


def test_load_exp3_cases_rejects_bucket_preserved_disagreement(tmp_path):
    bad_record = _record(5, ["pre"], [[]],
                         disco_rag=_arm(["c1"], preserved=True),
                         custom_fallback=_arm(["c2"], preserved=True),
                         contextual_retrieval=_arm(["c3"], preserved=True))
    # judge.preserved says True but bucket says dangerous_failure: an
    # internal disagreement between two already-computed fields.
    bad_record["arm_2_disco_rag"]["bucket"] = "dangerous_failure"
    bad_record["arm_2_disco_rag"]["failure_type"] = {
        "category": "dangerous_failure", "reasoning": "..."}
    path = tmp_path / "bad.json"
    path.write_text(json.dumps({"records": [bad_record]}))
    with pytest.raises(cfg.ConfigError, match="disagree"):
        cfg.load_exp3_cases(str(path), "general")


def test_load_exp3_cases_rejects_unexpected_failure_category(tmp_path):
    bad_record = _record(
        999, ["pre"], [[]],
        disco_rag=_arm(["c1"], preserved=False,
                       failure_category="detectable_failure"),
        custom_fallback=_arm(["c2"], preserved=True),
        contextual_retrieval=_arm(["c3"], preserved=True),
    )
    path = tmp_path / "bad.json"
    path.write_text(json.dumps({"records": [bad_record]}))
    with pytest.raises(cfg.ConfigError, match="failure_type"):
        cfg.load_exp3_cases(str(path), "general")


# ---------------------------------------------------------------------------
# integration check against the real, checked-in
# task8_factoidwiki_exp3_report.json

def test_real_exp3_report_loads_and_computes_expected_counts():
    assert os.path.isfile(REAL_EXP3_REPORT), (
        "expected task8_factoidwiki_exp3_report.json at " + REAL_EXP3_REPORT)

    cases = cfg.load_exp3_cases(REAL_EXP3_REPORT, "general")

    # Confirmed by directly reading task8_factoidwiki_exp3_report.json's 109
    # records x 3 pooled repair arms, with zero (record, arm) skips anywhere
    # in the checked-in data (zero 'error' set, zero empty 'propositions'
    # across all 3 arms x 109 records).
    assert len(cases) == 327  # opaque case count
    assert sum(len(c["claims"]) for c in cases) == 2256  # blind/triaged claim count

    from collections import Counter
    label_counts = Counter(c["ground_truth_label"] for c in cases)
    assert label_counts == {"correct": 202, "dangerous_failure": 125}

    for c in cases:
        assert c["ground_truth_label"] in cfg.EXP3_GROUND_TRUTH_LABELS
        assert c["arm"] in cfg.EXP3_REPAIR_ARMS
        assert isinstance(c["flags"], list)
        assert c["record_id"].startswith("factoidwiki:")


def test_real_exp3_report_case_ids_and_arms_are_stable_via_session_creation(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    config = {"cohorts": {
        "general": {"exp3_report_file": REAL_EXP3_REPORT},
    }}
    config_path = tmp_path / "study_config.json"
    config_path.write_text(json.dumps(config))
    monkeypatch.setenv("STUDY_CONFIG", str(config_path))

    app = Flask(__name__)
    app.config["TESTING"] = True
    app.register_blueprint(study_bp)
    real_client = app.test_client()

    resp = _create(real_client, condition="opaque")
    assert resp.status_code == 201, resp.get_json()
    assert resp.get_json()["item_count"] == 327
    assert resp.get_json()["document_id"] == GENERAL_DOC_ID

    resp = _create(real_client, condition="blind")
    assert resp.status_code == 201
    assert resp.get_json()["item_count"] == 2256
