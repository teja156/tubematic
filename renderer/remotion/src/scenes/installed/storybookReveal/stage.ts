/*
 * Where everything on a Storybook Reveal page is at a frame. Pure functions of
 * the data and the frame, so the component draws nothing it has to remember
 * and the MCP server's checks (mcp/storybook_reveal.py) can mirror them:
 * titleSize, pictureBox, pushScale and landFrame run the same shared cases on
 * both sides.
 */
import { H, TIMING, TITLE_CHAR_W, TITLE_SIZES, W, ZONES, type Page, type UV } from "./contract";

export type Pt = [number, number];

export const clamp01 = (v: number) => Math.max(0, Math.min(1, v));
export const smooth = (t: number) => {
  const x = clamp01(t);
  return x * x * (3 - 2 * x);
};
export const easeInOut = (t: number) => {
  const x = clamp01(t);
  return x < 0.5 ? 2 * x * x : 1 - (-2 * x + 2) ** 2 / 2;
};

export function pageIndexAt(pages: Page[], frame: number): number {
  let index = 0;
  pages.forEach((p, i) => {
    if (frame >= p.start) index = i;
  });
  return index;
}

export function pageEnd(pages: Page[], i: number, total: number): number {
  return i + 1 < pages.length ? pages[i + 1].start : total;
}

/** The title's font size: the largest up to TITLE_SIZES[0] at which it fits
 *  ZONES.titleWidth on one line, never under TITLE_SIZES[1]. */
export function titleSize(text: string): number {
  const n = Math.max(1, text.trim().length);
  return Math.max(TITLE_SIZES[1], Math.min(TITLE_SIZES[0], Math.floor(ZONES.titleWidth / (n * TITLE_CHAR_W))));
}

/** A still contain-fitted in the panel, as [x, y, width, height] in panel
 *  pixels: the whole picture, centred, never cropped. */
export function pictureBox(imgW: number, imgH: number): [number, number, number, number] {
  const s = Math.min(ZONES.panelWidth / imgW, ZONES.panelHeight / imgH);
  const w = imgW * s, h = imgH * s;
  return [(ZONES.panelWidth - w) / 2, (ZONES.panelHeight - h) / 2, w, h];
}

/** The frame a page's colour has finished flooding. */
export function landFrame(page: Pick<Page, "colourAt">): number {
  return page.colourAt + TIMING.colour;
}

/** The slow push: 1 until the colour lands, then easing to 1 + TIMING.push at the page's end. */
export function pushScale(frame: number, land: number, end: number): number {
  return 1 + TIMING.push * easeInOut((frame - land) / Math.max(1, end - land));
}

/** The picture's box at a push `scale`, grown about its `focus` point: the
 *  point of the still at `focus` stays where it was. */
export function pushedBox(box: [number, number, number, number], scale: number, focus: UV = [0.5, 0.5]): [number, number, number, number] {
  const [x, y, w, h] = box;
  const ax = x + focus[0] * w, ay = y + focus[1] * h;
  return [ax - focus[0] * w * scale, ay - focus[1] * h * scale, w * scale, h * scale];
}

/** How much of the pencil plate is drawn (0 to 1). A first page whose pencil
 *  is at its start (frame 0) is drawn whole from that frame. */
export function pencilProgress(page: Page, first: boolean, frame: number): number {
  if (first && page.pencilAt === page.start) return frame >= page.start ? 1 : 0;
  return clamp01((frame - page.pencilAt) / TIMING.pencil);
}

/** How much of the title is wiped in (0 to 1). The first page's title is whole from frame 0. */
export function titleProgress(page: Page, first: boolean, frame: number): number {
  return first ? 1 : clamp01((frame - page.start) / TIMING.title);
}

