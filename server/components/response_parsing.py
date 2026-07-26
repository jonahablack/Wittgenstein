import os
import json
import re
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from api_call import generate_response

def _empty_result(seg_idx):
    return {"segment_index": seg_idx, "claims": []}


def _build_claim_extraction_prompt(seg_idx, sentence):
    """Single source of truth for this prompt -- process_single_segment and
    extract_claims_sequential used to each keep their own copy, which is
    exactly how the two paths could silently drift out of sync.

    Kept deliberately narrow (one yes/no decision, verbatim extraction) so
    the same sentence gets classified the same way run to run: the previous
    version asked the model to sort each sentence into one of four buckets
    (claims/arguments/examples/decorative), none of which but "claims" was
    ever read downstream (main.py only consumes item["claims"]) -- so a
    genuine claim landing in "arguments" or "examples" instead of "claims"
    on a given run silently dropped it from the pipeline with no error,
    which is the most likely cause of "sometimes isn't catching all the
    claims" and inconsistent claim counts between runs on the same
    document. Reducing this to a single decision, plus verbatim (not
    paraphrased) extraction, removes both axes of that variability.
    """
    return f"""
    You are identifying checkable factual/normative assertions in a single
    sentence of source text, for downstream formalization into logic.

    This segment is exactly one sentence. Decide: does it assert something
    that could in principle be true or false (a claim), as opposed to being
    a transition, rhetorical flourish, or purely illustrative aside with no
    independent assertion of its own?

    If yes, extract the claim(s) it contains, reproduced VERBATIM from the
    source sentence -- do not paraphrase, summarize, or rewrite. Most
    sentences contain exactly one claim; only split into multiple claims if
    the sentence conjoins two clearly independent assertions (e.g. joined by
    "and"/"but"). If the sentence asserts nothing checkable, return an empty
    list.

    Output strict JSON with exactly these keys: "segment_index", "claims"
    (a list of strings, verbatim from the source, possibly empty).
    Return only valid JSON. Do not include Markdown code fences or
    additional text.

    Segment index: {seg_idx}
    Segment text: "{sentence}"
    """


def extract_json_from_response(response_content):
    try:
        clean_content = re.sub(r'```json|```', '', response_content).strip()
        clean_content = clean_content.replace('```', '').strip()
        clean_content = clean_content.strip('`')
        json_match = re.search(r'{.*}', clean_content, re.DOTALL)
        if not json_match:
            print("Skipping: No valid JSON found in response.")
            return None
        return json.loads(json_match.group(0))
    except json.JSONDecodeError as e:
        print(f"Skipping JSON decoding error: {e}")
        return None

def append_response_to_file(response_content, filename):
    with open(filename, "a", encoding="utf-8") as f:
        f.write(response_content.strip() + "\n---END-OF-SEGMENT---\n")

def parse_combined_responses(filename):
    if not os.path.exists(filename):
        print(f"No combined response file found: {filename}")
        return []

    with open(filename, "r", encoding="utf-8") as f:
        content = f.read()

    segments = content.split("---END-OF-SEGMENT---")
    parsed_data = []

    for segment in segments:
        segment = segment.strip()
        if not segment:
            continue

        clean_segment = re.sub(r'```json|```', '', segment).strip()
        clean_segment = clean_segment.replace('```', '').strip()
        clean_segment = clean_segment.strip('`')
        json_match = re.search(r'{.*}', clean_segment, re.DOTALL)
        if not json_match:
            print("Skipping: No valid JSON found in a segment.")
            parsed_data.append(_empty_result(None))
            continue

        try:
            data = json.loads(json_match.group(0))
            parsed_data.append(data)
        except json.JSONDecodeError as e:
            print(f"Skipping JSON decoding error: {e}")
            parsed_data.append(_empty_result(None))

    return parsed_data

