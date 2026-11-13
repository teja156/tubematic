/*
 * Isometric Infographic's painter: draws one board on the scene's Canvas 2D
 * context at a frame: the floating slab with its strata, the ground areas,
 * the scenery the engine fills in around the agent's props (trees on land,
 * blocks in a city, ripples on water), the props and the moving things in
 * depth order, the routes drawing ahead of their movers, and the clouds.
 * Text (title, readout, pins, legend) is DOM, drawn by IsometricInfographic.tsx.
 *
 * Canvas, not SVG, on purpose of cost: a board is a few hundred flat faces,
 * which as SVG paths cost about 1.7 times System Flow on the CPU renderer.
 * Routes are dashes drawn segment by segment, never stroke-dasharray.
 */
import { BOARD, GEOMETRY, TIMING, type Board, type CustomProp, type IsometricData, type PropItem } from "./contract";
import { AREA_COLORS, INK, PALETTE, PROPS, WARM_WHITE, drawSolid, mix, poly, project, tones, type Look, type PropDef, type Proj, type V2 } from "./kit";
import { dimAt, dropAt, effectAt, lengths, pointAt, projAt, ramp, viewAt } from "./stage";

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

export const colorOf = (name: string | undefined, fallback: string) => (name && PALETTE[name]) || fallback;

export function propDef(what: string, custom: CustomProp[]): PropDef | null {
  const own = custom.find((c) => c.id === what);
  if (own) return { solids: own.solids, main: colorOf(own.main, PALETTE.cream), accent: PALETTE.slate, height: own.height };
  return PROPS[what] ?? null;
}

// ── scenery, worked out once per board ─────────────────────────────────────
type Scenery = { what: "tree" | "block"; x: number; y: number; s: number; h: number; c: string }[];
const SCENERY = new Map<Board, Scenery>();

const distToSeg = (px: number, py: number, a: number[], b: number[]) => {
  const dx = b[0] - a[0], dy = b[1] - a[1];
  const u = Math.max(0, Math.min(1, ((px - a[0]) * dx + (py - a[1]) * dy) / (dx * dx + dy * dy || 1)));
  return Math.hypot(px - a[0] - u * dx, py - a[1] - u * dy);
};

/** Trees on land and forest, blocks in a city: everywhere the agent's props and routes leave free. */
export function scenery(b: Board, index: number): Scenery {
  const hit = SCENERY.get(b);
  if (hit) return hit;
  const r = rng(11 + index * 101);
  const out: Scenery = [];
  const busy = (x: number, y: number, m: number) =>
    b.props.some((p) => Math.abs(p.at[0] - x) < 0.75 + m && Math.abs(p.at[1] - y) < 0.75 + m) ||
    (b.routes ?? []).some((rt) => rt.points.some((p, i) => i > 0 && distToSeg(x, y, rt.points[i - 1], p) < 0.45 + m));
  const CITY = ["#D9C6A5", "#C9B597", "#B9C2C4", "#E3D3B8", "#CDBBA0"];
  for (const a of b.areas) {
    const [x0, y0, x1, y1] = a.rect;
    const step = a.kind === "city" ? 0.78 : a.kind === "forest" ? 0.46 : a.kind === "land" ? 0.62 : 0;
    if (!step) continue;
    for (let gy = y0 + step / 2; gy < y1 - 0.15; gy += step) {
      for (let gx = x0 + step / 2; gx < x1 - 0.15; gx += step) {
        const x = gx + (r() - 0.5) * step * 0.25, y = gy + (r() - 0.5) * step * 0.25;
        const roll = r();
        if (busy(x, y, 0.05)) continue;
        if (a.kind === "city") {
          if (roll < 0.2) continue;
          if (roll < 0.33) out.push({ what: "tree", x, y, s: 0.17, h: 0.55, c: "#5E9A55" });
          else out.push({ what: "block", x, y, s: 0.26 + r() * 0.06, h: 0.28 + r() * r() * 1.1, c: CITY[Math.floor(r() * CITY.length)] });
        } else {
          if (roll < (a.kind === "land" ? 0.55 : 0.3)) continue;
          out.push({ what: "tree", x, y, s: 0.15 + r() * 0.06, h: 0.42 + r() * 0.35, c: r() < 0.3 ? "#5E9A55" : "#4E8A4B" });
        }
      }
    }
  }
  SCENERY.set(b, out);
  return out;
}

