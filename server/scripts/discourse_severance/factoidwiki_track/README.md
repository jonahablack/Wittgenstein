# FactoidWiki / Propositionizer pilot

Started (2026-08) as a bounded pilot to resolve three open unknowns before
a large-scale rebuild of the discourse-severance experiments committed to
using Chen et al.'s real Propositionizer checkpoint on FactoidWiki-style
data (Tasks 3-6 below). **Task 7 is that full-scale rebuild**: full-scale
screening to 50+ comfortably-confirmed Condition/Concession instances,
building the Experiment 1/2 sample from Chen et al.'s already-released
Propositionizer output vs. a new relation-aware gpt-4o-mini atomizer, and
running this project's Experiment-1/2-style severance analyses -- the
paper's main empirical claim (does the RST-predicted severance failure
mode appear even under Chen et al.'s own trained model, on its own
training domain) is tested there, not in Tasks 3-6. See the per-task
sections below plus `results/*.json` and `logs/*` for full detail behind
every number quoted here. Nothing outside this `factoidwiki_track/`
directory was modified.

## Directory contents

- `env_utils.py` -- shared path/env helpers, self-contained (does not
  import from sibling scripts outside this directory -- see its
  docstring).
- `download_data.py` -- Task 2: downloads/caches
  `chentong00/propositionizer-wiki-data`'s `train.jsonl` (42,857 rows)
  and parses `sources` back into clean `(title, section, content)`
  fields. Also provides the fixed-seed, disjoint 3-way split used by
  every other script here (`shuffled_records()` /
  `get_format_test_slice()` / `get_throughput_slice()` /
  `get_classifier_pool()`).
- `propositionizer.py` -- shared model loading + generation helper for
  Tasks 3/4 (loads `chentong00/propositionizer-wiki-flan-t5-large`,
  builds either candidate prompt, runs one `generate()` call with the
  required `max_new_tokens`, decodes + `json.loads`s the output).
- `resolve_prompt_format.py` -- Task 3: runs both candidate prompt
  formats on the same 10 real paragraphs and picks a winner.
- `measure_throughput.py` -- Task 4: real per-paragraph wall-clock timing
  on 20 fresh paragraphs, CPU vs MPS.
- `relation_classifier.py` / `run_relation_screening.py` -- Task 5:
  zero-shot GPT-4o-mini Condition/Concession/Elaboration/None classifier
  for source paragraphs, and its batch-screening orchestration script.
- `candidate_prefilter.py` -- Task 6, Stage 1.5: free deterministic
  connective/satellite grounding check.
- `verification_classifier.py` -- Task 6, Stage 2: adversarial
  verification checklist (both the original and human-audit-validated
  revised `check_4` wordings; the revised one is the default as of Task 7).
- `run_two_stage_pipeline.py` -- Task 6/7: the Stage 1->1.5->2 screening
  orchestrator, resumable/pool-index-keyed.
- `manual_concession_audit.md` / `manual_concession_audit_manifest.json` /
  `tally_manual_concession_audit.py` -- the human audit that validated the
  revised `check_4` wording (84.6% vs. 46.2% agreement with human judgment).
- `run_check4_revision_experiment.py` -- the earlier bonus experiment that
  first tested the revised `check_4` wording on the validation batch's 85
  Concession survivors (57/85 confirmed); superseded as the DEFAULT by
  Task 7's promotion, kept for provenance.
- `confirmed_pool.py` -- Task 7: authoritative Stage-2-confirmed Condition/
  Concession sets (unions the two `check_4`-wording eras for Concession
  correctly) plus the available Elaboration pool.
- `condition_b_atomizer.py` -- Task 7 (Task 2 of the full-scale run):
  elicit-then-atomize prompt/call for paragraph-level input.
- `severance_judge_paragraph.py` -- Task 7 (Task 3 of the full-scale run):
  paragraph-adapted LLM severance judge.
- `run_experiment_1_2.py` -- Task 7: builds the Experiment 1/2 sample and
  runs both experiments' statistics.
- `no_split_diagnostic.py` -- Task 7 bonus: post-hoc severed-with-no-split
  audit.
- `audit_nucleus_bundling.py` -- Audit addendum (2026-08-14): post-hoc A1
  nucleus-bundling audit, ported from `../audit_severance.py`. Writes
  `results/task7_nucleus_bundling_audit.json` (additive, does not touch
  `task7_experiment_1_2_report.json`).
- `finalize_task7_screening_report.py` -- Task 7: writes the full-scale
  screening report from accumulated logs (no new LLM calls).
- `requirements.txt` -- experiment-script-only deps (torch, transformers,
  sentencepiece, protobuf). **Deliberately not added to
  `server/requirements.txt`** -- that file governs the deployed Flask
  app's production dependency footprint, which this pilot must not
  change.
- `data_cache/` -- downloaded dataset (gitignored-by-convention-sized;
  not committed).
- `logs/`, `results/` -- run logs and machine-readable JSON results per
  task.

## Environment

```
venv/bin/python -m pip install -r server/scripts/discourse_severance/factoidwiki_track/requirements.txt
```

`venv/bin/pip`'s shebang is stale from a path move -- always install via
`venv/bin/python -m pip install ...`, never `venv/bin/pip`. All scripts
in this directory must be run with `venv/bin/python` by absolute/relative
path, never bare `python3`.

**Extra dependency discovered during this pilot, not anticipated by the
original task brief:** `protobuf`. Loading the T5 tokenizer
(`AutoTokenizer.from_pretrained`) fails with
`ImportError: T5Converter requires the protobuf library` without it, even
though `sentencepiece` is installed. Added to `requirements.txt`.

No CUDA on this hardware (Apple M1 Pro, 16GB RAM, CPU + MPS backend
only, confirmed via `torch.backends.mps.is_available()`). See Task 4
below for whether MPS actually helped.

## Task 3: prompt-format resolution (RESOLVED)

**Decision: use the format WITH the `"Content:"` label** (the model
README's documented format):

```
Title: {title}. Section: {section}. Content: {content}
```

not the dataset card's prose-documented format (no `"Content:"` label).
**Every other script in this directory uses this format.** If the
full-scale rebuild reuses any of this pilot's code, it should keep using
`propositionizer.build_prompt(..., with_content_label=True)`.

### Evidence

**1. The ambiguity is not actually symmetric -- one side of it is simply
wrong about the real data.** Task 2's download let us check directly:
across ALL 42,857 rows of the actual downloaded `train.jsonl`, the
`sources` field contains the literal substring `". Content: "` in
**100% of rows (42,857/42,857, zero exceptions)**. The training-data
card's prose description of its own `sources` format (no `"Content:"`
label) does not match the data it is describing. The model README's
format does. This alone is strong evidence: the model was fine-tuned
exclusively on WITH-label-formatted input, so WITHOUT-label is
out-of-distribution for it, regardless of what either piece of
documentation claims.

(`download_data.py`'s `_split_sources` originally had a related bug,
found and fixed during this pilot: it split `content` off the first
`". "` after `"Section: ..."`, which left a leaked `"Content: "` prefix
glued onto the front of `content` in EVERY record -- harmless for
reconstructing the with-label format, but silently wrong for
reconstructing the without-label one. Fixed to explicitly strip
`". Content: "` before returning; verified with a full round-trip check
that reconstructing `f"Title: {t}. Section: {s}. Content: {c}"` from the
parsed fields exactly reproduces the original `sources` string for all
42,857 rows, 0 mismatches.)

**2. The actual generation test (10 real paragraphs, both formats, 20
calls, CPU, `max_new_tokens=512`) came out TIED on every hard metric** --
both formats are robust; neither "breaks":

| Metric | WITH label | WITHOUT label |
|---|---|---|
| Parsed as valid JSON list of strings | 10/10 (100%) | 10/10 (100%) |
| Non-empty output | 10/10 (100%) | 10/10 (100%) |
| Avg. propositions per paragraph | 5.8 | 5.9 |
| Avg. ground-truth propositions (same 10 paragraphs) | 5.8 | 5.8 |
| Avg. wall-clock time/call (CPU) | 13.10s | 12.99s |

Because the quantitative metrics were genuinely tied, the winner was
decided on evidence point 1 above (matches the model's real training
distribution), not on a coin flip.

### Side-by-side examples (3 of the 10; full 10 in `results/task3_prompt_format_resolution.json`)

**Example 1 -- "1922 British Mount Everest expedition" (Preparations)**

> Cecil Rawling had planned three expeditions in 1915 and 1916 but they
> never happened due to the outbreak of the First World War and his
> death in 1917. The expeditions in the 1920s were planned and managed
> by the British Royal Geographical Society and the Alpine Club...

- Ground truth (5): Cecil Rawling planned three expeditions in 1915/1916;
  they never happened (WWI); Rawling died in 1917; 1920s expeditions
  planned/managed by RGS + Alpine Club; RGS+Alpine Club formed a joint
  Mount Everest Committee.
- WITH label (14.5s): same 5 propositions, near-verbatim match.
- WITHOUT label (9.9s): **identical output**, word for word.

**Example 2 -- "History of the Jews in the United States" (Jewish immigration)**

> On a theological level, American Jews are divided into a number of
> Jewish denominations, of which the most numerous are Reform Judaism,
> Conservative Judaism and Orthodox Judaism. However, roughly 25% of
> American Jews are unaffiliated with any denomination...

- Ground truth (6) and WITH-label output (12.4s) and WITHOUT-label
  output (10.4s) are all **identical**, 6/6 propositions, word for word.

