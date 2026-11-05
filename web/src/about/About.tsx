import { ArrowLeft, ExternalLink } from "lucide-react";
import { useState } from "react";
import { cx } from "../lib";
import { LITERATURE, NLI_FOOLED, PLANTED, PROBE, REAL } from "./data";

const pct = (x: number) => `${Math.round(x * 100)}%`;

/** The three signals compared, in fixed categorical order (index.css --viz-1..3). */
const METHODS = [
  { key: "wittgenstein", label: "Wittgenstein", color: "var(--viz-1)" },
  { key: "nli", label: "NLI judge", color: "var(--viz-2)" },
  { key: "similarity", label: "Embedding similarity", color: "var(--viz-3)" },
] as const;
type MethodKey = (typeof METHODS)[number]["key"];

export function About() {
  return (
    <article className="mx-auto max-w-[860px] pt-10 pb-10">
      <a href="#/" className="inline-flex items-center gap-1.5 text-sm text-ink-3 hover:text-ink">
        <ArrowLeft className="size-4" /> Back to the app
      </a>

      <header className="mt-6">
        <p className="text-sm font-medium text-mn">About Wittgenstein</p>
        <h1 className="mt-2 text-balance text-4xl font-semibold tracking-tight sm:text-5xl">
          A citation isn’t evidence that the source says it.
        </h1>
        <p className="mt-5 max-w-2xl text-pretty text-lg text-ink-2">
          Retrieval-augmented systems answer from documents and show their sources, and that looks like safety.
          But the model can still misread a passage, mix up two documents, drop the condition a rule depends on,
          or return nothing and cite a passage anyway. Wittgenstein checks every sentence of an answer against
          the passages it came from, and checks the retrieval pipeline that chose them. It then points a person
          to the few places worth a look.
        </p>
      </header>

      <Section kicker="The problem" title="Grounded systems still get their own documents wrong">
        <div className="grid gap-3 sm:grid-cols-3">
          {LITERATURE.map((l) => (
            <a
              key={l.stat}
              href={l.href}
              target="_blank"
              rel="noreferrer"
              className="group rounded-xl border border-line bg-surface p-5 hover:border-ink-4"
            >
              <div className="num text-3xl font-semibold text-ink">{l.stat}</div>
              <p className="mt-2 text-sm text-ink-2">{l.text}</p>
              <p className="mt-3 inline-flex items-center gap-1 text-xs text-ink-3 group-hover:text-ink-2">
                {l.source} <ExternalLink className="size-3" />
              </p>
            </a>
          ))}
        </div>
        <p className="mt-5 text-ink-2">
          In 2024, Air Canada’s chatbot told a grieving customer he could claim a bereavement fare after
          travelling, within 90 days. The airline’s own policy page said the opposite. A tribunal held the airline
          responsible for what its chatbot said. The right answer was in the company’s own document; nothing
          flagged that the answer contradicted it.
        </p>
      </Section>

      <Section kicker="Our test" title="A real model, real drug labels, and the errors it made">
        <p className="text-ink-2">
          We ran a small open model ({REAL.model}) through a full retrieval pipeline over six FDA drug labels
          (metformin, warfarin, amoxicillin, lisinopril, atorvastatin, levothyroxine) and asked it {REAL.total}{" "}
          clinical questions written in advance. Each answer was then checked by hand against the label text.
        </p>
        <OutcomeBar />
        <div className="mt-5 grid gap-3 sm:grid-cols-3">
          <Stat value="55%" text="of answers had a problem a clinician would need to catch." />
          <Stat
            value={`${REAL.problemsWithCitation.k} of ${REAL.problemsWithCitation.n}`}
            text="problem answers carried a citation, so “sources shown” was no warning."
          />
          <Stat value="9 of 9" text="non-answers (a bare “[2]”) cited a passage and said nothing at all." />
        </div>
        <p className="mt-5 text-sm text-ink-3">
          The wrong answers were plausible: metformin’s maximum dose given for atorvastatin; the warfarin
          pregnancy contraindication cited for atorvastatin; the immediate-release maximum given for
          extended-release. A frontier model makes fewer errors, and subtler ones, which makes them harder to see.
        </p>
      </Section>

      <Section kicker="The usual safety nets" title="Do standard groundedness checks catch these?">
        <p className="text-ink-2">
          Pipelines that check answers usually check one of three things: that the answer cites a source, that it
          is similar in meaning to the passage (embedding similarity), or that an entailment model judges it
          supported by the passage (most automatic “faithfulness” scores). We tested both scored checks on 347
          answers, each with one known error planted in a sentence from labels the checker was never tuned on.
          Their thresholds were set so they raise false alarms on 5% of 240 correct answers. Wittgenstein raised none.
        </p>
        <DetectionChart />
        <p className="mt-4 text-sm text-ink-3">
          Embedding similarity barely moves when a dose changes: the error keeps almost every word. The entailment
          judge catches changed numbers and negations, but almost never notices a <em>missing</em> patient group
          or condition. Those omissions turn a correct rule into a wrong one. At the usual 0.5 cut-off it caught{" "}
          {pct(PLANTED.nliAtDefault)} of errors overall.
        </p>

        <h3 className="mt-8 font-medium text-ink">On the real model’s answers</h3>
        <RealTable />
        <p className="mt-3 text-sm text-ink-3">
          The entailment judge and Wittgenstein catch the same share of wrong content here and raise the same
          number of false alarms. The difference is the non-answers: a bare citation contains no claim to judge,
          so a sentence-level judge passes it. Wittgenstein reads it as an answer to the question and flags it as
          empty.
        </p>
      </Section>

      <Section kicker="Why a judge model isn’t enough" title="The entailment model rates dangerous errors as supported">
        <p className="text-ink-2">
          We probed the entailment model directly. Each claim below is wrong. The model rated each one as
          entailed by its source, and a model twice its size did the same. Had its verdict been allowed to clear a
          sentence, it would have <em>hidden</em> exactly these errors.
        </p>
        <div className="mt-5 space-y-3">
          {NLI_FOOLED.map((f) => (
            <div key={f.claim} className="rounded-xl border border-line bg-surface p-4">
              <p className="text-ink">“{f.claim}”</p>
              <p className="mt-1 text-sm text-ink-3">Source: {f.source}</p>
              <div className="mt-3 flex items-center gap-3">
                <span className="w-28 shrink-0 text-xs text-ink-3">Judged supported</span>
                <div className="relative h-2 flex-1 rounded-full bg-surface-2" aria-hidden>
                  <div className="h-2 rounded-full" style={{ width: pct(f.entailment), background: "var(--viz-2)" }} />
                </div>
                <span className="num w-12 text-right text-sm text-ink">{f.entailment.toFixed(2)}</span>
              </div>
              <p className="mt-2 text-xs">
                <span className="rounded bg-omit/15 px-1.5 py-0.5 text-omit">Truth: {f.truth}</span>
              </p>
            </div>
          ))}
        </div>
        <p className="mt-4 text-sm text-ink-3">
          So in Wittgenstein the meaning model can add a warning but can never overrule a deterministic check of
          the numbers, the drug, the formulation or the document.
        </p>
      </Section>

      <Section kicker="Reading vs remembering" title="Does the model read its sources at all?">
        <p className="text-ink-2">
          No check on a single answer can tell whether the model read the passage or answered from memory and
          added a citation. So Wittgenstein can change a value in the passages (500 mg to 750 mg) and ask the same
          model again. A model that reads its context changes its answer to match.
        </p>
        <ProbeBar />
        <p className="mt-4 text-sm text-ink-3">
          This model mostly reads its context. Its errors were misreadings, not memory. But in 8 of 29 probes, one
          edited number made it rewrite its whole answer (“20 mg” became “875 mg”). That instability is now its own
          warning. The one “kept the old value” was a probe mistake (the value came from the question), since fixed.
        </p>
      </Section>

      <Section kicker="What it checks" title="Answer errors and pipeline errors">
        <div className="grid gap-3 sm:grid-cols-2">
          <CheckGroup
            title="In the answer"
            items={[
              "Doses, units, ranges and frequencies against the source, with unit conversion",
              "Dropped patient groups, conditions and hedges",
              "Wrong formulation, route, drug or document",
              "Citations that point to the wrong passage, or to none",
              "Empty answers, off-question answers, false “not stated”",
            ]}
          />
          <CheckGroup
            title="In the pipeline"
            items={[
              "Relevant passages retrieved but left out of the prompt",
              "Instructions hidden in a passage, invisible characters",
              "Chunks cut mid-sentence, duplicates",
              "Embedding-model limits: truncation, unseen text",
              "Whether the model follows its passages (counterfactual probe)",
            ]}
          />
        </div>
        <p className="mt-4 text-sm text-ink-2">
          It runs inside its own pipeline, or alongside an existing one through an API (
          <code className="num text-ink">POST /v1/check</code>): send the question, the retrieved passages and the
          answer, and get back which sentences need a look and why.
        </p>
      </Section>

      <Section kicker="Limits" title="What these results don’t show">
        <ul className="list-disc space-y-1.5 pl-5 text-sm text-ink-2">
          <li>
            The real-model answers were labelled by an AI model against the label text, not by clinicians. Clinician
            labels on Claude and GPT answers are the next step.
          </li>
          <li>
            The samples are small (40 real answers; 17 to 60 planted errors per type), so the intervals are wide.
          </li>
          <li>
            On real answers, 4 of 18 correct ones drew a false alarm on content, mostly faithful paraphrases. This
            is the main remaining cost.
          </li>
          <li>Only FDA drug labels so far. Guidelines, clinical notes and legal text are untested.</li>
        </ul>
      </Section>

      <footer className="mt-14 rounded-2xl border border-line bg-surface p-6">
        <p className="text-sm text-ink-3">Support</p>
        <p className="mt-1 text-lg text-ink">
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
      </footer>
    </article>
  );
}