// ── the slab ───────────────────────────────────────────────────────────────
const EARTH = ["#9A6B47", "#7E5539", "#634330"];

function slab(ctx: Ctx, pr: Proj, b: Board) {
  const P = (x: number, y: number, z = 0): V2 => project(pr, x, y, z);
  const T = GEOMETRY.slab, N = BOARD;
  // the board floats: a soft shadow on the paper
  ctx.globalAlpha = 0.08;
  poly(ctx, [P(0.6, 0.6, -2.1), P(N + 0.4, 0.6, -2.1), P(N + 0.4, N + 0.4, -2.1), P(0.6, N + 0.4, -2.1)], INK);
  ctx.globalAlpha = 1;
  const layers = [[0, -0.14], [-0.14, -0.42], [-0.42, -0.72], [-0.72, -T]];
  layers.forEach(([za, zb], i) => {
    const c = i === 0 ? mix(AREA_COLORS.sand, INK, 0.05) : EARTH[i - 1];
    poly(ctx, [P(0, N, za), P(N, N, za), P(N, N, zb), P(0, N, zb)], c);
    poly(ctx, [P(N, 0, za), P(N, N, za), P(N, N, zb), P(N, 0, zb)], mix(c, INK, 0.22));
  });
  // ground: the default land, then each area on top
  poly(ctx, [P(0, 0), P(N, 0), P(N, N), P(0, N)], tones(AREA_COLORS.sand).top);
  for (const a of b.areas) {
    const [x0, y0, x1, y1] = a.rect;
    const z = a.kind === "water" ? -0.1 : 0.003;
    poly(ctx, [P(x0, y0, z), P(x1, y0, z), P(x1, y1, z), P(x0, y1, z)], tones(AREA_COLORS[a.kind] ?? AREA_COLORS.land).top);
    if (a.kind === "water") {
      poly(ctx, [P(x0, y0, 0), P(x1, y0, 0), P(x1, y0, -0.1), P(x0, y0, -0.1)], mix(AREA_COLORS.land, INK, 0.1));
    }
    if (a.kind === "road") {
      // lane dashes along the long side
      const long = x1 - x0 >= y1 - y0;
      ctx.fillStyle = WARM_WHITE;
      for (let s = (long ? x0 : y0) + 0.2; s < (long ? x1 : y1) - 0.3; s += 0.6) {
        const m = long ? (y0 + y1) / 2 : (x0 + x1) / 2;
        const q = long ? [P(s, m - 0.03, 0.01), P(s + 0.3, m - 0.03, 0.01), P(s + 0.3, m + 0.03, 0.01), P(s, m + 0.03, 0.01)]
          : [P(m - 0.03, s, 0.01), P(m + 0.03, s, 0.01), P(m + 0.03, s + 0.3, 0.01), P(m - 0.03, s + 0.3, 0.01)];
        poly(ctx, q, WARM_WHITE);
      }
    }
  }
}

function ripples(ctx: Ctx, pr: Proj, b: Board, frame: number) {
  const r = rng(5);
  ctx.strokeStyle = "#FFFFFF";
  ctx.lineWidth = 3 * (pr.k / GEOMETRY.k);
  ctx.lineCap = "round";
  ctx.globalAlpha = 0.55;
  for (const a of b.areas.filter((x) => x.kind === "water")) {
    const [x0, y0, x1, y1] = a.rect;
    const n = Math.round((x1 - x0) * (y1 - y0) * 0.8);
    for (let i = 0; i < n; i++) {
      const y = y0 + 0.2 + r() * (y1 - y0 - 0.4);
      const span = x1 - x0 - 0.6;
      const x = x0 + 0.2 + ((((r() * span + frame * 0.012) % span) + span) % span);
      if (b.props.some((pp) => Math.abs(pp.at[0] - x) < 0.8 && Math.abs(pp.at[1] - y) < 0.8)) continue;
      const p = project(pr, x, y, -0.1), q = project(pr, x + 0.35, y, -0.1);
      ctx.beginPath();
      ctx.moveTo(p[0], p[1]);
      ctx.lineTo(q[0], q[1]);
      ctx.stroke();
    }
  }
  ctx.globalAlpha = 1;
}

