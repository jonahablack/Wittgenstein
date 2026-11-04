"""Plumbing self-test for Experiment 3.

Runs ALL of Experiment 3's plumbing on a small, clearly labeled
SYNTHETIC hand-written fixture set with every LLM call site stubbed --
zero network, zero API cost (same purpose and pattern as
../self_test.py):

  - eval-set derivation is exercised for REAL against the saved
    ../discourse_severance_report.json + ../audit_addendum.json (pure
    local file reads, no network) and its 38/39/5 invariants asserted;
  - arm 1 runs the REAL vendored Disco-RAG parser/planner/generator
    code (RstParser._parse_output, Planner._parse, extract_answer) --
    only the chat-model backbone is a stub returning canned text in the
    vendor's own output formats, so the released parsing logic is
    genuinely exercised;
  - arm 2, both judge prompts, and the wrongness classifier run their
    real Python paths with generate_response stubbed per module;
  - condition 4 (risk_triage flags) is NOT stubbed at all -- it is
    real, pure-Python code;
  - summaries and the cross-tab are computed by the real run_exp3
    functions and asserted against hand-computed expectations.
"""

import json
import os
import sys

EXP3_DIR = os.path.dirname(os.path.abspath(__file__))
SCRIPT_DIR = os.path.dirname(EXP3_DIR)
SERVER_DIR = os.path.dirname(os.path.dirname(SCRIPT_DIR))
if SERVER_DIR not in sys.path:
    sys.path.insert(0, SERVER_DIR)

from langchain_core.language_models.chat_models import BaseChatModel  # noqa: E402
from langchain_core.messages import AIMessage  # noqa: E402
from langchain_core.outputs import ChatGeneration, ChatResult  # noqa: E402

from scripts.discourse_severance import severance_detection  # noqa: E402
from scripts.discourse_severance.exp3_recovery_comparison import (  # noqa: E402
    custom_fallback,
    disco_rag_adapter,
    exp3_scoring,
    run_exp3,
)

# --- synthetic fixtures -------------------------------------------------------
#
# Each fixture is a hand-written SYNTHETIC sentence (not corpus data)
# with canned outputs for every stubbed call site, chosen so that all
# outcome buckets are exercised: correct recovery, fluent-but-wrong,
# visibly-garbled, flag/no-flag, bundled-nucleus sub-clause re-read,
# and the a2_flagged separability path.

