/*
 * Plates: a framed picture laid over the stage for a few seconds, behind brass
 * shutters that part from a centre seam. Three kinds:
 *   constellation  stars drift into letters and gold strokes join them; the
 *                  same stars can then redraw a second set of words
 *   gauge          a brass dial whose needle springs to a value and settles
 *   morph          an ink-dot galaxy scatters and regroups as a prop or a word,
 *                  then the drawing itself fades in over the dots
 * The moving parts draw on one canvas per plate and stop repainting once they
 * settle, so a held plate costs what a still picture costs.
 */
import React, { useLayoutEffect, useRef, useState } from "react";
import { cancelRender, continueRender, delayRender } from "remotion";
import { Bitmap, bitmapUrl, type Drawing } from "./bitmap";
import { STAGE, TIMING, type PlateEvent, type PropSpec } from "./contract";
import { letter } from "./glyphs";
import { Sh, circle } from "./ink";
import { CREAM, GOLD, INK, IVORY, NAVY, SEAL, SERIF, STARGOLD, TEXT } from "./palette";
import { rng } from "./backdrops";
import { loadStorybookFonts } from "./fonts";
import { clamp01, ease } from "./stage";

const P = STAGE.plate;

const PANEL: Record<PlateEvent["type"], string> = { constellation: NAVY, gauge: CREAM, morph: IVORY };

/** The plate's frame, panel and shutters; `children` is drawn on the panel in plate coordinates. */
export const Plate: React.FC<{ kind: PlateEvent["type"]; open: number; children: React.ReactNode }> = ({ kind, open, children }) => {
  const half = (P.w / 2) * (1 - open);
  return (
    <div style={{ position: "absolute", left: P.x, top: P.y, width: P.w, height: P.h, overflow: "hidden" }}>
      <div style={{ position: "absolute", inset: 0, background: PANEL[kind], border: `4px solid ${INK}`, boxSizing: "border-box" }}>
        <div style={{ position: "absolute", inset: 12, border: `1.6px solid ${kind === "constellation" ? GOLD : INK}`, opacity: 0.7 }} />
        {children}
      </div>
      {half > 0.5 && (
        <>
          <div style={{ position: "absolute", left: 0, top: 0, width: half, height: P.h, background: GOLD, borderRight: `3px solid ${INK}` }} />
          <div style={{ position: "absolute", right: 0, top: 0, width: half, height: P.h, background: GOLD, borderLeft: `3px solid ${INK}` }} />
        </>
      )}
    </div>
  );
};

// ── constellation ─────────────────────────────────────────────────────────────
type CE = Extract<PlateEvent, { type: "constellation" }>;

/** Frames from the plate's start: stars arrive, then each word's strokes draw. */
export const CONSTELLATION = { arrive: 15, perWord: 8, nextWord: 12, fadeOld: 6, move: 9 } as const;

function useCanvasDraw(draw: (ctx: CanvasRenderingContext2D) => void, key: string) {
  const ref = useRef<HTMLCanvasElement>(null);
  const last = useRef<string | null>(null);
  useLayoutEffect(() => {
    const c = ref.current;
    if (!c || last.current === key) return;
    const ctx = c.getContext("2d")!;
    ctx.clearRect(0, 0, c.width, c.height);
    draw(ctx);
    last.current = key;
  });
  return ref;
}

