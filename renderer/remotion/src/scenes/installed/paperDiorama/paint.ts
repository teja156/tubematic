/*
 * Paints a paper prop onto a canvas, once.
 *
 * Every piece is a cut of flat colour with a slightly rough edge, a darker
 * strip along its bottom or a lighter one along its top, grain, and the whole
 * prop casts one soft shadow down and to the right (light from the top left).
 * The kit drew the same look live with SVG feTurbulence displacement and CSS
 * drop-shadows on every prop, which software GL redraws on every frame (10 to
 * 100x the cost). Here the rough edge is a jittered outline, the grain a
 * speck pattern painted over the paper, the shadow a canvas shadow, all drawn
 * once; the stage then only moves the finished bitmap.
 */
import { COLORS, type ColorName, type Piece, type PropDef } from "./contract";

export const PAD = 28;           // room around a prop for its shadow and rough edge
const ROUGH = 1.3;               // px the edge wanders either way
const STEP = 7;                  // px between outline points

export const FONT_FAMILY = {
  banner: "'Archivo Black', 'Arial Black', Impact, sans-serif",
  label: "Inter, 'Helvetica Neue', Arial, sans-serif",
  mono: "'JetBrains Mono', Menlo, monospace",
} as const;
const FONT_WEIGHT = { banner: 400, label: 800, mono: 700 } as const;

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

/** A stable number for a string, to seed a prop's edge by its name. */
export function hashSeed(s: string): number {
  let h = 2166136261;
  for (let i = 0; i < s.length; i++) {
    h ^= s.charCodeAt(i);
    h = Math.imul(h, 16777619);
  }
  return h >>> 0;
}

export const color = (name: ColorName | undefined, fallback = "#FF00FF") =>
  (name && COLORS[name]) || fallback;

/** A piece's outline as points, before the rough edge, in the prop's pixels. */
export function outline(p: Piece): [number, number][] {
  if (p.shape === "poly") {
    const pts = p.points ?? [];
    const out: [number, number][] = [];
    for (let i = 0; i < pts.length; i++) {
      const [x0, y0] = pts[i];
      const [x1, y1] = pts[(i + 1) % pts.length];
      const n = Math.max(1, Math.ceil(Math.hypot(x1 - x0, y1 - y0) / STEP));
      for (let k = 0; k < n; k++) out.push([x0 + ((x1 - x0) * k) / n, y0 + ((y1 - y0) * k) / n]);
    }
    return out;
  }
  const x = p.x ?? 0, y = p.y ?? 0, w = p.w ?? 0, h = p.h ?? 0;
  if (p.shape === "ellipse") {
    const n = Math.max(16, Math.ceil((Math.PI * (w + h)) / 2 / STEP));
    return Array.from({ length: n }, (_, i) => {
      const a = (i / n) * Math.PI * 2;
      return [x + w / 2 + (Math.cos(a) * w) / 2, y + h / 2 + (Math.sin(a) * h) / 2] as [number, number];
    });
  }
  // a rect with rounded corners, walked clockwise from the top left
  const r = Math.max(0, Math.min(p.r ?? 4, w / 2, h / 2));
  const out: [number, number][] = [];
  const edge = (x0: number, y0: number, x1: number, y1: number) => {
    const n = Math.max(1, Math.ceil(Math.hypot(x1 - x0, y1 - y0) / STEP));
    for (let k = 0; k < n; k++) out.push([x0 + ((x1 - x0) * k) / n, y0 + ((y1 - y0) * k) / n]);
  };
  const corner = (cx: number, cy: number, a0: number) => {
    if (r <= 0) return;
    for (let k = 0; k < 4; k++) {
      const a = a0 + (k / 4) * (Math.PI / 2);
      out.push([cx + Math.cos(a) * r, cy + Math.sin(a) * r]);
    }
  };
  edge(x + r, y, x + w - r, y);
  corner(x + w - r, y + r, -Math.PI / 2);
  edge(x + w, y + r, x + w, y + h - r);
  corner(x + w - r, y + h - r, 0);
  edge(x + w - r, y + h, x + r, y + h);
  corner(x + r, y + h - r, Math.PI / 2);
  edge(x, y + h - r, x, y + r);
  corner(x + r, y + r, Math.PI);
  return out;
}

/** The outline with a seeded rough cut: each point wanders a pixel or so. */
export function roughen(pts: [number, number][], seed: number): [number, number][] {
  const rnd = rng(seed);
  return pts.map(([x, y]) => [x + (rnd() - 0.5) * 2 * ROUGH, y + (rnd() - 0.5) * 2 * ROUGH]);
}

