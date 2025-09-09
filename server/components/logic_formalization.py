import json
import re
from sympy.logic.boolalg import sympify, simplify_logic

from api_call import generate_response

def formalize_claims(all_claims_data, mode, batch_size=50):
    mode_instructions = {
        "logic": "Convert the claims into formal logical propositions.",
        "english": "Convert the claims into structured, simplified English formalizations."
    }

    all_axioms = []
    total_claims = len(all_claims_data)
    
    print(f"Formalizing {total_claims} claims in batches of {batch_size}...")
    
    # Process claims in batches to avoid token limits
    for i in range(0, total_claims, batch_size):
        batch = all_claims_data[i:i + batch_size]
        batch_num = (i // batch_size) + 1
        total_batches = (total_claims + batch_size - 1) // batch_size
        
        print(f"Processing batch {batch_num}/{total_batches} ({len(batch)} claims)")
        
        formatted_claims = "\n".join([f"- (Index {c['segment_index']}) {c['english']}" for c in batch])

        prompt = f"""
        You are an assistant specialized in logic and formal reasoning.
        I will provide you with a list of English philosophical claims.
        For each claim:
        1. Provide the original English claim.
        2. {mode_instructions[mode]}
        3. Include the segment_index.

        Return a JSON with a "axioms" list. Each object: "segment_index", "english", "formal".
        Return only valid JSON. Do not include Markdown code fences or additional text.
        Input claims:
        {formatted_claims}
        """

        response = generate_response(prompt)
        if not response or not hasattr(response, "content"):
            print(f"Failed to get response for batch {batch_num}, skipping...")
            continue
            
        response_content = response.content.strip()
        response_content = re.sub(r'```json|```', '', response_content).strip()

        try:
            if response_content.startswith("{") or response_content.startswith("["):
                batch_data = json.loads(response_content)
                if "axioms" in batch_data:
                    all_axioms.extend(batch_data["axioms"])
                else:
                    print(f"Invalid response format for batch {batch_num}: {response_content}")
            else:
                print(f"Invalid response format for batch {batch_num}: {response_content}")
        except json.JSONDecodeError as e:
            print(f"JSON decoding error for batch {batch_num}: {e}")
            print(f"Raw response content: {response.content}")
            continue

    print(f"Successfully formalized {len(all_axioms)} claims")
    return {"axioms": all_axioms}

def check_contradictions(axioms):
    statements = [ax["formal"] for ax in axioms if ax.get("formal")]
    if not statements:
        return False
    combined = " & ".join([f"({stmt})" for stmt in statements])
    try:
        expr = sympify(combined) # turns string into symbolic expression
        simplified = simplify_logic(expr)
        return simplified == False # if false, there is contradiction -> returns true
    except:
        return False