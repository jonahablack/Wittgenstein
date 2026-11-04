"""Regression tests for the formalization reconciliation invariant
(logic_formalization.py):

    output axiom count == input claim count, ALWAYS -- under full model
    success, partial claim drops, unparseable garbage, and whole-batch
    exceptions. Unformalized claims become placeholder axioms with
    formal=None (formal_logic=None + formal_english=None in "both" mode).
    "english" is always the pipeline's own verbatim text, never the
    model's copy -- the model is never even asked for it.
"""

import json

import pytest

from components import logic_formalization
from conftest import FakeResponse


def _claims(n):
    """Input claims exactly as extraction now produces them: claim_index
    pre-assigned at extraction time."""
    return [
        {
            "claim_index": i,
            "segment_index": i * 10,
            "english": f"Original claim text number {i}.",
        }
        for i in range(n)
    ]


def _full_success_stub(monkeypatch, mode="logic"):
    """Model returns exactly one well-formed axiom per claim_index in the
    prompt -- and deliberately includes a paraphrased 'english' field, which
    the pipeline must ignore."""

    def fake(prompt, *args, **kwargs):
        import re
        indices = [int(m) for m in re.findall(r"\(claim_index (\d+)\)", prompt)]
        axioms = []
        for idx in indices:
            item = {
                "claim_index": idx,
                # Model tries to hand back its own (paraphrased) english --
                # reconciliation must never use it.
                "english": f"MODEL PARAPHRASE of claim {idx}",
            }
            if mode == "both":
                item["formal_logic"] = f"P{idx}(x)"
                item["formal_english"] = f"For every x, P{idx} holds."
            else:
                item["formal"] = f"P{idx}(x)"
            axioms.append(item)
        return FakeResponse(json.dumps({"axioms": axioms}))

    monkeypatch.setattr(logic_formalization, "generate_response", fake)


def test_full_success_count_and_verbatim_english(monkeypatch):
    claims = _claims(7)
    _full_success_stub(monkeypatch)
    result = logic_formalization.formalize_claims(claims, "logic", batch_size=3)
    axioms = result["axioms"]

    assert len(axioms) == 7
    assert result["unformalized_count"] == 0
    for i, ax in enumerate(sorted(axioms, key=lambda a: a["claim_index"])):
        assert ax["claim_index"] == i
        assert ax["english"] == f"Original claim text number {i}."
        assert "PARAPHRASE" not in ax["english"]
        assert ax["formal"] == f"P{i}(x)"
        assert ax["segment_index"] == i * 10


def test_model_drops_some_claims_placeholders_fill_gap(monkeypatch):
    """(ii) model silently drops/merges claim_indices -> placeholders with
    formal=None, count preserved."""
    dropped = {1, 4}

    def fake(prompt, *args, **kwargs):
        import re
        indices = [int(m) for m in re.findall(r"\(claim_index (\d+)\)", prompt)]
        axioms = [
            {"claim_index": idx, "formal": f"P{idx}(x)"}
            for idx in indices if idx not in dropped
        ]
        return FakeResponse(json.dumps({"axioms": axioms}))

    monkeypatch.setattr(logic_formalization, "generate_response", fake)

    claims = _claims(6)
    result = logic_formalization.formalize_claims(claims, "logic", batch_size=50)
    axioms = {ax["claim_index"]: ax for ax in result["axioms"]}

    assert len(axioms) == 6
    assert result["unformalized_count"] == 2
    for idx in range(6):
        assert axioms[idx]["english"] == f"Original claim text number {idx}."
        if idx in dropped:
            assert axioms[idx]["formal"] is None
        else:
            assert axioms[idx]["formal"] == f"P{idx}(x)"


def test_unparseable_garbage_yields_all_placeholders(monkeypatch):
    """(iii) model returns non-JSON garbage -> every claim becomes a
    placeholder axiom; nothing dropped, nothing raised."""
    monkeypatch.setattr(
        logic_formalization, "generate_response",
        lambda *a, **k: FakeResponse("Sure! Here are your axioms: <<<not json>>>"),
    )

    claims = _claims(5)
    result = logic_formalization.formalize_claims(claims, "logic")
    axioms = result["axioms"]

    assert len(axioms) == 5
    assert result["unformalized_count"] == 5
    for ax in sorted(axioms, key=lambda a: a["claim_index"]):
        assert ax["formal"] is None
        assert ax["english"] == f"Original claim text number {ax['claim_index']}."


