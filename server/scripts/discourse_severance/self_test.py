"""Plumbing self-test for the discourse-severance experiment code.

Runs the full pipeline (relation elicitation -> Condition A/B atomization
-> LLM-judge + rule-based severance detection) on a small, clearly
labeled SYNTHETIC hand-written sentence set, with every LLM call site
monkeypatched to a deterministic, network-free stub. This proves the
wiring works end to end without spending API credits or requiring
network access -- same purpose and precedent as
server/scripts/external_robustness_check.py's --self-test flag.

The stub does not try to be a language model: for each of the hand-
written SELF_TEST_SENTENCES below, it recognizes which of the four call
sites is being made (by the distinctive prompt-marker constants each
real module exports) and returns a canned, sentence-specific answer that
was written by hand alongside the sentence. The rule-based severance
check is NOT stubbed -- it is real, pure-Python code with no network
dependency, so self-test exercises it for real, against the stubbed
atomized-claim lists.
"""

import json
import os
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SERVER_DIR = os.path.dirname(os.path.dirname(SCRIPT_DIR))
if SERVER_DIR not in sys.path:
    sys.path.insert(0, SERVER_DIR)

from components import response_parsing  # noqa: E402
from scripts.discourse_severance import (  # noqa: E402
    atomization_conditions,
    relation_elicitation,
    severance_detection,
)

# --- synthetic fixtures ------------------------------------------------------

# Each entry is a hand-written SYNTHETIC sentence (not corpus data) with a
# canned "correct" elicitation, a canned Condition-A atomization (mimicking
# what standard atomization plausibly does -- for the Condition/Exception
# cases this is deliberately written to sever the relation, since that is
# the failure mode being tested for), and a canned Condition-B atomization
# (mimicking relation-aware atomization that keeps nucleus+connective+
# satellite together).
SELF_TEST_SENTENCES = [
    {
        "sentence": (
            "The form is valid unless a guardian signs it."
        ),
        "relation_type": "Exception",
        "nucleus": "The form is valid",
        "satellite": "a guardian signs it",
        "connective": "unless",
        # Standard atomization severs the exception: "the form is valid"
        # is left asserted unconditionally.
        "condition_a_claims": [
            "The form is valid.",
            "A guardian signs it.",
        ],
        # Relation-aware atomization keeps the exception intact in one claim.
        "condition_b_claims": [
            "The form is valid unless a guardian signs it.",
        ],
    },
    {
        "sentence": (
            "Although the device passed initial testing, it must not be "
            "distributed."
        ),
        "relation_type": "Concession",
        "nucleus": "it must not be distributed",
        "satellite": "the device passed initial testing",
        "connective": "Although",
        # Standard atomization drops the concession, leaving an
        # unconditional prohibition with no acknowledgement of the tension.
        "condition_a_claims": [
            "The device passed initial testing.",
            "The device must not be distributed.",
        ],
        "condition_b_claims": [
            "Although the device passed initial testing, it must not be "
            "distributed.",
        ],
    },
    {
        "sentence": (
            "If the container is damaged, the product may not be sold."
        ),
        "relation_type": "Condition",
        "nucleus": "the product may not be sold",
        "satellite": "the container is damaged",
        "connective": "If",
        # Here standard atomization happens to keep the clause together
        # (single claim, condition preserved) -- included so self-test
        # covers the "A already preserves it" case, not only the failure
        # case, and so run_experiments.py's severance-rate math is
        # exercised on both true and false outcomes.
        "condition_a_claims": [
            "If the container is damaged, the product may not be sold.",
        ],
        "condition_b_claims": [
            "If the container is damaged, the product may not be sold.",
        ],
    },
    {
        "sentence": (
            "The device must be labeled with the manufacturer's name, "
            "which is also printed on the shipping carton."
        ),
        "relation_type": "Elaboration",
        "nucleus": "The device must be labeled with the manufacturer's name",
        "satellite": "is also printed on the shipping carton",
        "connective": "which",
        # Elaboration satellites are independently-true additions, so
        # splitting them is expected to be harmless -- both claims stay
        # individually true.
        "condition_a_claims": [
            "The device must be labeled with the manufacturer's name.",
            "The manufacturer's name is also printed on the shipping "
            "carton.",
        ],
        "condition_b_claims": [
            "The device must be labeled with the manufacturer's name.",
            "The manufacturer's name is also printed on the shipping "
            "carton.",
        ],
    },
]


class _FakeMessage:
    """Mimics the .content attribute of the real
    completion.choices[0].message object that api_call.generate_response
    returns, which is all every caller in this codebase reads.
    """

    def __init__(self, content):
        self.content = content


def _find_fixture(query):
    for fx in SELF_TEST_SENTENCES:
        if fx["sentence"] in query:
            return fx
    return None


