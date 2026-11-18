import { Info } from "lucide-react";
import { useApp } from "../store";

/** Shown when this server runs some checks differently: turned off (so nobody mistakes a
 *  missing check for a passed one) or on a hosted model (so nobody sends a document to a
 *  third party without knowing). */
export function ServerNotice({ className = "" }: { className?: string }) {
  const note = useApp((s) => s.config?.meaning_checks);
  if (!note?.note) return null;
  return (
    <p className={`flex items-start gap-2 text-xs leading-relaxed text-ink-3 ${className}`}>
      <Info className="mt-0.5 size-3.5 shrink-0 text-info" />
      <span>{note.note}</span>
    </p>
  );
}
