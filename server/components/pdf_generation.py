import os
import uuid
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import LETTER
from reportlab.lib.units import inch

def generate_output_pdf(
    logic_text, english_text, output_path, formalizability_index, total_segments, formalizable_segments
):
    c = canvas.Canvas(output_path, pagesize=LETTER)
    width, height = LETTER

    c.setFont("Helvetica", 12)
    margin = 1 * inch
    y = height - margin

    # Add header and Formalizability Index summary
    c.drawString(margin, y, "Formalized Axioms and Analysis")
    y -= 0.5 * inch
    c.drawString(margin, y, f"Formalizability Index: {formalizability_index:.2f}")
    y -= 0.3 * inch
    c.drawString(margin, y, f"Total Segments: {total_segments}")
    y -= 0.3 * inch
    c.drawString(margin, y, f"Formalizable Segments: {formalizable_segments}")
    y -= 0.5 * inch

    # Add reconstructed logic text
    c.drawString(margin, y, "Logic Reconstruction:")
    y -= 0.3 * inch
    for line in logic_text.split("\n"):
        c.drawString(margin, y, line)
        y -= 0.2 * inch
        if y < margin:
            c.showPage()
            c.setFont("Helvetica", 12)
            y = height - margin

    # Add reconstructed English text
    c.drawString(margin, y, "English Reconstruction:")
    y -= 0.3 * inch
    for line in english_text.split("\n"):
        c.drawString(margin, y, line)
        y -= 0.2 * inch
        if y < margin:
            c.showPage()
            c.setFont("Helvetica", 12)
            y = height - margin

    c.save()