// ── routes ─────────────────────────────────────────────────────────────────
/** The dashed route, drawn ahead up to `progress` of its length: a warm-white casing, then coloured dashes. */
function route(ctx: Ctx, pr: Proj, pts: [number, number][], progress: number, color: string, alpha: number) {
  if (progress <= 0) return;
  const acc = lengths(pts);
  const len = acc[acc.length - 1] * progress;
  const s = pr.k / GEOMETRY.k;
  const at = (d: number) => {
    const p = pointAt(pts, acc, d);
    return project(pr, p[0], p[1], 0.02);
  };
  ctx.globalAlpha = alpha * 0.85;
  ctx.strokeStyle = WARM_WHITE;
  ctx.lineWidth = 11 * s;
  ctx.lineCap = "round";
  ctx.lineJoin = "round";
  ctx.beginPath();
  for (let d = 0; d <= len; d += 0.1) {
    const p = at(d);
    d ? ctx.lineTo(p[0], p[1]) : ctx.moveTo(p[0], p[1]);
  }
  const e = at(len);
  ctx.lineTo(e[0], e[1]);
  ctx.stroke();
  ctx.globalAlpha = alpha;
  ctx.strokeStyle = color;
  ctx.lineWidth = 5 * s;
  ctx.lineCap = "butt";
  const dash = 0.28, gap = 0.2;
  for (let d = 0; d < len; d += dash + gap) {
    const a = at(d), b = at(Math.min(len, d + dash));
    ctx.beginPath();
    ctx.moveTo(a[0], a[1]);
    ctx.lineTo(b[0], b[1]);
    ctx.stroke();
  }
  if (progress < 1) {
    ctx.fillStyle = INK;
    ctx.beginPath();
    ctx.arc(e[0], e[1], 7 * s, 0, Math.PI * 2);
    ctx.fill();
  }
  ctx.globalAlpha = 1;
}

// ── a whole board ──────────────────────────────────────────────────────────
type Drawable = { key: number; draw: () => void };

/** A board's still part, drawn once for as long as it does not change (see drawBoard). */
export interface BoardCache {
  canvas: HTMLCanvasElement;
  key: string;
}

export function makeBoardCache(): BoardCache {
  const canvas = document.createElement("canvas");
  canvas.width = 1080;
  canvas.height = 1920;
  return { canvas, key: "" };
}

interface PropState {
  p: PropItem;
  def: PropDef;
  z: number;
  sc: number;
  look: Look;
  lifted: number;
  cut: number;
  settled: boolean;
}

function propStates(data: IsometricData, b: Board, frame: number, dim: { prop: string | null; amount: number }): PropState[] {
  const custom = data.customProps ?? [];
  const out: PropState[] = [];
  for (const p of b.props) {
    const def = propDef(p.what, custom);
    const st = dropAt(p, frame);
    if (!def || !st.visible) continue;
    const lifted = effectAt(b.lifts, p.id, frame, TIMING.lift);
    const cut = effectAt(b.cutaways, p.id, frame, TIMING.cut);
    const spread = effectAt(b.explodes, p.id, frame, TIMING.cut) * 0.35;
    const fade = dim.prop && dim.prop !== p.id ? dim.amount * 0.62 : 0;
    const look: Look = { main: colorOf(p.color, def.main), accent: def.accent, fade, spread };
    const settled = st.lift === 0 && Math.abs(st.squash) < 0.004 && lifted === 0 && cut === 0 && spread === 0;
    out.push({ p, def, z: st.lift + lifted * 0.3, sc: (p.scale ?? 1) * (1 + st.squash * 0.5), look, lifted, cut, settled });
  }
  return out;
}

