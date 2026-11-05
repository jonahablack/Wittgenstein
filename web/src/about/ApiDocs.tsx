import { ArrowLeft, Check, Copy } from "lucide-react";
import { useState } from "react";
import { ServerNotice } from "../components/ServerNotice";

// API documentation for checking an existing RAG pipeline. Source of truth for the
// contract: engine/docs/integration.md and the OpenAPI schema at /docs (FastAPI).

const BASE = typeof window !== "undefined" ? window.location.origin : "http://127.0.0.1:8100";

function Code({ children, lang }: { children: string; lang?: string }) {
  const [copied, setCopied] = useState(false);
  return (
    <div className="group relative mt-3">
      <pre className="num overflow-x-auto rounded-xl border border-line bg-surface-2 p-4 text-[13px] leading-relaxed text-ink">
        <code data-lang={lang}>{children}</code>
      </pre>
      <button
        onClick={() => {
          void navigator.clipboard?.writeText(children).then(() => {
            setCopied(true);
            setTimeout(() => setCopied(false), 1500);
          });
        }}
        className="absolute top-2.5 right-2.5 rounded-md border border-line bg-surface p-1.5 text-ink-3 opacity-0 transition-opacity group-hover:opacity-100 hover:text-ink focus:opacity-100"
        aria-label="Copy code"
      >
        {copied ? <Check className="size-3.5" /> : <Copy className="size-3.5" />}
      </button>
    </div>
  );
}

function H2({ id, children }: { id: string; children: React.ReactNode }) {
  return (
    <h2 id={id} className="mt-12 scroll-mt-20 text-xl font-semibold tracking-tight">
      {children}
    </h2>
  );
}

function Field({ name, children }: { name: string; children: React.ReactNode }) {
  return (
    <tr className="border-t border-line-soft align-top">
      <td className="num py-2 pr-4 whitespace-nowrap text-ink">{name}</td>
      <td className="py-2 text-ink-2">{children}</td>
    </tr>
  );
}

const SECTIONS = [
  ["quickstart", "Quickstart"],
  ["local", "Run locally"],
  ["request", "Request"],
  ["response", "Response"],
  ["levels", "Access levels"],
  ["callbacks", "Your models"],
  ["python", "Python"],
  ["limits", "Limits"],
] as const;

