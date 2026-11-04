# AtomicRAG track

Second external chunker measured against the SAME 272 governing-relation
(75 Condition + 197 Concession) + 206 Elaboration-control FactoidWiki
paragraphs `../run_experiment_1_2.py` already built for Chen et al.'s
Propositionizer (Condition A) and the gpt-4o-mini relation-aware atomizer
(Condition B) -- see `../README.md`'s Task 7 for that full methodology.
This track's own results are in `results/atomicrag_experiment_1_2_report.json`;
per-paragraph detail (all extracted knowledge fragments + judge reasoning)
is in `logs/atomicrag_govern_log.jsonl` (272 records) and
`logs/atomicrag_elaboration_log.jsonl` (206 records). NuggetIndex is a
methodologically separate, parallel integration -- not assumed or
referenced here.

## Attribution (read this before quoting any number from this track)

AtomicRAG (Hou, Yuan, Zhou, Chen, Liang, Wang, Liu, Huang,
"AtomicRAG: Atom-Entity Graphs for Retrieval-Augmented Generation",
arXiv:2604.20844, https://github.com/7HHHHH/AtomicRAG) released OpenIE
code, `vendor/AtomicRAG` pinned at commit `4e6f0ed`. This track calls
ONLY `OpenIE.batch_unified_openie` (NER + unified triple/knowledge-
fragment extraction) in isolation -- the embedding store, Atom-Entity
Graph, PPR retrieval, and fragment filter stages were never run. See
`atomicrag_openie_adapter.py`'s module docstring for the full account of
what is real/bypassed/substituted (nothing at the model level: gpt-4o-mini,
temperature=0 are AtomicRAG's own published defaults; `seed=13` is this
project's own convention override).

**No Condition B for this chunker**: AtomicRAG's OpenIE prompts have no
relation-hint input slot (verified by reading every prompt template's
parameter list) -- there is no AtomicRAG analog of Experiment 1's
capacity-vs-elicitation ablation. Only the standard-atomization condition
is reported.

## Full-sample results (272 governing + 206 Elaboration control)

**1434 real LLM calls** (478 paragraphs x 2 AtomicRAG OpenIE calls +
478 severance-judge calls), **0 atomization errors**.

| Relation | N | Severed (AtomicRAG fragments) |
|---|---|---|
| Condition | 75 | 29/75 (38.7%) |
| Concession | 197 | 95/197 (48.2%) |
| **Governing pooled** | **272** | **124/272 (45.6%)** |
| Elaboration control | 206 | 24/206 (11.7%) |

Fisher's exact test: p = 3.23e-16 (odds ratio 6.35). AtomicRAG's own
knowledge fragments are much coarser than Propositionizer's (avg. 3.72
fragments/paragraph vs. 9.06), yet its connective-survival rate is
somewhat HIGHER overall (34.6% vs. 23.5%) -- full detail in
`results/atomicrag_experiment_1_2_report.json`'s
`structural_comparison_condition_a_vs_atomicrag` block.

## Files in this directory

- `atomicrag_openie_adapter.py` -- thin `OpenIE.batch_unified_openie`
  wrapper; module docstring carries the full attribution/bypass/
  substitution account.
- `run_pilot.py` -- small hand-inspection run before the full sample.
- `run_atomicrag_experiment.py` -- full-scale orchestration; entry point.
- `no_split_diagnostic.py` -- Audit addendum (2026-08-14): post-hoc
  severed-with-no-split (A2) diagnostic, direct port of
  `../no_split_diagnostic.py`.
- `audit_nucleus_bundling.py` -- Audit addendum (2026-08-14): post-hoc
  nucleus-bundling (A1) audit, direct port of `../audit_nucleus_bundling.py`.
- `requirements.txt` -- AtomicRAG's own dependencies (torch/transformers
  are NOT required -- see the adapter docstring's import-time bypass).
- `vendor/AtomicRAG/` -- pinned clone of the released repo.
- `logs/atomicrag_govern_log.jsonl` (272 records),
  `logs/atomicrag_elaboration_log.jsonl` (206 records).
- `results/atomicrag_experiment_1_2_report.json` (full run),
  `results/pilot_report.json` (pilot run),
  `results/atomicrag_no_split_diagnostic.json`,
  `results/atomicrag_nucleus_bundling_audit.json` (both audit addenda
  below).

# Audit addendum (2026-08-14): severed-with-no-split (A2) diagnostic, ported from `../no_split_diagnostic.py`

Post-hoc, pure structural/string analysis of the SAVED results above --
no new LLM calls. Machine-readable results:
`results/atomicrag_no_split_diagnostic.json`. Checks whether a
"severed" verdict is a real atomization failure or a judge/prompt
category error against an atomizer that did not actually split anything
apart: the atomized output, joined back together and normalized, near-
identical (difflib ratio >= 0.95) to the source paragraph.

**No adaptation of the check's logic was needed** -- AtomicRAG's atomic
unit (a "knowledge fragment") is still natural-language text, unlike
NuggetIndex's structured triples (see that track's own port for why THAT
one required redesigning the check; not assumed here, checked and found
unnecessary).

| | AtomicRAG |
|---|---|
| No-split (joined output ~= source, ratio >= 0.95) | 1/272 (0.4%) |
| ...of which STRICT (single fragment) | 1 |
| STRICT no-split yet scored severed=True | **1** |
| Any no-split yet scored severed=True | 1 |

