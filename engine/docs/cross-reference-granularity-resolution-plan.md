# Cross-reference granularity resolution plan

A narrow, additive extension of the cross-reference diagnostic layer
(`review/cross_reference_diagnostics.py`) and the deterministic parser
(`ingestion/parser.py`) so a citation like "Article 49(2)" can be checked against the
*specific* cited paragraph, not merely against "something from Article 49." Measurement
only -- this does not implement legal reasoning, does not resolve references
semantically, does not automatically retrieve/select/pack/expand a cited target, and
does not change any registry, activation policy, retrieval, packing, or claim-linking
behavior.

## 1. The false-reassurance problem

`docs/eu-ai-act-cross-reference-annotation-summary-2026-09-16.md`'s case
`euaia-003-explicit-cross-reference-registration` surfaced the motivating scenario: the
citation "Article 49(2)" resolves its coarse `target_state` by taking the union of
*every* segment belonging to the whole `article-49-registration` document (the existing
`_document_id_segment_ids` structural match, which deliberately resolves at
whole-document granularity -- see
`docs/eu-ai-act-article-cross-reference-fix-plan.md`, "Target-resolution behavior").
If *any* segment of that document is packed, `target_state = packed`, and
`cross_reference_warning()` returns `None` -- no warning at all. A reviewer seeing no
warning has no way to tell whether the packed excerpt is actually paragraph 2 (the
cited provision) or some other part of the same article. Silence is being read as "the
citation is satisfied," which the system has never actually verified. This is a
reviewer-safety gap, not a detection or normalization bug -- detection and
normalization were independently confirmed correct in the same annotation pass.

## 2. Coarse target state versus exact target availability

These remain two separate, independently meaningful signals, not a replacement of one
by the other:

- **Coarse target state** (`CrossReferenceTargetState`, unchanged): where *any part* of
  the cited article/annex document landed in the retrieval/packing pipeline. Existing
  consumers, the existing warning template, and the existing six-state vocabulary keep
  their current meaning and behavior exactly as before this plan.
- **Exact target availability** (new): whether the *specific* cited subdivision
  (paragraph/point) -- when one was cited -- is the part that actually landed there, a
  different sibling subdivision did, only generic surrounding material (title/heading)
  did, or the parser could not tell either way. This is strictly additional
  information layered on top of the coarse state, never a replacement for it.

A marker's coarse state can be `packed` while its exact target availability is
anything from `exact_target_present` to `target_missing` -- the two axes are
orthogonal by design.

## 3. Article, paragraph, point, and annex granularity

Citation forms already parsed by `review/cross_reference_diagnostics.py`
(`docs/eu-ai-act-article-cross-reference-fix-plan.md`) already carry a
`paragraph_number` and, when present, a `subdivision_type`/`subdivision_identifier`
(currently only `point`) on each `ReferenceTarget`. What is missing is *source-side*
structure to compare those cited numbers against: today no `SourceSegment` records
which legal paragraph or point it came from, so "Article 49(2) is packed" and "some
segment of Article 49 is packed" are indistinguishable questions. This plan adds that
source-side structure (§4) and a comparison step (`review/cross_reference_diagnostics.py`)
that reads it.

Requested-vs-resolved granularity, ordered coarse-to-fine for this plan's purposes:
`article`/`annex` (whole document) < `paragraph` < `point`. `subparagraph` and `table`
are added to the enum per the milestone brief's required vocabulary but are not
produced by this plan's parser extension -- see §8.

## 4. Required source-structure metadata

`SourceSegment` (`schemas/proposition.py`) gains four new, all-optional (default
`None`), additive fields -- `extra="forbid"` stays in force, so these are declared
fields, not free-form extras:

- `legal_article_number: str | None` -- set when the segment's document contains an
  explicit `"Article <N>"` title paragraph (matched exactly, case-insensitive,
  requiring the whole paragraph text to be just that), carried forward to every
  subsequent segment in the same document until (if ever) a new such title paragraph
  appears. Reused where useful, but not load-bearing for target resolution in this
  pilot's corpus -- that already works via the existing filename-based
  `_document_id_segment_ids` match, kept unchanged.
