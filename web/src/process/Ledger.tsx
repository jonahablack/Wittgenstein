import { useMemo, useState } from "react";
import type { CandidateFate, LedgerEntry } from "../generated/live";
import { FATE, channelColor, cx } from "../lib";
import { type FieldData, useApp } from "../store";

const FILTERS: { id: "all" | "used" | "left"; label: string }[] = [
  { id: "used", label: "Used" },
  { id: "left", label: "Left out" },
  { id: "all", label: "All" },
];
const USED: CandidateFate[] = ["selected", "pulled_in"];

/** Every candidate's fate and the reason for it: the full answer to "what was left out,
 *  and why?". */
export function Ledger({ entries, field, corpusId }: { entries: LedgerEntry[]; field?: FieldData; corpusId: string }) {
  const [filter, setFilter] = useState<"all" | "used" | "left">("used");
  const openSource = useApp((s) => s.openSource);
  const rows = useMemo(() => {
    const xs = entries.filter((e) =>
      filter === "all" ? true : filter === "used" ? USED.includes(e.fate) : !USED.includes(e.fate),
    );
    return xs.sort((a, b) => (a.order ?? 999) - (b.order ?? 999) || (a.fused_rank ?? 999) - (b.fused_rank ?? 999));
  }, [entries, filter]);
  const left = entries.filter((e) => !USED.includes(e.fate));

  return (
    <div>
      <div className="mb-2 flex items-center gap-1">
        {FILTERS.map((f) => (
          <button
            key={f.id}
            onClick={() => setFilter(f.id)}
            className={cx(
              "rounded-md px-2.5 py-1 text-xs",
              filter === f.id ? "bg-surface-2 text-ink" : "text-ink-3 hover:text-ink",
            )}
          >
            {f.label}
            <span className="num ml-1 text-ink-4">
              {f.id === "all" ? entries.length : f.id === "used" ? entries.length - left.length : left.length}
            </span>
          </button>
        ))}
      </div>
      <div className="max-h-[360px] overflow-auto rounded-xl border border-line-soft">
        <table className="w-full text-left text-xs">
          <thead className="sticky top-0 bg-surface text-ink-4">
            <tr>
              <th className="px-3 py-2 font-normal">Passage</th>
              <th className="px-3 py-2 font-normal">Outcome</th>
              <th className="hidden px-3 py-2 font-normal sm:table-cell">Why</th>
              <th className="px-3 py-2 text-right font-normal">Relevance</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-line-soft">
            {rows.slice(0, 200).map((e) => {
              const i = field?.index.get(e.unit_id);
              const u = i === undefined ? undefined : field!.units[i];
              return (
                <tr
                  key={e.unit_id}
                  className="cursor-pointer align-top hover:bg-surface-2/60"
                  onClick={() =>
                    u &&
                    openSource({ corpusId, documentId: u.document_id, start: u.char_start, end: u.char_end, label: u.location })
                  }
                >
                  <td className="max-w-[260px] px-3 py-2">
                    <span className="flex items-center gap-1.5">
                      <span className="size-2 shrink-0 rounded-full" style={{ background: channelColor(e.channels) }} />
                      <span className="truncate text-ink-2">{u?.preview ?? e.unit_id}</span>
                    </span>
                    <span className="block truncate pl-3.5 text-ink-4">{u?.location}</span>
                  </td>
                  <td className={cx("px-3 py-2 whitespace-nowrap", FATE[e.fate].tone)}>{FATE[e.fate].label}</td>
                  <td className="hidden px-3 py-2 text-ink-3 sm:table-cell">{e.reason}</td>
                  <td className="num px-3 py-2 text-right text-ink-3">{e.relevance_z.toFixed(1)}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