function Section({ kicker, title, children }: { kicker: string; title: string; children: React.ReactNode }) {
  return (
    <section className="mt-14">
      <p className="text-xs font-medium tracking-wide text-ink-3 uppercase">{kicker}</p>
      <h2 className="mt-1.5 text-balance text-2xl font-semibold tracking-tight">{title}</h2>
      <div className="mt-4">{children}</div>
    </section>
  );
}

function Stat({ value, text }: { value: string; text: string }) {
  return (
    <div className="rounded-xl border border-line bg-surface p-4">
      <div className="num text-2xl font-semibold text-ink">{value}</div>
      <p className="mt-1 text-sm text-ink-2">{text}</p>
    </div>
  );
}

function CheckGroup({ title, items }: { title: string; items: string[] }) {
  return (
    <div className="rounded-xl border border-line bg-surface p-5">
      <h3 className="font-medium text-ink">{title}</h3>
      <ul className="mt-2 space-y-1.5 text-sm text-ink-2">
        {items.map((i) => (
          <li key={i} className="flex gap-2">
            <span className="mt-2 size-1 shrink-0 rounded-full bg-ink-3" />
            {i}
          </li>
        ))}
      </ul>
    </div>
  );
}

/** One 100% bar split into labelled parts, with a 2px surface gap between them. */
function SplitBar({
  parts,
  total,
  colors,
  caption,
}: {
  parts: { key: string; label: string; n: number }[];
  total: number;
  colors: Record<string, string>;
  caption: string;
}) {
  const [hover, setHover] = useState<string | null>(null);
  return (
    <figure className="mt-5">
      <div className="flex h-7 w-full gap-[2px]" role="img" aria-label={caption}>
        {parts.map((p, i) => (
          <div
            key={p.key}
            onMouseEnter={() => setHover(p.key)}
            onMouseLeave={() => setHover(null)}
            title={`${p.label}: ${p.n} of ${total}`}
            className={cx(
              "h-full transition-opacity",
              i === 0 && "rounded-l",
              i === parts.length - 1 && "rounded-r",
              hover && hover !== p.key && "opacity-50",
            )}
            style={{ width: `${(p.n / total) * 100}%`, background: colors[p.key] }}
          />
        ))}
      </div>
      <figcaption className="mt-3 flex flex-wrap gap-x-5 gap-y-1.5 text-sm">
        {parts.map((p) => (
          <span
            key={p.key}
            className={cx("flex items-center gap-2 text-ink-2", hover === p.key && "text-ink")}
            onMouseEnter={() => setHover(p.key)}
            onMouseLeave={() => setHover(null)}
          >
            <span className="size-2.5 rounded-sm" style={{ background: colors[p.key] }} />
            {p.label} <span className="num text-ink">{p.n}</span>
          </span>
        ))}
      </figcaption>
    </figure>
  );
}

