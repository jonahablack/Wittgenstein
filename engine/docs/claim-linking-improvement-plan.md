# Claim-linking improvement plan

Replaces `review/claim_linking.py`'s pure lexical-overlap decision with a conservative,
primarily programmatic claim-evidence *comparison* layer that distinguishes topical
relevance from evidential support. Motivated by a real, demonstrated failure in the
smoke-test pilot (`docs/real-trace-smoke-test-results.md`):

> Claim: "Class III widgets must be inspected every 6 months."
> Source: "Class III widgets must be inspected once per Program Year."

The prior linker scored this `partial_support_candidate` from lexical overlap alone.
The claim and source share an entity (Class III widgets) and predicate (must be
inspected) but assert **incompatible frequencies** -- this is not partial support, and
a general-purpose lexical linker cannot see that without comparing the frequency field
specifically.

No dense/hybrid retrieval, no registry/evidence-status/activation-policy/validator-
threshold/general-trace-schema change, no human-subjects study, and the no-LLM default
path is unchanged -- this entire layer runs with zero LLM/semantic-provider calls
unless a caller explicitly opts in.

## 1. Candidate generation

Unchanged: candidate generation (which packed `ContextItem`s a claim is compared
against) stays `review/imported_answer.py`'s existing job -- every packed item is a
candidate, exactly as today. This milestone only replaces *how one (claim, candidate)
pair is scored*, not which pairs are considered.

## 2. Structured field extraction

New `review/field_extraction.py::extract_fields(text) -> list[ExtractedField]`, run
once per claim and once per candidate excerpt, extracting up to 17 field types
(`schemas/claim_comparison.py::ComparisonFieldName`): entity/subject, predicate/action,
object/value, polarity, modality/strength, quantification, population/scope,
condition, exception, temporal, version, frequency/duration, numeric value,
comparator, unit, jurisdiction/source authority, cross-reference marker.

Reuses, rather than reimplements: `proposition/annotations.py`'s existing cue
detectors for condition/exception/temporal/cross-reference/attribution (jurisdiction)
patterns, and `retrieval/lexical.py::tokenize` for the lexical-overlap feature that
remains part of (but no longer the sole determinant of) the comparison. Frequency/
duration/numeric/comparator extraction is new (`review/normalization.py`, §5).

