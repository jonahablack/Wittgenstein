import { AnimatePresence, motion, useReducedMotion } from "motion/react";
import { useEffect, useId, useState } from "react";

// About page: Wittgenstein as a third layer beside an existing RAG pipeline, told through
// one real case from the metformin label. The question asks for the extended-release
// maximum; search returns two look-alike passages (extended-release 2,000 mg, and a
// sentence about switching to immediate-release, 2,550 mg); the model answers 2,550 mg;
// Wittgenstein sees the number came from the immediate-release passage and routes the
// sentence to a reviewer. A panel above the pipeline shows what is passing through at each
// step; the taps into the band say what Wittgenstein noted there. Two layouts (wide,
// narrow) from one step sequence; reduced motion shows the final frame. Each step also
// carries a small abstract figure, and the band is a faint field of points.

// 0 question · 1 search · 2 prompt · 3 model · 4 answer · 5 flag · 6 hold
const STEP_MS = [2400, 3200, 3200, 1700, 2600, 5000, 900];
const STEPS = STEP_MS.length;

type P = { x: number; y: number };
type Layout = {
  w: number;
  h: number;
  panel: { x: number; y: number; w: number; h: number };
  nodes: P[]; // question, search, prompt, model, answer
  band: { x: number; y: number; w: number; h: number };
  taps: { from: P; to: P; at: P; anchor: "middle" | "start" | "end" }[];
  flag: { x: number; y: number; w: number };
  bandLabel: P;
};

const NH = 66; // node height
const FH = 82; // flag height

const NAMES = ["Question", "Search", "Prompt", "LLM", "Answer"];
const SUBS = ["from a user", "vector store", "context builder", "your model", "to the user"];

// What Wittgenstein notes at each tap, shown once the question has passed it.
const TAP_STEP = [1, 2, 4];
const TAP_TEXT: [string, string][] = [
  ["Two look-alikes:", "2,000 mg · 2,550 mg"],
  ["Both in the prompt,", "a few words apart"],
  ["“2,550 mg” is from [2],", "immediate-release"],
];

const QUESTION = "What is the maximum daily dose of metformin extended-release?";

// What is passing through the pipeline at each step (the answer stays from step 4 on).
const PANEL: { label: string; lines: React.ReactNode[] }[] = [
  { label: "The question", lines: [`“${QUESTION}”`] },
  {
    label: "Search returns",
    lines: [
      <>[1] Extended-release: “…up to a maximum of <b>2,000 mg</b> once daily…”</>,
      <>[2] “…may switch to immediate-release tablets and titrate to the maximum total daily dosage of <b>2,550 mg</b>.”</>,
    ],
  },
  {
    label: "The prompt sent to the model",
    lines: ["Answer only from the context.  [1] …2,000 mg once daily…  [2] …immediate-release… 2,550 mg.", `Question: ${QUESTION}`],
  },
  { label: "The model", lines: ["Reads the two passages and writes an answer…"] },
];

const WIDE: Layout = (() => {
  const xs = [70, 215, 360, 505, 650];
  const y = 152;
  const by = 282;
  return {
    w: 720,
    h: by + 64 + FH + 20,
    panel: { x: 10, y: 6, w: 700, h: 92 },
    nodes: xs.map((x) => ({ x, y })),
    band: { x: 10, y: by - 30, w: 700, h: 64 + FH + 40 },
    bandLabel: { x: 26, y: by - 10 },
    taps: [1, 2, 4].map((k) => ({
      from: { x: xs[k], y: y + NH / 2 },
      to: { x: xs[k], y: by + 6 },
      // the last label sits right-aligned so it stays inside the band
      at: { x: k === 4 ? 700 : xs[k], y: by + 28 },
      anchor: k === 4 ? ("end" as const) : ("middle" as const),
    })),
    flag: { x: 250, y: by + 60, w: 450 },
  };
})();

const NARROW: Layout = (() => {
  const ys = [190, 280, 370, 460, 550];
  const x = 70;
  const bx = 160;
  const bandTop = ys[0] - 42;
  const bandH = ys[4] + NH / 2 + 10 - bandTop;
  return {
    w: 360,
    h: bandTop + bandH + FH + 28,
    panel: { x: 6, y: 4, w: 348, h: 128 },
    nodes: ys.map((y) => ({ x, y })),
    band: { x: bx - 12, y: bandTop, w: 360 - bx + 8, h: bandH },
    bandLabel: { x: bx, y: bandTop + 20 },
    taps: [1, 2, 4].map((k) => ({ from: { x: x + 58, y: ys[k] }, to: { x: bx + 4, y: ys[k] }, at: { x: bx + 12, y: ys[k] - 4 }, anchor: "start" as const })),
    flag: { x: 6, y: bandTop + bandH + 14, w: 348 },
  };
})();

