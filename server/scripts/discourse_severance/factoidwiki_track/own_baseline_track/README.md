# own_baseline_track

Fourth chunker measured against the SAME 272 governing-relation (75
Condition + 197 Concession) + 206 Elaboration-control FactoidWiki
paragraphs `../run_experiment_1_2.py` already built for Chen et al.'s
Propositionizer (Condition A there) and the gpt-4o-mini relation-aware
atomizer (Condition B there) -- see `../README.md`'s Task 7 for that full
methodology. This is **this project's own minimal prompted baseline**:
`../../atomization_conditions.py`'s `run_condition_a` / `run_condition_b`
(the shipped, production claim-extraction logic used elsewhere in this
project for CFR sentences), run UNMODIFIED on FactoidWiki paragraphs --
see `own_baseline_adapter.py`'s module docstring for the full
INPUT-GRANULARITY DECISION and why it was run as-is rather than
reimplemented as a paragraph-flavored fifth atomizer.

## Framing (must be preserved wherever this baseline's numbers are cited)

"A minimal prompted baseline, included as one additional tested system
for the generality claim, not itself a claimed contribution." One of
four data points in a controlled comparison -- never described as this
project's own showcased pipeline. See `own_baseline_adapter.
FRAMING_STATEMENT`.

## Vocabulary note (read before touching any script in this directory)

This track's atomized units are called **"claims"**
(`condition_a_claims` / `condition_b_claims`), matching
`atomization_conditions.py`'s own return key literally, not
"propositions" the way `../run_experiment_1_2.py` / `../atomicrag_track`
/ `../nuggetindex_track` name theirs.

**Field-name landmine, already found and avoided in both audit scripts
below**: `logs/own_baseline_govern_log.jsonl` ALSO carries
`condition_a_propositions` / `condition_b_propositions` /
`verification_prompt_version` / `condition_b_error` keys. These are
**stale fields copied through from `../logs/task7_experiment_govern_log.
jsonl`** (Chen et al.'s real Propositionizer output and the
Propositionizer-track's own gpt-4o-mini elicit-then-atomize Condition B)
-- confirmed by diffing byte-for-byte, NOT this baseline's own output.
`run_own_baseline_experiment.py`'s `_process_govern_record` does
`{**rec, "condition_a_claims": claims_a, ..., "severance_a": severance_a,
...}`, which spreads the untouched source record first, so
`condition_a_propositions` survives unshadowed while `severance_a` /
`severance_b` DO get overwritten with this baseline's own judge verdicts
-- verdicts computed against `condition_a_claims` / `condition_b_claims`,
never against `condition_a_propositions` / `condition_b_propositions`.
Both `no_split_diagnostic.py` and `audit_nucleus_bundling.py` below use
only `condition_a_claims` / `condition_b_claims`.

## Full-sample results (272 governing + 206 Elaboration control)

From `results/own_baseline_experiment_1_2_report.json` (**1500 real LLM
calls**: 478 Condition-A atomize + 272 Condition-B atomize + 750
severance-judge calls; 1 judge call/parse failure -- pool_index 4849's
`severance_a`, an unparseable-JSON case, `preserved: null`, excluded from
scored counts):

| Relation | N | Severed (Condition A) | Severed (Condition B) |
|---|---|---|---|
| Condition | 75 | 16/75 (21.3%) | 14/75 (18.7%) |
| Concession | 197 | 91/196 (46.4%, 1 unscored) | 38/197 (19.3%) |
| **Governing pooled** | **272** | **107/271 (39.5%)** | **52/272 (19.1%)** |
| Elaboration control | 206 | 19/206 (9.2%) | -- (no Condition B on control) |

Fisher's exact test (Condition-A output, governing pooled vs. Elaboration
control): p = 1.28e-14, odds ratio 6.42.

## Files in this directory

- `own_baseline_adapter.py` -- thin wrapper around
  `../../atomization_conditions.py`'s `run_condition_a` / `run_condition_b`;
  module docstring carries the full INPUT-GRANULARITY DECISION.
- `env_utils.py` -- path/env helpers; READS (never writes)
  `../logs/task7_experiment_govern_log.jsonl` /
  `task7_experiment_elaboration_log.jsonl` as the source-paragraph corpus.
- `run_own_baseline_experiment.py` -- full-scale + pilot orchestration;
  entry point for Experiments 1/2.
- `run_own_baseline_experiment_3.py`, `own_baseline_exp3_dataset.py` --
  Experiment 3 (recovery) orchestration.
- `no_split_diagnostic.py` -- Audit addendum (2026-08-15): post-hoc
  severed-with-no-split (A2) diagnostic, direct port of
  `../atomicrag_track/no_split_diagnostic.py`, extended to report BOTH
  Condition A and Condition B (this baseline, unlike AtomicRAG, has a
  real Condition-B analog).
- `audit_nucleus_bundling.py` -- Audit addendum (2026-08-15): post-hoc
  nucleus-bundling (A1) audit, direct port of
  `../atomicrag_track/audit_nucleus_bundling.py`, likewise extended to
  both conditions.
- `logs/own_baseline_govern_log.jsonl` (272 records),
  `logs/own_baseline_elaboration_log.jsonl` (206 records).
- `results/own_baseline_experiment_1_2_report.json` (full run),
  `results/own_baseline_pilot_report.json` (pilot run),
  `results/own_baseline_exp3_report.json` (Experiment 3),
  `results/own_baseline_no_split_diagnostic.json`,
  `results/own_baseline_nucleus_bundling_audit.json` (both audit addenda
  below).

# Audit addendum (2026-08-15): severed-with-no-split (A2) diagnostic, ported from `../atomicrag_track/no_split_diagnostic.py`

Post-hoc, pure structural/string analysis of the SAVED results above --
no new LLM calls. Machine-readable results:
`results/own_baseline_no_split_diagnostic.json`. Checks whether a
"severed" verdict is a real atomization failure or a judge/prompt
category error against an atomizer that did not actually split anything
apart: the atomized claims, joined back together and normalized,
near-identical (difflib ratio >= 0.95) to the source paragraph.

**No adaptation of the check's logic was needed** -- this baseline's
atomic unit ("claim") is still natural-language text, exactly like
Propositionizer's and AtomicRAG's. **Unlike AtomicRAG** (no Condition-B
analog), this baseline has a real, independently-judged Condition B, so
this script reports TWO condition blocks -- matching
`../no_split_diagnostic.py`'s scoping, not AtomicRAG's single-condition
scoping.

| | Condition A | Condition B |
|---|---|---|
| No-split (joined claims ~= source, ratio >= 0.95) | 23/272 (8.5%) | 95/272 (34.9%) |
| ...of which STRICT (single claim) | 1 | 17 |
| STRICT no-split yet scored severed=True | **1** | **5** |
| Any no-split yet scored severed=True | 11 | 19 |

By relation type: Condition A -- Condition 12/75 no-split (1 strict),
Concession 11/197 no-split (0 strict). Condition B -- Condition 23/75
no-split (7 strict), Concession 72/197 no-split (10 strict). Condition
B's much higher no-split rate is expected: it is explicitly told the
relation to preserve and, per the structural comparison in
`own_baseline_experiment_1_2_report.json` (avg. 6.07 claims/paragraph vs.
Condition A's 8.36, 100%-by-construction connective survival), it
systematically keeps larger, less-decomposed spans intact to do so.

**Illustrative case, same category error both natural-language chunkers'
diagnostics have found: pool_index 5218** ("Duke Ellington Meets Coleman
Hawkins", Condition; **flagged under BOTH conditions**, and the STRICT
Condition-A case). Source: *"All tracks composed by Duke Ellington,
except where noted."* Condition A extracted exactly ONE claim,
near-verbatim: *"All tracks are composed by Duke Ellington, except where
noted."* -- nothing was split apart, the conditional exception clause
("except where noted") sits right there in the single claim, yet the
judge still scored it severed=True: *"the atomized proposition ...
presents the statement as an absolute without indicating that the
assertion is contingent on the satellite's truth."* Nothing was actually
split apart; a severed=True verdict here is a judge/prompt category
error, not an atomization failure -- the identical finding
`../atomicrag_track/README.md` already reports for the same pool_index
under AtomicRAG's own single fragment.

**Net effect on the headline numbers**: small for Condition A (11/107
originally-severed governing records, 10.3%, are any-no-split cases; 1 is
the cleanest STRICT category error) but non-trivial for Condition B
(19/52 originally-severed records, 36.5%, are any-no-split cases) --
Condition B's relation-aware prompting keeps output closer to source
wording far more often, so when it still gets scored severed, there is a
much higher chance the judge is penalizing something that was not
actually split apart. This mirrors the qualitative pattern
`../no_split_diagnostic.py` already found for the Propositionizer
track's own Condition B (elicit-then-atomize).

# Audit addendum (2026-08-15): nucleus-bundling (A1) audit, ported from `../atomicrag_track/audit_nucleus_bundling.py`

Post-hoc audit of the SAVED results above, run by
`audit_nucleus_bundling.py`. **All numbers above, and everything in
`results/own_baseline_experiment_1_2_report.json`, are untouched** -- the
figures below are a secondary, sub-clause-scoped alternative reading
reported alongside them, not a replacement. Machine-readable results:
`results/own_baseline_nucleus_bundling_audit.json`. No atomization or
primary-judge scoring was re-run; the only new LLM calls made were **26
real sub-clause-scoped judge calls** (13 bundled records x 2 conditions,
matching the Propositionizer-track port's per-record call count, since
this baseline -- unlike AtomicRAG -- has a real Condition B).

**Bundled nuclei: 13/272 (4.8%) -- 12 clear, 1 borderline -- the
IDENTICAL 13 pool_indices** already found for Propositionizer, AtomicRAG,
and NuggetIndex (1840, 1936, 3263, 3360, 3397, 3444, 4208, 4380, 4698,
4707, 4859, 4920, 5132). Verified programmatically by this script (it
would report a mismatch rather than assume it) -- not a coincidence:
bundling detection depends only on the `nucleus`/`content`/`satellite`
fields, copied verbatim from the same source govern log into every
chunker's own log.

## Sub-clause-scoped judge (bundled subset only, 26 LLM calls)

Verdict changes (original full-nucleus judge -> sub-clause judge), 6 of
13 flip for Condition A, 5 of 13 flip for Condition B:

| pool_index | Relation | Clarity | Condition A | Condition B |
|---|---|---|---|---|
| 1840 | Concession | clear | preserved -> **severed** | preserved -> preserved |
| 1936 | Concession | clear | preserved -> preserved | preserved -> preserved |
| 3263 | Concession | clear | severed -> **preserved** | preserved -> preserved |
| 3360 | Condition | clear | preserved -> preserved | severed -> **preserved** |
| 3397 | Condition | clear | severed -> **preserved** | severed -> **preserved** |
| 3444 | Condition | clear | preserved -> preserved | preserved -> preserved |
| 4208 | Condition | clear | severed -> **preserved** | preserved -> preserved |
| 4380 | Condition | clear | preserved -> preserved | preserved -> preserved |
| 4698 | Concession | borderline | severed -> severed | preserved -> preserved |
| 4707 | Concession | clear | severed -> **preserved** | severed -> **preserved** |
| 4859 | Concession | clear | preserved -> preserved | preserved -> preserved |
| 4920 | Concession | clear | severed -> **preserved** | severed -> **preserved** |
| 5132 | Condition | clear | preserved -> preserved | severed -> **preserved** |

## Adjusted secondary figures (sub-clause-scoped ALTERNATIVE reading)

| Figure | Original (full-nucleus judge) | Adjusted (all 13 bundled) |
|---|---|---|
| Condition A severed, overall (/272) | 107/272 (39.3%) | 103/272 (37.9%) |
| Condition A severed, Condition relation | 16/75 (21.3%) | 14/75 (18.7%) |
| Condition A severed, Concession relation | 91/197 (46.2%) | 89/197 (45.2%) |
| Condition B severed, overall (/272) | 52/272 (19.1%) | 47/272 (17.3%) |
| Condition B severed, Condition relation | 14/75 (18.7%) | 11/75 (14.7%) |
| Condition B severed, Concession relation | 38/197 (19.3%) | 36/197 (18.3%) |

(These "overall (/272)" figures divide by the full N=272, matching
`figure_block`'s convention in every sibling audit script; they differ
slightly in the numerator base from the headline
`own_baseline_experiment_1_2_report.json` rate, which divides Condition
A's 107 by its 271 SCORED records -- pool_index 4849's judge-parse
failure is excluded there but still counted in the N=272 denominator
here, same as every other chunker's bundling-audit convention.)

Condition A's adjustment (-1.4pp) is close to Propositionizer's (-1.5pp)
and AtomicRAG's (-1.5pp); Condition B's (-1.8pp) is the largest of any
condition measured across all four chunkers so far. One record flips
toward severed under Condition A (1840) while five flip toward preserved
(3263, 3397, 4208, 4707, 4920); under Condition B, five flip toward
preserved (3360, 3397, 4707, 4920, 5132) and none flip toward severed.
Does not change the qualitative comparison: both conditions still sever
governing relations at a materially higher rate than the Elaboration
control either way.

## Exclusion list for a future evaluation set

Records scored severed=True under Condition A by the ORIGINAL
full-nucleus judge that flip to preserved under the sub-clause judge:
pool_index 3263, 3397, 4208, 4707, 4920 (5 of the 107 originally-severed
Condition-A records).
