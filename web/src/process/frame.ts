import type { AwarenessFlag, CandidateFate, LedgerEntry } from "../generated/live";
import type { Candidate } from "../store";
import type { Step } from "./replay";

export interface UnitVisual {
  channels: string[];
  /** Order in which the candidate lit up (fused rank), for staggering. */
  rank: number;
  fate?: CandidateFate;
  entry?: LedgerEntry;
  packed: boolean;
  cited: boolean;
  flag?: "look" | "handled" | "info";
  /** Seconds-scale "freshness": 1 when something just happened to this unit, decaying. */
  lastChangeStep: number;
}

export interface Frame {
  units: Map<string, UnitVisual>;
  phase: string;
  stage?: string;
  analyzed: boolean;
  candidatesShown: number;
  candidatesTotal: number;
  decided: number;
  packed: number;
  flags: AwarenessFlag[];
  answerChars: number;
  citedUnits: string[];
  pulse: number; // step index of the latest "pulse from the center" moment
}

const PHASES: Record<string, string> = {
  "query.analyzed": "Reading the question",
  field: "Mapping the document",
  candidates: "Searching by keyword, by meaning, and by each part of the question",
  check: "Checking the search",
  flag: "Checking the search",
  decision: "Choosing evidence",
  "context.packed": "Assembling the context",
  "answer.delta": "Writing the answer",
  "answer.sentence": "Verifying each sentence against its source",
  "pipeline.completed": "Done",
};

/** Everything the evidence field shows at step `index` (with `progress` 0..1 through it). */
export function frameAt(steps: Step[], index: number, progress: number): Frame {
  const units = new Map<string, UnitVisual>();
  const frame: Frame = {
    units,
    phase: "Starting",
    analyzed: false,
    candidatesShown: 0,
    candidatesTotal: 0,
    decided: 0,
    packed: 0,
    flags: [],
    answerChars: 0,
    citedUnits: [],
    pulse: -1,
  };
  const flagById = new Map<string, AwarenessFlag>();
  const unit = (id: string, i: number) => {
    let u = units.get(id);
    if (!u) {
      u = { channels: [], rank: 9999, packed: false, cited: false, lastChangeStep: i };
      units.set(id, u);
    }
    return u;
  };

  for (let i = 0; i <= index && i < steps.length; i++) {
    const e = steps[i].event;
    const d = e.data as Record<string, any>;
    const p = i === index ? progress : 1;
    if (PHASES[e.type]) frame.phase = PHASES[e.type];
    switch (e.type) {
      case "query.analyzed":
        frame.analyzed = true;
        frame.pulse = i;
        break;
      case "stage":
        frame.stage = d.stage;
        break;
      case "candidates": {
        const items = d.items as Candidate[];
        frame.candidatesTotal = items.length;
        const shown = Math.ceil(items.length * p);
        frame.candidatesShown = shown;
        if (i === index || frame.pulse < i) frame.pulse = i;
        items.slice(0, shown).forEach((c) => {
          const u = unit(c.unit_id, i);
          u.channels = c.channels;
          u.rank = c.fused_rank;
          u.lastChangeStep = i;
        });
        break;
      }
      case "flag":
      case "flag.updated": {
        const f = d.flag as AwarenessFlag;
        flagById.set(f.flag_id, f);
        for (const r of f.refs ?? []) {
          const u = unit(r.unit_id, i);
          u.flag = f.disposition === "needs_review" ? "look" : f.disposition === "handled" ? "handled" : "info";
          u.lastChangeStep = i;
        }
        break;
      }
      case "decision": {
        const entry = d.entry as LedgerEntry;
        const u = unit(entry.unit_id, i);
        if (u.channels.length === 0) u.channels = entry.channels;
        u.fate = entry.fate;
        u.entry = entry;
        u.lastChangeStep = i;
        frame.decided++;
        break;
      }
      case "context.packed":
        for (const id of d.packed as string[]) {
          const u = unit(id, i);
          u.packed = true;
          u.lastChangeStep = i;
        }
        frame.packed = (d.packed as string[]).length;
        frame.pulse = i;
        break;
      case "answer.delta":
        frame.answerChars += String(d.text).length;
        break;
      case "answer.sentence": {
        const ids = (d.sentence.cited_unit_ids as (string | null)[]).filter(Boolean) as string[];
        for (const id of ids) {
          const u = unit(id, i);
          u.cited = true;
          u.lastChangeStep = i;
          if (!frame.citedUnits.includes(id)) frame.citedUnits.push(id);
        }
        break;
      }
    }
  }
  frame.flags = [...flagById.values()];
  return frame;
}
