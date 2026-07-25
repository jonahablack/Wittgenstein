import json
import re
from sympy.logic.boolalg import sympify, simplify_logic

from api_call import generate_response

# Kept ASCII-only and sympy-parseable (&, |, ~, >>) on purpose: check_contradictions()
# below feeds "formal" straight into sympify(), and the PDF renderer uses a base14
# font that can't encode most Unicode logic symbols (∀ ∃ → ¬ ∧ ∨ ↔ □ ◇), so asking
# the model for those would silently break both.
_LOGIC_INSTRUCTIONS = """Translate the claim into a symbolic logical proposition using
ONLY ASCII operators, in a style sympy can parse: `&` for AND, `|` for OR, `~` for NOT,
`>>` for IMPLIES, parentheses for grouping. Represent predicates as CamelCase
function-style names with simple arguments, e.g. Cause(y, x), Contingent(x).
Do NOT use Unicode symbols (no ∀, ∃, →, ¬, ∧, ∨, ↔, □, ◇) and do NOT restate the
claim in English inside "formal" -- symbolic notation only.
Example claim: "Every event has a cause."
Example formal: "Event(x) >> Cause(y, x)\""""

_ENGLISH_INSTRUCTIONS = """Rewrite the claim as a single, precise, formal English
sentence that makes its logical structure explicit (e.g. "If X, then Y", "For every
X, ...", "There exists an X such that ..."). Strip hedging and rhetorical language,
but do NOT use symbolic logic notation -- plain, rigorous English only.
Example claim: "Every event has a cause."
Example formal: "For every event, there exists a cause of that event.\""""

_BOTH_INSTRUCTIONS = f"""Produce BOTH of the following for the claim:
- "formal_logic": {_LOGIC_INSTRUCTIONS}
- "formal_english": {_ENGLISH_INSTRUCTIONS}"""

_MODE_INSTRUCTIONS = {
    "logic": _LOGIC_INSTRUCTIONS,
    "english": _ENGLISH_INSTRUCTIONS,
    "both": _BOTH_INSTRUCTIONS,
}
_MODE_FIELDS = {
    "logic": '"segment_index", "english", "formal"',
    "english": '"segment_index", "english", "formal"',
    "both": '"segment_index", "english", "formal_logic", "formal_english"',
}


def _extract_json_object(text):
    """Pull a JSON object out of an LLM response, tolerating code fences and
    leading/trailing prose the model adds despite being told not to."""
    cleaned = re.sub(r'```json|```', '', text).strip().strip('`')
    match = re.search(r'\{.*\}', cleaned, re.DOTALL)
    if not match:
        return None
    try:
        return json.loads(match.group(0))
    except json.JSONDecodeError:
        return None


def formalize_claims(all_claims_data, mode, batch_size=50):
    all_axioms = []
    total_claims = len(all_claims_data)

    print(f"Formalizing {total_claims} claims in batches of {batch_size}...")

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
        2. {_MODE_INSTRUCTIONS[mode]}
        3. Include the segment_index.

        Return a JSON object with an "axioms" list. Each object in that list has keys:
        {_MODE_FIELDS[mode]}.
        Return only valid JSON. Do not include Markdown code fences or additional text.
        Input claims:
        {formatted_claims}
        """

        response = generate_response(prompt)
        if not response or not hasattr(response, "content"):
            print(f"Failed to get response for batch {batch_num}, skipping...")
            continue

        batch_data = _extract_json_object(response.content)
        if not batch_data or "axioms" not in batch_data:
            print(f"Could not parse a valid axioms JSON object for batch {batch_num}.")
            print(f"Raw response content: {response.content[:2000]}")
            continue

        all_axioms.extend(batch_data["axioms"])

    if mode == "both":
        for ax in all_axioms:
            ax.setdefault("formal", ax.get("formal_logic", ""))

    print(f"Successfully formalized {len(all_axioms)} claims")
    if total_claims > 0 and not all_axioms:
        print(
            "WARNING: formalize_claims produced zero axioms from "
            f"{total_claims} claims -- the model likely returned unparseable "
            "responses for every batch. Check the raw-response logs above."
        )

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