export function ApiDocs() {
  const jump = (e: React.MouseEvent, id: string) => {
    e.preventDefault();
    document.getElementById(id)?.scrollIntoView({ behavior: "smooth", block: "start" });
  };
  return (
    <article className="mx-auto max-w-[760px] pt-10 pb-10">
      <a href="#/about" className="inline-flex items-center gap-1.5 text-sm text-ink-3 hover:text-ink">
        <ArrowLeft className="size-4" /> About
      </a>
      <h1 className="mt-8 text-4xl font-semibold tracking-tight">API</h1>
      <p className="mt-4 text-lg text-ink-2">
        Keep your retriever, chunker, embedding model and LLM. After each question, send Wittgenstein what your
        pipeline already has: the question, what it retrieved, what went into the prompt, and the answer. You get back
        the sentences a person should look at, and why.
      </p>

      <ServerNotice className="mt-4 rounded-xl border border-line bg-surface p-3" />

      <nav className="mt-6 flex flex-wrap gap-x-4 gap-y-1 text-sm">
        {SECTIONS.map(([id, label]) => (
          <a key={id} href={`#${id}`} onClick={(e) => jump(e, id)} className="text-ink-3 hover:text-ink">
            {label}
          </a>
        ))}
        <a href="/docs" target="_blank" rel="noreferrer" className="text-mn hover:underline">
          Interactive reference
        </a>
      </nav>

      <H2 id="quickstart">Quickstart</H2>
      <p className="mt-3 text-ink-2">One request per answer. Citations like [1] refer to the passages in prompt order.</p>
      <Code lang="bash">{`curl -X POST ${BASE}/v1/check \\
  -H "content-type: application/json" \\
  -H "authorization: Bearer $WITTGENSTEIN_KEY" \\
  -d '{
    "query": "What is the starting dose of metformin extended-release?",
    "candidates": [
      {"id": "c17", "text": "The recommended starting dosage of metformin extended-release is 500 mg orally once daily with the evening meal.", "score": 0.82},
      {"id": "c03", "text": "The maximum recommended dose is 2,000 mg once daily.", "score": 0.79}
    ],
    "context_ids": ["c17"],
    "answer": "Start at 850 mg once daily with the evening meal. [1]"
  }'`}</Code>
      <p className="mt-3 text-ink-2">
        The answer says 850 mg; the passage it cites says 500 mg. The response flags that sentence:
      </p>
      <Code lang="json">{`{
  "summary": {
    "needs_review": true,
    "worst_severity": "warning",
    "sentences": [{
      "text": "Start at 850 mg once daily with the evening meal.",
      "status": "review",
      "flags": [
        {"kind": "answer_contradicts_source", "title": "The answer may say the opposite of its source"},
        {"kind": "quantity_mismatch", "title": "“850 mg” doesn't appear in the cited source"}
      ]
    }]
  },
  ...
}`}</Code>
      <p className="mt-3 text-sm text-ink-3">
        <code className="num text-ink-2">summary.needs_review</code> is the one field most integrations need.
      </p>

      <H2 id="local">Run it locally, beside your app</H2>
      <p className="mt-3 text-ink-2">
        Wittgenstein runs as its own process on the machine your app runs on, independent of any terminal. Your app
        sends its requests as usual; Wittgenstein sees them and checks each answer afterwards, so it never adds
        latency or blocks a response.
      </p>
      <Code lang="bash">{`pip install wittgenstein-rag
wittgenstein start                 # runs in the background
wittgenstein watch                 # watch answers being checked, in the terminal
wittgenstein app                   # or in its own window (pip install "wittgenstein-rag[app]")
wittgenstein autostart enable      # optional: start at every login (macOS, Linux, Windows)
wittgenstein status                # running? how many audits?
wittgenstein stop`}</Code>

      <h3 className="mt-6 font-medium text-ink">1. Any language: the model proxy</h3>
      <p className="mt-2 text-ink-2">
        Point your app’s model client at Wittgenstein instead of the provider. Each request goes on to the real API
        unchanged, streamed or not, with your own API key; the response comes straight back. If the request carries
        retrieved passages, the answer is checked in the background.
      </p>
      <Code lang="text">{`OpenAI-compatible   ${BASE}/proxy/openai/v1
Anthropic           ${BASE}/proxy/anthropic`}</Code>
      <Code lang="javascript">{`// e.g. Node, OpenAI SDK
const client = new OpenAI({ baseURL: "${BASE}/proxy/openai/v1" });`}</Code>
      <p className="mt-3 text-sm text-ink-2">
        To forward to a local or other OpenAI-compatible server (Ollama, vLLM, LM Studio, LiteLLM):{" "}
        <code className="num">wittgenstein start --openai-upstream http://localhost:11434</code>. Passages are found in
        the prompt in the usual shapes: <code className="num">[1] …</code>, <code className="num">Source 1: …</code>,{" "}
        <code className="num">&lt;document&gt;…&lt;/document&gt;</code>, or a <code className="num">Context:</code>{" "}
        section. Requests without passages pass through unaudited. Send{" "}
        <code className="num">X-Wittgenstein-Source: my-app</code> to name your app in the feed.
      </p>

      <h3 className="mt-6 font-medium text-ink">2. Python, no code changes</h3>
      <Code lang="bash">{`wittgenstein run python app.py`}</Code>
      <p className="mt-2 text-sm text-ink-2">
        Starts your program with LangChain and LlamaIndex hooked. Nothing is installed into your program’s
        environment. What went into the prompt is read from the prompt itself, so custom templates, rerankers and
        filters need no configuration.
      </p>

      <h3 className="mt-6 font-medium text-ink">3. In code</h3>
      <Code lang="python">{`import wittgenstein.monitor as wm
wm.instrument()               # returns e.g. ["langchain"]

# any other pipeline: report each answer yourself
wm.record(question, retrieved_chunks, answer, prompt=prompt_text)`}</Code>
      <ul className="mt-3 list-disc space-y-1 pl-5 text-sm text-ink-2">
        <li>Reports go from a background thread; your pipeline is never slowed or broken if the server is down.</li>
        <li>
          Settings: <code className="num">WITTGENSTEIN_URL</code> (default the local server),{" "}
          <code className="num">WITTGENSTEIN_API_KEY</code>, <code className="num">WITTGENSTEIN_SOURCE</code>.
        </li>
        <li>
          The feed is kept in ~/.wittgenstein and served only to this machine. API keys passing through the proxy
          are never stored.
        </li>
      </ul>

      <H2 id="request">Request</H2>
      <p className="mt-3 text-ink-2">
        <code className="num text-ink">POST /v1/check</code>, JSON body.
      </p>
      <table className="mt-3 w-full text-left text-sm">
        <tbody>
          <Field name="query">The user’s question.</Field>
          <Field name="candidates">
            What your retriever returned, best first (up to 500): <code className="num">id</code>,{" "}
            <code className="num">text</code>, and optionally <code className="num">score</code>,{" "}
            <code className="num">document_id</code>, <code className="num">location</code>.
          </Field>
          <Field name="context_ids">
            The candidates that went into the prompt, in prompt order. Citations <code className="num">[n]</code> in the
            answer refer to this order. Defaults to all candidates.
          </Field>
          <Field name="answer">Optional. The generated answer; without it, only retrieval and context are checked.</Field>
          <Field name="pipeline">
            Optional declarations, e.g. <code className="num">{`{"retriever": "dense", "embedding_model": "…", "top_k": 5}`}</code>.
            Anything omitted is treated as unknown, never assumed.
          </Field>
          <Field name="corpus_id">Optional. A document uploaded to this server, for document-wide checks.</Field>
          <Field name="embed_url">Optional. Your embedding model, so the checks measure it instead of guessing.</Field>
          <Field name="generator_url">Optional. Your LLM, to test whether it reads its passages.</Field>
        </tbody>
      </table>
      <p className="mt-4 text-sm text-ink-2">
        <span className="text-ink">Batch:</span> <code className="num">POST /v1/check/batch</code> with{" "}
        <code className="num">{`{"items": [request, …]}`}</code>, up to 50. Results come back in order; a failed item
        returns <code className="num">{`{"error": …}`}</code> in its place.
      </p>
      <p className="mt-2 text-sm text-ink-2">
        <span className="text-ink">Keys:</span> when the server requires them, send{" "}
        <code className="num">Authorization: Bearer &lt;key&gt;</code> or <code className="num">X-API-Key: &lt;key&gt;</code>.
      </p>

      <H2 id="response">Response</H2>
      <table className="mt-3 w-full text-left text-sm">
        <tbody>
          <Field name="summary">
            <code className="num">needs_review</code> (the answer or its context needs a look),{" "}
            <code className="num">retrieval_needs_review</code> (the search may have missed evidence), and each answer
            sentence with its status and flags. <code className="num">checked_as</code> shows the full claim checked
            when a sentence can’t stand alone (“Yes.”).
          </Field>
          <Field name="flags">
            Each flag states what was measured, why it could matter, what to check, and the exact source span. Flags
            never say an answer is wrong.
          </Field>
          <Field name="checks">Every check, and whether it passed, flagged something, or wasn’t possible at your access level.</Field>
          <Field name="ledger">What happened to each passage: put in the prompt, or left out, and why.</Field>
          <Field name="access">The access level the request reached, and what it couldn’t check.</Field>
        </tbody>
      </table>

      <H2 id="levels">Access levels</H2>
      <p className="mt-3 text-ink-2">
        What can be checked depends on what you send. The checker knows the pipeline it is looking at, and says
        which checks your request made possible.
      </p>
      <div className="mt-3 overflow-x-auto rounded-xl border border-line">
        <table className="w-full text-left text-sm">
          <thead className="bg-surface text-xs text-ink-3">
            <tr>
              <th className="px-4 py-2 font-normal">You send</th>
              <th className="px-4 py-2 font-normal">Adds</th>
            </tr>
          </thead>
          <tbody className="text-ink-2">
            <tr className="border-t border-line-soft align-top">
              <td className="px-4 py-2 text-ink">Question, passages, answer</td>
              <td className="px-4 py-2">
                Each sentence against the passage it cites: doses and units, patient groups, conditions, negation,
                certainty, wrong drug or document, citations. Conflicts between passages. Prompt injection, hidden
                characters, cut-off chunks, duplicates.
              </td>
            </tr>
            <tr className="border-t border-line-soft align-top">
              <td className="px-4 py-2 text-ink">+ corpus_id</td>
              <td className="px-4 py-2">
                Whether the document covers the question; what keyword or meaning search would have found that your
                retriever didn’t; cross-references your pipeline didn’t follow.
              </td>
            </tr>
            <tr className="border-t border-line-soft align-top">
              <td className="px-4 py-2 text-ink">+ embed_url</td>
              <td className="px-4 py-2">
                Your embedding model is measured: its input window, and how much it registers negation and exact values.
              </td>
            </tr>
            <tr className="border-t border-line-soft align-top">
              <td className="px-4 py-2 text-ink">+ generator_url</td>
              <td className="px-4 py-2">
                A value in the passages is changed and your LLM is asked again. The same value back means it answered
                from memory. Up to two extra generations.
              </td>
            </tr>
          </tbody>
        </table>
      </div>

      <H2 id="callbacks">Connecting your own models</H2>
      <p className="mt-3 text-ink-2">
        Expose two small endpoints next to your pipeline. Only localhost URLs are accepted unless the server allows
        remote ones.
      </p>
      <Code lang="python">{`from fastapi import FastAPI
app = FastAPI()

@app.post("/embed")            # embed_url
def embed(body: dict):
    return {"embeddings": your_model.encode(body["texts"]).tolist()}

@app.post("/generate")         # generator_url
def generate(body: dict):
    context = "\\n\\n".join(f"[{p['n']}] {p['text']}" for p in body["passages"])
    return {"answer": your_llm(question=body["question"], context=context)}`}</Code>

      <H2 id="python">Python</H2>
      <p className="mt-3 text-ink-2">
        A one-file client with no dependencies:{" "}
        <a
          href="https://github.com/jonah410/Wittgenstein/blob/Cosmos/clients/python/wittgenstein_check.py"
          target="_blank"
          rel="noreferrer"
          className="num text-mn hover:underline"
        >
          clients/python/wittgenstein_check.py
        </a>
        .
      </p>
      <Code lang="python">{`from wittgenstein_check import check, needs_review

report = check("${BASE}", api_key=KEY,
               query=question, candidates=cands, context_ids=in_prompt, answer=answer)
if report["summary"]["needs_review"]:
    for f in needs_review(report):
        print(f["title"], "->", f["what_to_check"])`}</Code>
      <p className="mt-4 text-sm text-ink-2">With LangChain:</p>
      <Code lang="python">{`docs = retriever.invoke(question)
cands = [{"id": d.metadata.get("id", str(i)), "text": d.page_content} for i, d in enumerate(docs)]
answer = chain.invoke({"question": question, "context": docs})
report = check(BASE, query=question, candidates=cands, answer=answer)`}</Code>
      <p className="mt-4 text-sm text-ink-2">With LlamaIndex:</p>
      <Code lang="python">{`nodes = retriever.retrieve(question)
cands = [{"id": n.node.node_id, "text": n.node.get_content(), "score": n.score} for n in nodes]
response = query_engine.query(question)
used = [n.node.node_id for n in response.source_nodes]
report = check(BASE, query=question, candidates=cands, context_ids=used, answer=str(response))`}</Code>

      <H2 id="limits">Limits</H2>
      <ul className="mt-3 list-disc space-y-1.5 pl-5 text-sm text-ink-2">
        <li>The checker reads text and rankings, not your model’s internals.</li>
        <li>
          Drug-name and patient-group checks are tuned on drug labels; citation, document, empty-answer and context
          checks work in any domain.
        </li>
        <li>A flag means a person should look, not that the answer is wrong. Correct paraphrases are sometimes flagged.</li>
        <li>Each call is independent; nothing is stored.</li>
      </ul>
    </article>
  );
}