/** A word set's segments drawn up to `upto` (0..1 of their total length). */
function strokeSegments(ctx: CanvasRenderingContext2D, segs: [[number, number], [number, number]][], upto: number, alpha: number) {
  if (upto <= 0 || alpha <= 0) return;
  const lens = segs.map(([a, b]) => Math.hypot(b[0] - a[0], b[1] - a[1]));
  const total = lens.reduce((s, l) => s + l, 0);
  let left = total * upto;
  ctx.beginPath();
  segs.forEach(([a, b], i) => {
    if (left <= 0) return;
    const f = Math.min(1, left / lens[i]);
    ctx.moveTo(a[0], a[1]);
    ctx.lineTo(a[0] + (b[0] - a[0]) * f, a[1] + (b[1] - a[1]) * f);
    left -= lens[i];
  });
  ctx.globalAlpha = 0.18 * alpha;
  ctx.strokeStyle = STARGOLD;
  ctx.lineWidth = 14;
  ctx.lineCap = "round";
  ctx.stroke();
  ctx.globalAlpha = alpha;
  ctx.lineWidth = 4.5;
  ctx.stroke();
  ctx.globalAlpha = 1;
}

export const Constellation: React.FC<{ e: CE; frame: number }> = ({ e, frame }) => {
  const C = CONSTELLATION;
  const t = frame - e.at - TIMING.plateOpen;
  const a = letter(e.words, P.w / 2, P.h / 2, P.w - 140);
  const b = e.then ? letter(e.then, P.w / 2, P.h / 2, P.w - 140) : null;
  const tb = b && e.thenAt !== undefined ? frame - e.thenAt : -1;
  const n = Math.max(a.stars.length, b?.stars.length ?? 0);
  const r = rng(e.at * 7919 + 13);
  const scatter = Array.from({ length: n }, () => [40 + r() * (P.w - 80), 40 + r() * (P.h - 80)] as [number, number]);
  const field = Array.from({ length: 70 }, () => [20 + r() * (P.w - 40), 20 + r() * (P.h - 40), 0.25 + r() * 0.4] as [number, number, number]);
  // when everything has arrived and drawn, the picture only twinkles; it twinkles in 6 steps, then holds still
  const settledAt = b ? C.move + C.perWord + C.nextWord : C.arrive + C.nextWord * (e.words.length - 1) + C.perWord;
  const since = b && tb >= 0 ? tb : t;
  const twinkle = since > settledAt + 24 ? -1 : Math.floor(frame / 4) % 6;
  // once the stars have settled and stopped twinkling the picture is still: one key, one paint
  const key = twinkle < 0 ? `still:${b && tb >= 0 ? "then" : "first"}` : `${t}:${tb}:${twinkle}`;
  const ref = useCanvasDraw((ctx) => {
    for (const [x, y, o] of field) {
      ctx.globalAlpha = o;
      ctx.fillStyle = STARGOLD;
      ctx.fillRect(x - 1.2, y - 1.2, 2.4, 2.4);
    }
    const arrive = ease.out(clamp01(t / C.arrive));
    const move = b && tb >= 0 ? ease.inOut(clamp01((tb - C.fadeOld) / C.move)) : 0;
    for (let i = 0; i < n; i++) {
      const from = scatter[i];
      const pa = a.stars[i] ?? from;
      const pb = b ? b.stars[i] ?? scatter[i] : pa;
      const ax = from[0] + (pa[0] - from[0]) * arrive, ay = from[1] + (pa[1] - from[1]) * arrive;
      const x = ax + (pb[0] - ax) * move, y = ay + (pb[1] - ay) * move;
      const used = (move < 1 ? i < a.stars.length : true) || (b !== null && i < b.stars.length);
      const tw = twinkle < 0 ? 0 : Math.sin(i * 1.7 + twinkle) * 0.9;
      ctx.globalAlpha = used ? 1 : 0.35;
      ctx.fillStyle = STARGOLD;
      ctx.beginPath();
      ctx.arc(x, y, 4.2 + tw, 0, Math.PI * 2);
      ctx.fill();
    }
    const fadeOld = b && tb >= 0 ? 1 - clamp01(tb / C.fadeOld) : 1;
    a.segments.forEach((segs, wi) => strokeSegments(ctx, segs, clamp01((t - C.arrive - wi * C.nextWord) / C.perWord), fadeOld));
    if (b && tb >= 0) {
      b.segments.forEach((segs, wi) => strokeSegments(ctx, segs, clamp01((tb - C.fadeOld - C.move - wi * 6) / C.perWord), 1));
    }
    ctx.globalAlpha = 1;
  }, key);
  return <canvas ref={ref} width={P.w} height={P.h} style={{ position: "absolute", left: 0, top: 0 }} />;
};

