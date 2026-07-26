import os
import json
import uuid
import hashlib

from components.text_extraction import extract_text_from_pdf, extract_text_from_epub, segment_text
from components.response_parsing import extract_claims
from components.logic_formalization import formalize_claims, check_contradictions
from components.pdf_generation import generate_output_pdf
from components.reconstruction import generate_reconstructions
from components.risk_triage import annotate_axioms

def save_to_json(data, filename):
    os.makedirs(os.path.dirname(filename), exist_ok=True)
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)

def formalize_file(file_path, mode, use_parallel=True, max_workers=5, output_dir=None):
    """
    output_dir: base directory for this call's scratch and output files
    (claim-extraction scratch file, final_data.json, output PDF). Defaults
    to a relative "outputs" directory (as before) if not given, but the
    Flask app should pass its own OUTPUT_DIR (which respects the DATA_DIR
    env var for a persistent disk on Render) so files land in one
    consistent, intentional location instead of wherever the process
    happened to be launched from.

    Every artifact this call writes is now scoped under a request-unique
    output_id (generated up front, not just for the final PDF as before).
    Previously "outputs/final_data.json" and the claims-extraction scratch
    file used the same hardcoded name on every call; two /formalize
    requests running concurrently (two tabs, two users, or overlapping
    requests under a threaded server) would delete and overwrite each
    other's file mid-flight, and one request could read back another
    request's claims/axioms. Scoping every intermediate filename to this
    call's own output_id removes that race entirely.
    """
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"File not found: {file_path}")

    output_id = str(uuid.uuid4())
    output_dir = output_dir or "outputs"
    os.makedirs(output_dir, exist_ok=True)

    print(f"Starting formalization of: {file_path}")
    print(f"Mode: {mode}")
    print(f"Parallel processing: {use_parallel} (max_workers: {max_workers})")
    print(f"Request id: {output_id}")

    ext = os.path.splitext(file_path)[1].lower()
    print("Extracting text from file...")
    if ext == ".pdf":
        text = extract_text_from_pdf(file_path)
    elif ext == ".epub":
        text = extract_text_from_epub(file_path)
    else:
        raise ValueError("Unsupported file format")

    print(f"Text extracted. Length: {len(text)} characters")

    segments = segment_text(text)
    print(f"Text segmented into {len(segments)} segments")

    print("Extracting claims from segments...")
    if use_parallel:
        parsed_data = extract_claims(segments, max_workers=max_workers, scratch_dir=output_dir)
    else:
        from components.response_parsing import extract_claims_sequential
        parsed_data = extract_claims_sequential(segments, scratch_dir=output_dir)

    # Gather all claims
    print("Gathering all claims...")
    all_claims_data = []
    for item in parsed_data:
        seg_idx = item.get("segment_index")
        if seg_idx is not None:
            for claim in item.get("claims", []):
                all_claims_data.append({"segment_index": seg_idx, "english": claim})

    print(f"Found {len(all_claims_data)} total claims")

    # Formalize claims
    print("Starting formalization of claims...")
    formalized_data = formalize_claims(all_claims_data, mode, max_workers=max_workers)

    warning = None
    if all_claims_data and not formalized_data.get("axioms"):
        warning = (
            f"Found {len(all_claims_data)} claims in the source text, but the "
            "formalization model's responses could not be parsed into any "
            "axioms. Check the server logs for the raw model output."
        )
        print(f"WARNING: {warning}")
    else:
        unformalized_count = formalized_data.get("unformalized_count", 0)
        total_axioms = len(formalized_data.get("axioms", []))
        if unformalized_count:
            warning = (
                f"{unformalized_count} of {total_axioms} extracted claims could "
                "not be formalized and are shown with no formal representation "
                "(tagged \"Unformalized\"). This can happen when the model "
                "merges, skips, or fails to parse a specific claim."
            )
            print(f"WARNING: {warning}")

    # compute Formalizability Index
    print("Computing formalizability index...")
    total_segments = len(parsed_data)
    formalizable_segments = sum(1 for item in parsed_data if item.get("claims"))
    formalizability_index = (
        formalizable_segments / total_segments if total_segments > 0 else 0
    )
    print(f"Formalizability Index: {formalizability_index:.2f} ({formalizable_segments}/{total_segments} segments)")

    # Check contradictions
    print("Checking for contradictions...")
    contradiction_found = check_contradictions(formalized_data.get("axioms", []))
    print(f"Contradictions found: {contradiction_found}")

    base_url = file_path
    for ax in formalized_data.get("axioms", []):
        seg_idx = ax["segment_index"]
        ax["source"] = f"{base_url}#segment-{seg_idx}"
        ax["flag"] = "contradiction" if contradiction_found else "none"
        ax["id"] = hashlib.sha1(
            f"{seg_idx}|{ax.get('english', '')}|{ax.get('formal', '')}".encode("utf-8")
        ).hexdigest()[:12]

    # Risk-triage annotation (rule-based, legible reasons for reviewers)
    print("Computing risk-triage flags...")
    annotate_axioms(formalized_data.get("axioms", []), mode=mode)
    risk_counts = {"High": 0, "Medium": 0, "Low": 0, "Unformalized": 0}
    for ax in formalized_data.get("axioms", []):
        tier = ax.get("risk_tier")
        if tier in risk_counts:
            risk_counts[tier] += 1

    # Save to JSON -- filename scoped to this request's output_id, not a
    # fixed shared name (see docstring above for why that mattered).
    print("Saving results to JSON...")
    json_output_path = os.path.join(output_dir, f"{output_id}_final_data.json")
    save_to_json(formalized_data, json_output_path)

    # Read final data back
    with open(json_output_path, "r", encoding="utf-8") as f:
        final_data = json.load(f)

    # Generate reconstructions
    print("Generating reconstructions...")
    logic_text, english_text = generate_reconstructions(final_data["axioms"], mode)

    # Now generate the PDF with the Formalizability Index at the top
    print("Generating PDF output...")
    pdf_output_path = os.path.join(output_dir, f"{output_id}.pdf")
    generate_output_pdf(
        logic_text,
        english_text,
        pdf_output_path,
        formalizability_index,
        total_segments,
        formalizable_segments,
        risk_counts=risk_counts,
    )

    print(f"PDF generated: {pdf_output_path}")
    print("Formalization complete!")

    return {
        "axioms": final_data["axioms"],
        "output_pdf": pdf_output_path,
        "logic_reconstruction": logic_text,
        "english_reconstruction": english_text,
        "warning": warning,
    }