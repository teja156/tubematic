/*
 * Where everything on an Editorial Collage desk is at a frame. Pure functions
 * of the data and the frame, so the component draws nothing it has to
 * remember and the MCP server's checks (mcp/editorial_collage.py) can mirror
 * them: stationCenter, cameraAt, stepped, headlineLayout, typedChars,
 * typeFrames and figureText run the same shared cases on both sides.
 */
import {
  DESK, HEADLINE, KICKER_H, TIMING, ZONES,
  type CollageEvent, type HeadlineLayoutKind, type Hero, type Station,
} from "./contract";

export const clamp01 = (v: number) => Math.max(0, Math.min(1, v));
export const easeInOutSine = (t: number) => -(Math.cos(Math.PI * clamp01(t)) - 1) / 2;
export const easeOut = (t: number) => 1 - (1 - clamp01(t)) ** 3;
export const quartOut = (t: number) => 1 - (1 - clamp01(t)) ** 4;

/** A frame count held on twelve steps a second: pieces move only when this changes. */
export function stepped(frame: number): number {
  return Math.floor(frame / TIMING.step) * TIMING.step;
}

export function stationIndexAt(stations: Station[], frame: number): number {
  let index = 0;
  stations.forEach((s, i) => {
    if (frame >= s.start) index = i;
  });
  return index;
}

export function stationEnd(stations: Station[], i: number, total: number): number {
  return i + 1 < stations.length ? stations[i + 1].start : total;
}

/** The desk point the camera rests on for station i: a zig-zag down the desk. */
export function stationCenter(i: number): [number, number] {
  return [i % 2 === 1 ? DESK.dx : 0, i * DESK.dy];
}

/** How far the glide into the station starting at `start` has gone, 0 to 1. */
export function glideProgress(start: number, frame: number): number {
  return easeInOutSine((frame - start) / TIMING.glide);
}

/** The desk point at the centre of the frame: still on a station, gliding
 *  (easeInOutSine over TIMING.glide frames) from the previous one after a
 *  station starts. The camera never scales. */
export function cameraAt(starts: number[], frame: number): [number, number] {
  let k = 0;
  starts.forEach((s, i) => {
    if (frame >= s) k = i;
  });
  const to = stationCenter(k);
  if (k === 0) return to;
  const from = stationCenter(k - 1);
  const t = glideProgress(starts[k], frame);
  return [from[0] + (to[0] - from[0]) * t, from[1] + (to[1] - from[1]) * t];
}

/** Whether the camera is moving at this frame. */
export function gliding(starts: number[], frame: number): boolean {
  return starts.some((s, i) => i > 0 && frame >= s && frame < s + TIMING.glide);
}

/** A headline word as the agent names it: lower case, letters, digits and hyphens only. */
export function cleanWord(w: string): string {
  return Array.from(w.toLowerCase()).filter((c) => /[\p{L}\p{N}-]/u.test(c)).join("");
}

/** Which layout a headline takes: a black card with no hero fills both zones. */
export function layoutKind(kind: string, hasHero: boolean): HeadlineLayoutKind {
  return kind === "black" && !hasHero ? "blackFull" : (kind as HeadlineLayoutKind);
}

/** The headline's font size and lines: the largest size whose greedy word wrap
 *  fits the kind's width, its most lines and its zone's height. A headline
 *  that fits no size comes back with `fits` false (the server refuses it). */
export function headlineLayout(text: string, kind: HeadlineLayoutKind, kicker: boolean): { size: number; lines: string[]; fits: boolean } {
  const spec = HEADLINE[kind];
  const words = text.split(/\s+/).filter(Boolean);
  const room = spec.zone - 2 * spec.pad - (kicker ? KICKER_H : 0);
  let lines: string[] = [];
  let size: number = spec.sizes[0];
  for (const s of spec.sizes) {
    size = s;
    const fits = (t: string) => t.length * s * spec.charW <= spec.width;
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
    if (lines.length <= spec.maxLines && lines.every(fits) && lines.length * s * spec.line <= room) {
      return { size, lines, fits: true };
    }
  }
  return { size, lines, fits: false };
}

