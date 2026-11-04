"""Security + concurrency regression tests.

Covers the two audited bug classes end-to-end:

1. Arbitrary file read: every file-serving route (/download, /files/...,
   /assets/...) must resolve strictly inside its sandboxed directory --
   absolute paths, ../ traversal (literal and percent-encoded), and the
   on-disk server/.env must all be unreachable. /upload's client-supplied
   extension must not be able to smuggle path separators into UPLOAD_DIR.

2. Shared scratch/output filenames: two concurrent formalize_file() calls
   (deliberately interleaved with a barrier) must not corrupt each other's
   scratch files or outputs -- distinct output paths, each result's axioms
   and PDF matching its own input document only.

Plus the output-correctness items from the same audit: DATA_DIR respected
for all output paths, "Unformalized" present in EVERY risk-tier summary
(including zero), glyph-metric word-wrapping with no dropped words, and
unformalized claims explicitly annotated in the reconstruction.

No network calls: conftest's autouse fixture hard-fails any unmocked
generate_response, and every stub here is a pure function of its prompt.
"""

import importlib
import io
import json
import os
import re
import threading
from concurrent.futures import ThreadPoolExecutor

import pytest
from reportlab.lib.pagesizes import LETTER
from reportlab.pdfgen import canvas

from components import logic_formalization, main, pdf_generation, response_parsing
from components.reconstruction import generate_reconstructions
from components.text_extraction import extract_text_from_pdf
from conftest import FakeResponse

SERVER_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

UNFORMALIZED_NOTE = "[not available -- formalization failed for this claim]"


# ---------------------------------------------------------------------------
# Flask app fixture: import app.py with DATA_DIR pointed at a tmp sandbox
# ---------------------------------------------------------------------------

@pytest.fixture
def flask_app(monkeypatch, tmp_path):
    """app.py builds UPLOAD_DIR/OUTPUT_DIR from DATA_DIR at import time, so
    set DATA_DIR to a per-test tmp dir and (re)load the module fresh."""
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    import app as app_module
    importlib.reload(app_module)
    app_module.app.config["TESTING"] = True
    yield app_module


@pytest.fixture
def client(flask_app):
    return flask_app.app.test_client()


def _make_pdf(path, sentences):
    c = canvas.Canvas(str(path), pagesize=LETTER)
    y = 700
    for sentence in sentences:
        c.drawString(72, y, sentence)
        y -= 20
    c.save()
    return str(path)


# ---------------------------------------------------------------------------
# 1a. /download: strictly basename against UPLOAD_DIR/OUTPUT_DIR
# ---------------------------------------------------------------------------

def test_download_rejects_absolute_path(client):
    resp = client.get("/download?path=/etc/passwd")
    assert resp.status_code == 404
    assert b"root:" not in resp.data


def test_download_rejects_relative_traversal_to_env(client, flask_app):
    env_path = os.path.join(SERVER_DIR, ".env")
    assert os.path.exists(env_path), "test precondition: server/.env on disk"
    with open(env_path, "rb") as f:
        env_bytes = f.read()

    # Enough ../ to reach filesystem root from anywhere, plus the exact
    # relative hop from UPLOAD_DIR to the real server/.env.
    rel_to_env = os.path.relpath(env_path, flask_app.UPLOAD_DIR)
    for path in (
        "../../server/.env",
        rel_to_env,
        "../" * 20 + env_path.lstrip("/"),
        env_path,
    ):
        resp = client.get("/download", query_string={"path": path})
        assert resp.status_code == 404, f"served traversal path {path!r}"
        assert env_bytes not in resp.data


def test_download_resolves_by_basename_inside_sandbox_only(client, flask_app):
    # A file that exists in OUTPUT_DIR is served by basename even when the
    # caller supplies a bogus absolute prefix -- proving resolution happens
    # against the sandbox, never against the supplied path.
    target = os.path.join(flask_app.OUTPUT_DIR, "result.pdf")
    with open(target, "wb") as f:
        f.write(b"sandboxed-content")
    resp = client.get("/download", query_string={"path": "/some/other/dir/result.pdf"})
    assert resp.status_code == 200
    assert resp.data == b"sandboxed-content"


# ---------------------------------------------------------------------------
# 1b. /files/<path:filename> and /assets/<path:filename>
# ---------------------------------------------------------------------------

