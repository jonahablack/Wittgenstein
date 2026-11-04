# Cross-reference diagnostic spec

`review/cross_reference_diagnostics.py`, used by the real-corpus diagnostic harness
(`docs/evidence-set-real-corpus-diagnostics-plan.md` §8). **Measurement only** --
this module does not implement cross-reference/definition closure (pulling a
referenced target into an evidence set); `review/evidence_set.py` is unchanged by it.

## What it detects

Reuses `review/field_extraction.py::extract_fields`'s existing
`ComparisonFieldName.CROSS_REFERENCE` extraction unchanged (itself a reuse of
`proposition/annotations.py`'s `AnnotationCueType.CROSS_REFERENCE` cue detector,
pattern `\b(Section|Table|Figure|Exemption|Appendix|Clause)\s+[A-Za-z0-9.]+(?:\([a-z]\))?\b`)
-- no second regex, no new detection method. Every match in an answer claim's text is
one `CrossReferenceMarker`.

## How target state is resolved

For each marker, a fresh `ingestion.corpus_index.CorpusIndex` is built over the same
corpus text already used for the trace (via `index_corpus`, which is idempotent/
content-hash-cached per `docs/efficiency-and-processing-architecture.md` §3 -- this is
never a second, divergent index). The marker text is matched, case-insensitively, as a
substring against every `SourceSegment.location` in that index; a match is a candidate
target segment.

`CrossReferenceTargetState` (`core/enums.py`) is then set from the trace's own stage
lists, precedence highest first (a segment can appear in multiple stages; the most
"downstream" one wins):

1. `PACKED` -- target segment's id appears in `trace.packed_context_items`.
2. `OMITTED` -- appears in `trace.omitted_context_items` (retrieved/selected, but
   excluded by the token budget).
3. `SELECTED` -- appears in `trace.selected_context_items` but not packed/omitted.
4. `RETRIEVED` -- appears in `trace.retrieval_candidates` but not selected.
5. `IN_CORPUS` -- a segment's `location` matched the marker text, and the trace is
   instrumented, but this target never appears in any stage list (it was never
   retrieved for this query at all).
6. `UNKNOWN` -- either no segment's `location` matched the marker text at all, or the
   trace carries no stage lists to check against (e.g. an externally supplied `trace`
   with `retrieval_candidates=None`). The brief's six-state vocabulary does not
   distinguish "target doesn't exist in this corpus" from "cannot determine" -- both
   recommend the same human review either way, so both collapse to `UNKNOWN` here
   rather than inventing a seventh state.

This is a location-text heuristic, not a resolved reference graph -- two segments with
similar `location` text can both match, and the marker's *number* (e.g. "Exemption C"
vs. "Exemption D") is matched as part of the substring, so a location string like
"... Section 4 ..." only matches a "Section 4" marker, not "Section 40". A marker with
no matching segment at all is `UNKNOWN`, never guessed into the nearest similarly-named
heading.

## The diagnostic warning

Emitted only when a marker's target state is anything other than `PACKED` (i.e. the
reference may not have everything it needs already in front of the reviewer). Exact,
fixed template -- never freeform, never a stronger or weaker claim:

```
An explicit reference may require additional source context. The referenced
target was {state}. Human review is recommended.
```

`{state}` is filled from a small fixed phrase table, one per `CrossReferenceTargetState`
value (e.g. `RETRIEVED` -> "retrieved but not included in the packed context";
`IN_CORPUS` -> "present in the corpus but not retrieved for this query"; `UNKNOWN` ->
"in an unknown location relative to the retrieval/packing pipeline"). No other
sentence is ever appended. In particular, this module never emits, and no caller of it
may append:

- "The answer is unsupported."
- "The reference caused an error."
- "The target resolves the claim."

or any equivalent causal/adjudicative claim -- the warning states an observed trace
fact (where the target landed) and recommends review; it draws no conclusion about the
answer's correctness.

## What this measures, not fixes

The output of this module (`CrossReferenceMarker.target_state` +
`cross_reference_warning`) is diagnostic-report content only. It is never fed back
into `review/evidence_set.py`'s candidate pool, never used to expand
`packed_context_items`, and never changes any `ClaimSupportCandidateStatus`/
`EvidenceSet.relationship_status`. Whether closure is worth implementing is decision
rule A in `docs/evidence-set-real-corpus-diagnostics-plan.md` §10, made only after
manual review of `CrossReferenceClosureDiagnosticLabel` annotations across real cases.
