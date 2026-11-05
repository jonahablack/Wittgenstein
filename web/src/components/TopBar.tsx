import { ChevronDown, Columns2, FileUp, Loader2, Menu, Sparkles, X } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { cx } from "../lib";
import { type Route, useRoute } from "../route";
import { useApp } from "../store";
import { Upload } from "./Upload";

const PROVIDER_LABEL: Record<string, string> = {
  extractive: "Quote the document",
  claude: "Claude",
  openai: "OpenAI",
  local: "Open model (local)",
};

const NAV: { route: Route; href: string; label: string }[] = [
  { route: "about", href: "#/about", label: "About" },
  { route: "api", href: "#/api", label: "API" },
  { route: "pipeline", href: "#/pipeline", label: "Pipeline" },
];

// Window-size aware. Wide: nav links and every control with its label. Narrower:
// labels drop to icons (below xl), the answer-style picker moves into the menu (below
// lg), the nav links too (below md), then the document picker (below sm). The
// document controls only show on the app itself, not on About / API / Pipeline.

export function TopBar() {
  const route = useRoute();
  const onApp = route === "app";
  const [uploading, setUploading] = useState(false);
  const [menu, setMenu] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);

  useEffect(() => setMenu(false), [route]);
  useEffect(() => {
    if (!menu) return;
    const close = (e: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) setMenu(false);
    };
    const esc = (e: KeyboardEvent) => e.key === "Escape" && setMenu(false);
    document.addEventListener("mousedown", close);
    document.addEventListener("keydown", esc);
    return () => {
      document.removeEventListener("mousedown", close);
      document.removeEventListener("keydown", esc);
    };
  }, [menu]);

  return (
    <header className="sticky top-0 z-30 border-b border-line-soft bg-bg/75 backdrop-blur-xl">
      <div className="mx-auto flex h-14 w-full max-w-[1180px] items-center gap-2 px-4 sm:gap-3 sm:px-6">
        <a href="#/" className="flex shrink-0 items-center gap-2.5" aria-label="Wittgenstein home">
          <svg viewBox="0 0 32 32" className="size-6" aria-hidden>
            <circle cx="16" cy="16" r="3.2" fill="var(--ink)" />
            <circle cx="16" cy="16" r="8" fill="none" stroke="var(--mn)" strokeWidth="1.6" opacity=".85" />
            <circle cx="16" cy="16" r="12.5" fill="none" stroke="var(--kw)" strokeWidth="1.2" opacity=".6" />
          </svg>
          <span className="font-semibold tracking-tight">Wittgenstein</span>
        </a>

        <nav className="ml-2 hidden items-center gap-1 md:flex">
          {NAV.map((n) => (
            <a
              key={n.route}
              href={n.href}
              aria-current={route === n.route ? "page" : undefined}
              className={cx(
                "rounded-md px-2 py-1 text-sm whitespace-nowrap",
                route === n.route ? "bg-surface-2 text-ink" : "text-ink-3 hover:text-ink",
              )}
            >
              {n.label}
            </a>
          ))}
        </nav>

        <div className="ml-auto flex min-w-0 items-center gap-2">
          {onApp && (
            <>
              <DocumentPicker className="hidden sm:block" />
              <AddDocument onClick={() => setUploading(true)} className="hidden sm:flex" />
              <AnswerStyle className="hidden lg:block" />
              <Compare />
            </>
          )}

          <div ref={menuRef} className={cx("relative", onApp ? "lg:hidden" : "md:hidden")}>
            <button
              onClick={() => setMenu((m) => !m)}
              aria-expanded={menu}
              aria-label="Menu"
              className="flex h-9 w-9 items-center justify-center rounded-lg border border-line bg-surface text-ink-2 hover:text-ink"
            >
              {menu ? <X className="size-4" /> : <Menu className="size-4" />}
            </button>
            {menu && (
              <div className="absolute right-0 mt-2 w-[min(320px,calc(100vw-2rem))] space-y-3 rounded-xl border border-line bg-elev p-3 shadow-glow">
                <nav className="flex flex-col md:hidden">
                  {NAV.map((n) => (
                    <a
                      key={n.route}
                      href={n.href}
                      className={cx(
                        "rounded-lg px-2.5 py-2 text-sm",
                        route === n.route ? "bg-surface-2 text-ink" : "text-ink-2 hover:bg-surface-2 hover:text-ink",
                      )}
                    >
                      {n.label}
                    </a>
                  ))}
                  {!onApp && (
                    <a href="#/" className="rounded-lg px-2.5 py-2 text-sm text-ink-2 hover:bg-surface-2 hover:text-ink">
                      Ask a question
                    </a>
                  )}
                </nav>
                {onApp && (
                  <div className="space-y-2 border-line-soft md:border-0 [&:not(:first-child)]:border-t [&:not(:first-child)]:pt-3">
                    <p className="px-1 text-xs text-ink-3 sm:hidden">Document</p>
                    <DocumentPicker className="sm:hidden" wide />
                    <AddDocument
                      onClick={() => {
                        setMenu(false);
                        setUploading(true);
                      }}
                      className="flex w-full sm:hidden"
                      labelled
                    />
                    <p className="px-1 text-xs text-ink-3">How the answer is written</p>
                    <AnswerStyle wide />
                  </div>
                )}
              </div>
            )}
          </div>
        </div>
      </div>
      {uploading && <Upload onClose={() => setUploading(false)} />}
    </header>
  );
}