// ── gauge ─────────────────────────────────────────────────────────────────────
type GE = Extract<PlateEvent, { type: "gauge" }>;
/** The dial: its radius, its pivot in plate coordinates, and the needle's sweep either side of straight up. */
const DIAL = { r: 300, cx: 450, cy: 340, sweep: 120 } as const;

function dialDrawing(max: number, danger: number | undefined): Drawing {
  const { r } = DIAL;
  const ang = (v: number) => ((-DIAL.sweep + (2 * DIAL.sweep * v) / max) * Math.PI) / 180;
  const pt = (v: number, rr: number) => [r + rr * Math.sin(ang(v)), r + 20 - rr * Math.cos(ang(v))];
  const arc = (v0: number, v1: number, rr: number) => {
    const [x0, y0] = pt(v0, rr), [x1, y1] = pt(v1, rr);
    const large = ((v1 - v0) / max) * 2 * DIAL.sweep > 180 ? 1 : 0;
    return `M${x0} ${y0}A${rr} ${rr} 0 ${large} 1 ${x1} ${y1}`;
  };
  return {
    key: `dial:${max}:${danger ?? "-"}`,
    width: 2 * r,
    height: 2 * r + 40,
    render: () => (
      <g>
        <Sh d={circle(r, r + 20, r - 6)} fill={GOLD} penOp={0.2} sw={4} />
        <Sh d={circle(r, r + 20, r - 34)} fill={CREAM} pen="none" sw={3} />
        {danger !== undefined && danger < max && (
          <path d={arc(danger, max, r - 70)} fill="none" stroke={SEAL} strokeWidth={34} />
        )}
        {Array.from({ length: 11 }, (_, i) => {
          const v = (max * i) / 10;
          const [x0, y0] = pt(v, r - 50), [x1, y1] = pt(v, r - (i % 5 === 0 ? 96 : 80));
          return <line key={i} x1={x0} y1={y0} x2={x1} y2={y1} stroke={INK} strokeWidth={i % 5 === 0 ? 6 : 3} />;
        })}
        <path d={circle(r, r + 20, 22)} fill={INK} />
      </g>
    ),
  };
}

/** The needle's value at frame t of the plate: a damped spring from `from` to `to` that settles exactly. */
export function needleAt(e: { from: number; to: number }, t: number): number {
  const u = t - TIMING.plateOpen;
  if (u <= 0) return e.from;
  if (u >= 40) return e.to;
  return e.to + (e.from - e.to) * Math.exp(-0.16 * u) * Math.cos(0.33 * u);
}

function fmt(v: number, max: number): string {
  return max >= 20 ? String(Math.round(v)) : (Math.round(v * 10) / 10).toString();
}

export const Gauge: React.FC<{ e: GE; frame: number }> = ({ e, frame }) => {
  const v = Math.max(0, Math.min(e.max * 1.08, needleAt(e, frame - e.at)));
  const deg = -DIAL.sweep + (2 * DIAL.sweep * v) / e.max;
  const dial = dialDrawing(e.max, e.danger);
  return (
    <>
      <Bitmap d={dial} left={DIAL.cx - DIAL.r} top={DIAL.cy - DIAL.r - 20} />
      <svg width={P.w} height={P.h} style={{ position: "absolute", left: 0, top: 0 }}>
        <g transform={`translate(${DIAL.cx} ${DIAL.cy}) rotate(${deg.toFixed(2)})`}>
          <path d="M-9 30 L0 -230 L9 30Z" fill={INK} />
        </g>
        <circle cx={DIAL.cx} cy={DIAL.cy} r={14} fill={GOLD} stroke={INK} strokeWidth={3} />
      </svg>
      <div style={{ position: "absolute", left: 0, width: P.w, top: DIAL.cy + 100, textAlign: "center", fontFamily: SERIF, color: TEXT, fontSize: 84, fontWeight: 500, lineHeight: 1 }}>
        {fmt(v, e.max)}
      </div>
      <div style={{ position: "absolute", left: 0, width: P.w, top: DIAL.cy + DIAL.r + 70, textAlign: "center", fontFamily: SERIF, color: TEXT, fontSize: 48, fontStyle: "italic" }}>
        {e.label}
      </div>
    </>
  );
};

