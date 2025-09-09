import os
import json
import re
import asyncio
import aiohttp
from concurrent.futures import ThreadPoolExecutor, as_completed
from api_call import generate_response

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
    except (json.JSONDecodeError, Exception) as e:
        print(f"Skipping JSON decoding error: {e}")
        return None

def append_response_to_file(response_content, filename):
    with open(filename, "a", encoding="utf-8") as f:
        f.write(response_content.strip() + "\n---END-OF-SEGMENT---\n")

def parse_combined_responses(filename="all_responses.txt"):
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
            parsed_data.append({
                "segment_index": None,
                "claims": [],
                "arguments": [],
                "examples": [],
                "decorative": []
            })
            continue

        try:
            data = json.loads(json_match.group(0))
            parsed_data.append(data)
        except json.JSONDecodeError as e:
            print(f"Skipping JSON decoding error: {e}")
            parsed_data.append({
                "segment_index": None,
                "claims": [],
                "arguments": [],
                "examples": [],
                "decorative": []
            })

    return parsed_data

def process_single_segment(segment_data):
    """Process a single segment and return the result"""
    seg_idx, sentence = segment_data
    
    prompt = f"""
    You are an assistant specialized in philosophy and logic.
    You will receive a segment of a philosophical text along with a segment index.
    Identify:
    1. Core philosophical claims or axioms.
    2. Supporting arguments.
    3. Illustrative examples.
    4. Decorative or rhetorical language.

    Output a JSON with keys: "segment_index", "claims", "arguments", "examples", "decorative".

    Segment index: {seg_idx}
    Segment text: "{sentence}"
    """
    
    response = generate_response(prompt)
    if not response or not hasattr(response, "content"):
        print(f"Failed to get response for segment {seg_idx}, using empty data")
        return {
            "segment_index": seg_idx,
            "claims": [],
            "arguments": [],
            "examples": [],
            "decorative": []
        }
    
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
            return {
                "segment_index": seg_idx,
                "claims": [],
                "arguments": [],
                "examples": [],
                "decorative": []
            }
    except json.JSONDecodeError as e:
        print(f"JSON decoding error for segment {seg_idx}: {e}")
        return {
            "segment_index": seg_idx,
            "claims": [],
            "arguments": [],
            "examples": [],
            "decorative": []
        }

def extract_claims(segments, output_file="all_responses.txt", max_workers=5):
    import time
    import random
    
    if os.path.exists(output_file):
        os.remove(output_file)

    total_segments = len(segments)
    print(f"Processing {total_segments} segments with {max_workers} parallel workers...")
    
    # Use ThreadPoolExecutor for parallel processing
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        # Submit all tasks
        future_to_segment = {
            executor.submit(process_single_segment, segment): segment 
            for segment in segments
        }
        
        # Collect results as they complete
        results = []
        completed = 0
        
        for future in as_completed(future_to_segment):
            segment = future_to_segment[future]
            try:
                result = future.result()
                results.append(result)
                completed += 1
                print(f"Completed {completed}/{total_segments} segments (index {segment[0]})")
                
                # Add small delay to avoid overwhelming the API
                if completed < total_segments:
                    time.sleep(0.1)  # Small delay between completions
                    
            except Exception as e:
                print(f"Error processing segment {segment[0]}: {e}")
                # Add empty result for failed segment
                results.append({
                    "segment_index": segment[0],
                    "claims": [],
                    "arguments": [],
                    "examples": [],
                    "decorative": []
                })
                completed += 1
    
    # Sort results by segment index to maintain order
    results.sort(key=lambda x: x.get("segment_index", 0))
    
    # Write all results to file
    for result in results:
        append_response_to_file(json.dumps(result), filename=output_file)
    
    print(f"Parallel processing complete! Processed {len(results)} segments.")
    return parse_combined_responses(filename=output_file)

def extract_claims_sequential(segments, output_file="all_responses.txt"):
    """Original sequential version - kept as fallback"""
    import time
    import random
    
    if os.path.exists(output_file):
        os.remove(output_file)

    total_segments = len(segments)
    print(f"Processing {total_segments} segments sequentially...")
    
    for i, (seg_idx, sentence) in enumerate(segments):
        print(f"Processing segment {i+1}/{total_segments} (index {seg_idx})")
        
        prompt = f"""
        You are an assistant specialized in philosophy and logic.
        You will receive a segment of a philosophical text along with a segment index.
        Identify:
        1. Core philosophical claims or axioms.
        2. Supporting arguments.
        3. Illustrative examples.
        4. Decorative or rhetorical language.

        Output a JSON with keys: "segment_index", "claims", "arguments", "examples", "decorative".

        Segment index: {seg_idx}
        Segment text: "{sentence}"
        """
        
        response = generate_response(prompt)
        if not response or not hasattr(response, "content"):
            print(f"Failed to get response for segment {seg_idx}, using empty data")
            append_response_to_file(json.dumps({
                "segment_index": seg_idx,
                "claims": [],
                "arguments": [],
                "examples": [],
                "decorative": []
            }), filename=output_file)
            continue

        append_response_to_file(response.content, filename=output_file)
        
        # Add small delay between requests to avoid rate limiting
        if i < total_segments - 1:  # Don't delay after the last segment
            delay = 0.5 + random.uniform(0, 0.5)  # 0.5-1.0 seconds
            time.sleep(delay)

    return parse_combined_responses(filename=output_file)