/** A small deterministic random sequence (mulberry32). */
export function rng(seed: number): () => number {
  let a = seed >>> 0;
  return () => {
    a = (a + 0x6d2b79f5) >>> 0;
    let t = a;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

// How far the flood's front wanders either side of its line, in pixels, and
// how far ahead its faintest edge reaches.
export const FLOOD_WAVE = 26;
export const FLOOD_SOFT = 48;

/**
 * The colour flood's front at progress k (0 to 1), crossing a box `w` wide and
 * `h` tall from left to right: a wavy, slightly ragged line from top to bottom,
 * as points. The flooded region is everything left of it. Its waves drift a
 * little as it moves, like a wash finding its way through the paper. At k = 0
 * every point is left of the box, at k = 1 right of it, even `ahead` pixels
 * further right (the soft edge is the same front drawn several times, ahead
 * and fainter).
 */
export function floodFront(k: number, w: number, h: number, seed: number, ahead = 0): Pt[] {
  const r = rng(seed);
  const ph = [r() * 6.28, r() * 6.28, r() * 6.28];
  const margin = FLOOD_WAVE + FLOOD_SOFT + 24;
  const x0 = -margin + easeInOut(k) * (w + 2 * margin) + ahead;
  const out: Pt[] = [];
  for (let y = -20; y <= h + 20; y += 14) {
    const t = y / h;
    const wave = 0.55 * Math.sin(6.28 * 1.3 * t + ph[0] + 2.2 * k) + 0.3 * Math.sin(6.28 * 3.1 * t + ph[1] - 1.4 * k)
      + 0.15 * Math.sin(6.28 * 7.3 * t + ph[2]);
    out.push([x0 + FLOOD_WAVE * wave + (r() - 0.5) * 5, y]);
  }
  return out;
}

/** The flooded region left of a floodFront, as a closed polygon. */
export function floodPolygon(front: Pt[]): Pt[] {
  const top = front[0][1], bottom = front[front.length - 1][1];
  return [[-400, top], ...front, [-400, bottom]];
}

// ── the page curl ────────────────────────────────────────────────────────────
// The old page folds back from its bottom-right corner along a line at right
// angles to the page's diagonal. s is how far the fold has travelled from the
// corner, along the diagonal, in pixels.
const DIAG = Math.hypot(W, H);
const U: Pt = [-W / DIAG, -H / DIAG];
const along = (p: Pt) => (p[0] - W) * U[0] + (p[1] - H) * U[1];
// the turned flap is foreshortened, so it reads as a rolling page
const CURL_K = 0.42;
const PAGE: Pt[] = [[0, 0], [W, 0], [W, H], [0, H]];

function clipHalf(poly: Pt[], keep: (p: Pt) => number): Pt[] {
  const out: Pt[] = [];
  for (let i = 0; i < poly.length; i++) {
    const a = poly[i], b = poly[(i + 1) % poly.length];
    const ka = keep(a), kb = keep(b);
    if (ka >= 0) out.push(a);
    if ((ka >= 0) !== (kb >= 0)) {
      const t = ka / (ka - kb);
      out.push([a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t]);
    }
  }
  return out;
}

/** The fold's travel at a frame of a curl that starts at `start` (0 before, past the far corner after). */
export function curlTravel(frame: number, start: number): number {
  return easeInOut((frame - start) / TIMING.curl) * DIAG * 1.02;
}

// The flap's shading from the fold outward, as flat bands (no gradient): a
// shadowed crease, a bright roll, then paper turning away from the light.
export const FLAP_BANDS: [number, number, string][] = [
  [0, 0.05, "#D6CAB0"], [0.05, 0.12, "#EDE5D2"], [0.12, 0.3, "#FBF7EC"], [0.3, 0.55, "#F5EFDF"],
  [0.55, 0.8, "#ECE3CD"], [0.8, 1.01, "#E2D7BE"],
];

/** The parts of a curl at travel s: the old page that is still flat (`keep`),
 *  the turned flap as shaded bands (`bands`, each with its colour), its outline
 *  (`flap`), and the shadow band the fold casts on the new page. */
export function curlShapes(s: number): { keep: Pt[]; flap: Pt[]; bands: [Pt[], string][]; shade: Pt[] } {
  const keep = clipHalf(PAGE, (p) => along(p) - s);
  const under = clipHalf(PAGE, (p) => s - along(p));
  const turn = (p: Pt): Pt => {
    const d = (1 + CURL_K) * (s - along(p));
    return [p[0] + d * U[0], p[1] + d * U[1]];
  };
  const bands = FLAP_BANDS.map(([a, b, c]) => {
    const band = clipHalf(clipHalf(under, (p) => s - along(p) - a * s), (p) => b * s - (s - along(p)));
    return [band.map(turn), c] as [Pt[], string];
  }).filter(([band]) => band.length > 2);
  const shade = clipHalf(under, (p) => along(p) - (s - 90));
  return { keep, flap: under.map(turn), bands, shade };
}
