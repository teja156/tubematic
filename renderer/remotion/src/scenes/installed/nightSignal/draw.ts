/*
 * Night Signal's painter: draws one scene of the picture band on a Canvas 2D
 * context, in band pixels (1080 x 780), as a pure function of the data and the
 * frame. NightSignal.tsx calls it once per frame (twice during a glitch tear)
 * and adds the bloom and the tear on top.
 *
 * Canvas, not SVG, on purpose of cost: on the CPU renderer a scene of SVG
 * pictograms under a blur filter cost several times System Flow; on a canvas
 * the same shapes are a few hundred fills, and the glow is one blurred copy at
 * a quarter of the size.
 */
import {
  GEOMETRY, LIMITS, TIMING, type Bubble, type CameraPanel, type CaseCard, type Connector, type CustomPart, type Item,
  type NightSignalData, type PhoneScreen, type RuleCard, type Scene, type Shape, type Slot, type StepsCard, type Tableau, type Tone,
} from "./contract";
import { libraryShapes, shapesBox } from "./parts";
import { easeInOut, easeOutBack, itemAt, ramp } from "./stage";

export const BW = 1080;
export const BH = GEOMETRY.bandHeight;

export const COLORS = {
  bg: "#111316",
  black: "#050607",
  ink: "#e9e8d0",
  core: "#fbfcf0",
  grey: "#858990",
  dim: "#3d4046",
  red: "#D0303A",
  navy: "#101235",
  green: "#62C96F",
  panel: "#16181b",
} as const;

export const FONT = "Montserrat, 'Helvetica Neue', Arial, sans-serif";

const hex = (h: string) => [1, 3, 5].map((i) => parseInt(h.slice(i, i + 2), 16));
export function mix(a: string, b: string, t: number): string {
  if (t <= 0) return a;
  if (t >= 1) return b;
  const A = hex(a), B = hex(b);
  return "#" + A.map((v, i) => Math.round(v + (B[i] - v) * t).toString(16).padStart(2, "0")).join("");
}

