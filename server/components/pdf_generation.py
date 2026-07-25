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


def generate_output_pdf(
    logic_text, english_text, output_path, formalizability_index, total_segments,
    formalizable_segments, risk_counts=None,
):
    c = canvas.Canvas(output_path, pagesize=LETTER)
    width, height = LETTER

    c.setFont("Helvetica", 12)
    margin = 1 * inch
    y = height - margin

    def draw_line(line):
        nonlocal y
        c.drawString(margin, y, _pdf_safe(line))
        y -= 0.2 * inch
        if y < margin:
            c.showPage()
            c.setFont("Helvetica", 12)
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
            c.setFont("Helvetica", 12)
            y = height - margin

    if has_english:
        for line in english_text.split("\n"):
            draw_line(line)

    c.save()
