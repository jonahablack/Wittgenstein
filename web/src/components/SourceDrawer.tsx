import { FileText, Loader2, X } from "lucide-react";
import { AnimatePresence, motion } from "motion/react";
import { useEffect, useRef, useState } from "react";
import { getDocument } from "../api";
import { useApp } from "../store";

const CONTEXT_CHARS = 2400;

/** "Show me": the exact span in the original document, with the text around it, so a
 *  doubt can be settled in one click instead of re-reading the source. */
export function SourceDrawer() {
  const source = useApp((s) => s.source);
  const close = useApp((s) => s.closeSource);
  const [doc, setDoc] = useState<{ title: string; text: string }>();
  const [error, setError] = useState<string>();
  const markRef = useRef<HTMLElement>(null);

  useEffect(() => {
    if (!source) return;
    setDoc(undefined);
    setError(undefined);
    getDocument(source.corpusId, source.documentId).then(setDoc, (e) => setError(String(e)));
  }, [source]);

  useEffect(() => {
    if (doc) markRef.current?.scrollIntoView({ block: "center", behavior: "smooth" });
  }, [doc]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && close();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [close]);

  let before = "",
    mark = "",
    after = "";
  if (doc && source) {
    const a = Math.max(0, source.start - CONTEXT_CHARS);
    const b = Math.min(doc.text.length, source.end + CONTEXT_CHARS);
    before = (a > 0 ? "…" : "") + doc.text.slice(a, source.start);
    mark = doc.text.slice(source.start, source.end);
    after = doc.text.slice(source.end, b) + (b < doc.text.length ? "…" : "");
  }

  return (
    <AnimatePresence>
      {source && (
        <>
          <motion.div
            key="scrim"
            className="fixed inset-0 z-40 bg-black/30 backdrop-blur-[2px]"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            onClick={close}
          />
          <motion.aside
            key="drawer"
            role="dialog"
            aria-label="Source text"
            initial={{ x: "100%" }}
            animate={{ x: 0 }}
            exit={{ x: "100%" }}
            transition={{ type: "spring", stiffness: 380, damping: 38 }}
            className="fixed inset-y-0 right-0 z-50 flex w-full max-w-xl flex-col border-l border-line bg-elev shadow-glow"
          >
            <div className="flex items-center gap-3 border-b border-line px-5 py-4">
              <FileText className="size-4 text-ink-3" />
              <div className="min-w-0">
                <p className="truncate text-sm font-medium">{doc?.title ?? source.documentId}</p>
                {source.label && <p className="truncate text-xs text-ink-3">{source.label}</p>}
              </div>
              <button onClick={close} className="ml-auto text-ink-3 hover:text-ink" aria-label="Close">
                <X className="size-5" />
              </button>
            </div>
            <div className="flex-1 overflow-auto px-6 py-5">
              {error ? (
                <p className="text-sm text-omit">{error}</p>
              ) : !doc ? (
                <Loader2 className="size-5 animate-spin text-ink-3" />
              ) : (
                <p className="whitespace-pre-wrap text-[14.5px] leading-7 text-ink-3">
                  {before}
                  <mark
                    ref={markRef}
                    className="rounded-[4px] bg-mn/15 px-0.5 text-ink ring-1 ring-mn/40"
                    style={{ boxDecorationBreak: "clone", WebkitBoxDecorationBreak: "clone" }}
                  >
                    {mark}
                  </mark>
                  {after}
                </p>
              )}
            </div>
          </motion.aside>
        </>
      )}
    </AnimatePresence>
  );
}
