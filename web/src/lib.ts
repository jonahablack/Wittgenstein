import type { AwarenessFlag, CandidateFate, EpistemicStatus } from "./generated/live";

/** Plain-language rendering of the registry's epistemic statuses. Never stronger than
 *  the status itself: a research hypothesis is never shown as an established finding. */
export const EPISTEMIC: Record<EpistemicStatus, { label: string; hint: string }> = {
  externally_established: {
    label: "Established finding",
    hint: "Backed by peer-reviewed RAG studies meeting the registry's evidence bar.",
  },
  manifest_conditioned_transfer: {
    label: "Documented in related settings",
    hint: "Shown in studies whose setup resembles this pipeline; applies only under similar conditions.",
  },
  trace_integrity_condition: {
    label: "Observed pipeline fact",
    hint: "A directly observable fact about this run. It says what happened, not that it caused an error.",
  },
  research_hypothesis: {
    label: "Known risk pattern (hypothesis)",
    hint: "A plausible review cue that isn't yet backed by RAG-specific evidence.",
  },
  locally_validated: { label: "Validated for this deployment", hint: "Locally tested; scoped to this deployment." },
  unsupported_or_retired: { label: "Retired", hint: "Kept for the record; no longer considered supported." },
};

export const MEASUREMENT: Record<string, string> = {
  measured: "Measured on this run",
  inferred_from_rankings: "Inferred from rankings",
  pattern_match: "Matched in the text",
  model_judgment: "Judged by a language-inference model (can be wrong)",
};

export const FATE: Record<CandidateFate, { label: string; tone: string }> = {
  selected: { label: "Used", tone: "text-ink" },
  pulled_in: { label: "Pulled in", tone: "text-pull" },
  skipped_redundant: { label: "Duplicate", tone: "text-ink-3" },
  below_elbow: { label: "Below cutoff", tone: "text-ink-3" },
  omitted_budget: { label: "No room", tone: "text-omit" },
  not_reached: { label: "Not reached", tone: "text-ink-4" },
};

export const STAGE_LABEL: Record<string, string> = {
  retrieve: "Search",
  probe: "Check the search",
  select: "Choose evidence",
  pack: "Assemble context",
  generate: "Write answer",
  verify: "Verify answer",
};

export const CHANNEL: Record<string, { label: string; color: string }> = {
  lexical: { label: "Keyword", color: "var(--kw)" },
  dense: { label: "Meaning", color: "var(--mn)" },
  facet: { label: "Per-part", color: "var(--facet)" },
  remediation: { label: "Follow-up", color: "var(--pull)" },
};

/** Channel color for a candidate found by one or more channels. */
export function channelColor(channels: string[]): string {
  const c = new Set(channels);
  if (c.has("remediation") && c.size === 1) return "var(--pull)";
  if (c.has("lexical") && c.has("dense")) return "var(--both)";
  if (c.has("lexical")) return "var(--kw)";
  if (c.has("dense")) return "var(--mn)";
  if (c.has("facet")) return "var(--facet)";
  return "var(--ink-3)";
}

export const fmtMs = (ms: number) => (ms < 1000 ? `${Math.round(ms)} ms` : `${(ms / 1000).toFixed(1)} s`);
export const fmtInt = (n: number) => n.toLocaleString("en-US");

export function groupFlags(flags: AwarenessFlag[]) {
  const look = flags.filter((f) => f.disposition === "needs_review");
  const handled = flags.filter((f) => f.disposition === "handled");
  const info = flags.filter((f) => f.disposition === "informational");
  const sev = { warning: 0, caution: 1, info: 2 } as const;
  look.sort((a, b) => sev[a.severity] - sev[b.severity]);
  return { look, handled, info };
}

export const cx = (...xs: (string | false | null | undefined)[]) => xs.filter(Boolean).join(" ");