def process_single_segment(segment_data):
    """Process a single segment and return the result"""
    seg_idx, sentence = segment_data

    prompt = _build_claim_extraction_prompt(seg_idx, sentence)

    response = generate_response(prompt)
    if not response or not hasattr(response, "content"):
        print(f"Failed to get response for segment {seg_idx}, using empty data")
        return _empty_result(seg_idx)

    # Parse the response content
    try:
        clean_content = re.sub(r'```json|```', '', response.content).strip()
        clean_content = clean_content.replace('```', '').strip()
        clean_content = clean_content.strip('`')
        json_match = re.search(r'{.*}', clean_content, re.DOTALL)
        if json_match:
            return json.loads(json_match.group(0))
        else:
            print(f"No valid JSON found for segment {seg_idx}")
            return _empty_result(seg_idx)
    except json.JSONDecodeError as e:
        print(f"JSON decoding error for segment {seg_idx}: {e}")
        return _empty_result(seg_idx)

def extract_claims(segments, output_file=None, max_workers=5, scratch_dir=None):
    """
    output_file: if not given, a fresh uuid-named scratch file is created
    (in `scratch_dir` if given, else the current working directory) instead
    of the previous hardcoded "all_responses.txt". A shared, hardcoded
    filename means two concurrent /formalize requests (two browser tabs,
    two users, or overlapping requests under a threaded server) delete and
    rewrite each other's scratch file mid-flight -- one request's claims
    silently corrupt or get read by another. Each call now gets its own
    file, and it's removed after use so scratch files don't accumulate.
    """
    import time

    owns_file = output_file is None
    if output_file is None:
        scratch_dir = scratch_dir or os.getcwd()
        os.makedirs(scratch_dir, exist_ok=True)
        output_file = os.path.join(scratch_dir, f"claims_{uuid.uuid4().hex}.txt")

    if os.path.exists(output_file):
        os.remove(output_file)

    total_segments = len(segments)
    print(f"Processing {total_segments} segments with {max_workers} parallel workers...")

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_segment = {
            executor.submit(process_single_segment, segment): segment
            for segment in segments
        }

        results = []
        completed = 0

        for future in as_completed(future_to_segment):
            segment = future_to_segment[future]
            try:
                result = future.result()
                results.append(result)
                completed += 1
                print(f"Completed {completed}/{total_segments} segments (index {segment[0]})")

                if completed < total_segments:
                    time.sleep(0.1)

            except Exception as e:
                print(f"Error processing segment {segment[0]}: {e}")
                results.append(_empty_result(segment[0]))
                completed += 1

    results.sort(key=lambda x: x.get("segment_index", 0))

    for result in results:
        append_response_to_file(json.dumps(result), filename=output_file)

    print(f"Parallel processing complete! Processed {len(results)} segments.")
    parsed = parse_combined_responses(filename=output_file)

    if owns_file:
        try:
            os.remove(output_file)
        except OSError:
            pass

    return parsed

def extract_claims_sequential(segments, output_file=None, scratch_dir=None):
    """Original sequential version - kept as fallback.

    Same per-call scratch file fix as extract_claims() -- see its docstring.
    """
    import time
    import random

    owns_file = output_file is None
    if output_file is None:
        scratch_dir = scratch_dir or os.getcwd()
        os.makedirs(scratch_dir, exist_ok=True)
        output_file = os.path.join(scratch_dir, f"claims_{uuid.uuid4().hex}.txt")

    if os.path.exists(output_file):
        os.remove(output_file)

    total_segments = len(segments)
    print(f"Processing {total_segments} segments sequentially...")

    for i, (seg_idx, sentence) in enumerate(segments):
        print(f"Processing segment {i+1}/{total_segments} (index {seg_idx})")

        prompt = _build_claim_extraction_prompt(seg_idx, sentence)

        response = generate_response(prompt)
        if not response or not hasattr(response, "content"):
            print(f"Failed to get response for segment {seg_idx}, using empty data")
            append_response_to_file(json.dumps(_empty_result(seg_idx)), filename=output_file)
            continue

        append_response_to_file(response.content, filename=output_file)

        if i < total_segments - 1:
            delay = 0.5 + random.uniform(0, 0.5)
            time.sleep(delay)

    parsed = parse_combined_responses(filename=output_file)

    if owns_file:
        try:
            os.remove(output_file)
        except OSError:
            pass

    return parsed