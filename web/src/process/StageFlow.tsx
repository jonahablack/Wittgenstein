import { scaleLog } from "d3";
import { fmtInt } from "../lib";
import type { Frame } from "./frame";

/** How many passages survive each step, as it happens: document -> candidates ->
 *  considered -> context -> cited. Log-scaled so a 2,000-passage document and its
 *  eight cited passages fit on one track. */
export function StageFlow({ total, frame }: { total: number; frame: Frame }) {
  const used = [...frame.units.values()].filter((v) => v.fate === "selected" || v.fate === "pulled_in").length;
  const steps = [
    { label: "In the document", n: total, color: "var(--ink-4)" },
    { label: "Candidates found", n: frame.candidatesShown, color: "var(--both)" },
    { label: "Decided", n: frame.decided, color: "var(--mn)" },
    { label: "Used as evidence", n: frame.packed || used, color: "var(--ink)" },
    { label: "Cited in the answer", n: frame.citedUnits.length, color: "var(--mn)" },
  ];
  const x = scaleLog()
    .domain([1, Math.max(2, total)])
    .range([4, 100])
    .clamp(true);
  return (
    <ul className="space-y-2">
      {steps.map((s) => (
        <li key={s.label} className="grid grid-cols-[9.5rem_1fr_3.5rem] items-center gap-3 text-xs">
          <span className="text-ink-3">{s.label}</span>
          <span className="h-1.5 overflow-hidden rounded-full bg-surface-2">
            <span
              className="block h-full rounded-full transition-[width] duration-300"
              style={{ width: `${s.n ? x(s.n) : 0}%`, background: s.color }}
            />
          </span>
          <span className="num text-right text-ink-2">{fmtInt(s.n)}</span>
        </li>
      ))}
    </ul>
  );
}