export function LayerAnimation() {
  const reduce = useReducedMotion();
  const [step, setStep] = useState(reduce ? 5 : 0);
  useEffect(() => {
    if (reduce) return;
    const t = setTimeout(() => setStep((s) => (s + 1) % STEPS), STEP_MS[step]);
    return () => clearTimeout(t);
  }, [reduce, step]);

  return (
    <figure className="mt-10 rounded-2xl border border-line bg-surface p-4 sm:p-6">
      <figcaption>
        <div className="font-medium text-ink">A third layer, beside the pipeline you already run</div>
        <p className="mt-1 text-sm text-ink-3">
          Your retrieval and your model are unchanged. Wittgenstein reads each step as it happens and sends the few
          sentences worth checking to a person. Here, one question about a drug label, from search to answer.
        </p>
      </figcaption>
      <div className="mt-4 hidden sm:block">
        <Scene l={WIDE} step={step} narrow={false} />
      </div>
      <div className="mt-4 sm:hidden">
        <Scene l={NARROW} step={step} narrow />
      </div>
    </figure>
  );
}

function Panel({ l, step, narrow }: { l: Layout; step: number; narrow: boolean }) {
  const k = Math.min(step, 4);
  const flagged = step >= 5;
  return (
    <foreignObject x={l.panel.x} y={l.panel.y} width={l.panel.w} height={l.panel.h}>
      <div className="h-full overflow-hidden rounded-[10px] border border-line bg-surface-2 px-3 py-2">
        <AnimatePresence mode="wait" initial={false}>
          <motion.div key={k} initial={{ opacity: 0, y: 4 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -4 }} transition={{ duration: 0.3 }}>
            <div className="text-[10.5px] font-medium tracking-wide text-ink-3 uppercase">{k === 4 ? "The answer" : PANEL[k].label}</div>
            <div className={narrow ? "mt-1 space-y-1 text-[11.5px] leading-snug text-ink" : "mt-1 space-y-0.5 text-[12.5px] leading-snug text-ink"}>
              {k === 4 ? (
                <p>
                  “The maximum daily dose is{" "}
                  <span className="rounded px-0.5 transition-colors duration-500" style={flagged ? { background: "color-mix(in oklab, var(--look) 22%, transparent)", color: "var(--ink)" } : undefined}>
                    2,550 mg
                  </span>{" "}
                  [2].”
                </p>
              ) : (
                PANEL[k].lines.map((line, j) => <p key={j}>{line}</p>)
              )}
            </div>
          </motion.div>
        </AnimatePresence>
      </div>
    </foreignObject>
  );
}

