import { Activity, CheckCircle2, CircleDot, Search, Wrench } from "lucide-react";
import { cx, fmtInt, fmtMs } from "../lib";
import { type PipelineRun, type RunState, useApp } from "../store";

/** What is happening now, keyed by the last stage that *completed*. */
const NEXT_STEP: Record<string, string> = {
  retrieve: "Checking how well the search understood the question…",
  probe: "Choosing the evidence…",
  select: "Assembling the context…",
  pack: "Writing the answer…",
  generate: "Verifying the answer against its sources…",
};

/** The one-line account of the process under every answer (plan §8.1): the user who
 *  trusts the answer reads this and moves on. */
export function Receipt({ run, pipeline, compact = false }: { run: RunState; pipeline: PipelineRun; compact?: boolean }) {
  const showProcess = useApp((s) => s.showProcess);
  const setShowProcess = useApp((s) => s.setShowProcess);
  const r = pipeline.receipt;
  const channels = run.analysis ? "by keyword and by meaning" : "";
  if (!r) {
    const stage = pipeline.stages.at(-1)?.stage;
    return (
      <div className="flex items-center gap-2 px-1 text-sm text-ink-3">
        <Activity className="size-4 animate-pulse text-mn" />
        {(stage && NEXT_STEP[stage]) ?? "Searching the document…"}
      </div>
    );
  }
  return (
    <div className={cx("flex flex-wrap items-center gap-x-4 gap-y-2 px-1 text-sm text-ink-3", compact && "text-xs")}>
      <span className="flex items-center gap-1.5">
        <Search className="size-3.5" /> Searched <span className="num text-ink-2">{fmtInt(r.passages_searched)}</span>{" "}
        passages {!compact && channels}
      </span>
      <span>
        used <span className="num text-ink-2">{r.passages_used}</span>
      </span>
      <span className={cx("flex items-center gap-1.5", r.worth_a_look > 0 ? "text-look" : "")}>
        <CircleDot className="size-3.5" />
        <span className="num">{r.worth_a_look}</span> worth a look
      </span>
      <span className="flex items-center gap-1.5 text-handled">
        <Wrench className="size-3.5" />
        <span className="num">{r.handled}</span> handled
      </span>
      <span className="flex items-center gap-1.5">
        <CheckCircle2 className="size-3.5" />
        <span className="num text-ink-2">
          {r.checks_passed}/{r.checks_run}
        </span>{" "}
        checks passed
      </span>
      <span className="num text-ink-4">{fmtMs(r.total_ms)}</span>
      {!compact && (
        <button
          onClick={() => setShowProcess(!showProcess)}
          className={cx(
            "ml-auto flex h-8 items-center gap-1.5 rounded-lg border px-3 text-xs font-medium transition",
            showProcess ? "border-mn/50 bg-mn/10 text-ink" : "border-line bg-surface text-ink-2 hover:text-ink",
          )}
          aria-pressed={showProcess}
        >
          <Activity className="size-3.5" /> {showProcess ? "Hide the process" : "Show the process"}
        </button>
      )}
    </div>
  );
}