// ── morph ─────────────────────────────────────────────────────────────────────
type ME = Extract<PlateEvent, { type: "morph" }>;
export const MORPH = { turn: 18, scatter: 12, regroup: 18, reveal: 10, dots: 700 } as const;
/** The morph reveals its prop fitted to a 700 x 620 box, up to about 4x; drawn at this density it stays sharp. */
export const MORPH_DENSITY = 3;
const BOX = { w: 700, h: 620 } as const;

const targets = new Map<string, [number, number][]>();

function samplePoints(img: CanvasImageSource, w: number, h: number, seed: number): [number, number][] {
  const s = Math.min(BOX.w / w, BOX.h / h);
  const dw = w * s, dh = h * s;
  const c = document.createElement("canvas");
  c.width = BOX.w;
  c.height = BOX.h;
  const ctx = c.getContext("2d")!;
  ctx.drawImage(img, (BOX.w - dw) / 2, (BOX.h - dh) / 2, dw, dh);
  const data = ctx.getImageData(0, 0, BOX.w, BOX.h).data;
  const pts: [number, number][] = [];
  for (let y = 0; y < BOX.h; y += 4) for (let x = 0; x < BOX.w; x += 4) if (data[(y * BOX.w + x) * 4 + 3] > 120) pts.push([x, y]);
  const r = rng(seed);
  const out: [number, number][] = [];
  for (let i = 0; i < MORPH.dots; i++) out.push(pts.length ? pts[Math.floor(r() * pts.length)] : [BOX.w / 2, BOX.h / 2]);
  return out.map(([x, y]) => [x + (P.w - BOX.w) / 2, y + (P.h - BOX.h) / 2]);
}

/** A word is drawn this big on a canvas this size, then fitted into BOX like a prop (so it shows at WORD_PX * BOX.w / WORD_CANVAS.w). */
const WORD_PX = 260;
const WORD_CANVAS = { w: 1400, h: 360 } as const;

async function wordImage(word: string): Promise<HTMLCanvasElement> {
  const c = document.createElement("canvas");
  c.width = WORD_CANVAS.w;
  c.height = WORD_CANVAS.h;
  const ctx = c.getContext("2d")!;
  ctx.font = `500 ${WORD_PX}px ${SERIF}`;
  ctx.textAlign = "center";
  ctx.textBaseline = "middle";
  ctx.fillStyle = "#000";
  ctx.fillText(word, WORD_CANVAS.w / 2, WORD_CANVAS.h / 2, WORD_CANVAS.w - 40);
  return c;
}

/** The morph's target as points, sampled once per render tab. */
function useTarget(e: ME, drawing: Drawing | null): [number, number][] | null {
  // the seed is part of the key: two morphs to the same target sample their own points
  const key = `${drawing ? drawing.key : `word:${e.word}`}:${e.at}`;
  const [, rerender] = useState(0);
  useLayoutEffect(() => {
    if (targets.has(key)) return;
    const handle = delayRender(`StorybookAtlas: sampling the morph target ${key}`);
    const load: Promise<[CanvasImageSource, number, number]> = drawing
      ? bitmapUrl(drawing).then(async (url) => {
          const img = new Image();
          img.src = url;
          await img.decode();
          return [img, drawing.width, drawing.height];
        })
      : loadStorybookFonts()
          .then(() => document.fonts.load(`500 ${WORD_PX}px 'EB Garamond'`))
          .then(() => wordImage(e.word ?? ""))
          .then((c) => [c, c.width, c.height]);
    load
      .then(([img, w, h]) => {
        targets.set(key, samplePoints(img, w, h, e.at + 1));
        rerender((n) => n + 1);
        continueRender(handle);
      })
      .catch((err) => cancelRender(err));
    // the target is fully described by its key
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key]);
  return targets.get(key) ?? null;
}