function drawProp(ctx: Ctx, pr: Proj, data: IsometricData, b: Board, s: PropState, frame: number) {
  const { p, def, z, sc, look, lifted, cut } = s;
  const custom = data.customProps ?? [];
  if (lifted > 0.01) {
    // its shadow left on the ground while it hovers
    ctx.globalAlpha = 0.16 * lifted;
    poly(ctx, [project(pr, p.at[0] - 0.4, p.at[1] - 0.4), project(pr, p.at[0] + 0.4, p.at[1] - 0.4), project(pr, p.at[0] + 0.4, p.at[1] + 0.4), project(pr, p.at[0] - 0.4, p.at[1] + 0.4)], INK);
    ctx.globalAlpha = 1;
  }
  const cutaway = (b.cutaways ?? []).find((c) => c.prop === p.id && c.at <= frame);
  if (cutaway && cut > 0) {
    // the inside: small props on the floor, then the walls fading away
    cutaway.inside.slice(0, 3).forEach((w, i) => {
      const d = propDef(w, custom);
      if (d) for (const so of d.solids) drawSolid(ctx, pr, so, p.at[0] - 0.2 + i * 0.22, p.at[1] - 0.1 + i * 0.12, z, 0.38 * sc, { main: d.main, accent: d.accent, fade: 0, spread: 0 });
    });
    ctx.globalAlpha = 1 - 0.85 * cut;
  }
  for (const so of def.solids) drawSolid(ctx, pr, so, p.at[0], p.at[1], z, sc, look);
  ctx.globalAlpha = 1;
}

function sceneryDrawables(ctx: Ctx, pr: Proj, b: Board, index: number, fade: number): Drawable[] {
  return scenery(b, index).map((s) => ({
    key: s.x + s.y,
    draw: () => {
      const look: Look = { main: s.c, accent: s.c, fade, spread: 0 };
      if (s.what === "tree") drawSolid(ctx, pr, { s: "pyr", x: 0, y: 0, r: s.s, h: s.h, c: "main" }, s.x, s.y, 0, 1, look);
      else drawSolid(ctx, pr, { s: "box", x: 0, y: 0, w: s.s * 2, d: s.s * 2, h: s.h, c: "main" }, s.x, s.y, 0, 1, look);
    },
  }));
}

/**
 * Draws board `b` at `frame`. The still part of the board (the slab, the
 * ground, the routes, the scenery and every prop that is not dropping,
 * lifting, opening or separating) is drawn into `cache` only when it changes
 * (the camera glides, the rest steps back, a prop settles, a route draws on)
 * and placed with the board's drift; the ripples, the moving props, the
 * movers and the clouds are drawn over it every frame. A few hundred faces redrawn on every frame cost
 * about twice System Flow on the CPU renderer.
 */