function Scene({ l, step, narrow }: { l: Layout; step: number; narrow: boolean }) {
  const packetAt = Math.min(step, 4);
  const p = l.nodes[packetAt];
  const ease = [0.2, 0.7, 0.2, 1] as const;
  const dots = useId().replace(/:/g, "");
  return (
    <svg viewBox={`0 0 ${l.w} ${l.h}`} className="h-auto w-full" role="img" aria-label="A question about the maximum daily dose of metformin extended-release passes through search, prompt building and the model. Search returns two look-alike passages, 2,000 mg for extended-release and 2,550 mg for immediate-release. The model answers 2,550 mg. Wittgenstein sees the number came from the immediate-release passage and sends the sentence to a reviewer.">
      <defs>
        <pattern id={dots} width={14} height={14} patternUnits="userSpaceOnUse">
          <circle cx={7} cy={7} r={0.9} fill="var(--mn)" opacity={0.28} />
        </pattern>
      </defs>

      <Panel l={l} step={step} narrow={narrow} />

      {/* Wittgenstein band: a faint field of points */}
      <rect x={l.band.x} y={l.band.y} width={l.band.w} height={l.band.h} rx={14} fill="color-mix(in oklab, var(--mn) 6%, transparent)" />
      <rect x={l.band.x} y={l.band.y} width={l.band.w} height={l.band.h} rx={14} fill={`url(#${dots})`} stroke="var(--mn)" strokeOpacity={0.35} strokeDasharray="4 4" />
      <text x={l.bandLabel.x} y={l.bandLabel.y} fontSize={12} fontWeight={600} fill="var(--mn)">
        Wittgenstein
      </text>

      {/* pipeline links */}
      {l.nodes.slice(0, -1).map((a, i) => {
        const b = l.nodes[i + 1];
        return <line key={i} x1={a.x} y1={a.y} x2={b.x} y2={b.y} stroke="var(--line)" strokeWidth={2} />;
      })}

      {/* taps */}
      {l.taps.map((t, i) => {
        const on = step >= TAP_STEP[i];
        return (
          <g key={i}>
            <motion.line x1={t.from.x} y1={t.from.y} x2={t.to.x} y2={t.to.y} stroke="var(--mn)" strokeWidth={1.5} strokeDasharray="3 3" initial={false} animate={{ opacity: on ? 0.9 : 0.15 }} transition={{ duration: 0.4 }} />
            {step === TAP_STEP[i] && (
              <motion.circle key={step} cx={t.to.x} cy={t.to.y} fill="none" stroke="var(--mn)" strokeWidth={1.2} initial={{ r: 4, opacity: 0.7 }} animate={{ r: 22, opacity: 0 }} transition={{ duration: 1.1, ease: "easeOut" }} />
            )}
            <motion.g initial={false} animate={{ opacity: on ? 1 : 0.25 }} transition={{ duration: 0.4 }}>
              <circle cx={t.to.x} cy={t.to.y} r={4} fill="var(--mn)" />
              {TAP_TEXT[i].map((line, j) => (
                <text key={j} x={t.at.x} y={t.at.y + j * 15} fontSize={11.5} textAnchor={t.anchor} fill="var(--ink-2)">
                  {line}
                </text>
              ))}
            </motion.g>
          </g>
        );
      })}

      {/* pipeline nodes */}
      {l.nodes.map((n, i) => (
        <g key={i}>
          <rect x={n.x - 56} y={n.y - NH / 2} width={112} height={NH} rx={10} fill="var(--surface-2)" stroke={step === i || (i === 4 && step >= 4) ? "var(--ink-3)" : "var(--line)"} />
          <g transform={`translate(${n.x} ${n.y - 13}) scale(1.2) translate(${-n.x} ${-(n.y - 13)})`}>
            <Figure kind={i} x={n.x} y={n.y - 13} step={step} />
          </g>
          <text x={n.x} y={n.y + 10} fontSize={13} textAnchor="middle" fill="var(--ink)" fontWeight={500}>
            {NAMES[i]}
          </text>
          <text x={n.x} y={n.y + 24} fontSize={10.5} textAnchor="middle" fill="var(--ink-3)">
            {SUBS[i]}
          </text>
        </g>
      ))}

      {/* the question moving through, with a short trail */}
      {[0.12, 0.06].map((d, k) => (
        <motion.circle key={k} r={5 - k * 1.5} fill="var(--ink)" initial={false} animate={{ cx: p.x, cy: p.y - NH / 2 - 10, opacity: step >= 6 ? 0 : 0.25 - k * 0.1 }} transition={{ duration: step === 0 ? 0 : 0.7, ease, delay: step === 0 ? 0 : d * (k + 1) * 2 }} />
      ))}
      <motion.circle r={6} fill="var(--ink)" initial={false} animate={{ cx: p.x, cy: p.y - NH / 2 - 10, opacity: step >= 6 ? 0 : 1 }} transition={{ duration: step === 0 ? 0 : 0.7, ease }} />

      {/* the flag to a reviewer */}
      <motion.g initial={false} animate={{ opacity: step >= 5 ? 1 : 0, y: step >= 5 ? 0 : 8 }} transition={{ duration: 0.45, ease }}>
        <rect x={l.flag.x} y={l.flag.y} width={l.flag.w} height={FH} rx={10} fill="var(--bg-elev)" stroke="var(--look)" strokeOpacity={0.8} />
        <text x={l.flag.x + 14} y={l.flag.y + 22} fontSize={11} fill="var(--look)" fontWeight={600}>
          To a reviewer · worth a look
        </text>
        <text x={l.flag.x + 14} y={l.flag.y + 43} fontSize={12.5} fill="var(--ink)">
          “2,550 mg” is the immediate-release maximum [2].
        </text>
        <text x={l.flag.x + 14} y={l.flag.y + 62} fontSize={12.5} fill="var(--ink-2)">
          The extended-release maximum is 2,000 mg [1].
        </text>
      </motion.g>
    </svg>
  );
}

