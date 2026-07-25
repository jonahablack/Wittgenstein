_SECTION_TITLES = {
    "logic": "=== Formal Logic Reconstruction ===",
    "english": "=== English Formalization Reconstruction ===",
    "both": "=== Formal Logic + English Formalization Reconstruction ===",
}


def _risk_line(ax):
    tier = ax.get("risk_tier")
    if not tier:
        return None
    flags = ax.get("risk_flags") or []
    if not flags:
        return f"    Risk tier: {tier} (no flags)"
    reasons = "; ".join(f"{f['type']}: {f['reason']}" for f in flags)
    return f"    Potential formalization risk ({tier} tier): {reasons}"


def generate_reconstructions(axioms, mode="logic"):
    # Sort axioms by segment_index
    axioms = sorted(axioms, key=lambda x: x.get("segment_index", 0))

    formal_lines = []
    for ax in axioms:
        seg = ax.get("segment_index", "N/A")
        eng = ax.get("english", "N/A")

        if mode == "both":
            formal_logic = ax.get("formal_logic")
            formal_english = ax.get("formal_english")
            if not formal_logic and not formal_english:
                continue
            formal_lines.append(f"({seg}) {eng}")
            if formal_logic:
                formal_lines.append(f"    Logic: {formal_logic}")
            if formal_english:
                formal_lines.append(f"    English formalization: {formal_english}")
        else:
            formal = ax.get("formal")
            if not formal:
                continue
            formal_lines.append(f"({seg}) {eng}")
            formal_lines.append(f"    Formal: {formal}")

        risk_line = _risk_line(ax)
        if risk_line:
            formal_lines.append(risk_line)
        formal_lines.append("")

    logic_text = ""
    if formal_lines:
        title = _SECTION_TITLES.get(mode, _SECTION_TITLES["logic"])
        logic_text = "\n".join([title, ""] + formal_lines).strip()

    # Build English-based reconstruction text (the claims themselves, in the
    # source's own words -- independent of formalization mode)
    english_lines = []
    if any(ax.get("english", "N/A") != "N/A" for ax in axioms):
        english_lines.append("=== English Reconstruction of the Argument ===")
        english_lines.append("")
        current_seg = None
        for ax in axioms:
            eng = ax.get("english", "N/A")
            seg_idx = ax.get("segment_index", None)
            if eng != "N/A":
                if current_seg is not None and seg_idx is not None and seg_idx != current_seg:
                    english_lines.append("")
                english_lines.append(f"- {eng}")
                current_seg = seg_idx
    english_text = "\n".join(english_lines).strip()

    return logic_text, english_text