function DocumentPicker({ className, wide }: { className?: string; wide?: boolean }) {
  const { corpora, corpusId, setCorpus } = useApp();
  const current = corpora.find((c) => c.corpus_id === corpusId);
  return (
    <div className={cx("flex shrink-0 items-center gap-2", className)}>
      <label className={cx("relative block min-w-0", wide ? "w-full" : "w-[150px] md:w-[200px] xl:w-[220px]")}>
        <span className="sr-only">Document</span>
        <select
          value={corpusId ?? ""}
          onChange={(e) => setCorpus(e.target.value)}
          title={current?.title}
          className={cx(
            "h-9 appearance-none truncate rounded-lg border border-line bg-surface pr-8 pl-3 text-sm text-ink focus:outline-2 focus:outline-mn/60",
            "w-full",
          )}
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
      {current?.status === "loading" && <Loader2 className="size-4 shrink-0 animate-spin text-ink-3" />}
    </div>
  );
}

function AddDocument({ onClick, className, labelled }: { onClick: () => void; className?: string; labelled?: boolean }) {
  return (
    <button
      onClick={onClick}
      title="Add document"
      aria-label="Add document"
      className={cx(
        "h-9 shrink-0 items-center gap-1.5 rounded-lg border border-line bg-surface px-3 text-sm whitespace-nowrap text-ink-2 hover:text-ink",
        className,
      )}
    >
      <FileUp className="size-4" /> <span className={labelled ? "" : "hidden xl:inline"}>Add document</span>
    </button>
  );
}

function AnswerStyle({ className, wide }: { className?: string; wide?: boolean }) {
  const { config, provider, setProvider } = useApp();
  return (
    <label className={cx("relative shrink-0", wide && "block w-full", className)}>
      <span className="sr-only">Answer style</span>
      <select
        value={provider}
        onChange={(e) => setProvider(e.target.value)}
        className={cx(
          "h-9 appearance-none rounded-lg border border-line bg-surface pr-8 pl-8 text-sm text-ink focus:outline-2 focus:outline-mn/60",
          wide && "w-full",
        )}
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
  );
}

function Compare() {
  const { config, compare, setCompare } = useApp();
  const comparePipelines = useApp((s) => s.comparePipelines);
  const toggle = useApp((s) => s.toggleComparePipeline);
  const [open, setOpen] = useState(false);
  return (
    <div className="relative shrink-0">
      <button
        onClick={() => (compare ? setOpen((o) => !o) : setCompare(true))}
        title="Compare pipelines"
        aria-label="Compare pipelines"
        className={cx(
          "flex h-9 items-center gap-1.5 rounded-lg border px-3 text-sm whitespace-nowrap",
          compare ? "border-mn/50 bg-mn/10 text-ink" : "border-line bg-surface text-ink-2 hover:text-ink",
        )}
        aria-expanded={open}
      >
        <Columns2 className="size-4" /> <span className="hidden xl:inline">Compare pipelines</span>
      </button>
      {compare && open && (
        <div className="absolute right-0 mt-2 w-[min(320px,calc(100vw-2rem))] rounded-xl border border-line bg-elev p-2 shadow-glow">
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
              setOpen(false);
            }}
            className="mt-1 w-full rounded-lg px-2 py-2 text-left text-sm text-ink-3 hover:bg-surface-2 hover:text-ink"
          >
            Turn comparison off
          </button>
        </div>
      )}
    </div>
  );
}
