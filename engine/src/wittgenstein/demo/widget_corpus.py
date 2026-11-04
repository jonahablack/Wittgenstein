"""A small, fictional multi-document corpus for the vertical-slice demo: a "widget
certification program" (the same invented domain as
`data/examples/local_validation/`). Deliberately includes headings, paragraphs, list
items, table rows, cross-references, and condition/exception language, so the
demo exercises Tier 0 structural variety and Tier 1/2 rule-based detectors on
realistic-shaped text -- none of it is real regulatory or legal guidance.
"""

from __future__ import annotations

CERTIFICATION_HANDBOOK = """# Widget Certification Handbook

## Section 1: Eligibility

A manufacturer is eligible for Standard Certification if it has held a valid Facility
Registration for at least 12 months and has not received a Class A nonconformance
finding in the preceding 24 months. A manufacturer that has received a Class B
nonconformance finding remains eligible, provided that a corrective action plan was
filed within 30 business days of the finding.

Eligibility does not extend to facilities operating under a Temporary Variance, except
when the variance concerns packaging labeling only. See Section 4 for the full
variance exception list.

## Section 2: Application Requirements

An applicant must submit the following: a completed Form W-100, evidence of facility
registration, and a summary of the last two internal audits.

- Form W-100, signed by an authorized representative
- Facility Registration certificate, issued within the last 5 years
- Internal audit summaries covering Program Year 2024 and Program Year 2025
- A calibration log for any load-bearing test equipment, if applicable

Applications missing any required item will be returned without review. Applications
are typically processed within 45 business days, though complex cases involving
Table 3 exemptions may take longer.

## Section 3: Testing Standards

| Widget Class | Required Test | Pass Threshold |
| --- | --- | --- |
| Class I | Load Stress Test | 95% |
| Class II | Load Stress Test | 90% |
| Class III | Thermal Cycling Test | 85% |

A Class I widget must pass the Load Stress Test at a 95% threshold unless it qualifies
for the reduced-threshold exemption described in Section 4, Exemption C. Class II and
Class III widgets are tested according to Table 3 above.

## Section 4: Exemptions and Variances

Exemption C applies to widgets manufactured before January 2023, which may be tested
at an 85% threshold instead of the standard 95% threshold. Exemption C does not apply
to any widget that has been remanufactured or substantially modified since its
original manufacture date.

A Temporary Variance may be granted for packaging labeling changes only; it does not
permit deviation from the testing standards in Section 3. According to the Certification
Board, variances are reviewed quarterly and expire automatically after 180 days unless
renewed.

## Section 5: Revocation

Certification may be revoked if a Class A nonconformance is found after certification
is granted, or if the manufacturer fails to maintain facility registration. Revocation
is not automatic for a Class B finding; the Board must first offer an opportunity to
file a corrective action plan within 30 business days.
"""

INSPECTION_PROCEDURES = """# Inspection Procedures Manual

## Overview

Inspectors conduct on-site facility reviews to confirm that certified manufacturers
continue to meet the standards described in the Widget Certification Handbook,
Section 3.

## Scheduling

Routine inspections occur once per Program Year, unless a complaint triggers an
unscheduled inspection. An unscheduled inspection may occur at any time if the Board
receives a credible report of a Class A nonconformance.

## Inspection Checklist

- Confirm current Facility Registration is displayed and unexpired
- Verify calibration logs for load-bearing test equipment match Section 2 requirements
- Sample at least 10 units per widget class for retest
- Document any deviation from the pass thresholds in Table 3 of the Handbook

## Findings

A finding is classified as Class A if it directly affects test result validity; it is
classified as Class B for all other deviations, including documentation gaps. Class A
findings must be reported to the Certification Board within 5 business days. Class B
findings should be reported within 15 business days, except when they co-occur with a
Class A finding, in which case both are reported on the Class A timeline.

Inspectors may not issue a finding without direct observation or verified test data;
a finding based solely on a manufacturer's self-report is not permitted.
"""


def documents() -> dict[str, str]:
    """source_document_id -> raw text, for `ingestion.corpus_index.index_corpus`."""

    return {
        "certification-handbook": CERTIFICATION_HANDBOOK,
        "inspection-procedures": INSPECTION_PROCEDURES,
    }


DEMO_QUERIES: list[str] = [
    "What is the pass threshold for a Class I widget?",
    "When does a Class A nonconformance finding need to be reported?",
    "Does a Temporary Variance allow deviation from the testing standards?",
]
