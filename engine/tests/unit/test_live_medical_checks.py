"""Medical-document checks: quantities (doses, thresholds, units), patient-population
qualifiers, and drug-label style numbered cross-references."""

from __future__ import annotations

from wittgenstein.core.enums import FlagKind, PullInReason
from wittgenstein.live.corpus import LiveCorpus
from wittgenstein.live.flags import FlagCollector
from wittgenstein.live.generate import ContextPassage
from wittgenstein.live.quantities import compare, quantities
from wittgenstein.live.select import reference_targets
from wittgenstein.live.verify import verify_answer

LABEL = """# Exampledrug: prescribing information

## 2 Dosage and Administration

### 2.1 Recommended Dosage

The recommended starting dosage in adults is 500 mg orally twice daily with meals.

In pediatric patients 10 years and older, the starting dosage is 500 mg once daily.

### 2.4 Dosage in Renal Impairment

Do not start treatment in patients with an eGFR between 30 and 45 mL/min/1.73 m2
[see Warnings and Precautions (5.1)].

## 5 Warnings and Precautions

### 5.1 Lactic Acidosis

Postmarketing cases of lactic acidosis have resulted in death, hypothermia and hypotension.
"""

OTHER = """# Otherdrug: prescribing information

## 5 Warnings and Precautions

### 5.1 Bleeding

Bleeding risk increases with higher doses.
"""


def _corpus(cid: str) -> LiveCorpus:
    return LiveCorpus(cid, {"exampledrug": LABEL, "otherdrug": OTHER})


def test_quantity_extraction_normalizes_values_and_units() -> None:
    qs = quantities("Give 1,000 mg every 12 hours; eGFR 30-45 mL/min/1.73 m2; 2.50 mcg.")
    pairs = {(q.value, q.unit) for q in qs}
    assert ("1000", "mg") in pairs
    assert ("12", "hour") in pairs
    assert ("30", "ml/min/1.73m2") in pairs and ("45", "ml/min/1.73m2") in pairs
    assert ("2.5", "mcg") in pairs


def test_quantity_compare_flags_wrong_value_and_wrong_unit_only() -> None:
    src = "The starting dosage is 500 mg orally twice daily, up to 2,000 mg per day."
    assert compare("Start at 500 mg twice daily.", src) == []
    assert compare("The maximum is 2000 mg per day.", src) == []
    wrong_value = compare("Start at 850 mg twice daily.", src)
    assert [(q.value, p) for q, p, _ in wrong_value] == [("850", "value_not_in_source")]
    wrong_unit = compare("Start at 500 mcg twice daily.", src)
    assert [(q.value, p) for q, p, _ in wrong_unit] == [("500", "different_unit")]
    # small unitless counts are not checked (list positions, "two of the criteria")
    assert compare("There are 3 options.", src) == []


def _verify(answer: str, unit_text: str, cid: str) -> FlagCollector:
    corpus = _corpus(cid)
    units = corpus.units()
    unit = next(u for u in units.units if unit_text in u.text)
    out = FlagCollector("t")
    verify_answer(answer, [ContextPassage(1, unit)], units, out)
    return out


def test_verification_flags_a_dose_the_source_does_not_state() -> None:
    out = _verify(
        "The recommended starting dosage in adults is 850 mg twice daily. [1]", "recommended starting", "q1"
    )
    assert any(f.kind == FlagKind.QUANTITY_MISMATCH for f in out.flags)
    ok = _verify(
        "The recommended starting dosage in adults is 500 mg twice daily. [1]", "recommended starting", "q2"
    )
    assert not any(f.kind == FlagKind.QUANTITY_MISMATCH for f in ok.flags)


def test_verification_flags_a_dropped_patient_population() -> None:
    dropped = _verify("The starting dosage is 500 mg once daily. [1]", "pediatric patients", "p1")
    assert any(f.kind == FlagKind.POPULATION_QUALIFIER_DROPPED for f in dropped.flags)
    kept = _verify("In children 10 years and older, start at 500 mg once daily. [1]", "pediatric patients", "p2")
    assert not any(f.kind == FlagKind.POPULATION_QUALIFIER_DROPPED for f in kept.flags)


def test_population_and_quantity_flags_link_to_registry_hypotheses() -> None:
    out = _verify("The starting dosage is 850 mg once daily. [1]", "pediatric patients", "p3")
    kinds = {f.kind: f for f in out.flags}
    assert kinds[FlagKind.QUANTITY_MISMATCH].registry.mechanism_id == "HYP_THRESHOLD_UNIT_COMPARATOR_MISBINDING"
    assert kinds[FlagKind.POPULATION_QUALIFIER_DROPPED].registry.epistemic_status.value == "research_hypothesis"


def test_label_cross_reference_resolves_within_the_same_document_only() -> None:
    corpus = _corpus("x1")
    units = corpus.units()
    citing = next(u for u in units.units if "see Warnings and Precautions" in u.text)
    refs = reference_targets(citing, units)
    targets = {t for _, ts in refs for t in ts}
    assert targets, "the (5.1) reference should resolve"
    assert all(units.by_id[t].document_id == "exampledrug" for t in targets)
    assert any("lactic acidosis" in units.by_id[t].text.lower() for t in targets)


def test_article_paragraph_is_not_read_as_a_section_reference() -> None:
    corpus = LiveCorpus("x2", {"d": "## 1 Scope\n\nThe scope.\n\n## 2 Rules\n\nSee Article 2(1) for details."})
    units = corpus.units()
    citing = next(u for u in units.units if "Article 2(1)" in u.text)
    assert all("(1)" not in text for text, _ in reference_targets(citing, units))


def test_pull_in_reason_enum_still_covers_cross_references() -> None:
    assert PullInReason.CROSS_REFERENCE_TARGET.value == "cross_reference_target"