/** The box a piece covers, rotation aside. */
export function pieceBox(p: Piece): [number, number, number, number] {
  if (p.shape === "poly") {
    const xs = (p.points ?? []).map((q) => q[0]);
    const ys = (p.points ?? []).map((q) => q[1]);
    return [Math.min(...xs), Math.min(...ys), Math.max(...xs), Math.max(...ys)];
  }
  if (p.shape === "text") {
    const size = p.size ?? 30;
    const half = ((p.text ?? "").length * size * 0.62) / 2;
    return [(p.x ?? 0) - half, (p.y ?? 0) - size * 0.6, (p.x ?? 0) + half, (p.y ?? 0) + size * 0.6];
  }
  return [p.x ?? 0, p.y ?? 0, (p.x ?? 0) + (p.w ?? 0), (p.y ?? 0) + (p.h ?? 0)];
}

let noise: HTMLCanvasElement | null = null;
/** The grain: dark and light fibre specks on a transparent tile, made once. */
function grainTile(): HTMLCanvasElement {
  if (noise) return noise;
  const c = document.createElement("canvas");
  c.width = c.height = 256;
  const g = c.getContext("2d")!;
  const rnd = rng(9);
  for (let i = 0; i < 2600; i++) {
    const dark = rnd() < 0.6;
    g.fillStyle = dark ? `rgba(40,30,20,${(0.08 + rnd() * 0.12).toFixed(3)})` : `rgba(255,250,240,${(0.08 + rnd() * 0.12).toFixed(3)})`;
    const len = 1 + rnd() * 2.5;
    g.fillRect(rnd() * 256, rnd() * 256, rnd() < 0.5 ? len : 1, rnd() < 0.5 ? 1 : len);
  }
  noise = c;
  return c;
}

function tracePath(g: CanvasRenderingContext2D, pts: [number, number][]) {
  g.beginPath();
  pts.forEach(([x, y], i) => (i ? g.lineTo(x, y) : g.moveTo(x, y)));
  g.closePath();
}

function drawPiece(g: CanvasRenderingContext2D, p: Piece, seed: number) {
  const [x0, y0, x1, y1] = pieceBox(p);
  const cx = (x0 + x1) / 2, cy = (y0 + y1) / 2;
  g.save();
  if (p.rot) {
    g.translate(cx, cy);
    g.rotate((p.rot * Math.PI) / 180);
    g.translate(-cx, -cy);
  }
  if (p.shape === "text") {
    const font = p.font ?? "label";
    g.font = `${FONT_WEIGHT[font]} ${p.size ?? 30}px ${FONT_FAMILY[font]}`;
    g.textAlign = "center";
    g.textBaseline = "middle";
    g.fillStyle = color(p.fill);
    g.fillText(p.text ?? "", p.x ?? 0, p.y ?? 0);
    g.restore();
    return;
  }
  tracePath(g, roughen(outline(p), seed));
  g.fillStyle = color(p.fill);
  g.fill();
  if (p.shade || p.hi) {
    g.clip();
    if (p.shade) {
      const h = (y1 - y0) * (p.shadeH ?? 0.18);
      g.fillStyle = color(p.shade);
      g.fillRect(x0 - 4, y1 - h, x1 - x0 + 8, h + 4);
    }
    if (p.hi) {
      g.fillStyle = color(p.hi);
      g.fillRect(x0 - 4, y0 - 4, x1 - x0 + 8, (y1 - y0) * (p.hiH ?? 0.12) + 4);
    }
  }
  g.restore();
}

/** Paint `def` onto a new canvas of (w + 2 PAD) x (h + 2 PAD), the prop's
 *  top-left corner at (PAD, PAD). `lift` sets how far the shadow falls. */
export function paintProp(def: PropDef, seed: number, lift = 5): HTMLCanvasElement {
  const w = Math.ceil(def.w + 2 * PAD), h = Math.ceil(def.h + 2 * PAD);
  const paper = document.createElement("canvas");
  paper.width = w;
  paper.height = h;
  const g = paper.getContext("2d")!;
  g.translate(PAD, PAD);
  def.pieces.forEach((p, i) => {
    if (p.shape !== "text") drawPiece(g, p, seed + i * 7919);
  });
  // grain on the paper only, then the printed text on top of the grain
  g.globalCompositeOperation = "source-atop";
  const pat = g.createPattern(grainTile(), "repeat");
  if (pat) {
    g.fillStyle = pat;
    g.fillRect(-PAD, -PAD, w, h);
  }
  g.globalCompositeOperation = "source-over";
  def.pieces.forEach((p, i) => {
    if (p.shape === "text") drawPiece(g, p, seed + i * 7919);
  });
  const out = document.createElement("canvas");
  out.width = w;
  out.height = h;
  const o = out.getContext("2d")!;
  o.shadowColor = "rgba(0,0,0,0.36)";
  o.shadowBlur = lift * 2;
  o.shadowOffsetX = lift * 0.5;
  o.shadowOffsetY = lift;
  o.drawImage(paper, 0, 0);
  return out;
}
