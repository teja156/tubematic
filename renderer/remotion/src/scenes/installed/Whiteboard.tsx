/*
 * Whiteboard: the whole of a Whiteboard video, as one scene.
 *
 * One large board. The camera rests on one region at a time and glides to the
 * next when the narration moves on; a floating marker writes and draws there a
 * moment after the narrator says it, in three inks that each mean one thing;
 * the video ends by pulling back to the whole board with its regions numbered,
 * a map of the argument. The agent never writes this file's kind of code: it
 * writes `props.whiteboard` (regions, each a layout with items timed to the
 * narration's words), which the MCP server validates against the rules in
 * ./whiteboard/contract.ts before the video can render.
 *
 * Cheap on the CPU: the ink is drawn on one canvas (see paintInk for why), and
 * following System Flow's measurements there are no SVG filters, no blend
 * modes, no gradients and no stroke-dasharray (a stroke draws on as a prefix
 * of its polyline). All geometry is built once per video. Text is HTML in screen coordinates at camera-scaled
 * sizes, so the text-layout audit can measure it, revealed with clip-path.
 *
 * The font is bundled in public/fonts and loaded before the first frame, so a
 * renderer with no internet access renders the same picture.
 */
import React, { useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { AbsoluteFill, Easing, continueRender, delayRender, spring, staticFile, useCurrentFrame, useVideoConfig } from "remotion";
import {
  BOARD, BOARD_COLOR, HIGHLIGHTER, INKS, SIZES, TIMING, doodleShare, type WBItem, type WhiteboardData,
} from "./whiteboard/contract";
import { DOODLES, expandDoodle, type P as DoodlePt } from "./whiteboard/doodles";
import { arrowEnds, placeRegion, regionOrigin, type Placement, type TextLine } from "./whiteboard/layout";
import { schedule, type Scheduled } from "./whiteboard/schedule";
import { H, W, cameraAt, svgTransform, toScreen, type Cam } from "./whiteboard/camera";
import { inkPoint, inkStroke, type Ink, type Pt } from "./whiteboard/ink";

const HAND = "Kalam, 'Comic Sans MS', cursive";
const INK_ALPHA = 0.94;

// ── font ──────────────────────────────────────────────────────────────────────
let fontLoaded: Promise<void> | null = null;
function loadFont(): Promise<void> {
  if (!fontLoaded) {
    fontLoaded = new FontFace("Kalam", `url(${staticFile("fonts/kalam-latin-700-normal.woff2")}) format("woff2")`, { weight: "700" })
      .load()
      .then((face) => {
        document.fonts.add(face);
      });
  }
  return fontLoaded;
}

const strokeEase = Easing.bezier(0.42, 0, 0.58, 1);

/** A colour laid over the board at `alpha`, as one opaque colour. The board
 *  is flat, so a pre-mixed colour looks the same as a translucent one and the
 *  page never blends ink. */
function onBoard(hex: string, alpha: number): string {
  const c = (h: string, i: number) => parseInt(h.slice(1 + 2 * i, 3 + 2 * i), 16);
  const out = [0, 1, 2].map((i) => Math.round(c(hex, i) * alpha + c(BOARD_COLOR, i) * (1 - alpha)));
  return `#${out.map((v) => v.toString(16).padStart(2, "0")).join("")}`;
}
const clamp01 = (v: number) => Math.max(0, Math.min(1, v));

const GHOST = onBoard(INKS.black, 0.025);

// ── prepared geometry ─────────────────────────────────────────────────────────
type Drawn = {
  s: Scheduled;
  color: string;
  width: number;
  /** Highlighter strokes sit under everything else. */
  under: boolean;
  strokes: Ink[];
  total: number;
  /** Fraction of the item's time spent on strokes; the rest writes its text. */
  strokeShare: number;
  /** Text lines in board coordinates. */
  lines: TextLine[];
  chars: number;
};

const shift = (r: Placement, o: Pt): Placement => ({
  bbox: [r.bbox[0] + o[0], r.bbox[1] + o[1], r.bbox[2], r.bbox[3]],
  lines: r.lines.map((l) => ({ ...l, x: l.x + o[0], y: l.y + o[1] })),
  doodle: r.doodle ? { ...r.doodle, cx: r.doodle.cx + o[0], cy: r.doodle.cy + o[1] } : undefined,
});

const lh = (size: number) => size * SIZES.lineHeight;
const inked = (s: string) => s.replace(/\s+/g, "").length;

function marksFor(it: WBItem, target: Placement, seed: string): { strokes: Ink[]; width: number; under: boolean } {
  const [x, y, w, h] = target.bbox;
  if (it.kind === "highlight") {
    return {
      strokes: target.lines.map((l, i) => inkStroke([[l.x - 10, l.y + lh(l.size) * 0.55], [l.x + l.width + 10, l.y + lh(l.size) * 0.55]], `${seed}${i}`, 1.2)),
      width: target.lines.length ? target.lines[0].size * 0.78 : 40,
      under: true,
    };
  }
  if (it.kind === "underline") {
    const last = target.lines[target.lines.length - 1];
    const yy = last ? last.y + lh(last.size) * 0.98 : y + h + 8;
    const x0 = last ? last.x : x;
    const x1 = last ? last.x + last.width : x + w;
    return { strokes: [inkStroke([[x0 - 6, yy + 2], [(x0 + x1) / 2, yy - 2], [x1 + 8, yy + 3]], seed, 1.8)], width: 9, under: false };
  }
  if (it.kind === "circle") {
    const cx = x + w / 2;
    const cy = y + h / 2;
    const rx = w / 2 + 34;
    const ry = h / 2 + 26;
    const pts: Pt[] = [];
    for (let a = -110; a <= 275; a += 6) pts.push([cx + Math.cos((a * Math.PI) / 180) * rx, cy + Math.sin((a * Math.PI) / 180) * ry]);
    return { strokes: [inkStroke(pts, seed, 3)], width: 9, under: false };
  }
  if (it.kind === "box") {
    const p = 20;
    return { strokes: [inkStroke([[x - p, y - p], [x + w + p, y - p], [x + w + p, y + h + p], [x - p, y + h + p], [x - p, y - p - 4]], seed, 2.2)], width: 9, under: false };
  }
  // cross
  return {
    strokes: [inkStroke([[x - 10, y - 6], [x + w + 10, y + h + 6]], `${seed}a`, 2), inkStroke([[x + w + 10, y - 6], [x - 10, y + h + 6]], `${seed}b`, 2)],
    width: 10,
    under: false,
  };
}

function prepare(data: WhiteboardData): Drawn[] {
  const scheduled = schedule(data);
  // The video's own doodles first (the validator refuses a name that shadows
  // the library), then the shipped library.
  const custom: Record<string, DoodlePt[][]> = Object.fromEntries(
    Object.entries(data.doodles ?? {}).map(([name, def]) => [name, expandDoodle(def)]),
  );
  const doodleStrokes = (name: string) => custom[name] ?? DOODLES[name] ?? [];
  const placements = data.regions.map((region, ri) => {
    const o = regionOrigin(ri);
    const placed = placeRegion(region);
    const out = new Map<string, Placement>();
    placed.forEach((p, id) => out.set(id, shift(p, o)));
    return out;
  });
  return scheduled.map((s) => {
    const it = s.item;
    const color = it.kind === "highlight" ? onBoard(HIGHLIGHTER, 0.7) : onBoard(INKS[it.ink ?? "black"], INK_ALPHA);
    const seed = `${s.region}:${it.id}`;
    const base = { s, color, under: false, lines: [] as TextLine[], strokes: [] as Ink[], width: 11, strokeShare: 1 };
    const pl = placements[s.region];
    let d: Omit<Drawn, "total" | "chars">;
    if (it.kind === "text" || it.kind === "formula") {
      d = { ...base, lines: pl.get(it.id)?.lines ?? [], strokeShare: 0 };
    } else if (it.kind === "doodle") {
      const p = pl.get(it.id);
      const strokes: Ink[] = [];
      if (p?.doodle) {
        const { cx, cy, size } = p.doodle;
        const k = size / 100;
        doodleStrokes(it.doodle).forEach((st, i) =>
          strokes.push(inkStroke(st.map(([px, py]) => [cx - size / 2 + px * k, cy - size / 2 + py * k] as Pt), `${seed}:${i}`, Math.max(1.4, size * 0.006))),
        );
      }
      const width = Math.max(8, Math.min(12, (p?.doodle?.size ?? 200) * 0.03));
      const share = doodleShare(it, s.dur);
      d = { ...base, strokes, width, lines: p?.lines ?? [], strokeShare: share };
    } else if (it.kind === "arrow") {
      const a = pl.get(it.from);
      const b = pl.get(it.to);
      const strokes: Ink[] = [];
      if (a && b) {
        const [p0, p1] = arrowEnds(a.bbox, b.bbox);
        const ang = Math.atan2(p1[1] - p0[1], p1[0] - p0[0]);
        const head = (da: number): Pt => [p1[0] - Math.cos(ang + da) * 34, p1[1] - Math.sin(ang + da) * 34];
        strokes.push(inkStroke([p0, p1], seed, 2.4), inkStroke([head(0.5), p1, head(-0.5)], `${seed}h`, 1));
      }
      d = { ...base, strokes, width: 10 };
    } else {
      const target = pl.get(it.target);
      const m = target ? marksFor(it, target, seed) : { strokes: [], width: 9, under: false };
      d = { ...base, ...m };
    }
    return { ...d, total: d.strokes.reduce((a, st) => a + st.len, 0), chars: d.lines.reduce((a, l) => a + inked(l.text), 0) };
  });
}

/** Progress of an item at a frame: strokes (0..1) then text (0..1). */
function progress(d: Drawn, frame: number): { ps: number; pt: number } {
  const u = clamp01((frame - d.s.start) / d.s.dur);
  if (frame < d.s.start) return { ps: 0, pt: 0 };
  const ps = d.strokeShare > 0 ? strokeEase(clamp01(u / d.strokeShare)) : 1;
  const raw = d.strokeShare < 1 ? clamp01((u - d.strokeShare) / (1 - d.strokeShare)) : 1;
  // Each letter is written with its own slow-fast-slow stroke.
  const n = Math.max(1, d.chars);
  const idx = raw * n;
  const k = Math.floor(idx);
  const pt = raw >= 1 ? 1 : (k + strokeEase(idx - k)) / n;
  return { ps, pt };
}

/** How much of each line is written at text progress pt. */
function lineReveal(d: Drawn, pt: number): number[] {
  let left = pt * d.chars;
  return d.lines.map((l) => {
    const c = Math.max(1, inked(l.text));
    const r = clamp01(left / c);
    left -= c;
    return r;
  });
}

/** Where the marker's tip is on the board while it works on an item. */
function tipAt(d: Drawn, frame: number): Pt | null {
  const { ps, pt } = progress(d, frame);
  if (d.strokeShare > 0 && ps < 1 && d.strokes.length) {
    let at = ps * d.total;
    for (const st of d.strokes) {
      if (at <= st.len) return inkPoint(st, at);
      at -= st.len;
    }
  }
  if (d.lines.length) {
    const rev = lineReveal(d, pt);
    let i = rev.findIndex((r) => r < 1);
    if (i < 0) i = d.lines.length - 1;
    const l = d.lines[i];
    const wig = Math.sin(rev[i] * Math.max(1, l.text.length) * Math.PI * 2) * l.size * 0.12;
    return [l.x + l.width * rev[i], l.y + lh(l.size) * 0.5 + wig];
  }
  return d.strokes.length ? inkPoint(d.strokes[d.strokes.length - 1], Infinity) : null;
}

// ── the marker ───────────────────────────────────────────────────────────────
const PARK: Pt = [1260, 1300];
const HOP = 18;
const OUT = 9;

type PenState = { x: number; y: number; lift: number; color: string } | null;

function penAt(drawn: Drawn[], frame: number, cam: Cam): PenState {
  let prev: Drawn | null = null;
  let next: Drawn | null = null;
  for (const d of drawn) {
    const end = d.s.start + d.s.dur;
    if (frame >= d.s.start && frame < end) {
      const tip = tipAt(d, frame);
      if (!tip) return null;
      const [x, y] = toScreen(cam, tip[0], tip[1]);
      return { x, y, lift: 0, color: d.color };
    }
    if (end <= frame) prev = d;
    if (d.s.start > frame && !next) next = d;
  }
  const endPos = (d: Drawn) => tipAt(d, d.s.start + d.s.dur);
  const startPos = (d: Drawn) => tipAt(d, d.s.start);
  const scr = (p: Pt | null): Pt => (p ? toScreen(cam, p[0], p[1]) : PARK);
  const lerp = (a: number, b: number, t: number) => a + (b - a) * t;
  if (prev && next) {
    const pe = prev.s.start + prev.s.dur;
    const gap = next.s.start - pe;
    if (gap <= HOP) {
      const t = clamp01((frame - pe) / Math.max(1, gap));
      const e = strokeEase(t);
      const a = scr(endPos(prev));
      const b = scr(startPos(next));
      const dist = Math.hypot(b[0] - a[0], b[1] - a[1]);
      return {
        x: lerp(a[0], b[0], e),
        y: lerp(a[1], b[1], e) - Math.sin(Math.PI * t) * Math.min(60, 10 + dist * 0.12),
        lift: Math.sin(Math.PI * t) * Math.min(40, 10 + dist * 0.1),
        color: t < 0.5 ? prev.color : next.color,
      };
    }
  }
  if (prev && frame - (prev.s.start + prev.s.dur) < OUT) {
    const t = (frame - (prev.s.start + prev.s.dur)) / OUT;
    const a = scr(endPos(prev));
    const e = Easing.bezier(0.5, 0, 0.9, 0.6)(t);
    return { x: lerp(a[0], PARK[0], e), y: lerp(a[1], PARK[1], e), lift: 40 * clamp01(t * 3), color: prev.color };
  }
  if (next && next.s.start - frame <= OUT) {
    const t = 1 - (next.s.start - frame) / OUT;
    const b = scr(startPos(next));
    const e = Easing.bezier(0.1, 0.5, 0.3, 1)(t);
    return { x: lerp(PARK[0], b[0], e), y: lerp(PARK[1], b[1], e), lift: 40 * clamp01((1 - t) * 3), color: next.color };
  }
  return null;
}

/** A chisel marker with a cap, tip at (0, 0). Its shadow is an offset
 *  translucent copy, never a blur filter. */
const MarkerBody: React.FC<{ fill: string; ink: string; outline?: boolean }> = ({ fill, ink, outline }) => (
  <g>
    <path d="M0 0 L22 -9 L22 9 Z" fill={ink} />
    <rect x={20} y={-15} width={22} height={30} rx={4} fill={ink} />
    <rect x={40} y={-21} width={170} height={42} rx={9} fill={fill} stroke={outline ? "rgba(35,38,44,0.35)" : undefined} strokeWidth={outline ? 2 : 0} />
    <rect x={206} y={-23} width={58} height={46} rx={12} fill={ink} />
  </g>
);

const Pen: React.FC<{ p: NonNullable<PenState>; scale: number }> = ({ p, scale }) => (
  <g transform={`translate(${p.x.toFixed(1)} ${p.y.toFixed(1)}) scale(${scale.toFixed(3)})`}>
    <g transform={`translate(${(10 + p.lift * 0.9).toFixed(1)} ${(14 + p.lift * 1.05).toFixed(1)}) rotate(-40)`}>
      <MarkerBody fill="rgba(0,0,0,0.12)" ink="rgba(0,0,0,0.12)" />
    </g>
    <g transform={`translate(0 ${(-p.lift * 0.45).toFixed(1)}) rotate(-56)`}>
      <MarkerBody fill="#f2f1ed" ink={p.color} outline />
      <rect x={60} y={-15} width={120} height={7} rx={3} fill="rgba(255,255,255,0.8)" />
      <rect x={84} y={4} width={70} height={8} rx={3} fill={p.color} fillOpacity={0.75} />
    </g>
  </g>
);

/** Faint marks of earlier lessons in the gutters, so the board reads as a used
 *  whiteboard. Static, built once. */
function ghostStrokes(regionCount: number): Ink[] {
  const out: Ink[] = [];
  for (let i = 0; i < regionCount; i++) {
    const [x, y] = regionOrigin(i);
    out.push(inkStroke([[x + 140, y - 120], [x + 420, y - 170], [x + 760, y - 110]], `g${i}a`, 5));
    out.push(inkStroke([[x + 300, y + BOARD.regionH + 110], [x + 620, y + BOARD.regionH + 140]], `g${i}b`, 4));
  }
  return out;
}

/** Stroke the first `upTo` px of a polyline. */
function strokeInk(ctx: CanvasRenderingContext2D, ink: Ink, upTo: number) {
  const { pts, cum } = ink;
  ctx.beginPath();
  ctx.moveTo(pts[0][0], pts[0][1]);
  for (let i = 1; i < pts.length; i++) {
    if (cum[i] <= upTo) {
      ctx.lineTo(pts[i][0], pts[i][1]);
      continue;
    }
    const seg = cum[i] - cum[i - 1];
    const t = seg > 0 ? (upTo - cum[i - 1]) / seg : 0;
    ctx.lineTo(pts[i - 1][0] + (pts[i][0] - pts[i - 1][0]) * t, pts[i - 1][1] + (pts[i][1] - pts[i - 1][1]) * t);
    break;
  }
  ctx.stroke();
}

/** Paint every stroke on screen for this frame: the ghosts, then the
 *  highlighter, then the ink, with the camera as the canvas transform.
 *
 *  The ink is a canvas, not SVG paths, because of what it costs in software
 *  GL. A hand-drawn stroke is a many-segment polyline, and Chrome drew each
 *  one as an SVG path far slower than a simple shape: six faint ghost strokes
 *  alone took a 150-frame render from 26 to 51 CPU seconds (straight lines of
 *  the same length cost almost nothing), and the whole scene cost 1.7x System
 *  Flow. Drawn here, it costs 1.1x (48 against 43 CPU seconds for the same 150
 *  frames, CPU time of every process, swangle, concurrency 2). */
function paintInk(ctx: CanvasRenderingContext2D, cam: Cam, ghostInks: Ink[], visible: Drawn[], frame: number) {
  ctx.setTransform(1, 0, 0, 1, 0, 0);
  ctx.clearRect(0, 0, W, H);
  ctx.setTransform(cam.z, 0, 0, cam.z, W / 2 - cam.x * cam.z, cam.sy - cam.y * cam.z);
  ctx.lineJoin = "round";
  ctx.lineCap = "round";
  ctx.strokeStyle = GHOST;
  ctx.lineWidth = 12;
  for (const g of ghostInks) strokeInk(ctx, g, Infinity);
  for (const under of [true, false]) {
    for (const d of visible) {
      if (d.under !== under) continue;
      let left = progress(d, frame).ps * d.total;
      ctx.strokeStyle = d.color;
      ctx.lineWidth = d.width;
      ctx.lineCap = d.under ? "butt" : "round";
      for (const st of d.strokes) {
        if (left <= 0) break;
        strokeInk(ctx, st, left);
        left -= st.len;
      }
    }
  }
}

// ── the scene ─────────────────────────────────────────────────────────────────
export default function Whiteboard({ whiteboard }: { whiteboard?: WhiteboardData; durationInFrames: number }) {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const [handle] = useState(() => delayRender("Whiteboard: loading the bundled font"));
  useEffect(() => {
    loadFont()
      .then(() => continueRender(handle))
      .catch((err) => {
        // A bundled font that will not load means a broken image; render with
        // the fallback rather than hang, and say so in the render log.
        console.error("Whiteboard: font load failed", err);
        continueRender(handle);
      });
  }, [handle]);

  const data: WhiteboardData = whiteboard ?? { regions: [], recapFrame: 0 };
  // The props are static for the whole render.
  const drawn = useMemo(() => prepare(data), [whiteboard]); // eslint-disable-line react-hooks/exhaustive-deps
  const ghostInks = useMemo(() => ghostStrokes(data.regions.length), [whiteboard]); // eslint-disable-line react-hooks/exhaustive-deps
  const cam = cameraAt(data, frame);
  const visible = drawn.filter((d) => frame >= d.s.start);

  const canvasRef = useRef<HTMLCanvasElement>(null);
  useLayoutEffect(() => {
    const ctx = canvasRef.current?.getContext("2d");
    if (ctx) paintInk(ctx, cam, ghostInks, visible, frame);
  });

  if (!data.regions.length) return <AbsoluteFill style={{ background: BOARD_COLOR }} />;

  // Recap: a circled number pops onto each region.
  const numberAt = (i: number) => data.recapFrame + TIMING.recapPull + i * TIMING.recapNumberStep;
  const pen = penAt(drawn, frame, cam);

  return (
    <AbsoluteFill style={{ background: BOARD_COLOR, width: W, height: H, overflow: "hidden" }}>
      <canvas ref={canvasRef} width={W} height={H} style={{ position: "absolute", left: 0, top: 0 }} />
      {frame >= numberAt(0) ? (
        <svg width={W} height={H} style={{ position: "absolute", left: 0, top: 0 }}>
          <g transform={svgTransform(cam)}>
            {data.regions.map((_, i) => {
              const f = frame - numberAt(i);
              if (f < 0) return null;
              const [x, y] = regionOrigin(i);
              const s = spring({ frame: f, fps, config: { stiffness: 200, damping: 20, mass: 0.8 } });
              return (
                <g key={i} transform={`translate(${x - 70} ${y - 70}) scale(${(0.6 + 0.4 * s).toFixed(3)})`} opacity={s * 3 < 1 ? s * 3 : undefined}>
                  <circle r={62} fill="none" stroke={INKS.orange} strokeWidth={12} />
                  <text textAnchor="middle" y={34} fontFamily={HAND} fontWeight={700} fontSize={100} fill={INKS.black}>
                    {i + 1}
                  </text>
                </g>
              );
            })}
          </g>
        </svg>
      ) : null}
      {visible.map((d) => {
        if (!d.lines.length) return null;
        const rev = lineReveal(d, progress(d, frame).pt);
        return d.lines.map((l, k) => {
          if (rev[k] <= 0) return null;
          const [sx, sy] = toScreen(cam, l.x, l.y);
          return (
            <div
              key={`${d.s.region}:${d.s.item.id}:${k}`}
              style={{
                position: "absolute",
                left: sx,
                top: sy,
                fontFamily: HAND,
                fontWeight: 700,
                fontSize: l.size * cam.z,
                lineHeight: SIZES.lineHeight,
                whiteSpace: "nowrap",
                color: d.color,
                // Negative insets keep the ascenders and descenders, which
                // overflow the line box.
                clipPath: rev[k] < 1 ? `inset(-40% ${((1 - rev[k]) * 100).toFixed(2)}% -40% -10%)` : undefined,
              }}
            >
              {l.text}
            </div>
          );
        });
      })}
      {pen ? (
        <svg width={W} height={H} style={{ position: "absolute", left: 0, top: 0 }}>
          <Pen p={pen} scale={Math.max(0.62, Math.min(1, cam.z))} />
        </svg>
      ) : null}
    </AbsoluteFill>
  );
}