export function drawBoard(ctx: Ctx, data: IsometricData, b: Board, index: number, frame: number, cache?: BoardCache) {
  const view = viewAt(b, frame);
  const still = projAt(view);
  const drift = { x: Math.sin(frame / 95) * 5, y: Math.sin(frame / 70 + 1) * 3.5 };
  const pr: Proj = { ...still, cx: still.cx + drift.x, cy: still.cy + drift.y };
  const dim = dimAt(b, frame);
  const states = propStates(data, b, frame, dim);
  const fade = Math.round(dim.amount * 100) / 100;
  const settled = states.filter((s) => s.settled);
  const lifted = dim.prop ? 1 - fade * 0.6 : 1;
  const drawn = (b.routes ?? []).map((r) => ramp(frame, r.at, TIMING.draw));
  const key = [index, view.x.toFixed(4), view.y.toFixed(4), view.zoom.toFixed(4), dim.prop ?? "", fade, settled.map((s) => s.p.id).join(","), drawn.map((d) => d.toFixed(3)).join(",")].join("|");
  const paintStill = (c: Ctx, at: Proj) => {
    slab(c, at, b);
    // routes lie on the ground: under the props and the movers that travel them
    (b.routes ?? []).forEach((r, i) => route(c, at, r.points, drawn[i], colorOf(r.color, PALETTE.red), lifted));
    const items = [...sceneryDrawables(c, at, b, index, fade * 0.62), ...settled.map((s) => ({ key: s.p.at[0] + s.p.at[1] + 0.01, draw: () => drawProp(c, at, data, b, s, frame) }))];
    items.sort((a, z) => a.key - z.key);
    for (const it of items) it.draw();
  };
  if (cache) {
    if (cache.key !== key) {
      const cc = cache.canvas.getContext("2d")!;
      cc.clearRect(0, 0, cache.canvas.width, cache.canvas.height);
      paintStill(cc, still);
      cache.key = key;
    }
    ctx.drawImage(cache.canvas, drift.x, drift.y);
  } else {
    paintStill(ctx, pr);
  }
  ripples(ctx, pr, b, frame);

  const custom = data.customProps ?? [];
  const items: Drawable[] = states.filter((s) => !s.settled).map((s) => ({ key: s.p.at[0] + s.p.at[1] + 0.01, draw: () => drawProp(ctx, pr, data, b, s, frame) }));
  for (const m of b.movers ?? []) {
    const rt = (b.routes ?? []).find((r) => r.id === m.route);
    if (!rt || frame < m.at) continue;
    const acc = lengths(rt.points);
    const total = acc[acc.length - 1];
    const k = ramp(frame, m.at, TIMING.move);
    const [x, y] = pointAt(rt.points, acc, m.back ? total * (1 - k) : total * k);
    const def = propDef(m.what, custom);
    if (!def) continue;
    const bob = Math.abs(Math.sin(frame * 0.45)) * 0.08;
    items.push({
      key: x + y + 0.02,
      draw: () => {
        for (const so of def.solids) drawSolid(ctx, pr, so, x, y, 0.06 + bob, 0.55, { main: colorOf(m.color, def.main), accent: def.accent, fade: 0, spread: 0 });
      },
    });
  }
  items.sort((a, c) => a.key - c.key);
  for (const it of items) it.draw();

  // clouds drift over the board, faster than it (parallax)
  for (const [x, y, s, v] of [[900, 668, 0.85, -0.22], [150, 980, 0.75, 0.28]] as const) {
    const cx = x + drift.x * 1.3 + frame * v, cy = y + drift.y * 1.3;
    ctx.fillStyle = "rgba(35,26,44,0.07)";
    ctx.beginPath();
    ctx.ellipse(cx + 4 * s, cy + 40 * s, 70 * s, 14 * s, 0, 0, Math.PI * 2);
    ctx.fill();
    ctx.fillStyle = "#FFFFFF";
    ctx.beginPath();
    ctx.ellipse(cx - 20 * s, cy, 42 * s, 22 * s, 0, 0, Math.PI * 2);
    ctx.ellipse(cx + 18 * s, cy - 8 * s, 40 * s, 28 * s, 0, 0, Math.PI * 2);
    ctx.ellipse(cx + 48 * s, cy + 2 * s, 28 * s, 16 * s, 0, 0, Math.PI * 2);
    ctx.fill();
  }
}

/** Where a prop's pin is anchored on screen at a frame (its top), with the board's drift. */
export function pinAnchor(data: IsometricData, b: Board, p: PropItem, frame: number): V2 {
  const def = propDef(p.what, data.customProps ?? []);
  const pr = projAt(viewAt(b, frame));
  pr.cx += Math.sin(frame / 95) * 5;
  pr.cy += Math.sin(frame / 70 + 1) * 3.5;
  const st = dropAt(p, frame);
  const lifted = effectAt(b.lifts, p.id, frame, TIMING.lift);
  return project(pr, p.at[0], p.at[1], (def?.height ?? 1) * (p.scale ?? 1) + 0.15 + st.lift + lifted * 0.3);
}

/** The paper with its faint dot lattice, drawn once. */
export function paintPaper(c: HTMLCanvasElement) {
  const ctx = c.getContext("2d")!;
  ctx.fillStyle = "#F1E8D8";
  ctx.fillRect(0, 0, c.width, c.height);
  ctx.fillStyle = "rgba(35,26,44,0.13)";
  for (let y = 0; y < c.height; y += 25.4) {
    for (let x = 0; x < c.width; x += 44) {
      ctx.beginPath();
      ctx.arc(x + 2, y + 2, 2, 0, Math.PI * 2);
      ctx.arc(x + 24, y + 14.7, 2, 0, Math.PI * 2);
      ctx.fill();
    }
  }
}