Only one case, and it is a clean, illustrative one: **pool_index 5218**
("List of compositions by Duke Ellington", Condition). Source: *"All
tracks composed by Duke Ellington, except where noted."* AtomicRAG
extracted exactly ONE knowledge fragment, near-verbatim: *"All tracks are
composed by Duke Ellington, except where noted."* -- nothing was split
apart, the conditional exception clause ("except where noted") is sitting
right there in the single fragment, yet the judge still scored it
severed=True ("does not clearly convey the conditional relationship...
presents the statement as an absolute"). This is the same category error
`../no_split_diagnostic.py`'s docstring names for the Propositionizer
track's Condition B: an atomizer that returns its input back essentially
unsplit cannot have "severed" a relation by omission.

**Net effect on the headline numbers: negligible** (1/272 records,
0.4pp of AtomicRAG's 45.6% pooled severed rate) -- far smaller than the
Propositionizer track's Condition-B no-split artifact (8.3% of B's
severed cases), consistent with AtomicRAG almost always decomposing
(avg. 3.72 fragments/paragraph, never near-zero).

# Audit addendum (2026-08-14): nucleus-bundling (A1) audit, ported from `../audit_nucleus_bundling.py`

Post-hoc audit of the SAVED results above, run by
`audit_nucleus_bundling.py`. **All numbers above, and everything in
`results/atomicrag_experiment_1_2_report.json`, are untouched** -- the
figures below are a secondary, sub-clause-scoped alternative reading
reported alongside them, not a replacement. Machine-readable results:
`results/atomicrag_nucleus_bundling_audit.json`. No atomization or
primary-judge scoring was re-run; the only new LLM calls made were **13
real sub-clause-scoped judge calls** (one per bundled record -- half as
many as the Propositionizer-track port's 26, since AtomicRAG has only one
condition, not two).

This is a fairly direct port, as expected going in: AtomicRAG's atomic
unit is still natural-language text, so the SAME bundling heuristic
(`detect_bundling_sites` / `choose_bundling_site` /
`assign_governed_subclause` / `connective_attachment`, imported
unmodified from `../../audit_severance.py`) and the SAME sub-clause-
scoped judge (`severance_detection.llm_judge_severance_subclause`) used
for the Propositionizer-track port are reused without modification; only
the field names changed (`atomicrag_propositions` / `severance_atomicrag`
in place of the A/B pair) and there is one condition instead of two.

**Bundled nuclei: 13/272 (4.8%) -- 12 clear, 1 borderline -- the
IDENTICAL 13 pool_indices `../audit_nucleus_bundling.py` already found
for the Propositionizer track.** This is not a coincidence: bundling
detection depends only on the `nucleus`/`content`/`satellite` fields,
which are copied verbatim from the same source govern log into every
chunker's own log -- verified programmatically by this script (it raises
if the set ever diverges), not assumed.

## Sub-clause-scoped judge (bundled subset only, 13 LLM calls)

Verdict changes (original full-nucleus judge -> sub-clause judge), 5 of
13 calls flip:

| pool_index | Relation | Clarity | AtomicRAG |
|---|---|---|---|
| 1840 | Concession | clear | preserved -> preserved |
| 1936 | Concession | clear | severed -> **preserved** |
| 3263 | Concession | clear | severed -> **preserved** |
| 3360 | Condition | clear | severed -> **preserved** |
| 3397 | Condition | clear | severed -> severed |
| 3444 | Condition | clear | preserved -> preserved |
| 4208 | Condition | clear | preserved -> preserved |
| 4380 | Condition | clear | preserved -> preserved |
| 4698 | Concession | borderline | preserved -> **severed** |
| 4707 | Concession | clear | severed -> **preserved** |
| 4859 | Concession | clear | preserved -> preserved |
| 4920 | Concession | clear | severed -> **preserved** |
| 5132 | Condition | clear | severed -> severed |

## Adjusted secondary figures (sub-clause-scoped ALTERNATIVE reading)

| Figure | Original (full-nucleus judge) | Adjusted (all 13 bundled) |
|---|---|---|
| AtomicRAG severed, overall | 124/272 (45.6%) | 120/272 (44.1%) |
| AtomicRAG severed, clear bundles only (12) | 124/272 (45.6%) | 119/272 (43.8%) |
| AtomicRAG severed, Condition relation | 29/75 (38.7%) | 28/75 (37.3%) |
| AtomicRAG severed, Concession relation | 95/197 (48.2%) | 92/197 (46.7%) |

Overall severed rate drops modestly under the adjusted reading (45.6% ->
44.1%, -1.5pp) -- same direction and similar magnitude to the
Propositionizer track's own adjustment (40.1% -> 38.6%, -1.5pp). Five
records flip toward preserved (1936, 3263, 3360, 4707, 4920) and one
flips toward severed (4698). Does not change the
qualitative comparison: AtomicRAG still severs governing relations at a
much higher rate than its own Elaboration control either way.

## Exclusion list for a future evaluation set

Records scored severed=True under AtomicRAG by the ORIGINAL full-nucleus
judge that flip to preserved under the sub-clause judge: pool_index 1936,
3263, 3360, 4707, 4920 (5 of the 124 originally-severed records).
