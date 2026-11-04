"""Regression tests for text_extraction.py: a PDF page whose
extract_text() returns None (scanned/image page, odd encoding, malformed
content stream) is logged and skipped -- it must never raise and kill the
whole upload."""

import pytest

from components import text_extraction


class _FakePage:
    def __init__(self, text):
        self._text = text

    def extract_text(self):
        return self._text


class _FakeReader:
    def __init__(self, _fileobj):
        self.pages = [
            _FakePage("First page text."),
            _FakePage(None),  # the crash case: image/scan page
            _FakePage("Third page text."),
        ]


def test_none_text_page_skipped_not_raised(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(text_extraction.PyPDF2, "PdfReader", _FakeReader)
    fake_pdf = tmp_path / "doc.pdf"
    fake_pdf.write_bytes(b"%PDF-1.4 fake")

    text = text_extraction.extract_text_from_pdf(str(fake_pdf))

    assert "First page text." in text
    assert "Third page text." in text
    # the skip is logged, so a truncated extraction stays debuggable
    out = capsys.readouterr().out
    assert "page 1" in out and "skipping" in out


def test_all_pages_none_returns_empty_string(monkeypatch, tmp_path):
    class _AllNoneReader:
        def __init__(self, _f):
            self.pages = [_FakePage(None), _FakePage(None)]

    monkeypatch.setattr(text_extraction.PyPDF2, "PdfReader", _AllNoneReader)
    fake_pdf = tmp_path / "doc.pdf"
    fake_pdf.write_bytes(b"%PDF-1.4 fake")

    assert text_extraction.extract_text_from_pdf(str(fake_pdf)) == ""


def test_segment_text_returns_indexed_sentences():
    segments = text_extraction.segment_text("All swans are white. Socrates is mortal.")
    assert segments == [(0, "All swans are white."), (1, "Socrates is mortal.")]
