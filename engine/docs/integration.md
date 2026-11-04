# Checking your own RAG pipeline with Wittgenstein

Keep your retriever, chunker, embedding model and LLM. After each question, send
Wittgenstein what your pipeline already has, and get back the same checks the web app
shows: what may be missing, what was left out and why, what the answer says that its
sources don't, and the few places a person should look.

```
your pipeline:  question -> retrieve -> choose context -> generate answer
                                                 |
                                                 v
                         POST /live/check  ->  checks, flags, ledger, receipt
```

## Access levels

What can be checked depends on what you send. Every check in the response says whether
it ran, passed, flagged something, or was not possible at your access level (and why).

| You send | Level | Adds |
|---|---|---|
| question, candidates, context, answer | `trace` | Answer verification (each sentence vs. the passage it cites: support, doses/units, patient-population qualifiers, conditions and exceptions, certainty); near-miss identifiers; per-part coverage; redundancy; cutoff checks |
| + `corpus_id` (document uploaded to this server) | `document` | Whether the document covers the question at all; what keyword or meaning search would have found that your retriever didn't; severed context; cross-references and definitions your pipeline didn't follow |
| + `embed_url` (your embedding model) | `+embeddings` | Your model is measured: input window, how much it registers negation and exact values, dilution in long passages; then the embedding probes run against it |

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
- `embed_url`: an endpoint that embeds texts with your model:
  `POST {"texts": ["...", ...]}` → `{"embeddings": [[...], ...]}`. For safety, only
  `localhost` URLs are accepted unless the server sets `WITTGENSTEIN_ALLOW_REMOTE_EMBED=1`.
  `embed_headers` is passed through (e.g. an auth header).

## Response (abridged)

```json
{
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

Flags never say an answer is wrong. Each states what was measured or matched, why it
could matter, what to check, and the exact source span. Flags that correspond to a
registry failure mechanism carry its id and epistemic status as recorded in the registry.

## Python

`clients/python/wittgenstein_check.py` (standard library only):

```python
from wittgenstein_check import check, needs_review

report = check("http://127.0.0.1:8100", query=q, candidates=cands, context_ids=ctx, answer=answer)
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

## Limits

- The checker measures text and rankings; it does not see your model's internals
  (attention, logits). Token-level attribution is planned for open-weights models.
- Matching your candidates to an uploaded document is textual; heavily rewritten or
  summarized chunks may not match and are reported as unmatched.
- Each call is independent; nothing is stored unless you also use the web app.
