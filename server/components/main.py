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

def save_to_json(data, filename="output_data.json"):
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)

def formalize_file(file_path, mode, use_parallel=True, max_workers=5):
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"File not found: {file_path}")

    print(f"Starting formalization of: {file_path}")
    print(f"Mode: {mode}")
    print(f"Parallel processing: {use_parallel} (max_workers: {max_workers})")
    
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
        parsed_data = extract_claims(segments, max_workers=max_workers)
    else:
        from components.response_parsing import extract_claims_sequential
        parsed_data = extract_claims_sequential(segments)

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
    annotate_axioms(formalized_data.get("axioms", []))
    risk_counts = {"High": 0, "Medium": 0, "Low": 0}
    for ax in formalized_data.get("axioms", []):
        tier = ax.get("risk_tier")
        if tier in risk_counts:
            risk_counts[tier] += 1

    # Save to JSON
    print("Saving results to JSON...")
    os.makedirs("outputs", exist_ok=True)
    json_output_path = os.path.join("outputs", "final_data.json")
    save_to_json(formalized_data, json_output_path)

    # Read final data
    with open(json_output_path, "r", encoding="utf-8") as f:
        final_data = json.load(f)

    # Generate reconstructions
    print("Generating reconstructions...")
    logic_text, english_text = generate_reconstructions(final_data["axioms"], mode)

    # Now generate the PDF with the Formalizability Index at the top
    print("Generating PDF output...")
    output_id = str(uuid.uuid4())
    pdf_output_path = os.path.join("outputs", f"{output_id}.pdf")
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