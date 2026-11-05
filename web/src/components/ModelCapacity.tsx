import { Gauge, Loader2 } from "lucide-react";
import { useEffect, useState } from "react";

// How many passages the answering model uses reliably, as measured
// (engine live/generator_profile.py): shown under the question box, with the full
// record one click away, or a button to measure it.

type Profile = {
  model: string;
  measured_at: string;
  sizes: number[];
  accuracy: Record<string, number>;
  wrong_passage: Record<string, number>;
  reliable_passages: number;
  n_probes: number;
};

const PAID = new Set(["claude", "openai"]);
const pct = (x: number) => `${Math.round(x * 100)}%`;

export function ModelCapacity({ provider }: { provider: string }) {
  const [prof, setProf] = useState<Profile | null | undefined>(undefined);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string>();

  useEffect(() => {
    let live = true;
    setProf(undefined);
    fetch(`/live/generator-profile?provider=${provider}`)
      .then((r) => (r.ok ? (r.json() as Promise<Profile>) : null))
      .then((p) => live && setProf(p))
      .catch(() => live && setProf(null));
    return () => {
      live = false;
    };
  }, [provider]);

  const measure = async () => {
    if (PAID.has(provider) && !window.confirm("Measuring sends 60 requests to this model, billed to your API key. Continue?"))
      return;
    setBusy(true);
    setError(undefined);
    try {
      const r = await fetch(`/live/generator-profile?provider=${provider}`, { method: "POST" });
      if (!r.ok) throw new Error((await r.json()).detail ?? r.statusText);
      setProf((await r.json()) as Profile);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  if (prof === undefined) return null;
  return (
    <p className="mt-2 flex flex-wrap items-center gap-x-2 gap-y-1 px-1 text-xs text-ink-3">
      <Gauge className="size-3.5 shrink-0" />
      {prof ? (
        <>
          <span
            title={prof.sizes
              .map((s) => `${s} passages: ${pct(prof.accuracy[String(s)])} correct, ${pct(prof.wrong_passage[String(s)])} from the wrong passage`)
              .join("\n")}
          >
            This model uses up to <span className="text-ink-2">{prof.reliable_passages} passages</span> reliably
            (measured {prof.measured_at.slice(0, 10)}, {prof.n_probes} probes per size).
          </span>
          <a
            href={`/live/generator-profile?provider=${provider}`}
            target="_blank"
            rel="noreferrer"
            className="underline underline-offset-2 hover:text-ink"
          >
            Full record
          </a>
          <button onClick={() => void measure()} disabled={busy} className="underline underline-offset-2 hover:text-ink">
            {busy ? "Measuring…" : "Measure again"}
          </button>
        </>
      ) : (
        <>
          <span>How much context this model handles hasn’t been measured.</span>
          <button
            onClick={() => void measure()}
            disabled={busy}
            className="flex items-center gap-1 underline underline-offset-2 hover:text-ink"
          >
            {busy && <Loader2 className="size-3 animate-spin" />}
            {busy ? "Measuring (about a minute)…" : "Measure it (60 requests)"}
          </button>
        </>
      )}
      {error && <span className="text-omit">{error}</span>}
    </p>
  );
}