// Small abstract figures, one per pipeline step, drawn in a 48 x 16 box centred on (x, y).
// Each wakes when the question reaches its step.
const SCATTER: [number, number][] = [[-20, -4], [-12, 5], [-6, -6], [2, 2], [8, -3], [14, 6], [20, -5], [-16, 0], [11, 1]];
const NEAR = new Set([3, 4, 8]); // the passages the search returns
const BARS = [36, 28, 32, 22]; // context assembled into the prompt; the third is left out
const NET = [[-6, 0, 6], [-4, 4], [-6, 0, 6]];
const LINES = [40, 30, 36];

function Figure({ kind, x, y, step }: { kind: number; x: number; y: number; step: number }) {
  const on = step >= kind;
  const now = step === kind;
  const t = { duration: 0.5 };
  const dim = "var(--ink-3)";
  if (kind === 0)
    return (
      <g>
        <circle cx={x} cy={y} r={3} fill={on ? "var(--ink-2)" : dim} />
        {[0, 1].map((k) =>
          now ? (
            <motion.circle key={`${step}-${k}`} cx={x} cy={y} fill="none" stroke="var(--ink-3)" strokeWidth={1} initial={{ r: 3, opacity: 0.8 }} animate={{ r: 12, opacity: 0 }} transition={{ duration: 1.1, delay: k * 0.35, ease: "easeOut" }} />
          ) : (
            <circle key={k} cx={x} cy={y} r={7 + k * 4} fill="none" stroke="var(--line)" strokeWidth={1} />
          ),
        )}
      </g>
    );
  if (kind === 1)
    return (
      <g>
        <motion.circle cx={x + 6} cy={y} fill="none" stroke="var(--mn)" strokeWidth={1} strokeDasharray="2 2" initial={false} animate={{ r: on ? 10 : 4, opacity: on ? 0.7 : 0 }} transition={t} />
        {SCATTER.map(([dx, dy], k) => (
          <motion.circle key={k} cx={x + dx} cy={y + dy} r={1.8} initial={false} animate={{ fill: on && NEAR.has(k) ? "var(--mn)" : dim, opacity: on && !NEAR.has(k) ? 0.45 : 0.85 }} transition={t} />
        ))}
      </g>
    );
  if (kind === 2)
    return (
      <g>
        {BARS.map((w, k) => {
          const left = k === 2;
          return (
            <motion.rect key={k} x={x - 20} y={y - 7 + k * 4} height={2.4} rx={1.2} initial={false} animate={{ width: on ? w : 10, opacity: left && on ? 0.3 : 0.85 }} fill={left && on ? "var(--mn)" : dim} transition={{ ...t, delay: on ? k * 0.08 : 0 }} />
          );
        })}
      </g>
    );
  if (kind === 3) {
    const cols = NET.map((col, c) => col.map((dy) => [x - 14 + c * 14, y + dy] as const));
    return (
      <g>
        {cols.slice(0, -1).flatMap((col, c) =>
          col.flatMap(([x1, y1], a) =>
            cols[c + 1].map(([x2, y2], b) => (
              <motion.line key={`${c}-${a}-${b}`} x1={x1} y1={y1} x2={x2} y2={y2} stroke={now ? "var(--ink-3)" : "var(--line)"} strokeWidth={0.8} initial={false} animate={{ opacity: now ? [0.3, 1, 0.3] : 0.8 }} transition={now ? { duration: 0.9, repeat: Infinity, delay: (a + b) * 0.08 } : t} />
            )),
          ),
        )}
        {cols.flat().map(([cx, cy], k) => (
          <circle key={k} cx={cx} cy={cy} r={1.8} fill={on ? "var(--ink-2)" : dim} />
        ))}
      </g>
    );
  }
  const flagged = step >= 5;
  return (
    <g>
      {LINES.map((w, k) => (
        <motion.rect key={k} x={x - 20} y={y - 6 + k * 5} height={2.4} rx={1.2} initial={false} animate={{ width: on ? w : 8 }} fill={k === 1 && flagged ? "var(--look)" : dim} transition={{ ...t, delay: on ? k * 0.1 : 0 }} />
      ))}
    </g>
  );
}
