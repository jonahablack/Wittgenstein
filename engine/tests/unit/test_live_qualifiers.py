"""Patient-group extent (live/qualifiers.py) and copula-question reconstruction
(live/claims.py): the widening of "severe renal impairment" to "renal impairment"."""

from __future__ import annotations

import pytest

from wittgenstein.live.claims import reconstruct
from wittgenstein.live.qualifiers import extents, widened

SRC = (
    "Metformin hydrochloride extended-release tablets are contraindicated in patients with severe renal "
    "impairment (eGFR below 30 mL/min/1.73 m2)."
)


def test_extent_reads_degree_and_threshold() -> None:
    e = extents(SRC)["renal"]
    assert e.degrees == {"severe"} and e.threshold
    assert e.phrase.startswith("severe renal impairment (eGFR below 30")
    assert extents("No adjustment in mild or moderate hepatic impairment.")["hepatic"].degrees == {
        "mild",
        "moderate",
    }
    assert extents("Reduce the dose if CrCl < 30 mL/min.")["renal"].threshold


@pytest.mark.parametrize(
    ("answer", "kind"),
    [
        ("Metformin is contraindicated in renal impairment.", "dropped"),
        ("Metformin is contraindicated in patients with kidney disease.", "dropped"),
        ("Metformin is contraindicated in moderate renal impairment.", "changed"),
        ("Metformin is contraindicated in moderate to severe renal impairment.", "changed"),
        ("Metformin is contraindicated in severe renal impairment.", None),
        ("Metformin is contraindicated when eGFR is below 30 mL/min/1.73 m2.", None),
        ("Metformin is contraindicated in patients with severely impaired renal function.", None),
        ("Metformin is contraindicated in pregnancy.", None),  # group gone: not this check's call
    ],
)
def test_widened(answer: str, kind: str | None) -> None:
    got = widened(SRC, answer)
    assert (got[0].kind if got else None) == kind


def test_degree_in_question_counts_as_kept() -> None:
    claim = "Metformin is contraindicated in renal impairment."
    assert widened(SRC, claim, given="Is metformin contraindicated in severe renal impairment?") == []


@pytest.mark.parametrize(
    ("question", "claim"),
    [
        (
            "Is metformin extended-release contraindicated in severe renal impairment?",
            "Metformin extended-release is contraindicated in severe renal impairment.",
        ),
        (
            "Is metformin contraindicated in severe renal impairment?",
            "Metformin is contraindicated in severe renal impairment.",
        ),
        ("Is the maximum daily dose of lisinopril 80 mg?", "The maximum daily dose of lisinopril is 80 mg."),
        (
            "Is severe renal impairment a contraindication for metformin?",
            "Severe renal impairment is a contraindication for metformin.",
        ),
        ("Is grapefruit juice safe with atorvastatin?", "Grapefruit juice is safe with atorvastatin."),
    ],
)
def test_copula_questions_rebuild(question: str, claim: str) -> None:
    assert reconstruct(question, "Yes.") == claim
