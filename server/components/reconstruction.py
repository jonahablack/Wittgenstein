def generate_reconstructions(axioms):
    # Sort axioms by segment_index
    axioms = sorted(axioms, key=lambda x: x.get("segment_index", 0))

    # Build logic-based reconstruction text
    logic_lines = []
    # Only add a title if we have actual axioms
    if any(ax.get("formal", "N/A") != "N/A" for ax in axioms):
        logic_lines.append("=== Formal Logic Reconstruction ===")
        logic_lines.append("")  # Blank line after title
        for ax in axioms:
            seg = ax.get("segment_index", "N/A")
            eng = ax.get("english", "N/A")
            form = ax.get("formal", "N/A")
            # Only print if we have a real formal statement
            if form != "N/A":
                logic_lines.append(f"({seg}) {eng}")
                logic_lines.append(f"    Formal: {form}")
                logic_lines.append("")
    logic_text = "\n".join([line for line in logic_lines if line.strip()])

    # Build English-based reconstruction text
    # If there are English claims, present them
    english_lines = []
    if any(ax.get("english", "N/A") != "N/A" for ax in axioms):
        english_lines.append("=== English Reconstruction of the Argument ===")
        english_lines.append("")  # Blank line after title
        current_seg = None
        for ax in axioms:
            eng = ax.get("english", "N/A")
            seg_idx = ax.get("segment_index", None)
            if eng != "N/A":
                # Add a small separation when segment index changes to indicate a new point
                if current_seg is not None and seg_idx is not None and seg_idx != current_seg:
                    english_lines.append("")
                english_lines.append(f"- {eng}")
                current_seg = seg_idx
        english_lines.append("")
    english_text = "\n".join([line for line in english_lines if line.strip()])

    return logic_text.strip(), english_text.strip()


def generate_output_pdf(logic_text, english_text, output_path):
    from reportlab.pdfgen import canvas
    from reportlab.lib.pagesizes import LETTER
    from reportlab.lib.units import inch

    # Ensure all arrows are displayed correctly
    logic_text = logic_text.replace('■ightarrow', '→')
    logic_text = logic_text.replace('\\rightarrow', '→')
    english_text = english_text.replace('■ightarrow', '→')
    english_text = english_text.replace('\\rightarrow', '→')

    c = canvas.Canvas(output_path, pagesize=LETTER)
    width, height = LETTER
    c.setFont("Helvetica", 12)
    margin = 1 * inch
    y = height - margin

    # If neither logic nor English sections have content, we can title the whole PDF differently
    has_logic = bool(logic_text.strip())
    has_english = bool(english_text.strip())

    if not has_logic and not has_english:
        # No content at all
        c.drawString(margin, y, "No formalized content found.")
        c.save()
        return

    # Title for the PDF
    c.drawString(margin, y, "Formalized Argument Reconstructions")
    y -= 0.5 * inch

    # Draw logic section if available
    if has_logic:
        logic_lines = logic_text.split('\n')
        for line in logic_lines:
            if y < margin:
                c.showPage()
                c.setFont("Helvetica", 12)
                y = height - margin
            c.drawString(margin, y, line)
            y -= 0.3 * inch

        # Add spacing before English section
        y -= 0.5 * inch
        if y < margin:
            c.showPage()
            c.setFont("Helvetica", 12)
            y = height - margin

    # Draw English section if available
    if has_english:
        english_lines = english_text.split('\n')
        for line in english_lines:
            if y < margin:
                c.showPage()
                c.setFont("Helvetica", 12)
                y = height - margin
            c.drawString(margin, y, line)
            y -= 0.3 * inch

    c.save()
