import { CircleAlert, CircleCheck, Radio, Trash2 } from "lucide-react";
import { useEffect, useState } from "react";
import { cx } from "../lib";

// "Your pipeline": the live feed of audits sent by wittgenstein.monitor from the user's
// own RAG pipeline (GET /v1/audits). Polls every 2 s; nothing here leaves the machine.

type Brief = {
  audit_id: string;
  created: string;
  source: string | null;
  query: string;
  answer: string;
  needs_review: boolean;
  retrieval_needs_review: boolean;
  candidates: number;
  in_prompt: number;
};
type Flag = {
  flag_id: string;
  stage: string;
  severity: string;
  disposition: string;
  title: string;
  observation: string;
  why_it_matters: string;
  what_to_check: string;
};
type Sentence = { sentence_id: string; text: string; status: string; checked_as?: string | null; flags: { title: string }[] };
type Audit = {
  audit_id: string;
  created: string;
  source: string | null;
  request: { query: string; answer?: string; candidates: { id: string; text: string }[]; context_ids?: string[] };
  report: {
    summary: { needs_review: boolean; sentences: Sentence[] };
    flags: Flag[];
    receipt: { candidates: number; in_prompt: number; checks_passed: number; checks_run: number };
    ledger: { unit_id: string; fate: string; reason: string }[];
  };
};

async function get<T>(path: string): Promise<T> {
  const r = await fetch(path);
  if (!r.ok) throw new Error(`${r.status}`);
  return (await r.json()) as T;
}

const time = (iso: string) => new Date(iso).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });

