# Research

All research material for Wittgenstein in one place, by topic, newest last within each
topic (`YYYY-MM-DD_name`). Only this index is committed; everything else here is
local-only (`research/.gitignore`): unpublished results, paper drafts, copyrighted
literature, participant data, and large archives.

Experiments that run from the old app's code (`server/scripts/...`) stay where they run;
the entries below are symlinks to them, so nothing breaks and nothing is duplicated.

## Topics

### `risk-triage/` — the original claim-formalization risk classifier
- `2026-08-07_research-summary-for-collaborators.md` — project summary as of August.
- `2026-08-12_external-robustness-check.md` → `server/scripts/EXTERNAL_ROBUSTNESS.md`
  (risk triage on FactoidWiki).
- `2026-09-01_risk-triage-learnings.txt`, `2026-09-02_risk-triage-edge-cases.txt` —
  design lessons and the edge-case log the live pipeline's text detectors were ported from.
- `2026-09-03_risk-triage-edge-cases_cosmos-copy.txt` → the slightly later copy kept in
  the cosmos workspace (header notes it describes an older implementation).

### `discourse-severance/` — does atomizing text sever conditions and exceptions? (Aug 2026)
- `2026-08-06_exp1-2_severance-under-atomization` → `server/scripts/discourse_severance/`
  (Experiments 1-2; `RESULTS.md` inside).
- `2026-08-07_exp3_recovery-strategy-comparison` → Experiment 3 (Disco-RAG adapted vs.
  this project's fallback; `RESULTS.md` inside).
- `2026-08-10_factoidwiki-propositionizer-track` → FactoidWiki / Propositionizer pilot and
  full-scale rebuild (Task 7).
- `2026-08-14_{atomicrag,nuggetindex,own}-baseline-track` → the three baseline tracks.

### `rag-reliability-engine/` — evidence-graded failure registry (Sep 2026)
- `2026-09_engine-implementation-log.md` → `engine/docs/implementation-plan.md`.
- `2026-09-09_literature-review-results.md`, `..._second-review-results.md`.
- `2026-09-11_real-trace-smoke-test-results.md`, `2026-09-15_evidence-set-real-corpus-diagnostics-results.md`.
- `2026-09-11..16_eu-ai-act-*` — EU AI Act pilot, article cross-reference fix,
  granularity resolution, annotation summaries.

### `live-pipeline/` — the self-aware pipeline and web app (Nov 2026)
- `2026-11-04_live-pipeline-plan-and-status.md` → `engine/docs/live-pipeline-plan.md`.
- `2026-11-04_verification-audit.md` (+ folder): what the integration demo's checks caught, each flag
  verified against the label text, three checker bugs found and fixed, and what is not yet established.

### `medical-education/` — University of Arizona College of Medicine conversation
- `2026-11-04_medical-ai-problems-and-features.md` — evidence on medical LLM/RAG
  failures (citations, omissions, conflicts, drug labels, automation bias), features
  ranked, and a possible pilot design.

### `case-studies/`
- `2026-11-04_public-llm-document-failures.md` — Air Canada chatbot (Moffatt v. Air Canada),
  NYC MyCity chatbot, Stanford legal-RAG study; the Air Canada case run through the checker,
  including what it didn't catch.

### `user-study/`
- `2026-08_pilot-sessions_PARTICIPANT-DATA` → `study_data/` (participant sessions from
  the original app's study harness). **Never commit or share without the study's consent
  terms.**

### `papers/` — drafts (LaTeX)
- `2026-08-06_text-atomization-reasoning/`
- `2026-08-18_human-in-the-loop-rag/`

### `literature/` — PDFs, `author_year_topic/`
- Ten papers from the August work (Carlson 2001, Chen 2024, Datla 2025, Edge 2024,
  Fang 2023, Guo 2024, Gutierrez 2024, Hou 2026, Leung 2025, Zerhoudi 2026).
- `cosmos-literature-review` → the cosmos workspace's literature folder.

### `_archive/` — kept, not current
- `2026-08_snapshots/` — `Wittgenstein.zip` (Aug 13 snapshot, 368 MB; may contain state
  that was never committed, so it was kept rather than deleted), the paper zip and its
  build script.
- `2026-08_superseded-experiment-artifacts/` — pre-retry and pre-refresh backups,
  partial and rate-limited runs, mirrored by their original paths. No script reads them.

## Housekeeping done (2026-11-04)
Deleted only regenerable files (`.DS_Store`, `__pycache__`). Nothing with research
content was deleted; superseded items were moved to `_archive/`.
