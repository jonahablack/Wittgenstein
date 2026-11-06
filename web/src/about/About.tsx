import { ArrowLeft } from "lucide-react";
import { useState } from "react";
import { cx } from "../lib";
import { PATTERNS, SOURCES } from "./data";
import { Epigraph } from "./Epigraph";
import { LayerAnimation } from "./LayerAnimation";

const pct = (x: number) => `${Math.round(x * 100)}%`;

const SERIES = [
  { key: "wittgenstein", label: "Wittgenstein", color: "var(--viz-1)" },
  { key: "judge", label: "Entailment judge", color: "var(--viz-2)" },
] as const;

function Ref({ n }: { n: number }) {
  return (
    <sup>
      <a href={`#src-${n}`} className="text-mn hover:underline" onClick={(e) => jump(e, n)}>
        {n}
      </a>
    </sup>
  );
}

function Refs({ ns }: { ns: number[] }) {
  return (
    <sup>
      {ns.map((n, i) => (
        <span key={n}>
          {i > 0 && ","}
          <a href={`#src-${n}`} className="text-mn hover:underline" onClick={(e) => jump(e, n)}>
            {n}
          </a>
        </span>
      ))}
    </sup>
  );
}

/** Footnote links scroll without touching the hash, which holds the route. */
function jump(e: React.MouseEvent, n: number) {
  e.preventDefault();
  document.getElementById(`src-${n}`)?.scrollIntoView({ behavior: "smooth", block: "center" });
}

export function About() {
  return (
    <article className="mx-auto max-w-[720px] pt-10 pb-10">
      <a href="#/" className="inline-flex items-center gap-1.5 text-sm text-ink-3 hover:text-ink">
        <ArrowLeft className="size-4" /> Back to the app
      </a>

      <Epigraph className="mx-auto mt-12 mb-14 max-w-xl" />
      <div className="mx-auto mb-12 h-px w-16 bg-line" aria-hidden />

      <h1 className="text-4xl font-semibold tracking-tight">About Wittgenstein</h1>

      <div className="mt-6 space-y-5 text-pretty text-lg leading-relaxed text-ink-2">
        <p>
          Retrieving information from a body of text is a fundamentally interpretive act. But interpretations can be
          misleading, especially given the presence of linguistic complexities. Large language models have
          documented weaknesses untangling these complexities
          <Refs ns={[1, 2, 3, 4, 5]} />, and any assertion, claim, or inference based on information they retrieve is therefore
          subject to scrutiny
          <Ref n={6} />.
        </p>
        <p>
          Wittgenstein makes retrieved information legible to human review. It is a checking layer for AI systems
          that answer questions from documents, often called retrieval-augmented generation (RAG). It runs alongside
          such a system, reads each answer against the passages it was drawn from, and flags the sentences a person
          should look at, without changing the answers itself. It is built to be self-aware. It
          understands the system it sits inside, from how documents are stored and searched to what the AI model is
          finally shown, and it can tell how a problem early in that process carries through to the answer a person
          reads. That lets it point reviewers to the few passages most likely to have been misread, so they can check
          what matters without wading through false alarms.
        </p>
        <p>
          More broadly, this project explores how humans can remain engaged in AI-mediated information retrieval by
          making model failure modes transparent and auditable.
        </p>
      </div>

      <LayerAnimation />

      <PatternChart />

      <section className="mt-12">
        <h2 className="text-sm font-medium text-ink">Sources</h2>
        <ol className="mt-3 list-decimal space-y-2 pl-5 text-sm text-ink-3">
          {SOURCES.map((s, i) => (
            <li key={s.href} id={`src-${i + 1}`}>
              {s.text}{" "}
              <a href={s.href} target="_blank" rel="noreferrer" className="text-ink-2 hover:text-ink hover:underline">
                {s.label}
              </a>
            </li>
          ))}
        </ol>
      </section>

      <div className="mt-12 space-y-3 border-t border-line pt-6 text-ink-2">
      <p>
        Wittgenstein is also now available via API, so it can check an existing RAG pipeline.{" "}
        <a href="#/api" className="text-mn underline decoration-mn/40 underline-offset-4 hover:decoration-mn">
          Read the API docs
        </a>
        .
      </p>
      <p>Or run it on your own machine, as its own process beside the RAG app you already have:</p>
      <pre className="num overflow-x-auto rounded-xl border border-line bg-surface-2 p-4 text-[13px] leading-relaxed text-ink">
        {`pip install wittgenstein-rag
wittgenstein start`}
      </pre>
      <p>
        Then point your app’s model client at it, or start a Python app with{" "}
        <code className="num text-ink">wittgenstein run</code>. Requests go through unchanged, and every answer is
        checked as this site does, shown in the terminal (<code className="num text-ink">wittgenstein watch</code>) or
        in its own window (<code className="num text-ink">wittgenstein app</code>).
      </p>
      <p>
        Wittgenstein is supported by a grant from the{" "}
        <a
          href="https://www.cosmos-institute.org/"
          target="_blank"
          rel="noreferrer"
          className="text-mn underline decoration-mn/40 underline-offset-4 hover:decoration-mn"
        >
          Cosmos Institute
        </a>
        .
      </p>
      </div>
    </article>
  );
}

