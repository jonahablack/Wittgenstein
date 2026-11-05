import { FileText, Loader2, X } from "lucide-react";
import { useEffect, useState } from "react";
import { createPortal } from "react-dom";
import { uploadCorpus } from "../api";
import { useApp } from "../store";

export function Upload({ onClose }: { onClose: () => void }) {
  const refresh = useApp((s) => s.refreshCorpora);
  const setCorpus = useApp((s) => s.setCorpus);
  const [files, setFiles] = useState<File[]>([]);
  const [title, setTitle] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string>();
  const [drag, setDrag] = useState(false);

  const add = (list: FileList | null) => {
    if (!list) return;
    const ok = [...list].filter((f) => /\.(txt|md|markdown|pdf)$/i.test(f.name));
    setFiles((cur) => [...cur, ...ok]);
    if (!title && ok[0]) setTitle(ok[0].name.replace(/\.[^.]+$/, ""));
  };

  const submit = async () => {
    setBusy(true);
    setError(undefined);
    try {
      const c = await uploadCorpus(title || "Untitled", files);
      await refresh();
      setCorpus(c.corpus_id);
      onClose();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  useEffect(() => {
    const esc = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    document.addEventListener("keydown", esc);
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.removeEventListener("keydown", esc);
      document.body.style.overflow = prev;
    };
  }, [onClose]);

  // Rendered into <body>: inside the header, whose backdrop blur makes it the
  // containing block for fixed elements, the dialog was pinned to the header and
  // opened half under it.
  return createPortal(
    <div
      className="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto bg-black/50 p-4 backdrop-blur-sm sm:items-center"
      onClick={onClose}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-label="Add a document"
        className="my-auto w-full max-w-lg rounded-2xl border border-line bg-elev p-5 shadow-glow"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between">
          <h2 className="font-semibold">Add a document</h2>
          <button onClick={onClose} aria-label="Close" className="text-ink-3 hover:text-ink">
            <X className="size-5" />
          </button>
        </div>
        <p className="mt-1 text-sm text-ink-3">
          PDF, Markdown or plain text. It stays on this machine; nothing is sent anywhere unless you choose a
          language-model answer style.
        </p>
        <label
          onDragOver={(e) => {
            e.preventDefault();
            setDrag(true);
          }}
          onDragLeave={() => setDrag(false)}
          onDrop={(e) => {
            e.preventDefault();
            setDrag(false);
            add(e.dataTransfer.files);
          }}
          className={`mt-4 flex cursor-pointer flex-col items-center justify-center rounded-xl border border-dashed px-4 py-8 text-sm ${
            drag ? "border-mn bg-mn/5" : "border-line text-ink-3"
          }`}
        >
          <FileText className="mb-2 size-6" />
          Drop files here or click to choose
          <input type="file" multiple accept=".txt,.md,.markdown,.pdf" className="hidden" onChange={(e) => add(e.target.files)} />
        </label>
        {files.length > 0 && (
          <ul className="mt-3 max-h-32 space-y-1 overflow-auto text-sm text-ink-2">
            {files.map((f, i) => (
              <li key={i} className="flex justify-between gap-3">
                <span className="truncate">{f.name}</span>
                <span className="num text-ink-4">{(f.size / 1024).toFixed(0)} KB</span>
              </li>
            ))}
          </ul>
        )}
        <input
          value={title}
          onChange={(e) => setTitle(e.target.value)}
          placeholder="Name"
          className="mt-4 h-10 w-full rounded-lg border border-line bg-surface px-3 text-sm focus:outline-2 focus:outline-mn/60"
        />
        {error && <p className="mt-3 text-sm text-omit">{error}</p>}
        <div className="mt-4 flex justify-end gap-2">
          <button onClick={onClose} className="h-9 rounded-lg px-3 text-sm text-ink-3 hover:text-ink">
            Cancel
          </button>
          <button
            onClick={submit}
            disabled={!files.length || busy}
            className="flex h-9 items-center gap-2 rounded-lg bg-ink px-4 text-sm font-medium text-bg disabled:opacity-40"
          >
            {busy && <Loader2 className="size-4 animate-spin" />} Add
          </button>
        </div>
      </div>
    </div>,
    document.body,
  );
}