def test_whole_batch_exception_yields_placeholders_for_that_batch(monkeypatch):
    """(iv) one batch's model call raises outright (simulated partial
    failure) -> that batch's claims survive as placeholders while the other
    batch formalizes normally. Total count still equals input count."""

    def fake(prompt, *args, **kwargs):
        import re
        indices = [int(m) for m in re.findall(r"\(claim_index (\d+)\)", prompt)]
        if 0 in indices:  # first batch blows up entirely
            raise RuntimeError("simulated API meltdown")
        axioms = [{"claim_index": idx, "formal": f"P{idx}(x)"} for idx in indices]
        return FakeResponse(json.dumps({"axioms": axioms}))

    monkeypatch.setattr(logic_formalization, "generate_response", fake)

    claims = _claims(6)
    result = logic_formalization.formalize_claims(claims, "logic", batch_size=3)
    axioms = {ax["claim_index"]: ax for ax in result["axioms"]}

    assert len(axioms) == 6
    assert result["unformalized_count"] == 3
    for idx in (0, 1, 2):
        assert axioms[idx]["formal"] is None
        assert axioms[idx]["english"] == f"Original claim text number {idx}."
    for idx in (3, 4, 5):
        assert axioms[idx]["formal"] == f"P{idx}(x)"


def test_none_response_yields_placeholders(monkeypatch):
    """generate_response returning None (retries exhausted) is reconciled,
    not crashed on."""
    monkeypatch.setattr(logic_formalization, "generate_response", lambda *a, **k: None)
    claims = _claims(3)
    result = logic_formalization.formalize_claims(claims, "logic")
    assert len(result["axioms"]) == 3
    assert result["unformalized_count"] == 3


def test_both_mode_placeholders_have_both_fields_none(monkeypatch):
    monkeypatch.setattr(
        logic_formalization, "generate_response",
        lambda *a, **k: FakeResponse("garbage"),
    )
    claims = _claims(2)
    result = logic_formalization.formalize_claims(claims, "both")
    assert len(result["axioms"]) == 2
    for ax in result["axioms"]:
        assert ax["formal_logic"] is None
        assert ax["formal_english"] is None


def test_both_mode_success_keeps_verbatim_english(monkeypatch):
    claims = _claims(4)
    _full_success_stub(monkeypatch, mode="both")
    result = logic_formalization.formalize_claims(claims, "both", batch_size=2)
    axioms = sorted(result["axioms"], key=lambda a: a["claim_index"])
    assert len(axioms) == 4
    for i, ax in enumerate(axioms):
        assert ax["english"] == f"Original claim text number {i}."
        assert ax["formal_logic"] == f"P{i}(x)"
        assert ax["formal_english"] == f"For every x, P{i} holds."


def test_preassigned_claim_index_respected(monkeypatch):
    """claim_index assigned at extraction time must never be overwritten
    by formalize_claims -- reconciliation is keyed on the extraction-time
    identity."""
    claims = [
        {"claim_index": 40, "segment_index": 4, "english": "Claim forty."},
        {"claim_index": 41, "segment_index": 5, "english": "Claim forty-one."},
    ]
    _full_success_stub(monkeypatch)
    result = logic_formalization.formalize_claims(claims, "logic")
    indices = sorted(ax["claim_index"] for ax in result["axioms"])
    assert indices == [40, 41]
    by_idx = {ax["claim_index"]: ax for ax in result["axioms"]}
    assert by_idx[40]["english"] == "Claim forty."
    assert by_idx[40]["formal"] == "P40(x)"


def test_model_never_asked_for_english(monkeypatch):
    """The prompt must not request the claim's english text back -- that is
    how paraphrase drift got into the output historically."""
    prompts = []

    def fake(prompt, *args, **kwargs):
        prompts.append(prompt)
        return FakeResponse(json.dumps({"axioms": []}))

    monkeypatch.setattr(logic_formalization, "generate_response", fake)
    logic_formalization.formalize_claims(_claims(2), "logic")

    assert prompts
    for p in prompts:
        assert "Do not include the claim's English text" in p
        # The requested output fields never include an "english" key.
        assert '"english"' not in p
