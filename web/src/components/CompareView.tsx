import { CircleDot, Wrench } from "lucide-react";
import { cx, groupFlags } from "../lib";
import { type RunState, useApp } from "../store";
import { AnswerCard } from "./AnswerCard";
import { ChecksPanel } from "./Checks";
import { Receipt } from "./Receipt";

/** Several pipelines on the same question. The point isn't a scoreboard: it's to see
 *  what a typical setup would have missed, and which of those misses the self-aware
 *  pipeline caught and handled. */
export function CompareView({ run }: { run: RunState }) {
  const active = useApp((s) => s.activePipeline);
  const setActive = useApp((s) => s.setActivePipeline);
  const base = run.pipelines[run.order[0]];
  const baseSet = new Set(base?.packed ?? []);
  const cols = run.order.map((id) => run.pipelines[id]).filter(Boolean);

  return (
    <div className="space-y-4">
      <div className={cx("grid gap-4", cols.length >= 3 ? "lg:grid-cols-3" : "md:grid-cols-2")}>
        {cols.map((p) => {
          const { look, handled } = groupFlags(Object.values(p.flags));
          const mine = new Set(p.packed);
          const onlyBase = [...baseSet].filter((u) => !mine.has(u)).length;
          const onlyMine = [...mine].filter((u) => !baseSet.has(u)).length;
          const isBase = p.id === run.order[0];
          return (
            <section
              key={p.id}
              onClick={() => setActive(p.id)}
              className={cx(
                "cursor-pointer space-y-3 rounded-2xl border p-3 transition",
                active === p.id ? "border-mn/40 bg-mn/[0.03]" : "border-transparent hover:border-line",
              )}
            >
              <header className="px-1">
                <h3 className="text-sm font-semibold text-ink">{p.label}</h3>
                <p className="text-xs leading-5 text-ink-3">{p.description}</p>
              </header>
              <AnswerCard run={run} pipeline={p} compact />
              <Receipt run={run} pipeline={p} compact />
              {p.done && (
                <div className="space-y-1.5 px-1 text-xs">
                  {!isBase && p.done && base?.done && (onlyBase > 0 || onlyMine > 0) && (
                    <p className="text-ink-3">
                      Evidence: <span className="num text-ink-2">{onlyBase}</span> passage{onlyBase === 1 ? "" : "s"} the
                      self-aware pipeline used that this one didn't
                      {onlyMine ? (
                        <>
                          , <span className="num text-ink-2">{onlyMine}</span> the other way round
                        </>
                      ) : null}
                      .
                    </p>
                  )}
                  {look.slice(0, 4).map((f) => (
                    <p key={f.flag_id} className="flex gap-1.5 text-ink-2">
                      <CircleDot className="mt-0.5 size-3.5 shrink-0 text-look" /> {f.title}
                    </p>
                  ))}
                  {look.length > 4 && <p className="text-ink-4">+{look.length - 4} more worth a look</p>}
                  {handled.length > 0 && (
                    <p className="flex gap-1.5 text-handled">
                      <Wrench className="mt-0.5 size-3.5 shrink-0" /> {handled.length} handled automatically
                    </p>
                  )}
                </div>
              )}
            </section>
          );
        })}
      </div>
      {active && run.pipelines[active] && (
        <div>
          <p className="mb-2 px-1 text-xs text-ink-3">
            Details for <span className="text-ink-2">{run.pipelines[active].label}</span> (click a column to switch)
          </p>
          <ChecksPanel run={run} pipeline={run.pipelines[active]} />
        </div>
      )}
    </div>
  );
}
