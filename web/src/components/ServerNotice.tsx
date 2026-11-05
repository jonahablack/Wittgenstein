import { Info } from "lucide-react";
import { useApp } from "../store";

/** Shown when this server runs with some checks turned off (e.g. the meaning-level
 *  checks on a small hosted demo), so nobody mistakes a missing check for a passed one. */
export function ServerNotice({ className = "" }: { className?: string }) {
  const note = useApp((s) => s.config?.meaning_checks);
  if (!note || note.enabled || !note.note) return null;
  return (
    <p className={`flex items-start gap-2 text-xs leading-relaxed text-ink-3 ${className}`}>
      <Info className="mt-0.5 size-3.5 shrink-0 text-info" />
      <span>{note.note}</span>
    </p>
  );
}
