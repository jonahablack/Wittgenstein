import os
import json
import re
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from api_call import generate_response

def _empty_result(seg_idx):
    return {"segment_index": seg_idx, "claims": []}


def _build_claim_extraction_prompt(seg_idx, sentence):
    """Single source of truth for the "propositional"-mode prompt --
    process_single_segment and extract_claims_sequential used to each keep
    their own copy, which is exactly how the two paths could silently
    drift out of sync.

    PROPOSITIONAL DECOMPOSITION (Chen et al.): the criteria below are a
    close conceptual implementation, via prompting, of the propositional-
    decomposition criteria stated in Chen et al. ("Dense X Retrieval: What
    Retrieval Granularity Should We Use?"): each extracted claim should be
    (1) ATOMIC -- exactly one distinct assertion, not further divisible;
    (2) SELF-CONTAINED -- pronouns/references resolved where the sentence
    itself provides the antecedent, so the claim is interpretable out of
    context; (3) VERBATIM where possible -- the source's own wording,
    deviating only as far as (1) and (2) require. This is NOT a
    reproduction of their fine-tuned Propositionizer model, and it is
    deliberately NOT tuned or benchmarked for retrieval quality: chunking
    here is a formalization pre-processing step, not a retrieval-quality
    contribution. No retrieval-benchmark comparison is made and none
    should be attempted; do not "improve" this prompt against a retrieval
    metric. (For the plain fixed-size baseline, see extract_passages.)

    Kept deliberately narrow (one yes/no decision, then decomposition of
    a single sentence) so the same sentence gets classified the same way
    run to run: the previous version asked the model to sort each sentence
    into one of four buckets (claims/arguments/examples/decorative), none
    of which but "claims" was ever read downstream (main.py only consumes
    item["claims"]) -- so a genuine claim landing in "arguments" or
    "examples" instead of "claims" on a given run silently dropped it from
    the pipeline with no error, which is the most likely cause of
    "sometimes isn't catching all the claims" and inconsistent claim
    counts between runs on the same document. Reducing this to a single
    decision, plus verbatim-where-possible extraction, removes both axes
    of that variability.
    """
    return f"""
    You are decomposing a single sentence of source text into atomic,
    self-contained claims (checkable factual/normative assertions), for
    downstream formalization into logic.

    This segment is exactly one sentence. First decide: does it assert
    anything that could in principle be true or false (a claim), as
    opposed to being a transition, rhetorical flourish, or purely
    illustrative aside with no independent assertion of its own? If it
    asserts nothing checkable, return an empty list of claims.

    If it does assert something, decompose it into claims using exactly
    these criteria:
    1. ATOMIC: each extracted claim expresses exactly ONE assertion. If
       the sentence conjoins or embeds several clearly distinct
       assertions, output one claim per assertion. Do not merge separate
       assertions into one claim, and do not split a single assertion
       into fragments that cannot stand alone.
    2. SELF-CONTAINED: each claim must be interpretable on its own. Where
       THIS SENTENCE itself provides the antecedent for a pronoun or
       shorthand reference, substitute the antecedent into the claim
       (e.g. "it" -> the thing named earlier in the sentence). If the
       antecedent is NOT present in this sentence, leave the reference
       exactly as written -- never guess or invent one.
    3. VERBATIM WHERE POSSIBLE: keep the source's own wording. Deviate
       from the exact words only as far as criteria 1 and 2 require
       (splitting a conjunction, substituting an in-sentence antecedent);
       never paraphrase, summarize, embellish, or "clean up" the
       language.

    Output strict JSON with exactly these keys: "segment_index", "claims"
    (a list of strings, possibly empty).
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


def extract_passages(segments, passage_size=5):
    """"passage"-mode chunking: fixed-size windowed passages, the common
    industry baseline. Purely mechanical -- consecutive non-overlapping
    windows of `passage_size` sentences over the already-segmented text,
    with NO LLM call of any kind. Each passage becomes one "claim" record
    downstream, so the two chunking modes produce an identical output
    shape and everything after extraction (formalization, reconciliation,
    risk triage) is mode-agnostic.

    Each unit's segment_index is the index of the passage's FIRST
    sentence, so main.py's segment_lookup (segment_index -> sentence)
    still resolves for risk_triage.py's segment-level checks.

    Returns the same per-unit shape as extract_claims():
    [{"segment_index": <first sentence idx>, "claims": [<passage text>]}]
    """
    passage_size = max(1, int(passage_size))
    unit_results = []
    for i in range(0, len(segments), passage_size):
        window = segments[i:i + passage_size]
        if not window:
            continue
        first_idx = window[0][0]
        passage = " ".join(sentence for _, sentence in window).strip()
        unit_results.append({
            "segment_index": first_idx,
            "claims": [passage] if passage else [],
        })
    return unit_results


def build_claim_records(unit_results):
    """Flatten per-unit extraction output ({"segment_index", "claims"})
    into flat claim records, assigning each claim its globally unique
    claim_index HERE, at extraction time.

    claim_index used to be assigned later, inside formalize_claims() --
    which worked, but meant the identity of a claim only existed once
    formalization started, and anything between extraction and
    formalization had no stable key to refer to a claim by.
    formalize_claims() now respects a pre-assigned claim_index (via
    setdefault) instead of overwriting it, and this function is the one
    place indices are minted: 0..N-1 in extraction order, so the
    reconciliation invariant (output axiom count == input claim count,
    keyed by claim_index) is anchored at the earliest point a claim
    exists.
    """
    records = []
    for item in unit_results:
        seg_idx = item.get("segment_index")
        if seg_idx is None:
            continue
        for claim in item.get("claims", []):
            records.append({
                "claim_index": len(records),
                "segment_index": seg_idx,
                "english": claim,
            })
    return records


def extract_claim_records(segments, chunking_mode="propositional",
                          use_parallel=True, max_workers=5,
                          scratch_dir=None, passage_size=5):
    """Unified extraction entry point over the two chunking modes.

    chunking_mode:
      - "propositional" (default): LLM decomposition of each sentence
        into atomic, self-contained claims (see
        _build_claim_extraction_prompt for the criteria and for the
        Chen et al. scope note -- conceptual implementation of their
        stated criteria via prompting, not a retrieval-tuned system).
      - "passage": fixed-size sentence windows, no LLM call at all
        (see extract_passages).

    Returns (claim_records, unit_results):
      - claim_records: flat list of {"claim_index", "segment_index",
        "english"} dicts -- identical shape for both modes, so
        everything downstream is chunking-mode-agnostic.
      - unit_results: the per-unit {"segment_index", "claims"} list, for
        per-unit accounting (e.g. main.py's formalizability index).
    """
    if chunking_mode == "passage":
        unit_results = extract_passages(segments, passage_size=passage_size)
    elif chunking_mode == "propositional":
        if use_parallel:
            unit_results = extract_claims(
                segments, max_workers=max_workers, scratch_dir=scratch_dir)
        else:
            unit_results = extract_claims_sequential(
                segments, scratch_dir=scratch_dir)
    else:
        raise ValueError(
            f"Unknown chunking_mode: {chunking_mode!r} "
            "(expected 'propositional' or 'passage')"
        )
    return build_claim_records(unit_results), unit_results


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