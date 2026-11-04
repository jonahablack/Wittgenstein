import { Quote } from "lucide-react";
import { motion } from "motion/react";
import { Fragment, useState } from "react";
import type { AwarenessFlag, VerifiedSentence } from "../generated/live";
import { cx } from "../lib";
import { type PipelineRun, type RunState, useApp } from "../store";
import { unitOf, useField } from "./useField";

const CITE = /\[(\d+(?:\s*,\s*\d+)*)\]/g;

function Cite({ n, run, pipeline }: { n: number; run: RunState; pipeline: PipelineRun }) {
  const field = useField(run, pipeline);
  const openSource = useApp((s) => s.openSource);
  const [hover, setHover] = useState(false);
  const unit = unitOf(field, pipeline.packed[n - 1]);
  return (
    <span className="relative inline-block align-baseline">
      <button
        onMouseEnter={() => setHover(true)}
        onMouseLeave={() => setHover(false)}
        onFocus={() => setHover(true)}
        onBlur={() => setHover(false)}
        onClick={() =>
          unit &&
          openSource({
            corpusId: run.corpusId,
            documentId: unit.document_id,
            start: unit.char_start,
            end: unit.char_end,
            label: `Passage [${n}] · ${unit.location}`,
          })
        }
        className="num mx-0.5 inline-flex h-[18px] min-w-[18px] items-center justify-center rounded-[5px] border border-mn/40 bg-mn/10 px-1 text-[11px] leading-none text-mn hover:bg-mn/20"
        aria-label={`Source ${n}`}
      >
        {n}
      </button>
      {hover && unit && (
        <span className="absolute bottom-full left-1/2 z-20 mb-2 block w-80 -translate-x-1/2 rounded-xl border border-line bg-elev p-3 text-left text-xs leading-5 shadow-glow">
          <span className="mb-1 block truncate text-ink-3">{unit.location}</span>
          <span className="block text-ink-2">“{unit.preview}{unit.preview.length >= 140 ? "…" : ""}”</span>
          <span className="mt-1.5 block text-ink-4">Click to open it in the document</span>
        </span>
      )}
    </span>
  );
}

function withCites(text: string, run: RunState, pipeline: PipelineRun) {
  const out: React.ReactNode[] = [];
  let last = 0;
  for (const m of text.matchAll(CITE)) {
    out.push(text.slice(last, m.index));
    for (const n of m[1].split(",").map((x) => Number(x.trim())))
      out.push(<Cite key={`${m.index}-${n}`} n={n} run={run} pipeline={pipeline} />);
    last = m.index! + m[0].length;
  }
  out.push(text.slice(last));
  return out;
}

function Sentence({
  s,
  flags,
  run,
  pipeline,
}: {
  s: VerifiedSentence;
  flags: AwarenessFlag[];
  run: RunState;
  pipeline: PipelineRun;
}) {
  const open = flags.filter((f) => f.disposition === "needs_review");
  const [hover, setHover] = useState(false);
  return (
    <span className="relative" onMouseEnter={() => setHover(true)} onMouseLeave={() => setHover(false)}>
      <span
        className={cx(
          open.length > 0 && "decoration-look/70 underline decoration-dotted decoration-[1.5px] underline-offset-[5px]",
        )}
      >
        {s.text}
      </span>
      {s.cited.map((n) => (
        <Cite key={n} n={n} run={run} pipeline={pipeline} />
      ))}{" "}
      {hover && open.length > 0 && (
        <span className="absolute top-full left-0 z-20 mt-1 block w-80 rounded-xl border border-look/40 bg-elev p-3 text-xs leading-5 shadow-glow">
          {open.map((f) => (
            <span key={f.flag_id} className="block text-ink-2">
              <span className="text-look">●</span> {f.title}
            </span>
          ))}
        </span>
      )}
    </span>
  );
}

export function AnswerCard({ run, pipeline, compact = false }: { run: RunState; pipeline: PipelineRun; compact?: boolean }) {
  const verified = pipeline.done && pipeline.sentences.length > 0;
  const flags = Object.values(pipeline.flags);
  const byId = Object.fromEntries(flags.map((f) => [f.flag_id, f]));
  const waiting = !pipeline.answer && run.status === "running";
  const quoting = pipeline.provider ? !pipeline.provider.uses_llm : run.provider === "extractive";

  return (
    <motion.article
      layout
      className={cx("rounded-2xl border border-line bg-surface shadow-glow", compact ? "p-4" : "p-6 sm:p-7")}
    >
      <div className="mb-3 flex items-center gap-2 text-xs text-ink-3">
        <Quote className="size-3.5" />
        {quoting ? "Quoted from the document — no language model" : `Written by ${pipeline.provider?.label ?? run.provider}`}
        {pipeline.provider?.model_identifier && <span className="num text-ink-4">· {pipeline.provider.model_identifier}</span>}
      </div>
      {waiting ? (
        <div className="space-y-2.5" aria-busy>
          {[92, 78, 85].map((w, i) => (
            <div key={i} className="h-4 animate-pulse rounded bg-surface-2" style={{ width: `${w}%` }} />
          ))}
        </div>
      ) : (
        <p className={cx("text-pretty text-ink", compact ? "text-[14px] leading-6" : "text-[16.5px] leading-[1.8]")}>
          {verified
            ? pipeline.sentences.map((s) => (
                <Fragment key={s.sentence_id}>
                  <Sentence s={s} flags={(s.flag_ids ?? []).map((id) => byId[id]).filter(Boolean)} run={run} pipeline={pipeline} />
                </Fragment>
              ))
            : withCites(pipeline.answer, run, pipeline)}
          {!pipeline.done && pipeline.answer && <span className="ml-0.5 inline-block h-4 w-[2px] animate-pulse bg-mn align-middle" />}
        </p>
      )}
    </motion.article>
  );
}