/** How many characters of an index line are typed at a frame: 13 a second, on twos. */
export function typedChars(text: string, at: number, frame: number): number {
  if (frame < at) return 0;
  const age = Math.floor((frame - at) / 2) * 2;
  return Math.min(text.length, Math.floor((age * TIMING.typeRate) / 30) + 1);
}

/** The frames an index line takes to type out in full. */
export function typeFrames(text: string): number {
  let age = 0;
  while (Math.floor((age * TIMING.typeRate) / 30) + 1 < text.length) age += 2;
  return age;
}

/** How many decimals a figure shows: as many as its value has, at most 2. */
export function decimalsOf(value: number): number {
  for (const d of [0, 1]) {
    if (Math.abs(Math.round(value * 10 ** d) / 10 ** d - value) < 1e-9) return d;
  }
  return 2;
}

function grouped(n: number, decimals: number): string {
  const [whole, frac] = n.toFixed(decimals).split(".");
  const digits = whole.replace(/\B(?=(\d{3})+(?!\d))/g, ",");
  return frac ? `${digits}.${frac}` : digits;
}

/** The figure's text when it has counted `k` (0 to 1) of the way up: the value
 *  floored to its own decimals, grouped in thousands, between its prefix and
 *  suffix (a suffix that starts with a word of three letters or more, such as
 *  "hours", gets a space before it; "%", "x" or "M" does not). */
export function figureText(value: number, prefix = "", suffix = "", k = 1): string {
  const d = decimalsOf(value);
  const shown = k >= 1 ? value : Math.floor(value * clamp01(k) * 10 ** d + 1e-9) / 10 ** d;
  const space = /^\p{L}{3}/u.test(suffix) ? " " : "";
  return `${prefix}${grouped(shown, d)}${space}${suffix}`;
}

/** How far a figure has counted at a frame: 0 before countAt, then over TIMING.count frames on twos. */
export function countProgress(countAt: number, frame: number): number {
  if (frame < countAt) return 0;
  return easeOut(stepped(frame - countAt) / TIMING.count);
}

/** A landing piece's scale: a little large, a small undershoot, then still. */
export function landScale(age: number, dur: number, from = 1.16): number {
  const t = clamp01(age / dur);
  if (t < 0.6) return from - (from - 0.96) * (t / 0.6);
  return 0.96 + 0.04 * ((t - 0.6) / 0.4);
}

