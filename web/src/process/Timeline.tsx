import { FastForward, Pause, Play, SkipForward } from "lucide-react";
import { STAGE_LABEL, cx, fmtMs } from "../lib";
import type { Replay } from "./replay";

/** Transport controls plus the real stage timings. The replay plays at human pace; the
 *  numbers next to each stage are what it actually took. */
export function Timeline({ replay, phase, stages }: { replay: Replay; phase: string; stages: { stage: string; ms: number }[] }) {
  const pct = replay.total ? Math.min(100, (replay.t / replay.total) * 100) : 0;
  const real = stages.reduce((a, s) => a + s.ms, 0);
  return (
    <div className="space-y-3">
      <div className="flex items-center gap-3">
        <button
          onClick={replay.playing ? replay.pause : replay.play}
          className="flex size-8 items-center justify-center rounded-lg bg-ink text-bg"
          aria-label={replay.playing ? "Pause" : "Play"}
        >
          {replay.playing ? <Pause className="size-4" /> : <Play className="size-4" />}
        </button>
        <button onClick={replay.toEnd} className="text-ink-3 hover:text-ink" aria-label="Skip to the end" title="Skip to the end">
          <SkipForward className="size-4" />
        </button>
        <button
          onClick={() => replay.setSpeed(replay.speed >= 4 ? 0.5 : replay.speed * 2)}
          className="num flex items-center gap-1 rounded-md border border-line px-2 py-1 text-xs text-ink-2"
          title="Playback speed"
        >
          <FastForward className="size-3.5" /> {replay.speed}×
        </button>
        <div className="min-w-0 flex-1 truncate text-sm text-ink-2" aria-live="polite">
          {phase}
        </div>
        <span className="num hidden text-xs text-ink-4 sm:block" title="Real time the pipeline took">
          actual: {fmtMs(real)}
        </span>
      </div>
      <input
        type="range"
        min={0}
        max={Math.max(1, replay.total)}
        value={Math.min(replay.t, replay.total)}
        onChange={(e) => {
          replay.pause();
          replay.seek(Number(e.target.value));
        }}
        className="w-full accent-[var(--mn)]"
        aria-label="Replay position"
      />
      <ol className="flex flex-wrap gap-x-5 gap-y-1 text-xs">
        {stages.map((s, i) => (
          <li key={`${s.stage}-${i}`} className="flex items-center gap-1.5 text-ink-3">
            <span className={cx("size-1.5 rounded-full", pct >= 99.9 || i < stages.length - 1 ? "bg-mn" : "bg-ink-4")} />
            {STAGE_LABEL[s.stage] ?? s.stage}
            <span className="num text-ink-4">{fmtMs(s.ms)}</span>
          </li>
        ))}
      </ol>
    </div>
  );
}
