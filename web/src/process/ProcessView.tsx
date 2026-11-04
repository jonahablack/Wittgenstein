import { CircleDot, Info, Wrench } from "lucide-react";
import { AnimatePresence, motion } from "motion/react";
import { useMemo } from "react";
import { useField } from "../components/useField";
import { cx } from "../lib";
import { useApp } from "../store";
import { EvidenceField } from "./EvidenceField";
import { frameAt } from "./frame";
import { Ledger } from "./Ledger";
import { useReplay } from "./replay";
import { StageFlow } from "./StageFlow";
import { Timeline } from "./Timeline";

const LEGEND = [
  { color: "var(--kw)", label: "found by keyword" },
  { color: "var(--mn)", label: "found by meaning" },
  { color: "var(--both)", label: "found by both" },
  { color: "var(--facet)", label: "found by one part of the question" },
  { color: "var(--ink)", label: "used as evidence" },
  { color: "var(--pull)", label: "pulled in by a follow-up" },
  { color: "var(--omit)", label: "no room in the context" },
];

export default function ProcessView() {
  const run = useApp((s) => s.run)!;
  const active = useApp((s) => s.activePipeline) ?? run.order[0];
  const setActive = useApp((s) => s.setActivePipeline);
  const pipeline = run.pipelines[active];
  const field = useField(run, pipeline);
  const replay = useReplay(run.events, active);
  const frame = useMemo(() => frameAt(replay.steps, replay.index, replay.progress), [replay.steps, replay.index, replay.progress]);
  const feed = frame.flags.filter((f) => f.disposition !== "informational").slice(-6).reverse();

  return (
    <section className="rounded-2xl border border-line bg-surface p-4 shadow-glow sm:p-5" aria-label="How the answer was produced">
      <header className="mb-3 flex flex-wrap items-center gap-3">
        <h2 className="text-sm font-semibold">How this answer was produced</h2>
        {run.order.length > 1 && (
          <div className="flex gap-1 rounded-lg bg-surface-2 p-0.5">
            {run.order.map((id) => (
              <button
                key={id}
                onClick={() => setActive(id)}
                className={cx(
                  "rounded-md px-2.5 py-1 text-xs",
                  id === active ? "bg-elev text-ink shadow-glow" : "text-ink-3 hover:text-ink",
                )}
              >
                {run.pipelines[id]?.label ?? id}
              </button>
            ))}
          </div>
        )}
      </header>

      <div className="grid gap-5 lg:grid-cols-[minmax(0,1fr)_300px]">
        <div className="min-w-0">
          <div className="overflow-hidden rounded-xl border border-line-soft bg-bg/40">
            {field ? (
              <EvidenceField field={field} frame={frame} steps={replay.steps} t={replay.t} corpusId={run.corpusId} />
            ) : (
              <div className="h-[420px] animate-pulse" />
            )}
          </div>
          <div className="mt-3 flex flex-wrap gap-x-4 gap-y-1.5 text-[11px] text-ink-3">
            {LEGEND.map((l) => (
              <span key={l.label} className="flex items-center gap-1.5">
                <span className="size-2 rounded-full" style={{ background: l.color }} /> {l.label}
              </span>
            ))}
            <span className="flex items-center gap-1.5">
              <span className="size-2.5 rounded-full border border-look" /> worth a look
            </span>
            <span className="text-ink-4">
              Closer to the center = closer in meaning. Around the ring = position in the document.
            </span>
          </div>
          <div className="mt-4">
            <Timeline replay={replay} phase={frame.phase} stages={pipeline.stages} />
          </div>
        </div>

        <aside className="space-y-5">
          <div>
            <h3 className="mb-2 text-xs font-medium tracking-wide text-ink-3 uppercase">Passages at each step</h3>
            <StageFlow total={field?.units.length ?? 0} frame={frame} />
          </div>
          <div>
            <h3 className="mb-2 text-xs font-medium tracking-wide text-ink-3 uppercase">What the checks found</h3>
            <ul className="space-y-1.5">
              <AnimatePresence initial={false}>
                {feed.map((f) => (
                  <motion.li
                    key={f.flag_id}
                    layout
                    initial={{ opacity: 0, x: 8 }}
                    animate={{ opacity: 1, x: 0 }}
                    exit={{ opacity: 0 }}
                    className="flex gap-2 text-xs leading-5 text-ink-2"
                  >
                    {f.disposition === "needs_review" ? (
                      <CircleDot className="mt-0.5 size-3.5 shrink-0 text-look" />
                    ) : f.disposition === "handled" ? (
                      <Wrench className="mt-0.5 size-3.5 shrink-0 text-handled" />
                    ) : (
                      <Info className="mt-0.5 size-3.5 shrink-0 text-info" />
                    )}
                    {f.title}
                  </motion.li>
                ))}
              </AnimatePresence>
              {feed.length === 0 && <li className="text-xs text-ink-4">Nothing so far.</li>}
            </ul>
          </div>
        </aside>
      </div>

      <div className="mt-6">
        <h3 className="mb-2 text-xs font-medium tracking-wide text-ink-3 uppercase">Every candidate, and why it was used or left out</h3>
        <Ledger entries={pipeline.decisions} field={field} corpusId={run.corpusId} />
      </div>
    </section>
  );
}