function PatternChart() {
  const [hover, setHover] = useState<string | null>(null);
  return (
    <figure className="mt-10 rounded-2xl border border-line bg-surface p-5 sm:p-6">
      <figcaption>
        <div className="font-medium text-ink">An omitted condition is easy to miss</div>
        <p className="mt-1 text-sm text-ink-3">
          Share of answers flagged, when one error is planted in a sentence from an FDA drug label.
        </p>
      </figcaption>
      <div className="mt-4 flex flex-wrap gap-4 text-xs text-ink-2">
        {SERIES.map((s) => (
          <span key={s.key} className="flex items-center gap-1.5">
            <span className="size-2.5 rounded-sm" style={{ background: s.color }} />
            {s.label}
          </span>
        ))}
      </div>

      <div className="mt-5 space-y-5">
        {PATTERNS.map((r) => (
          <div key={r.pattern} className="grid gap-x-4 gap-y-1.5 sm:grid-cols-[170px_1fr]">
            <div>
              <div className="text-sm text-ink">{r.pattern}</div>
              <div className="text-xs text-ink-3">{r.example}</div>
            </div>
            <div className="space-y-1.5 self-center">
              {SERIES.map((s) => {
                const v = r[s.key];
                const id = `${r.pattern}-${s.key}`;
                return (
                  <div
                    key={s.key}
                    className="flex items-center gap-2"
                    onMouseEnter={() => setHover(id)}
                    onMouseLeave={() => setHover(null)}
                    title={`${s.label}: ${pct(v)} of ${r.n}`}
                  >
                    <div className="h-2.5 flex-1">
                      <div
                        className={cx("h-full rounded-r-[4px] transition-opacity", hover && hover !== id && "opacity-60")}
                        style={{ width: `max(${v * 100}%, 2px)`, background: s.color }}
                      />
                    </div>
                    <span className="num w-10 text-right text-xs text-ink-2">{pct(v)}</span>
                  </div>
                );
              })}
            </div>
          </div>
        ))}
      </div>

      <p className="mt-6 text-xs leading-relaxed text-ink-3">
        The entailment judge is the kind of model behind most automatic “faithfulness” scores, with its threshold set
        to flag 5% of correct answers; Wittgenstein flagged none of 240. Both catch a flipped “not”, but the judge
        rarely notices what is missing. A recent study finds the same gap in larger LLM judges of clinical notes
        <Ref n={7} />. Held-out labels for lisinopril, atorvastatin and levothyroxine; 17–60 errors per pattern.
      </p>
    </figure>
  );
}
