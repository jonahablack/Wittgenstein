# Study harness

Self-contained backend for the within-subjects triage study: a single
general-population cohort (`config.COHORTS`, currently `("general",)`) x
three conditions (`blind`, `triaged`, `opaque`), with up to two task types
per session -- batch claim review and query-answer verification. Everything
lives under the `/study` URL prefix and is fully separate from the main
product routes.

This module **consumes** already-computed output; it never computes risk
tiers, risk flags, or correct/dangerous-failure verdicts itself. There are
two independent corpus-sourcing paths, chosen per cohort in the study
config:

1. **Pipeline-sourced** (the original path). Each session's document must
   already have `outputs/{document_id}_final_data.json` produced by the
   pipeline, whose axiom records carry `claim_index`, `risk_tier`
   (`Low`/`Medium`/`High`/`Unformalized`) and `risk_flags`. Ground truth
   comes from a hand-written seeded-error file.
2. **exp3-report-sourced**. Each session's items come from
   `server/scripts/discourse_severance/factoidwiki_track/results/
   task8_factoidwiki_exp3_report.json` -- the discourse-severance
   research's own FactoidWiki recovery-comparison output (109 real
   FactoidWiki paragraph excerpts with a severed discourse relation, each
   already run through 3 automated-repair arms and the shipped
   risk_triage.py classifier). No pipeline output file and no hand-written
   ground truth are needed for this path. See "exp3-sourced cohorts" below.

The sourcing choice (pipeline vs. exp3-report) is a per-cohort config field
-- see `load_study_config`'s mutual-exclusivity check below.

## Registration

```python
from study_harness.routes import study_bp
app.register_blueprint(study_bp)
```

## Data locations

Same `DATA_DIR` convention as `app.py` (env var, default = repo base):

- pipeline outputs read from `DATA_DIR/outputs/`
- session + export files written under `DATA_DIR/study_data/`, one file
  per session keyed by its uuid `session_id` (no shared filenames)
- study config read from `$STUDY_CONFIG` if set, else
  `DATA_DIR/study_config.json` (an admin request may also pass an explicit
  `config_path`)

## Study config format

```json
{
  "cohorts": {
    "general": {
      "document_id": "17c81e7c-c629-43cd-a4ce-7ee8765d1bbc",
      "ground_truth_file": "ground_truth.json",
      "queries": [
        {
          "query_id": "q1",
          "query": "What dose does the protocol specify?",
          "classification": "clean",
          "answer": "The protocol specifies 5 mg twice daily.",
          "source_claim_indices": [3, 7]
        },
        {
          "query_id": "q2",
          "query": "Is the contraindication absolute?",
          "classification": "compromised",
          "answer": "No, it is only a relative contraindication.",
          "source_claim_indices": [4, 9, 12],
          "weak_source_claim_index": 9
        }
      ]
    }
  }
}
```

Rules:

- Cohort names must be one of `config.COHORTS` (currently just `general`).
  The field itself stays generic -- a config still names its cohort
  explicitly -- so a further cohort can be added later as its own entry in
  `config.COHORTS` without a schema change; none is defined today.
- Per cohort, either the `document_id` + `ground_truth_file` shorthand
  shown above (one document), or a `documents` list of
  `{"document_id": ..., "ground_truth_file": ...}` entries. Session
  creation defaults to the first document; pass `document_id` to pick
  another. A query may carry an optional `document_id` to scope it to one
  of the cohort's documents; unscoped queries apply to every document.
- `ground_truth_file` (relative paths resolve against the config file's
  directory) marks the seeded-error claims for batch review:
  `{"seeded_error_claim_indices": [2, 5, 11]}` (a bare JSON list of ints
  is also accepted). Every listed index must exist in the document.
- Queries are pre-written; `answer` is the pre-generated answer text (no
  LLM call is ever made by this module). `classification` is `clean` or
  `compromised`; compromised queries must name the weak retrieved source
  via `weak_source_claim_index`, which must be one of
  `source_claim_indices`.
- A cohort must not mix this pipeline shorthand/`documents` with
  `exp3_report_file` (below) -- pick one corpus-sourcing path per cohort.

## exp3-sourced cohorts

Instead of a pipeline document + hand-written ground truth, a cohort can
be sourced straight from the discourse-severance research's own FactoidWiki
recovery-comparison output:

```json
{
  "cohorts": {
    "general": {
      "exp3_report_file": "../server/scripts/discourse_severance/factoidwiki_track/results/task8_factoidwiki_exp3_report.json"
    }
  }
}
```

Unlike an earlier CFR-track version of this report (dropped from the
paper), this file has no per-record field splitting its records across
more than one cohort -- every record in it belongs to the single cohort
above.