export function PipelineView() {
  const [list, setList] = useState<Brief[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  // 403: this server doesn't serve the feed to other machines (a hosted deployment).
  const hosted = error === "403";
  const [selected, setSelected] = useState<string | null>(null);
  const [audit, setAudit] = useState<Audit | null>(null);

  useEffect(() => {
    let live = true;
    const load = () =>
      get<{ audits: Brief[] }>("/v1/audits")
        .then((d) => {
          if (!live) return;
          setList(d.audits);
          setError(null);
          setSelected((s) => s ?? d.audits[0]?.audit_id ?? null);
        })
        .catch((e: Error) => {
          if (!live) return;
          setError(e.message);
          if (e.message === "403") clearInterval(t); // won't change: stop asking
        });
    const t = setInterval(load, 2000);
    void load();
    return () => {
      live = false;
      clearInterval(t);
    };
  }, []);

  useEffect(() => {
    if (!selected) return setAudit(null);
    void get<Audit>(`/v1/audits/${selected}`).then(setAudit).catch(() => setAudit(null));
  }, [selected]);

  const clear = async () => {
    await fetch("/v1/audits", { method: "DELETE" });
    setList([]);
    setSelected(null);
  };

  return (
    <div className="pt-8 pb-10">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-3xl font-semibold tracking-tight">Your pipeline</h1>
          {!hosted && (
            <p className="mt-1.5 flex items-center gap-2 text-sm text-ink-3">
              <Radio className={cx("size-4", error ? "text-omit" : "text-handled")} />
              {error ? `Can’t reach the local server (${error}).` : "Watching for answers from your RAG pipeline."}
            </p>
          )}
        </div>
        {!!list?.length && (
          <button onClick={() => void clear()} className="flex items-center gap-1.5 rounded-lg border border-line bg-surface px-3 py-1.5 text-sm text-ink-3 hover:text-ink">
            <Trash2 className="size-4" /> Clear
          </button>
        )}
      </div>

      {hosted && <OnYourMachine />}
      {list && list.length === 0 && <Connect />}

      {!!list?.length && (
        <div className="mt-6 grid gap-5 lg:grid-cols-[320px_1fr]">
          <ul className="space-y-1.5 lg:max-h-[calc(100vh-180px)] lg:overflow-y-auto lg:pr-1">
            {list.map((a) => (
              <li key={a.audit_id}>
                <button
                  onClick={() => setSelected(a.audit_id)}
                  className={cx(
                    "w-full rounded-xl border px-3.5 py-2.5 text-left",
                    selected === a.audit_id ? "border-mn/50 bg-mn/10" : "border-line bg-surface hover:border-ink-4",
                  )}
                >
                  <div className="flex items-center gap-2 text-xs text-ink-3">
                    {a.needs_review ? <CircleAlert className="size-3.5 text-look" /> : <CircleCheck className="size-3.5 text-handled" />}
                    <span>{a.needs_review ? "Worth a look" : "No issues found"}</span>
                    <span className="ml-auto num">{time(a.created)}</span>
                  </div>
                  <div className="mt-1 line-clamp-2 text-sm text-ink">{a.query}</div>
                  {a.source && <div className="mt-1 text-xs text-ink-4">{a.source}</div>}
                </button>
              </li>
            ))}
          </ul>
          {audit && <Detail audit={audit} />}
        </div>
      )}
    </div>
  );
}

function Detail({ audit }: { audit: Audit }) {
  const { request: req, report } = audit;
  const look = report.flags.filter((f) => f.disposition === "needs_review");
  const left = report.ledger.filter((l) => l.fate !== "selected");
  return (
    <div className="min-w-0 space-y-4">
      <section className="rounded-2xl border border-line bg-surface p-5">
        <p className="text-xs text-ink-3">Question</p>
        <p className="mt-1 text-lg text-ink">{req.query}</p>
        <p className="mt-4 text-xs text-ink-3">Answer, sentence by sentence</p>
        {report.summary.sentences.length ? (
          <div className="mt-2 space-y-2">
            {report.summary.sentences.map((s) => (
              <div key={s.sentence_id} className={cx("rounded-lg border-l-2 py-1 pl-3", s.status === "review" ? "border-look" : "border-handled/60")}>
                <p className="text-ink">{s.text}</p>
                {s.checked_as && s.checked_as !== s.text && <p className="text-xs text-ink-3">Checked as: {s.checked_as}</p>}
                {s.flags.map((f) => (
                  <p key={f.title} className="text-sm text-look">
                    {f.title}
                  </p>
                ))}
              </div>
            ))}
          </div>
        ) : (
          <p className="mt-2 text-ink-2">{req.answer || <span className="text-ink-3">No answer was sent.</span>}</p>
        )}
      </section>

      <section className="rounded-2xl border border-line bg-surface p-5">
        <div className="flex flex-wrap gap-x-6 gap-y-1 text-sm text-ink-2">
          <span>
            <span className="num text-ink">{report.receipt.candidates}</span> retrieved
          </span>
          <span>
            <span className="num text-ink">{report.receipt.in_prompt}</span> in the prompt
          </span>
          <span>
            <span className="num text-ink">
              {report.receipt.checks_passed}/{report.receipt.checks_run}
            </span>{" "}
            checks passed
          </span>
        </div>
        {left.length > 0 && (
          <p className="mt-2 text-sm text-ink-3">
            Left out of the prompt: {left.length} passage{left.length > 1 ? "s" : ""}.
          </p>
        )}
      </section>

      {look.length > 0 && (
        <section>
          <h2 className="text-sm font-medium text-ink">Worth a look</h2>
          <div className="mt-2 space-y-2.5">
            {look.map((f) => (
              <div key={f.flag_id} className="rounded-xl border border-line bg-surface p-4">
                <div className="flex items-start gap-2">
                  <CircleAlert className={cx("mt-0.5 size-4 shrink-0", f.severity === "warning" ? "text-omit" : "text-look")} />
                  <div className="min-w-0">
                    <p className="text-ink">{f.title}</p>
                    <p className="mt-1 text-sm text-ink-2">{f.observation}</p>
                    <p className="mt-2 text-sm text-ink-3">
                      <span className="text-ink-2">Check:</span> {f.what_to_check}
                    </p>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </section>
      )}
    </div>
  );
}

function OnYourMachine() {
  return (
    <div className="mt-8 max-w-2xl rounded-2xl border border-line bg-surface p-6">
      <h2 className="font-medium text-ink">This page runs on your own computer</h2>
      <p className="mt-2 text-sm leading-relaxed text-ink-2">
        It shows, as they happen, the answers your own RAG app produces, each checked the way this site checks them.
        Those answers stay on your machine, so a hosted site like this one never sees them and this page is empty
        here. To use it, install Wittgenstein where your app runs:
      </p>
      <pre className="num mt-4 overflow-x-auto rounded-xl border border-line bg-surface-2 p-4 text-[13px] leading-relaxed text-ink">
        {`pip install wittgenstein-rag
wittgenstein start      # runs in the background
wittgenstein app        # this page, in a window
wittgenstein watch      # or in the terminal`}
      </pre>
      <p className="mt-4 text-sm text-ink-2">
        Then point your app’s model client at{" "}
        <code className="num text-ink">http://127.0.0.1:8100/proxy/openai/v1</code>, or start a Python app with{" "}
        <code className="num text-ink">wittgenstein run python app.py</code>.{" "}
        <a href="#/api" className="text-mn underline decoration-mn/40 underline-offset-4 hover:decoration-mn">
          More in the API docs
        </a>
        .
      </p>
      <p className="mt-4 text-sm text-ink-3">
        To try the checks here without installing anything, ask a question on the{" "}
        <a href="#/" className="underline underline-offset-4 hover:text-ink">
          main page
        </a>
        .
      </p>
    </div>
  );
}

function Connect() {
  const base = window.location.origin;
  return (
    <div className="mt-8 max-w-2xl rounded-2xl border border-line bg-surface p-6">
      <h2 className="font-medium text-ink">Connect your RAG app</h2>
      <p className="mt-1 text-sm text-ink-2">
        Wittgenstein runs on its own, beside your app. Connect it one of three ways; every answer then appears here
        with the same checks the site runs. Your app is never slowed or blocked.
      </p>
      <p className="mt-5 text-sm font-medium text-ink">Any language: point your model client here</p>
      <p className="mt-1 text-sm text-ink-3">Requests go on to the real API unchanged; answers are checked afterwards.</p>
      <pre className="num mt-2 overflow-x-auto rounded-xl border border-line bg-surface-2 p-4 text-[13px] text-ink">
        {`OpenAI-compatible   ${base}/proxy/openai/v1
Anthropic           ${base}/proxy/anthropic`}
      </pre>
      <p className="mt-5 text-sm font-medium text-ink">Python with LangChain or LlamaIndex: no code changes</p>
      <pre className="num mt-2 overflow-x-auto rounded-xl border border-line bg-surface-2 p-4 text-[13px] text-ink">
        {`wittgenstein run python app.py`}
      </pre>
      <p className="mt-5 text-sm font-medium text-ink">Or in code</p>
      <pre className="num mt-2 overflow-x-auto rounded-xl border border-line bg-surface-2 p-4 text-[13px] text-ink">
        {`import wittgenstein.monitor as wm
wm.instrument()                       # LangChain / LlamaIndex
wm.record(question, chunks, answer)   # anything else`}
      </pre>
      <p className="mt-5 text-sm text-ink-3">
        Keep it running in the background with <code className="num text-ink-2">wittgenstein start</code>, or at every
        login with <code className="num text-ink-2">wittgenstein autostart enable</code>. Watch from the terminal with{" "}
        <code className="num text-ink-2">wittgenstein watch</code>, or open this view in its own window with{" "}
        <code className="num text-ink-2">wittgenstein app</code>.
      </p>
    </div>
  );
}