TRAVERSAL_SUFFIXES = [
    "../app.py",
    "..%2fapp.py",
    "..%2f..%2fserver%2fapp.py",
    "%2e%2e%2fapp.py",
    "..%5c..%5capp.py",
    "%2fetc%2fpasswd",
    "..%2f..%2fserver%2f.env",
    "../../server/.env",
    ".env",
]


def _forbidden_payloads():
    with open(os.path.join(SERVER_DIR, "app.py"), "rb") as f:
        app_src = f.read()
    with open(os.path.join(SERVER_DIR, ".env"), "rb") as f:
        env_bytes = f.read()
    return app_src, env_bytes


def test_files_route_rejects_traversal(client):
    app_src, env_bytes = _forbidden_payloads()
    for suffix in TRAVERSAL_SUFFIXES:
        # follow_redirects: werkzeug's merge_slashes may 308 a //-path before
        # rejecting it; what matters is the final answer.
        resp = client.get(f"/files/{suffix}", follow_redirects=True)
        assert resp.status_code == 404, f"/files/{suffix} returned {resp.status_code}"
        assert app_src not in resp.data
        assert env_bytes not in resp.data


def test_files_route_serves_only_output_dir(client, flask_app):
    with open(os.path.join(flask_app.OUTPUT_DIR, "ok.pdf"), "wb") as f:
        f.write(b"legit-output")
    resp = client.get("/files/ok.pdf")
    assert resp.status_code == 200
    assert resp.data == b"legit-output"
    # basename normalization: a traversal-looking prefix cannot escape, at
    # worst it resolves to the same sandboxed basename
    resp = client.get("/files/subdir%2f..%2fok.pdf")
    assert resp.status_code in (200, 404)
    if resp.status_code == 200:
        assert resp.data == b"legit-output"


def test_assets_route_rejects_traversal(client):
    app_src, env_bytes = _forbidden_payloads()
    for suffix in TRAVERSAL_SUFFIXES:
        resp = client.get(f"/assets/{suffix}", follow_redirects=True)
        assert app_src not in resp.data
        assert env_bytes not in resp.data
        # The test client sends no text/html Accept header, so the SPA
        # fallback stays out of the way and a plain 404 is expected here.
        assert resp.status_code == 404, f"/assets/{suffix} returned {resp.status_code}"


def test_no_route_serves_server_env(client):
    """server/.env exists on disk; no route may expose its bytes."""
    _, env_bytes = _forbidden_payloads()
    for url in (
        "/.env",
        "/server/.env",
        "/files/.env",
        "/assets/.env",
        "/download?path=.env",
        "/download?path=server/.env",
    ):
        resp = client.get(url)
        assert env_bytes not in resp.data, f"{url} leaked server/.env"


# ---------------------------------------------------------------------------
# 1c. /upload: client-supplied extension cannot smuggle separators
# ---------------------------------------------------------------------------

def _upload(client, filename):
    return client.post(
        "/upload",
        data={"file": (io.BytesIO(b"dummy"), filename)},
        content_type="multipart/form-data",
    )


def test_upload_normal_extension_kept(client, flask_app):
    resp = _upload(client, "paper.PDF")
    assert resp.status_code == 200
    file_id = resp.get_json()["fileId"]
    assert file_id.endswith(".pdf")
    assert os.path.exists(os.path.join(flask_app.UPLOAD_DIR, file_id))


def test_upload_extension_cannot_contain_separators(client, flask_app):
    # os.path.splitext on POSIX happily returns extensions containing
    # backslashes (and other junk); none of it may reach the stored filename.
    for filename in (
        "evil.p\\..\\..\\x",
        "evil.pdf\\..\\..\\.env",
        "evil.p df",
        "evil.pdf\x00.txt",
        "evil.",
    ):
        resp = _upload(client, filename)
        if resp.status_code != 200:
            continue  # rejected outright is also safe
        file_id = resp.get_json()["fileId"]
        assert "/" not in file_id and "\\" not in file_id and ".." not in file_id, (
            f"filename {filename!r} produced unsafe fileId {file_id!r}")
        assert re.fullmatch(r"[0-9a-f-]{36}(\.[a-z0-9]{1,10})?", file_id), file_id
        stored = os.path.join(flask_app.UPLOAD_DIR, file_id)
        assert os.path.exists(stored)
        assert os.path.dirname(os.path.abspath(stored)) == os.path.abspath(
            flask_app.UPLOAD_DIR)


