# Corpus selection rationale

Why these three corpus slices were chosen for the first real/licensed corpus
diagnostic pass (`docs/evidence-set-real-corpus-diagnostics-plan.md`,
`docs/real-corpus-diagnostic-runbook.md`), and what each is -- and is not -- used for.
The full metadata for each lives in
`data/examples/evidence_set_diagnostics/corpus-catalog.yaml`; this document explains
the reasoning behind that catalog.

## Why three corpora, and why these three

The prior diagnostic milestones (`docs/multi-passage-evidence-plan.md`,
`docs/evidence-set-real-corpus-diagnostics-plan.md`) identified two open questions
this pipeline's own synthetic fixtures cannot answer: how well the field-extraction/
claim-linking/evidence-set/cross-reference layers hold up on **real, professionally
drafted prose** with genuine structural complexity, and whether the two known
limitations (cross-reference closure, extraction reliability on long sentences) are
common or rare in that kind of text. Three corpora, each a different structural
"shape," were chosen to spread that question across variation rather than betting on
one document's idiosyncrasies:

- **`eu-ai-act-2024`** (primary) -- a modern, heavily cross-referenced regulatory
  text with explicit numbered articles, definitions, scope conditions, and temporal
  applicability clauses. Chosen as the primary corpus because its structure most
  directly exercises this project's own claim-linking field vocabulary (entity,
  scope, condition, exception, temporal, cross-reference) with minimal ambiguity about
  what "correct" extraction looks like.
- **`hipaa-privacy-rule`** (secondary) -- a long-established, hierarchically
  organized US federal regulation with dense permitted-versus-required distinctions
  and covered-entity scope conditions. Chosen to test the same extraction/comparison
  layers against a different drafting convention and a public-domain source (US
  federal regulatory text), reducing licensing risk relative to the first corpus.
- **`ada-standards-2026`** (tertiary, added only after slices 1-2 are working) --
  clinical guidance with a genuinely different diagnostic shape: recommendation
  strength/modality, numeric thresholds, population eligibility conditions, and
  table/text dependencies rather than pure legal cross-referencing. Chosen last, and
  deliberately gated on confirmed access/licensing, because it is the most
  copyright-sensitive and most likely to require care about accidental
  clinical-advice framing (see "Scope boundary" below).

## What "diagnostic" means for all three

Every one of the diagnostic question types listed per corpus in the catalog
(definition-plus-obligation, scope/condition, cross-reference target state,
numeric threshold, temporal applicability, table/text dependency, and so on) is a
question about **this software's behavior** -- does the extractor find the right
span, does the comparator classify the relationship conservatively, does the
evidence-set layer compose the right passages, does the cross-reference diagnostic
report the right target state. None of them are questions about what the regulation
or guideline actually requires in any real situation.

## Scope boundary

- No document is downloaded, scraped, or committed by anything in this repository.
  Every corpus entry in the catalog is a *description of where to look and what to
  record*, not an automated fetch. See each corpus's own
  `data/examples/evidence_set_diagnostics/<corpus_id>/README.md` and
  `docs/real-corpus-diagnostic-runbook.md` for the manual steps.
- No raw source text for any of these three corpora is ever committed to this
  repository. It lives only under the gitignored
  `data/examples/evidence_set_diagnostics/local_corpora/<corpus_id>/` on the machine
  running the diagnostic pass, unless a human has separately confirmed and documented
  redistribution rights.
- None of the three corpora's output may be presented as legal or clinical advice, a
  compliance determination, or an authoritative statement of current law/guidance.
  This applies with extra force to `ada-standards-2026`, which is professional
  clinical guidance, not a public regulatory text -- see its README for the specific
  licensing caution.
- This pass never adds legal or clinical reasoning to the pipeline. The claim-linking
  and evidence-set layers treat these documents exactly like the fictional
  widget-certification corpus: as structured text to extract fields from and compare,
  nothing more.

## Recommended order

`docs/real-corpus-diagnostic-runbook.md`'s "Recommended corpus order" section gives
the exact sequencing: EU AI Act first, HIPAA second, ADA Standards only after
access/licensing is confirmed and safe research-only labeling is in place -- start
with a 6-8 case pilot before expanding to the full 12-20 case set.

## The widget-certification corpus remains the default

`src/wittgenstein/demo/widget_corpus.py` (entirely fictional, authored for this
project) remains the default domain-neutral regression/demo corpus for every existing
test, demo, and CI-run check. Nothing in this document changes that -- the three real
corpora above are additive, used only for the manually run diagnostic pass described
in `docs/real-corpus-diagnostic-runbook.md`, never as a replacement for the bundled
synthetic fixture in automated tests.
