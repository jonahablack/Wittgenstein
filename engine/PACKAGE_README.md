# Wittgenstein

A review layer for retrieval-augmented generation (RAG). It runs beside the pipeline you
already have, checks every answer against the passages it came from, and points a
person to the few sentences worth a look: a dose that isn't in the source, a patient
group or condition that was dropped, a citation to the wrong passage, an answer that
says nothing at all.

It also knows the pipeline it is watching: how the documents were split, what the
search returned, and what never reached the model. So a flag can say whether the model
misread a passage or was never given the right one.

## Install and run

```bash
pip install wittgenstein-rag
wittgenstein serve          # opens the local interface at http://127.0.0.1:8100
```

Add `--demo` to see a few example answers first. Everything runs on your machine; the
first run downloads a small English language model (about 12 MB).

## Connect your pipeline

Add two lines where your app starts:

```python
import wittgenstein.monitor as wm
wm.instrument()
```

LangChain and LlamaIndex pipelines are detected and hooked automatically, with no other
code changes. Every answer then appears in the local interface with what was retrieved,
what went into the prompt, and what needs checking. For any other pipeline, report each
answer yourself:

```python
wm.record(question, retrieved_chunks, answer, prompt=prompt_text)
```

Reporting happens in the background and never slows or breaks your pipeline.

## Or call the API

```bash
curl -X POST http://127.0.0.1:8100/v1/check -H "content-type: application/json" -d '{
  "query": "What is the starting dose of metformin extended-release?",
  "candidates": [{"id": "c1", "text": "The recommended starting dosage is 500 mg once daily with the evening meal."}],
  "answer": "Start at 850 mg once daily. [1]"
}'
```

`summary.needs_review` in the response says whether a person should look, and each
flagged sentence says why. Full documentation is in the running app under **API**.

## Limits

Flags mean "a person should look", not "this is wrong". The checks are tuned on drug
labels; citation, empty-answer, document and context checks work in any domain. See the
[repository](https://github.com/jonahablack/Wittgenstein) for the evaluation behind it.

Supported by a grant from the [Cosmos Institute](https://www.cosmos-institute.org/).
