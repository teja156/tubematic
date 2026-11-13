/*
 * Isometric Infographic's drawing kit: the true isometric projection, the
 * three tones of a face, the solids (box, cylinder, cone, pyramid, gable roof,
 * billboard) and the prop library built from them, all drawn on a Canvas 2D
 * context. Pure functions of their inputs.
 *
 * World units are board tiles; the board is BOARD x BOARD tiles, x running
 * down to the right and y down to the left on screen, z up. A prop is a list
 * of solids in its own coordinates, centred on its footprint (x and y from
 * about -0.5 to 0.5 for a one-tile prop), listed back to front.
 */

export const INK = "#231A2C";
export const WARM_WHITE = "#FFF8EC";
export const PAPER = "#F1E8D8";
const C30 = Math.cos(Math.PI / 6);

/** The named colours a prop, a route or a legend entry can take, one meaning each. */
export const PALETTE: Record<string, string> = {
  red: "#CF5140",
  gold: "#E2AE3A",
  slate: "#58627C",
  teal: "#3F7F86",
  green: "#7BA75F",
  blue: "#5A9BCB",
  cream: "#EFE5D2",
  grey: "#A9A39A",
  plum: "#8A5A7A",
};

export const AREA_COLORS: Record<string, string> = {
  land: "#7BA75F",
  forest: "#6E9E58",
  city: "#D3C3A2",
  sand: "#D3C3A2",
  water: "#5A9BCB",
  road: "#9A948A",
  plaza: "#E4D8C2",
  field: "#B9B26A",
};

const hex = (h: string) => [1, 3, 5].map((i) => parseInt(h.slice(i, i + 2), 16));
export function mix(a: string, b: string, t: number): string {
  const A = hex(a), B = hex(b);
  return "#" + A.map((v, i) => Math.round(v + (B[i] - v) * t).toString(16).padStart(2, "0")).join("");
}
/** Three tones from one base: top 20% toward warm white, left side = base, right side 22% toward ink. */
export const tones = (base: string) => ({ top: mix(base, WARM_WHITE, 0.2), left: base, right: mix(base, INK, 0.22) });

export type V2 = [number, number];

/** A projection: board tiles to canvas pixels at a scale and an origin. */
export interface Proj {
  k: number;
  cx: number;
  cy: number;
}
export const project = (pr: Proj, x: number, y: number, z = 0): V2 => [pr.cx + (x - y) * C30 * pr.k, pr.cy + (x + y) * 0.5 * pr.k - z * pr.k];

type Ctx = CanvasRenderingContext2D;

export function poly(ctx: Ctx, pts: V2[], fill: string) {
  ctx.fillStyle = fill;
  ctx.beginPath();
  pts.forEach((p, i) => (i ? ctx.lineTo(p[0], p[1]) : ctx.moveTo(p[0], p[1])));
  ctx.closePath();
  ctx.fill();
}

// ── solids ─────────────────────────────────────────────────────────────────
/** The colour a solid is drawn in: "main" is the prop's own colour, "accent" a second one, else a hex. */
export type Paint = string;

export type Solid =
  | { s: "box"; x: number; y: number; z?: number; w: number; d: number; h: number; c: Paint; top?: Paint; layer?: number }
  | { s: "cyl"; x: number; y: number; z?: number; r: number; h: number; c: Paint }
  | { s: "cone"; x: number; y: number; z?: number; r: number; h: number; c: Paint }
  | { s: "pyr"; x: number; y: number; z?: number; r: number; h: number; c: Paint }
  | { s: "gable"; x: number; y: number; z?: number; w: number; d: number; h: number; c: Paint }
  | { s: "bill"; x: number; y: number; z?: number; w: number; h: number; c: Paint; shape: "person" | "disc" | "panel" };

export interface Look {
  main: string;
  accent: string;
  /** 0..1 toward the paper: a solid stepped back while another lifts. */
  fade: number;
  /** z offset per explode layer. */
  spread: number;
}

function paint(c: Paint, look: Look): string {
  // a custom prop names its colours from the palette; the library writes them as hex
  const base = c === "main" ? look.main : c === "accent" ? look.accent : (PALETTE[c] ?? c);
  return look.fade > 0 ? mix(base, "#E6DDCC", look.fade) : base;
}

