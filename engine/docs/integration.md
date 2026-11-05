# Checking your own RAG pipeline with Wittgenstein

Keep your retriever, chunker, embedding model and LLM. After each question, send
Wittgenstein what your pipeline already has, and get back the same checks the web app
shows: what may be missing, what was left out and why, what the answer says that its
sources don't, and the few places a person should look.

```
your pipeline:  question -> retrieve -> choose context -> generate answer
                                                 |
                                                 v
                           POST /v1/check  ->  summary, checks, flags, ledger, receipt
```

`/v1/check` and `/live/check` are the same endpoint; `/v1/...` is the stable path to
build against. `POST /v1/check/batch` takes `{"items": [request, ...]}` (up to 50) and
returns the results in order -- one item's failure comes back as `{"error": ...}` in its
place without failing the batch.

**API keys.** When the server sets `WITTGENSTEIN_API_KEYS` (comma-separated), the check
endpoints require one: `Authorization: Bearer <key>` or `X-API-Key: <key>`. Unset (local
use), they're open.

## Running it locally, beside your app

```bash
pip install wittgenstein-rag        # or, from this repo: make wheel && pip install dist/*.whl
wittgenstein start                   # background process; feed at http://127.0.0.1:8100/#/pipeline
wittgenstein autostart enable        # optional: launchd (macOS), systemd user unit (Linux), Startup (Windows)
wittgenstein status | stop
```

`wittgenstein serve` runs the same thing in the foreground (`--demo` adds 4 examples).
State, log, settings and the feed live in `~/.wittgenstein` (`WITTGENSTEIN_HOME`).

Three ways to connect an app; none of them adds latency, since each answer is checked
after it has been returned:

