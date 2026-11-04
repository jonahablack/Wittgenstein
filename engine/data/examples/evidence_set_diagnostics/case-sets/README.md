# case-sets/

Guidance for assembling the actual diagnostic case files (`cases.json`, built from
`data/examples/evidence_set_diagnostics/case-template.json` per
`docs/real-corpus-case-authoring-guide.md`) across the three real corpora in
`data/examples/evidence_set_diagnostics/corpus-catalog.yaml`. This directory holds
guidance only -- no case files are checked in here, since a real case's `answer`/
`query`/`expected_evidence_locations` are meaningful only alongside the specific
local corpus text they were written against, which is never committed
(`docs/corpus-selection-rationale.md`, "Scope boundary").

## How many cases

- **Total across all three corpora: 12-20**, matching
  `docs/evidence-set-real-corpus-diagnostics-plan.md` §5's original sampling
  guidance.
- **Start with a 6-8 case pilot** before committing to the full set --
  `docs/real-corpus-diagnostic-runbook.md`'s recommended order runs the pilot first
  and only expands if the annotation workflow itself proves usable.
- Not statistically powered either way -- select for structural diversity across the
  case categories below, not for answer difficulty or corpus coverage completeness.

## Suggested distribution for the full first pass

| Corpus | Cases |
|---|---|
| `eu-ai-act-2024` | 5-7 |
| `hipaa-privacy-rule` | 4-6 |
| `ada-standards-2026` | 4-6 |

For a 6-8 case pilot, take roughly 2-3 cases from `eu-ai-act-2024`, 2 from
`hipaa-privacy-rule`, and (only once that corpus is onboarded) 2 from
`ada-standards-2026` -- or omit ADA entirely from the pilot per
`docs/real-corpus-diagnostic-runbook.md`'s recommended order, since it is gated on
confirmed access/licensing.

## Suggested case shapes (never fabricated answers)

These are *shapes* -- structural patterns to look for in your actual local documents
-- not pre-written answers. Every case's `answer` must still be
`document_verbatim`/`manual_transcription_from_document`/`human_authored_for_pilot`-from-what-the-document-actually-says,
or an explicitly labeled `controlled_perturbation_*`
(`docs/real-corpus-case-authoring-guide.md`'s rules) -- never a plausible-sounding
legal or clinical claim invented to fit a shape.

**EU AI Act** (`eu-ai-act-2024`):
- Definition plus obligation
- Scope/condition
- Temporal applicability
- Cross-reference target
- Exception
- Same-topic but non-supporting evidence
- Multi-article evidence set

**HIPAA** (`hipaa-privacy-rule`):
- Definition plus permitted disclosure
- Condition or exception
- Covered-entity scope
- Cross-reference
- Multiple nearby sections with similar terminology
- Unresolved applicability

**ADA Standards** (`ada-standards-2026`):
- Recommendation plus population condition
- Modality/strength comparison
- Numeric threshold
- Table/text dependency
- Temporal follow-up
- Unresolved/insufficient evidence

Not every category needs a case in the initial pilot -- per
`docs/real-corpus-diagnostic-runbook.md`'s case-sampling guidance, record which
categories are absent explicitly in the results document rather than silently
omitting them.

## What every case must preserve

Regardless of corpus or shape, every case (via the template mapping in
`docs/real-corpus-case-authoring-guide.md`) must preserve:

- the exact `query`;
- `user_stated_constraints` (`query_constraints`);
- `unresolved_intent_fields`, when the query's own intent is genuinely ambiguous;
- `answer_origin` -- how the answer was actually obtained, never left implicit;
- the exact `answer` text;
- `document_version`/source version information (which revision or effective date
  the answer depends on, if any);
- `expected_evidence_locations` -- recorded strictly as **researcher navigation aids
  for this diagnostic pass, never as a claim of universal factual truth** about what
  the document means or requires;
- `controlled-perturbation status`, explicitly, whenever an answer was deliberately
  seeded as unsupported or contradicted (`answer_origin:
  controlled_perturbation_unsupported`/`controlled_perturbation_contradicted`).

No case authored under this guidance may claim that its `expected_evidence_locations`
or `answer` constitutes a correct legal or clinical conclusion -- only that this is
where the diagnostic pass expects the pipeline to look, and what text the case is
built around.