FIXTURES = [
    {
        # Both arms recover correctly; a claim-level hedge flag fires ->
        # exercises the false-alarm cell of the cross-tab.
        "id": "synthetic:1",
        "part_label": "SYNTHETIC (self-test)",
        "sentence_index": 1,
        "sentence": "The permit generally remains valid unless the applicant withdraws it.",
        "relation": {
            "relation_type": "Exception",
            "nucleus": "The permit generally remains valid",
            "satellite": "the applicant withdraws it",
            "connective": "unless",
        },
        "a2_flagged": False,
        "bundled_nucleus": False,
        "governed_subclause": None,
        "condition_a_claims": [
            "The permit generally remains valid.",
            "The applicant withdraws it.",
        ],
        "rst_output": (
            "EDUs:\n"
            "[1] The permit generally remains valid\n"
            "[2] unless the applicant withdraws it.\n"
            "RST ANALYSIS:\n"
            "RELATION(EDU_1, EDU_2): {CONDITION}\n"
            "TREE STRUCTURE:\n"
            "ROOT[1-2]\n"
            "|--- NUCLEUS[1] The permit generally remains valid (N)\n"
            "|--- SATELLITE[2] unless the applicant withdraws it. (S): {CONDITION}\n"
        ),
        "plan_output": "PLAN: State the exception together with the requirement it governs.",
        "answer_output": (
            "ANSWER:\n"
            "- The permit generally remains valid unless the applicant withdraws it."
        ),
        "expected_arm1_claims": [
            "The permit generally remains valid unless the applicant withdraws it.",
        ],
        "expected_arm1_parse_mode": "lines",
        "arm2_claims": [
            "The permit generally remains valid unless the applicant withdraws it.",
        ],
        "judge": {
            "arm1_full": (True, "stub judge: exception intact in one claim"),
            "arm2_full": (True, "stub judge: exception intact in one claim"),
        },
        "wrongness": {},
        "expect_flags": {"any": True, "segment": False,
                         "types_contain": ["hedge"]},
    },
    {
        # Bundled nucleus. Arm 1 attaches the condition to the WRONG
        # sub-clause (fluent-but-wrong under both readings); arm 2
        # narrows scope correctly (severed under the full-nucleus judge,
        # preserved under the sub-clause judge -> exercises the
        # side-by-side divergence). Both segment-level flags fire.
        "id": "synthetic:2",
        "part_label": "SYNTHETIC (self-test)",
        "sentence_index": 2,
        "sentence": (
            "If the label is damaged or if the seal is broken, the device "
            "must not be shipped and the batch must be logged."
        ),
        "relation": {
            "relation_type": "Condition",
            "nucleus": "the device must not be shipped and the batch must be logged",
            "satellite": "the label is damaged or if the seal is broken",
            "connective": "If",
        },
        "a2_flagged": False,
        "bundled_nucleus": True,
        "governed_subclause": "the device must not be shipped",
        "condition_a_claims": [
            "The device must not be shipped.",
            "The batch must be logged.",
            "The label is damaged or the seal is broken.",
        ],
        "rst_output": (
            "EDUs:\n"
            "[1] If the label is damaged or if the seal is broken,\n"
            "[2] the device must not be shipped\n"
            "[3] and the batch must be logged.\n"
            "RST ANALYSIS:\n"
            "RELATION(EDU_1, EDU_2): {CONDITION}\n"
            "TREE STRUCTURE:\n"
            "ROOT[1-3]\n"
            "|--- NUCLEUS[2] the device must not be shipped (N)\n"
            "|--- SATELLITE[1] If the label is damaged or if the seal is broken, (S): {CONDITION}\n"
        ),
        "plan_output": "PLAN: Attach the condition to each governed requirement.",
        "answer_output": (
            "ANSWER:\n"
            "- The device must not be shipped.\n"
            "- If the label is damaged or if the seal is broken, the batch must be logged."
        ),
        "expected_arm1_claims": [
            "The device must not be shipped.",
            "If the label is damaged or if the seal is broken, the batch must be logged.",
        ],
        "expected_arm1_parse_mode": "lines",
        "arm2_claims": [
            "If the label is damaged or if the seal is broken, the device must not be shipped.",
            "The batch must be logged.",
        ],
        "judge": {
            "arm1_full": (False, "stub judge: condition attached to the wrong sub-clause"),
            "arm1_sub": (False, "stub judge: governed sub-clause asserted unconditionally"),
            "arm2_full": (False, "stub judge: second bundled assertion lost the condition"),
            "arm2_sub": (True, "stub judge: condition attached to the governed sub-clause"),
        },
        "wrongness": {
            "arm1": ("fluent_but_wrong",
                     "stub classifier: fluent authoritative claims, wrong attachment"),
            "arm2": ("fluent_but_wrong",
                     "stub classifier: fluent claims, bundled co-assertion unconditional"),
        },
        "expect_flags": {"any": True, "segment": True,
                         "types_contain": ["segment_nested_conditional",
                                           "segment_negation_scope"]},
    },
    {
        # Arm 1 correct via the whole-answer (prose) parse path; arm 2
        # visibly garbled. No flags fire. Tagged a2_flagged to exercise
        # the excluding_a2_flagged summary split.
        "id": "synthetic:3",
        "part_label": "SYNTHETIC (self-test)",
        "sentence_index": 3,
        "sentence": "Records must be retained, except records covered by section 12.",
        "relation": {
            "relation_type": "Exception",
            "nucleus": "Records must be retained",
            "satellite": "records covered by section 12",
            "connective": "except",
        },
        "a2_flagged": True,
        "bundled_nucleus": False,
        "governed_subclause": None,
        "condition_a_claims": [
            "Records must be retained.",
            "Records covered by section 12 exist.",
        ],
        "rst_output": (
            "EDUs:\n"
            "[1] Records must be retained,\n"
            "[2] except records covered by section 12.\n"
            "RST ANALYSIS:\n"
            "RELATION(EDU_1, EDU_2): {CONDITION}\n"
            "TREE STRUCTURE:\n"
            "ROOT[1-2]\n"
            "|--- NUCLEUS[1] Records must be retained, (N)\n"
            "|--- SATELLITE[2] except records covered by section 12. (S): {CONDITION}\n"
        ),
        "plan_output": "PLAN: Keep the exception attached to the retention requirement.",
        # Deliberately NOT identical to the source sentence: judge prompts
        # embed the source sentence, so an arm-1 claim equal to it would
        # make the stub's arm dispatch ambiguous.
        "answer_output": (
            "ANSWER: All records must be retained, except records covered by section 12."
        ),
        "expected_arm1_claims": [
            "All records must be retained, except records covered by section 12.",
        ],
        "expected_arm1_parse_mode": "whole_answer",
        "arm2_claims": [
            "Records must be",
            "except section",
        ],
        "judge": {
            "arm1_full": (True, "stub judge: exception intact"),
            "arm2_full": (False, "stub judge: fragments do not express the relation"),
        },
        "wrongness": {
            "arm2": ("visibly_incomplete_or_garbled",
                     "stub classifier: truncated fragments, visibly broken"),
        },
        "expect_flags": {"any": False, "segment": False, "types_contain": []},
    },
]


