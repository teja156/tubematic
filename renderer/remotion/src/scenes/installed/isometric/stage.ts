/*
 * What the Isometric Infographic scene shows at a frame: which board, where
 * the camera is, how far each prop has dropped in, each route has drawn, each
 * mover has travelled, each pin has built, what is lifted, cut away or
 * exploded, and what the readout reads. Pure functions, so vitest can pin them
 * without a browser; mcp/isometric_infographic.py mirrors the ones the checks
 * need.
 */
import { BOARD, GEOMETRY, TIMING, eventFrames, type Board, type IsometricData, type PropItem } from "./contract";

export const clamp01 = (v: number) => Math.max(0, Math.min(1, v));
export const easeInOut = (t: number) => {
  const x = clamp01(t);
  return x < 0.5 ? 4 * x * x * x : 1 - (-2 * x + 2) ** 3 / 2;
};
export const easeOutBack = (t: number) => {
  const x = clamp01(t);
  const c1 = 1.70158, c3 = c1 + 1;
  return 1 + c3 * (x - 1) ** 3 + c1 * (x - 1) ** 2;
};
export const ramp = (frame: number, at: number, frames: number) => (frames <= 0 ? (frame >= at ? 1 : 0) : clamp01((frame - at) / frames));

export function boardIndexAt(data: IsometricData, frame: number): number {
  let idx = 0;
  data.boards.forEach((b, i) => {
    if (frame >= b.start) idx = i;
  });
  return idx;
}

export function boardEnd(data: IsometricData, i: number, total: number): number {
  return i + 1 < data.boards.length ? data.boards[i + 1].start : total;
}

export type View = { x: number; y: number; zoom: number };
/** The whole board's centre, in tiles. */
export const WHOLE: View = { x: BOARD / 2, y: BOARD / 2, zoom: 1 };

const lerpView = (a: View, b: View, k: number): View => ({
  x: a.x + (b.x - a.x) * k, y: a.y + (b.y - a.y) * k, zoom: a.zoom + (b.zoom - a.zoom) * k,
});

/** Where the camera looks at a frame: each move eases over TIMING.glide frames from wherever the camera is when it starts. */
export function viewAt(b: Board, frame: number): View {
  const moves = (b.camera ?? []).filter((c) => c.at <= frame);
  let from: View = WHOLE;
  let cur: View = WHOLE;
  let at = b.start;
  for (const m of moves) {
    // a move that starts while the last one still glides starts from the view on screen, so the camera never jumps
    from = lerpView(from, cur, easeInOut(ramp(m.at, at, TIMING.glide)));
    const p = m.focus ? b.props.find((q) => q.id === m.focus) : undefined;
    cur = p ? { x: p.at[0], y: p.at[1], zoom: m.zoom ?? 1.5 } : { ...WHOLE, zoom: m.zoom ?? 1 };
    at = m.at;
  }
  return lerpView(from, cur, easeInOut(ramp(frame, at, TIMING.glide)));
}

/** The projection a view gives: tile size and the screen point of tile (0, 0). */
export function projAt(v: View): { k: number; cx: number; cy: number } {
  const G = GEOMETRY;
  const k = G.k * v.zoom;
  // the screen point of the view's centre stays where the board's centre is at zoom 1
  const C30 = Math.cos(Math.PI / 6);
  const centreX = G.cx, centreY = G.cy + (BOARD / 2) * G.k;
  return { k, cx: centreX - (v.x - v.y) * C30 * k, cy: centreY - (v.x + v.y) * 0.5 * k };
}