# ---------------------------------------------------------------------------
# DATA_DIR respected for all output paths
# ---------------------------------------------------------------------------

def test_data_dir_respected(flask_app, tmp_path):
    assert flask_app.UPLOAD_DIR == os.path.join(str(tmp_path), "uploads")
    assert flask_app.OUTPUT_DIR == os.path.join(str(tmp_path), "outputs")
    assert os.path.isdir(flask_app.UPLOAD_DIR)
    assert os.path.isdir(flask_app.OUTPUT_DIR)
    # reviews store lives under the DATA_DIR-scoped outputs dir too
    assert flask_app.REVIEWS_FILE.startswith(flask_app.OUTPUT_DIR)


# ---------------------------------------------------------------------------
# PDF output: Unformalized in EVERY risk-tier summary; real word-wrapping
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("unformalized_count", [0, 3])
def test_pdf_risk_summary_always_includes_unformalized(tmp_path, unformalized_count):
    out = str(tmp_path / "out.pdf")
    pdf_generation.generate_output_pdf(
        "=== Formal Logic Reconstruction ===\n(0) claim\n    Formal: P(x)",
        "=== English Reconstruction ===\n- claim",
        out,
        0.5, 2, 1,
        risk_counts={"High": 1, "Medium": 0, "Low": 1,
                     "Unformalized": unformalized_count},
    )
    text = extract_text_from_pdf(out)
    flat = " ".join(text.split())
    assert f"Unformalized {unformalized_count}" in flat, flat


def test_wrap_line_fits_width_and_drops_no_words(tmp_path):
    c = canvas.Canvas(str(tmp_path / "scratch.pdf"), pagesize=LETTER)
    long_reason = (
        "Potential formalization risk (High tier): nested_conditional: this "
        "segment contains multiple nested conditional clauses whose "
        "antecedents and consequents interact in ways that commonly get "
        "flattened or mis-scoped during formalization into propositional "
        "logic, and additionally negation_scope: the negation in this claim "
        "may take scope over either the whole conditional or only its "
        "consequent " + "verylongunbreakabletoken" * 6
    )
    max_width = LETTER[0] - 2 * 72
    wrapped = pdf_generation._wrap_line(c, long_reason, "Helvetica", 12, max_width)
    assert len(wrapped) > 1, "long line was not wrapped at all"
    for line in wrapped[:-1]:
        # every line except possibly a single-oversized-word line must fit
        if " " in line:
            assert c.stringWidth(line, "Helvetica", 12) <= max_width
    # nothing silently dropped: rejoining reproduces every original word
    assert " ".join(wrapped).split() == long_reason.split()


# ---------------------------------------------------------------------------
# Reconstruction: unformalized claims explicitly annotated, never omitted
# ---------------------------------------------------------------------------

def test_reconstruction_annotates_unformalized_claims():
    axioms = [
        {"claim_index": 0, "segment_index": 0, "english": "A good claim.",
         "formal": "P(x)", "risk_tier": "Low", "risk_flags": []},
        {"claim_index": 1, "segment_index": 1, "english": "A failed claim.",
         "formal": None, "risk_tier": "Unformalized", "risk_flags": []},
    ]
    logic_text, english_text = generate_reconstructions(axioms, mode="logic")
    assert "A failed claim." in logic_text  # not omitted
    assert UNFORMALIZED_NOTE in logic_text
    assert "Unformalized" in logic_text
    assert "A failed claim." in english_text


def test_reconstruction_annotates_unformalized_claims_both_mode():
    axioms = [
        {"claim_index": 0, "segment_index": 0, "english": "A failed claim.",
         "formal_logic": None, "formal_english": None,
         "risk_tier": "Unformalized", "risk_flags": []},
    ]
    logic_text, _ = generate_reconstructions(axioms, mode="both")
    assert "A failed claim." in logic_text
    assert UNFORMALIZED_NOTE in logic_text


# ---------------------------------------------------------------------------
# 2. Concurrency: two simultaneous formalize_file calls must not interfere
# ---------------------------------------------------------------------------

