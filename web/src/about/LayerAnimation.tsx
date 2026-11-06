import { motion, useReducedMotion } from "motion/react";
import { useEffect, useId, useState } from "react";

// About page: Wittgenstein as a third layer beside an existing RAG pipeline. A question
// moves through the user's pipeline unchanged; at each step, Wittgenstein reads what
// happened and, at the end, routes one sentence to a reviewer. Two layouts (wide,
// narrow) from one step sequence; reduced motion shows the final frame. Each step carries a
// small abstract figure (a ripple, a scatter of stored passages, assembled context, a
// network, lines of text), and the band is a faint field of points Wittgenstein reads.

const STEPS = 7; // 0 question · 1 search · 2 prompt · 3 model · 4 answer · 5 flag · 6 hold
const STEP_MS = 1300;

type P = { x: number; y: number };
type Layout = {
  w: number;
  h: number;
  nodes: P[]; // question, search, prompt, model, answer
  band: { x: number; y: number; w: number; h: number };
  taps: { from: P; to: P; label: [string, string]; at: P; anchor: "middle" | "start" }[];
  flag: { x: number; y: number; w: number };
  bandLabel: P;
};

const NH = 66; // node height

const NAMES = ["Question", "Search", "Prompt", "LLM", "Answer"];
const SUBS = ["from a user", "vector store", "context builder", "your model", "to the user"];

const WIDE: Layout = (() => {
  const xs = [70, 215, 360, 505, 650];
  const y = 70;
  const by = 200;
  return {
    w: 720,
    h: 362,
    nodes: xs.map((x) => ({ x, y })),
    band: { x: 10, y: by - 30, w: 700, h: 182 },
    bandLabel: { x: 26, y: by - 10 },
    taps: [
      { from: { x: xs[1], y: y + NH / 2 }, to: { x: xs[1], y: by + 12 }, label: ["What the search", "found and missed"], at: { x: xs[1], y: by + 34 }, anchor: "middle" },
      { from: { x: xs[2], y: y + NH / 2 }, to: { x: xs[2], y: by + 12 }, label: ["What was left", "out of the prompt"], at: { x: xs[2], y: by + 34 }, anchor: "middle" },
      { from: { x: xs[4], y: y + NH / 2 }, to: { x: xs[4], y: by + 12 }, label: ["Each sentence vs", "its passage"], at: { x: xs[4], y: by + 34 }, anchor: "middle" },
    ],
    flag: { x: 290, y: by + 72, w: 410 },
  };
})();

const NARROW: Layout = (() => {
  const ys = [44, 134, 224, 314, 404];
  const x = 70;
  const bx = 160;
  return {
    w: 360,
    h: 540,
    nodes: ys.map((y) => ({ x, y })),
    band: { x: bx - 12, y: 8, w: 360 - bx + 8, h: 440 },
    bandLabel: { x: bx, y: 28 },
    taps: [
      { from: { x: x + 58, y: ys[1] }, to: { x: bx + 4, y: ys[1] }, label: ["What the search", "found and missed"], at: { x: bx + 12, y: ys[1] - 4 }, anchor: "start" },
      { from: { x: x + 58, y: ys[2] }, to: { x: bx + 4, y: ys[2] }, label: ["What was left", "out of the prompt"], at: { x: bx + 12, y: ys[2] - 4 }, anchor: "start" },
      { from: { x: x + 58, y: ys[4] }, to: { x: bx + 4, y: ys[4] }, label: ["Each sentence vs", "its passage"], at: { x: bx + 12, y: ys[4] - 4 }, anchor: "start" },
    ],
    flag: { x: 10, y: 466, w: 340 },
  };
})();

const TAP_STEP = [1, 2, 4]; // the step at which each tap lights

export function LayerAnimation() {
  const reduce = useReducedMotion();
  const [step, setStep] = useState(reduce ? 5 : 0);
  useEffect(() => {
    if (reduce) return;
    const t = setInterval(() => setStep((s) => (s + 1) % STEPS), STEP_MS);
    return () => clearInterval(t);
  }, [reduce]);

  return (
    <figure className="mt-10 rounded-2xl border border-line bg-surface p-4 sm:p-6">
      <figcaption>
        <div className="font-medium text-ink">A third layer, beside the pipeline you already run</div>
        <p className="mt-1 text-sm text-ink-3">
          Your retrieval and your model are unchanged. Wittgenstein reads each step as it happens and sends the few
          sentences worth checking to a person.
        </p>
      </figcaption>
      <div className="mt-4 hidden sm:block">
        <Scene l={WIDE} step={step} />
      </div>
      <div className="mt-4 sm:hidden">
        <Scene l={NARROW} step={step} />
      </div>
    </figure>
  );
}

function Scene({ l, step }: { l: Layout; step: number }) {
  const packetAt = Math.min(step, 4);
  const p = l.nodes[packetAt];
  const ease = [0.2, 0.7, 0.2, 1] as const;
  const dots = useId().replace(/:/g, "");
  return (
    <svg viewBox={`0 0 ${l.w} ${l.h}`} className="h-auto w-full" role="img" aria-label="A question passes through search, prompt building and the model to an answer. At the search, the prompt and the answer, Wittgenstein records what happened, and it sends one flagged sentence to a reviewer.">
      <defs>
        <pattern id={dots} width={14} height={14} patternUnits="userSpaceOnUse">
          <circle cx={7} cy={7} r={0.9} fill="var(--mn)" opacity={0.28} />
        </pattern>
      </defs>

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
              {t.label.map((line, j) => (
                <text key={j} x={t.at.x} y={t.at.y + j * 15} fontSize={12} textAnchor={t.anchor} fill="var(--ink-2)">
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
        <rect x={l.flag.x} y={l.flag.y} width={l.flag.w} height={64} rx={10} fill="var(--bg-elev)" stroke="var(--look)" strokeOpacity={0.8} />
        <text x={l.flag.x + 14} y={l.flag.y + 22} fontSize={11} fill="var(--look)" fontWeight={600}>
          To a reviewer · worth a look
        </text>
        <text x={l.flag.x + 14} y={l.flag.y + 42} fontSize={12.5} fill="var(--ink)">
          “2,550 mg” is the immediate-release maximum,
        </text>
        <text x={l.flag.x + 14} y={l.flag.y + 57} fontSize={12.5} fill="var(--ink)">
          not extended-release.
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
