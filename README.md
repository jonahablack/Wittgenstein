![alt text](minimum_length.png)

# Wittgenstein

Wittgenstein formalizes claims extracted from documents and flags the
formalizations most likely to have lost meaning in translation, so a human
reviewer can triage their attention efficiently instead of reading every claim
equally or trusting an opaque score. Every flag comes with a human-readable
reason tied to a documented linguistic pattern (hedges, modal mismatches,
ambiguous negation scope, cross-referenced conditions, unresolved references,
nested conditionals).

The tool is domain-agnostic. Clinical, legal, and policy documents appear in
the evaluation materials as **test inputs**, chosen because they are dense in
the linguistic patterns the detectors target — they are not the product's
identity.

This is a proof-of-concept demo, not a production system: reviewer decisions
are logged to a local JSON file (no real database, no auth).

## Pipeline

1. **Ingestion** — PDF or EPUB upload (`server/components/text_extraction.py`).
2. **Sentence segmentation** — the extracted text is split into sentence
   segments; the original segment text is retained so later stages can refer
   back to the pre-chunking sentence.
3. **Claim extraction** (`server/components/response_parsing.py`), two modes:
   - **Propositional decomposition** (default): sentences are decomposed into
     atomic, self-contained claims following the decomposition criteria stated
     in Chen et al., ["Dense X Retrieval: What Retrieval Granularity Should We
     Use?"](https://aclanthology.org/2024.emnlp-main.845/) (EMNLP 2024,
     [arXiv:2312.06648](https://arxiv.org/abs/2312.06648)), applied **via LLM
     prompting**. This is explicitly *not* their trained Propositionizer
     model, and no retrieval benchmark comparison has been made or attempted —
     the criteria are borrowed as a chunking discipline, not reproduced as a
     retrieval result.
   - **Fixed-size passage chunking**: sentence windows with no LLM extraction
     call, kept as the common baseline. Both modes produce the same claim
     record shape, so everything downstream is mode-agnostic.
4. **Formalization** (`server/components/logic_formalization.py`) — each claim
   is rewritten as logically explicit English, ASCII symbolic logic, or both,
   with a **reconciliation guarantee**: every extracted claim yields exactly
   one output record. If the model drops or fails a claim, that claim becomes
   an explicit "Unformalized" record — never a silent drop.
5. **Rule-based risk triage** (`server/components/risk_triage.py`) — five
   claim-level linguistic detectors (hedges, negation scope, cross-reference,
   unresolved reference, nested conditionals), a modal-mismatch check that
   compares the claim against its formal output (active only in modes where
   modal language is expressible in the formal string), and two segment-level
   fallback detectors that re-examine the original source sentence for
   nested-conditional and compound-negation structure that atomization may
   have stripped from the individual claims. Every flag traces to a documented
   linguistic pattern and carries a plain-language reason; tiers
   (Low/Medium/High) come from a transparent, inspectable weighting rule. The
   rule-based design is a **deliberate choice** — auditable patterns with
   stated reasons, no trained model — not a placeholder for a future trained
   classifier.
6. **Outputs** — a generated PDF report and in-app review (Approve / Flag /
   Reject per claim, decisions logged to `outputs/reviews.json`).
7. **Query-scoped retrieval** (`server/components/retrieval.py`) — ask a
   question of a processed document and review only the retrieved claims.
   Retrieval is plain Okapi BM25 with standard untuned parameters,
   **deliberately standard**: retrieval quality is not a contribution of this
   work. What the tool adds is **risk-tiered source attribution** — retrieved
   claims are presented riskiest first (Unformalized, High, Medium, Low, ties
   broken by BM25 score), so the reviewer sees the weakest links in an
   answer's support before the strong ones.

## Study harness

`server/study_harness/` is a self-contained backend for a **within-subjects
human evaluation**: two cohorts (clinical and legal test documents) x two
conditions (**blind** — risk fields stripped, claims in document order — and
**triaged** — risk fields shown, riskiest first), with batch claim review and
query-answer verification tasks per session. See
[server/study_harness/README.md](server/study_harness/README.md) for the
config format, endpoints, and export record.

## External robustness check

To see how the detectors behave on text far from this project's own corpus,
the claim-level detectors were run over a real external sample: the first
5,000 propositions of Chen et al.'s
[FactoidWiki](https://huggingface.co/datasets/chentong00/factoid-wiki) release
(encyclopedic text; the full ~250M-proposition dataset was deliberately not
downloaded). Results (`server/scripts/EXTERNAL_ROBUSTNESS.md`, generated by
`server/scripts/external_robustness_check.py`):

- 274 of 5,000 propositions (5.5%) received at least one flag; 98.8% tiered
  Low, 1.2% Medium, none High — i.e., the detectors stay quiet on plain
  declarative text rather than blanketing it with alerts.
- Flag breakdown: hedge 3.7%, negation scope 1.2%, unresolved reference 0.5%,
  cross-reference 0.2%, nested conditional 0%.
- **Known limitation, reported as found:** 19 of the 187 hedge flags are
  attributable solely to the capitalized month "May" (e.g. "released on May
  29, 2019") — the classifier lowercases before matching, so the month
  collides with the modal "may". Rare on this project's philosophical corpus,
  but a measurable false-positive source on date-heavy encyclopedic text. The
  classifier was tested as-is and not modified.

## Scope and limitations

- **Graph-based chunking is out of scope / future work.** Graph-RAG-style
  approaches — [GraphRAG](https://arxiv.org/abs/2404.16130) (Edge et al.),
  [LightRAG](https://arxiv.org/abs/2410.05779) (Guo et al.), and
  [HippoRAG](https://arxiv.org/abs/2405.14831) (Gutiérrez et al.) — build
  community summaries or graph-derived units that are LLM-generated syntheses
  with **no original source segment to recover**, which the segment-level
  fallback detectors require. Extending triage to such representations is
  future work, not something this codebase does.
- **No fine-tuning or benchmarking of chunking.** The propositional mode
  follows Chen et al.'s stated criteria via prompting only; no retrieval
  benchmarks were run, and no claim of retrieval superiority (over passage
  chunking or anything else) is made.
- **Structured formal representations are infrastructure, not a
  contribution.** The predicate-style formal strings exist so triage and
  contradiction-checking have something concrete to inspect. Programmatic
  lookup and consistency checking over structured representations is
  long-established territory (RDF/SPARQL, standard knowledge-graph tooling)
  and is not claimed as novel here.
- **The risk classifier is rules, on purpose.** See the pipeline section:
  auditable, reason-carrying patterns are the design, not a stopgap.

## Run locally

Start the Flask API (needed either way — it serves `/upload`, `/formalize`,
`/query`, `/review`, etc.):

```bash
cd server
pip install -r requirements.txt
export OPENAI_API_KEY=sk-...   # required; read from the environment at call time
python3 app.py                 # serves on :3000 (or $PORT)
```

Optional: set `DATA_DIR` to redirect uploads, generated PDFs, and the review
log to a persistent location (defaults to the repo root).

Then, for the client, pick one:

**Editing the UI (hot-reload)** — `vite.config.js` proxies API calls to
`localhost:3000`, so this reflects `.jsx` edits instantly without a rebuild:

```bash
cd client
npm install
npm run dev              # open http://localhost:5173
```

**Just running it as deployed** — Flask serves the built `client/dist`
directly; any time you change client source, you must rebuild or Flask will
keep serving the old bundle:

```bash
cd client
npm install
npm run build             # then open http://localhost:3000
```

Either way: upload a PDF/EPUB, choose a formalization type, and each resulting
claim is shown with its risk tier, flagged reasons, and Approve/Flag/Reject
controls. The Query review tab runs query-scoped retrieval over a processed
document; the Study tab hosts the study-harness participant UI.

## Tests

```bash
cd server
../venv/bin/python -m pytest tests/   # 128 tests
```

(Any Python environment with `server/requirements.txt` installed works;
`../venv/bin/python` is the repo's checked-out virtualenv.)

See [DEPLOYMENT.md](DEPLOYMENT.md) for deploying to Render.

You will need your own OpenAI API key for now 😔