Every `ExtractedField` carries `value`, `raw_surface_form`, `source_span`,
`extraction_method`, `extraction_status` (`extracted`/`absent`/`extraction_failed`/
`extraction_conflict`), and `confidence`. **Regex/lexicon methods only in this pass** --
dependency parsing (spaCy) is deliberately not added as a new dependency here (kept
out of `pyproject.toml`'s base dependencies, matching the project's "lightweight by
default" rule); the extraction-method vocabulary includes `spacy_dependency` and the
field-comparison logic already treats disagreement between extraction methods as an
extraction conflict (§4), so a future spaCy-backed extractor can be added later as an
optional signal without changing this design. Never treated as authoritative even when
added -- extraction failure or extractor disagreement always degrades to `UNKNOWN` or
an explicit `extraction_conflict`, never a silent pick.

## 3. Field comparison

New `review/field_comparison.py::compare_field(claim_field, source_field) -> FieldComparison`,
a four-state outcome (`schemas/claim_comparison.py::ComparisonOutcome`):

- `MATCH` -- present and compatible on both sides after conservative normalization.
- `MISMATCH` -- present on both sides and explicitly incompatible.
- `ABSENT` -- not expressed on at least one side (never conflated with `UNKNOWN`).
- `UNKNOWN` -- may be present, but extraction/normalization/scope confidence is
  insufficient to call it `MATCH` or `MISMATCH`.

Each `FieldComparison` preserves field name, claim/source value, claim/source spans,
outcome, extraction method, normalization method, confidence, and a bounded
explanation string -- never just a status code.

## 4. Mismatch classification

When a `FieldComparison` outcome is `MISMATCH`, `review/field_comparison.py` classifies
it (`schemas/claim_comparison.py::MismatchType`, 18 values exactly per the task's list:
`frequency_mismatch`, `duration_mismatch`, `numeric_mismatch`, `unit_mismatch`,
`comparator_mismatch`, `polarity_mismatch`, `modality_escalation`,
`modality_weakening`, `scope_broadening`, `scope_narrowing`, `condition_omission`,
`exception_omission`, `temporal_mismatch`, `version_mismatch`,
`jurisdiction_mismatch`, `entity_binding_mismatch`, `predicate_mismatch`,
`value_mismatch`). A mismatch is never automatically treated as a contradiction --
that inference happens only in relationship classification (§5), and only under the
stated conditions there.

## 5. Relationship classification

New `review/relationship_classification.py::classify_relationship(field_comparisons, lexical_overlap) -> RelationshipResult`
implements rules A-G from the task exactly, using the field-comparison vector (never
lexical overlap alone): `direct_support_candidate`, `partial_support_candidate`,
`qualification_required`, `contradiction_candidate`, `conflict_candidate`,
`no_support_found` (kept as the existing `NO_SUPPORT_EDGE_FOUND` enum member --
synonymous with the task's "no_support_found," and CLAUDE.md's "avoid two vocabularies
for one category" rule argues against adding a duplicate member for the same concept),
`unresolved`. Three new, additive `ClaimSupportCandidateStatus` members are added:
`DIRECT_SUPPORT_CANDIDATE`, `QUALIFICATION_REQUIRED`, `CONTRADICTION_CANDIDATE` --
`SUPPORTED_CANDIDATE` (the old, lexical-only "supported" outcome) is kept, unused by
the new engine, for backward compatibility with anything already relying on it.

## 6. Abstention behavior

`unresolved` is returned whenever: a critical field (entity or predicate alignment, or
any field the claim's own content makes load-bearing) is `UNKNOWN`; normalization is
domain-dependent and the comparison confidence is insufficient; structured extraction
methods disagree; or an opted-in semantic/NLI provider fails or returns a neutral/
uncertain result. `unresolved` is preferred over an unjustified `partial_support_candidate`
in every ambiguous case -- this is the central behavioral fix this milestone makes.

## 7. Optional semantic/NLI integration

New `review/semantic_provider.py::SemanticProvider` protocol (`is_available`/`compare`),
mirroring `proposition/llm_client.py::LLMClient` exactly. `NullSemanticProvider` is the
default (always unavailable). Never required for the no-LLM baseline or for any test in
this pass. Used only *after* programmatic field comparison, as an additional signal
that can raise support/contradiction priority but never itself asserts truth
(`entailment_like`/`contradiction_like`/`neutral`/`uncertain`/`provider_error` -- never
mapped directly to `direct_support_candidate` or `contradiction_candidate` without the
programmatic comparison already being at least consistent with that direction). No
real provider is implemented in this pass (same treatment as
`proposition/providers/anthropic_client.py` -- interface-complete, not exercised
against a live model here).

## 8. Caching

New `ingestion/kv_cache.py::SqliteKVCache` (a third `KVCache` implementation alongside
`MemoryKVCache`/`FileKVCache` -- same two-method interface, so nothing about the
existing cache abstraction changes) backs optional semantic/NLI results. Cache key via
the existing `ingestion/content_hash.py::cache_key` composite-key helper, over claim
text, passage text, provider, model id/version, prompt version, extractor version,
schema version, and normalization version -- one hashing scheme, not a second one.
Local-only by default (a `.sqlite` file, never a network cache), deterministic, never
persists credentials, supports both an in-memory `":memory:"` database (test isolation)
and an explicit `clear()` method. A cache hit means no external provider call and no
external provider cost -- it is not described as zero latency (`SemanticComparisonResult`
still records `latency_seconds` for a cache hit's local lookup/deserialization cost).

## 9. Reviewer-facing explanations

`ClaimEvidenceComparison.explanation` (built in `relationship_classification.py`) is
assembled only from the fixed, bounded sentence templates given in the task brief
("Candidate support identified.", "This passage is topically related but may not
support the claim.", "A possible frequency mismatch was detected.", etc.) -- never a
freeform LLM-generated sentence, and never one of the prohibited claims ("This passage
proves the claim.", "The answer is false.", "The model hallucinated.", "This source is
authoritative."). This mirrors the existing discipline in `matching/explanation.py` for
registry mechanisms.

## 10. Tests and diagnostics

29 required test categories (final report enumerates the count/location); smoke-test
reporting (`smoke_test/report.py`) gains the additional rate breakdowns the task
requires (§ "SMOKE-TEST REPORTING"), and a new manual annotation template field set for
real/licensed runs. See `docs/real-trace-smoke-test-results.md` for the updated
reporting shape.

## 11. Implementation notes and tuning decisions

Several concrete calibration decisions emerged only once the engine was run against
real (if synthetic) text, and are recorded here since they are now load-bearing:

- **Entity/predicate extraction uses a shared "subject precedes the verb" anchor**
  (`review/field_extraction.py::_find_verb_start`): the first modal auxiliary, or (if
  none) the first copula/do-support auxiliary ("is"/"are"/"does"/"do"/"did", with
  their negated forms). An earlier plural-noun-suffix pattern for entity extraction
  was replaced after it false-matched words merely ending in "s" (e.g. "Class") and
  failed on singular subjects.
- **Predicate compares only the base verb**, with the modal/copula and any negation
  particle stripped from the comparable surface form -- both are already carried by
  the dedicated MODALITY and POLARITY fields. Without this, a claim/source pair
  differing only by modal strength or negation registered as a *predicate* mismatch
  too, which blocked predicate alignment and prevented rules C/D from ever being
  reached.
- **Entity comparison applies a conservative singular/plural normalization**
  (`review/field_comparison.py::_singularize`, trailing "s" only) -- "Class A finding"
  vs "Class A findings" is an extremely common singular-claim-vs-plural-source pattern
  and must not register as an `entity_binding_mismatch`.
- **A candidate excerpt is decomposed into clauses before comparison**
  (`review/claim_linking.py::_clause_spans`, composing the existing Tier-0 sentence
  splitter with the existing Tier-1 clause splitter), and the claim is compared
  against every clause, keeping the most informative result. A packed candidate is
  often a full multi-clause paragraph; comparing the whole blob at once let whichever
  verb appeared *first* in the text (possibly in an unrelated clause) silently drive
  the entire comparison.
- **A noise floor on MISMATCH confidence** (`review/relationship_classification.py`,
  `_NOISE_FLOOR_CONFIDENCE = 0.35`): a mismatch below this confidence is dropped
  entirely rather than counted, so an inherently noisy field (`object_value`'s "rest
  of the sentence" heuristic, deliberately extracted at ~0.3 confidence) cannot single-
  handedly drag an otherwise cleanly-matching comparison down to `unresolved`.
- **Only claim-asserted fields count as "critical absences"**: a `FieldComparison`
  with outcome `ABSENT` where the claim itself never asserted that field
  (`claim_value is None`) is excluded from rule A's "no critical field is absent"
  check -- most claims simply don't mention most of the 17 possible fields, and
  treating every such non-assertion as blocking `direct_support_candidate` would make
  that status nearly unreachable.
- **A known, accepted limitation: pronoun coreference is not attempted.** When a
  source clause refers back to its subject only via a pronoun ("it", not "the
  Temporary Variance"), entity alignment to that specific clause cannot be
  established with regex/lexicon methods, and the conservative, correct outcome is
  `unresolved` -- not a guess. `smoke-004-conflict-negation` in the bundled pilot is a
  demonstrated instance of this (see docs/real-trace-smoke-test-results.md).

## Registry boundary

"Topical overlap without evidential support" is treated as a claim-linking diagnostic
finding, not a new canonical registry `FailureMechanism` -- no mechanism is added or
promoted in this milestone, and this comparison layer's output is never represented as
an externally-established generic RAG failure detector. If literature review later
establishes it as a distinct, generalizable mechanism, it goes through
`docs/registry-governance.md`'s existing process, not through this code change.

## Successor: multi-passage evidence sets

This milestone's single-passage comparison engine (`review/field_extraction.py`,
`review/field_comparison.py`, `review/relationship_classification.py`,
`review/claim_linking.py`) is unchanged by, and remains the foundation for,
`docs/multi-passage-evidence-plan.md`'s multi-passage evidence-set layer
(`review/evidence_set.py`): the same 17-field extraction, the same four-state
MATCH/MISMATCH/ABSENT/UNKNOWN lattice, and the same `compare_field` dispatch table are
reused, not duplicated, when checking whether two packed passages jointly cover an
answer claim's components. `ClaimSupportCandidateStatus` gained five `composite_*`
members for that layer's output; `AnswerSupportEdge.candidate_support_status` (this
milestone's field) is never assigned one of them -- only `EvidenceSet.relationship_status`
is.