class _FakeMessage:
    def __init__(self, content):
        self.content = content


def _find_fixture(text):
    for fx in FIXTURES:
        if fx["sentence"] in text:
            return fx
    raise AssertionError(
        "self-test stub received a prompt containing no fixture sentence "
        "-- self-test wiring is broken.")


def _which_arm(fixture, text):
    """Which arm's claim set is embedded in this judge/classifier prompt."""
    if all(c in text for c in fixture["expected_arm1_claims"]):
        return "arm1"
    if all(c in text for c in fixture["arm2_claims"]):
        return "arm2"
    raise AssertionError(
        f"self-test stub: prompt for {fixture['id']} matches neither arm's "
        "canned claims -- self-test wiring is broken.")


class StubBackbone(BaseChatModel):
    """Stands in for ChatOpenAIBackbone at the SAME boundary (the
    langchain chat-model interface), so the REAL vendor chains
    (prompt | llm | StrOutputParser()) and the real vendor output
    parsers all execute. Dispatches on the vendor prompts' own
    distinctive system-message text (safe to hard-code: the vendor repo
    is pinned at commit 0755104).
    """

    model_name: str = "stub-backbone"

    @property
    def _llm_type(self):
        return "exp3-self-test-stub"

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        text = "\n".join(str(m.content) for m in messages)
        fixture = _find_fixture(text)
        if "Rhetorical Structure Theory" in text:
            out = fixture["rst_output"]
        elif "discourse-aware plan" in text and "discourse knowledge" not in text:
            out = fixture["plan_output"]
        elif "retrieval-augmented generation with discourse knowledge" in text:
            out = fixture["answer_output"]
        else:
            raise AssertionError(
                "self-test stub backbone could not classify a vendor prompt.")
        return ChatResult(generations=[ChatGeneration(message=AIMessage(content=out))])


def _stub_generate_response(query, *args, **kwargs):
    """Stub for the api_call.generate_response call sites (arm-2 rewrite,
    both judge prompts, wrongness classifier). Dispatches on each
    module's own prompt-marker constant; raises on anything it cannot
    classify, so failures are loud."""
    fixture = _find_fixture(query)

    # (custom_fallback prompts never reach this stub -- they are patched
    # separately with _stub_generate_response_fallback, because the
    # fallback prompt does not contain the full source sentence.)

    # Sub-clause marker first: its text contains the full-nucleus marker
    # as a prefix.
    if severance_detection.LLM_JUDGE_SUBCLAUSE_PROMPT_MARKER in query:
        arm = _which_arm(fixture, query)
        preserved, reasoning = fixture["judge"][f"{arm}_sub"]
        return _FakeMessage(json.dumps({"preserved": preserved, "reasoning": reasoning}))

    if severance_detection.LLM_JUDGE_PROMPT_MARKER in query:
        arm = _which_arm(fixture, query)
        preserved, reasoning = fixture["judge"][f"{arm}_full"]
        return _FakeMessage(json.dumps({"preserved": preserved, "reasoning": reasoning}))

    if exp3_scoring.WRONGNESS_PROMPT_MARKER in query:
        arm = _which_arm(fixture, query)
        category, reasoning = fixture["wrongness"][arm]
        return _FakeMessage(json.dumps({"category": category, "reasoning": reasoning}))

    raise AssertionError("self-test stub could not classify prompt type.")


def _stub_generate_response_fallback(query, *args, **kwargs):
    """Separate stub for custom_fallback: its prompt carries the claims
    and relation fields but not the full source sentence, so dispatch on
    the nucleus field instead."""
    if custom_fallback.CUSTOM_FALLBACK_PROMPT_MARKER not in query:
        raise AssertionError(
            "custom_fallback stub received a non-fallback prompt.")
    for fx in FIXTURES:
        if fx["relation"]["nucleus"] in query:
            return _FakeMessage(json.dumps({"claims": fx["arm2_claims"]}))
    raise AssertionError(
        "custom_fallback stub: no fixture nucleus found in prompt.")