**Example 3 -- "South America" (Infrastructure, Energy)**

> Nuclear energy accounts for about 4% of Brazil's electricity. The
> nuclear power generation monopoly is owned by Eletronuclear
> (Eletrobrás Eletronuclear S/A), a wholly owned subsidiary of
> Eletrobrás...

- Ground truth: 12 propositions. WITH label (22.9s) and WITHOUT label
  (26.5s) produced **identical** 13-item lists (one ground-truth
  proposition pair -- "Angra III is planned to be finished" /
  "...has a projected output of 1,350 MW" -- got split into 2 by the
  model under both formats instead of staying as 1; both formats made
  the exact same split, and the model also silently dropped the special
  character in "Álvaro" -> "lvaro" under both formats -- a real but
  format-INDEPENDENT quirk).

**Takeaway:** on this sample the model is genuinely robust to the
label's presence/absence -- most outputs were byte-for-byte identical
between formats. The choice therefore rests almost entirely on evidence
point 1 (matches real training data), not on any observed quality gap.

## Task 4: throughput

**CPU, 20 fresh paragraphs (disjoint from Task 3's 10), `max_new_tokens=512`:**

| | seconds/paragraph |
|---|---|
| mean | 16.58 |
| median | 17.50 |
| min | 1.69 |
| max | 40.20 |
| stdev | 9.40 |

Wide spread (1.7s-40.2s) driven mostly by proposition-count/output
length, not raw paragraph character length alone (e.g. the 40.2s outlier,
"South West Coast Path", is only 468 chars; the 1.7s fastest case,
"Howard County Public School System", is a 36-char stub paragraph that
produced almost no propositions).

**MPS: it works, and it's a net win here -- but verify further before
betting the full run on it.** This project's own prior research flagged
incomplete MPS op coverage for T5-style models historically, so this ran
with `PYTORCH_ENABLE_MPS_FALLBACK` deliberately UNSET -- if any op this
model needs were unsupported on MPS, it would hard-crash here rather
than silently falling back to CPU and confounding the timing. **It did
not crash.** Re-running the first 5 of the same 20 paragraphs on MPS
(same model instance, moved device with `.to("mps")`):

| Title | CPU (s) | MPS (s) | MPS faster? |
|---|---|---|---|
| Stieg Larsson | 17.42 | 23.96 | No |
| Tooth whitening | 20.90 | 22.13 | No |
| Legacy of the Roman Empire | 12.35 | 6.76 | Yes |
| Ruby Gloom | 13.74 | 10.14 | Yes |
| South West Coast Path | 40.20 | 11.23 | Yes |

Matched-subset means: **CPU 20.92s vs MPS 14.85s (29% faster on
average)**. But note this is genuinely mixed at the per-example level --
2 of 5 were SLOWER on MPS, and the aggregate win is disproportionately
driven by one case (the CPU pass's slowest outlier happened to be MPS's
best case). n=5 is too small to fully trust; direction (MPS net-helps,
doesn't crash) is a real finding, magnitude (29%) is not.

**Recommendation for the full-scale run: use MPS, but validate on a
larger matched sample (30-50 paragraphs) before committing** -- the
historical "incomplete op coverage" concern did NOT materialize on this
torch build (2.7.1) for this model, which is itself worth knowing, but
this pilot's n=5 MPS sample is too small to fully retire the "is it
reliably faster" question, only the "does it crash" one.

**Illustrative time budget at the CPU rate (16.58s/paragraph, single
process, no batching -- use as the conservative bound; MPS may cut this
by roughly a quarter to a third per the above, unconfirmed at scale):**

| N paragraphs | Estimated wall-clock (CPU) |
|---|---|
| 100 | ~0.46 hours |
| 1,000 | ~4.6 hours |
| 10,000 | ~46 hours |

These are single-process, unbatched numbers -- real batching (multiple
paragraphs per `generate()` call) was not tested in this pilot and would
very likely help throughput more than the CPU/MPS device choice does;
worth exploring before the full-scale run if screening tens of
thousands of paragraphs.

## Task 5: Condition/Concession/Elaboration/None yield on Wikipedia prose

**903 paragraphs screened** (2 batches: 403 + 500, `gpt-4o-mini`,
zero-shot, 8-way parallel; 0 API errors across all 903 calls; total
wall-clock ~127s for the LLM calls -- extremely cheap/fast, see below).
Raw classifier output:

| Relation | Raw count | Raw % of 903 |
|---|---|---|
| Condition | 78 | 8.6% |
| Concession | 122 | 13.5% |
| Elaboration | 82 | 9.1% |
| None | 621 | 68.8% |

**Headline surprise: the raw Concession rate (13.5%) is ~9.6x HIGHER
than the regulatory-text baseline (13/900 = 1.4%), not lower** -- this
contradicts the pre-pilot hypothesis in the task brief that Wikipedia
prose would show even less concessive framing than regulatory text.
Taken at face value, all three relation-bearing categories already
exceed 50 raw hits within this single 903-paragraph pilot batch.

**That headline number does not survive a closer look, and should NOT
be taken at face value.** A manual spot-check of 39 raw hits (24 of the
122 Concession hits, 15 of the 78 Condition hits -- an unbiased sample
since the underlying corpus was globally pre-shuffled with a fixed seed
before any classification, so "the first N hits encountered scanning in
order" is not a cherry-picked subset) found real, systematic precision
problems:

- **Concession, 24 reviewed: ~9 clearly correct, ~2 borderline, ~13
  likely misclassified** (rough precision ~38-46%). Recurring failure
  modes: causal connectives ("since", "because") mislabeled as
  concessive; plain narrative contrast ("but", "however", "X did / Y did
  not") mislabeled as Concession despite no "apparent-incompatibility
  resolved, positive regard increases" dynamic; one degenerate case
  where the model extracted an IDENTICAL string for both nucleus and
  satellite.
- **Condition, 15 reviewed: ~5 clearly correct, ~3 borderline, ~7 likely
  misclassified** (rough precision ~33-43%). Recurring failure modes:
  purpose clauses ("to avoid X", "in order to") mislabeled as Condition
  -- **the same failure mode this project's own regulatory-text audit
  already flagged** (`../manual_condition_audit.md`'s "to maximize
  capture of forward scattered radiation" check case); causal "because"
  mislabeled as Condition; and, most commonly, definite PAST-tense
  narrative "when" ("When the IAFE was transformed... in 1937")
  mislabeled as Condition even though Condition's definition explicitly
  requires a hypothetical/future/UNREALIZED situation, not a narrated
  historical fact.
- On the positive side, the one thing this spot-check *validates*: the
  instruction to fold exceptive/restrictive framing into Condition
  rather than a separate "Exception" bucket worked as intended --
  e.g. "China would not make a formal trade agreement **unless** a
  country was a tributary state" was correctly classified Condition.

This spot-check is a single-reviewer pilot-level read, done by the same
process that wrote the classifier prompt -- treat it as an early
directional signal (consistent with this project's own already-cited
literature that zero-shot LLM RST parsing tops out around 58.6
relation-F1 vs. a 60.0 supervised baseline), not a validated
inter-annotator metric. A real audit before committing to a full-scale
target should mirror `../manual_condition_audit.md`'s approach (blank
verdict sheet, independent human review, `tally_manual_audit.py`-style
scoring) -- not performed here; out of scope for this checkpoint.

### Extrapolation to 50+ CONFIRMED instances

Two versions, because "confirmed" should mean post-audit, not raw
classifier output:

| | Raw rate | Raw-rate paragraphs needed for 50 | Precision-adjusted rate (rough band) | Adjusted paragraphs needed for 50 confirmed |
|---|---|---|---|---|
| Condition | 8.6% (78/903) | ~579 (already exceeded: 78 raw hits in 903) | ~2.9-3.7% (78 x [33%,43%] / 903) | ~1,340-1,740 |
| Concession | 13.5% (122/903) | ~370 (already exceeded: 122 raw hits in 903) | ~5.1-6.2% (122 x [38%,46%] / 903) | ~810-990 |

In plain terms: if you only look at the RAW classifier output, this
pilot batch alone already "found" 50+ Concession and 50+ Condition
instances, comfortably. But applying the precision spot-check, the
CONFIRMED count sitting in this same 903-paragraph batch is more
realistically only ~46-56 Concession (right on the edge of 50, not a
comfortable margin) and only ~26-34 Condition (short of 50). Reaching a
comfortable 50+ CONFIRMED margin for Condition specifically would
plausibly need on the order of 1,300-1,700 screened paragraphs, not the
~580 the raw rate alone would suggest -- roughly 2-3x more than a
raw-rate read implies. **Do not plan a full-scale target count off the
raw rate alone; budget for the precision haircut, and get a real human
audit sample before locking in a target N.**

One genuinely good-news finding, unqualified: unlike the regulatory-text
track (where Concession was the hard bottleneck at 13/900), Concession
in Wikipedia prose is NOT the bottleneck category here even after the
precision haircut -- Condition is. Screening effort for a full-scale run
should be sized against Condition's adjusted rate, not Concession's.

### Cost/time

903 `gpt-4o-mini` calls (short paragraph in, ~40-word structured JSON
out) completed in **~127s of wall-clock LLM time total** (51.7s for the
first 403, 75.8s for the next 500), 8-way parallel, 0 errors. This is
genuinely cheap and fast -- screening even the higher end of the
precision-adjusted estimates above (~1,700 paragraphs) would take on the
order of 4 minutes of wall-clock LLM time. Token cost was not metered
directly (`api_call.generate_response` discards `completion.usage`), but
at gpt-4o-mini's list pricing (order of $0.15/1M input + $0.60/1M output
tokens) and this prompt/response size, 903 calls is a low-single-digit-
cents-to-tens-of-cents cost, not a budget concern at any of the scales
discussed above. **Time/cost is not the constraint for Task 5 at
full scale -- classifier PRECISION is.**

## Task 5b: did the revised prompt actually fix precision?

Task 5's spot-check (above) found the raw classifier badly overcounted
Condition/Concession (~33-46% real precision against strict Mann &
Thompson definitions) via four recurring failure modes: causal
"because"/"since" mislabeled as Concession; purpose/goal clauses
mislabeled as Condition; past-tense narrative "when" mislabeled as
Condition; plain narrative contrast mislabeled as Concession.
`relation_classifier.py` was revised to add a negative example and a
checklist question for each failure mode, plus a "rationale" field the
model must write before choosing `relation_type` (see that file's
docstring for the exact revised prompt). The revised prompt was piloted
on a fresh, disjoint 900-paragraph batch (pool_index 903-1802; see
`logs/task5b_screening_log.jsonl` and
`results/task5b_revised_precision_report.json`), and the raw rates
dropped substantially:

| Relation | Old raw rate (903 paragraphs) | New raw rate (887 scored) |
|---|---|---|
| Condition | 8.6% (78/903) | 6.0% (53/887) |
| Concession | 13.5% (122/903) | 8.0% (71/887) |
| Elaboration | 9.1% (82/903) | 3.3% (29/887) |
| None | 68.8% (621/903) | 82.75% (734/887) |

A lower raw rate is ambiguous on its own -- it is equally consistent
with genuinely sharper filtering (fewer false positives) or with the
model just becoming more conservative across the board (fewer false
**and** true positives, no real precision gain). That distinction can
only be resolved by spot-checking the new hits against the same strict
definitions used before, which had not yet been done. This section does
that check.

### Methodology (mirrors Task 5's spot-check exactly, for comparability)

Every Condition hit (53/53) and every Concession hit (71/71) in
`logs/task5b_screening_log.jsonl` was read in full -- not a sample, per
this task's instruction to bias toward reading more given how much rides
on the answer -- and checked against the exact strict definitions used
throughout this track (Condition: satellite is a hypothetical, future,
or otherwise unrealized situation the nucleus's realization depends on;
Concession: nucleus and satellite present an apparent-but-not-actual
incompatibility, with the writer's positive regard for the nucleus
increasing once it's recognized they're actually compatible). Each hit
was scored **genuine** (clearly satisfies the definition), **borderline**
(a real argument either way), or **not genuine** (fails the definition --
whether via one of the four targeted failure modes or some other
mislabeling). Full detail and per-item failure-mode tags are in
`results/task5b_revised_precision_report.json`'s `spot_check` key.

**Same limitation as Task 5's original spot-check, stated with the same
plainness: this is a single-reviewer, non-independent read, done by the
same process that revised the classifier prompt. It is a directional
signal, not a validated inter-annotator metric, and it is NOT a
substitute for a real independent human audit** (still out of scope
here, same as it was for Task 5).

### Results

| | Old spot-check (Task 5) | New spot-check (Task 5b) |
|---|---|---|
| Condition | 15/78 hits reviewed; ~33-43% precision | **All 53/53 hits reviewed; 13 genuine, 5 borderline, 35 not genuine -- 24.5%-34.0% precision** |
| Concession | 24/122 hits reviewed; ~38-46% precision | **All 71/71 hits reviewed; 33 genuine, 5 borderline, 33 not genuine -- 46.5%-53.5% precision** |

**Which of the three possible outcomes happened: (c), something more
complicated -- not a clean win.** Specifically:

- **Concession's precision genuinely improved** (~38-46% -> ~46.5-53.5%,
  and on a full 71-hit review this time vs. the original's 24-hit
  sample, so it's the better-powered number of the two). The revision's
  negative example for plain narrative contrast and causal "because"
  did real, measurable work here.
- **Condition's precision did NOT improve** -- if anything it is
  flat-to-lower (~33-43% -> ~24.5-34.0%, again on a full 53-hit review
  vs. the original's 15-hit sample). The lower raw rate for Condition
  looks like added conservatism (fewer hits overall, including fewer
  *true* hits), not sharper filtering.
- **A subtler problem: precision and screening-efficiency are not the
  same thing, and this revision improved one while worsening the other
  for BOTH relations.** Because the raw rate fell so much (especially
  for Condition), the absolute number of CONFIRMED instances per
  paragraph screened is now lower than Task 5's original estimate for
  both relations -- Condition's confirmed rate is 1.47%-2.03% of scored
  paragraphs now vs. ~2.9-3.7% originally; Concession's is 3.72%-4.28%
  now vs. ~5.1-6.2% originally, DESPITE Concession's precision going up.
  A precision win doesn't help if recall drops by more.
- **A fifth failure mode dominates Condition's remaining errors, and it
  is not one of the four the revision targeted.** The model frequently
  identifies genuinely conditional-sounding language somewhere in a
  paragraph but pairs `nucleus`/`satellite` to clauses that don't
  actually stand in that dependency relation to each other --
  cross-sentence misattachment, sometimes compounded by an outright
  hallucinated connective (a stated `"if"` that appears nowhere in the
  source paragraph, e.g. pool_index 1108, 1148). This single bucket
  accounts for roughly a third of Condition's 35 non-genuine hits --
  larger than any of the four originally-targeted modes individually,
  post-revision. It was not addressed by this prompt revision at all.
  A close variant of the ORIGINAL pilot's already-documented "identical
  string extracted for both nucleus and satellite" bug also recurred --
  not byte-identical this time, but overlapping to the point of being
  circular (pool_index 1400: satellite is `"making it likely " +
  nucleus`, i.e. the nucleus text repeated verbatim inside its own
  satellite). A single, blatant Condition/Concession
  cross-category confusion also turned up (pool_index 1568: "Although
  radioactivity levels... decline, the longer-lived isotopes could pose
  risks..." -- textbook Concession, mislabeled Condition).

### Concrete before/after examples

**1. Condition / purpose clause (failure mode 2) -- fix works sometimes, not always.**

The revision explicitly warns against exactly this pattern ("to avoid
X", "in order to X" is the nucleus's motivation, not a precondition it
depends on). It correctly rejects it here:

> The Zion Evangelical Lutheran congregation was founded in 1755 **in
> order to serve the needs of Lutheran immigrants from Germany**, as
> well as Germans from Pennsylvania who moved to Baltimore.
> -- pool_index 999, "History of Baltimore" -- correctly labeled **None**
> ("explains the purpose of the congregation's founding, not a
> hypothetical or unrealized condition").

...but not here, on the same construction:

> **In order to prevent abuse of the system**, the majority of ranked
> games have relatively limited options for matchmaking.
> -- pool_index 1722, "Games for Windows – Live" -- INCORRECTLY labeled
> **Condition** ("the satellite presents a hypothetical situation about
> preventing abuse, and the nucleus's realization depends on this
> condition being met") -- almost a verbatim match to the prompt's own
> negative-example phrasing, missed anyway.

**2. Condition / past-tense narrative "when" (failure mode 3) -- the cleanest real win, with a near-cousin miss.**

> In the United Kingdom, ... **When BSB merged with Sky in November
> 1990** to form BskyB, the soap moved to Sky's flagship channel...
> **When BskyB's original three-year contract** to air the soap expired,
> Sky chose not to renew it.
> -- pool_index 1158, "The Young and the Restless" -- correctly labeled
> **None**, rationale explicitly: "contains several past-tense 'when'
> clauses that narrate completed events, which do not present
> hypothetical or unrealized situations, thus not qualifying as
> Condition." This closely mirrors the exact failure the original pilot
> flagged ("When the IAFE was transformed... in 1937") and looks like a
> genuine, substantial fix for this specific pattern.

But the identical underlying error (dated, completed, one-time
historical narration) still slips through when it isn't spelled with
the literal word "when":

> In 1889, a new, larger factory with a large foundry and a powerhouse,
> would be erected in Linden, **where** the firm's headquarters has been
> to this day.
> -- pool_index 1434, "Körting Hannover" -- INCORRECTLY labeled
> **Condition**. Suggests the fix is keyed fairly literally to the word
> "when" rather than the deeper category (narrated history vs. genuine
> hypothetical).

**3. Concession / plain narrative contrast (failure mode 4) -- still the single largest error bucket.**

> The "bad" kind promoted hatred of Jews because of their descent...
> The "good" kind criticized alleged Jewish conspiracies to control
> newspapers, banks, and other institutions...
> -- pool_index 1034, "Religious antisemitism" -- correctly labeled
> **None** ("contains a contrast... but it does not resolve an apparent
> incompatibility; rather, it presents a series of facts... without a
> governing structure that indicates a concession").

The model can clearly articulate that exact distinction when it works
-- and then doesn't apply it consistently:

> Chromium, unlike iron and nickel, does not suffer from hydrogen
> embrittlement. **However**, it does suffer from nitrogen
> embrittlement, reacting with nitrogen from air and forming brittle
> nitrides...
> -- pool_index 976, "Chromium" -- INCORRECTLY labeled **Concession**,
> rationale merely restates the contrast as if restating it were a
> resolution. Structurally near-identical to the "good kind/bad kind"
> example above, and one of 16 (of 33 non-genuine) Concession hits
> following this exact plain-contrast pattern -- the largest single
> bucket, at ~48%.

### Revised extrapolation to 50+ CONFIRMED instances

Recomputed against the same 887-scored-paragraph base, using this
spot-check's confirmed range (genuine, to genuine+borderline) rather
than the raw hit count:

| | New raw rate | New confirmed rate (precision-adjusted) | Paragraphs needed for 50 confirmed | For comparison, Task 5's original estimate |
|---|---|---|---|---|
| Condition | 6.0% (53/887) | 1.47%-2.03% (13-18/887) | **~2,464-3,412** | ~1,340-1,740 |
| Concession | 8.0% (71/887) | 3.72%-4.28% (33-38/887) | **~1,167-1,344** | ~810-990 |

Both numbers went **up**, not down, versus Task 5's already-cautious
estimate -- despite Concession's real precision improvement -- because
the raw-rate collapse outweighed the precision gain in the yield
calculation. Condition remains the bottleneck, and by a wider margin
than before: its confirmed rate (1.47-2.03%) is now below even Task 5's
original pessimistic estimate (2.9-3.7%).

**Recommendation: target ~3,500 screened paragraphs for the next
full-scale run**, sized to Condition (the binding constraint) rather
than Concession or the raw rate -- clearing Condition's ~2,464-3,412
requirement will clear Concession's ~1,167-1,344 requirement along the
way. This is roughly 4x this pilot's 900-paragraph batch, and is
**still cheap and fast**: at this pilot's observed throughput (900
paragraphs in ~385s wall-clock LLM time, 8-way parallel), ~3,500
paragraphs is on the order of 25 minutes. Do not use Task 5's
~1,300-1,700 figure or the raw-rate-only ~837 figure (from
`results/task5b_revised_precision_report.json`'s un-adjusted
extrapolation) to size the next run -- both are now demonstrably too
low. Before committing real screening effort at this scale: (1) get an
actual independent human audit sample -- both this and Task 5's
spot-check remain single-reviewer, non-independent reads; (2) strongly
consider fixing the nucleus/satellite misattachment problem identified
above in `relation_classifier.py` first, since it is now the largest
single Condition error source and this revision did not address it at
all.

## Task 7: full-scale run -- screening, Experiment 1/2, and the paper's main empirical claim

Full-scale continuation of the validated pipeline (2026-08). Promotes the
human-audit-validated revised `check_4` wording to the pipeline's default,
screens fresh paragraphs to comfortably clear 50+ Stage-2-confirmed
Condition and Concession instances, then builds and scores the
Experiment 1/2 sample this whole track exists to produce. **This is the
first point in this track where the paper's actual empirical claims get
tested**, not just pipeline-validation numbers.

### Default promotion: revised `check_4`

`verification_classifier.verify_candidate()`'s `prompt_builder` now
defaults to `build_verification_prompt_check4_revision` instead of the
original `build_verification_prompt`, per the completed human audit
(`manual_concession_audit.md` / `manual_concession_audit_manifest.json`,
tallied by `tally_manual_concession_audit.py`): on a stratified 26-item
sample, the revised wording agrees with independent human judgment
**84.6% of the time (22/26)** vs. **46.2% (12/26)** for the original
wording. The original function is unchanged and stays fully usable via an
explicit `prompt_builder=build_verification_prompt` argument (e.g.
`run_check4_revision_experiment.py` still uses it that way) -- it has just
stopped being the default. Every Stage-2 log record now also carries a
`verification_prompt_version` field (`"original"` / `"check4_revision"` /
`None` for pre-promotion records that predate the field) precisely because
`logs/task6_stage2_log.jsonl` now spans both eras: pool_index 1803-2802
was verified under the original wording (Task 6's validation batch,
unchanged/not re-verified here), pool_index >= 2803 (this task's fresh
screening) is verified under the revised wording by default.

**New helper, `confirmed_pool.py`**, exists specifically to paper over one
resulting accounting subtlety so nothing downstream has to re-derive it:
the validated revised-wording verdicts for the OLD Concession batch
(pool_index 1803-2802) live only in the separate
`logs/task6_stage2_concession_check4_revision_experiment.jsonl` (57/85
confirmed there), never in the main `task6_stage2_log.jsonl` (which shows
confirmed=False for all 85, per the original-wording run that actually
produced that log). `confirmed_pool.get_confirmed_concession()` unions
both sources by pool_index (with an explicit conflict-assertion, never a
silent preference) so "the Stage-2-confirmed Concession set" always means
the same, correct thing everywhere in Task 7. Condition needed no such
union (check_4 is a Concession-specific check; it triggered on only 2/48
Condition verifications in the validation batch).

### Task 1: full-scale screening

Verified against existing logs before starting (per task instructions,
not assumed): `task5_screening_log.jsonl` = pool_index 0-902,
`task5b_screening_log.jsonl` = 903-1802, `task6_stage1_log.jsonl` =
1803-2802 -- so pool_index 2803 was confirmed genuinely fresh. Also
verified directly (per task instructions) that `data_cache/train.jsonl`'s
`targets` field parses as a non-empty list of proposition strings across a
sample of rows before relying on it as Condition A's source.

Screened **pool_index 2803-5352 (2,550 fresh paragraphs)** in three
batches (50 / 1,000 / 1,500) with the two-stage pipeline
(Stage 1 gpt-4o-mini -> Stage 1.5 free grounding filter -> Stage 2 gpt-4o,
now defaulting to the revised `check_4`), then ran
`--retry-stage2-errors` once to recover Stage-2 calls that had exhausted
`generate_response`'s built-in rate-limit retry (a real, expected,
non-silent failure mode at this call volume -- sustained 429s were
routinely visible in the raw run logs; every one that mattered was
resolved by the retry pass, 0 Stage-2 errors remaining in the final logs).

| | Cumulative (two-stage pipeline, pool_index 1803-5352) | This task's fresh screening only (pool_index 2803-5352) |
|---|---|---|
| Paragraphs screened | 3,550 | 2,550 |
| Scored (no Stage-1 error) | 3,514 | ~2,514 |
| Condition raw hits | 214 | 155 |
| Condition Stage-2 confirmed (main log, any wording) | 75 | 59 (+16 from the validation batch, original wording) |
| Concession raw hits | 293 | 201 |
| Concession Stage-2 confirmed (**authoritative, union with the revision-experiment log**) | **197** | 140 (+57 from the validation batch, revised-wording re-verification) |

**Final authoritative confirmed counts (`confirmed_pool.py`, what Task 2
actually builds from): Condition = 75, Concession = 197.** Both comfortably
clear the 50+ target and the 60-70 "comfortable margin" band the task
brief asked for -- Concession by a wide margin (it was already close to
target from the validated batch's revised-`check_4` re-verification alone;
Condition was the true bottleneck and needed the bulk of this task's fresh
screening, consistent with every prior extrapolation in this track
flagging Condition, not Concession, as the binding constraint). Screening
stopped once both cleared this band -- not run to exhaustion, per the task
brief's "use judgment" instruction. Elaboration availability (a byproduct
of Stage 1 classifying every screened paragraph): 222 raw hits accumulated
across all screening in this track to date.

Full detail: `results/task7_full_scale_screening_report.json`
(`finalize_task7_screening_report.py`), raw logs unchanged in
`logs/task6_stage1_log.jsonl` / `task6_stage1_5_log.jsonl` /
`task6_stage2_log.jsonl` (all pool-index-keyed, resumable, per Task 6's
existing convention -- this task only ever appended to them).

### Task 2: the Experiment 1/2 sample

**Condition A** ("standard atomization"): looked up directly from
`data_cache/train.jsonl`'s `targets` field by pool_index (via
`download_data.get_classifier_pool(shuffled_records())`, the same
deterministic pool every script in this track indexes into) -- Chen et
al.'s own already-released Propositionizer checkpoint output. No model was
run. A hard assertion (`run_experiment_1_2._condition_a_lookup`) refuses
to score severance if the freshly-looked-up record's `content` doesn't
byte-for-byte match what Stage 1/2 logged for that pool_index, so a silent
pool/index drift can't corrupt this join.

**Condition B** ("elicitation-then-atomize", new for this task --
`condition_b_atomizer.py`): one gpt-4o-mini call per governing paragraph,
given the bare paragraph plus its already-elicited Stage-1/2 relation
(type/nucleus/satellite/connective) and instructed to atomize into
self-contained propositions while explicitly preserving or flagging that
relation -- conceptually mirroring `../atomization_conditions.py`'s
Condition B, reimplemented fresh here because the input is a whole
multi-sentence paragraph, not one sentence (self-contained/pronoun-
resolution guidance, in particular, needed paragraph-appropriate wording).
Ran clean: 0 atomization call/parse errors across all 272 paragraphs.

**Two confounds are real here and are not papered over:**
1. **Model choice.** Condition A is Chen et al.'s small fine-tuned
   FLAN-T5-large Propositionizer checkpoint; Condition B is gpt-4o-mini,
   zero-shot prompted. A vs B differences here are NOT a clean same-model
   ablation the way the CFR track's A/B (both gpt-4o-mini) arguably was --
   they conflate elicitation-awareness with a real capability/training
   difference. The task brief anticipated this and asked for it to be
   reported, not resolved (this project does not train or fine-tune a
   "relation-aware Propositionizer").
2. **Input shape.** Condition B sees only the bare paragraph `content`
   string -- the same view Stage 1/2's relation elicitation saw -- NOT the
   `"Title: X. Section: Y. Content: Z."` string the real Propositionizer
   was trained on and given for Condition A (see Task 3's prompt-format
   resolution above). Chosen so that, within Condition B, the relation is
   elicited from and atomized from identical text; the alternative (giving
   B title/section too) would have introduced a THIRD variable inside one
   condition instead of an already-disclosed one between conditions.

**Elaboration control**: Stage-1 raw Elaboration hits (this track has no
Stage-2-equivalent verification for Elaboration, matching the parent CFR
track's own Elaboration-is-Condition-A-only design), filtered to grounded,
then all available used (target size of 272 not reached). **The grounding
filter deliberately does NOT reuse Condition/Concession's full Stage 1.5
bar**: checking the actual data found 139 of 177 raw Elaboration hits (at
the time of this check) have `connective=None` -- not hallucination, but
the normal, expected case, since RST Elaboration frequently has no lexical
marker at all (unlike "although"/"if"). Requiring `connective_grounded`
(which `is_grounded(None, ...)` correctly always fails) would have
discarded ~80% of otherwise-good Elaboration hits for a non-reason; this
was caught before spending any LLM calls on a needlessly starved control
sample. The filter actually used requires `satellite_grounded` AND
`nucleus_grounded_diagnostic_only` (176/177 and effectively all pass
respectively), not connective groundedness. Final control sample: **206**
paragraphs (222 available, 16 excluded as ungrounded on this stricter-
than-nothing-but-looser-than-Stage-1.5 bar).

**Final sample: 272 governing paragraphs (75 Condition + 197 Concession)
+ 206 Elaboration control.**

### Task 3: severance scoring and the two experiments

Severance judge (`severance_judge_paragraph.py`) adapts
`../severance_detection.py`'s `judge_prompt_full_nucleus` design --
identical question ("reading ONLY the atomized output, not the original
text, would a reader still correctly understand the satellite-governs-
nucleus relationship?") and identical `Condition`/`Concession`/
`Elaboration` relation descriptions, verbatim -- retargeted from
"sentence"/"claims" to "paragraph"/"propositions". Only the LLM-judge was
reused/adapted, not `rule_based_severance` (a CFR/regulatory-connective-
wordlist-tuned proxy never validated on Wikipedia prose; the task brief's
own framing of the judge question is specifically the LLM-judge's
question, and introducing an un-validated second metric risked a silently
miscalibrated number rather than reused, validated infrastructure). Model:
gpt-4o-mini (matches `../severance_detection.py`'s own default).

#### Experiment 1 (capacity-vs-elicitation ablation): A vs B

| Relation | N | Severed under A | Severed under B |
|---|---|---|---|
| Condition | 75 | 13/75 (17.3%) | 12/75 (16.0%) |
| Concession | 197 | 96/197 (48.7%) | 48/197 (24.4%) |
| **Pooled** | **272** | **109/272 (40.1%)** | **60/272 (22.1%)** |

- "Correctly elicited but still severed under B" (same metric definition
  as the CFR track's headline number: `severance_b.preserved is False`,
  not conditioned on A): **60/272 (22.1%)**. The failure mode the CFR
  track's Experiment 1 flagged **does appear here too** -- explicit
  relation-awareness prompting does not fully close the gap -- but at a
  much lower rate than CFR's 26/47 (55.3%).
- Condition B atomization: 0 call/parse errors across all 272 paragraphs.

**This does NOT replicate the CFR track uniformly, and that is reported
plainly rather than smoothed over: Concession replicates the CFR-track
direction (A > B, explicit awareness helps substantially -- roughly
halves severance, 48.7% -> 24.4%, similar in spirit to CFR's 92.3% ->
76.9% though starting from a much lower base here); Condition does
NOT (17.3% -> 16.0%, essentially flat / within noise at this N) --
sharply unlike CFR's Condition, where relation-aware prompting cut
severance nearly in half (79.4% -> 47.1%).** The likely reason is visible
directly in the structural comparison below: Condition A's baseline
severance is already low here (17.3%, vs. CFR's 79.4%), leaving B little
room to improve on -- a ceiling/floor-effect explanation, not evidence
that elicitation-awareness "doesn't work" for Condition in general.

#### Experiment 2 (relation-type-stratified severance vs. Elaboration control) -- the paper's main empirical claim

This is Condition-A output only (Chen et al.'s own trained checkpoint, on
its own in-domain training data) -- the best-case scenario for the
null hypothesis that severance is just an artifact of using an
out-of-domain, general-purpose LLM as the atomizer.

| Relation type | N | Severed (Condition A) |
|---|---|---|
| Condition | 75 | 13/75 (17.3%) |
| Concession | 197 | 96/197 (48.7%) |
| **Governing pooled (Condition+Concession)** | **272** | **109/272 (40.1%)** |
| Elaboration control | 206 | 6/206 (2.9%) |

- **Fisher's exact test: p = 1.36e-24** (odds ratio 22.3). Chi-square:
  p = 1.34e-20.
- **The RST-predicted failure mode appears even under best-case in-domain
  conditions.** Chen et al.'s own purpose-trained Propositionizer, decoding
  its own training-domain paragraphs, still severs governing relations at
  ~13.8x the rate of the Elaboration control (40.1% vs. 2.9%) -- an even
  larger relative gap than the CFR track found with a general-purpose LLM
  atomizer on out-of-domain regulatory text (83.0% vs. 24.4%, ~3.4x). The
  absolute severance rate is considerably LOWER here than in the CFR track
  (40.1% vs. 83.0% pooled) -- but the control's baseline is also much
  lower (2.9% vs. 24.4%), so the qualitative claim this experiment exists
  to test (governing relations severed at a materially higher rate than a
  non-governing control) is not just replicated but sharpened: it survives
  the single best-case objection ("maybe it's just because the atomizer is
  out-of-domain/general-purpose") that could have been raised against the
  CFR-track-only result.

#### No-split diagnostic (bonus, mirrors `../audit_severance.py`'s A2 audit)

Computed post-hoc, no new LLM calls, from data already collected
(`no_split_diagnostic.py`, appended to
`results/task7_experiment_1_2_report.json`'s `no_split_diagnostic` key).
Checks whether a "severed" verdict is a real atomization failure or a
judge/prompt category error against an atomizer that did not actually
split anything:

| | Condition A | Condition B |
|---|---|---|
| No-split (joined output ~= source, ratio >= 0.95) | 3/272 | 68/272 |
| ...of which STRICT (single proposition) | 0 | 11 |
| STRICT no-split yet scored severed=True | 0 | **5** |
| Any no-split yet scored severed=True | 3 | 19 |

Condition A (Propositionizer) essentially never returns a no-split output
(it always decomposes -- see propositions-per-paragraph below), so this
category error barely exists for A here (unlike the CFR track, where
Condition A's production atomizer had 16/47 no-split, 6 STRICT). Condition
B does show the same category error the CFR track flagged, at a much
smaller relative scale: of B's 60 "severed" verdicts, 5 (8.3%) are STRICT
single-proposition outputs that are near-verbatim copies of the source
paragraph -- nothing was split, so nothing was severed by omission, and
the judge's severed=True there is a prompt-calibration artifact, not an
atomization-capacity finding. Concrete example: pool_index 2965
("Survivin", Condition) -- Condition B's third proposition is the
ENTIRE original sentence, connective included, returned verbatim
alongside two split-out halves; the judge still scored it severed=False.
**Net effect on the headline numbers: small.** Even generously excluding
all 19 "any no-split yet severed" cases from Condition B's 60 severed
paragraphs, B's severed count would still be 41-60 (15.1%-22.1%) --
directionally unchanged from the 22.1% reported above, so this caveat
qualifies but does not overturn Experiment 1's B-column numbers.

#### Qualitative comparison: Propositionizer vs. gpt-4o-mini atomization

Reportable difference the task brief asked to flag if present -- it is
present, and it runs in two different directions for two different
things:

| | Condition A (Propositionizer) | Condition B (gpt-4o-mini) |
|---|---|---|
| Avg. propositions / paragraph (overall, n=272) | **9.06** | 7.05 |
| ...Condition paragraphs only | 8.45 | 7.07 |
| ...Concession paragraphs only | 9.29 | 7.04 |
| Elicited connective survives verbatim in >=1 output proposition (overall) | **23.5%** (64/272) | 100% (272/272, by construction) |
| ...Condition paragraphs only | **76.0%** (57/75) | 100% |
| ...Concession paragraphs only | **3.6%** (7/197) | 100% |

Two findings, neither smoothed over:

1. **Propositionizer produces MORE propositions per paragraph than
   gpt-4o-mini's relation-aware atomizer** (9.06 vs. 7.05) -- it is the
   more finely-grained decomposer of the two here, not the coarser one,
   despite being the much smaller model. Plausible reading: Propositionizer
   was trained specifically to maximize atomic factual decomposition with
   no other instruction competing for its behavior, whereas Condition B is
   explicitly told to protect a relation, which visibly trades off against
   maximal splitting (consistent with the no-split findings just above).
2. **Propositionizer's connective survival is sharply asymmetric by
   relation type, and this by itself is a large part of why its Condition
   severance (17.3%) is so much lower than its Concession severance
   (48.7%).** It keeps the elicited connective intact 76% of the time for
   Condition ("if"/"when"-type satellites) but only 3.6% of the time for
   Concession ("although"/"but"/"despite"-type satellites). A plausible
   mechanism (offered as a hypothesis, not confirmed by this data): a
   conditional satellite like "If X" often does not stand alone as a
   complete, independently-true assertion the way a concessive satellite
   like "Although X" does (X itself is usually already a complete,
   grammatical, fact-bearing clause) -- so a model trained to extract
   independently-true atomic facts has much less pressure to split a
   conditional apart, and correspondingly more pressure to split a
   concessive one, incidentally preserving the former's connective far
   more often than the latter's. This asymmetry, not a general "Condition
   relations are inherently easier to preserve" property, looks like the
   actual driver of Experiment 2's per-relation-type gap under Condition A.

### Illustrative examples (full records in `logs/task7_experiment_govern_log.jsonl`)

**[Condition, preserved under both A and B]** pool_index 1814, "Gospel of
Barnabas": satellite "If true," / connective "If". Propositionizer's last
proposition is `"If true, this would also support an Italian origin for
the Gospel of Barnabas."` -- kept fully intact, connective included.

**[Concession, severed under A, preserved under B]** pool_index 1964,
"Same-sex marriage": connective "Rather". Propositionizer splits the
satellite and nucleus into two separate, connective-free propositions (no
"however"/"rather"/contrast marker survives anywhere); gpt-4o-mini's
relation-aware atomizer keeps them as two propositions but explicitly
re-attaches "Rather, ..." to the nucleus, and the judge scores it
preserved.

**[Concession, severed under BOTH A and B -- "correctly elicited but
still severed"]** pool_index 2004, "Miga, Quatchi, Sumi and Mukmuk":
connective "However". Condition A splits the criticism out as an
independent fact with no contrast marker. Condition B keeps "however" in
one joined proposition, but the judge still scores it severed --
reasoning that the surviving "however" now reads as undermining the
nucleus rather than being conceded without defeating it, a subtler
failure than simply dropping the connective.

**[Condition, severed under both A and B, and a no-split category error
for B]** pool_index 2965, "Survivin": Condition B outputs the two split
halves PLUS a third proposition that is the entire original sentence
verbatim, connective included -- and the judge still scores it severed.
See the no-split diagnostic above.

### New files this task added (all inside `factoidwiki_track/`)

- `confirmed_pool.py` -- authoritative Stage-2-confirmed Condition/
  Concession sets (handles the check_4-wording-era split for Concession)
  plus the available Elaboration pool.
- `condition_b_atomizer.py` -- Task 2's new elicit-then-atomize prompt/call
  for paragraph-level input.
- `severance_judge_paragraph.py` -- paragraph-adapted LLM severance judge
  (`judge_prompt_full_nucleus` design, retargeted from sentence/claims to
  paragraph/propositions).
- `run_experiment_1_2.py` -- Task 2+3 orchestration: builds the sample,
  scores severance under A and B, runs both experiments' statistics.
- `no_split_diagnostic.py` -- bonus post-hoc audit, mirrors
  `../audit_severance.py`'s A2 design.
- `finalize_task7_screening_report.py` -- writes
  `results/task7_full_scale_screening_report.json` from the accumulated
  logs (no new LLM calls).

Full machine-readable results:
`results/task7_full_scale_screening_report.json` (Task 1) and
`results/task7_experiment_1_2_report.json` (Tasks 2-3, including the
`no_split_diagnostic` key). Raw per-paragraph logs:
`logs/task7_experiment_govern_log.jsonl` (272 records, both conditions'
full propositions + both severance verdicts) and
`logs/task7_experiment_elaboration_log.jsonl` (206 records).

## Task 8: Experiment 3 (repair reliability) -- six recovery/deferral arms on the 109 severed-under-A cases

This track's first Experiment 3, built from scratch (2026-08). Mirrors
`../exp3_recovery_comparison/`'s CFR-track design as closely as this
track's paragraph-level input shape allows -- fixed eval set derived
programmatically from already-saved verdicts (never resampled), the same
`severance_judge_paragraph.py` scoring methodology Experiment 1/2 used,
and the same flagged-deferral cross-tab design -- extended with two arms
the CFR track's version does not have (Contextual Retrieval context
injection; a parent-segment ceiling/reality-check arm) and a
confidence-calibration/hedging field the project owner explicitly asked
to add to Experiment 3. **Headline result: this run could not be
scored.** `OPENAI_API_KEY` (`server/.env`) has a zero credit balance, so
every LLM call in arms 2-5 failed -- confirmed conclusively (see
"Execution status" below), not guessed at. What follows reports exactly
what is and is not real.

### Evaluation set (fixed, derived, never resampled)

**109 cases**: every governing (Condition/Concession) paragraph
Experiment 1/2 already scored `severance_a.preserved == False` under
Condition A, read directly from `logs/task7_experiment_govern_log.jsonl`
(`exp3_dataset.derive_eval_set`) -- **13/75 Condition + 96/197 Concession
= 109/272**, matching Task 7's own numbers above exactly (asserted
programmatically: the derivation function hard-fails if the source log's
severed counts ever drift from these). `severance_a` verdicts are reused
byte-for-byte; this task never resamples or recomputes severance.

### Six arms

1. **No elicitation** -- Condition-A's real Propositionizer output +
   Experiment 1/2's saved judge verdict, reused directly, zero
   regeneration. By construction, **109/109 severed** here (confirmed):
   the baseline.
2. **Disco-RAG adapted** (`disco_rag_paragraph_adapter.py`) -- the SAME
   released Disco-RAG code `../exp3_recovery_comparison/`'s own arm 1
   exercises (vendor/Disco-RAG, commit `0755104`), read directly and
   read-only from that directory's already-vendored copy (not
   re-vendored a second time -- see the module's docstring for why),
   retargeted from the CFR track's sentence/claim vocabulary to this
   track's paragraph/proposition vocabulary. Retrieval and the
   inter-chunk rhetorical graph are bypassed for the same reason as the
   CFR track's adapter: one paragraph is not a corpus to query, and the
   graph is empty by construction with one chunk (the released
   pipeline's own supported `use_graph=False` path). **"Disco-RAG
   released code (commit 0755104) with gpt-4o-mini substituted for the
   published Llama-3.3-70B backbone; NOT an evaluation of Disco-RAG as
   published."**
3. **Custom fallback** (`custom_fallback_paragraph.py`) -- mirrors
   `../exp3_recovery_comparison/custom_fallback.py`'s design: auto-
   rewrites Condition-A's atomized propositions using the saved Stage
   1/2 relation-elicitation record (type/nucleus/satellite/connective),
   no human review, no access to the source paragraph (a pure downstream
   corrector operating only on the pipeline's saved artifacts). NOT
   Disco-RAG, NOT a reproduction of HCA (Fan et al. 2023; corpus/weights
   unreleased).
4. **Contextual Retrieval context injection** (`contextual_retrieval_context.py`,
   new -- no CFR-track analog) -- adapts Anthropic's published Contextual
   Retrieval technique ("Introducing Contextual Retrieval", 2024) to
   single-proposition discourse-relation recovery instead of its original
   retrieval-recall purpose. Chen et al.'s Propositionizer atomizes one
   paragraph into ~9 propositions on average (Task 7's structural
   comparison); applying Contextual Retrieval to literally every one of
   them per case would have cost ~9x every other arm's generation budget
   for no proportionate benefit, so exactly ONE proposition per case --
   the one with highest token overlap against the elicited `nucleus`
   text, selected deterministically at zero LLM cost
   (`select_target_proposition`; **mean overlap 0.650, median 0.625, min
   0.125, max 1.0 across all 109 real cases, never zero** -- this part
   ran for real regardless of the billing block, since it costs no API
   call) -- receives the LLM-generated situating-context sentence, using
   the exact framing the task brief quoted ("generate a short, succinct
   context to situate this proposition within its source paragraph").
   Scored the same way as every other arm: the full proposition list,
   target substituted in, run through the severance judge -- this IS the
   "check whether the generated context states the missing relation" the
   task brief asked for, kept commensurable with arms 2/3/5 rather than
   introducing a separate ad hoc check.
5. **Parent-segment fallback** -- the full source paragraph in place of
   Condition-A's split propositions. Ceiling/reality-check arm, not a
   competitive one: nothing was split, so recovery is close to trivial by
   construction. **Whether that construction actually holds could not be
   checked this run** -- its judge call is blocked exactly like every
   other arm's (see below).
6. **Flagged deferral** -- `server/components/risk_triage.py`'s
   detectors, imported UNMODIFIED, run per Condition-A proposition with
   `segment_text` = the source paragraph. Surfaces cases for human
   review; incorporates nothing automatically. **Zero LLM cost -- this
   arm is the one fully real, fully scored result in this run** (see
   Results below).

### Scoring design (as specified; NOT exercised this run -- see Execution status)

Arms 2-5 are judged with the SAME `severance_judge_paragraph.py`
methodology as Experiment 1/2 (identical judge prompt/model), then
classified into exactly three buckets
(`exp3_scoring_paragraph.classify_failure_type`): **correct** (relation
preserved) / **dangerous_failure** (relation absent but the output reads
complete/fluent/authoritative -- no visible sign anything is missing) /
**detectable_failure** (relation absent and the output looks incomplete,
truncated, or hedged). The dangerous-failure rate is designed to be
reported separately per arm, never folded into a combined "incorrect"
bucket. For every dangerous_failure/detectable_failure case in arms 2-4
(not arm 5), an independent confidence-calibration classification
(`exp3_scoring_paragraph.classify_hedging_calibration`) checks the arm's
own output for hedging/uncertainty language -- deliberately never reusing
`risk_triage.py`'s rule-based hedge detector, so the "could the model's
own uncertainty have substituted for the classifier" comparison stays
non-circular. None of this machinery produced a single scored case this
run (0 judge calls succeeded) -- it is unexercised on real data, not
broken; see the stub-based unit test evidence in "Execution status."

### Execution status: BLOCKED on OpenAI billing, confirmed multiple ways, not a code bug

**`OPENAI_API_KEY` (`server/.env`) has a zero credit balance.** Every
call fails with HTTP 429 `insufficient_quota` / `credit_balance_exhausted`
("You have no credits remaining. Add credits to continue using the API
at https://platform.openai.com/settings/organization/billing/."). This
was confirmed, not assumed, in five independent ways before any number in
this section was written off as unobtainable:

1. A standalone direct call to `generate_response` before any Task 8 code
   existed.
2. A raw `openai.OpenAI(...)` client call with `max_retries=0` (rules out
   a transient per-minute rate limit masquerading as something worse).
3. A live 2-case smoke test through this task's actual orchestrator
   (`run_experiment_3.py --limit 2`) -- captured the identical error
   in-situ in arm 2's `error` field.
4. A live, full, unmodified 109-case run, backgrounded -- reached
   **50/109 cases before being stopped; 715/715 attempted LLM calls in
   that run's own log failed with this identical error, zero exceptions,
   zero successes.**
5. One more fresh direct check, timestamped immediately before the final
   report was produced, reproducing the identical error.

This diagnosis was also independently reached by a parallel agent working
the sibling `../exp3_recovery_comparison/` extension at the same time,
against the same account.

**What this means for the numbers below:** continuing to wait for, or
re-attempt, live LLM calls against a confirmed zero-balance account
cannot succeed and was stopped rather than run to a slow, foregone
conclusion (the live 109-case run was on pace for ~20+ minutes to grind
through retry-exhaustion on every single call). Every case's LLM-blocked
fields were therefore short-circuited -- via the REAL, unmodified
`run_experiment_3.process_case`/`build_summary` code, with only the
network boundary stubbed to return exactly what a real call against this
key would return (nothing/an exception), never a fabricated success --
rather than independently re-confirming the identical already-proven
outcome roughly 700 more times. Every such field is tagged with the
distinct error code `blocked_api_quota_exhausted_not_reattempted`, never
conflated with an organic per-case failure code
(`no_response`/`unparseable_json`). This methodology, and exactly which
fields are real vs. short-circuited, is recorded in the JSON report's own
`offline_reconstruction_note`. Separately, the two classifiers Task 8
adds (`exp3_scoring_paragraph.classify_failure_type` and
`classify_hedging_calibration`) were verified correct via stub-based unit
tests with `generate_response` mocked (not live data, but real assurance
the cascade logic -- judge -> failure-type -> calibration, and the
`run_calibration=False` short-circuit for arm 5 -- behaves as designed;
see the task's own working notes) -- they simply never got to run against
a live judge verdict this session, because no judge call ever succeeded.

**To reproduce with real scores once credits are restored:**
```
venv/bin/python server/scripts/discourse_severance/factoidwiki_track/run_experiment_3.py
```
No code changes are needed -- the exact same command that ran this
session will produce live-scored numbers once `OPENAI_API_KEY` has a
non-zero balance.

### Results

**Real, for all 109 cases (zero LLM cost, unaffected by the billing block):**

| | Value |
|---|---|
| Arm 1 (no elicitation) severed | **109/109 (100.0%)** -- by construction |
| Arm 6: cases with ANY risk-triage flag on the Condition-A output | **60/109 (55.0%)** |
| Arm 6: cases with a SEGMENT-level flag (`segment_nested_conditional`/`segment_negation_scope`) | **37/109 (33.9%)** |
| Arm 6: flag-type case counts | `hedge` 32, `segment_negation_scope` 37, `negation_scope` 10, `unresolved_reference` 5, `segment_nested_conditional` 2, `cross_reference` 1 |
| Arm 4: target-proposition selection overlap (deterministic, all 109 cases) | mean 0.650, median 0.625, min 0.125, max 1.0 (never zero) |

Read plainly: **flagged deferral alone, with zero LLM calls, already
surfaces a flag on 55.0% of the paragraphs where the real Propositionizer
severed a governing relation** -- a real, standalone finding about this
track's data, independent of whether any automated-repair arm can be
scored this run. Whether that 55.0% concentrates on the cases the
repair arms would get dangerously wrong (the actual point of the
cross-tab this task was asked to build) is exactly the question arms 2-5
being blocked leaves unanswered this session.

**Blocked (0/109 scored, every case, all four criteria):**

| Arm | n scored | Correct | Dangerous failure | Detectable failure |
|---|---|---|---|---|
| 2. Disco-RAG adapted | 0/109 | -- | -- | -- |
| 3. Custom fallback | 0/109 | -- | -- | -- |
| 4. Contextual Retrieval | 0/109 | -- | -- | -- |
| 5. Parent-segment fallback | 0/109 | -- | -- | -- |

Confidence-calibration (hedging) rates on failures: **not computable --
zero failures were scored in any arm** (the classifier only runs on cases
already scored dangerous/detectable, and none exist yet). Concrete
dangerous-failure examples: **zero available**, for the same reason --
none is invented in their place.

**Flag-coverage cross-tab (arm 6 vs. each automated arm's dangerous
failures):** the cross-tab machinery itself is real, tested, and safe on
zero data (verified: `0/0` reported as `null`, not a crash or a
misleading `0%`) -- but with 0 dangerous-failure cases in every arm this
run, every coverage/false-alarm cell is genuinely `0/0` (undefined), not
a small-but-real number. This is the honest state of the cross-tab this
session, not a rounding artifact.

### New files this task added (all inside `factoidwiki_track/`)

- `exp3_dataset.py` -- fixed 109-case Experiment 3 eval-set derivation
  from `logs/task7_experiment_govern_log.jsonl`, asserted counts.
  **Exercised for real, correct** (109 cases, 13+96, confirmed).
- `disco_rag_paragraph_adapter.py` -- arm 2: Disco-RAG's released code
  (read read-only from `../exp3_recovery_comparison/vendor/Disco-RAG`),
  retargeted to paragraph/proposition input. Object construction and
  vendor-code import path verified real; generation blocked.
- `custom_fallback_paragraph.py` -- arm 3: the custom elicit-then-rewrite
  fallback, mirroring `../exp3_recovery_comparison/custom_fallback.py`.
  Generation blocked.
- `contextual_retrieval_context.py` -- arm 4: Contextual Retrieval
  context injection, adapted to single-proposition recovery (new, no
  CFR-track analog). `select_target_proposition` exercised for real on
  all 109 cases (see Results); context-generation call blocked.
- `exp3_scoring_paragraph.py` -- the dangerous-vs-detectable failure-type
  classifier (mirrors `../exp3_recovery_comparison/exp3_scoring.py`) plus
  the new confidence-calibration/hedging classifier. Verified via
  stub-based unit tests (mocked `generate_response`), never against live
  data this session.
- `run_experiment_3.py` -- Task 8 orchestration: runs all six arms on the
  109-case set, scores, cross-tabs against arm 6's flags, writes
  `results/task8_factoidwiki_exp3_report.json`. Arm 5 (parent-segment)
  and arm 6 (flagged deferral) are implemented inline here (trivial
  construction / a thin wrapper around the existing
  `risk_triage.flag_claim`) rather than as separate modules. Supports
  `--limit N` for smoke-testing without running the full 109-case set.

Full machine-readable results:
`results/task8_factoidwiki_exp3_report.json` (full per-case records, all
six arms, including the `execution_note` and `offline_reconstruction_note`
fields documenting exactly what is real vs. blocked in this run).

# Audit addendum (2026-08-14): nucleus-bundling (A1) audit, ported from `../audit_severance.py`

Post-hoc audit of the SAVED Task 7 results above, run by
`audit_nucleus_bundling.py`. **All Task 7 numbers above, and everything
in `results/task7_experiment_1_2_report.json`, are untouched** -- the
figures below are a secondary, sub-clause-scoped alternative reading
reported alongside them, not a replacement. Machine-readable results:
`results/task7_nucleus_bundling_audit.json`. No screening, relation
elicitation, or atomization was re-run; the only new LLM calls made were
26 sub-clause-scoped judge calls (13 bundled records x 2 conditions,
gpt-4o-mini, temperature=0, seed=13 -- `api_call.generate_response`'s
own defaults, same as every other LLM call in this project).

This is the FactoidWiki-track port of the CFR track's A1 audit -- see
`../RESULTS.md`'s "Audit addendum (2026-08-07)" for the original design
and CFR-track numbers. **A2 (severed-with-no-split) is out of scope
here**; it was already ported separately as `no_split_diagnostic.py` --
see the "No-split diagnostic" subsection under Task 7 above. This
addendum covers A1 only.

## Why this audit exists

The primary severance judge (`severance_judge_paragraph.py`) scores
severance against the FULL elicited nucleus. When that nucleus bundles
two coordinated, independently-governed assertions and the satellite
only ever governed one of them, a "severed" verdict can be an artifact
of judging against too much text, not a real atomization failure. This
audit (1) flags bundled nuclei with a documented structural heuristic,
(2) checks (read-only) where the elicited connective attached in the
saved atomized output, (3) re-judges ONLY the bundled subset with a
sub-clause-scoped judge, and (4) reports adjusted secondary severed
rates.

## Reuse, not re-implementation -- the one exception to this track's self-containment rule

Every other script in this directory (see `env_utils.py`'s docstring)
deliberately avoids importing from outside `factoidwiki_track/`, so the
whole track stays self-contained and safely deletable/movable as a
unit. `audit_nucleus_bundling.py` is a narrow, documented exception: it
imports (does not re-implement) `../audit_severance.py`'s
bundling-detection functions (`detect_bundling_sites`,
`choose_bundling_site`, `assign_governed_subclause`,
`connective_attachment`) and `../severance_detection.py`'s
already-validated `llm_judge_severance_subclause`, rather than copying
~250 lines of regex/heuristic logic and a once-iterated judge prompt
into a second, driftable copy. See the script's module docstring for
the full reasoning. Nothing else about this track's self-containment
changed -- screening, elicitation, atomization, and the primary
severance judge remain exactly as self-contained as before; only this
bonus audit script reaches across the directory boundary.

## Does the CFR-tuned heuristic transfer to Wikipedia prose?

Yes, unmodified -- **no wordlist or rule changes were made.** The
heuristic was run as-is against all 272 elicited nuclei (75 Condition +
197 Concession).

**Bundled nuclei: 13 of 272 (4.8%) -- 12 clear, 1 borderline.** Lower
than the CFR track's 8/47 (17.0%), which is the expected direction:
Wikipedia narrative prose has less of CFR's list-heavy, multiply-
coordinated regulatory sentence structure. Every one of the 13 catches
came from the heuristic's two REGISTER-NEUTRAL rules -- (a)
"a_second_full_predicate" (a modal/auxiliary reappears after the
conjunction, e.g. "...cross flow was found to ... and IS therefore
better...") and (d) "d_participial_second_predication" (a
comma-attached past-participle second predication, e.g. "..., signed by
Breton, ..."). Rules (b) and (c), which key off CFR-curated regulatory
verb lists (`FINITE_S_VERBS` / `BASE_VERBS` -- e.g. "identifies", "shall
follow"/"shall precede"), matched **zero** FactoidWiki nuclei -- an
honest, reportable finding (that vocabulary is CFR's regulatory
register, not Wikipedia's), not a defect to fix. Tuning those curated
lists for Wikipedia's much broader vocabulary was deliberately not
attempted without a held-out validation set (the same concern
`severance_judge_paragraph.py`'s docstring raises about reusing the CFR
rule-based check un-validated).

`assign_governed_subclause`'s difflib span-matching also worked
unmodified for all 13 cases against the source `content` field (a whole
Wikipedia paragraph, typically several sentences, not a single CFR
sentence) -- no `RuntimeError` (which fires if the satellite/sub-clauses
can't be located in the source text) was raised.

| pool_index | Relation | Clarity | Rule | Governed sub-clause (adjacency note) |
|---|---|---|---|---|
| 1840 | Concession | clear | (a) | 1: "others felt that she was genuinely content with the direction her career..." (sentence-initial satellite; may scope over both) |
| 1936 | Concession | clear | (a) | 2: "some say it does not include shoplifting" (satellite embedded inside this sub-clause) |
| 3263 | Concession | clear | (a) | 1: "the word choice indicates that khati'ah is more than just a moral lapse or mistake" (sentence-initial satellite; may scope over both) |
| 3360 | Condition | clear | (a) | 2: "the Habsburgs would have an entire season to recruit" (satellite span overlaps this sub-clause) |
| 3397 | Condition | clear | (a) | 2: "may be used to explain disparate events" (satellite embedded inside this sub-clause) |
| 3444 | Condition | clear | (a) | 1: "the luxury item is forfeited" (sentence-initial satellite; may scope over both) |
| 4208 | Condition | clear | (a) | 1: "X-rays refracted in the sample by a smaller angle will be reflected less" (sentence-initial satellite; may scope over both) |
| 4380 | Condition | clear | (a) | 1: "the pot will be $30" (sentence-initial satellite; may scope over both) |
| 4698 | Concession | borderline | (d) | 1: "Murderous Humanitarianism' (1932) which was drafted mainly by Crevel, ... perhaps makes it the original document of what is later called 'black Surrealism'" (satellite embedded inside this sub-clause) |
| 4707 | Concession | clear | (a) | 1: "Counterflow was found to obtain lower temperatures more suitable for home cooling" (satellite span overlaps this sub-clause) |
| 4859 | Concession | clear | (a) | 1: "the Netherlands contains a Bible Belt from Zeeland to the northern parts of the province Overijssel, ..." (sentence-initial satellite; may scope over both) |
| 4920 | Concession | clear | (a) | 2: "have entered the Church" (satellite embedded inside this sub-clause) |
| 5132 | Condition | clear | (a) | 1: "The dish is made with tucupi (yellow broth extracted from cassava, ..." (satellite span overlaps this sub-clause) |

## Sub-clause-scoped judge (bundled subset only, 26 LLM calls)

Unlike the original CFR audit, no prompt-iteration issue recurred here:
the imported `llm_judge_severance_subclause` is already the CFR track's
tightened, validated prompt (the claims-blind first draft was discarded
during the original CFR audit -- see `../RESULTS.md`), used as-is, once.
Spot-checked reasoning strings for the flipped verdicts below cite
specific atomized-proposition content, not the relation description
alone -- e.g. pool_index 1840 condition A: *"The satellite's
qualification regarding the thoughts of friends and former advisers is
not present in any of the atomized claims related to the governed
sub-clause..."* -- no sign of the claims-blind failure mode recurring.

Verdict changes (original full-nucleus judge -> sub-clause judge), 12 of
26 calls flip:

| pool_index | Relation | Clarity | Condition A | Condition B |
|---|---|---|---|---|
| 1840 | Concession | clear | preserved -> **severed** | preserved -> preserved |
| 1936 | Concession | clear | preserved -> preserved | preserved -> preserved |
| 3263 | Concession | clear | severed -> **preserved** | preserved -> preserved |
| 3360 | Condition | clear | preserved -> preserved | preserved -> preserved |
| 3397 | Condition | clear | severed -> **preserved** | severed -> **preserved** |
| 3444 | Condition | clear | preserved -> preserved | preserved -> preserved |
| 4208 | Condition | clear | severed -> **preserved** | preserved -> preserved |
| 4380 | Condition | clear | preserved -> preserved | preserved -> preserved |
| 4698 | Concession | borderline | preserved -> **severed** | preserved -> preserved |
| 4707 | Concession | clear | severed -> **preserved** | severed -> **preserved** |
| 4859 | Concession | clear | preserved -> preserved | preserved -> preserved |
| 4920 | Concession | clear | severed -> **preserved** | severed -> **preserved** |
| 5132 | Condition | clear | severed -> **preserved** | severed -> **preserved** |

## Adjusted secondary figures (sub-clause-scoped ALTERNATIVE reading)

Bundled-subset records use the sub-clause verdict; all other records
keep their original saved verdict. Secondary, alternative reading --
**NOT a replacement** of the headline `task7_experiment_1_2_report.json`
figures above.

| Figure | Original (full-nucleus judge) | Adjusted (all 13 bundled) |
|---|---|---|
| Condition A severed, overall | 109/272 (40.1%) | 105/272 (38.6%) |
| Condition A severed, clear bundles only (12) | 109/272 (40.1%) | 104/272 (38.2%) |
| Condition B severed, overall | 60/272 (22.1%) | 56/272 (20.6%) |
| Condition B severed, clear bundles only (12) | 60/272 (22.1%) | 56/272 (20.6%) |
| Condition A severed, Condition relation | 13/75 (17.3%) | 10/75 (13.3%) |
| Condition A severed, Concession relation | 96/197 (48.7%) | 95/197 (48.2%) |
| Condition B severed, Condition relation | 12/75 (16.0%) | 10/75 (13.3%) |
| Condition B severed, Concession relation | 48/197 (24.4%) | 46/197 (23.4%) |

Both conditions' overall severed rate drops modestly under the adjusted
reading (A: 40.1% -> 38.6%, -1.5pp; B: 22.1% -> 20.6%, -1.5pp). Six
records flip toward preserved under Condition A (pool_index 3263, 3397,
4208, 4707, 4920, 5132) while two flip toward severed (1840, 4698 --
both cases where the sub-clause judge found the satellite's
qualification genuinely absent from Condition A's propositions once
scored against the correct governed sub-clause rather than credited
against the full bundled nucleus). Under Condition B, four records flip,
all toward preserved (3397, 4707, 4920, 5132), and none flip toward
severed. Direction and magnitude are consistent with the CFR track's
finding: bundling inflates the full-nucleus severed rate by a small,
non-reversing amount -- it does not change which condition severs more
(Condition A still severs substantially more than Condition B either
way, and Concession still severs more than Condition under either
reading).

## Exclusion list for a future evaluation set

Records scored severed=True under Condition A by the ORIGINAL
full-nucleus judge that flip to preserved under the sub-clause judge
(candidates for exclusion from a future experiment's evaluation set, the
same convention as the CFR audit's exclusion list): pool_index 3263,
3397, 4208, 4707, 4920, 5132 (6 of the 109 originally-severed-under-A
records).
