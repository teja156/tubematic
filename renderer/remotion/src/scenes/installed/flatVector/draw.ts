/*
 * Flat Vector Science's painter: draws one shot of the world on the scene's
 * Canvas 2D context, as a pure function of the data and the frame: the
 * backdrop, the drifting specks, the props (cached bitmaps, ./sprites.ts) and
 * their halos. Text (pills, the counter, the rule, the scale bar, titles) is
 * DOM drawn by FlatVectorScience.tsx, so the text audit can measure it.
 */
import {
  GEOMETRY, H, LIMITS, TIMING, W, propScale, type Backdrop, type DescentShot, type FlatVectorData, type Item, type LadderShot,
  type Shot, type Size, type StagesShot, type ZoomShot,
} from "./contract";
import { PROPS } from "./props";
import { type Sprite } from "./sprites";
import { clamp01, depthAt, drift, easeInOut, easeOut, itemScale, pictureAts, ramp, stepAt } from "./stage";

export const COLORS = {
  white: "#F9FCFB",
  red: "#d8343a",
  gold: "#FACC12",
  core: "#F9EF93",
  unlit: "#6f8487",
} as const;

/** Each backdrop's top and bottom colour, and the kind of speck that drifts in it. */
export const BACKDROP: Record<Backdrop, { top: string; bottom: string; speck: "snow" | "stars" | "dust" | "blobs" }> = {
  abyss: { top: "#030c0f", bottom: "#081c22", speck: "snow" },
  ocean: { top: "#12609a", bottom: "#081c22", speck: "snow" },
  night: { top: "#070b1d", bottom: "#121a38", speck: "stars" },
  sky: { top: "#0b1d3a", bottom: "#3f7fb8", speck: "dust" },
  strata: { top: "#2a1d18", bottom: "#120c0a", speck: "dust" },
  inside: { top: "#1c0d1a", bottom: "#2e1028", speck: "blobs" },
};

/** The ocean column a descent scrolls through: sunlit cyan at the top to the abyss at the bottom. */
export const DESCENT_STOPS = ["#1f97d1", "#1680bb", "#12609a", "#0d4466", "#0b3048", "#0a2430", "#081c22", "#05111a", "#030c0f"];

export interface Assets {
  sprites: Record<string, Sprite>;
  halos: Record<string, HTMLCanvasElement>;
  backdrops: Record<string, HTMLCanvasElement>;
  descent: HTMLCanvasElement;
  speck: HTMLCanvasElement;
  blur: HTMLCanvasElement;
}

type Ctx = CanvasRenderingContext2D;