def _check_real_eval_set_derivation():
    """Exercise the REAL eval-set derivation against the saved reports
    (local file reads only -- no network)."""
    if not (os.path.exists(run_exp3.SOURCE_REPORT)
            and os.path.exists(run_exp3.AUDIT_ADDENDUM)):
        raise AssertionError(
            "FATAL: saved Experiment-1 report/audit addendum not found -- "
            "eval-set derivation cannot be self-tested.")
    with open(run_exp3.SOURCE_REPORT, encoding="utf-8") as fh:
        report = json.load(fh)
    with open(run_exp3.AUDIT_ADDENDUM, encoding="utf-8") as fh:
        addendum = json.load(fh)
    eval_records, derivation = run_exp3.derive_eval_set(report, addendum)
    assert len(eval_records) == 38
    assert derivation["n_condition_a_severed_llm_judge"] == 39
    assert len(derivation["a2_flagged_ids_kept_and_tagged"]) == 5
    assert "cfr21p201:467" not in {r["id"] for r in eval_records}
    print("  real eval-set derivation OK: 39 severed -> minus cfr21p201:467 "
          "-> 38 cases; 5 a2_flagged; "
          f"{len(derivation['bundled_nucleus_ids_in_eval_set'])} bundled-nucleus.")
    return derivation


