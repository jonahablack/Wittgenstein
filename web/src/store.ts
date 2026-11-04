import { create } from "zustand";
import { type CorpusSummary, type LiveConfig, getConfig, getCorpora, streamRun } from "./api";
import type {
  AwarenessFlag,
  CheckRecord,
  LedgerEntry,
  LiveEvent,
  ProviderInfo,
  QueryAnalysis,
  Receipt,
  UnitPoint,
  VerifiedSentence,
} from "./generated/live";

export interface Candidate {
  unit_id: string;
  channels: string[];
  lexical_rank: number | null;
  dense_rank: number | null;
  fused_rank: number;
  relevance_z: number;
  facet_hits: Record<string, number>;
}

export interface FieldData {
  chunker: string;
  units: UnitPoint[];
  index: Map<string, number>;
  dense_z: number[] | null;
  lexical_z: number[];
}

export interface ModelProfile {
  embedder_id: string;
  model_identifier: string;
  family: string;
  declared_window: number | null;
  measured_window: number | null;
  window_status: string;
  negation_shift_vs_word: number | null;
  dilution_at_400_words: number | null;
  typical_unrelated_similarity: number | null;
  insufficient_baselines: string[];
}

export interface StageInfo {
  stage: string;
  ms: number;
  [k: string]: unknown;
}

export interface PipelineRun {
  id: string;
  label: string;
  description: string;
  stages: StageInfo[];
  candidates: Candidate[];
  flags: Record<string, AwarenessFlag>;
  flagOrder: string[];
  checks: CheckRecord[];
  decisions: LedgerEntry[];
  packed: string[];
  omitted: string[];
  tokens: number;
  budget: number;
  answer: string;
  sentences: VerifiedSentence[];
  receipt?: Receipt;
  provider?: ProviderInfo;
  done: boolean;
}

export interface RunState {
  runId?: string;
  query: string;
  corpusId: string;
  provider: string;
  status: "running" | "done" | "error";
  error?: string;
  notices: string[];
  analysis?: QueryAnalysis;
  profile?: ModelProfile;
  fields: Record<string, FieldData>;
  pipelines: Record<string, PipelineRun>;
  order: string[];
  events: LiveEvent[];
}

const emptyPipeline = (id: string, label = id, description = ""): PipelineRun => ({
  id,
  label,
  description,
  stages: [],
  candidates: [],
  flags: {},
  flagOrder: [],
  checks: [],
  decisions: [],
  packed: [],
  omitted: [],
  tokens: 0,
  budget: 0,
  answer: "",
  sentences: [],
  done: false,
});

/** Folds one event into the run. Pure: the same event sequence always yields the same
 *  state, which is what makes stored runs replayable. */
export function reduce(run: RunState, e: LiveEvent): RunState {
  const d = e.data as Record<string, any>;
  const pid = e.pipeline_id ?? undefined;
  const next: RunState = { ...run, events: [...run.events, e] };
  const touch = (fn: (p: PipelineRun) => PipelineRun) => {
    if (!pid) return;
    const cur = next.pipelines[pid] ?? emptyPipeline(pid);
    next.pipelines = { ...next.pipelines, [pid]: fn(cur) };
  };
  switch (e.type) {
    case "run.started":
      next.runId = d.run_id;
      next.order = d.pipelines.map((p: any) => p.pipeline_id);
      next.pipelines = Object.fromEntries(
        d.pipelines.map((p: any) => [p.pipeline_id, emptyPipeline(p.pipeline_id, p.label, p.description)]),
      );
      break;
    case "query.analyzed":
      next.analysis = d.analysis;
      break;
    case "model.profile":
      next.profile = next.profile ?? d.profile;
      break;
    case "field": {
      const units = d.units as UnitPoint[];
      next.fields = {
        ...next.fields,
        [d.chunker]: {
          chunker: d.chunker,
          units,
          index: new Map(units.map((u, i) => [u.unit_id, i])),
          dense_z: d.dense_z,
          lexical_z: d.lexical_z,
        },
      };
      break;
    }
    case "stage":
      touch((p) => ({ ...p, stages: [...p.stages, d as StageInfo] }));
      break;
    case "candidates":
      touch((p) => ({ ...p, candidates: d.items }));
      break;
    case "flag":
    case "flag.updated":
      touch((p) => {
        const f = d.flag as AwarenessFlag;
        const order = p.flags[f.flag_id] ? p.flagOrder : [...p.flagOrder, f.flag_id];
        return { ...p, flags: { ...p.flags, [f.flag_id]: f }, flagOrder: order };
      });
      break;
    case "check":
      touch((p) => ({ ...p, checks: [...p.checks, d.check] }));
      break;
    case "decision":
      touch((p) => ({ ...p, decisions: [...p.decisions, d.entry] }));
      break;
    case "context.packed":
      touch((p) => ({ ...p, packed: d.packed, omitted: d.omitted, tokens: d.tokens, budget: d.budget }));
      break;
    case "answer.delta":
      touch((p) => ({ ...p, answer: p.answer + d.text }));
      break;
    case "answer.sentence":
      touch((p) => ({ ...p, sentences: [...p.sentences, d.sentence] }));
      break;
    case "pipeline.completed":
      touch((p) => ({ ...p, receipt: d.receipt, provider: d.provider, done: true }));
      break;
    case "run.completed":
      next.status = "done";
      break;
    case "error":
      if (pid) next.notices = [...next.notices, String(d.message)];
      else {
        next.status = "error";
        next.error = String(d.message);
      }
      break;
  }
  return next;
}

