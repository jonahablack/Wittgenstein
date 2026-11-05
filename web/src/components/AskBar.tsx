import { ArrowUp, Loader2 } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { useApp } from "../store";

const EXAMPLES: Record<string, string[]> = {
  asteria: [
    "What clearance margin must a Class R inspection unit meet before deployment?",
    "Are legacy units manufactured before 2025 exempt from the clearance margin?",
    "What clearance margin applies to Class S units, and who counts as a registered operator?",
  ],
  "fda-labels": [
    "What is the starting dose of metformin extended-release, and when should it not be started in kidney impairment?",
    "What is the amoxicillin dose for children with ear infections?",
    "Which drugs should not be combined with warfarin, and why?",
  ],
  austen: [
    "Who does Lydia elope with?",
    "How did Elizabeth's opinion of Mr. Darcy change after she read his letter?",
    "What is the airspeed velocity of an unladen swallow?",
  ],
};

const DEFAULT_PROVIDERS: Record<string, boolean> = { extractive: true };

export function AskBar() {
  const ask = useApp((s) => s.ask);
  const run = useApp((s) => s.run);
  const corpusId = useApp((s) => s.corpusId);
  const corpora = useApp((s) => s.corpora);
  const setCorpus = useApp((s) => s.setCorpus);
  const provider = useApp((s) => s.provider);
  const setProvider = useApp((s) => s.setProvider);
  const providers = useApp((s) => s.config?.providers) ?? DEFAULT_PROVIDERS;
  const [q, setQ] = useState("");
  const ref = useRef<HTMLTextAreaElement>(null);
  const corpus = corpora.find((c) => c.corpus_id === corpusId);
  const ready = corpus?.status === "ready";
  const busy = run?.status === "running";

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    el.style.height = "0px";
    el.style.height = `${Math.min(el.scrollHeight, 160)}px`;
  }, [q]);

  const [hint, setHint] = useState<string>();
  // Why asking is blocked right now, if it is. Shown instead of a silent no-op.
  const blocked = !corpus
    ? "Choose a document first."
    : corpus.status === "loading"
      ? `“${corpus.title}” is still being prepared — this takes a few seconds.`
      : corpus.status === "error"
        ? `“${corpus.title}” couldn't be loaded${corpus.error ? `: ${corpus.error}` : "."} Choose another document.`
        : undefined;

  const submit = (text = q) => {
    const t = text.trim();
    const why = blocked ?? (t.length < 2 ? "Type a question first." : undefined);
    if (why) {
      setHint(why);
      return;
    }
    setHint(undefined);
    setQ(t);
    void ask(t);
  };

  const examples = EXAMPLES[corpusId ?? ""] ?? [];

  return (
    <div className="mx-auto max-w-3xl">
      <form
        onSubmit={(e) => {
          e.preventDefault();
          submit();
        }}
        className="group relative rounded-2xl border border-line bg-surface shadow-glow transition focus-within:border-mn/50"
      >
        <textarea
          ref={ref}
          rows={1}
          value={q}
          onChange={(e) => {
            setQ(e.target.value);
            setHint(undefined);
          }}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              submit();
            }
          }}
          placeholder={ready ? `Ask about ${corpus?.title}…` : "Preparing the document…"}
          aria-label="Your question"
          className="block w-full resize-none bg-transparent px-5 pt-4 pb-12 text-[15px] leading-6 text-ink placeholder:text-ink-4 focus:outline-none"
        />
        <div className="absolute inset-x-3 bottom-2.5 flex items-center gap-2">
          <select
            value={corpusId ?? ""}
            onChange={(e) => setCorpus(e.target.value)}
            className="h-8 max-w-[44%] truncate rounded-md border border-line-soft bg-surface-2 px-2 text-xs text-ink-2 sm:hidden"
            aria-label="Document"
          >
            {corpora.map((c) => (
              <option key={c.corpus_id} value={c.corpus_id} disabled={c.status !== "ready"}>
                {c.title}
              </option>
            ))}
          </select>
          <select
            value={provider}
            onChange={(e) => setProvider(e.target.value)}
            className="h-8 max-w-[34%] truncate rounded-md border border-line-soft bg-surface-2 px-2 text-xs text-ink-2 sm:hidden"
            aria-label="Answer style"
          >
            {Object.entries(providers).map(([name, ok]) => (
              <option key={name} value={name} disabled={!ok}>
                {name === "extractive" ? "Quote" : name === "claude" ? "Claude" : "OpenAI"}
              </option>
            ))}
          </select>
          <span className="hidden text-xs text-ink-4 sm:block">
            {corpus?.units ? `${corpus.units.toLocaleString()} passages` : ""}
          </span>
          <button
            type="submit"
            aria-disabled={!ready || q.trim().length < 2}
            title={blocked ?? (q.trim().length < 2 ? "Type a question first" : "Ask")}
            className="ml-auto flex size-8 items-center justify-center rounded-lg bg-ink text-bg transition aria-disabled:opacity-30"
            aria-label="Ask"
          >
            {busy ? <Loader2 className="size-4 animate-spin" /> : <ArrowUp className="size-4" />}
          </button>
        </div>
      </form>
      {hint && (
        <p role="status" className="mt-2 px-1 text-sm text-look">
          {hint}
        </p>
      )}
      {!run && examples.length > 0 && (
        <div className="mt-4 flex flex-wrap justify-center gap-2">
          {examples.map((x) => (
            <button
              key={x}
              onClick={() => submit(x)}
              disabled={!ready}
              className="rounded-full border border-line-soft bg-surface/60 px-3 py-1.5 text-left text-xs text-ink-2 hover:border-line hover:text-ink disabled:opacity-40"
            >
              {x}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