/** A seeded generator (mulberry32): every random-looking thing is a pure function of a seed. */
export function rng(seed: number) {
  let a = seed >>> 0;
  return () => {
    a = (a + 0x6d2b79f5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

type Ctx = CanvasRenderingContext2D;

// ── shapes ──────────────────────────────────────────────────────────────────
export interface ShapeLook {
  /** 0..1: how far ink, core and grey have turned red (the threat). */
  red?: number;
  /** Dark shapes on an ink ground (a bubble's icon, a card's photo). */
  inverted?: boolean;
  /** Blur the last shape, the head of a person: the threat has no face. */
  faceless?: boolean;
  alpha?: number;
}

function toneColor(tone: Tone, look: ShapeLook): string {
  if (look.inverted) {
    return tone === "hole" ? COLORS.ink : tone === "grey" || tone === "dim" ? "#55585e" : tone === "red" ? COLORS.red : COLORS.black;
  }
  if (tone === "hole") return COLORS.bg;
  if (tone === "red") return COLORS.red;
  const base = tone === "core" ? COLORS.core : tone === "grey" ? COLORS.grey : tone === "dim" ? COLORS.dim : COLORS.ink;
  return mix(base, COLORS.red, look.red ?? 0);
}

/** Draws shapes with their origin at (x, y), scaled by s, mirrored when flip is -1. */
export function drawShapes(ctx: Ctx, shapes: Shape[], x: number, y: number, s: number, flip: number, look: ShapeLook = {}) {
  ctx.save();
  ctx.translate(x, y);
  ctx.scale(s * flip, s);
  if (look.alpha !== undefined) ctx.globalAlpha *= look.alpha;
  ctx.lineCap = "round";
  ctx.lineJoin = "round";
  shapes.forEach((sh, i) => {
    const color = toneColor(sh.tone, look);
    if (look.faceless && i === shapes.length - 1 && sh.shape === "circle") {
      // The threat's head, blurred to facelessness: a soft-edged disc from a
      // radial gradient. A canvas blur filter here cost about 0.2 CPU-seconds
      // a frame on the CPU renderer.
      const g = ctx.createRadialGradient(sh.cx, sh.cy, sh.r * 0.3, sh.cx, sh.cy, sh.r * 1.45);
      g.addColorStop(0, color);
      g.addColorStop(0.55, color);
      g.addColorStop(1, mix(color, COLORS.bg, 1) + "00");
      ctx.fillStyle = g;
      ctx.beginPath();
      ctx.arc(sh.cx, sh.cy, sh.r * 1.45, 0, Math.PI * 2);
      ctx.fill();
      return;
    }
    if (sh.shape === "circle") {
      ctx.fillStyle = color;
      ctx.beginPath();
      ctx.arc(sh.cx, sh.cy, Math.max(0, sh.r), 0, Math.PI * 2);
      ctx.fill();
    } else if (sh.shape === "rect") {
      ctx.fillStyle = color;
      ctx.beginPath();
      ctx.roundRect(sh.x, sh.y, sh.w, sh.h, Math.max(0, Math.min(sh.r ?? 0, Math.abs(sh.w) / 2, Math.abs(sh.h) / 2)));
      ctx.fill();
    } else if (sh.shape === "line") {
      if (sh.points.length < 2) return;
      ctx.strokeStyle = color;
      ctx.lineWidth = sh.width;
      ctx.beginPath();
      sh.points.forEach((p, k) => (k ? ctx.lineTo(p[0], p[1]) : ctx.moveTo(p[0], p[1])));
      ctx.stroke();
    } else {
      if (sh.points.length < 3) return;
      ctx.fillStyle = color;
      ctx.beginPath();
      sh.points.forEach((p, k) => (k ? ctx.lineTo(p[0], p[1]) : ctx.moveTo(p[0], p[1])));
      ctx.closePath();
      ctx.fill();
    }
  });
  ctx.restore();
}

// ── the QR code ─────────────────────────────────────────────────────────────
const QR_N = 21;
const QR: boolean[][] = (() => {
  const r = rng(4242);
  const g: boolean[][] = [];
  for (let y = 0; y < QR_N; y++) {
    g.push([]);
    for (let x = 0; x < QR_N; x++) g[y].push(r() > 0.52);
  }
  const finder = (ox: number, oy: number) => {
    for (let y = -1; y < 8; y++)
      for (let x = -1; x < 8; x++) {
        const gx = ox + x, gy = oy + y;
        if (gx < 0 || gy < 0 || gx >= QR_N || gy >= QR_N) continue;
        const inside = x >= 0 && y >= 0 && x < 7 && y < 7;
        const ring = inside && (x === 0 || y === 0 || x === 6 || y === 6);
        const core = x >= 2 && x <= 4 && y >= 2 && y <= 4;
        g[gy][gx] = inside && (ring || core);
      }
  };
  finder(0, 0);
  finder(14, 0);
  finder(0, 14);
  return g;
})();

export function drawQR(ctx: Ctx, x: number, y: number, size: number, fg: string, bg?: string) {
  const m = size / QR_N;
  if (bg) {
    ctx.fillStyle = bg;
    ctx.beginPath();
    ctx.roundRect(x - m * 2, y - m * 2, size + m * 4, size + m * 4, m * 1.4);
    ctx.fill();
  }
  ctx.fillStyle = fg;
  for (let gy = 0; gy < QR_N; gy++) for (let gx = 0; gx < QR_N; gx++) if (QR[gy][gx]) ctx.fillRect(x + gx * m, y + gy * m, m * 1.04, m * 1.04);
}

// ── parts by name ───────────────────────────────────────────────────────────
export function partShapes(what: string, custom: CustomPart[]): Shape[] | null {
  const own = custom.find((c) => c.id === what);
  return own ? own.shapes : libraryShapes(what);
}

/** Draws a named part (library or custom) standing at (x, y). The QR code is drawn as itself. */
export function drawPart(ctx: Ctx, what: string, custom: CustomPart[], x: number, y: number, s: number, flip: number, look: ShapeLook = {}) {
  if (what === "qr") {
    const size = 180 * s;
    drawQR(ctx, x - size / 2, y - size - 20 * s, size, look.inverted ? COLORS.black : COLORS.black, look.inverted ? undefined : COLORS.ink);
    return;
  }
  const shapes = partShapes(what, custom);
  if (shapes) drawShapes(ctx, shapes, x, y, s, flip, { ...look, faceless: look.faceless && what.startsWith("person") });
}

/** Draws a part scaled to fit a box centred on (cx, cy), its feet at the box's foot. */
export function drawPartInBox(ctx: Ctx, what: string, custom: CustomPart[], cx: number, cy: number, box: number, look: ShapeLook = {}) {
  if (what === "qr") {
    drawQR(ctx, cx - box * 0.42, cy - box * 0.42, box * 0.84, look.inverted ? COLORS.black : COLORS.ink);
    return;
  }
  const shapes = partShapes(what, custom);
  if (!shapes) return;
  const [x0, y0, x1, y1] = shapesBox(shapes);
  const s = Math.min(box / Math.max(1, x1 - x0), box / Math.max(1, y1 - y0));
  drawShapes(ctx, shapes, cx - ((x0 + x1) / 2) * s, cy - ((y0 + y1) / 2) * s, s, 1, look);
}

// ── text ───────────────────────────────────────────────────────────────────
export function text(ctx: Ctx, s: string, x: number, y: number, size: number, color: string, opts: { weight?: number; spacing?: number; align?: CanvasTextAlign; maxWidth?: number } = {}) {
  let px = size;
  ctx.font = `${opts.weight ?? 700} ${px}px ${FONT}`;
  (ctx as unknown as { letterSpacing: string }).letterSpacing = `${opts.spacing ?? 0}px`;
  if (opts.maxWidth) {
    while (px > 12 && ctx.measureText(s).width > opts.maxWidth) {
      px -= 2;
      ctx.font = `${opts.weight ?? 700} ${px}px ${FONT}`;
    }
  }
  ctx.fillStyle = color;
  ctx.textAlign = opts.align ?? "left";
  ctx.textBaseline = "alphabetic";
  ctx.fillText(s, x, y);
  (ctx as unknown as { letterSpacing: string }).letterSpacing = "0px";
}

// ── dotted paths ───────────────────────────────────────────────────────────
/** A dotted quadratic curve from a to b over control c, drawn up to `progress`, its dots marching. */
export function drawDots(ctx: Ctx, a: [number, number], c: [number, number], b: [number, number], progress: number, march: number, color: string, r = 5.5) {
  if (progress <= 0) return;
  const pts: [number, number][] = [];
  const N = 120;
  for (let i = 0; i <= N; i++) {
    const t = i / N;
    pts.push([(1 - t) ** 2 * a[0] + 2 * (1 - t) * t * c[0] + t * t * b[0], (1 - t) ** 2 * a[1] + 2 * (1 - t) * t * c[1] + t * t * b[1]]);
  }
  const lens = [0];
  for (let i = 1; i < pts.length; i++) lens.push(lens[i - 1] + Math.hypot(pts[i][0] - pts[i - 1][0], pts[i][1] - pts[i - 1][1]));
  const total = lens[lens.length - 1] * progress;
  ctx.fillStyle = color;
  const gap = 24;
  let k = 0;
  for (let d = ((march % gap) + gap) % gap; d <= total; d += gap) {
    while (k < lens.length - 2 && lens[k + 1] < d) k++;
    const seg = lens[k + 1] - lens[k] || 1;
    const t = (d - lens[k]) / seg;
    ctx.beginPath();
    ctx.arc(pts[k][0] + (pts[k + 1][0] - pts[k][0]) * t, pts[k][1] + (pts[k + 1][1] - pts[k][1]) * t, r, 0, Math.PI * 2);
    ctx.fill();
  }
}

// ── settings ───────────────────────────────────────────────────────────────
function stars(ctx: Ctx, frame: number, seed: number, n: number, box: [number, number, number, number]) {
  const r = rng(seed);
  ctx.fillStyle = COLORS.ink;
  for (let i = 0; i < n; i++) {
    const x = box[0] + r() * (box[2] - box[0]);
    const y = box[1] + r() * (box[3] - box[1]);
    const ph = r() * 6.28;
    const rr = 2.5 + r() * 2;
    ctx.globalAlpha = 0.8 * (0.35 + 0.65 * Math.max(0, Math.sin(frame * 0.16 + ph)));
    ctx.beginPath();
    ctx.arc(x, y, rr, 0, Math.PI * 2);
    ctx.fill();
  }
  ctx.globalAlpha = 1;
}

function ground(ctx: Ctx, y: number, x0 = 40, x1 = 1040) {
  ctx.strokeStyle = COLORS.ink;
  ctx.globalAlpha = 0.85;
  ctx.lineWidth = 5;
  ctx.lineCap = "round";
  ctx.beginPath();
  ctx.moveTo(x0, y);
  ctx.lineTo(x1, y);
  ctx.stroke();
  ctx.globalAlpha = 1;
}

function setting(ctx: Ctx, scene: Tableau, frame: number, seed: number) {
  const G = GEOMETRY.ground;
  if (scene.setting === "night") {
    stars(ctx, frame, seed, 11, [80, 30, 1000, 300]);
    drawShapes(ctx, libraryShapes("moon")!, 905, 480, 1, 1);
  } else if (scene.setting === "street") {
    stars(ctx, frame, seed, 5, [80, 30, 700, 220]);
    ctx.fillStyle = COLORS.ink;
    ctx.globalAlpha = 0.05 + 0.02 * Math.sin(frame * 0.9);
    ctx.beginPath();
    ctx.moveTo(1010, G - 380);
    ctx.lineTo(950, G);
    ctx.lineTo(1070, G);
    ctx.fill();
    ctx.globalAlpha = 1;
    drawShapes(ctx, libraryShapes("lamp")!, 1010, G, 0.97, 1);
  } else if (scene.setting === "room") {
    ctx.strokeStyle = COLORS.dim;
    ctx.lineWidth = 4;
    ctx.beginPath();
    ctx.moveTo(40, 90);
    ctx.lineTo(1040, 90);
    ctx.stroke();
    drawShapes(ctx, libraryShapes("window")!, 540, G - 30, 0.9, 1, { alpha: 0.55 });
  }
  ground(ctx, G);
}

// ── items, connectors and bubbles ──────────────────────────────────────────
function drawItems(ctx: Ctx, items: Item[], custom: CustomPart[], frame: number, groundY: number, s: number, slotX: (sl: Slot) => number) {
  // Objects first, then animals and people, so a figure stands in front of a door.
  const order = [...items].sort((a, b) => Number(a.what.startsWith("person")) - Number(b.what.startsWith("person")));
  for (const it of order) {
    const st = itemAt(it, frame, slotX);
    if (!st.visible || st.scale <= 0) continue;
    drawPart(ctx, it.what, custom, st.x, groundY, s * st.scale, st.facing, { red: st.red, faceless: !!it.threat && st.red > 0.5 });
  }
}

function connector(ctx: Ctx, c: Connector, frame: number, y: number, slotX: (sl: Slot) => number, s: number) {
  const a: [number, number] = [slotX(c.from), y];
  const b: [number, number] = [slotX(c.to), y];
  const mid: [number, number] = [(a[0] + b[0]) / 2, y - 220 * s];
  drawDots(ctx, a, mid, b, easeInOut(ramp(frame, c.at, TIMING.connector)), frame * 1.4, COLORS.grey, 5.5 * s + 1);
}

function bubble(ctx: Ctx, b: Bubble, custom: CustomPart[], frame: number) {
  const p = Math.max(0, easeOutBack(ramp(frame, b.at, TIMING.pop)));
  if (p <= 0) return;
  const x = Math.min(1040 - 130, Math.max(40 + 130, GEOMETRY.slotX[b.over] + 60));
  const cy = 166;
  ctx.save();
  ctx.translate(x, cy + 130);
  ctx.scale(p, p);
  ctx.translate(-x, -(cy + 130));
  ctx.fillStyle = COLORS.ink;
  if ((b.kind ?? "thought") === "thought") {
    ctx.beginPath();
    ctx.arc(x - 30, cy + 162, 14, 0, Math.PI * 2);
    ctx.arc(x - 52, cy + 196, 9, 0, Math.PI * 2);
    ctx.fill();
  } else {
    ctx.beginPath();
    ctx.moveTo(x - 50, cy + 110);
    ctx.lineTo(x - 70, cy + 180);
    ctx.lineTo(x - 10, cy + 110);
    ctx.fill();
  }
  ctx.beginPath();
  ctx.roundRect(x - 125, cy - 110, 250, 250, 34);
  ctx.fill();
  drawPartInBox(ctx, b.icon, custom, x, cy + 15, 190, { inverted: true });
  // the scanner glint over a code, a running loop
  if (b.icon === "qr") {
    ctx.fillStyle = COLORS.core;
    ctx.globalAlpha = 0.5;
    ctx.fillRect(x - 85, cy - 65 + ((frame * 6) % 160), 170, 6);
    ctx.globalAlpha = 1;
  }
  ctx.restore();
}

// ── scenes ─────────────────────────────────────────────────────────────────
function tableau(ctx: Ctx, s: Tableau, custom: CustomPart[], frame: number, seed: number) {
  setting(ctx, s, frame, seed);
  const slotX = (sl: Slot) => GEOMETRY.slotX[sl];
  if (s.connector) connector(ctx, s.connector, frame, GEOMETRY.ground - 250, slotX, 1);
  drawItems(ctx, s.items, custom, frame, GEOMETRY.ground, 1, slotX);
  if (s.bubble) bubble(ctx, s.bubble, custom, frame);
}

/** The camera's clock: the scene's `clock` (HH:MM) running on with the video, on a 12-hour face. */
export function clockText(clock: string | undefined, frame: number, fps: number): string {
  const m = /^(\d\d):(\d\d)$/.exec(clock ?? "") ?? ["", "03", "12"];
  const secs = (Number(m[1]) * 60 + Number(m[2])) * 60 + Math.floor(frame / fps);
  const h24 = Math.floor(secs / 3600) % 24;
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${h24 % 12 || 12}:${pad(Math.floor(secs / 60) % 60)}:${pad(secs % 60)} ${h24 < 12 ? "AM" : "PM"}`;
}

function camera(ctx: Ctx, s: CameraPanel, custom: CustomPart[], frame: number, fps: number, clock: string | undefined) {
  ctx.fillStyle = COLORS.panel;
  ctx.strokeStyle = COLORS.ink;
  ctx.lineWidth = 9;
  ctx.beginPath();
  ctx.roundRect(36, 36, 1008, 650, 40);
  ctx.fill();
  ctx.stroke();
  ctx.save();
  ctx.beginPath();
  ctx.roundRect(64, 64, 952, 470, 20);
  ctx.clip();
  ctx.fillStyle = "#30333a";
  ctx.fillRect(64, 64, 952, 240);
  ctx.fillStyle = "#24272c";
  ctx.fillRect(64, 304, 952, 240);
  // the camera's hum band, a running loop
  ctx.fillStyle = COLORS.core;
  ctx.globalAlpha = 0.035;
  ctx.fillRect(64, ((frame * 3.2) % 620) + 40, 952, 40);
  ctx.globalAlpha = 1;
  const floor = GEOMETRY.cameraGround;
  ctx.fillStyle = "#17191c";
  ctx.fillRect(64, floor, 952, 70);
  ctx.strokeStyle = COLORS.ink;
  ctx.globalAlpha = 0.7;
  ctx.lineWidth = 4;
  ctx.beginPath();
  ctx.moveTo(64, floor);
  ctx.lineTo(1016, floor);
  ctx.stroke();
  ctx.globalAlpha = 1;
  const slotX = (sl: Slot) => 64 + (GEOMETRY.slotX[sl] / BW) * 952;
  const sc = GEOMETRY.cameraScale;
  if (s.connector) connector(ctx, s.connector, frame, floor - 160 * sc, slotX, sc);
  drawItems(ctx, s.items, custom, frame, floor, sc, slotX);
  // REC dot and the time
  ctx.fillStyle = COLORS.red;
  ctx.globalAlpha = Math.floor(frame / 12) % 2 === 0 ? 1 : 0.25;
  ctx.beginPath();
  ctx.arc(104, 118, 11, 0, Math.PI * 2);
  ctx.fill();
  ctx.globalAlpha = 1;
  text(ctx, clockText(clock, frame, fps), 128, 133, 40, COLORS.ink);
  ctx.restore();
  text(ctx, s.label.toUpperCase(), 84, 636, 40, COLORS.grey, { weight: 600, spacing: 5, maxWidth: s.button ? 740 : 920 });
  if (s.button) {
    ctx.strokeStyle = COLORS.grey;
    ctx.lineWidth = 5;
    ctx.beginPath();
    ctx.roundRect(858, 584, 150, 72, 36);
    ctx.stroke();
    text(ctx, s.button.text.toUpperCase(), 933, 634, 40, COLORS.grey, { align: "center", maxWidth: 124 });
    if (s.button.crossAt !== undefined) {
      const k = easeInOut(ramp(frame, s.button.crossAt, TIMING.mark));
      if (k > 0) {
        ctx.strokeStyle = COLORS.red;
        ctx.lineWidth = 7;
        ctx.lineCap = "round";
        ctx.beginPath();
        ctx.moveTo(870, 650);
        ctx.lineTo(870 + 128 * k, 650 - 60 * k);
        ctx.stroke();
      }
    }
  }
}

function mark(ctx: Ctx, kind: "check" | "cross", x: number, y: number, k: number) {
  if (k <= 0) return;
  ctx.save();
  ctx.translate(x, y);
  ctx.scale(k, k);
  ctx.fillStyle = kind === "check" ? COLORS.green : COLORS.red;
  ctx.beginPath();
  ctx.arc(0, 0, 34, 0, Math.PI * 2);
  ctx.fill();
  ctx.strokeStyle = COLORS.black;
  ctx.lineWidth = 10;
  ctx.lineCap = "round";
  ctx.lineJoin = "round";
  ctx.beginPath();
  if (kind === "check") {
    ctx.moveTo(-15, 0);
    ctx.lineTo(-3, 12);
    ctx.lineTo(17, -12);
  } else {
    ctx.moveTo(-13, -13);
    ctx.lineTo(13, 13);
    ctx.moveTo(13, -13);
    ctx.lineTo(-13, 13);
  }
  ctx.stroke();
  ctx.restore();
}

function phone(ctx: Ctx, s: PhoneScreen, frame: number) {
  const f = frame - s.start;
  // you, behind a table, reaching for the phone
  drawShapes(ctx, personShapesBehindTable(), 250, 872, 1.7, 1);
  ctx.fillStyle = COLORS.ink;
  ctx.beginPath();
  ctx.roundRect(30, 688, 1020, 22, 8);
  ctx.fill();
  ctx.fillStyle = COLORS.grey;
  ctx.fillRect(90, 710, 18, 80);
  ctx.fillRect(972, 710, 18, 80);
  const px = 510, py = 50, pw = 400, ph = 640;
  ctx.fillStyle = COLORS.black;
  ctx.strokeStyle = COLORS.ink;
  ctx.lineWidth = 14;
  ctx.beginPath();
  ctx.roundRect(px, py, pw, ph, 52);
  ctx.fill();
  ctx.stroke();
  ctx.fillStyle = COLORS.ink;
  ctx.beginPath();
  ctx.roundRect(px + pw / 2 - 40, py + 22, 80, 12, 6);
  ctx.fill();
  text(ctx, s.title.toUpperCase(), px + 40, py + 112, 42, COLORS.ink, { spacing: 2, maxWidth: pw - 150 });
  const lineIn = (i: number) => clamp(ramp(f, 4 + i * 8, 10));
  if (s.screen === "message" || s.screen === "alert") {
    if (s.screen === "alert") drawShapes(ctx, libraryShapes("warning")!, px + pw / 2, py + 330, 0.62, 1, { red: 0 });
    const top = s.screen === "alert" ? py + 360 : py + 160;
    s.lines.forEach((l, i) => {
      const k = lineIn(i);
      if (k <= 0) return;
      const y = top + i * 110 + (1 - easeInOut(k)) * 30;
      ctx.globalAlpha = k;
      ctx.fillStyle = COLORS.ink;
      ctx.beginPath();
      ctx.roundRect(px + 28, y, pw - 56, 90, 24);
      ctx.fill();
      text(ctx, l, px + 52, y + 60, 40, COLORS.black, { maxWidth: pw - 104 });
      ctx.globalAlpha = 1;
    });
  } else if (s.screen === "link") {
    drawQR(ctx, px + 40, py + 146, 84, COLORS.grey);
    const tap = (frame % 40) / 40;
    ctx.strokeStyle = COLORS.ink;
    ctx.lineWidth = 4;
    ctx.globalAlpha = (1 - tap) * 0.6;
    ctx.beginPath();
    ctx.arc(px + 82, py + 188, 20 + tap * 60, 0, Math.PI * 2);
    ctx.stroke();
    ctx.globalAlpha = 1;
    const k = easeInOut(ramp(f, 3, 13));
    const cardY = py + 250 + (1 - k) * 240;
    if (k > 0) {
      ctx.fillStyle = COLORS.ink;
      ctx.beginPath();
      ctx.roundRect(px + 28, cardY, pw - 56, 250, 26);
      ctx.fill();
      s.lines.forEach((l, i) => text(ctx, l, px + 56, cardY + 70 + i * 64, i === 0 ? 40 : 46, i === 0 ? "#55585e" : COLORS.black, { maxWidth: pw - 112 }));
    }
  } else if (s.screen === "qr") {
    const cx = px + pw / 2, cy = py + 320;
    drawQR(ctx, cx - 90, cy - 90, 180, COLORS.ink);
    ctx.strokeStyle = COLORS.grey;
    ctx.lineWidth = 8;
    ctx.lineCap = "round";
    for (const [sx, sy] of [[-1, -1], [1, -1], [-1, 1], [1, 1]]) {
      ctx.beginPath();
      ctx.moveTo(cx + sx * 112, cy + sy * 80);
      ctx.lineTo(cx + sx * 112, cy + sy * 112);
      ctx.lineTo(cx + sx * 80, cy + sy * 112);
      ctx.stroke();
    }
    ctx.fillStyle = COLORS.core;
    ctx.fillRect(cx - 104, cy + 92 * Math.sin(frame * 0.28) - 3, 208, 6);
    s.lines.forEach((l, i) => text(ctx, l, cx, py + 520 + i * 52, 36, COLORS.grey, { align: "center", weight: 600, spacing: 3, maxWidth: pw - 80 }));
  } else {
    const cx = px + pw / 2;
    const pulse = (frame % 30) / 30;
    ctx.strokeStyle = COLORS.ink;
    ctx.lineWidth = 4;
    ctx.globalAlpha = 1 - pulse;
    ctx.beginPath();
    ctx.arc(cx, py + 280, 90 + pulse * 50, 0, Math.PI * 2);
    ctx.stroke();
    ctx.globalAlpha = 1;
    drawPartInBox(ctx, "person", [], cx, py + 280, 150);
    s.lines.forEach((l, i) => text(ctx, l, cx, py + 450 + i * 52, 38, COLORS.grey, { align: "center", weight: 600, spacing: 3, maxWidth: pw - 80 }));
    for (const [dx, c] of [[-90, COLORS.grey], [90, COLORS.dim]] as const) {
      ctx.fillStyle = c;
      ctx.beginPath();
      ctx.arc(cx + dx, py + 580, 34, 0, Math.PI * 2);
      ctx.fill();
    }
  }
  if (s.mark) mark(ctx, s.mark.kind, px + pw - 66, py + 97, Math.max(0, easeOutBack(ramp(frame, s.mark.at, TIMING.mark))));
}

const clamp = (v: number) => Math.max(0, Math.min(1, v));

/** You, seen from the waist up behind the phone scene's table, reaching for the phone. */
function personShapesBehindTable(): Shape[] {
  return [
    { shape: "rect", x: -44, y: -238, w: 88, h: 136, r: 36, tone: "ink" },
    { shape: "line", points: [[30, -205], [104, -178], [158, -246]], width: 44, tone: "hole" },
    { shape: "line", points: [[30, -205], [104, -178], [158, -246]], width: 28, tone: "ink" },
    { shape: "circle", cx: 10, cy: -286, r: 38, tone: "ink" },
  ];
}

function rule(ctx: Ctx, s: RuleCard, custom: CustomPart[], frame: number) {
  const f = frame - s.start;
  text(ctx, "RULE", 96, 320, 128, COLORS.ink, { spacing: 6 });
  text(ctx, String(s.number).padStart(2, "0"), 100, 440, 96, "#c9ccd2", { spacing: 8 });
  ctx.fillStyle = COLORS.red;
  ctx.beginPath();
  ctx.roundRect(100, 482, 350 * easeInOut(ramp(f, 1, TIMING.underline)), 8, 4);
  ctx.fill();
  s.lines.forEach((l, i) => text(ctx, l.toUpperCase(), 100, 566 + i * 52, 40, COLORS.grey, { weight: 600, spacing: 6, maxWidth: 400 }));
  const cx = 770, cy = 385, R = 214;
  drawPartInBox(ctx, s.icon, custom, cx, cy, 250);
  const ring = easeInOut(ramp(f, TIMING.ringStart, TIMING.ringFrames));
  const slashAt = (s.slashAt ?? s.start + TIMING.slashDelay) - s.start;
  const slash = easeInOut(ramp(f, slashAt, TIMING.slashFrames));
  ctx.strokeStyle = COLORS.red;
  ctx.lineWidth = 26;
  ctx.lineCap = "round";
  if (ring > 0) {
    const a0 = (-130 * Math.PI) / 180;
    ctx.beginPath();
    ctx.arc(cx, cy, R, a0, a0 + Math.PI * 2 * ring);
    ctx.stroke();
  }
  if (slash > 0) {
    ctx.beginPath();
    ctx.moveTo(cx - R * 0.707, cy - R * 0.707);
    ctx.lineTo(cx - R * 0.707 + R * 1.414 * slash, cy - R * 0.707 + R * 1.414 * slash);
    ctx.stroke();
  }
}

function caseCard(ctx: Ctx, s: CaseCard, custom: CustomPart[], frame: number) {
  ctx.fillStyle = "#1a1c20";
  ctx.strokeStyle = COLORS.ink;
  ctx.lineWidth = 6;
  ctx.beginPath();
  ctx.roundRect(70, 60, 940, 640, 24);
  ctx.fill();
  ctx.stroke();
  text(ctx, `${s.label.toUpperCase()}:`, 120, 150, 44, COLORS.grey, { weight: 600, spacing: 5, maxWidth: 360 });
  text(ctx, s.name.toUpperCase(), 120 + Math.min(360, (s.label.length + 2) * 44 * 0.78), 150, 52, COLORS.ink, { spacing: 4, maxWidth: 480 });
  // the ID photo
  ctx.fillStyle = COLORS.ink;
  ctx.beginPath();
  ctx.roundRect(120, 210, 300, 380, 14);
  ctx.fill();
  drawPartInBox(ctx, s.icon, custom, 270, 420, 280, { inverted: true });
  // redaction bars, drawn on one after another
  const n = Math.max(LIMITS.minBars, Math.min(LIMITS.maxBars, s.bars));
  for (let i = 0; i < n; i++) {
    const k = easeInOut(ramp(frame - s.start, 4 + i * 5, 8));
    ctx.fillStyle = COLORS.grey;
    ctx.globalAlpha = i % 2 ? 0.75 : 1;
    ctx.fillRect(470, 240 + i * 90, (i % 2 ? 360 : 480) * k, 44);
    ctx.globalAlpha = 1;
  }
  if (s.stamp) {
    const k = Math.max(0, easeOutBack(ramp(frame, s.stamp.at, TIMING.mark)));
    if (k > 0) {
      ctx.save();
      ctx.translate(690, 600);
      ctx.rotate((-12 * Math.PI) / 180);
      ctx.scale(1.6 - 0.6 * k, 1.6 - 0.6 * k);
      ctx.globalAlpha = Math.min(1, k * 2);
      ctx.strokeStyle = COLORS.red;
      ctx.lineWidth = 8;
      ctx.beginPath();
      ctx.roundRect(-200, -60, 400, 100, 10);
      ctx.stroke();
      text(ctx, s.stamp.text.toUpperCase(), 0, 12, 60, COLORS.red, { align: "center", spacing: 6, maxWidth: 360 });
      ctx.restore();
    }
  }
}

function steps(ctx: Ctx, s: StepsCard, frame: number) {
  ctx.fillStyle = COLORS.navy;
  ctx.beginPath();
  ctx.roundRect(40, 40, 1000, 700, 30);
  ctx.fill();
  text(ctx, s.title.toUpperCase(), 100, 150, 56, COLORS.ink, { spacing: 4, maxWidth: 880 });
  ctx.fillStyle = COLORS.red;
  ctx.fillRect(100, 182, 120, 8);
  s.steps.forEach((st, i) => {
    const k = easeInOut(ramp(frame, st.at, TIMING.stepIn));
    if (k <= 0) return;
    const y = 270 + i * 120;
    ctx.globalAlpha = k;
    const x = 100 + (1 - k) * 60;
    ctx.strokeStyle = COLORS.ink;
    ctx.lineWidth = 5;
    ctx.beginPath();
    ctx.roundRect(x, y, 70, 70, 10);
    ctx.stroke();
    text(ctx, String(i + 1), x + 35, y + 52, 44, COLORS.ink, { align: "center" });
    text(ctx, st.text.toUpperCase(), x + 100, y + 50, 42, COLORS.ink, { weight: 600, spacing: 2, maxWidth: 780 });
    ctx.globalAlpha = 1;
  });
}

/** Draws scene `scene` at `frame` on a band-sized context, its own push applied around the band's centre. */
export function drawScene(ctx: Ctx, data: NightSignalData, scene: Scene, index: number, frame: number, fps: number, push: number) {
  const custom = data.customParts ?? [];
  ctx.save();
  ctx.translate(BW / 2, BH / 2);
  ctx.scale(push, push);
  ctx.translate(-BW / 2, -BH / 2);
  switch (scene.kind) {
    case "tableau":
      tableau(ctx, scene, custom, frame, 11 + index * 7);
      break;
    case "camera":
      camera(ctx, scene, custom, frame, fps, data.clock);
      break;
    case "phone":
      phone(ctx, scene, frame);
      break;
    case "rule":
      rule(ctx, scene, custom, frame);
      break;
    case "case":
      caseCard(ctx, scene, custom, frame);
      break;
    case "steps":
      steps(ctx, scene, frame);
      break;
  }
  ctx.restore();
}