function OutcomeBar() {
  return (
    <SplitBar
      parts={REAL.outcomes}
      total={REAL.total}
      caption={`${REAL.total} answers: ${REAL.outcomes.map((o) => `${o.n} ${o.label.toLowerCase()}`).join(", ")}`}
      colors={{
        correct: "var(--ink-4)",
        error: "var(--omit)",
        empty: "color-mix(in oklab, var(--omit) 65%, var(--surface))",
        cite: "color-mix(in oklab, var(--omit) 40%, var(--surface))",
      }}
    />
  );
}

function ProbeBar() {
  return (
    <SplitBar
      parts={PROBE.parts}
      total={PROBE.total}
      caption={`${PROBE.total} probes: ${PROBE.parts.map((o) => `${o.n} ${o.label.toLowerCase()}`).join(", ")}`}
      colors={{
        follows: "var(--viz-3)",
        inconclusive: "var(--look)",
        ignored: "var(--omit)",
      }}
    />
  );
}

function DetectionChart() {
  const [hover, setHover] = useState<{ row: string; m: MethodKey } | null>(null);
  const [table, setTable] = useState(false);
  return (
    <figure className="mt-6 rounded-2xl border border-line bg-surface p-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <figcaption className="text-sm font-medium text-ink">Share of planted errors flagged</figcaption>
        <div className="flex flex-wrap items-center gap-4 text-xs text-ink-2">
          {METHODS.map((m) => (
            <span key={m.key} className="flex items-center gap-1.5">
              <span className="size-2.5 rounded-sm" style={{ background: m.color }} />
              {m.label}
              <span className="text-ink-3">
                ({pct(PLANTED.falseAlarms[m.key])} false alarms)
              </span>
            </span>
          ))}
        </div>
      </div>

      {table ? (
        <table className="mt-4 w-full text-left text-sm">
          <thead className="text-xs text-ink-3">
            <tr>
              <th className="py-1.5 font-normal">Planted error</th>
              <th className="py-1.5 text-right font-normal">n</th>
              {METHODS.map((m) => (
                <th key={m.key} className="py-1.5 text-right font-normal">
                  {m.label}
                </th>
              ))}
            </tr>
          </thead>
          <tbody className="num">
            {[...PLANTED.rows, { error: "All errors", ...PLANTED.all }].map((r) => (
              <tr key={r.error} className="border-t border-line-soft">
                <td className="py-1.5 font-sans text-ink-2">{r.error}</td>
                <td className="py-1.5 text-right text-ink-3">{r.n}</td>
                {METHODS.map((m) => (
                  <td key={m.key} className="py-1.5 text-right text-ink">
                    {pct(r[m.key])}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      ) : (
        <div className="mt-4 space-y-4">
          {[...PLANTED.rows, { error: "All errors", example: "", ...PLANTED.all }].map((r) => (
            <div key={r.error} className={cx("grid gap-x-4 sm:grid-cols-[190px_1fr]", r.error === "All errors" && "border-t border-line pt-4")}>
              <div className="mb-1.5 sm:mb-0">
                <div className="text-sm text-ink">{r.error}</div>
                {r.example && <div className="text-xs text-ink-3">{r.example}</div>}
              </div>
              <div className="relative space-y-[3px]">
                {METHODS.map((m) => {
                  const v = r[m.key];
                  const on = hover?.row === r.error && hover.m === m.key;
                  return (
                    <div
                      key={m.key}
                      className="group relative flex h-[10px] items-center"
                      onMouseEnter={() => setHover({ row: r.error, m: m.key })}
                      onMouseLeave={() => setHover(null)}
                    >
                      {/* hit target taller than the mark */}
                      <div className="absolute inset-x-0 -inset-y-[2px]" />
                      <div
                        className={cx("h-[8px] rounded-r-[4px] transition-opacity", hover && !on && "opacity-55")}
                        style={{ width: `max(${v * 100}%, 2px)`, background: m.color }}
                      />
                      {on && (
                        <div className="pointer-events-none absolute -top-8 left-0 z-10 rounded-md border border-line bg-elev px-2 py-1 text-xs whitespace-nowrap text-ink shadow-glow">
                          {m.label}: <span className="num">{pct(v)}</span>{" "}
                          <span className="text-ink-3">of {r.n}</span>
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            </div>
          ))}
          <div className="grid gap-x-4 sm:grid-cols-[190px_1fr]">
            <div />
            <div className="num flex justify-between text-[11px] text-ink-4">
              <span>0%</span>
              <span>50%</span>
              <span>100%</span>
            </div>
          </div>
        </div>
      )}
      <button onClick={() => setTable((t) => !t)} className="mt-4 text-xs text-ink-3 underline underline-offset-4 hover:text-ink">
        {table ? "Show as chart" : "Show as table"}
      </button>
    </figure>
  );
}

function RealTable() {
  return (
    <div className="mt-3 overflow-x-auto rounded-xl border border-line bg-surface">
      <table className="w-full text-left text-sm">
        <thead className="text-xs text-ink-3">
          <tr>
            <th className="px-4 py-2 font-normal">Answers</th>
            <th className="px-3 py-2 text-right font-normal">n</th>
            <th className="px-3 py-2 text-right font-normal">Similarity</th>
            <th className="px-3 py-2 text-right font-normal">NLI judge</th>
            <th className="px-4 py-2 text-right font-normal">Wittgenstein</th>
          </tr>
        </thead>
        <tbody className="num">
          {REAL.table.map((r) => (
            <tr key={r.group} className="border-t border-line-soft">
              <td className="px-4 py-2 font-sans text-ink-2">{r.group}</td>
              <td className="px-3 py-2 text-right text-ink-3">{r.n}</td>
              <td className="px-3 py-2 text-right text-ink">{r.similarity}</td>
              <td className="px-3 py-2 text-right text-ink">{r.nli}</td>
              <td className="px-4 py-2 text-right text-ink">{r.wittgenstein}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <p className="border-t border-line-soft px-4 py-2 text-xs text-ink-3">
        Number of answers flagged for review. Same thresholds rule as above (5% false alarms on correct answers for
        similarity; 0.5 for the judge).
      </p>
    </div>
  );
}
