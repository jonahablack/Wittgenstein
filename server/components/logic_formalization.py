import json
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
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
Do NOT use Unicode symbols (no ∀, ∃, →, ¬, ∧, ∨, ↔, □, ◇).
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
# "english" is deliberately NOT one of the keys the model is asked for.
# It used to be -- the model would re-type the claim back to us -- which
# meant (a) the model's copy could silently paraphrase or drift from the
# source, and (b) there was no guaranteed 1:1 mapping between input claims
# and output axioms, since nothing forced the model to produce exactly one
# output object per input claim. The pipeline already has the original
# verbatim text; the model's only job now is to formalize, keyed by
# claim_index, which _formalize_batch reconciles against the input batch
# after parsing (see below).
_MODE_FIELDS = {
    "logic": '"claim_index", "formal"',
    "english": '"claim_index", "formal"',
    "both": '"claim_index", "formal_logic", "formal_english"',
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


def _build_batch_prompt(mode, batch):
    formatted_claims = "\n".join(
        f"- (claim_index {c['claim_index']}) {c['english']}" for c in batch
    )
    return f"""
    You are an assistant specialized in logic and formal reasoning.
    I will provide you with a list of English claims, each with a claim_index.

    For each claim, in order:
    1. {_MODE_INSTRUCTIONS[mode]}
    2. Echo back its claim_index exactly as given -- do not renumber, skip,
       or merge claims. Every claim_index listed below must appear exactly
       once in your output, even if you are unsure how to formalize it well
       -- do your best rather than omitting it.

    Do not include the claim's English text in your output at all; only the
    claim_index and the formal representation(s).

    Return a JSON object with an "axioms" list. Each object in that list has
    keys: {_MODE_FIELDS[mode]}.
    Return only valid JSON. Do not include Markdown code fences or additional text.
    Input claims:
    {formatted_claims}
    """


def _reconcile_batch(mode, batch, model_axioms):
    """Rebuild this batch's axioms keyed off the INPUT claims, not the
    model's output list -- guarantees exactly one axiom per input claim,
    with "english" always the pipeline's own verbatim text, never the
    model's copy of it.

    Any claim_index the model didn't return (dropped, merged into another,
    or unparseable) gets a placeholder axiom with formal=None (or
    formal_logic/formal_english=None for "both" mode) rather than silently
    vanishing from the count. Downstream, reconstruction.py already skips
    axioms with no "formal" when building the formal-logic listing, but
    still lists them in the English reconstruction -- so a failed
    formalization stays visible (and countable) instead of disappearing.
    """
    by_index = {}
    for item in model_axioms:
        idx = item.get("claim_index")
        if idx is not None:
            by_index[idx] = item

    reconciled = []
    for claim in batch:
        idx = claim["claim_index"]
        model_item = by_index.get(idx)

        axiom = {
            "claim_index": idx,
            "segment_index": claim["segment_index"],
            "english": claim["english"],  # always the pipeline's own text
        }

        if model_item is None:
            print(f"WARNING: model did not return claim_index {idx} "
                  f"(\"{claim['english'][:60]}...\") -- keeping as unformalized.")
            if mode == "both":
                axiom["formal_logic"] = None
                axiom["formal_english"] = None
            else:
                axiom["formal"] = None
        else:
            if mode == "both":
                axiom["formal_logic"] = model_item.get("formal_logic")
                axiom["formal_english"] = model_item.get("formal_english")
            else:
                axiom["formal"] = model_item.get("formal")

        reconciled.append(axiom)

    return reconciled


def _formalize_batch(mode, batch, batch_num):
    prompt = _build_batch_prompt(mode, batch)
    response = generate_response(prompt)
    if not response or not hasattr(response, "content"):
        print(f"Failed to get response for batch {batch_num}, skipping...")
        model_axioms = []
    else:
        batch_data = _extract_json_object(response.content)
        if not batch_data or "axioms" not in batch_data:
            print(f"Could not parse a valid axioms JSON object for batch {batch_num}.")
            print(f"Raw response content: {response.content[:2000]}")
            model_axioms = []
        else:
            model_axioms = batch_data["axioms"]

    # Reconcile regardless of whether the call succeeded, failed, or
    # partially succeeded -- every claim in `batch` gets an axiom out of
    # this function, one way or another.
    return _reconcile_batch(mode, batch, model_axioms)


def formalize_claims(all_claims_data, mode, batch_size=50, max_workers=5):
    """Send each batch of claims to the model in parallel.

    Each item in all_claims_data is assigned a stable claim_index (its
    position in this list) up front. That index is the reconciliation key
    used in _reconcile_batch to guarantee the output axiom count always
    equals len(all_claims_data) -- see _reconcile_batch's docstring for why
    that wasn't previously guaranteed.
    """
    for i, claim in enumerate(all_claims_data):
        claim["claim_index"] = i

    total_claims = len(all_claims_data)
    batches = [
        all_claims_data[i:i + batch_size]
        for i in range(0, total_claims, batch_size)
    ]
    total_batches = len(batches)

    print(f"Formalizing {total_claims} claims in {total_batches} batches of up to {batch_size}, {max_workers} at a time...")

    results_by_batch = {}
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_batch_num = {
            executor.submit(_formalize_batch, mode, batch, batch_num): batch_num
            for batch_num, batch in enumerate(batches, start=1)
        }
        for future in as_completed(future_to_batch_num):
            batch_num = future_to_batch_num[future]
            try:
                results_by_batch[batch_num] = future.result()
            except Exception as e:
                print(f"Error formalizing batch {batch_num}: {e}")
                # Even on an unexpected exception, reconcile against an
                # empty model response so this batch's claims still show
                # up as unformalized placeholders instead of vanishing.
                batch = batches[batch_num - 1]
                results_by_batch[batch_num] = _reconcile_batch(mode, batch, [])
            print(f"Completed batch {len(results_by_batch)}/{total_batches}")

    all_axioms = []
    for batch_num in range(1, total_batches + 1):
        all_axioms.extend(results_by_batch.get(batch_num, []))

    if mode == "both":
        for ax in all_axioms:
            ax.setdefault("formal", ax.get("formal_logic") or "")

    unformalized = sum(1 for ax in all_axioms if not ax.get("formal") and not ax.get("formal_logic"))
    print(f"Successfully formalized {len(all_axioms) - unformalized}/{len(all_axioms)} claims "
          f"({unformalized} unformalized)")

    if total_claims > 0 and unformalized == len(all_axioms):
        print(
            "WARNING: formalize_claims produced zero successfully-formalized "
            f"axioms from {total_claims} claims -- the model likely returned "
            "unparseable responses for every batch. Check the raw-response logs above."
        )

    return {"axioms": all_axioms, "unformalized_count": unformalized}


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