**Item source: 3 pooled automated-repair arms, not the raw unrepaired
propositions.** The paper's real question is whether risk-flagging + human
deferral catches cases where *automated repair* produces fluent-but-wrong
output ("dangerous failures") -- nobody deploys raw, unrepaired,
claim-split output; a real system either auto-repairs or defers. So this
path pools the 3 arms that actually attempt automated repair of a severed
discourse relation, one "case" per (record, repair arm) pair:

| arm key (`config.EXP3_REPAIR_ARMS`) | report's per-case key | what it is |
| --- | --- | --- |
| `disco_rag` | `arm_2_disco_rag` | Disco-RAG (adapted) |
| `custom_fallback` | `arm_3_custom_fallback` | custom fallback rewriter |
| `contextual_retrieval` | `arm_4_contextual_retrieval` | Contextual Retrieval (context injection) |

This reuses the same 3-arm scope an earlier CFR-track version of this
report established as the arms that "can be wrong in a way that matters":
it excludes `arm_1_no_elicitation` (pre-repair scaffolding, not a repair),
`arm_6_flagged_deferral` (flagged deferral, "a different kind of arm", not
a repair), and `arm_5_parent_segment` (a ceiling/reality-check arm, not a
competitive recovery arm, that doesn't fail in the same sense).

Rules:

- `exp3_report_file` (relative paths resolve against the config file's
  directory, same as `ground_truth_file`) must point at a JSON file
  shaped like `task8_factoidwiki_exp3_report.json`: a top-level
  `"records"` list, each record carrying an integer `pool_index`,
  `arm_6_flagged_deferral` (with a `per_proposition_flags` list of
  `{"proposition", "flags"}`), and each of the 3 repair-arm keys above
  (with a `propositions` list, a `judge.preserved` bool, an already-computed
  `bucket` string, and -- when `bucket` is `"dangerous_failure"` -- a
  `failure_type.category` string). This module only reads these fields --
  it never recomputes a correct/dangerous-failure verdict and never
  recomputes a risk flag; both are already-computed research output.
- **Record identity**: since the report itself carries no string record id
  (only the integer `pool_index`), `record_id` is constructed as
  `"<document_id>:<pool_index>"` (e.g. `"factoidwiki:1918"`), where
  `document_id` is `config.EXP3_DOCUMENT_IDS["general"]`. In the checked-in
  report this covers 109 records; pooling all 3 repair arms per record
  gives 327 `opaque` cases (no repair arm fails outright or produces zero
  propositions anywhere in the checked-in file) and 2256 individual claims
  for `blind`/`triaged`, split 202 `correct` / 125 `dangerous_failure` by
  case. A repair arm that fails outright for a record (`error` set, or an
  empty `propositions` list -- not observed anywhere in the checked-in
  file, but handled explicitly) contributes no case for that (record, arm)
  pair rather than crashing or fabricating one.
- **No queries** on this path -- a cohort with `exp3_report_file` must
  not also set `queries`.
- **No `document_id` to pick** -- there is exactly one implicit
  "document" per exp3-sourced cohort (the whole report), reported as
  `factoidwiki` in the session/export `document_id` field. Passing a
  different `document_id` at session creation for this cohort is a `400`.
- **Item granularity depends on the condition** (see "Conditions" below):
  `blind`/`triaged` sessions get one item per individual claim within a
  (record, repair arm) case (a case with N claims contributes N items, all
  sharing that case's ground truth, `arm`, and record-level flags); an
  `opaque` session gets exactly one item per *case* instead -- 327 total in
  the checked-in file (up to 3x the per-record count, one per repair arm).
- **Risk flags are record-level, not arm-level.** `arm_6_flagged_deferral`
  is computed once per record, against `arm_1_no_elicitation`'s pre-repair
  propositions and the original source paragraph -- i.e. it is what the
  shipped pipeline would have flagged *before* any repair was attempted.
  Every repair arm's case for a given record therefore shares the
  identical flags list (flattened from `per_proposition_flags[*].flags`,
  deduped by `(type, reason)`, order preserved) -- this is deliberate: the
  research question is whether that pre-repair signal would have caught a
  given arm's eventual failure, not a per-arm re-triage.
- **Ground-truth vocabulary**: `correct` / `dangerous_failure` (see
  `config.EXP3_GROUND_TRUTH_LABELS`) -- deliberately distinct from the
  pipeline path's `seeded_error`/`clean`, since exp3 items have no
  seeded/injected error; the label is that repair arm's own already-computed
  `bucket` field, read verbatim after confirming it agrees with that arm's
  own `judge.preserved` bool (`preserved: true` iff `bucket == "correct"`)
  and, when `bucket == "dangerous_failure"`, that `failure_type.category`
  equals `"dangerous_failure"` -- the only failure category this corpus's
  methodology has ever produced for these 3 arms; any other bucket or
  category is a config error rather than a silent fold into
  `"dangerous_failure"`.
- **`arm`**: every exp3-sourced item (batch claim or batch passage) also
  carries a top-level `"arm"` key -- the short key from the table above
  identifying which repair arm produced that item's claims/passage. Like
  `ground_truth_label`, it lives outside `payload` and is never shown to
  the participant; it is exported (see "Export record" below).

Note: an earlier CFR-track version of this report additionally tagged
records with an `a2_flagged` audit boolean. `task8_factoidwiki_exp3_report.
json` has no such field, so this harness's exp3-sourced items no longer
carry one.

## Conditions

Set **only** at session creation via the admin endpoint -- never
participant-facing.

- `blind`: responses strip `risk_tier`/`risk_flags` (and the legacy
  `flag` field) everywhere, including query sources; batch claims are
  served as an undifferentiated list in `claim_index` order.
- `triaged`: risk fields are passed through verbatim (never recomputed).
  On the pipeline path, batch claims (and each query's sources) are
  served sorted `Unformalized`, `High`, `Medium`, `Low` first. On the
  exp3 path, there is no pipeline-style tier -- claims with any
  `arm_6_flagged_deferral` flag are served first instead, so triaged still
  surfaces the flagged claims first without inventing a tier the shipped
  classifier never computed for this corpus.
- `opaque`: the participant never sees individual claims, risk tiers, or
  risk flags at all -- each case is collapsed into a single continuous
  passage (its claims joined with a plain space) and reviewed as one
  holistic decision, the way an end user of a naive, non-triaged system
  would encounter it. There is no per-claim breakdown and no sort order
  within a case (there is nothing to sort). On the exp3 path this is one
  item per *(record, repair arm) case* (see above); on the pipeline path,
  which has no finer natural grouping than "the whole document", it is one
  item for the whole session.

No condition ever leaks the source's severity, seeded-error assignment, or
condition label to the participant -- this includes `opaque`, which is
held to exactly the same invariant as `blind`.

Query items (pipeline path only) always follow the batch items, in config
order. Participant responses never contain ground-truth labels, the exp3
path's `arm`, query classifications, or the compromised query's
weak-source answer.

## Endpoints

| Method | Path | Purpose |
| --- | --- | --- |
| POST | `/study/admin/sessions` | Create a session. Body: `{"participant_id", "cohort", "condition", "document_id"?, "config_path"?}` -> `201 {"session_id", ...}` |
| GET | `/study/admin/sessions` | List session ids on disk |
| GET | `/study/admin/sessions/<sid>` | Full stored session state (admin/debug) |
| GET | `/study/sessions/<sid>/items` | All items in serve order (stamps first-view time on any not yet viewed) |
| GET | `/study/sessions/<sid>/items/next` | Next undecided item (stamps its first view); `{"done": true}` when finished |
| POST | `/study/sessions/<sid>/decisions` | Body: `{"item_id", "decision": "approved"\|"flagged"\|"rejected", "confidence": 1-5, "identified_weak_source"?}` |
| GET | `/study/sessions/<sid>/export` | Analysis export record (also persisted to `study_data/exports/`) |

Decision rules: an item must have been served before a decision is
accepted (409 otherwise); one decision per item (409 on repeats);
`identified_weak_source` is **required** when `decision == "flagged"` on a
query item, and must be the `claim_index` of one of that item's sources.
`time_to_decision` is computed server-side as decision time minus
first-view time.

## Export record

One JSON record per session:

```json
{
  "participant_id": "P01",
  "cohort": "general",
  "condition": "blind",
  "document_id": "17c81e7c-...",
  "items": [
    {
      "item_id": "claim_3",
      "item_type": "batch_claim",
      "decision": "approved",
      "confidence": 4,
      "time_to_decision": 12.81,
      "ground_truth_label": "seeded_error",
      "identified_weak_source": null
    }
  ]
}
```

`ground_truth_label` is `seeded_error`/`clean` for pipeline-sourced batch
items, `clean`/`compromised` for query items, or `correct`/
`dangerous_failure` for exp3-sourced batch items (see "exp3-sourced
cohorts" above). Undecided items appear with null decision fields.
`item_type` is `batch_claim`, `batch_passage` (opaque), or
`query_verification`.

exp3-sourced items additionally carry an **`arm`** string identifying
which of `config.EXP3_REPAIR_ARMS` (`"disco_rag"` / `"custom_fallback"` /
`"contextual_retrieval"`) produced the item. This key is purely additive:
it never replaces any of the keys above, and it is omitted entirely (not
present as `null`) on pipeline-sourced items, so that corpus's export
shape is unchanged.

```json
{
  "item_id": "claim_3",
  "item_type": "batch_claim",
  "decision": "approved",
  "confidence": 4,
  "time_to_decision": 9.42,
  "ground_truth_label": "dangerous_failure",
  "identified_weak_source": null,
  "arm": "disco_rag"
}
```

An `opaque` batch item exports the same way, just with `item_type:
"batch_passage"` and one decision covering the whole collapsed case.
