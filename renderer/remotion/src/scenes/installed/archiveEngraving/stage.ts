/*
 * Where everything on an Archive and Engraving page is at a frame. Pure
 * functions of the data and the frame, so the component draws nothing it has
 * to remember and the MCP server's checks (mcp/archive_engraving.py) can
 * mirror the geometry: titleLayout, pushScale, plateView, toWindow and
 * rulerScale run the same shared cases on both sides.
 */
import { TIMING, TITLE_CHAR_W, TITLE_SIZES, W, H, ZONES, type ArchiveEvent, type Beat, type UV } from "./contract";

export const clamp01 = (v: number) => Math.max(0, Math.min(1, v));
export const easeInOut = (t: number) => (t < 0.5 ? 2 * t * t : 1 - (-2 * t + 2) ** 2 / 2);
export const easeOut = (t: number) => 1 - (1 - clamp01(t)) ** 3;

export function beatIndexAt(beats: Beat[], frame: number): number {
  let index = 0;
  beats.forEach((b, i) => {
    if (frame >= b.start) index = i;
  });
  return index;
}

export function beatEnd(beats: Beat[], i: number, total: number): number {
  return i + 1 < beats.length ? beats[i + 1].start : total;
}

/** A title word as the agent names it: lower case, letters, digits and hyphens only. */
export function cleanWord(w: string): string {
  return Array.from(w.toLowerCase()).filter((c) => /[\p{L}\p{N}-]/u.test(c)).join("");
}

/** The title's font size and its lines: the largest size whose greedy word wrap
 *  fits two lines of ZONES.titleWidth. A title that fits no size comes back with
 *  more than two lines (the server refuses it). */
export function titleLayout(text: string): { size: number; lines: string[] } {
  const words = text.split(/\s+/).filter(Boolean);
  let lines: string[] = [];
  let size: number = TITLE_SIZES[0];
  for (const s of TITLE_SIZES) {
    size = s;
    const fits = (t: string) => t.length * s * TITLE_CHAR_W <= ZONES.titleWidth;
    lines = [];
    let cur = "";
    for (const w of words) {
      const cand = cur ? `${cur} ${w}` : w;
      if (fits(cand)) cur = cand;
      else {
        if (cur) lines.push(cur);
        cur = w;
      }
    }
    if (cur) lines.push(cur);
    if (lines.length <= 2 && lines.every(fits)) return { size, lines };
  }
  return { size, lines };
}

/** A plate's slow push: 1 at the beat's start to 1 + TIMING.push at its end. */
export function pushScale(frame: number, start: number, end: number): number {
  return 1 + TIMING.push * clamp01((frame - start) / Math.max(1, end - start));
}

/**
 * The part of a still on screen in the plate window at `scale` about `focus`,
 * as [x, y, width, height] in still pixels. A still is laid out as a W x H
 * frame (cover-fitted), so [u, v] is u * W, v * H; the view keeps the
 * window's shape and stays inside the still.
 */
export function plateView(scale: number, focus: UV = [0.5, 0.5]): [number, number, number, number] {
  const s = Math.max(1, scale);
  const vw = W / s;
  const vh = (vw * ZONES.winH) / ZONES.winW;
  const x = Math.min(W - vw, Math.max(0, focus[0] * W - vw / 2));
  const y = Math.min(H - vh, Math.max(0, focus[1] * H - vh / 2));
  return [x, y, vw, vh];
}

/** Where a point of the still lands on the page, through the window's view. */
export function toWindow(view: [number, number, number, number], p: UV): [number, number] {
  const [x, y, vw, vh] = view;
  return [ZONES.winLeft + ((p[0] * W - x) / vw) * ZONES.winW, ZONES.winTop + ((p[1] * H - y) / vh) * ZONES.winH];
}

export const RULER_STEPS = [1, 2, 5, 10, 20, 25, 50, 100, 200, 500] as const;

/** The ruler's first and last labelled year and its step, from every year the
 *  video's timeline events name, or null when no step keeps it to maxTicks. */
export function rulerScale(years: number[], maxTicks: number = 8): { start: number; end: number; step: number } | null {
  if (!years.length) return null;
  const lo = Math.min(...years), hi = Math.max(...years);
  for (const step of RULER_STEPS) {
    const start = Math.floor(lo / step) * step - step;
    const end = Math.ceil(hi / step) * step + step;
    if ((end - start) / step + 1 <= maxTicks) return { start, end, step };
  }
  return null;
}

export function rulerX(year: number, scale: { start: number; end: number }): number {
  return ZONES.rulerLeft + ((year - scale.start) / Math.max(1, scale.end - scale.start)) * (ZONES.rulerRight - ZONES.rulerLeft);
}

/** The year the ruler's marker shows at a frame, or null before the first timeline event. */
export function rulerMarker(events: ArchiveEvent[], frame: number): number | null {
  const fired = events.filter((e) => e.do === "timeline" && e.at <= frame).sort((a, b) => a.at - b.at);
  const e = fired[fired.length - 1];
  if (!e || e.from === undefined || e.to === undefined) return null;
  return e.from + (e.to - e.from) * easeInOut(clamp01((frame - e.at) / TIMING.timeline));
}

/** Points every `gap` pixels along a polyline, as far as `progress` (0 to 1) has drawn it. */
export function dotsAlong(points: [number, number][], progress: number, gap = 22): [number, number][] {
  if (points.length < 2) return [];
  const segs = points.slice(1).map((p, i) => Math.hypot(p[0] - points[i][0], p[1] - points[i][1]));
  const total = segs.reduce((a, b) => a + b, 0);
  const upto = total * clamp01(progress);
  const out: [number, number][] = [];
  for (let d = 0; d <= upto + 1e-6; d += gap) {
    let rest = d, k = 0;
    while (k < segs.length - 1 && rest > segs[k]) {
      rest -= segs[k];
      k++;
    }
    const t = segs[k] > 0 ? Math.min(1, rest / segs[k]) : 0;
    out.push([points[k][0] + (points[k + 1][0] - points[k][0]) * t, points[k][1] + (points[k + 1][1] - points[k][1]) * t]);
  }
  return out;
}

/** How many characters of a document line are written at a frame. */
export function writtenChars(text: string, at: number, frame: number, hand: boolean): number {
  if (frame < at) return 0;
  return Math.min(text.length, Math.floor((frame - at + 1) * (hand ? TIMING.handRate : TIMING.typeRate)));
}

/** A document card's font size: the largest up to 46 (50 by hand) at which the
 *  longest line fits the card's inner width. */
export function documentSize(lines: string[], hand: boolean): number {
  const longest = Math.max(1, ...lines.map((l) => l.length));
  const charW = hand ? 0.56 : 0.5;
  return Math.max(28, Math.min(hand ? 50 : 46, Math.floor(760 / (longest * charW))));
}

/** The boxes of a `people` row: [left, width] for each of n cards. */
export function peopleBoxes(n: number): [number, number][] {
  const gap = 36;
  const width = (ZONES.cardRight - ZONES.cardLeft - gap * (n - 1)) / n;
  return Array.from({ length: n }, (_, i) => [ZONES.cardLeft + i * (width + gap), width]);
}

/** Whether a magnifying roundel for `point` flies to the window's right side
 *  (it goes to the side away from the point, so the point stays in view). */
export function magnifierOnRight(view: [number, number, number, number], point: UV): boolean {
  return toWindow(view, point)[0] <= W / 2;
}
