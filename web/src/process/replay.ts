import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { LiveEvent } from "../generated/live";

/** One scheduled step of the replay: an event, when it starts, and how long it plays. */
export interface Step {
  event: LiveEvent;
  start: number;
  duration: number;
}

/** How long each kind of event takes to play at 1x, in ms. The pipeline itself runs in a
 *  few hundred milliseconds; the replay spreads the *same events, in the same order*
 *  over a few seconds so a person can follow them. Nothing is invented: every frame of
 *  the animation is derived from an event that actually happened. */
function durationOf(e: LiveEvent, counts: Record<string, number>): number {
  const n = (t: string) => Math.max(1, counts[t] ?? 1);
  switch (e.type) {
    case "query.analyzed":
      return 650;
    case "field":
      return 350;
    case "candidates":
      return 1500;
    case "stage":
      return 160;
    case "flag":
    case "flag.updated":
      return 110;
    case "check":
      return Math.min(30, 600 / n("check"));
    case "decision":
      return Math.max(6, Math.min(110, 1700 / n("decision")));
    case "context.packed":
      return 600;
    case "answer.delta":
      return Math.max(15, Math.min(70, 1200 / n("answer.delta")));
    case "answer.sentence":
      return 220;
    case "pipeline.completed":
      return 400;
    default:
      return 0;
  }
}

export function schedule(events: LiveEvent[], pipelineId: string): Step[] {
  const relevant = events.filter((e) => e.pipeline_id == null || e.pipeline_id === pipelineId);
  const counts: Record<string, number> = {};
  for (const e of relevant) counts[e.type] = (counts[e.type] ?? 0) + 1;
  let t = 0;
  return relevant.map((event) => {
    const duration = durationOf(event, counts);
    const step = { event, start: t, duration };
    t += duration;
    return step;
  });
}

export interface Replay {
  steps: Step[];
  t: number;
  total: number;
  playing: boolean;
  speed: number;
  /** Index of the last step that has started at time t (-1 before the first). */
  index: number;
  /** 0..1 progress through the step at `index`. */
  progress: number;
  play: () => void;
  pause: () => void;
  seek: (t: number) => void;
  setSpeed: (s: number) => void;
  toEnd: () => void;
}

const reducedMotion = () =>
  typeof window !== "undefined" && window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;

/** A playhead over the schedule. While a run is still streaming, the schedule keeps
 *  growing and playback simply continues into the new steps. */
export function useReplay(events: LiveEvent[], pipelineId: string, autoplay = true): Replay {
  const steps = useMemo(() => schedule(events, pipelineId), [events, pipelineId]);
  const total = steps.length ? steps[steps.length - 1].start + steps[steps.length - 1].duration : 0;
  const [t, setT] = useState(() => (reducedMotion() ? Number.POSITIVE_INFINITY : 0));
  const [playing, setPlaying] = useState(autoplay && !reducedMotion());
  const [speed, setSpeed] = useState(1);
  const totalRef = useRef(total);
  totalRef.current = total;

  useEffect(() => {
    setT(reducedMotion() ? Number.POSITIVE_INFINITY : 0);
    setPlaying(autoplay && !reducedMotion());
  }, [pipelineId, autoplay]);

  useEffect(() => {
    if (!playing) return;
    let raf = 0;
    let last = performance.now();
    const tick = (now: number) => {
      const dt = (now - last) * speed;
      last = now;
      setT((cur) => Math.min(cur + dt, totalRef.current));
      raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [playing, speed]);

  const clamped = Math.min(t, total);
  let index = -1;
  for (let i = 0; i < steps.length; i++) {
    if (steps[i].start <= clamped) index = i;
    else break;
  }
  const step = steps[index];
  const progress = step ? (step.duration ? Math.min(1, (clamped - step.start) / step.duration) : 1) : 0;

  return {
    steps,
    t: clamped,
    total,
    playing: playing && clamped < total,
    speed,
    index,
    progress,
    play: useCallback(() => {
      setT((cur) => (cur >= totalRef.current ? 0 : cur));
      setPlaying(true);
    }, []),
    pause: useCallback(() => setPlaying(false), []),
    seek: useCallback((x: number) => setT(Math.max(0, Math.min(x, totalRef.current))), []),
    setSpeed,
    toEnd: useCallback(() => {
      setT(Number.POSITIVE_INFINITY);
      setPlaying(false);
    }, []),
  };
}