/** Draws one solid at prop origin (ox, oy, oz) with scale `sc` (a prop's size relative to its tile). */
export function drawSolid(ctx: Ctx, pr: Proj, sd: Solid, ox: number, oy: number, oz: number, sc: number, look: Look, open = false) {
  const z0 = oz + ((sd.z ?? 0) + (sd.s === "box" ? (sd.layer ?? 0) * look.spread : 0)) * sc;
  const X = (v: number) => ox + v * sc, Y = (v: number) => oy + v * sc;
  const P = (x: number, y: number, z: number) => project(pr, x, y, z);
  const base = paint(sd.c, look);
  const t = tones(base);
  if (sd.s === "box") {
    const x0 = X(sd.x - sd.w / 2), x1 = X(sd.x + sd.w / 2), y0 = Y(sd.y - sd.d / 2), y1 = Y(sd.y + sd.d / 2), z1 = z0 + sd.h * sc;
    if (!open) {
      poly(ctx, [P(x0, y1, z0), P(x1, y1, z0), P(x1, y1, z1), P(x0, y1, z1)], t.left);
      poly(ctx, [P(x1, y0, z0), P(x1, y1, z0), P(x1, y1, z1), P(x1, y0, z1)], t.right);
    }
    poly(ctx, [P(x0, y0, z1), P(x1, y0, z1), P(x1, y1, z1), P(x0, y1, z1)], sd.top ? paint(sd.top, look) : t.top);
  } else if (sd.s === "cyl" || sd.s === "cone") {
    const [cx, cy] = P(X(sd.x), Y(sd.y), z0);
    const rx = 1.2247 * sd.r * sc * pr.k, ry = 0.7071 * sd.r * sc * pr.k;
    const hpx = sd.h * sc * pr.k;
    if (sd.s === "cyl") {
      ctx.fillStyle = t.left;
      ctx.beginPath();
      ctx.ellipse(cx, cy, rx, ry, 0, 0, Math.PI);
      ctx.lineTo(cx - rx, cy - hpx);
      ctx.ellipse(cx, cy - hpx, rx, ry, 0, Math.PI, 0, true);
      ctx.closePath();
      ctx.fill();
      // the right half a shade darker
      ctx.fillStyle = t.right;
      ctx.beginPath();
      ctx.ellipse(cx, cy, rx, ry, 0, 0, Math.PI / 2);
      ctx.lineTo(cx, cy - hpx + ry);
      ctx.lineTo(cx + rx, cy - hpx);
      ctx.closePath();
      ctx.fill();
      ctx.fillStyle = t.top;
      ctx.beginPath();
      ctx.ellipse(cx, cy - hpx, rx, ry, 0, 0, Math.PI * 2);
      ctx.fill();
    } else {
      poly(ctx, [[cx - rx, cy], [cx, cy - hpx], [cx, cy + ry]], t.left);
      poly(ctx, [[cx, cy + ry], [cx, cy - hpx], [cx + rx, cy]], t.right);
    }
  } else if (sd.s === "pyr") {
    const x = X(sd.x), y = Y(sd.y), r = sd.r * sc;
    const apex = P(x, y, z0 + sd.h * sc);
    poly(ctx, [P(x - r, y + r, z0), P(x + r, y + r, z0), apex], t.left);
    poly(ctx, [P(x + r, y - r, z0), P(x + r, y + r, z0), apex], t.right);
  } else if (sd.s === "gable") {
    // a roof along x: ridge at the middle of y
    const x0 = X(sd.x - sd.w / 2), x1 = X(sd.x + sd.w / 2), y0 = Y(sd.y - sd.d / 2), y1 = Y(sd.y + sd.d / 2), yc = (y0 + y1) / 2;
    const zr = z0 + sd.h * sc;
    poly(ctx, [P(x0, y0, z0), P(x1, y0, z0), P(x1, yc, zr), P(x0, yc, zr)], t.top);
    poly(ctx, [P(x0, y1, z0), P(x1, y1, z0), P(x1, yc, zr), P(x0, yc, zr)], t.left);
    poly(ctx, [P(x1, y0, z0), P(x1, y1, z0), P(x1, yc, zr)], t.right);
  } else {
    // a billboard: a flat upright shape facing the camera
    const [bx, by] = P(X(sd.x), Y(sd.y), z0);
    const w = sd.w * sc * pr.k, h = sd.h * sc * pr.k;
    ctx.fillStyle = "rgba(35,26,44,0.18)";
    ctx.beginPath();
    ctx.ellipse(bx, by, w * 0.7, w * 0.27, 0, 0, Math.PI * 2);
    ctx.fill();
    if (sd.shape === "person") {
      ctx.fillStyle = base;
      ctx.beginPath();
      ctx.roundRect(bx - w / 2, by - h * 0.82, w, h * 0.64, w * 0.45);
      ctx.fill();
      ctx.fillStyle = INK;
      ctx.fillRect(bx - w * 0.38, by - h * 0.24, w * 0.26, h * 0.24);
      ctx.fillRect(bx + w * 0.12, by - h * 0.24, w * 0.26, h * 0.24);
      ctx.fillStyle = "#6B4A3A";
      ctx.beginPath();
      ctx.arc(bx, by - h * 0.92, w * 0.5, 0, Math.PI * 2);
      ctx.fill();
    } else if (sd.shape === "disc") {
      ctx.fillStyle = t.top;
      ctx.beginPath();
      ctx.arc(bx, by - h / 2, w / 2, 0, Math.PI * 2);
      ctx.fill();
    } else {
      poly(ctx, [[bx - w / 2, by], [bx + w / 2, by - w * 0.25], [bx + w / 2, by - h - w * 0.25], [bx - w / 2, by - h]], t.left);
    }
  }
}

