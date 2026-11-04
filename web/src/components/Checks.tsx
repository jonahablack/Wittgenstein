import { CheckCircle2, ChevronDown, CircleDot, Eye, Info, Wrench } from "lucide-react";
import { AnimatePresence, motion } from "motion/react";
import { useState } from "react";
import type { AwarenessFlag, CheckRecord } from "../generated/live";
import { EPISTEMIC, MEASUREMENT, cx, groupFlags } from "../lib";
import { type PipelineRun, type RunState, useApp } from "../store";

const MAX_LOOK_SHOWN = 3;

function FlagCard({ flag, run, tone }: { flag: AwarenessFlag; run: RunState; tone: "look" | "handled" | "info" }) {
  const openSource = useApp((s) => s.openSource);
  const [more, setMore] = useState(false);
  const ref = flag.refs?.[0];
  const accent = tone === "look" ? "border-l-look" : tone === "handled" ? "border-l-handled" : "border-l-info";
  return (
    <motion.li
      layout
      initial={{ opacity: 0, y: 4 }}
      animate={{ opacity: 1, y: 0 }}
      className={cx("rounded-xl border border-line border-l-2 bg-surface-2/60 px-4 py-3", accent)}
    >
      <div className="flex items-start gap-3">
        <div className="min-w-0 flex-1">
          <h4 className="text-sm font-medium text-ink">{flag.title}</h4>
          <p className="mt-1 text-sm leading-6 text-ink-2">{flag.observation}</p>
          {flag.action_taken && (
            <p className="mt-1.5 text-sm leading-6 text-handled">
              <span className="font-medium">What we did:</span> {flag.action_taken}
            </p>
          )}
          {more && (
            <div className="mt-2 space-y-1.5 text-xs leading-5 text-ink-3">
              <p>
                <span className="text-ink-2">Why it matters:</span> {flag.why_it_matters}
              </p>
              {flag.what_to_check && (
                <p>
                  <span className="text-ink-2">What to check:</span> {flag.what_to_check}
                </p>
              )}
              <p className="flex flex-wrap gap-1.5 pt-1">
                <span className="rounded-md border border-line px-1.5 py-0.5">{MEASUREMENT[flag.measurement] ?? flag.measurement}</span>
                <span className="rounded-md border border-line px-1.5 py-0.5">
                  {flag.origin === "text" ? "About the text" : flag.origin === "pipeline" ? "About the pipeline" : "Text and pipeline"}
                </span>
                {flag.registry && (
                  <span className="rounded-md border border-line px-1.5 py-0.5" title={EPISTEMIC[flag.registry.epistemic_status].hint}>
                    {EPISTEMIC[flag.registry.epistemic_status].label}: {flag.registry.canonical_name}
                  </span>
                )}
              </p>
            </div>
          )}
          <div className="mt-2 flex gap-3 text-xs">
            {ref && (
              <button
                onClick={() =>
                  openSource({
                    corpusId: run.corpusId,
                    documentId: ref.document_id,
                    start: ref.char_start,
                    end: ref.char_end,
                    label: flag.title,
                  })
                }
                className="flex items-center gap-1 text-mn hover:underline"
              >
                <Eye className="size-3.5" /> Show me
              </button>
            )}
            <button onClick={() => setMore((m) => !m)} className="text-ink-3 hover:text-ink">
              {more ? "Less" : "Why this matters"}
            </button>
          </div>
        </div>
      </div>
    </motion.li>
  );
}

function Group({
  icon,
  title,
  count,
  tone,
  children,
  defaultOpen,
}: {
  icon: React.ReactNode;
  title: string;
  count: number;
  tone: string;
  children: React.ReactNode;
  defaultOpen: boolean;
}) {
  const [open, setOpen] = useState(defaultOpen);
  if (count === 0) return null;
  return (
    <section>
      <button onClick={() => setOpen((o) => !o)} className="flex w-full items-center gap-2 py-2 text-left text-sm" aria-expanded={open}>
        <span className={tone}>{icon}</span>
        <span className="font-medium text-ink">{title}</span>
        <span className="num text-ink-3">{count}</span>
        <ChevronDown className={cx("ml-auto size-4 text-ink-3 transition", open && "rotate-180")} />
      </button>
      <AnimatePresence initial={false}>
        {open && (
          <motion.div initial={{ height: 0, opacity: 0 }} animate={{ height: "auto", opacity: 1 }} exit={{ height: 0, opacity: 0 }} className="overflow-hidden">
            {children}
          </motion.div>
        )}
      </AnimatePresence>
    </section>
  );
}

function PassedList({ checks }: { checks: CheckRecord[] }) {
  return (
    <ul className="grid gap-x-6 gap-y-1.5 pb-2 sm:grid-cols-2">
      {checks.map((c) => (
        <li key={c.check_id} className="flex gap-2 text-sm" title={c.detail}>
          <CheckCircle2 className="mt-0.5 size-4 shrink-0 text-handled/80" />
          <span>
            <span className="text-ink-2">{c.label}</span>
            <span className="block text-xs text-ink-4">{c.detail}</span>
          </span>
        </li>
      ))}
    </ul>
  );
}

export function ChecksPanel({ run, pipeline }: { run: RunState; pipeline: PipelineRun }) {
  const [showAllLook, setShowAllLook] = useState(false);
  if (!pipeline.done) return null;
  const flags = pipeline.flagOrder.map((id) => pipeline.flags[id]);
  const { look, handled, info } = groupFlags(flags);
  const passed = pipeline.checks.filter((c) => c.outcome === "passed");
  const lookShown = showAllLook ? look : look.slice(0, MAX_LOOK_SHOWN);

  return (
    <div className="rounded-2xl border border-line bg-surface p-4 shadow-glow sm:p-5">
      {look.length === 0 && (
        <p className="flex items-center gap-2 pb-2 text-sm text-ink-2">
          <CheckCircle2 className="size-4 text-handled" />
          Nothing needs your attention. Here is what was checked and what was taken care of.
        </p>
      )}
      <div className="divide-y divide-line-soft">
        <Group icon={<CircleDot className="size-4" />} title="Worth a look" count={look.length} tone="text-look" defaultOpen>
          <ul className="space-y-2 pb-3">
            {lookShown.map((f) => (
              <FlagCard key={f.flag_id} flag={f} run={run} tone="look" />
            ))}
          </ul>
          {look.length > MAX_LOOK_SHOWN && (
            <button onClick={() => setShowAllLook((s) => !s)} className="mb-3 text-xs text-ink-3 hover:text-ink">
              {showAllLook ? "Show fewer" : `Show ${look.length - MAX_LOOK_SHOWN} more`}
            </button>
          )}
        </Group>
        <Group icon={<Wrench className="size-4" />} title="Handled for you" count={handled.length} tone="text-handled" defaultOpen={look.length === 0}>
          <ul className="space-y-2 pb-3">
            {handled.map((f) => (
              <FlagCard key={f.flag_id} flag={f} run={run} tone="handled" />
            ))}
          </ul>
        </Group>
        <Group icon={<Info className="size-4" />} title="Good to know" count={info.length} tone="text-info" defaultOpen={false}>
          <ul className="space-y-2 pb-3">
            {info.map((f) => (
              <FlagCard key={f.flag_id} flag={f} run={run} tone="info" />
            ))}
          </ul>
        </Group>
        <Group icon={<CheckCircle2 className="size-4" />} title="Checks passed" count={passed.length} tone="text-handled" defaultOpen={false}>
          <PassedList checks={passed} />
        </Group>
      </div>
    </div>
  );
}
