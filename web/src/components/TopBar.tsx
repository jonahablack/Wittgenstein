import { ChevronDown, Columns2, FileUp, Loader2, Sparkles } from "lucide-react";
import { useState } from "react";
import { cx } from "../lib";
import { useApp } from "../store";
import { Upload } from "./Upload";

const PROVIDER_LABEL: Record<string, string> = {
  extractive: "Quote the document",
  claude: "Claude",
  openai: "OpenAI",
  local: "Open model (local)",
};

export function TopBar() {
  const { corpora, corpusId, setCorpus, config, provider, setProvider, compare, setCompare } = useApp();
  const comparePipelines = useApp((s) => s.comparePipelines);
  const toggle = useApp((s) => s.toggleComparePipeline);
  const [uploading, setUploading] = useState(false);
  const [pipesOpen, setPipesOpen] = useState(false);
  const current = corpora.find((c) => c.corpus_id === corpusId);

  return (
    <header className="sticky top-0 z-30 border-b border-line-soft bg-bg/75 backdrop-blur-xl">
      <div className="mx-auto flex h-14 w-full max-w-[1180px] items-center gap-3 px-4 sm:px-6">
        <a href="#/" className="flex items-center gap-2.5" aria-label="Wittgenstein home">
          <svg viewBox="0 0 32 32" className="size-6" aria-hidden>
            <circle cx="16" cy="16" r="3.2" fill="var(--ink)" />
            <circle cx="16" cy="16" r="8" fill="none" stroke="var(--mn)" strokeWidth="1.6" opacity=".85" />
            <circle cx="16" cy="16" r="12.5" fill="none" stroke="var(--kw)" strokeWidth="1.2" opacity=".6" />
          </svg>
          <span className="font-semibold tracking-tight">Wittgenstein</span>
        </a>

        <a href="#/about" className="ml-3 text-sm text-ink-3 hover:text-ink">
          About
        </a>

        <div className="ml-auto flex min-w-0 items-center gap-2">
          <label className="relative hidden min-w-0 sm:block">
            <span className="sr-only">Document</span>
            <select
              value={corpusId ?? ""}
              onChange={(e) => setCorpus(e.target.value)}
              className="h-9 max-w-[280px] appearance-none truncate rounded-lg border border-line bg-surface pr-8 pl-3 text-sm text-ink focus:outline-2 focus:outline-mn/60"
            >
              {corpora.map((c) => (
                <option key={c.corpus_id} value={c.corpus_id} disabled={c.status !== "ready"}>
                  {c.title}
                  {c.status === "loading" ? " (preparing…)" : c.status === "error" ? " (failed)" : ""}
                </option>
              ))}
            </select>
            <ChevronDown className="pointer-events-none absolute top-2.5 right-2.5 size-4 text-ink-3" />
          </label>
          {current?.status === "loading" && <Loader2 className="size-4 animate-spin text-ink-3" />}

          <button
            onClick={() => setUploading(true)}
            className="flex h-9 items-center gap-1.5 rounded-lg border border-line bg-surface px-3 text-sm text-ink-2 hover:text-ink"
          >
            <FileUp className="size-4" /> <span className="hidden md:inline">Add document</span>
          </button>

          <label className="relative hidden sm:block">
            <span className="sr-only">Answer style</span>
            <select
              value={provider}
              onChange={(e) => setProvider(e.target.value)}
              className="h-9 appearance-none rounded-lg border border-line bg-surface pr-8 pl-8 text-sm text-ink focus:outline-2 focus:outline-mn/60"
              title="How the answer is written"
            >
              {Object.entries(config?.providers ?? { extractive: true }).map(([name, ok]) => (
                <option key={name} value={name} disabled={!ok}>
                  {PROVIDER_LABEL[name] ?? name}
                  {ok ? "" : " (not configured)"}
                </option>
              ))}
            </select>
            <Sparkles className="pointer-events-none absolute top-2.5 left-2.5 size-4 text-ink-3" />
            <ChevronDown className="pointer-events-none absolute top-2.5 right-2.5 size-4 text-ink-3" />
          </label>

          <div className="relative">
            <button
              onClick={() => (compare ? setPipesOpen((o) => !o) : setCompare(true))}
              className={cx(
                "flex h-9 items-center gap-1.5 rounded-lg border px-3 text-sm",
                compare ? "border-mn/50 bg-mn/10 text-ink" : "border-line bg-surface text-ink-2 hover:text-ink",
              )}
              aria-expanded={pipesOpen}
            >
              <Columns2 className="size-4" /> <span className="hidden md:inline">Compare pipelines</span>
            </button>
            {compare && pipesOpen && (
              <div className="absolute right-0 mt-2 w-80 rounded-xl border border-line bg-elev p-2 shadow-glow">
                <p className="px-2 pt-1 pb-2 text-xs text-ink-3">
                  The self-aware pipeline always runs. Add others to see what they would have done differently.
                </p>
                {config?.pipelines
                  .filter((p) => p.pipeline_id !== config.default_pipeline)
                  .map((p) => (
                    <label key={p.pipeline_id} className="flex cursor-pointer gap-2.5 rounded-lg px-2 py-2 hover:bg-surface-2">
                      <input
                        type="checkbox"
                        className="mt-1 accent-[var(--mn)]"
                        checked={comparePipelines.includes(p.pipeline_id)}
                        onChange={() => toggle(p.pipeline_id)}
                      />
                      <span>
                        <span className="block text-sm text-ink">{p.label}</span>
                        <span className="block text-xs text-ink-3">{p.description}</span>
                      </span>
                    </label>
                  ))}
                <button
                  onClick={() => {
                    setCompare(false);
                    setPipesOpen(false);
                  }}
                  className="mt-1 w-full rounded-lg px-2 py-2 text-left text-sm text-ink-3 hover:bg-surface-2 hover:text-ink"
                >
                  Turn comparison off
                </button>
              </div>
            )}
          </div>
        </div>
      </div>
      {uploading && <Upload onClose={() => setUploading(false)} />}
    </header>
  );
}