/** A small deterministic random sequence (mulberry32). */
export function seeded(seed: number): () => number {
  let a = seed >>> 0;
  return () => {
    a = (a + 0x6d2b79f5) >>> 0;
    let t = a;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

/** A print's tilt in degrees, from the station's and the item's number. */
export function tiltOf(station: number, item = 0): number {
  return (seeded(station * 131 + item * 17 + 7)() * 2 - 1) * TIMING.tilt;
}

/** A one-stroke pen ellipse whose ends overshoot and do not close, as points. */
export function penEllipse(cx: number, cy: number, rx: number, ry: number, seed: number): [number, number][] {
  const r = seeded(seed);
  const p1 = r() * 6, p2 = r() * 6;
  const a0 = (200 * Math.PI) / 180, sweep = (385 * Math.PI) / 180, n = 72;
  const pts: [number, number][] = [];
  for (let i = 0; i <= n; i++) {
    const t = i / n, a = a0 + sweep * t;
    const grow = 1 + 0.07 * t + 0.025 * Math.sin(3 * a + p1);
    pts.push([cx + Math.cos(a) * rx * grow + Math.sin(5 * a + p2) * 3, cy + Math.sin(a) * ry * grow - t * 10]);
  }
  return pts;
}

/** The first `progress` (0 to 1) of a polyline, by count of points. */
export function upTo(points: [number, number][], progress: number): [number, number][] {
  const n = Math.round(clamp01(progress) * (points.length - 1));
  return progress <= 0 ? [] : points.slice(0, n + 1);
}

/** A string pinned at a and b that sags under its own weight, as points. */
export function stringPoints(a: [number, number], b: [number, number], n = 40): [number, number][] {
  const len = Math.hypot(b[0] - a[0], b[1] - a[1]);
  const sag = 0.16 * len;
  // gravity pulls the middle down; on a steep string the sag shows sideways, away from the desk's middle
  const side = b[0] >= a[0] ? -1 : 1;
  const steep = Math.abs(b[1] - a[1]) / Math.max(1, len);
  const pts: [number, number][] = [];
  for (let i = 0; i <= n; i++) {
    const t = i / n, bow = Math.sin(Math.PI * t) * sag;
    pts.push([a[0] + (b[0] - a[0]) * t + side * bow * steep * 0.6, a[1] + (b[1] - a[1]) * t + bow * (1 - steep * 0.6)]);
  }
  return pts;
}

/** Where a picture of aspect `aspect` (width / height) sits when fitted into a
 *  w x h box centred on (cx, cy): [x, y, width, height]. */
export function fitBox(aspect: number, cx: number, cy: number, w: number, h: number): [number, number, number, number] {
  const a = aspect > 0 ? aspect : 1;
  const fw = Math.min(w, h * a), fh = fw / a;
  return [cx - fw / 2, cy - fh / 2, fw, fh];
}

export const PRINT_BOX = { w: 760, h: 600, captionH: 66 } as const;
export const STICKER_BOX = { w: 700, h: 600 } as const;
export const INDEX = { width: 820, head: 96, foot: 60 } as const;

/** An index card's type size and line height, from its longest line. */
export function indexSize(lines: string[]): { size: number; lineH: number } {
  const longest = Math.max(1, ...lines.map((l) => l.length));
  const size = Math.max(30, Math.min(62, Math.floor((INDEX.width - 110) / (longest * 0.56))));
  return { size, lineH: Math.round(size * 1.55) };
}

/** A figure's type size, from its final text. */
export function figureSize(text: string): number {
  return Math.max(48, Math.min(230, Math.floor(780 / (Math.max(1, text.length) * 0.6))));
}

/** The hero's box on the station, in frame pixels at rest: what a circle goes
 *  round, a stamp lands on and an arrow points at. `aspects` holds each
 *  picture's width / height as loaded. */
export function heroBox(hero: Hero | undefined, aspects: Record<string, number>): [number, number, number, number] {
  const cx = (ZONES.left + ZONES.right) / 2, cy = ZONES.heroCenterY;
  if (!hero) return [ZONES.left + 60, ZONES.headTop, ZONES.right - ZONES.left - 120, ZONES.heroBottom - ZONES.headTop];
  if (hero.kind === "print") {
    const cap = hero.caption ? PRINT_BOX.captionH : 0;
    return fitBox(aspects[hero.image] ?? 0.5625, cx, cy - cap / 2, PRINT_BOX.w, PRINT_BOX.h - cap);
  }
  if (hero.kind === "sticker") return fitBox(aspects[hero.image] ?? 1, cx, cy, STICKER_BOX.w, STICKER_BOX.h);
  if (hero.kind === "index") {
    const { lineH } = indexSize(hero.lines.map((l) => l.text));
    const h = INDEX.head + hero.lines.length * lineH + INDEX.foot;
    return [cx - INDEX.width / 2, cy - h / 2, INDEX.width, h];
  }
  if (hero.kind === "figure") {
    const size = figureSize(figureText(hero.value, hero.prefix, hero.suffix));
    const h = size * 1.2 + 40 + 100;
    return [ZONES.left + 30, cy - h / 2, ZONES.right - ZONES.left - 60, h];
  }
  const n = hero.items.length;
  return [ZONES.left, cy - 250 - (n === 2 ? 30 : 0), ZONES.right - ZONES.left, 500 + (n === 2 ? 60 : 0)];
}

/** The cells of a stack hero: [cx, cy, w, h] for each of n items. */
export function stackCells(n: number): [number, number, number, number][] {
  const gap = 24;
  const w = (ZONES.right - ZONES.left - gap * (n - 1)) / n;
  const h = n === 2 ? 520 : 440;
  return Array.from({ length: n }, (_, i) => [ZONES.left + w / 2 + i * (w + gap), ZONES.heroCenterY + (i % 2 ? 26 : -26), w, h]);
}

/** Events of a station that have started by a frame. */
export function fired(events: CollageEvent[] | undefined, frame: number): CollageEvent[] {
  return (events ?? []).filter((e) => e.at <= frame);
}
