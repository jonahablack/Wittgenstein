# NuggetIndex track

Second external chunker measured against the SAME 272 governing-relation
(75 Condition + 197 Concession) + 206 Elaboration-control FactoidWiki
paragraphs `../run_experiment_1_2.py` already built for Chen et al.'s
Propositionizer (Condition A) and the gpt-4o-mini relation-aware atomizer
(Condition B) -- see `../README.md`'s Task 7 for that full methodology.
This track's own results are in `results/nuggetindex_severance_report.json`;
per-paragraph detail (all extracted triples + judge reasoning) is in
`logs/nuggetindex_govern_log.jsonl` (272 records) and
`logs/nuggetindex_elaboration_log.jsonl` (206 records). AtomicRAG is a
methodologically separate, parallel integration -- not assumed or
referenced here.

## Framing (stated explicitly, not softened)

NuggetIndex's own README and CITATION.cff self-describe it as **"a
governed, time-aware fact-retrieval sidecar for RAG"** (SIGIR 2026,
DOI 10.1145/3805712.3809687, Zerhoudi/Granitzer/Mitrovic) -- built around
validity intervals, staleness detection (`Active`/`Deprecated`/
`Contested` lifecycle states), and cross-source conflict resolution. It
is **not** designed, marketed, or evaluated by its own authors as a
general-purpose chunker/atomizer the way Propositionizer or AtomicRAG
are. This track uses ONLY `nuggetindex.extractors.llm.LLMExtractor`, one
component of that larger pipeline, pulled out and called in isolation --
none of NuggetIndex's actual governance machinery (temporal inference
beyond a placeholder timestamp, lifecycle states, conflict detection,
`NuggetStore`, `DocumentConstructor` orchestration) runs anywhere in this
track. This distinction is documented in full, with source-level
citations, in `nuggetindex_extractor_adapter.py`'s module docstring --
confirmed by reading the actual cloned source
(`src/nuggetindex/extractors/llm.py`, `extractors/base.py`,
`extractors/clients/base.py`, `extractors/prompts/extraction.md`), not
assumed from the README.

## Environment

```
venv/bin/python -m pip install -r server/scripts/discourse_severance/factoidwiki_track/nuggetindex_track/requirements.txt
```

Installs the real, published `nuggetindex` PyPI package (`nuggetindex[openai]`).
This upgraded the shared venv's `openai` package 1.57.0 -> 2.54.0 (a
transitive resolver upgrade); verified this did not break
`server/api_call.py`'s existing `generate_response` with a real
"PONG" round-trip call before any other work in this track began.
`OPENAI_API_KEY` loads via `env_utils.load_server_env()` (reads
`server/.env`, same convention as every sibling script in this project) --
confirmed working with that same PONG smoke test.

## Relation-aware (Condition-B-style) extraction: NOT POSSIBLE, confirmed by reading the code

