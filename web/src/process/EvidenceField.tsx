import { Application, Container, Graphics, Sprite, type Texture } from "pixi.js";
import { useEffect, useMemo, useRef, useState } from "react";
import { FATE } from "../lib";
import { type FieldData, useApp } from "../store";
import type { Frame } from "./frame";
import type { Step } from "./replay";

interface Palette {
  ink: number;
  ink3: number;
  ink4: number;
  kw: number;
  mn: number;
  both: number;
  facet: number;
  pull: number;
  omit: number;
  look: number;
  handled: number;
  line: number;
}

function readPalette(): Palette {
  const css = getComputedStyle(document.documentElement);
  const hex = (name: string) => Number.parseInt(css.getPropertyValue(name).trim().replace("#", "") || "888888", 16);
  return {
    ink: hex("--ink"),
    ink3: hex("--ink-3"),
    ink4: hex("--ink-4"),
    kw: hex("--kw"),
    mn: hex("--mn"),
    both: hex("--both"),
    facet: hex("--facet"),
    pull: hex("--pull"),
    omit: hex("--omit"),
    look: hex("--look"),
    handled: hex("--handled"),
    line: hex("--line"),
  };
}

function channelTint(channels: string[], p: Palette): number {
  const c = new Set(channels);
  if (c.has("lexical") && c.has("dense")) return p.both;
  if (c.has("lexical")) return p.kw;
  if (c.has("dense")) return p.mn;
  if (c.has("facet")) return p.facet;
  if (c.has("remediation")) return p.pull;
  return p.ink3;
}

const mix = (a: number, b: number, k: number) => {
  const ar = (a >> 16) & 255,
    ag = (a >> 8) & 255,
    ab = a & 255;
  const br = (b >> 16) & 255,
    bg = (b >> 8) & 255,
    bb = b & 255;
  return (
    (Math.round(ar + (br - ar) * k) << 16) | (Math.round(ag + (bg - ag) * k) << 8) | Math.round(ab + (bb - ab) * k)
  );
};

interface Props {
  field: FieldData;
  frame: Frame;
  steps: Step[];
  t: number;
  corpusId: string;
}

/** The evidence field. Center: the question. Distance from center: how close a passage
 *  is in meaning (by rank, so "near" always means "unusually close", never "high raw
 *  cosine"). Angle: where it sits in the document, read clockwise from the top. Color:
 *  how it was found. Passages chosen as evidence move into the core. */