export type Theme = "system" | "light" | "dark";

interface AppState {
  config?: LiveConfig;
  corpora: CorpusSummary[];
  corpusId?: string;
  provider: string;
  compare: boolean;
  comparePipelines: string[];
  showProcess: boolean;
  run?: RunState;
  activePipeline?: string;
  source?: { corpusId: string; documentId: string; start: number; end: number; label?: string };
  loadError?: string;
  abort?: AbortController;

  init: () => Promise<void>;
  refreshCorpora: () => Promise<void>;
  setCorpus: (id: string) => void;
  setProvider: (p: string) => void;
  setCompare: (on: boolean) => void;
  toggleComparePipeline: (id: string) => void;
  setShowProcess: (on: boolean) => void;
  setActivePipeline: (id: string) => void;
  openSource: (s: AppState["source"]) => void;
  closeSource: () => void;
  ask: (query: string) => Promise<void>;
}

const pref = <T,>(key: string, fallback: T): T => {
  try {
    const v = localStorage.getItem(key);
    return v == null ? fallback : (JSON.parse(v) as T);
  } catch {
    return fallback;
  }
};
const savePref = (key: string, value: unknown) => {
  try {
    localStorage.setItem(key, JSON.stringify(value));
  } catch {
    /* storage unavailable: preference just isn't remembered */
  }
};

export const useApp = create<AppState>((set, get) => ({
  corpora: [],
  provider: pref("wg.provider", "extractive"),
  compare: pref("wg.compare", false),
  comparePipelines: pref("wg.comparePipelines", ["aware", "semantic-top5"]),
  showProcess: pref("wg.showProcess", false),

  init: async () => {
    try {
      const [config, corpora] = await Promise.all([getConfig(), getCorpora()]);
      const provider = config.providers[get().provider] ? get().provider : "extractive";
      set({ config, corpora, provider, corpusId: get().corpusId ?? corpora[0]?.corpus_id });
      if (corpora.some((c) => c.status === "loading")) setTimeout(() => get().refreshCorpora(), 1200);
    } catch (e) {
      set({ loadError: e instanceof Error ? e.message : String(e) });
    }
  },
  refreshCorpora: async () => {
    const corpora = await getCorpora();
    set({ corpora });
    if (corpora.some((c) => c.status === "loading")) setTimeout(() => get().refreshCorpora(), 1200);
  },
  setCorpus: (corpusId) => set({ corpusId }),
  setProvider: (provider) => {
    savePref("wg.provider", provider);
    set({ provider });
  },
  setCompare: (compare) => {
    savePref("wg.compare", compare);
    set({ compare });
  },
  toggleComparePipeline: (id) => {
    const cur = get().comparePipelines;
    const next = cur.includes(id) ? cur.filter((x) => x !== id) : [...cur, id];
    if (next.length === 0) return;
    savePref("wg.comparePipelines", next);
    set({ comparePipelines: next });
  },
  setShowProcess: (showProcess) => {
    savePref("wg.showProcess", showProcess);
    set({ showProcess });
  },
  setActivePipeline: (activePipeline) => set({ activePipeline }),
  openSource: (source) => set({ source }),
  closeSource: () => set({ source: undefined }),

  ask: async (query) => {
    const { corpusId, config, provider, compare, comparePipelines } = get();
    if (!corpusId || !config) return;
    get().abort?.abort();
    const abort = new AbortController();
    const def = config.default_pipeline;
    const pipelines = compare ? [def, ...comparePipelines.filter((p) => p !== def)] : [def];
    let run: RunState = {
      query,
      corpusId,
      provider,
      status: "running",
      notices: [],
      fields: {},
      pipelines: {},
      order: pipelines,
      events: [],
    };
    set({ run, abort, activePipeline: def, source: undefined });
    // Batch state updates per animation frame: a run emits hundreds of events in a
    // few hundred milliseconds, and re-rendering per event would be wasted work.
    let pending: LiveEvent[] = [];
    let raf = 0;
    const flush = () => {
      raf = 0;
      for (const e of pending) run = reduce(run, e);
      pending = [];
      set({ run });
    };
    try {
      await streamRun({ corpus_id: corpusId, query, pipelines, provider }, (e) => {
        pending.push(e);
        if (!raf) raf = requestAnimationFrame(flush);
      }, abort.signal);
      if (raf) cancelAnimationFrame(raf);
      flush();
      if (run.status === "running") set({ run: { ...run, status: "done" } });
    } catch (e) {
      if (abort.signal.aborted) return;
      if (raf) cancelAnimationFrame(raf);
      flush();
      set({ run: { ...run, status: "error", error: e instanceof Error ? e.message : String(e) } });
    }
  },
}));