- `legal_paragraph_number: str | None` -- set only when a line's *own* leading marker
  is an explicit bare-number-and-period list marker (`"1. "`, `"2. "`, ... -- exactly
  the marker `ingestion/parser.py::_LIST_ITEM_RE` already recognizes as a list item,
  today discarded after matching). Carried forward (not reset) to every following
  segment in the same document until a new numbered marker appears, so a point or
  continuation sentence that follows "2. ..." without its own new number is correctly
  understood as still part of paragraph 2 -- verified against all six pilot documents
  by direct inspection of parser output (e.g. Article 49's final sentence "Only the
  Commission and national authorities..." correctly inherits `legal_paragraph_number
  = "4"`, matching its real position in the source text as part of paragraph 4).
- `legal_point_identifier: str | None` -- set only when a paragraph's own text begins
  with an explicit `"(<letter>) "` marker (`^\([a-z]\)\s`) -- a point always also
  carries whatever `legal_paragraph_number` is currently in force, so "paragraph 3,
  point (a)" is identifiable as a pair, not just a bare letter.
- `legal_annex_identifier: str | None` -- same mechanism as `legal_article_number` but
  for an `"Annex <roman numeral>"` title paragraph. Never populated in this pilot's
  six-document corpus (it contains no annex file), documented as such rather than
  silently omitted -- see §8.

No new segment type, no change to `char_start`/`char_end`/`location`/`text`/existing
segment counts. Populated only in `ingestion/parser.py::parse_document`, at the exact
point each segment is already constructed, using only explicit surface markers already
present in the source text -- never inferred from `source_document_id`/filename (that
remains the existing, separate, unchanged article/annex *document*-level match), never
inferred by an LLM, never guessed when a marker is absent (left `None`, not defaulted
to a plausible-looking value).

## 5. Exactness statuses

Two new enums in `core/enums.py`, both `str, Enum`, exactly the milestone brief's
vocabulary:

- `CrossReferenceResolutionGranularity`: `DOCUMENT`, `ARTICLE`, `PARAGRAPH`, `POINT`,
  `SUBPARAGRAPH`, `ANNEX`, `TABLE`, `UNKNOWN`. Describes the *finest granularity the
  corpus's parsed structure could actually support* for this specific citation, capped
  at whatever the citation itself asked for (a bare "Article 49" citation is reported
  as `ARTICLE` granularity even if the document happens to have paragraph markers --
  there is nothing finer to resolve when nothing finer was cited).
- `ExactTargetAvailability`: `EXACT_TARGET_PRESENT`, `PARENT_ONLY_PRESENT`,
  `SIBLING_ONLY_PRESENT`, `BROADER_CONTEXT_PRESENT`, `TARGET_MISSING`,
  `TARGET_UNKNOWN`. Describes what was actually found relative to what was cited, once
  granularity is known.

Computed once per `ReferenceTarget` in `review/cross_reference_diagnostics.py`
(`_resolve_granularity_and_exactness`, new), using only: the requested
paragraph/point (already on the `ReferenceTarget`), the set of segments the existing
target-resolution match already found (`target_segment_ids`, unchanged), each of those
segments' new `legal_paragraph_number`/`legal_point_identifier` fields, and the union
of every trace stage list's segment ids ("surfaced ids" -- appeared in
`retrieval_candidates`/`selected_context_items`/`packed_context_items`/
`omitted_context_items`, whichever the trace instruments).

Decision rules (deterministic, no semantic inference):

1. `target_segment_ids` empty -> granularity `UNKNOWN`, exactness `TARGET_UNKNOWN`.
2. Citation is bare article/annex (no paragraph cited) -> granularity `ARTICLE`/`ANNEX`;
   exactness `EXACT_TARGET_PRESENT` if any of `target_segment_ids` is surfaced, else
   `TARGET_MISSING`. (This preserves old semantics exactly -- see §6 -- the new fields
   simply restate the same fact in the new vocabulary for a bare citation.)
3. Citation cites a paragraph/point, but *no* segment among `target_segment_ids` carries
   a `legal_paragraph_number` at all (the matched document has no parsed internal
   structure) -> granularity `ARTICLE`; exactness `PARENT_ONLY_PRESENT` if any of
   `target_segment_ids` is surfaced, else `TARGET_MISSING`.
4. Citation cites a paragraph/point and the matched document does carry
   `legal_paragraph_number` structure -> granularity `PARAGRAPH` (or `POINT` only if a
   point was cited *and* at least one segment anywhere in the document carries
   `legal_point_identifier`; otherwise stays `PARAGRAPH` even for a point citation --
   see §7). Then:
   - the specific cited paragraph/point's own segment(s) (`legal_paragraph_number` ==
     cited, and `legal_point_identifier` == cited point if one was cited) intersect the
     surfaced ids -> `EXACT_TARGET_PRESENT`;
   - else, some *other* segment carrying a `legal_paragraph_number` (a genuine sibling
     provision) is surfaced -> `SIBLING_ONLY_PRESENT`;
   - else, some segment of the document is surfaced but none of the surfaced segments
     carry any `legal_paragraph_number` (only title/heading/framing text) ->
     `BROADER_CONTEXT_PRESENT`;
   - else nothing from the document is surfaced at all -> `TARGET_MISSING`.

Verified by hand against the milestone brief's five worked examples (all five match
this rule set exactly) and against this pilot's actual parsed segment output for all
six documents (`article-49-registration.txt` in particular -- confirmed via
`parse_document` that its numbered paragraphs 1-5 are already isolated `LIST_ITEM`
segments today, just without a stored paragraph number).

## 6. Backward compatibility behavior

- `CrossReferenceTargetState` (six existing values), `_resolve_target_state`,
  `_aggregate_state`, `target_segment_ids`, `target_state`, and `cross_reference_warning()`
  are **not modified**. Every existing test in `test_article_cross_reference_detection.py`,
  `test_cross_reference_diagnostics.py`, and the integration harness must keep passing
  unchanged.
- `ReferenceTarget` gains two new fields, `resolution_granularity` and
  `exact_target_status`, both with safe defaults so any code constructing one without
  them (none currently does outside this module) still works.
- `_detect_generic_cue_markers` (the pre-existing Section/Table/Figure/Exemption/
  Appendix/Clause path) is untouched; it produces no `ReferenceTarget` objects today and
  still produces none -- `resolution_granularity`/`exact_target_status` are simply
  never computed for it, not set to a misleading value.
- A new, separate function, `exactness_explanation(target, marker_target_state)`,
  returns the new bounded reviewer text (§ reviewer-facing language in the milestone
  brief) -- it does not replace `cross_reference_warning()`, which keeps returning
  exactly what it returns today for every existing caller. For a bare article/annex
  citation it returns `None` (nothing new to say beyond the unchanged coarse warning),
  preserving "do not change plain `Article 49` semantics" precisely.
- `runner.py`'s per-marker/per-target dict dump gains new keys
  (`resolution_granularity`, `exact_target_status`, `exactness_explanation`) alongside
  the existing ones -- additive JSON keys, old keys unchanged in name, type, or meaning.
- `report.py` gains new aggregate distributions (`by_resolution_granularity`,
  `by_exact_target_status`) alongside the existing `by_target_state`/
  `by_reference_type` -- additive, old keys unchanged.

## 7. What happens when source segmentation is too coarse

If a document's paragraphs are not marked with an explicit, parser-recognized leading
number (this pilot's own real corpus always is, but a differently formatted future
corpus might not be), no segment in it ever gets `legal_paragraph_number` set. Any
paragraph/point citation against that document falls into decision rule 3 above:
granularity caps at `ARTICLE`, and exactness is `PARENT_ONLY_PRESENT` (something from
the article is surfaced, precise location unverifiable) or `TARGET_MISSING` (nothing
is). This is the explicit, honest "cannot claim more than the corpus's own explicit
structure supports" behavior the milestone brief requires -- never inferred from
filename, never guessed from proximity, never claimed as `EXACT_TARGET_PRESENT`
without an explicit matching marker.

A citation naming a point but a corpus paragraph that has numbered subparagraphs
without lettered points (or vice versa) similarly caps at `PARAGRAPH` granularity
(rule 4's parenthetical) rather than fabricating point-level precision the parser
never actually confirmed.

## 8. What remains unresolved

- `DOCUMENT`, `SUBPARAGRAPH`, and `TABLE` granularity values exist in the enum (the
  milestone brief's required vocabulary) but are not produced by this plan's parser
  extension -- no current pilot document exercises them, and inventing a rule to
  populate them without a real example to validate against would risk exactly the kind
  of unverified precision claim this plan exists to avoid. Documented as reserved,
  not silently dropped.
- `legal_annex_identifier` is added to the schema per the required source-structure
  list but is never populated in this pilot's six-document corpus (no annex file
  exists locally) -- every `Annex III` marker's exactness therefore still resolves via
  decision rule 1 (`UNKNOWN`/`TARGET_UNKNOWN`), identical to its pre-existing behavior.
- Point-level exactness for a paragraph whose points are only distinguishable by
  inline text (not their own line, e.g. "point (a) above" mentioned mid-sentence
  rather than as its own `"(a) ..."` line) is not detected -- only explicit leading
  markers are parsed, per the milestone brief's "explicit document structure ... only."
- Cross-document paragraph numbering conflicts (two different corpus documents both
  using "paragraph 2" for unrelated provisions) are resolved correctly only because
  `target_segment_ids` is already scoped to the one matched document
  (`_document_id_segment_ids`'s ambiguity-safe match, unchanged) before paragraph
  comparison ever happens -- this plan does not add any new cross-document
  disambiguation logic beyond what already existed.
- Whether an `EXACT_TARGET_PRESENT` result means the citation is legally satisfied,
  necessary, or correctly interpreted -- never established here, same as the coarse
  layer (`docs/eu-ai-act-article-cross-reference-fix-plan.md`, "What this fix does not
  establish").

## 9. Test strategy

Unit tests in `tests/unit/test_article_cross_reference_detection.py` (extended) and a
new `tests/unit/test_cross_reference_granularity.py`, covering the milestone brief's 20
required categories, built the same way the existing 22-category suite is: hand-built
`SourceSegment`/`QueryTrace` fixtures (via the file's existing `_segment()`/`_trace()`
helpers, extended with the new optional fields) exercising each of the five decision
rules and their sub-branches directly, plus:

- A parser-level unit test asserting `legal_paragraph_number`/`legal_point_identifier`/
  `legal_article_number` are populated exactly as expected for the *real* pilot corpus
  text (regression-pinning the ground truth already verified by hand in §4/§5), without
  committing that source text itself -- the fixture text is a short, self-authored
  synthetic legal-style document (numbered paragraphs + lettered points), never the
  actual EU AI Act text, so this test never needs the gitignored local corpus to run in
  CI.
- Determinism: calling the same detection/resolution pipeline twice on identical input
  produces byte-identical `resolution_granularity`/`exact_target_status`/
  `exactness_explanation` output (mirrors the existing "deterministic diagnostics" test
  pattern in the integration harness).
- No automatic retrieval/packing/closure: assert that computing these new fields never
  mutates `trace.packed_context_items`/`selected_context_items`/`retrieval_candidates`/
  `result.evidence_sets`, and that `import_answer`'s output is identical whether or not
  the new detection path runs (it is diagnostic-only, called after the trace already
  exists).
- No legal/factual/causal language: a substring check over every fixed reviewer-facing
  template string (the five given templates plus the new `BROADER_CONTEXT_PRESENT`
  addition) for each of the five prohibited phrases the milestone brief lists.
- Baseline/prior post-fix output byte-for-byte unchanged (file listing/hash comparison
  against `output-baseline-before-article-xref/` and `output-after-article-xref/`,
  mirroring the existing "baseline preserved" test pattern from the prior fix).
- Third output directory (`output-after-granularity-resolution/`) confirmed gitignored
  via `git check-ignore`, mirroring the existing CLI-output-must-be-gitignored test
  pattern from `test_cross_reference_comparison.py`.
- Claim-linking/evidence-set outputs unchanged under the same inputs before/after this
  change (compare `claim_evidence_comparisons`/`evidence_sets` JSON between a run before
  and after this plan's code lands, over the bundled synthetic smoke-test corpus --
  never the real corpus, which is not committed).

## 10. How to preserve baseline/post-fix comparability

Exactly the pattern established by the prior two milestones: this plan's re-run writes
to a **third**, brand-new, gitignored output directory,
`local_corpora/eu-ai-act-2024/output-after-granularity-resolution/`, never overwriting
`output-baseline-before-article-xref/` or `output-after-article-xref/`. The new run
summary (`docs/eu-ai-act-cross-reference-granularity-run-summary.md`) compares only
what changed in the *cross-reference* fields between `output-after-article-xref/` and
`output-after-granularity-resolution/` for the same six cases, same manifest, same
corpus text, same budget, same no-LLM configuration -- so any difference observed is
attributable only to this plan's new granularity/exactness computation, never to a
retrieval, packing, or claim-linking change (none occur). `docs/eu-ai-act-cross-reference-annotation-protocol.md`
and `docs/eu-ai-act-cross-reference-comparison-template.md` are updated only if the new
fields require questions the existing protocol cannot already express (see the
milestone's own instruction to update the checklist "only if needed"); no existing
annotation file is touched, and the new run's output is explicitly not auto-annotated.
