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
    if tier == "Unformalized":
        # Distinct wording on purpose: "(no flags)" reads like "nothing to
        # worry about" when it actually means "we have no formal string to
        # check at all" -- a different and more urgent situation than a
        # Low-risk claim that was successfully formalized cleanly.
        return "    Risk tier: Unformalized (no formal representation was produced for this claim)"
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
            # Previously: `if not formal_logic and not formal_english: continue`
            # -- this silently dropped every claim formalize_claims() marked
            # as unformalized (formal_logic=None, formal_english=None; see
            # logic_formalization.py's _reconcile_batch) from this section
            # entirely. The claim still appeared in the English reconstruction
            # further down with no indication anything had failed, and
            # risk_triage.py's "Unformalized" tier (added specifically to make
            # this visible) never actually got printed anywhere, since the
            # `continue` above ran before _risk_line() was ever reached for
            # these axioms. Now we still print the claim and its Unformalized
            # risk line, just without a Logic:/English formalization: line
            # under it, so a failed formalization is visible per-claim, not
            # just as a number in the PDF header's risk-tier summary.
            formal_lines.append(f"({seg}) {eng}")
            if formal_logic:
                formal_lines.append(f"    Logic: {formal_logic}")
            if formal_english:
                formal_lines.append(f"    English formalization: {formal_english}")
            if not formal_logic and not formal_english:
                formal_lines.append("    Formal: [not available -- formalization failed for this claim]")
        else:
            formal = ax.get("formal")
            # Same fix as above for the single-formal-field modes.
            formal_lines.append(f"({seg}) {eng}")
            if formal:
                formal_lines.append(f"    Formal: {formal}")
            else:
                formal_lines.append("    Formal: [not available -- formalization failed for this claim]")

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