// ── the prop library ───────────────────────────────────────────────────────
export interface PropDef {
  /** The solids, back to front. */
  solids: Solid[];
  /** The default colour of "main" and of "accent". */
  main: string;
  accent: string;
  /** Its height in tiles, for a pin's anchor. */
  height: number;
  /** A building whose front walls can be cut away to show what is inside. */
  room?: boolean;
  /** Layers that separate when exploded. */
  layers?: number;
}

const box = (x: number, y: number, w: number, d: number, h: number, c: Paint, z = 0, layer?: number): Solid => ({ s: "box", x, y, z, w, d, h, c, layer });
const cyl = (x: number, y: number, r: number, h: number, c: Paint, z = 0): Solid => ({ s: "cyl", x, y, z, r, h, c });
const cone = (x: number, y: number, r: number, h: number, c: Paint, z = 0): Solid => ({ s: "cone", x, y, z, r, h, c });
const pyr = (x: number, y: number, r: number, h: number, c: Paint, z = 0): Solid => ({ s: "pyr", x, y, z, r, h, c });
const gable = (x: number, y: number, w: number, d: number, h: number, c: Paint, z = 0): Solid => ({ s: "gable", x, y, z, w, d, h, c });
const bill = (x: number, y: number, w: number, h: number, c: Paint, shape: "person" | "disc" | "panel", z = 0): Solid => ({ s: "bill", x, y, z, w, h, c, shape });

/** Window strips on a box's two visible faces, as thin boxes just proud of the walls. */
function windows(w: number, d: number, h: number, rows: number, c: Paint): Solid[] {
  const out: Solid[] = [];
  for (let r = 0; r < rows; r++) {
    const z = 0.15 + (r * (h - 0.25)) / Math.max(1, rows);
    out.push(box(0, d / 2 + 0.005, w * 0.8, 0.01, 0.06, c, z), box(w / 2 + 0.005, 0, 0.01, d * 0.8, 0.06, c, z));
  }
  return out;
}