def run_self_test():
    print("=" * 68)
    print("EXP3 SELF-TEST: SYNTHETIC fixtures, all LLM call sites stubbed.")
    print("Zero network, zero API cost. risk_triage flags run for REAL;")
    print("vendor Disco-RAG parser/planner/generator code runs for REAL.")
    print("=" * 68)

    print("\n[1/3] Eval-set derivation (real saved reports, local reads only):")
    _check_real_eval_set_derivation()

    print("\n[2/3] Four conditions on synthetic fixtures (stubbed LLMs):")
    orig = {
        "fallback": custom_fallback.generate_response,
        "severance": severance_detection.generate_response,
        "scoring": exp3_scoring.generate_response,
    }
    custom_fallback.generate_response = _stub_generate_response_fallback
    severance_detection.generate_response = _stub_generate_response
    exp3_scoring.generate_response = _stub_generate_response

    try:
        recovery = disco_rag_adapter.DiscoRagSingleSentenceRecovery(
            backbone=StubBackbone())
        base_records = [
            {
                "id": fx["id"],
                "part_label": fx["part_label"],
                "sentence_index": fx["sentence_index"],
                "sentence": fx["sentence"],
                "relation": fx["relation"],
                "a2_flagged": fx["a2_flagged"],
                "bundled_nucleus": fx["bundled_nucleus"],
                "governed_subclause": fx["governed_subclause"],
                "condition_a_claims": fx["condition_a_claims"],
                "saved_severance_a": {
                    "llm_judge_preserved": False,
                    "llm_judge_reasoning": "synthetic: severed by construction",
                    "rule_based_preserved": None,
                    "rule_based_detail": "synthetic fixture",
                },
            }
            for fx in FIXTURES
        ]

        results = []
        for fx, rec in zip(FIXTURES, base_records):
            result = run_exp3.process_case(rec, recovery)
            results.append(result)

            arm1 = result["condition_2_disco_rag"]
            assert arm1["error"] is None, arm1["error"]
            assert arm1["claims"] == fx["expected_arm1_claims"], (
                f"{fx['id']}: arm-1 claims {arm1['claims']!r}")
            assert arm1["answer_parse_mode"] == fx["expected_arm1_parse_mode"]
            # The REAL vendor RST parser must have produced a structured tree.
            assert arm1["rst_edu_count"] >= 2, "vendor RST parse produced no EDUs"
            assert arm1["rst_relation_count"] >= 1, "vendor RST parse produced no relations"
            assert arm1["plan_text"], "vendor Planner parse produced no plan"
            assert arm1["judge_full_nucleus"]["preserved"] is fx["judge"]["arm1_full"][0]

            arm2 = result["condition_3_custom_fallback"]
            assert arm2["error"] is None
            assert arm2["claims"] == fx["arm2_claims"]
            assert arm2["judge_full_nucleus"]["preserved"] is fx["judge"]["arm2_full"][0]

            if fx["bundled_nucleus"]:
                assert arm1["judge_subclause"]["preserved"] is fx["judge"]["arm1_sub"][0]
                assert arm2["judge_subclause"]["preserved"] is fx["judge"]["arm2_sub"][0]
            else:
                assert arm1["judge_subclause"] is None

            for arm_name, arm in (("arm1", arm1), ("arm2", arm2)):
                expected = fx["wrongness"].get(arm_name)
                if expected:
                    assert arm["wrongness"]["category"] == expected[0], (
                        f"{fx['id']}/{arm_name}: {arm['wrongness']}")
                else:
                    assert arm["wrongness"] is None

            flags = result["condition_4_flags"]
            ef = fx["expect_flags"]
            assert flags["any_flag_fired"] is ef["any"], (
                f"{fx['id']}: flags {flags['flag_types_fired']}")
            assert flags["segment_flag_fired"] is ef["segment"]
            for t in ef["types_contain"]:
                assert t in flags["flag_types_fired"], (
                    f"{fx['id']}: expected flag {t}, got {flags['flag_types_fired']}")

            print(f"  {fx['id']}: arm1={_v(arm1)}, arm2={_v(arm2)}, "
                  f"flags={flags['flag_types_fired'] or 'none'} -- OK")

        print("\n[3/3] Summaries + cross-tab (real run_exp3 aggregation code):")
        derivation = {
            "n_condition_a_severed_llm_judge": len(FIXTURES),
            "exclusions_applied": [],
            "exclusion_rationale": "synthetic self-test, no exclusions",
            "n_eval": len(FIXTURES),
            "a2_flagged_ids_kept_and_tagged": [
                fx["id"] for fx in FIXTURES if fx["a2_flagged"]],
            "a2_note": "synthetic",
            "bundled_nucleus_ids_in_eval_set": [
                fx["id"] for fx in FIXTURES if fx["bundled_nucleus"]],
        }
        summary = run_exp3.build_summary(results, derivation)

        a1 = summary["arm_1_disco_rag"]["all_38"]["full_nucleus_primary"]
        assert (a1["n_scored"], a1["n_correct"], a1["n_confidently_wrong"]) == (3, 2, 1)
        a1_alt = summary["arm_1_disco_rag"]["all_38"]["subclause_alternative_reading"]
        assert a1_alt["n_correct"] == 2  # arm-1 sub-clause verdict also severed
        a2s = summary["arm_2_custom_fallback"]["all_38"]["full_nucleus_primary"]
        assert (a2s["n_scored"], a2s["n_correct"], a2s["n_confidently_wrong"],
                a2s["n_visibly_incomplete_or_garbled"]) == (3, 1, 1, 1)
        a2_alt = summary["arm_2_custom_fallback"]["all_38"]["subclause_alternative_reading"]
        assert a2_alt["n_correct"] == 2  # bundled case flips under sub-clause judge

        excl = summary["arm_1_disco_rag"]["excluding_a2_flagged"]["full_nucleus_primary"]
        assert excl["n"] == 2  # fixture 3 is a2_flagged

        assert len(summary["subclause_side_by_side_bundled_cases"]) == 1

        ct1 = summary["cross_tab_arm_1_vs_flags"]
        assert ct1["fluent_but_wrong"]["n"] == 1
        assert ct1["fluent_but_wrong"]["n_segment_flag"] == 1
        assert ct1["correct"]["n"] == 2 and ct1["correct"]["n_any_flag"] == 1
        ct2 = summary["cross_tab_arm_2_vs_flags"]
        assert ct2["visibly_incomplete_or_garbled"]["n"] == 1
        assert ct2["visibly_incomplete_or_garbled"]["n_any_flag"] == 0

        assert len(summary["confidently_wrong_documentation"]) == 2  # fixture 2, both arms

        print("  arm-1 primary: 2/3 correct, 1 confidently wrong "
              "(flag coverage 1/1); arm-2 primary: 1/3 correct, "
              "1 confidently wrong, 1 visibly garbled -- all asserted OK.")
        print("  sub-clause alternative reading flips arm-2 bundled case: "
              "asserted OK.")
    finally:
        custom_fallback.generate_response = orig["fallback"]
        severance_detection.generate_response = orig["severance"]
        exp3_scoring.generate_response = orig["scoring"]

    print("\nSelf-test complete: all plumbing exercised with zero network calls.")
    return True


def _v(arm):
    j = arm["judge_full_nucleus"]["preserved"]
    w = (arm["wrongness"] or {}).get("category")
    return f"{'preserved' if j else 'severed'}{('/' + w) if w else ''}"


if __name__ == "__main__":
    run_self_test()
