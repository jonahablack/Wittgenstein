"""Red-team regression: every scenario in scripts/redteam/scenarios.py (pipeline errors,
model errors, and correct-answer controls) must keep raising -- or not raising -- the
flags it was written for. Plus unit tests for the pieces those cases drove."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts" / "redteam"))

import scenarios  # noqa: E402

from wittgenstein.live import counterfactual  # noqa: E402
from wittgenstein.live.claims import abstains, drug_names, reconstruct, referent_conflict  # noqa: E402
from wittgenstein.live.context_checks import truncated  # noqa: E402
from wittgenstein.live.quantities import compare, compare_frequency, quantities  # noqa: E402


@pytest.mark.parametrize("case", scenarios.CASES, ids=[c.id for c in scenarios.CASES])
def test_scenario(case: scenarios.Case) -> None:
    r = scenarios.run_case(case)
    assert r["pass"], f"{case.id}: raised {r['raised']}; titles {r['titles']}"


def test_reconstruct_yes_no_and_value() -> None:
    q = "Can a patient with a GFR below 30 mL/min take the 875 mg amoxicillin tablet?"
    assert reconstruct(q, "Yes.") == "A patient with a GFR below 30 mL/min can take the 875 mg amoxicillin tablet."
    assert reconstruct("Does metformin cause weight gain?", "No.") == "Metformin does not cause weight gain."
    assert (
        reconstruct("What is the maximum daily dose of metformin extended-release?", "2,550 mg.")
        == "The maximum daily dose of metformin extended-release is 2,550 mg."
    )
    assert reconstruct("What is the dose?", "The dose is 500 mg twice daily.") is None


def test_abstention_and_drug_names() -> None:
    assert abstains("The provided passages do not mention how it should be taken.")
    assert abstains("No information is provided about grapefruit.")
    assert not abstains("The label does not recommend use in children.")
    names = drug_names("erythromycin and warfarin, not routine or guideline")
    assert names == {"erythromycin", "warfarin"}


def test_referent_conflict() -> None:
    s = scenarios.MET_SWITCH
    got = referent_conflict("The maximum dose of metformin extended-release is 2,550 mg.", s, s.find("2,550"))
    assert got == ("immediate-release", "extended-release")


def test_quantities_units_ranges_frequency_derived() -> None:
    assert compare("Up to 2 g once daily.", scenarios.MET_ER) == []  # 2 g = 2,000 mg
    assert compare("30 to 60 minutes before breakfast.", scenarios.LEVO_EMPTY) == []  # one-half to one hour
    (q, problem, _), *_ = compare("Keep the INR between 2.5 and 3.0.", scenarios.WARF_AF)
    assert problem == "range_differs"
    assert compare_frequency("20 mg twice daily", scenarios.ATOR_CLARI, scenarios.ATOR_CLARI)
    (q, problem, how), *_ = compare(
        "That is 112 mcg per day.", scenarios.LEVO_FULL, given="What dose for a 70 kg adult?"
    )
    assert problem == "derived" and "70 kg" in (how or "")
    assert [x.value for x in quantities("once a day")] == []


def test_truncated() -> None:
    assert truncated("Stop it before contrast in patients with a")
    assert not truncated("Stop it before contrast.")
    assert not truncated("2.4 Recommended Dosage in Renal Impairment (2.4)")


def test_counterfactual_probe_outcomes() -> None:
    passages = [(1, scenarios.MET_ER)]
    answer = "The maximum is 2,000 mg once daily. [1]"

    def memory(_q: str, _ps: list[tuple[int, str]]) -> str:
        return answer

    def reads(_q: str, ps: list[tuple[int, str]]) -> str:
        return "The maximum is 3,000 mg once daily. [1]" if "3,000" in ps[0][1] else answer

    def jumps(_q: str, _ps: list[tuple[int, str]]) -> str:
        return "The maximum is 875 mg. [1]"

    out = {
        name: [r.outcome for r in counterfactual.run_probes("Max?", passages, answer, g)]
        for name, g in [("memory", memory), ("reads", reads), ("jumps", jumps)]
    }
    assert out == {"memory": ["ignores_context"], "reads": ["follows_context"], "jumps": ["unstable"]}
    # A value the question gives is never probed.
    assert counterfactual.targets("Over 3 months of age.", [(1, "3 months")], "Children over 3 months?") == []
