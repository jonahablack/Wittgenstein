"""Regression tests for the two chunking modes in response_parsing.py:

  - "propositional": LLM decomposition; claim records carry claim_index
    (assigned at extraction time) and segment_index.
  - "passage": fixed-size sentence windows with NO LLM call at all;
    segment_index is the passage's first sentence's index so
    segment_lookup still resolves.
  - Both modes produce an identical record shape downstream.
  - Model failure paths (garbage / no response) yield empty claims for
    that segment, never a crash.
"""

import json

import pytest

from components import response_parsing
from components.response_parsing import (
    build_claim_records,
    extract_claim_records,
    extract_passages,
)
from conftest import FakeResponse

SEGMENTS = [
    (0, "All swans are white."),
    (1, "Socrates is a man and Socrates is mortal."),
    (2, "Therefore, consider the following."),
    (3, "Every event has a cause."),
    (4, "Nothing comes from nothing."),
]

EXPECTED_KEYS = {"claim_index", "segment_index", "english"}


def _propositional_stub(monkeypatch):
    """Echo each sentence back as claims: seg 1 splits into two atomic
    claims, seg 2 asserts nothing, others return themselves."""

    def fake(prompt, *args, **kwargs):
        import re
        m = re.search(r"Segment index: (\d+)", prompt)
        seg_idx = int(m.group(1))
        if seg_idx == 1:
            claims = ["Socrates is a man.", "Socrates is mortal."]
        elif seg_idx == 2:
            claims = []
        else:
            claims = [dict(SEGMENTS)[seg_idx]]
        return FakeResponse(json.dumps({"segment_index": seg_idx, "claims": claims}))

    monkeypatch.setattr(response_parsing, "generate_response", fake)


def test_propositional_mode_records(monkeypatch):
    _propositional_stub(monkeypatch)
    records, unit_results = extract_claim_records(
        SEGMENTS, chunking_mode="propositional", use_parallel=False)

    # 4 asserting segments, one of which split into 2 atomic claims
    assert len(records) == 5
    # claim_index assigned at extraction time: globally unique, 0..N-1
    assert [r["claim_index"] for r in records] == list(range(5))
    for r in records:
        assert set(r.keys()) == EXPECTED_KEYS
    # segment_index preserved per claim; split claims share their segment
    split = [r for r in records if r["segment_index"] == 1]
    assert {r["english"] for r in split} == {"Socrates is a man.", "Socrates is mortal."}
    # non-asserting segment contributed no records but is still a unit
    assert len(unit_results) == 5
    assert not any(r["segment_index"] == 2 for r in records)


def test_propositional_mode_parallel_path(monkeypatch):
    """Same invariants hold through the ThreadPoolExecutor path."""
    _propositional_stub(monkeypatch)
    records, unit_results = extract_claim_records(
        SEGMENTS, chunking_mode="propositional", use_parallel=True, max_workers=3)
    assert len(records) == 5
    assert [r["claim_index"] for r in records] == list(range(5))
    assert len(unit_results) == 5
    for r in records:
        assert set(r.keys()) == EXPECTED_KEYS


def test_passage_mode_no_llm_call(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("passage mode must not call the LLM")

    monkeypatch.setattr(response_parsing, "generate_response", forbidden)

    records, unit_results = extract_claim_records(
        SEGMENTS, chunking_mode="passage", passage_size=2)

    # 5 sentences in windows of 2 -> 3 passages
    assert len(records) == 3
    assert [r["claim_index"] for r in records] == [0, 1, 2]
    # segment_index = index of the passage's FIRST sentence
    assert [r["segment_index"] for r in records] == [0, 2, 4]
    assert records[0]["english"] == "All swans are white. Socrates is a man and Socrates is mortal."
    assert records[2]["english"] == "Nothing comes from nothing."
    for r in records:
        assert set(r.keys()) == EXPECTED_KEYS


def test_passage_segment_index_resolves_in_segment_lookup():
    segment_lookup = dict(SEGMENTS)
    records, _ = extract_claim_records(SEGMENTS, chunking_mode="passage", passage_size=3)
    for r in records:
        assert r["segment_index"] in segment_lookup


def test_both_modes_identical_record_shape(monkeypatch):
    _propositional_stub(monkeypatch)
    prop_records, _ = extract_claim_records(
        SEGMENTS, chunking_mode="propositional", use_parallel=False)
    pass_records, _ = extract_claim_records(SEGMENTS, chunking_mode="passage")

    assert prop_records and pass_records
    for r in prop_records + pass_records:
        assert set(r.keys()) == EXPECTED_KEYS
        assert isinstance(r["claim_index"], int)
        assert isinstance(r["segment_index"], int)
        assert isinstance(r["english"], str)


def test_unknown_chunking_mode_raises():
    with pytest.raises(ValueError):
        extract_claim_records(SEGMENTS, chunking_mode="semantic")


def test_extract_passages_window_boundaries():
    units = extract_passages(SEGMENTS, passage_size=4)
    assert len(units) == 2
    assert units[0]["segment_index"] == 0
    assert units[1]["segment_index"] == 4
    assert units[1]["claims"] == ["Nothing comes from nothing."]
    # degenerate passage_size clamps to 1 rather than looping forever
    assert len(extract_passages(SEGMENTS, passage_size=0)) == 5


def test_build_claim_records_skips_units_without_segment_index():
    units = [
        {"segment_index": None, "claims": ["orphan claim"]},
        {"segment_index": 7, "claims": ["kept claim"]},
    ]
    records = build_claim_records(units)
    assert len(records) == 1
    assert records[0] == {"claim_index": 0, "segment_index": 7, "english": "kept claim"}


def test_propositional_garbage_response_yields_empty_not_crash(monkeypatch):
    monkeypatch.setattr(
        response_parsing, "generate_response",
        lambda *a, **k: FakeResponse("total garbage, no json here"),
    )
    records, unit_results = extract_claim_records(
        [(0, "All swans are white.")], chunking_mode="propositional", use_parallel=False)
    assert records == []
    assert len(unit_results) == 1


def test_propositional_none_response_yields_empty_not_crash(monkeypatch):
    monkeypatch.setattr(response_parsing, "generate_response", lambda *a, **k: None)
    records, unit_results = extract_claim_records(
        [(0, "All swans are white.")], chunking_mode="propositional", use_parallel=False)
    assert records == []
    assert unit_results == [{"segment_index": 0, "claims": []}]


def test_propositional_prompt_states_criteria_and_scope():
    """The prompt is the conceptual implementation of Chen et al.'s stated
    criteria (atomic / self-contained / verbatim where possible) -- make
    sure the three criteria stay present if the prompt is edited."""
    prompt = response_parsing._build_claim_extraction_prompt(0, "It rains.")
    for marker in ("ATOMIC", "SELF-CONTAINED", "VERBATIM"):
        assert marker in prompt