def _stub_generate_response(query, *args, **kwargs):
    """Dispatches on which of the four real prompts `query` is, using
    each module's own PROMPT_MARKER constant, then returns a canned,
    fixture-specific JSON answer. Raises if a query matches no known
    fixture/marker combination, so a self-test failure is loud rather
    than silently returning empty data.
    """
    fixture = _find_fixture(query)
    if fixture is None:
        raise AssertionError(
            "self-test stub received a prompt that doesn't contain any "
            "SELF_TEST_SENTENCES sentence -- self-test wiring is broken."
        )

    # Condition A: response_parsing.py's own (unmodified) prompt.
    if "You are decomposing a single sentence of source text into atomic," in query \
            and atomization_conditions.CONDITION_B_PROMPT_MARKER not in query:
        return _FakeMessage(json.dumps({
            "segment_index": 0,
            "claims": fixture["condition_a_claims"],
        }))

    # Condition B: our relation-aware atomization prompt.
    if atomization_conditions.CONDITION_B_PROMPT_MARKER in query:
        return _FakeMessage(json.dumps({"claims": fixture["condition_b_claims"]}))

    # Relation elicitation.
    if relation_elicitation.PROMPT_MARKER in query:
        return _FakeMessage(json.dumps({
            "relation_type": fixture["relation_type"],
            "nucleus": fixture["nucleus"],
            "satellite": fixture["satellite"],
            "connective": fixture["connective"],
        }))

    # LLM-judge severance check: determine which condition's claims are
    # embedded in this particular query, and give a canned, honest
    # judgement about whether that claim set actually preserves the
    # relation (mirrors what a real judge should conclude).
    if severance_detection.LLM_JUDGE_PROMPT_MARKER in query:
        claims_in_query_a = all(c in query for c in fixture["condition_a_claims"])
        which_claims = fixture["condition_a_claims"] if claims_in_query_a else fixture["condition_b_claims"]
        preserved = _claims_preserve_relation(fixture, which_claims)
        return _FakeMessage(json.dumps({
            "preserved": preserved,
            "reasoning": (
                "stub judge: nucleus and satellite appear together with "
                "the connective in one claim" if preserved else
                "stub judge: the nucleus claim reads as unconditional once "
                "separated from the satellite"
            ),
        }))

    raise AssertionError("self-test stub could not classify prompt type.")


def _claims_preserve_relation(fixture, claims):
    """Ground truth used by the stub LLM-judge: preserved iff the
    connective and the satellite's own wording co-occur with the nucleus
    in the SAME claim (i.e. atomization did not split them apart). This
    is deliberately a stricter, more literal check than the real rule-
    based proxy, so self-test can demonstrate the two methods disagreeing
    (agreement-rate reporting) as well as agreeing.
    """
    if fixture["relation_type"] == "Elaboration":
        return True
    connective = fixture["connective"].lower()
    satellite_word = fixture["satellite"].split()[0].lower()
    for c in claims:
        cl = c.lower()
        if connective in cl and satellite_word in cl:
            return True
    return False


def run_self_test():
    print("=" * 68)
    print("SELF-TEST MODE: SYNTHETIC hand-written sentences, NOT corpus data.")
    print("All LLM call sites are stubbed -- no network, no API cost.")
    print("=" * 68)

    orig = {
        "response_parsing": response_parsing.generate_response,
        "relation_elicitation": relation_elicitation.generate_response,
        "atomization_conditions": atomization_conditions.generate_response,
        "severance_detection": severance_detection.generate_response,
    }
    response_parsing.generate_response = _stub_generate_response
    relation_elicitation.generate_response = _stub_generate_response
    atomization_conditions.generate_response = _stub_generate_response
    severance_detection.generate_response = _stub_generate_response

    results = []
    try:
        for fixture in SELF_TEST_SENTENCES:
            sentence = fixture["sentence"]
            relation = relation_elicitation.elicit_relation(sentence)
            assert relation["relation_type"] == fixture["relation_type"], (
                f"elicitation stub mismatch for {sentence!r}: "
                f"got {relation['relation_type']!r}"
            )

            claims_a = atomization_conditions.run_condition_a(sentence)
            claims_b = atomization_conditions.run_condition_b(sentence, relation)
            assert claims_a == fixture["condition_a_claims"]
            assert claims_b == fixture["condition_b_claims"]

            severance_a = severance_detection.run_severance_checks(sentence, relation, claims_a)
            severance_b = severance_detection.run_severance_checks(sentence, relation, claims_b)

            row = {
                "sentence": sentence,
                "relation_type": relation["relation_type"],
                "condition_a_claims": claims_a,
                "condition_b_claims": claims_b,
                "severance_a": severance_a,
                "severance_b": severance_b,
            }
            results.append(row)

            print(f"\nSentence: {sentence}")
            print(f"  Relation type: {relation['relation_type']} "
                  f"(nucleus={relation['nucleus']!r}, satellite={relation['satellite']!r}, "
                  f"connective={relation['connective']!r})")
            print(f"  Condition A claims: {claims_a}")
            print(f"    -> LLM-judge preserved={severance_a['llm_judge_preserved']} "
                  f"({severance_a['llm_judge_reasoning']})")
            print(f"    -> rule-based preserved={severance_a['rule_based_preserved']} "
                  f"({severance_a['rule_based_detail']})")
            print(f"  Condition B claims: {claims_b}")
            print(f"    -> LLM-judge preserved={severance_b['llm_judge_preserved']} "
                  f"({severance_b['llm_judge_reasoning']})")
            print(f"    -> rule-based preserved={severance_b['rule_based_preserved']} "
                  f"({severance_b['rule_based_detail']})")
    finally:
        response_parsing.generate_response = orig["response_parsing"]
        relation_elicitation.generate_response = orig["relation_elicitation"]
        atomization_conditions.generate_response = orig["atomization_conditions"]
        severance_detection.generate_response = orig["severance_detection"]

    print("\nSelf-test complete: all plumbing exercised with zero network calls.")
    return results


if __name__ == "__main__":
    run_self_test()