`../condition_b_atomizer.py`'s "Condition B" (elicit-then-atomize: give
the atomizer the already-elicited relation and instruct it to preserve
it) has no NuggetIndex analogue. `LLMExtractor.aextract` has no parameter
for "relation to preserve," and `extractors/prompts/extraction.md`
(NuggetIndex's own extraction prompt, read in full) contains zero mention
of discourse relations, conditions, concessions, or any "preserve this
relation" instruction -- it is entirely about predicate normalization,
NER-style entity typing, and one-fact-per-(subject,object)-pair splitting.
Hand-writing a custom relation-aware prompt and swapping it in via
`LLMExtractor`'s `prompt_path` override was considered and rejected: that
would test our own prompt engineering under NuggetIndex's name, not
NuggetIndex's own capability. **Only the standard-extraction condition is
reported below** -- no Experiment-1-style A-vs-B ablation exists for this
chunker, matching how this same limitation would be reported for
AtomicRAG if it turned out to have no relation-aware mode either (not
assumed here; that integration is separate).

## Context-window caveat: CONFIRMED FALSE by reading the real code

Checked, not assumed: `LLMExtractor.aextract(text, *, context="", source_id=None)`
accepts an optional `context` string, but nothing in NuggetIndex's own
pipeline populates it automatically -- `pipeline/constructor.py`'s
`DocumentConstructor.aprocess` (the only caller of `aextract` anywhere in
the codebase) passes the WHOLE document text as `text` and never supplies
`context`. There is no sentence-window assembly ("current sentence + one
preceding sentence" or any variant) anywhere in NuggetIndex's source. This
track's adapter also calls `aextract(text=paragraph)` with `context` left
at its default empty string, so NuggetIndex sees exactly the same
single-paragraph unit every other chunker in this comparison sees -- **no
cross-chunker context-richness confound exists here**, and the severance
numbers below should not be discounted (or credited) on that basis.

Per the task brief's separate instruction, `sentence_boundary_diagnostic.py`
still flags any SEVERED governing case where the elicited connective's
satellite sits in a different sentence of the source paragraph than the
nucleus it governs -- a property of the Wikipedia source data (shared by
every chunker processing the same paragraphs), not of NuggetIndex.
**21 of 206 severed governing cases (10.2%) are flagged** (177/206 were
determinable via exact-substring sentence matching; 29 were not, and are
reported as indeterminate rather than guessed):

| pool_index | relation | connective | nucleus sentence idx | satellite sentence idx |
|---|---|---|---|---|
| 1936 | Concession | But | 2 | 3 |
| 2272 | Concession | However | 1 | 0 |
| 2372 | Concession | whilst | 2 | 1 |
| 2527 | Concession | But | 1 | 2 |
| 2657 | Concession | However | 1 | 2 |
| 2691 | Concession | Nonetheless | 3 | 2 |
| 3320 | Concession | although | 0 | 1 |
| 3451 | Concession | but | 1 | 0 |
| 3456 | Concession | Despite | 0 | 1 |
| 3549 | Concession | However | 0 | 1 |
| 3759 | Concession | Despite | 2 | 3 |
| 4240 | Concession | However | 2 | 1 |
| 4524 | Concession | However | 0 | 1 |
| 4787 | Condition | When | 1 | 2 |
| 4831 | Concession | However | 2 | 1 |
| 4920 | Concession | But | 0 | 2 |
| 5118 | Concession | However | 0 | 1 |
| 5224 | Concession | however | 2 | 4 |
| 5261 | Concession | Despite this | 1 | 0 |
| 5275 | Concession | however | 0 | 1 |
| 5347 | Condition | unless | 1 | 0 |

19/21 are Concession (matches the parent track's already-documented
finding that Concession connectives -- "however"/"but"/"despite" -- are
disproportionately sentence-initial discourse markers referring back to a
prior sentence, unlike Condition's typically clause-internal "if"/"unless").

## Judge design: triple-aware, documented in `triple_severance_judge.py`

NuggetIndex's atomic unit is a (subject, predicate, object) triple with a
normalized, often camelCase predicate (e.g. `"chiefExecutiveOfficer"`,
`"foundedIn"`), not a natural-language proposition. Three options were on
the table: (A) bare-reuse `../severance_judge_paragraph.py`'s prompt with
triples rendered as text, (B) a fully bespoke triple-native prompt, or a
middle path. **A middle path was used**: each triple is rendered into a
pseudo-sentence (`render_triple`: humanized predicate, e.g. `"founded in"`)
AND shown alongside its raw structured fields, with an explicit up-front
note telling the judge this rendering convention applies to every case
(so normal triple terseness -- no articles, no copula -- is never mistaken
for "garbled" text). The underlying judge QUESTION and
`_RELATION_DESCRIPTIONS` text are reused byte-for-byte from
`../severance_judge_paragraph.py` (itself copied from
`../../severance_detection.py`) for comparability. **`evidence_span` is
deliberately excluded** from what the judge sees -- including it would let
the judge "cheat" by reading the original sentence's own wording back
through the citation field, collapsing severance to near-zero and
measuring something different from what the other chunkers' severance
rates measure. Full reasoning: `triple_severance_judge.py`'s module
docstring.

## Pilot (hand-audited before the full run)

Two pilot passes, both hand-inspected:

1. **Tiny smoke test** (`--pilot 1`, 3 paragraphs, 6 calls): confirmed the
   plumbing end-to-end (extraction -> triples -> judge -> log -> report).
2. **Real pilot** (`--pilot 6`, 16 paragraphs stratified 6 Condition + 6
   Concession + 4 Elaboration, 32 calls): every extracted triple set and
   every judge verdict read by hand.

**Extraction sanity: PASSED.** Across both pilot passes, triples were
never empty and never syntactically garbled -- consistently readable
subject-predicate-object facts. Real, recurring extraction-quality issues
were found and are worth naming (not a blocking problem, but the kind of
thing this project's audits always name rather than smooth over):
predicate misapplication from NuggetIndex's fixed canonical-predicate
table when no good match exists (e.g. pool_index 1809: "he **chief
executive officer** Lord Chief Justice of England" for a judicial
appointment, not a CEO relationship; pool_index 27's first extraction
attempt: "Defiance **merged_with** Alliance" for a same-imprint comic
relationship), and at least one clear subject/direction error (pool_index
34: "Sainte-Marie **adopted** Emile Piapot" -- the source paragraph says
the reverse, that Piapot's family adopted Sainte-Marie; pool_index 5109's
full-run spot-check: a triple asserts "Imperial Star Destroyers regarded
as last refuge..." when the source clearly means the bunkers, not the
Star Destroyers, are the refuge). Extraction is also **not
byte-for-byte deterministic** across repeated calls on identical input
despite `LLMConfig.temperature=0.0` (pool_index 27 produced different
triple sets across two separate pilot runs) -- expected OpenAI API
behavior (this project's own `api_call.py` documents the same caveat for
its own `generate_response`), sharpened here by one further fact
confirmed by reading `extractors/clients/openai.py`: NuggetIndex's
`achat_structured` call never passes a `seed` parameter at all (unlike
`server/api_call.py.generate_response`'s explicit `seed=13`), so
NuggetIndex's own calls are less run-to-run-stable than this project's
other LLM calls by construction, not just by API nondeterminism.

**Judge sanity: MOSTLY SOUND, with one named, real calibration caveat.**
The judge is not a rubber stamp -- it produced varied, content-grounded
verdicts in both directions and its reasoning correctly cites specific
missing/present content in the majority of hand-checked cases (clean
correct severed calls: pool_index 1831, 1867, 1882, 1943, 2506, 3138,
4124, 5109; clean correct preserved calls: pool_index 1861, 1986, 2165,
3409). **The caveat**: in a handful of hand-checked cases (pool_index
1809, 2102, 3822, 4398 across both pilot and full-run spot-checks) the
judge scored `preserved=True` when the nucleus's content and the
satellite's content both appear as SEPARATE, unlinked triples with no
triple expressing that they stand in a Condition/Concession relationship
to each other at all -- i.e. it sometimes treats "both pieces of raw
content are present somewhere in the set" as sufficient, which is a
looser bar than "the governing relationship is structurally evident." A
concrete example: pool_index 1814 (Condition, satellite "If true,"),
where the extracted triple asserts "textual similarities support Italian
origin" as an unconditional fact -- the hypothetical framing is fully
gone -- yet the judge scored it preserved=True both times it was
hand-checked. **This is not a new problem invented by the triple
rendering**: it mirrors an already-documented pattern in this project
family, where the SAME judge design scores natural-language Propositionizer
output preserved=True in the majority of cases (51.3% for Concession)
despite the literal connective surviving verbatim only 3.6% of the time
(`../README.md`'s Task 7 qualitative-comparison section) -- the judge has
always been willing to credit "preserved" from co-present content without
a surviving connective, for any chunker. Stated plainly as a real,
disclosed limitation of the aggregate numbers below (likely biasing the
severed rate slightly DOWN, not up, since some of these lenient calls are
arguably real severances) -- not fixed by re-tuning the judge, since doing
so would decalibrate this track's numbers relative to the two other
chunkers using the identical judge design.

## Full-sample results (272 governing + 206 Elaboration control)

**956 real LLM calls** (478 records x [1 extraction call + 1 judge call]),
**395.2s wall-clock**, **0 judge call/parse failures**, **13 extraction
errors (2.7% of records)**: 5 `pydantic.ValidationError` (model emitted a
triple with an empty `object` string -- FactTriple requires
`min_length=1`) and 8 `InstructorRetryException` wrapping real OpenAI 429
rate-limit errors (`"Rate limit reached for gpt-4o-mini ... tokens per
min (TPM): Limit 200000"`), concentrated in a burst across Elaboration
pool_index 4063-5043 (7 of the 8 in the tighter 4063-4588 sub-range)
under 8-way parallel load. Every error record was
handled per this project's fail-loud-but-continue convention: an empty
triple list, `_error` logged verbatim, and the severance judge correctly
scored these 0-triple cases `severed=True` with an honest "no triples were
extracted" reasoning (spot-checked: all 13 confirmed) -- never silently
dropped or miscounted.

| Relation | N | Severed (NuggetIndex triples) |
|---|---|---|
| Condition | 75 | 60/75 (80.0%) |
| Concession | 197 | 146/197 (74.1%) |
| **Governing pooled (Condition+Concession)** | **272** | **206/272 (75.7%)** |
| Elaboration control | 206 | 77/206 (37.4%) |

**Fisher's exact test: p = 2.34e-17** (odds ratio 5.23). Chi-square:
p = 6.48e-17. The governing-vs-Elaboration gap is real and highly
significant, same qualitative direction as every other chunker measured
in this project.

**Robustness check excluding the 13 extraction-error records** (they
contribute a small severed-rate inflation since a 0-triple case can only
ever be scored severed): governing 202/268 (75.4%), Elaboration 68/197
(34.5%), Fisher p = 7.35e-19, odds ratio 5.81 -- **directionally
unchanged**, confirms the errors are not driving the headline finding.

**NuggetIndex's governing severance rate (75.7%) is dramatically higher
than Propositionizer's Condition-A rate on the SAME 272 paragraphs
(40.1%, `../README.md`) and higher than its own Elaboration control
(37.4%).** The most direct, measured explanation: connective survival is
far lower for NuggetIndex's triples than for either natural-language
atomizer measured in this project:

| | Connective survives in >=1 output unit |
|---|---|
| NuggetIndex triples, overall | **5.5%** (15/272) |
| NuggetIndex triples, Condition only | 14.7% (11/75) |
| NuggetIndex triples, Concession only | 2.0% (4/197) |
| Propositionizer (Condition A), overall (`../README.md`) | 23.5% (64/272) |
| gpt-4o-mini relation-aware atomizer (Condition B) | 100% (by construction) |

Avg. 7.17 triples/paragraph overall (6.71 Condition, 7.34 Concession) --
in the same range as Propositionizer's 9.06 and Condition B's 7.05
(`../README.md`), so this is not simply an under-extraction/too-few-facts
effect. The SAME Condition > Concession connective-survival asymmetry
Propositionizer showed is reproduced here (14.7% vs 2.0%, vs
Propositionizer's 76.0% vs 3.6%) -- directionally consistent, though at a
much lower absolute level for both relation types, consistent with
NuggetIndex's one-fact-per-(subject,object)-pair extraction design (no
instruction anywhere in its prompt permits keeping a governing clause and
its qualifier bundled in one output unit the way Condition B was
explicitly told it could) structurally leaving far less room for a
connective to survive than either natural-language atomizer.

## Files in this directory

- `env_utils.py` -- path/env helpers; READS (never writes)
  `../logs/task7_experiment_govern_log.jsonl` /
  `task7_experiment_elaboration_log.jsonl` as the source-paragraph corpus.
- `nuggetindex_extractor_adapter.py` -- thin `LLMExtractor` wrapper;
  module docstring carries the full framing statement, context-window
  finding, and API-key/client-lifetime notes.
- `triple_severance_judge.py` -- triple-aware severance judge; module
  docstring carries the judge-design decision and its rationale. Audit
  addendum (2026-08-14): extended (additively) with
  `llm_judge_triple_severance_subclause` / `build_triple_judge_prompt_subclause`
  for the nucleus-bundling audit below.
- `sentence_boundary_diagnostic.py` -- naive-sentence-split boundary check
  for the task brief's connective-spans-a-sentence-boundary flag.
- `run_nuggetindex_experiment.py` -- orchestration (pilot + full modes);
  entry point.
- `no_split_diagnostic.py` -- Audit addendum (2026-08-14): post-hoc
  severed-with-no-split (A2) diagnostic, ADAPTED for triple output (see
  addendum section below for why).
- `audit_nucleus_bundling.py` -- Audit addendum (2026-08-14): post-hoc
  nucleus-bundling (A1) audit, ADAPTED for triple output (see addendum
  section below for why).
- `requirements.txt` -- `nuggetindex[openai]`.
- `logs/nuggetindex_govern_log.jsonl` (272 records),
  `logs/nuggetindex_elaboration_log.jsonl` (206 records),
  `logs/nuggetindex_pilot_govern_log.jsonl` / `_pilot_elaboration_log.jsonl`
  (pilot-scale, kept for provenance).
- `results/nuggetindex_severance_report.json` (full run),
  `results/nuggetindex_pilot_report.json` (pilot run),
  `results/nuggetindex_no_split_diagnostic.json`,
  `results/nuggetindex_nucleus_bundling_audit.json` (both audit addenda
  below).

## Known cosmetic wart (does not affect correctness)

Constructing a fresh `AsyncOpenAI`/`instructor` client per `asyncio.run()`
call inside a `ThreadPoolExecutor` worker (necessary -- see
`nuggetindex_extractor_adapter.py`'s docstring on why clients can't be
shared across threads/event loops here) produces noisy
`RuntimeError: Event loop is closed` tracebacks on stderr during garbage
collection AFTER each call has already returned successfully. Confirmed
cosmetic: 0 judge errors and exactly the expected 13 extraction errors
(all independently attributable to real API-level causes, see above) were
observed at both pilot and full scale -- no call was silently dropped.
Not patched by relying on undocumented internals of the
`instructor`-wrapped client (`OpenAIClient` exposes no public
`close`/`aclose`), per this project's preference for disclosed warts over
fragile workarounds.

# Audit addendum (2026-08-14): severed-with-no-split (A2) diagnostic, ADAPTED for triples

Post-hoc, pure structural/keyword analysis of the SAVED results above --
no new LLM calls. Machine-readable results:
`results/nuggetindex_no_split_diagnostic.json` (script:
`no_split_diagnostic.py`). Checks whether a "severed" verdict is a real
extraction failure or a judge/prompt category error against an
extraction that did not actually separate nucleus content from satellite
content.

**This check required real adaptation, not a direct port** --
`../no_split_diagnostic.py`'s and `../atomicrag_track/no_split_diagnostic.py`'s
design (join every output unit, normalize, compare to the source
paragraph via difflib ratio >= 0.95) assumes the atomized output is
meant to stay close to the source's own wording. A triple extractor's
whole job is the OPPOSITE -- lossy compression into a terse, normalized
`(subject, predicate, object)` form. Applied unmodified, the literal
check fires for only **1/272** NuggetIndex records (confirmed
empirically, not assumed) -- not because the artifact this check exists
to catch is rare here, but because the metric is measuring "verbatim
wording survival," which triples are never designed to have.

**Adapted definition** (stated plainly, per this track's own convention
of naming design decisions rather than hiding them): "no-split" = at
least one SINGLE extracted triple, by itself, covers >= 0.6 keyword-
overlap of BOTH the nucleus and the satellite text (`content_keywords`,
imported unmodified from `../../corpus.py` -- the same utility and the
same 0.6 "both" threshold `../../audit_severance.py`'s
`connective_attachment` already uses to decide whether one claim's
content covers two different sub-clauses at once). "STRICT" additionally
requires that triple be the ONLY one extracted for the record
(`n_nuggetindex_triples == 1`) -- the triple-shaped analog of "the
extractor did not decompose the paragraph at all."

| | NuggetIndex (adapted metric) | NuggetIndex (literal ratio metric, informational only) |
|---|---|---|
| No-split (any single triple covers both nucleus + satellite) | 15/272 (5.5%) | 1/272 (0.4%) |
| ...of which STRICT (single triple, that triple) | 3/272 (1.1%) | -- |
| STRICT no-split yet scored severed=True | **1** | -- |
| Any no-split yet scored severed=True | **8** | -- |

By relation type (adapted metric): Condition 10/75 any (3 strict),
Concession 5/197 any (0 strict) -- the same Condition > Concession
asymmetry this track's connective-survival numbers above already show,
now visible in the no-split diagnostic too.

**Concrete example (the strict, category-error case): pool_index 2589**
("Content theory", Condition). Source: *"...Accordingly, if an
employee's social needs are unmet, then he will act disobediently."*
Nucleus: *"he will act disobediently."* Satellite: *"if an employee's
social needs are unmet,"* NuggetIndex extracted exactly ONE triple:
`subject="employee", predicate="actsDisobediently",
object="unmet social needs"` -- rendered: *"employee acts disobediently
unmet social needs"*. Nothing was split apart (one triple, covering both
sides' content at 100% keyword overlap each), yet the judge scored it
severed=True: *"the satellite's content is not explicitly linked to the
nucleus's assertion in a way that indicates a condition."* This is a
DIFFERENT flavor of the same category error the other tracks' no-split
diagnostics found: it is not that content was omitted by splitting it
into a separate, disconnected unit -- it is that a single triple's
`(subject, predicate, object)` slots have no place to encode "if...then"
conditional framing at all, so even total non-splitting can still fail to
preserve the relation. Worth naming as a structural limitation of the
triple representation itself, not an extraction-quality defect.

**Net effect on the headline numbers: small either way you slice it.**
Even the broader "any no-split yet severed" set (8 records) is under 3%
of NuggetIndex's 206 severed governing cases, and the strict set (the
cleanest category-error claim) is a single record.

# Audit addendum (2026-08-14): nucleus-bundling (A1) audit, ADAPTED for triples

Post-hoc audit of the SAVED results above, run by
`audit_nucleus_bundling.py`. **All numbers above, and everything in
`results/nuggetindex_severance_report.json`, are untouched** -- the
figures below are a secondary, sub-clause-scoped alternative reading
reported alongside them, not a replacement. Machine-readable results:
`results/nuggetindex_nucleus_bundling_audit.json`. No extraction or
primary-judge scoring was re-run; the only new LLM calls made were **13
real sub-clause-scoped TRIPLE-judge calls** (one per bundled record).

## Bundling detection: unmodified, identical result to the other two chunkers

`detect_bundling_sites` / `choose_bundling_site` / `assign_governed_
subclause` (imported unmodified from `../../audit_severance.py`) operate
only on the `nucleus`/`content`/`satellite` fields, which are copied
verbatim from the same source govern log into every chunker's own log.
**Bundled nuclei: 13/272 (4.8%) -- 12 clear, 1 borderline -- the
IDENTICAL 13 pool_indices** `../audit_nucleus_bundling.py` (Propositionizer)
and `../atomicrag_track/audit_nucleus_bundling.py` (AtomicRAG) already
found. This script verifies the identity programmatically (it would raise
if the set ever diverged) rather than assuming it.

## Two adaptation decisions for triples (stated explicitly)

**1. Connective attachment (step 2, structural, no LLM call)**:
`connective_attachment` (also imported unmodified) is called against
`nuggetindex_triples_rendered` -- the SAME humanized pseudo-sentence
rendering `triple_severance_judge.py`'s primary judge already shows the
LLM -- in place of a natural-language claims list. Real reuse, not a new
heuristic; only which saved field gets passed in changes. Result: **the
connective is present in 0 of 13 bundled records' rendered triples**,
consistent with this track's already-documented near-zero connective
survival (5.5% overall, `../README.md`'s parent numbers above).

**2. Sub-clause-scoped judge (step 3, the real adaptation)**: per this
task's brief, this step must use a TRIPLE-AWARE judge, not
`../../severance_detection.py`'s natural-language sub-clause judge (which
the Propositionizer and AtomicRAG audits reuse unmodified, since their
claims genuinely are natural language). No triple-aware sub-clause judge
existed anywhere in this project before this task, so
`triple_severance_judge.py` was extended -- additively, its existing
`llm_judge_triple_severance` / `build_triple_judge_prompt` untouched --
with `llm_judge_triple_severance_subclause` / `build_triple_judge_prompt_subclause`,
mirroring exactly how `../../severance_detection.py` itself houses both
its full-nucleus and sub-clause judges side by side. What is reused, not
re-derived: `render_triple`, `_RELATION_DESCRIPTIONS`, and the "IMPORTANT
SCOPING NOTE" wording pattern from the existing natural-language
sub-clause prompt; what is new is only the triples-block presentation
(raw + rendered fields shown together, same as the primary triple judge)
in place of a claims-block.

## Sub-clause-scoped judge (bundled subset only, 13 LLM calls)

Verdict changes (original full-nucleus judge -> sub-clause judge), 3 of
13 calls flip:

| pool_index | Relation | Clarity | NuggetIndex |
|---|---|---|---|
| 1840 | Concession | clear | preserved -> **severed** |
| 1936 | Concession | clear | severed -> **preserved** |
| 3263 | Concession | clear | preserved -> preserved |
| 3360 | Condition | clear | preserved -> preserved |
| 3397 | Condition | clear | severed -> severed |
| 3444 | Condition | clear | severed -> severed |
| 4208 | Condition | clear | severed -> severed |
| 4380 | Condition | clear | severed -> severed |
| 4698 | Concession | borderline | severed -> severed |
| 4707 | Concession | clear | severed -> severed |
| 4859 | Concession | clear | preserved -> preserved |
| 4920 | Concession | clear | severed -> **preserved** |
| 5132 | Condition | clear | severed -> severed |

Fewer flips than the natural-language chunkers (3/13 here vs. 12/26
Propositionizer-condition-pairs, 5/13 AtomicRAG) -- consistent with this
track's already-documented finding that NuggetIndex's triples rarely
preserve enough of EITHER sub-clause's content for the sub-clause judge's
strict evidence requirement to find grounds to flip a verdict in either
direction.

## Adjusted secondary figures (sub-clause-scoped ALTERNATIVE reading)

| Figure | Original (full-nucleus judge) | Adjusted (all 13 bundled) |
|---|---|---|
| NuggetIndex severed, overall | 206/272 (75.7%) | 205/272 (75.4%) |
| NuggetIndex severed, clear bundles only (12) | 206/272 (75.7%) | 205/272 (75.4%) |
| NuggetIndex severed, Condition relation | 60/75 (80.0%) | 60/75 (80.0%, unchanged) |
| NuggetIndex severed, Concession relation | 146/197 (74.1%) | 145/197 (73.6%) |

The smallest adjustment of the three chunkers measured so far (-0.3pp vs.
Propositionizer's -1.5pp and AtomicRAG's -1.5pp), for the reason above:
one record flips toward preserved (1936), one flips toward preserved
then is offset by one flipping toward severed elsewhere (net: 1936 and
4920 flip toward preserved, 1840 flips toward severed -- net -1 severed
overall). Does not change the qualitative picture: NuggetIndex still
severs governing relations at a far higher rate than its own Elaboration
control, and higher than either natural-language chunker measured in
this project, either way.

## Exclusion list for a future evaluation set

Records scored severed=True under NuggetIndex by the ORIGINAL
full-nucleus judge that flip to preserved under the sub-clause judge:
pool_index 1936, 4920 (2 of the 206 originally-severed records --
markedly fewer candidates than either natural-language chunker, again
consistent with NuggetIndex's triples rarely carrying enough surviving
content for ANY judge reading, full-nucleus or sub-clause-scoped, to find
the relation preserved).