1. **Model proxy (any language).** Base URL `http://127.0.0.1:8100/proxy/openai/v1`
   (OpenAI-compatible) or `http://127.0.0.1:8100/proxy/anthropic`. Requests are forwarded
   unchanged to `WITTGENSTEIN_OPENAI_UPSTREAM` / `WITTGENSTEIN_ANTHROPIC_UPSTREAM`
   (defaults: the providers' APIs; set with `wittgenstein start --openai-upstream ...`),
   streamed or not, with the app's own key, which is never stored. Afterwards the request
   is read for a question and passages (`live/prompt_parse.py`: `[1] ...`, `Source 1: ...`,
   `<document>`, or a `Context:` section); if found, the answer is checked and recorded.
   Requests without passages pass through unaudited. `X-Wittgenstein-Source` names the app.
   Local requests only.
2. **`wittgenstein run python app.py`** starts a Python program with a `sitecustomize`
   shim on `PYTHONPATH` that loads the LangChain / LlamaIndex hooks (a standalone copy of
   `wittgenstein.monitor`, standard library only), so nothing is installed into the
   program's environment. An existing `sitecustomize` still runs.
3. **In code:**

```python
import wittgenstein.monitor as wm
wm.instrument()          # hooks LangChain and LlamaIndex if installed; returns what it hooked
# any other pipeline, after each answer:
wm.record(question, retrieved_chunks, answer, prompt=prompt_text)
```

- **LangChain**: a callback handler is registered through LangChain's configure hook,
  so every chain, retriever and model call reports without code changes. A model call
  is audited when its prompt contains retrieved passages (question rewriting and other
  calls without them are skipped).
- **LlamaIndex**: an event handler on the root instrumentation dispatcher; the
  response's source nodes are what went into the prompt.
- **What went into the prompt** is read from the prompt text, so custom templates,
  rerankers and filters need no configuration.
- Reports go from a background thread and never raise; queued reports are flushed (up
  to 15 s) when a short script exits.
- Each audit goes to `POST /v1/audits` and is listed by `GET /v1/audits`. The feed is
  kept in `~/.wittgenstein/audits.jsonl` and, unless the server sets API keys, served
  only to this machine.

## How much context your model handles

The answering model's capacity is measured, not assumed: `wittgenstein measure-model
--provider local|claude|openai`, or for your own model through its generator callback,
`POST /v1/generator-profile {"generator_url": ..., "model": "<pipeline.llm>"}` (60
generations). Fictional probes with near-identical decoys at 2, 4, 8 and 12 passages,
graded by value and citation; the result, with every probe and answer, is saved in
`~/.wittgenstein/models/`. Afterwards any run (or `/v1/check` with `pipeline.llm`) that
gives the model more passages than its measured reliable size is flagged
(`context_over_capacity`), with the measured curve as evidence. Trimming to that size is
opt-in (`fit_context`): on 40 held-out drug-label questions it fixed 2 answers and broke 4
for Qwen2-1.5B. The over-capacity note is informational: passage count alone is a weak
predictor.

Two per-answer checks look for misleading context directly:
- `answer_from_neighbor`: a part of the question (a definition, an amount, a frequency;
  named classes, articles and tiers must match exactly) answered from a look-alike
  passage while the passage that answers it was in the prompt; both are quoted.
- `answer_context_sensitive` (with `counterfactual` / "Test the model", or a
  `generator_url`): the model is asked again with only the passages most relevant to
  each question part (or the same passages reversed). A different value or yes/no in
  two answers means at least one is wrong; held out: 2 flags, both real errors, none on
  correct answers.

## Access levels

What can be checked depends on what you send. Every check in the response says whether
it ran, passed, flagged something, or was not possible at your access level (and why).

| You send | Level | Adds |
|---|---|---|
| question, candidates, context, answer | `trace` | Answer verification (each sentence vs. the passage it cites: support, doses/units, patient-population qualifiers, conditions and exceptions, certainty, recommendation grade); conflicting values or polarity between passages used; near-miss identifiers; per-part coverage; redundancy; cutoff checks |
| + `corpus_id` (document uploaded to this server) | `document` | Whether the document covers the question at all; what keyword or meaning search would have found that your retriever didn't; severed context; cross-references and definitions your pipeline didn't follow |
| + `embed_url` (your embedding model) | `+embeddings` | Your model is measured: input window, how much it registers negation and exact values, dilution in long passages; then the embedding probes run against it |
| + `generator_url` (your LLM) | `+generator` | The counterfactual probe: a value the answer took from a passage is changed in the passages and your generator is asked again. Same value back = answering from memory; the answer jumping elsewhere = unstable. Up to 2 extra generations |

At every level, what reached the model is checked too: instructions aimed at the model
inside a passage (prompt injection), invisible characters, passages cut off
mid-sentence, and duplicates.

Without `embed_url`, comparisons "by meaning" use the checker's own model and say so;
probes that are only meaningful for your model report "needs access" instead of guessing.

## Request

```json
POST /live/check
{
  "query": "What is the starting dose of metformin extended-release?",
  "candidates": [
    {"id": "chunk-17", "text": "...", "score": 0.82, "document_id": "metformin-label", "location": "2.2"},
    {"id": "chunk-03", "text": "...", "score": 0.79}
  ],
  "context_ids": ["chunk-17"],
  "answer": "Start at 500 mg once daily with the evening meal. [1]",
  "pipeline": {"retriever": "dense", "embedding_model": "your-model", "top_k": 5, "token_budget": 2000},
  "corpus_id": "fda-labels",
  "embed_url": "http://localhost:9000/embed"
}
```

- `candidates`: what your retriever returned, best first (up to 500). Your scores are
  optional; ids must be unique.
- `context_ids`: what went into the prompt, in prompt order. **Citations `[n]` in the
  answer refer to this order (1-based).** Defaults to all candidates.
- `answer`: optional. The answer is always verified against exactly the context text you
  sent, even when `corpus_id` is set.
- `pipeline`: optional declarations. Anything omitted is treated as unknown, never
  assumed.
- `corpus_id`: a document uploaded to this server (`POST /live/corpora`, or the web
  app's "Add document"). Your candidates are matched to its passages by text; any that
  don't match are listed in `unmatched_candidates` and still checked as sent.
- `generator_url`: an endpoint that answers with your pipeline's own LLM:
  `POST {"question": "...", "passages": [{"n": 1, "text": "..."}, ...]}` → `{"answer": "..."}`.
  Same localhost rule as `embed_url`; `generator_headers` is passed through.
- `embed_url`: an endpoint that embeds texts with your model:
  `POST {"texts": ["...", ...]}` → `{"embeddings": [[...], ...]}`. For safety, only
  `localhost` URLs are accepted unless the server sets `WITTGENSTEIN_ALLOW_REMOTE_EMBED=1`.
  `embed_headers` is passed through (e.g. an auth header).

## Response (abridged)

```json
{
  "api_version": "1.1",
  "summary": {"needs_review": true, "retrieval_needs_review": false, "worst_severity": "warning",
              "answer_flags": 1, "context_flags": 0, "retrieval_flags": 0,
              "sentences": [{"sentence_id": "s1", "text": "2,550 mg.", "status": "review",
                             "checked_as": "The maximum daily dose of metformin extended-release is 2,550 mg.",
                             "flags": [{"kind": "quantity_referent", "severity": "warning",
                                        "title": "“2,550 mg” belongs to immediate-release, not extended-release"}]}]},
  "access": {"level": "document+embeddings", "scope": "document", "notes": ["..."]},
  "receipt": {"candidates": 5, "in_prompt": 1, "worth_a_look": 2, "checks_passed": 14, "checks_run": 16,
              "checks_not_possible": 3},
  "flags": [{"kind": "quantity_mismatch", "disposition": "needs_review", "severity": "warning",
             "title": "“850 mg” doesn't appear in the cited source", "observation": "...",
             "why_it_matters": "...", "what_to_check": "...",
             "refs": [{"unit_id": "...", "document_id": "...", "char_start": 0, "char_end": 120, "quote": "..."}],
             "registry": {"mechanism_id": "HYP_THRESHOLD_UNIT_COMPARATOR_MISBINDING",
                          "epistemic_status": "research_hypothesis"}}],
  "checks": [{"label": "Doses, numbers and units match the source", "outcome": "flagged", "detail": "..."}],
  "ledger": [{"unit_id": "...", "fate": "selected", "reason": "Put in the prompt by your pipeline."}],
  "sentences": [{"text": "...", "cited": [1], "support": "direct_support_candidate", "flag_ids": ["..."]}],
  "unit_to_candidates": {"...": ["chunk-17"]},
  "unmatched_candidates": [],
  "model_profile": {"model": "your-model", "measured_window_tokens": 512, "measured_on": "your model"}
}
```

`summary.needs_review` is the one field most integrations need: the answer, or what
reached the model, has something a person should look at. `retrieval_needs_review`
says the search may have missed evidence even when the answer is fine.
`checked_as` shows the claim actually checked when a sentence can't be checked alone
("Yes." is checked as the question's statement, affirmed).

Flags never say an answer is wrong. Each states what was measured or matched, why it
could matter, what to check, and the exact source span. Flags that correspond to a
registry failure mechanism carry its id and epistemic status as recorded in the registry.

## Python

`clients/python/wittgenstein_check.py` (standard library only):

```python
from wittgenstein_check import check, needs_review

report = check("http://127.0.0.1:8100", query=q, candidates=cands, context_ids=ctx, answer=answer)
if report["summary"]["needs_review"]:
    for f in needs_review(report):
        print(f["title"], "->", f["what_to_check"])
```

### LangChain

```python
docs = retriever.invoke(question)                       # list[Document]
cands = [{"id": d.metadata.get("id", str(i)), "text": d.page_content,
          "score": d.metadata.get("score")} for i, d in enumerate(docs)]
answer = chain.invoke({"question": question, "context": docs})
report = check(BASE, query=question, candidates=cands, answer=answer,
               pipeline={"retriever": "dense", "embedding_model": "text-embedding-3-small"})
```

### LlamaIndex

```python
nodes = retriever.retrieve(question)                    # list[NodeWithScore]
cands = [{"id": n.node.node_id, "text": n.node.get_content(), "score": n.score} for n in nodes]
response = query_engine.query(question)
used = [n.node.node_id for n in response.source_nodes]
report = check(BASE, query=question, candidates=cands, context_ids=used, answer=str(response))
```

### Exposing your embedding model (`embed_url`)

```python
from fastapi import FastAPI
app = FastAPI()

@app.post("/embed")
def embed(body: dict):
    return {"embeddings": your_model.encode(body["texts"]).tolist()}
# uvicorn embed_server:app --port 9000   ->   embed_url="http://localhost:9000/embed"
```

### Exposing your generator (`generator_url`)

```python
@app.post("/generate")
def generate(body: dict):
    context = "\n\n".join(f"[{p['n']}] {p['text']}" for p in body["passages"])
    return {"answer": your_llm(question=body["question"], context=context)}
```

## What the checks catch (red-team suite)

`engine/scripts/redteam/scenarios.py` holds 33 cases -- pipeline errors, model errors
and correct-answer controls -- each a request with the flags it must (or must not)
raise; `tests/unit/test_live_redteam.py` runs them on every test run. Pipeline errors:
injected instructions, hidden characters, superseded versions, another document's
passage, off-by-one and out-of-range citations, a retrieved-but-dropped passage behind
a false "not stated", severed chunks, duplicates. Model errors: a number from the
wrong referent (immediate- vs extended-release), bare "Yes."/"2,550 mg." answers,
narrowed ranges, lost negation, swapped drug names, frequency changes, generalized
populations, a group's severity or threshold dropped ("severe renal impairment" as "renal
impairment"), dropped conditions, parametric additions, false abstention. Controls:
values echoed from the question, worked-out doses, equal amounts in other units,
faithful paraphrase, correct abstention.

## Limits

- The checker measures text and rankings; it does not see your model's internals
  (attention, logits). Token-level attribution is planned for open-weights models.
- Drug-name and patient-group checks use vocabularies tuned on drug labels; other
  domains need their own (the document-name check is domain-independent).
- The meaning-level model (NLI) is small and misreads numbers and entity swaps as
  agreement; it can add warnings but never clears a sentence a deterministic check
  flagged.
- Matching your candidates to an uploaded document is textual; heavily rewritten or
  summarized chunks may not match and are reported as unmatched.
- `/v1/check` calls are independent and nothing is stored; `/v1/audits` records to the local feed.