/** A prop's drop: how high above its tile it still is (tiles) and its squash (0 at rest). */
export function dropAt(p: PropItem, frame: number): { lift: number; squash: number; visible: boolean } {
  if (p.enter === undefined) return { lift: 0, squash: 0, visible: true };
  if (frame < p.enter - TIMING.drop) return { lift: 0, squash: 0, visible: false };
  const fall = 1 - ramp(frame, p.enter - TIMING.drop, TIMING.drop);
  const it = frame - p.enter;
  const squash = it >= 0 ? 0.18 * Math.exp(-it / 4.5) * Math.cos(it * 0.62) : 0;
  return { lift: fall * fall * 2.4, squash, visible: true };
}

/** How far a lift, a cutaway or an explode on a prop has gone at a frame (0..1), or 0. */
export function effectAt(list: { prop: string; at: number }[] | undefined, id: string, frame: number, frames: number): number {
  // the latest one that has started, whatever order the config lists them in
  const e = (list ?? []).filter((x) => x.prop === id && x.at <= frame).reduce<{ at: number } | undefined>((a, x) => (!a || x.at >= a.at ? x : a), undefined);
  return e ? easeInOut(ramp(frame, e.at, frames)) : 0;
}

/** How far the stepping back of every other prop has gone: the strongest running lift. */
export function dimAt(b: Board, frame: number): { prop: string | null; amount: number } {
  // the latest lift that has started, whatever order the config lists them in
  const last = (b.lifts ?? []).filter((l) => l.at <= frame).reduce<{ prop: string; at: number } | undefined>(
    (a, l) => (!a || l.at >= a.at ? l : a), undefined);
  return last ? { prop: last.prop, amount: easeInOut(ramp(frame, last.at, TIMING.lift)) } : { prop: null, amount: 0 };
}

/** A polyline's cumulative lengths. */
export function lengths(pts: [number, number][]): number[] {
  const acc = [0];
  for (let i = 1; i < pts.length; i++) acc.push(acc[i - 1] + Math.hypot(pts[i][0] - pts[i - 1][0], pts[i][1] - pts[i - 1][1]));
  return acc;
}

export function pointAt(pts: [number, number][], acc: number[], s: number): [number, number] {
  const total = acc[acc.length - 1];
  const d = Math.max(0, Math.min(total, s));
  for (let i = 1; i < pts.length; i++) {
    if (d <= acc[i] || i === pts.length - 1) {
      const u = (d - acc[i - 1]) / Math.max(1e-6, acc[i] - acc[i - 1]);
      return [pts[i - 1][0] + (pts[i][0] - pts[i - 1][0]) * u, pts[i - 1][1] + (pts[i][1] - pts[i - 1][1]) * u];
    }
  }
  return pts[pts.length - 1];
}

/** The readout's value at a frame: rolling from the last step to the current one over TIMING.roll frames. */
export function readoutAt(data: IsometricData, frame: number): { value: number; red: boolean; shown: boolean } {
  const steps = data.readout?.steps ?? [];
  let i = -1;
  steps.forEach((s, k) => {
    if (frame >= s.at) i = k;
  });
  if (i < 0) return { value: 0, red: false, shown: false };
  const from = i === 0 ? 0 : steps[i - 1].value;
  return { value: from + (steps[i].value - from) * easeInOut(ramp(frame, steps[i].at, TIMING.roll)), red: !!steps[i].red, shown: true };
}

/**
 * The stretches in which nothing new happens apart from the drift and the
 * things already moving, as [from, to] frames: between a board's events (and
 * the readout steps and the legend that fall on it) and to its end.
 */
export function quietSpans(data: IsometricData, total: number): [number, number][] {
  const spans: [number, number][] = [];
  const extra = [...(data.readout?.steps ?? []).map((s) => s.at), ...(data.legend ? [data.legend.at] : [])];
  data.boards.forEach((b, i) => {
    const end = boardEnd(data, i, total);
    const frames = [...new Set([...eventFrames(b), ...extra.filter((f) => f >= b.start && f < end)])].sort((a, c) => a - c);
    frames.push(end);
    for (let k = 1; k < frames.length; k++) spans.push([frames[k - 1], frames[k]]);
  });
  return spans;
}
