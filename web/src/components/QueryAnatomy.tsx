import { Cpu } from "lucide-react";
import { useState } from "react";
import type { QueryAnalysis } from "../generated/live";
import { useApp } from "../store";

const KIND_LABEL: Record<string, string> = {
  negation: "negation",
  number: "number",
  date: "date",
  identifier: "exact name",
  comparator: "comparison",
  quoted: "exact phrase",
  modality: "obligation/permission",
};
const QTYPE: Record<string, string> = {
  factoid: "a direct question",
  enumeration: "a request for a complete list",
  comparison: "a comparison",
  explanation: "a request for an explanation",
  unknown: "a question",
};
const FACET_COLORS = ["var(--mn)", "var(--facet)", "var(--kw)", "var(--both)"];

/** How the system read the question: its parts (each searched on its own) and its exact
 *  conditions (each tested against the search model). Showing this up front is the
 *  first piece of transparency: the user sees what was actually looked for. */
export function QueryAnatomy({ analysis }: { analysis: QueryAnalysis }) {
  const profile = useApp((s) => s.run?.profile);
  const [modelOpen, setModelOpen] = useState(false);
  const q = analysis.query;
  const marks: { start: number; end: number; kind: "facet" | "constraint"; color: string; label: string }[] = [];
  analysis.facets.forEach((f, i) =>
    marks.push({ start: f.span.start, end: f.span.end, kind: "facet", color: FACET_COLORS[i % 4], label: `Part ${i + 1}` }),
  );
  for (const c of analysis.constraints)
    if (c.kind !== "modality") marks.push({ start: c.span.start, end: c.span.end, kind: "constraint", color: "var(--look)", label: KIND_LABEL[c.kind] });

  // Render character by character into runs that share the same set of marks.
  const runs: { text: string; facet?: (typeof marks)[0]; constraint?: (typeof marks)[0] }[] = [];
  for (let i = 0; i < q.length; i++) {
    const facet = marks.find((m) => m.kind === "facet" && m.start <= i && i < m.end);
    const constraint = marks.find((m) => m.kind === "constraint" && m.start <= i && i < m.end);
    const last = runs.at(-1);
    if (last && last.facet === facet && last.constraint === constraint) last.text += q[i];
    else runs.push({ text: q[i], facet, constraint });
  }
  const constraints = analysis.constraints.filter((c) => c.kind !== "modality");

  return (
    <div className="mx-auto max-w-3xl px-1">
      <p className="text-[15px] leading-8 text-ink-2">
        {runs.map((r, i) => (
          <span
            key={i}
            style={{
              textDecorationColor: r.facet?.color,
              background: r.constraint ? "color-mix(in oklab, var(--look) 16%, transparent)" : undefined,
            }}
            className={`${r.facet ? "text-ink underline decoration-2 underline-offset-[6px]" : ""} ${r.constraint ? "rounded-[4px] px-[1px]" : ""}`}
            title={[r.facet?.label, r.constraint?.label].filter(Boolean).join(" · ") || undefined}
          >
            {r.text}
          </span>
        ))}
      </p>
      <div className="mt-1 flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-ink-3">
        <span>Read as {QTYPE[analysis.question_type]}</span>
        {analysis.facets.length > 1 && <span>{analysis.facets.length} parts, each searched separately</span>}
        {constraints.length > 0 && (
          <span>
            Exact conditions tested against the search model:{" "}
            {constraints.map((c) => `“${c.span.text}”`).join(", ")}
          </span>
        )}
        {profile && (
          <span className="relative">
            <button onClick={() => setModelOpen((o) => !o)} className="flex items-center gap-1 text-ink-3 hover:text-ink" aria-expanded={modelOpen}>
              <Cpu className="size-3.5" /> About the search model
            </button>
            {modelOpen && (
              <span className="absolute left-0 z-20 mt-2 block w-[min(26rem,85vw)] rounded-xl border border-line bg-elev p-4 text-xs leading-5 text-ink-2 shadow-glow">
                <span className="mb-2 block font-medium text-ink">{profile.model_identifier}</span>
                <span className="mb-2 block text-ink-3">
                  Measured on this document by probing the model, not taken from its documentation:
                </span>
                <span className="block space-y-1.5">
                  <span className="block">
                    • Reads about <b className="num text-ink">{profile.measured_window ?? "?"}</b> tokens of each passage
                    {profile.declared_window ? ` (declared: ${profile.declared_window})` : ""}; anything past that is
                    invisible to meaning-based search.
                  </span>
                  {profile.negation_shift_vs_word != null && (
                    <span className="block">
                      • Removing “not” changes its reading of a sentence{" "}
                      <b className="num text-ink">{Math.round(profile.negation_shift_vs_word * 100)}%</b> as much as removing
                      an ordinary word{profile.negation_shift_vs_word < 0.5 ? " — it barely registers negation." : "."}
                    </span>
                  )}
                  {profile.dilution_at_400_words != null && (
                    <span className="block">
                      • A sentence surrounded by 400 words of other text keeps{" "}
                      <b className="num text-ink">{Math.round(profile.dilution_at_400_words * 100)}%</b> of its similarity to
                      itself: long passages dilute what's in them.
                    </span>
                  )}
                  {profile.typical_unrelated_similarity != null && (
                    <span className="block">
                      • Unrelated passages typically score <b className="num text-ink">{profile.typical_unrelated_similarity.toFixed(2)}</b>{" "}
                      similarity, so scores are reported relative to this document, not as raw numbers.
                    </span>
                  )}
                </span>
              </span>
            )}
          </span>
        )}
      </div>
    </div>
  );
}