export const PROPS: Record<string, PropDef> = {
  house: { main: "#EFE5D2", accent: "#3F7F86", height: 0.95, room: true,
    solids: [box(0, 0, 0.8, 0.8, 0.55, "main"), gable(0, 0, 0.8, 0.8, 0.38, "accent", 0.55), box(0, 0.405, 0.22, 0.01, 0.32, "accent")] },
  office: { main: "#B9C2C4", accent: "#86A6C0", height: 2.2, room: true,
    solids: [box(0, 0, 0.8, 0.8, 2.1, "main"), ...windows(0.8, 0.8, 2.1, 6, "accent")] },
  tower_block: { main: "#C9B597", accent: "#9DB0CF", height: 3, solids: [box(0, 0, 0.7, 0.7, 2.9, "main"), ...windows(0.7, 0.7, 2.9, 8, "accent")] },
  factory: { main: "#A9A39A", accent: "#CF5140", height: 1.9, room: true,
    solids: [cyl(0.25, -0.25, 0.12, 1.8, "accent"), box(0, 0.1, 1.0, 0.8, 0.7, "main"), gable(0, 0.1, 1.0, 0.8, 0.25, "#8C8378", 0.7)] },
  warehouse: { main: "#C9B597", accent: "#8C7A66", height: 0.9, room: true,
    solids: [box(0, 0, 1.4, 0.9, 0.6, "main"), gable(0, 0, 1.4, 0.9, 0.3, "accent", 0.6), box(0, 0.455, 0.4, 0.01, 0.4, "accent")] },
  data_centre: { main: "#58627C", accent: "#BFD0EA", height: 1.2, room: true,
    solids: [box(0, 0, 1.4, 1.0, 1.0, "main"), ...windows(1.4, 1.0, 1.0, 3, "accent"), box(-0.3, -0.2, 0.4, 0.3, 0.18, "#8C93A6", 1.0), box(0.3, -0.2, 0.4, 0.3, 0.18, "#8C93A6", 1.0)] },
  server_rack: { main: "#3E4660", accent: "#7DD3DC", height: 1.1, layers: 4,
    solids: [0, 1, 2, 3].map((i) => box(0, 0, 0.45, 0.45, 0.24, "main", i * 0.26, i)).concat([0, 1, 2, 3].map((i) => box(0, 0.23, 0.3, 0.01, 0.04, "accent", i * 0.26 + 0.1, i))) },
  cell_tower: { main: "#A9A39A", accent: "#CF5140", height: 2.3,
    solids: [cone(0, 0, 0.18, 2.2, "main"), box(0, 0, 0.3, 0.06, 0.18, "accent", 1.8), box(0, 0, 0.06, 0.3, 0.18, "accent", 1.6)] },
  dish: { main: "#EFE5D2", accent: "#A9A39A", height: 1.0, solids: [cyl(0, 0, 0.08, 0.5, "accent"), bill(0, 0, 0.7, 0.6, "main", "disc", 0.45)] },
  router: { main: "#58627C", accent: "#7DD3DC", height: 0.6,
    solids: [box(-0.2, -0.1, 0.05, 0.05, 0.55, "main"), box(0.2, -0.1, 0.05, 0.05, 0.55, "main"), box(0, 0, 0.6, 0.4, 0.15, "main"), box(0, 0.205, 0.4, 0.01, 0.04, "accent", 0.06)] },
  phone: { main: "#231A2C", accent: "#7DD3DC", height: 0.6, solids: [box(0, 0, 0.3, 0.06, 0.55, "main"), box(0, 0.035, 0.24, 0.01, 0.45, "accent", 0.05)] },
  laptop: { main: "#A9A39A", accent: "#7DD3DC", height: 0.4, solids: [box(0, 0, 0.6, 0.4, 0.04, "main"), box(0, -0.18, 0.6, 0.04, 0.36, "main", 0.04), box(0, -0.155, 0.5, 0.01, 0.28, "accent", 0.08)] },
  shop: { main: "#EFE5D2", accent: "#CF5140", height: 0.9, room: true,
    solids: [box(0, 0, 0.8, 0.8, 0.6, "main"), box(0, 0.44, 0.8, 0.12, 0.05, "accent", 0.45), box(0, 0, 0.8, 0.8, 0.08, "accent", 0.6)] },
  bank: { main: "#E6DCC8", accent: "#A9A39A", height: 1.2, room: true,
    solids: [box(0, 0, 1.0, 0.9, 0.12, "accent"), ...[-0.35, -0.12, 0.12, 0.35].map((x) => cyl(x, 0.35, 0.06, 0.6, "main", 0.12)), box(0, 0, 1.0, 0.9, 0.12, "accent", 0.72), gable(0, 0, 1.0, 0.9, 0.3, "main", 0.84)] },
  hospital: { main: "#F4EFE6", accent: "#CF5140", height: 1.4, room: true,
    solids: [box(0, 0, 1.0, 0.8, 1.2, "main"), ...windows(1.0, 0.8, 1.2, 3, "#9DB0CF"), box(0, 0.405, 0.3, 0.01, 0.1, "accent", 0.95), box(0, 0.405, 0.1, 0.01, 0.3, "accent", 0.85)] },
  school: { main: "#D9A86A", accent: "#8C4A3A", height: 1.2, room: true,
    solids: [box(0, 0, 1.2, 0.8, 0.7, "main"), gable(0, 0, 1.2, 0.8, 0.3, "accent", 0.7), box(0, -0.1, 0.25, 0.25, 0.4, "main", 0.7), pyr(0, -0.1, 0.17, 0.25, "accent", 1.1)] },
  power_plant: { main: "#A9A39A", accent: "#EFE5D2", height: 1.6, room: true,
    solids: [cyl(-0.3, -0.3, 0.32, 1.5, "accent"), box(0.25, 0.25, 0.7, 0.6, 0.6, "main")] },
  wind_turbine: { main: "#F4EFE6", accent: "#A9A39A", height: 2.3,
    solids: [cyl(0, 0, 0.05, 2.0, "main"), bill(0, 0, 0.18, 0.18, "accent", "disc", 1.95), box(0, 0.05, 0.05, 0.02, 0.8, "main", 2.05), box(0.25, 0.05, 0.6, 0.02, 0.05, "main", 1.85)] },
  solar_panel: { main: "#2C4A8A", accent: "#A9A39A", height: 0.4,
    solids: [box(-0.25, 0, 0.05, 0.05, 0.25, "accent"), box(0.25, 0, 0.05, 0.05, 0.25, "accent"), box(0, 0, 0.8, 0.5, 0.05, "main", 0.25)] },
  water_tower: { main: "#5A9BCB", accent: "#A9A39A", height: 1.6,
    solids: [box(-0.15, -0.15, 0.05, 0.05, 1.0, "accent"), box(0.15, 0.15, 0.05, 0.05, 1.0, "accent"), cyl(0, 0, 0.3, 0.45, "main", 1.0)] },
  tank: { main: "#EFE5D2", accent: "#A9A39A", height: 0.8, solids: [cyl(0, 0, 0.4, 0.7, "main")] },
  pipe: { main: "#A9A39A", accent: "#58627C", height: 0.3, solids: [box(0, 0, 1.0, 0.16, 0.16, "main", 0.12), box(-0.4, 0, 0.08, 0.08, 0.12, "accent"), box(0.4, 0, 0.08, 0.08, 0.12, "accent")] },
  truck: { main: "#CF5140", accent: "#EFE5D2", height: 0.6,
    solids: [box(-0.15, 0, 0.6, 0.35, 0.4, "accent", 0.08), box(0.3, 0, 0.25, 0.35, 0.3, "main", 0.08), box(0, 0, 0.9, 0.3, 0.08, INK)] },
  van: { main: "#EFE5D2", accent: "#231A2C", height: 0.5, solids: [box(0, 0, 0.6, 0.32, 0.36, "main", 0.08), box(0, 0, 0.6, 0.28, 0.08, "accent")] },
  car: { main: "#CF5140", accent: "#231A2C", height: 0.4, solids: [box(0, 0, 0.55, 0.3, 0.16, "main", 0.06), box(-0.03, 0, 0.3, 0.26, 0.12, "main", 0.22), box(0, 0, 0.5, 0.26, 0.06, "accent")] },
  bus: { main: "#E2AE3A", accent: "#231A2C", height: 0.55, solids: [box(0, 0, 1.0, 0.34, 0.4, "main", 0.08), box(0, 0.175, 0.9, 0.01, 0.12, "#5A7A96", 0.28), box(0, 0, 0.95, 0.3, 0.08, "accent")] },
  train: { main: "#3F7F86", accent: "#EFE5D2", height: 0.55,
    solids: [-0.55, 0, 0.55].map((x) => box(x, 0, 0.5, 0.3, 0.38, "main", 0.08)).concat([box(0, 0.155, 1.5, 0.01, 0.08, "accent", 0.28)]) },
  ship: { main: "#58627C", accent: "#CF5140", height: 0.9,
    solids: [box(0, 0, 1.6, 0.5, 0.3, "main"), box(-0.55, 0, 0.3, 0.4, 0.5, "#EFE5D2", 0.3), ...[0, 0.35].flatMap((x) => [box(x, -0.1, 0.3, 0.2, 0.2, "accent", 0.3), box(x, 0.12, 0.3, 0.2, 0.2, "#E2AE3A", 0.3)])] },
  plane: { main: "#EFE5D2", accent: "#A9A39A", height: 0.5, solids: [box(0, 0, 0.2, 1.2, 0.06, "accent", 0.22), box(0, 0, 1.1, 0.2, 0.2, "main", 0.15), box(-0.45, 0, 0.12, 0.06, 0.3, "main", 0.3)] },
  crane: { main: "#E2AE3A", accent: "#231A2C", height: 2.2,
    solids: [box(0, 0, 0.15, 0.15, 2.0, "main"), box(0.4, 0, 1.1, 0.12, 0.12, "main", 1.95), box(0.8, 0, 0.02, 0.02, 0.8, "accent", 1.15)] },
  container_stack: { main: "#CF5140", accent: "#5A9BCB", height: 0.9, layers: 3,
    solids: [box(0, 0, 0.9, 0.4, 0.28, "main", 0, 0), box(0, 0, 0.9, 0.4, 0.28, "accent", 0.29, 1), box(0, 0, 0.9, 0.4, 0.28, "#E2AE3A", 0.58, 2)] },
  conveyor: { main: "#A9A39A", accent: "#231A2C", height: 0.4, solids: [box(-0.6, 0, 0.06, 0.3, 0.3, "accent"), box(0.6, 0, 0.06, 0.3, 0.3, "accent"), box(0, 0, 1.4, 0.3, 0.06, "main", 0.3)] },
  tree: { main: "#4E8A4B", accent: "#7A5238", height: 0.8, solids: [pyr(0, 0, 0.22, 0.75, "main")] },
  cloud: { main: "#FFFFFF", accent: "#E9E4DC", height: 2.6, solids: [bill(0, 0, 0.9, 0.35, "main", "disc", 2.2), bill(0.25, 0, 0.6, 0.3, "main", "disc", 2.3)] },
  person: { main: "#3F7F86", accent: "#231A2C", height: 0.7, solids: [bill(0, 0, 0.22, 0.6, "main", "person")] },
  crowd: { main: "#3F7F86", accent: "#CF5140", height: 0.7,
    solids: [[-0.25, -0.2, "main"], [0.1, -0.25, "accent"], [-0.1, 0.1, "#E2AE3A"], [0.25, 0.15, "main"]].map(([x, y, c]) => bill(x as number, y as number, 0.2, 0.55, c as string, "person")) },
  parcel: { main: "#C9A26A", accent: "#8C7A66", height: 0.35, solids: [box(0, 0, 0.35, 0.35, 0.3, "main"), box(0, 0, 0.36, 0.08, 0.005, "accent", 0.3)] },
  cube: { main: "#CF5140", accent: "#231A2C", height: 0.35, solids: [box(0, 0, 0.3, 0.3, 0.3, "main")] },
  coin: { main: "#E2AE3A", accent: "#B88A2A", height: 0.2, solids: [cyl(0, 0, 0.22, 0.08, "main"), cyl(0, 0, 0.22, 0.08, "main", 0.09)] },
  dam: { main: "#A9A39A", accent: "#5A9BCB", height: 0.9, solids: [box(0, 0, 0.5, 1.6, 0.85, "main"), box(0.3, 0, 0.1, 1.4, 0.3, "accent")] },
  silo: { main: "#EFE5D2", accent: "#CF5140", height: 1.5, solids: [cyl(0, 0, 0.3, 1.2, "main"), cone(0, 0, 0.3, 0.3, "accent", 1.2)] },
};

export const PROP_NAMES = Object.keys(PROPS);

/** Half the side of the square a prop's solids stand on, in tiles at scale 1: how far it reaches from its tile's centre. */
export function footprint(solids: Solid[]): number {
  let h = 0;
  for (const s of solids) {
    const hx = "w" in s ? s.w / 2 : s.r;
    const hy = "d" in s ? s.d / 2 : "w" in s ? s.w / 2 : s.r;
    h = Math.max(h, Math.abs(s.x) + hx, Math.abs(s.y) + hy);
  }
  return Math.round(h * 100) / 100;
}

/** A small screen-space isometric cube (chips, Isotype counts, the legend). */
export function miniCube(ctx: Ctx, x: number, y: number, s: number, base: string) {
  const t = tones(base);
  const c = C30 * s, h = s / 2;
  poly(ctx, [[x - c, y - s + h], [x, y], [x, y + s], [x - c, y + h]], t.left);
  poly(ctx, [[x, y], [x + c, y - s + h], [x + c, y + h], [x, y + s]], t.right);
  poly(ctx, [[x, y - s], [x + c, y - s + h], [x, y], [x - c, y - s + h]], t.top);
}