DOC_A = [
    "AlphaCats are always animals.",
    "AlphaDogs are always animals.",
    "AlphaBirds are always animals.",
]
DOC_B = [
    "BetaRocks are never animals.",
    "BetaTrees are never animals.",
    "BetaClouds are never animals.",
]


def test_concurrent_formalize_requests_do_not_interfere(monkeypatch, tmp_path):
    """Two formalize_file calls run concurrently (interleaved via a barrier
    at every stubbed LLM call) against different documents. Each call's
    scratch file, final_data.json, and PDF must be its own: distinct output
    paths, axioms matching its own document only, PDF containing only its
    own content."""
    pdf_a = _make_pdf(tmp_path / "doc_a.pdf", DOC_A)
    pdf_b = _make_pdf(tmp_path / "doc_b.pdf", DOC_B)
    out_dir = str(tmp_path / "out")

    # Reusable 2-party barrier: each stubbed LLM call waits for the other
    # request to arrive at the same phase, forcing genuine interleaving of
    # the scratch-file writes and output writes. Timeout + broken-barrier
    # tolerance so an asymmetric call count can never deadlock the test.
    barrier = threading.Barrier(2)

    def _sync():
        try:
            barrier.wait(timeout=5)
        except threading.BrokenBarrierError:
            pass

    def fake_extraction(prompt, *args, **kwargs):
        _sync()
        seg_idx = int(re.search(r"Segment index: (\d+)", prompt).group(1))
        sentence = re.search(r'Segment text: "(.*)"', prompt, re.DOTALL).group(1).strip()
        return FakeResponse(json.dumps(
            {"segment_index": seg_idx, "claims": [sentence]}))

    def fake_formalization(prompt, *args, **kwargs):
        _sync()
        # Distinguishable per call: the formal string encodes which document
        # the claim came from, derived from the prompt itself.
        axioms = []
        for m in re.finditer(r"\(claim_index (\d+)\) (.+)", prompt):
            idx, english = int(m.group(1)), m.group(2).strip()
            token = "ALPHA" if "Alpha" in english else "BETA"
            axioms.append({"claim_index": idx, "formal": f"{token}_{idx}(x)"})
        return FakeResponse(json.dumps({"axioms": axioms}))

    monkeypatch.setattr(response_parsing, "generate_response", fake_extraction)
    monkeypatch.setattr(logic_formalization, "generate_response", fake_formalization)

    def run(path):
        return main.formalize_file(path, "logic", use_parallel=False,
                                   output_dir=out_dir,
                                   chunking_mode="propositional")

    with ThreadPoolExecutor(max_workers=2) as pool:
        fut_a = pool.submit(run, pdf_a)
        fut_b = pool.submit(run, pdf_b)
        result_a = fut_a.result(timeout=60)
        result_b = fut_b.result(timeout=60)

    # Distinct, existing output files
    assert result_a["output_pdf"] != result_b["output_pdf"]
    assert os.path.exists(result_a["output_pdf"])
    assert os.path.exists(result_b["output_pdf"])

    # Each result contains exactly its own document's claims -- nothing
    # missing, nothing cross-contaminated from the other request.
    def check(result, own_sentences, own_token, other_token):
        englishes = sorted(ax["english"] for ax in result["axioms"])
        assert englishes == sorted(own_sentences)
        for ax in result["axioms"]:
            assert ax["formal"] is not None
            assert own_token in ax["formal"]
            assert other_token not in ax["formal"]
        assert other_token.capitalize() not in result["english_reconstruction"]

    check(result_a, DOC_A, "ALPHA", "BETA")
    check(result_b, DOC_B, "BETA", "ALPHA")

    # The PDFs on disk are likewise uncorrupted and unmixed.
    text_a = extract_text_from_pdf(result_a["output_pdf"])
    text_b = extract_text_from_pdf(result_b["output_pdf"])
    assert "AlphaCats" in text_a and "BetaRocks" not in text_a
    assert "BetaRocks" in text_b and "AlphaCats" not in text_b

    # No leftover shared scratch files in the output dir: only the two
    # requests' uuid-scoped artifacts remain.
    leftovers = [f for f in os.listdir(out_dir) if f.startswith("claims_")]
    assert leftovers == [], f"scratch files leaked: {leftovers}"
    assert not os.path.exists(os.path.join(out_dir, "final_data.json")), (
        "a fixed shared final_data.json was written")