export const Morph: React.FC<{ e: ME; frame: number; drawing: Drawing | null; spec: PropSpec | null }> = ({ e, frame, drawing, spec }) => {
  const M = MORPH;
  const t = frame - e.at - TIMING.plateOpen;
  const target = useTarget(e, drawing);
  const r = rng(e.at * 31 + 5);
  const galaxy = Array.from({ length: M.dots }, (_, i) => {
    const arm = i % 3, d = 30 + Math.pow(r(), 0.7) * 300;
    return { a: (arm * 2 * Math.PI) / 3 + d / 90 + (r() - 0.5) * 0.5, d };
  });
  const cloud = Array.from({ length: M.dots }, () => [60 + r() * (P.w - 120), 60 + r() * (P.h - 120)] as [number, number]);
  const end = M.turn + M.scatter + M.regroup + M.reveal;
  const key = `${Math.max(-1, Math.min(t, end + 1))}:${target ? 1 : 0}`;
  const ref = useCanvasDraw((ctx) => {
    if (!target) return;
    // the galaxy holds still while the shutters open: the key below is clamped there, so the drawing must be too
    const spin = Math.max(0, Math.min(t, M.turn)) * 0.035;
    const s = ease.inOut(clamp01((t - M.turn) / M.scatter));
    const g = ease.inOut(clamp01((t - M.turn - M.scatter) / M.regroup));
    const fade = 1 - 0.75 * clamp01((t - M.turn - M.scatter - M.regroup) / M.reveal);
    ctx.fillStyle = INK;
    ctx.globalAlpha = fade;
    for (let i = 0; i < M.dots; i++) {
      const gx = P.w / 2 + galaxy[i].d * Math.cos(galaxy[i].a + spin), gy = P.h / 2 + galaxy[i].d * 0.62 * Math.sin(galaxy[i].a + spin);
      const sx = gx + (cloud[i][0] - gx) * s, sy = gy + (cloud[i][1] - gy) * s;
      const x = sx + (target[i][0] - sx) * g, y = sy + (target[i][1] - sy) * g;
      ctx.fillRect(x - 2.2, y - 2.2, 4.4, 4.4);
    }
    ctx.globalAlpha = 1;
  }, key);
  const reveal = clamp01((t - M.turn - M.scatter - M.regroup) / M.reveal);
  let img: React.ReactNode = null;
  if (drawing && spec && reveal > 0) {
    const s = Math.min(BOX.w / drawing.width, BOX.h / drawing.height);
    img = (
      <Bitmap d={drawing} left={(P.w - drawing.width) / 2} top={(P.h - drawing.height) / 2}
        transform={`scale(${s})`} origin={[drawing.width / 2, drawing.height / 2]} opacity={reveal} />
    );
  } else if (!drawing && reveal > 0) {
    img = (
      <div style={{ position: "absolute", left: 0, width: P.w, top: P.h / 2 - 90, textAlign: "center", fontFamily: SERIF, fontWeight: 500,
        fontSize: WORD_PX * (BOX.w / WORD_CANVAS.w), lineHeight: "180px", color: INK, opacity: reveal, whiteSpace: "nowrap" }}>{e.word}</div>
    );
  }
  return (
    <>
      <canvas ref={ref} width={P.w} height={P.h} style={{ position: "absolute", left: 0, top: 0 }} />
      {img}
    </>
  );
};
