import os
import uuid
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import LETTER
from reportlab.lib.units import inch


def _pdf_safe(text):
    """Base14 PDF fonts only support Latin-1. Replace anything else instead of
    letting reportlab raise mid-render and silently produce a truncated PDF."""
    try:
        text.encode("latin-1")
        return text
    except UnicodeEncodeError:
        return text.encode("latin-1", errors="replace").decode("latin-1")


def _wrap_line(c, line, font_name, font_size, max_width):
    """Greedy word-wrap a single line to fit max_width, using actual glyph
    metrics for the given font/size rather than a fixed character count.

    Without this, canvas.drawString() draws the whole line unbroken -- any
    text past the page's right edge is drawn outside the page's visible
    area and is silently clipped by the viewer/printer with no ellipsis,
    no warning, and no indication anything is missing. This is what
    produced reason strings cut off mid-word ("...multiple cla") and,
    worse, entire additional flags on the same line vanishing past the
    page edge with no visible sign a second flag ever existed.
    """
    words = line.split(" ")
    wrapped = []
    current = ""
    for word in words:
        candidate = f"{current} {word}".strip()
        if c.stringWidth(candidate, font_name, font_size) <= max_width:
            current = candidate
        else:
            if current:
                wrapped.append(current)
            # A single word longer than max_width on its own still needs to
            # go somewhere; emit it as its own line rather than dropping it.
            current = word
    if current:
        wrapped.append(current)
    return wrapped or [""]


def generate_output_pdf(
    logic_text, english_text, output_path, formalizability_index, total_segments,
    formalizable_segments, risk_counts=None,
):
    c = canvas.Canvas(output_path, pagesize=LETTER)
    width, height = LETTER

    font_name = "Helvetica"
    font_size = 12
    c.setFont(font_name, font_size)
    margin = 1 * inch
    max_text_width = width - (2 * margin)
    y = height - margin

    def draw_line(line):
        nonlocal y
        safe_line = _pdf_safe(line)
        for wrapped_line in _wrap_line(c, safe_line, font_name, font_size, max_text_width):
            c.drawString(margin, y, wrapped_line)
            y -= 0.2 * inch
            if y < margin:
                c.showPage()
                c.setFont(font_name, font_size)
                y = height - margin

    # Add header and Formalizability Index summary
    draw_line("Formalized Axioms and Analysis")
    y -= 0.3 * inch
    draw_line(f"Formalizability Index: {formalizability_index:.2f}")
    draw_line(f"Total Segments: {total_segments}")
    draw_line(f"Formalizable Segments: {formalizable_segments}")
    if risk_counts:
        draw_line(
            f"Risk Tiers: High {risk_counts.get('High', 0)}, "
            f"Medium {risk_counts.get('Medium', 0)}, Low {risk_counts.get('Low', 0)}"
        )
    y -= 0.3 * inch

    has_logic = bool(logic_text.strip())
    has_english = bool(english_text.strip())

    if not has_logic and not has_english:
        draw_line("No formalized content found.")
        c.save()
        return

    if has_logic:
        for line in logic_text.split("\n"):
            draw_line(line)
        y -= 0.3 * inch
        if y < margin:
            c.showPage()
            c.setFont(font_name, font_size)
            y = height - margin

    if has_english:
        for line in english_text.split("\n"):
            draw_line(line)

    c.save()