"""End-to-end smoke test: formalize_file() runs the full pipeline
(PDF extraction -> segmentation -> claim extraction -> formalization ->
reconciliation -> risk triage -> reconstruction -> PDF output) in BOTH
chunking modes, with every LLM call stubbed. No network, ever."""

import json
import os
import re

import pytest
from reportlab.lib.pagesizes import LETTER
from reportlab.pdfgen import canvas

from components import logic_formalization, main, response_parsing
from conftest import FakeResponse

_DOC_SENTENCES = [
    "All men are mortal.",
    "Socrates is a man and Socrates is a philosopher.",
    "Every event has a cause.",
    "Nothing can come from nothing.",
]


@pytest.fixture
def sample_pdf(tmp_path):
    pdf_path = tmp_path / "sample.pdf"
    c = canvas.Canvas(str(pdf_path), pagesize=LETTER)
    y = 700
    for sentence in _DOC_SENTENCES:
        c.drawString(72, y, sentence)
        y -= 20
    c.save()
    return str(pdf_path)


def _stub_extraction(monkeypatch):
    """Propositional-mode extraction stub: each sentence yields itself as
    one claim (echoing the segment text out of the prompt)."""

    def fake(prompt, *args, **kwargs):
        seg_idx = int(re.search(r"Segment index: (\d+)", prompt).group(1))
        sentence = re.search(r'Segment text: "(.*)"', prompt, re.DOTALL).group(1).strip()
        return FakeResponse(json.dumps({"segment_index": seg_idx, "claims": [sentence]}))

    monkeypatch.setattr(response_parsing, "generate_response", fake)


def _stub_formalization(monkeypatch):
    def fake(prompt, *args, **kwargs):
        indices = [int(m) for m in re.findall(r"\(claim_index (\d+)\)", prompt)]
        axioms = [{"claim_index": idx, "formal": f"P{idx}(x)"} for idx in indices]
        return FakeResponse(json.dumps({"axioms": axioms}))

    monkeypatch.setattr(logic_formalization, "generate_response", fake)


def _assert_pipeline_output(result, output_dir):
    axioms = result["axioms"]
    assert axioms, "pipeline produced no axioms"
    # reconciliation invariant surfaces end-to-end: unique, per-claim ids
    claim_indices = [ax["claim_index"] for ax in axioms]
    assert len(claim_indices) == len(set(claim_indices))
    for ax in axioms:
        assert ax["english"]
        assert "segment_index" in ax
        assert ax["risk_tier"] in ("High", "Medium", "Low", "Unformalized")
        assert "risk_flags" in ax
    assert os.path.exists(result["output_pdf"])
    assert result["output_pdf"].startswith(output_dir)
    assert result["logic_reconstruction"]
    assert result["english_reconstruction"]


def test_end_to_end_propositional_mode(monkeypatch, sample_pdf, tmp_path):
    _stub_extraction(monkeypatch)
    _stub_formalization(monkeypatch)
    out_dir = str(tmp_path / "out")

    result = main.formalize_file(
        sample_pdf, "logic", use_parallel=False, output_dir=out_dir,
        chunking_mode="propositional",
    )

    _assert_pipeline_output(result, out_dir)
    # one claim per sentence from the stub -> axiom count matches
    assert len(result["axioms"]) == len(_DOC_SENTENCES)
    assert result["warning"] is None


def test_end_to_end_passage_mode(monkeypatch, sample_pdf, tmp_path):
    # extraction LLM must never be consulted in passage mode
    monkeypatch.setattr(
        response_parsing, "generate_response",
        lambda *a, **k: (_ for _ in ()).throw(
            AssertionError("passage mode called the extraction LLM")),
    )
    _stub_formalization(monkeypatch)
    out_dir = str(tmp_path / "out")

    result = main.formalize_file(
        sample_pdf, "logic", use_parallel=False, output_dir=out_dir,
        chunking_mode="passage",
    )

    _assert_pipeline_output(result, out_dir)
    assert result["warning"] is None


def test_end_to_end_reconciliation_visible_when_model_drops_claims(
        monkeypatch, sample_pdf, tmp_path):
    """Model drops one claim end-to-end -> placeholder axiom survives to the
    final output, tagged Unformalized, and the user-facing warning fires."""
    _stub_extraction(monkeypatch)

    def dropping_formalizer(prompt, *args, **kwargs):
        indices = [int(m) for m in re.findall(r"\(claim_index (\d+)\)", prompt)]
        axioms = [{"claim_index": idx, "formal": f"P{idx}(x)"}
                  for idx in indices if idx != 0]
        return FakeResponse(json.dumps({"axioms": axioms}))

    monkeypatch.setattr(logic_formalization, "generate_response", dropping_formalizer)
    out_dir = str(tmp_path / "out")

    result = main.formalize_file(
        sample_pdf, "logic", use_parallel=False, output_dir=out_dir,
        chunking_mode="propositional",
    )

    axioms = result["axioms"]
    assert len(axioms) == len(_DOC_SENTENCES)  # nothing vanished
    dropped = [ax for ax in axioms if ax["claim_index"] == 0]
    assert len(dropped) == 1
    assert dropped[0]["formal"] is None
    assert dropped[0]["risk_tier"] == "Unformalized"
    assert result["warning"] is not None and "Unformalized" in result["warning"]


def test_invalid_chunking_mode_raises(monkeypatch, sample_pdf, tmp_path):
    _stub_extraction(monkeypatch)
    _stub_formalization(monkeypatch)
    with pytest.raises(ValueError):
        main.formalize_file(
            sample_pdf, "logic", use_parallel=False,
            output_dir=str(tmp_path / "out"), chunking_mode="bogus",
        )
