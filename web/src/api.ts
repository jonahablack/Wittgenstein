import type { LiveEvent } from "./generated/live";

export interface PipelinePreset {
  pipeline_id: string;
  label: string;
  description: string;
  chunker: string;
  channels: string[];
  embedder: string | null;
  k_policy: string;
  k: number;
  token_budget: number;
}

export interface LiveConfig {
  pipelines: PipelinePreset[];
  default_pipeline: string;
  providers: Record<string, boolean>;
  embedders: string[];
  default_embedder: string;
  /** Meaning-level checks can be turned off on a small server; `note` says so to users. */
  meaning_checks?: { enabled: boolean; note: string | null };
}

export interface CorpusSummary {
  corpus_id: string;
  title: string;
  source: "fixture" | "sample" | "upload";
  status: "loading" | "ready" | "error";
  error: string | null;
  documents: { document_id: string; title: string; chars: number }[];
  units: number | null;
  characters: number;
  warm_ms: number | null;
}

async function json<T>(res: Response): Promise<T> {
  if (!res.ok) {
    let detail = res.statusText;
    try {
      detail = (await res.json()).detail ?? detail;
    } catch {
      /* not JSON */
    }
    throw new Error(typeof detail === "string" ? detail : JSON.stringify(detail));
  }
  return res.json() as Promise<T>;
}

export const getConfig = () => fetch("/live/config").then(json<LiveConfig>);
export const getCorpora = () => fetch("/live/corpora").then(json<CorpusSummary[]>);

export function uploadCorpus(title: string, files: File[]): Promise<CorpusSummary> {
  const body = new FormData();
  body.set("title", title);
  for (const f of files) body.append("files", f);
  return fetch("/live/corpora", { method: "POST", body }).then(json<CorpusSummary>);
}

const docCache = new Map<string, Promise<{ title: string; text: string }>>();
export function getDocument(corpusId: string, documentId: string) {
  const key = `${corpusId}/${documentId}`;
  if (!docCache.has(key)) {
    docCache.set(
      key,
      fetch(`/live/corpora/${encodeURIComponent(corpusId)}/documents/${encodeURIComponent(documentId)}`).then(
        json<{ title: string; text: string }>,
      ),
    );
  }
  return docCache.get(key)!;
}

export interface RunRequest {
  corpus_id: string;
  query: string;
  pipelines: string[];
  provider: string;
  /** Also test whether the model answers from the passages (LLM providers only). */
  counterfactual?: boolean;
}

/** POSTs a run and parses the Server-Sent Events stream as it arrives. EventSource
 *  can't POST, so the stream is read from fetch's body directly. */
export async function streamRun(req: RunRequest, onEvent: (e: LiveEvent) => void, signal: AbortSignal) {
  const res = await fetch("/live/runs", {
    method: "POST",
    headers: { "content-type": "application/json", accept: "text/event-stream" },
    body: JSON.stringify(req),
    signal,
  });
  if (!res.ok || !res.body) await json(res);
  const reader = res.body!.pipeThrough(new TextDecoderStream()).getReader();
  let buffer = "";
  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += value.replace(/\r\n/g, "\n");
    let cut: number;
    while ((cut = buffer.indexOf("\n\n")) !== -1) {
      const block = buffer.slice(0, cut);
      buffer = buffer.slice(cut + 2);
      const data = block
        .split("\n")
        .filter((l) => l.startsWith("data:"))
        .map((l) => l.slice(5).trimStart())
        .join("\n");
      if (data) onEvent(JSON.parse(data) as LiveEvent);
    }
  }
}