export function rng(seed: number) {
  let a = seed >>> 0;
  return () => {
    a = (a + 0x6d2b79f5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

// ── backdrops, drawn once ───────────────────────────────────────────────────
export function makeBackdrop(b: Backdrop): HTMLCanvasElement {
  const c = document.createElement("canvas");
  c.width = W;
  c.height = H;
  const ctx = c.getContext("2d")!;
  const g = ctx.createLinearGradient(0, 0, 0, H);
  g.addColorStop(0, BACKDROP[b].top);
  g.addColorStop(1, BACKDROP[b].bottom);
  ctx.fillStyle = g;
  ctx.fillRect(0, 0, W, H);
  if (b === "strata") {
    const bands = ["#3a2a22", "#4a3326", "#5a3c2a", "#6e4630", "#8a4e2e", "#a8552c"];
    bands.forEach((col, i) => {
      ctx.fillStyle = col;
      ctx.globalAlpha = 0.5;
      ctx.fillRect(0, 300 + i * 260, W, 250);
    });
    ctx.globalAlpha = 1;
  }
  if (b === "sky") {
    ctx.fillStyle = "#6fa8d8";
    ctx.globalAlpha = 0.35;
    ctx.beginPath();
    ctx.ellipse(W / 2, H + 1500, 1900, 1700, 0, 0, Math.PI * 2);
    ctx.fill();
    ctx.globalAlpha = 1;
  }
  // a soft vignette, baked in
  const v = ctx.createRadialGradient(W / 2, H * 0.45, H * 0.35, W / 2, H * 0.45, H * 0.75);
  v.addColorStop(0, "rgba(0,0,0,0)");
  v.addColorStop(1, "rgba(0,0,0,0.4)");
  ctx.fillStyle = v;
  ctx.fillRect(0, 0, W, H);
  return c;
}

/** The ocean column, 3 frames tall, drawn once. */
export function makeDescent(): HTMLCanvasElement {
  const c = document.createElement("canvas");
  c.width = W / 4;
  c.height = (H * 3) / 4;
  const ctx = c.getContext("2d")!;
  const g = ctx.createLinearGradient(0, 0, 0, c.height);
  DESCENT_STOPS.forEach((col, i) => g.addColorStop(i / (DESCENT_STOPS.length - 1), col));
  ctx.fillStyle = g;
  ctx.fillRect(0, 0, c.width, c.height);
  return c;
}

/** A white speck and a blurred foreground speck, drawn once each. */
export function makeSpeck(blurred: boolean): HTMLCanvasElement {
  const c = document.createElement("canvas");
  c.width = c.height = 64;
  const ctx = c.getContext("2d")!;
  const g = ctx.createRadialGradient(32, 32, 0, 32, 32, 32);
  g.addColorStop(0, "rgba(249,252,251,1)");
  g.addColorStop(blurred ? 0.2 : 0.6, "rgba(249,252,251,0.9)");
  g.addColorStop(1, "rgba(249,252,251,0)");
  ctx.fillStyle = g;
  ctx.fillRect(0, 0, 64, 64);
  return c;
}

// ── specks ──────────────────────────────────────────────────────────────────
type Speck = { x: number; y: number; r: number; ph: number; o: number };
const SPECKS: Record<string, Speck[]> = {};
function specks(seed: number, n: number, rMin: number, rMax: number): Speck[] {
  const key = `${seed}|${n}`;
  if (!SPECKS[key]) {
    const r = rng(seed);
    SPECKS[key] = Array.from({ length: n }, () => ({ x: r() * W, y: r() * H, r: rMin + r() * (rMax - rMin), ph: r() * 6.28, o: 0.4 + r() * 0.6 }));
  }
  return SPECKS[key];
}

function drawSpecks(ctx: Ctx, a: Assets, kind: "snow" | "stars" | "dust" | "blobs", frame: number, scroll: number) {
  if (kind === "stars") {
    for (const p of specks(31, 70, 2, 5)) {
      ctx.globalAlpha = p.o * (0.45 + 0.55 * Math.max(0, Math.sin(frame * 0.09 + p.ph)));
      ctx.drawImage(a.speck, p.x - p.r, p.y - p.r, p.r * 2, p.r * 2);
    }
  } else if (kind === "blobs") {
    for (const p of specks(41, 26, 10, 26)) {
      const y = ((p.y - frame * 0.5) % H + H) % H;
      ctx.globalAlpha = 0.12 * p.o;
      ctx.drawImage(a.speck, p.x + Math.sin(frame * 0.02 + p.ph) * 20 - p.r, y - p.r, p.r * 2, p.r * 2);
    }
  } else {
    const fall = kind === "snow" ? 0.6 : -0.3;
    for (const [seed, n, r0, r1, d, alpha] of [[11, 46, 2, 3.5, 0.55, 0.32], [23, 30, 3.5, 6, 1, 0.45]] as const) {
      for (const p of specks(seed, n, r0, r1)) {
        const y = ((p.y - (scroll + frame * fall) * d) % H + H) % H;
        const x = p.x + Math.sin(frame * 0.03 + p.ph) * 10 * d;
        ctx.globalAlpha = alpha * p.o;
        ctx.drawImage(a.speck, x - p.r * 2, y - p.r * 2, p.r * 4, p.r * 4);
      }
    }
  }
  ctx.globalAlpha = 1;
}

function drawForeground(ctx: Ctx, a: Assets, frame: number, scroll: number) {
  for (const p of specks(37, 8, 14, 24)) {
    const y = ((p.y - (scroll + frame * 0.6) * 1.6) % H + H) % H;
    ctx.globalAlpha = 0.22 * p.o;
    ctx.drawImage(a.blur, p.x - p.r * 2, y - p.r * 2, p.r * 4, p.r * 4);
  }
  ctx.globalAlpha = 1;
}

// ── props ───────────────────────────────────────────────────────────────────
export function boxOf(what: string, data: FlatVectorData): [number, number] {
  const own = (data.customProps ?? []).find((c) => c.id === what);
  return own ? own.box : PROPS[what]?.box ?? [200, 200];
}

export function lightOf(what: string, data: FlatVectorData): string | undefined {
  const own = (data.customProps ?? []).find((c) => c.id === what);
  return own ? own.light : PROPS[what]?.light;
}

/** Draws a prop's bitmap centred at (x, y), its longest side `px` pixels, rotated `rot` degrees. */
export function drawProp(ctx: Ctx, a: Assets, data: FlatVectorData, what: string, x: number, y: number, px: number, rot = 0, flip = false, alpha = 1) {
  const sp = a.sprites[what];
  if (!sp || px <= 0.5) return;
  const s = px / Math.max(sp.width, sp.height);
  const light = lightOf(what, data);
  if (light && a.halos[light]) {
    const r = Math.max(sp.width, sp.height) * s * 0.75;
    ctx.globalAlpha = 0.6 * alpha;
    ctx.drawImage(a.halos[light], x - r, y - r, r * 2, r * 2);
  }
  ctx.save();
  ctx.globalAlpha = alpha;
  ctx.translate(x, y);
  if (rot) ctx.rotate((rot * Math.PI) / 180);
  ctx.scale(flip ? -s : s, s);
  ctx.drawImage(sp.canvas, -sp.width / 2, -sp.height / 2, sp.width, sp.height);
  ctx.restore();
}

const sizePx = (data: FlatVectorData, what: string, size: Size) => propScale(boxOf(what, data), size) * Math.max(...boxOf(what, data));

function drawItems(ctx: Ctx, a: Assets, data: FlatVectorData, items: Item[], frame: number) {
  items.forEach((it, i) => {
    const sc = itemScale(it, frame);
    if (sc <= 0) return;
    const [cx, cy] = GEOMETRY.slot[it.slot];
    const d = drift(frame, i + 1);
    drawProp(ctx, a, data, it.what, cx + d.dx, cy + d.dy, sizePx(data, it.what, it.size) * sc, d.rot, it.flip);
  });
}

/** A ladder or a zoom: the current thing grows in from beyond the frame while the last one shrinks to a small mark. */
function drawGrowth(ctx: Ctx, a: Assets, data: FlatVectorData, shot: LadderShot | ZoomShot, frame: number) {
  const list = shot.kind === "ladder" ? shot.rungs : shot.levels;
  const { index, progress } = stepAt(pictureAts(shot), frame);
  const [cx, cy] = GEOMETRY.slot.center;
  const d = drift(frame, 3);
  const big = GEOMETRY.size.l;
  const zoom = shot.kind === "zoom";
  if (index < 0) return;
  if (index > 0) {
    // the last one shrinks to a small mark at the centre of the new one
    const prev = list[index - 1].what;
    const k = zoom ? Math.pow(10, -progress) : 1 - 0.84 * progress;
    drawProp(ctx, a, data, prev, cx + d.dx * (1 - progress), cy + d.dy * (1 - progress) + 60 * progress, big * k, 0, false, 1 - 0.4 * progress);
  }
  const k = zoom ? Math.pow(10, 1 - progress) : 1 + 2 * (1 - progress);
  drawProp(ctx, a, data, list[index].what, cx + d.dx, cy + d.dy, big * k, d.rot, false, index === 0 ? easeOut(progress * 2) : 1);
}

function drawDescent(ctx: Ctx, a: Assets, data: FlatVectorData, shot: DescentShot, frame: number) {
  const { index, progress } = stepAt(pictureAts(shot), frame);
  if (index < 0) return;
  const layer = shot.layers[index];
  if (!layer.what) return;
  const d = drift(frame, index + 5);
  const [cx, cy] = GEOMETRY.slot.center;
  // each layer's thing rises in from below as the camera sinks to it
  drawProp(ctx, a, data, layer.what, cx + 80 + d.dx, cy + d.dy + (1 - easeOut(progress)) * 700, GEOMETRY.size.m, d.rot);
}

function drawStages(ctx: Ctx, a: Assets, data: FlatVectorData, shot: StagesShot, frame: number) {
  const { index, progress } = stepAt(pictureAts(shot), frame);
  if (index < 0) return;
  const [cx, cy] = GEOMETRY.slot.center;
  const d = drift(frame, 7);
  // earlier stages as a row of small marks under the current one, joined by arrows
  const n = index;
  const gap = 150;
  const row = GEOMETRY.stripY - 40;
  for (let i = 0; i < n; i++) {
    const x = W / 2 - ((n - 1) * gap) / 2 + i * gap;
    drawProp(ctx, a, data, shot.steps[i].what, x, row, 110, 0, false, 0.75);
    if (i < n - 1) {
      ctx.fillStyle = COLORS.white;
      ctx.globalAlpha = 0.5;
      ctx.beginPath();
      ctx.moveTo(x + 64, row - 10);
      ctx.lineTo(x + 86, row);
      ctx.lineTo(x + 64, row + 10);
      ctx.fill();
      ctx.globalAlpha = 1;
    }
  }
  const sc = Math.max(0, 0.2 + 0.8 * easeOut(progress));
  drawProp(ctx, a, data, shot.steps[index].what, cx + d.dx, cy + d.dy - 40, GEOMETRY.size.l * 0.85 * sc, d.rot);
}

/** How far down the ocean column a descent is at a frame (0 at the surface, 1 at its last layer). */
export function descentFraction(shot: DescentShot, frame: number): number {
  const max = Math.max(1, shot.layers[shot.layers.length - 1].value);
  return clamp01(depthAt(shot, frame) / max);
}

/** Draws shot `shot` at `frame` on a frame-sized context. */
export function drawShot(ctx: Ctx, a: Assets, data: FlatVectorData, shot: Shot, frame: number) {
  let scroll = 0;
  if (shot.kind === "descent") {
    const f = descentFraction(shot, frame);
    const col = a.descent;
    const sy = f * (col.height - col.height / 3);
    ctx.drawImage(col, 0, sy, col.width, col.height / 3, 0, 0, W, H);
    scroll = f * 4000;
  } else {
    ctx.drawImage(a.backdrops[shot.backdrop], 0, 0);
  }
  const kind = shot.kind === "descent" ? "snow" : BACKDROP[shot.backdrop].speck;
  drawSpecks(ctx, a, kind, frame, scroll);
  switch (shot.kind) {
    case "subject":
      drawItems(ctx, a, data, shot.items, frame);
      break;
    case "ladder":
    case "zoom":
      drawGrowth(ctx, a, data, shot, frame);
      break;
    case "descent":
      drawDescent(ctx, a, data, shot, frame);
      break;
    case "stages":
      drawStages(ctx, a, data, shot, frame);
      break;
  }
  drawForeground(ctx, a, frame, scroll);
}

/** The number of props a shot uses, for the limits (the validator mirrors this). */
export const MAX_ITEMS = LIMITS.maxItems;
export const POP = TIMING.pop;
export { easeInOut, ramp };