export function EvidenceField({ field, frame, steps, t, corpusId }: Props) {
  const host = useRef<HTMLDivElement>(null);
  const frameRef = useRef(frame);
  const timeRef = useRef({ t, steps });
  frameRef.current = frame;
  timeRef.current = { t, steps };
  const posRef = useRef<{ x: Float32Array; y: Float32Array; s: Float32Array }>(null);
  const [hover, setHover] = useState<{ i: number; x: number; y: number }>();
  const [size, setSize] = useState({ w: 800, h: 520 });
  const openSource = useApp((s) => s.openSource);

  // Static layout: angle from document position, radius from meaning rank.
  const layout = useMemo(() => {
    const n = field.units.length;
    const z = field.dense_z ?? field.lexical_z;
    const order = [...z.keys()].sort((a, b) => z[b] - z[a]);
    const rankFrac = new Float32Array(n);
    order.forEach((idx, r) => (rankFrac[idx] = n > 1 ? r / (n - 1) : 0));
    const angle = new Float32Array(n);
    field.units.forEach((u, i) => (angle[i] = -Math.PI / 2 + 2 * Math.PI * u.position));
    const docStarts: { id: string; angle: number }[] = [];
    let lastDoc = "";
    field.units.forEach((u, i) => {
      if (u.document_id !== lastDoc) {
        docStarts.push({ id: u.document_id, angle: angle[i] });
        lastDoc = u.document_id;
      }
    });
    return { n, rankFrac, angle, docStarts };
  }, [field]);

  useEffect(() => {
    const el = host.current;
    if (!el) return;
    const ro = new ResizeObserver(([entry]) => {
      const w = Math.max(280, entry.contentRect.width);
      setSize({ w, h: Math.round(Math.min(620, Math.max(340, w * 0.62))) });
    });
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  const sizeRef = useRef(size);
  sizeRef.current = size;

  useEffect(() => {
    const el = host.current;
    if (!el) return;
    let disposed = false;
    let app: Application | undefined;
    const palette = readPalette();
    (async () => {
      const a = new Application();
      await a.init({
        width: sizeRef.current.w,
        height: sizeRef.current.h,
        backgroundAlpha: 0,
        antialias: true,
        resolution: Math.min(2, window.devicePixelRatio || 1),
        autoDensity: true,
        preference: "webgpu",
      });
      if (disposed) {
        a.destroy(true, { children: true, texture: true });
        return;
      }
      app = a;
      el.appendChild(a.canvas);
      a.canvas.style.display = "block";

      // A soft dot texture: drawn once, tinted per passage.
      const dotG = new Graphics();
      dotG.circle(0, 0, 16).fill({ color: 0xffffff, alpha: 0.08 });
      dotG.circle(0, 0, 10).fill({ color: 0xffffff, alpha: 0.22 });
      dotG.circle(0, 0, 6).fill({ color: 0xffffff, alpha: 1 });
      const dot: Texture = a.renderer.generateTexture(dotG);

      const backdrop = new Graphics();
      const links = new Graphics();
      const dots = new Container();
      const overlay = new Graphics();
      a.stage.addChild(backdrop, links, dots, overlay);

      const n = layout.n;
      const sprites: Sprite[] = [];
      const cx = new Float32Array(n),
        cy = new Float32Array(n),
        ca = new Float32Array(n),
        cs = new Float32Array(n),
        ct = new Uint32Array(n);
      for (let i = 0; i < n; i++) {
        const s = new Sprite(dot);
        s.anchor.set(0.5);
        dots.addChild(s);
        sprites.push(s);
        ca[i] = 0;
        cs[i] = 0.2;
        ct[i] = palette.ink4;
      }
      posRef.current = { x: cx, y: cy, s: cs };
      let initialized = false;
      let applied = { w: sizeRef.current.w, h: sizeRef.current.h };

      a.ticker.add((ticker) => {
        const { w, h } = sizeRef.current;
        if (applied.w !== w || applied.h !== h) {
          a.renderer.resize(w, h);
          applied = { w, h };
        }
        const R = Math.min(w, h) / 2 - 26;
        const ox = w / 2,
          oy = h / 2;
        const core = R * 0.2;
        const fr = frameRef.current;
        const { t: now, steps } = timeRef.current;
        const k = 1 - Math.exp(-ticker.deltaMS / 140);
        const kmax = Math.max(1, ...[...fr.units.values()].map((v) => v.entry?.order ?? 0));

        backdrop.clear();
        backdrop.circle(ox, oy, R).stroke({ width: 1, color: palette.line, alpha: 0.9 });
        backdrop.circle(ox, oy, core).stroke({ width: 1, color: palette.mn, alpha: 0.28 });
        for (const d of layout.docStarts) {
          const x1 = ox + Math.cos(d.angle) * (R - 4),
            y1 = oy + Math.sin(d.angle) * (R - 4);
          const x2 = ox + Math.cos(d.angle) * (R + 6),
            y2 = oy + Math.sin(d.angle) * (R + 6);
          backdrop.moveTo(x1, y1).lineTo(x2, y2).stroke({ width: 1.5, color: palette.ink3, alpha: 0.7 });
        }

        links.clear();
        overlay.clear();
        for (let i = 0; i < n; i++) {
          const u = field.units[i];
          const v = fr.units.get(u.unit_id);
          const ang = layout.angle[i];
          let r = core + (R - core) * (0.06 + 0.94 * Math.sqrt(layout.rankFrac[i]));
          let alpha = 0.16,
            scale = 0.26,
            tint = palette.ink4;
          if (v) {
            const ch = channelTint(v.channels, palette);
            if (v.channels.length) {
              tint = ch;
              alpha = 0.9;
              scale = 0.48;
            }
            switch (v.fate) {
              case "selected":
              case "pulled_in": {
                const o = (v.entry?.order ?? 1) - 1;
                r = core * (0.35 + 0.6 * (kmax > 1 ? o / (kmax - 1) : 0.5));
                tint = v.fate === "pulled_in" ? palette.pull : palette.ink;
                alpha = 1;
                scale = 0.64;
                break;
              }
              case "below_elbow":
              case "not_reached":
                alpha = v.channels.length ? 0.34 : 0.16;
                scale = 0.38;
                break;
              case "skipped_redundant":
                tint = palette.ink3;
                alpha = 0.4;
                scale = 0.38;
                break;
              case "omitted_budget":
                tint = palette.omit;
                alpha = 0.95;
                scale = 0.5;
                break;
            }
            if (v.cited) scale = 0.82;
          }
          const tx = ox + Math.cos(ang) * r,
            ty = oy + Math.sin(ang) * r;
          if (!initialized) {
            cx[i] = tx;
            cy[i] = ty;
          }
          cx[i] += (tx - cx[i]) * k;
          cy[i] += (ty - cy[i]) * k;
          ca[i] += (alpha - ca[i]) * k;
          cs[i] += (scale - cs[i]) * k;
          ct[i] = mix(ct[i], tint, Math.min(1, k * 1.5));
          const s = sprites[i];
          s.position.set(cx[i], cy[i]);
          s.alpha = ca[i];
          s.scale.set(cs[i]);
          s.tint = ct[i];
          if (v?.cited) links.moveTo(ox, oy).lineTo(cx[i], cy[i]).stroke({ width: 1.6, color: palette.mn, alpha: 0.85 });
          if (v?.flag === "look")
            overlay.circle(cx[i], cy[i], 8.5).stroke({ width: 1.4, color: palette.look, alpha: 0.95 });
          else if (v?.flag === "handled")
            overlay.circle(cx[i], cy[i], 8).stroke({ width: 1, color: palette.handled, alpha: 0.6 });
        }
        initialized = true;

        // The question at the center, and a ripple each time the search fans out.
        overlay.circle(ox, oy, 4.5).fill({ color: palette.ink, alpha: fr.analyzed ? 1 : 0.4 });
        overlay.circle(ox, oy, 9).stroke({ width: 1.2, color: palette.mn, alpha: 0.6 });
        const ps = steps[fr.pulse];
        if (ps) {
          const age = now - ps.start;
          if (age >= 0 && age < 1300) {
            const q = age / 1300;
            overlay.circle(ox, oy, 9 + (R - 9) * q).stroke({ width: 1.5, color: palette.mn, alpha: 0.45 * (1 - q) });
          }
        }
      });
    })();
    return () => {
      disposed = true;
      posRef.current = null;
      app?.destroy(true, { children: true, texture: true });
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [field, layout]);

  const nearest = (x: number, y: number) => {
    const pos = posRef.current;
    if (!pos) return undefined;
    let best = -1,
      bd = 12 * 12;
    for (let i = 0; i < layout.n; i++) {
      const dx = pos.x[i] - x,
        dy = pos.y[i] - y;
      const d = dx * dx + dy * dy;
      if (d < bd) {
        bd = d;
        best = i;
      }
    }
    return best >= 0 ? best : undefined;
  };

  const hu = hover ? field.units[hover.i] : undefined;
  const hv = hu ? frame.units.get(hu.unit_id) : undefined;

  return (
    <div className="relative">
      <div
        ref={host}
        className="relative w-full cursor-crosshair"
        style={{ height: size.h }}
        onPointerMove={(e) => {
          const rect = e.currentTarget.getBoundingClientRect();
          const x = e.clientX - rect.left,
            y = e.clientY - rect.top;
          const i = nearest(x, y);
          setHover(i === undefined ? undefined : { i, x, y });
        }}
        onPointerLeave={() => setHover(undefined)}
        onClick={() => {
          if (!hu) return;
          openSource({
            corpusId,
            documentId: hu.document_id,
            start: hu.char_start,
            end: hu.char_end,
            label: hu.location,
          });
        }}
        role="img"
        aria-label="Evidence field: every passage of the document arranged by how close it is to the question and where it sits in the document"
      />
      <div className="pointer-events-none absolute top-3 left-1/2 -translate-x-1/2 text-[11px] tracking-wide text-ink-4 uppercase">
        start of document
      </div>
      {hu && hover && (
        <div
          className="pointer-events-none absolute z-10 w-72 rounded-xl border border-line bg-elev/95 p-3 text-xs leading-5 shadow-glow backdrop-blur"
          style={{
            left: Math.min(hover.x + 14, size.w - 300),
            top: Math.min(hover.y + 14, size.h - 150),
          }}
        >
          <p className="truncate text-ink-3">{hu.location}</p>
          <p className="mt-1 line-clamp-3 text-ink-2">{hu.preview}</p>
          {hv?.channels.length ? (
            <p className="mt-1.5 text-ink-3">
              Found by {hv.channels.map((c) => ({ lexical: "keyword", dense: "meaning", facet: "per-part", remediation: "follow-up" })[c] ?? c).join(" + ")} search
            </p>
          ) : (
            <p className="mt-1.5 text-ink-4">Not among the candidates</p>
          )}
          {hv?.entry && (
            <p className="mt-1 text-ink-2">
              <span className={FATE[hv.entry.fate].tone}>{FATE[hv.entry.fate].label}.</span> {hv.entry.reason}
            </p>
          )}
        </div>
      )}
    </div>
  );
}
