/*
 * The Editorial Collage's paper pieces, each painted ONCE onto a canvas before
 * the first frame: the desk's fibre tile, torn clippings and black cards, the
 * desk scraps, the ruled index cards, the taped prints, the cut-out stickers
 * and the red paper arrow. The component only copies and moves them.
 *
 * Why canvases (measured on the CPU renderer, software GL): an <img> or
 * Remotion <Img> costs about twice a canvas painted once with the same
 * picture, and per-frame SVG filters, blend modes and large CSS gradients cost
 * from 2x to 100x. A gradient or a shadow drawn here is drawn once.
 */
import { COLORS, DESK, H, NOTES, W } from "./contract";
import { seeded } from "./stage";

export const SERIF = "'Source Serif 4', Georgia, serif";
export const GROTESK = "'Bricolage Grotesque', 'Arial Black', Arial, sans-serif";
export const TYPED = "'Special Elite', 'Courier New', monospace";

type Edges = { top?: number; right?: number; bottom?: number; left?: number };

export function makeCanvas(w: number, h: number): [HTMLCanvasElement, CanvasRenderingContext2D] {
  const c = document.createElement("canvas");
  c.width = Math.max(1, Math.ceil(w));
  c.height = Math.max(1, Math.ceil(h));
  return [c, c.getContext("2d")!];
}

/** A w x h rectangle with torn edges (each number is the edge's roughness in px), as points. */
export function tornPoints(w: number, h: number, seed: number, e: Edges, grow = 0): [number, number][] {
  const r = seeded(seed);
  const pts: [number, number][] = [];
  const edge = (x0: number, y0: number, x1: number, y1: number, rough: number, nx: number, ny: number) => {
    const len = Math.hypot(x1 - x0, y1 - y0);
    const n = Math.max(2, Math.round(len / (rough > 0 ? 11 : 200)));
    for (let i = 0; i < n; i++) {
      const t = i / n;
      let off = rough > 0 ? (r() - 0.5) * 2 * rough : 0;
      if (rough > 0 && r() < 0.07) off -= rough * 1.8;
      pts.push([x0 + (x1 - x0) * t + nx * (off + grow), y0 + (y1 - y0) * t + ny * (off + grow)]);
    }
  };
  edge(0, 0, w, 0, e.top ?? 0, 0, -1);
  edge(w, 0, w, h, e.right ?? 0, 1, 0);
  edge(w, h, 0, h, e.bottom ?? 0, 0, 1);
  edge(0, h, 0, 0, e.left ?? 0, -1, 0);
  return pts;
}

function poly(g: CanvasRenderingContext2D, pts: [number, number][], dx = 0, dy = 0) {
  g.beginPath();
  pts.forEach(([x, y], i) => (i ? g.lineTo(x + dx, y + dy) : g.moveTo(x + dx, y + dy)));
  g.closePath();
}

/** Torn paper on a canvas with `pad` around it: a weak hard shadow, a pale fibre fringe, then the paper. */
export function tornPaper(w: number, h: number, seed: number, fill: string, edges: Edges, opts: { fringe?: string; shadow?: number; pad?: number } = {}): HTMLCanvasElement {
  const pad = opts.pad ?? 24;
  const [c, g] = makeCanvas(w + 2 * pad, h + 2 * pad);
  g.translate(pad, pad);
  const fringe = tornPoints(w, h, seed + 101, edges, 4);
  g.fillStyle = `rgba(23,23,22,${opts.shadow ?? 0.2})`;
  poly(g, fringe, 4, 7);
  g.fill();
  g.fillStyle = opts.fringe ?? "#F4F0E6";
  poly(g, fringe);
  g.fill();
  g.fillStyle = fill;
  poly(g, tornPoints(w, h, seed, edges));
  g.fill();
  return c;
}

/** The desk's repeating fibre texture: a tile of (W + tile) x (H + tile) that
 *  repeats every DESK.tile pixels both ways, so it can be shifted under the
 *  camera by up to one period and always cover the frame. */
export function paintDesk(): HTMLCanvasElement {
  const P = DESK.tile;
  const [c, g] = makeCanvas(W + P, H + P);
  g.fillStyle = COLORS.desk;
  g.fillRect(0, 0, c.width, c.height);
  const r = seeded(4117);
  const blots = Array.from({ length: 3 }, () => [r() * P, r() * P, 260 + r() * 260] as const);
  const fibres = Array.from({ length: 900 }, () => {
    const x = r() * P, y = r() * P, a = r() * Math.PI * 2, l = 10 + r() * 34;
    return { x, y, a, l, bx: (r() - 0.5) * 8, by: (r() - 0.5) * 8, light: r() < 0.35 };
  });
  for (let ox = 0; ox < c.width + P; ox += P) {
    for (let oy = 0; oy < c.height + P; oy += P) {
      for (const [bx, by, br] of blots) {
        for (const [sx, sy] of [[0, 0], [-P, 0], [0, -P], [-P, -P]]) {
          const x = bx + ox + sx, y = by + oy + sy;
          const grad = g.createRadialGradient(x, y, 0, x, y, br);
          grad.addColorStop(0, "rgba(207,196,173,0.40)");
          grad.addColorStop(1, "rgba(207,196,173,0)");
          g.fillStyle = grad;
          g.fillRect(x - br, y - br, 2 * br, 2 * br);
        }
      }
      for (const f of fibres) {
        const x = f.x + ox - P, y = f.y + oy - P;
        g.strokeStyle = f.light ? "rgba(246,242,234,0.55)" : "rgba(163,150,124,0.24)";
        g.lineWidth = f.light ? 1.6 : 1.4;
        g.beginPath();
        g.moveTo(x, y);
        g.quadraticCurveTo(x + Math.cos(f.a) * f.l * 0.5 + f.bx, y + Math.sin(f.a) * f.l * 0.5 + f.by, x + Math.cos(f.a) * f.l, y + Math.sin(f.a) * f.l);
        g.stroke();
      }
    }
  }
  return c;
}

/** A yellowed newsprint clipping: torn top and bottom, an aged edge, a double rule under the kicker. */
export function paintClipping(w: number, h: number, seed: number, ruleY: number | null): HTMLCanvasElement {
  const pad = 24;
  const c = tornPaper(w, h, seed, COLORS.newsprint, { top: 7, bottom: 9, left: 2, right: 3 }, { pad });
  const g = c.getContext("2d")!;
  g.save();
  g.translate(pad, pad);
  poly(g, tornPoints(w, h, seed, { top: 7, bottom: 9, left: 2, right: 3 }));
  g.clip();
  const age = g.createRadialGradient(w / 2, h * 0.45, Math.min(w, h) * 0.3, w / 2, h * 0.45, Math.max(w, h) * 0.75);
  age.addColorStop(0, "rgba(207,177,149,0)");
  age.addColorStop(1, "rgba(207,177,149,0.55)");
  g.fillStyle = age;
  g.fillRect(-10, -10, w + 20, h + 20);
  if (ruleY !== null) {
    g.fillStyle = COLORS.ink;
    g.fillRect(30, ruleY, w - 60, 4);
    g.fillRect(30, ruleY + 9, w - 60, 1.5);
  }
  g.restore();
  return c;
}

/** A torn black card for a dark beat. */
export function paintBlack(w: number, h: number, seed: number): HTMLCanvasElement {
  return tornPaper(w, h, seed, "#1B1B1A", { top: 8, right: 8, bottom: 8, left: 8 }, { fringe: "#E9E4D8", shadow: 0.25 });
}

/** The desk scrap under a station's hero, one of three by the station's number. */
export function paintScrap(i: number): { canvas: HTMLCanvasElement; x: number; y: number } {
  const kind = i % 3;
  const r = seeded(900 + i * 7);
  if (kind === 0) {
    const strip = tornPaper(1500, 170, 52 + i, COLORS.redDark, { top: 8, bottom: 8, left: 5, right: 5 });
    return rotated(strip, -7 + r() * 3, i % 2 ? 300 : 780, 1120);
  }
  if (kind === 1) {
    const card = paintBlack(780, 640, 33 + i);
    return rotated(card, 2 - r() * 4, i % 2 ? 330 : 750, 900);
  }
  const scrap = tornPaper(720, 560, 41 + i, COLORS.clipping, { top: 8, right: 8, bottom: 8, left: 8 }, { fringe: "#EFE7D6" });
  return rotated(scrap, 5 - r() * 10, i % 2 ? 260 : 820, 1010);
}

/** The desk scrap low on a station, under the captions, one of three by the station's number. */
export function paintLowScrap(i: number): { canvas: HTMLCanvasElement; x: number; y: number } {
  const kind = (i + 1) % 3;
  const r = seeded(1700 + i * 11);
  const side = i % 2 ? -1 : 1;
  if (kind === 0) {
    const strip = tornPaper(980, 120, 71 + i, COLORS.highlight, { top: 6, bottom: 6, left: 3, right: 3 }, { shadow: 0.24 });
    return rotated(strip, -3 + r() * 6, 540 + side * 180, 1660);
  }
  if (kind === 1) {
    // a scrap of newsprint: grey bars for its body text, no words
    const w = 620, h = 400;
    const paper = tornPaper(w, h, 88 + i, COLORS.newsprint, { top: 6, right: 7, bottom: 6, left: 7 });
    const g = paper.getContext("2d")!;
    g.fillStyle = "rgba(23,23,22,0.85)";
    g.fillRect(24 + 40, 24 + 46, w * 0.55, 30);
    g.fillStyle = "rgba(183,174,157,0.9)";
    for (let k = 0; k < 7; k++) g.fillRect(24 + 40, 24 + 112 + k * 34, (w - 80) * (k === 6 ? 0.5 : 0.92 - r() * 0.15), 13);
    return rotated(paper, 4 - r() * 8, 540 - side * 240, 1720);
  }
  // a tan map scrap with a dotted red route
  const w = 600, h = 380;
  const map = tornPaper(w, h, 140 + i, COLORS.clipping, { top: 8, right: 8, bottom: 8, left: 8 }, { fringe: "#EFE7D6" });
  const g = map.getContext("2d")!;
  g.translate(24, 24);
  g.strokeStyle = "rgba(138,116,88,0.55)";
  g.lineWidth = 3;
  for (let k = 0; k < 3; k++) {
    g.beginPath();
    for (let x = 0; x <= w; x += 30) {
      const y = 90 + k * 110 + Math.sin(x / 70 + k + i) * 26 + (r() - 0.5) * 14;
      if (x) g.lineTo(x, y);
      else g.moveTo(x, y);
    }
    g.stroke();
  }
  g.fillStyle = COLORS.red;
  for (let t = 0; t <= 1; t += 0.045) {
    g.beginPath();
    g.arc(70 + t * (w - 150), h - 80 - Math.sin(t * Math.PI * 0.9) * (h - 170), 5, 0, Math.PI * 2);
    g.fill();
  }
  return rotated(map, -4 + r() * 8, 540 + side * 250, 1720);
}

/** A canvas turned by `deg` about its centre, placed with that centre at (cx, cy). */
export function rotated(src: HTMLCanvasElement, deg: number, cx: number, cy: number): { canvas: HTMLCanvasElement; x: number; y: number } {
  const a = (deg * Math.PI) / 180;
  const cw = Math.abs(src.width * Math.cos(a)) + Math.abs(src.height * Math.sin(a));
  const ch = Math.abs(src.width * Math.sin(a)) + Math.abs(src.height * Math.cos(a));
  const [c, g] = makeCanvas(cw, ch);
  g.translate(c.width / 2, c.height / 2);
  g.rotate(a);
  g.drawImage(src, -src.width / 2, -src.height / 2);
  return { canvas: c, x: cx - c.width / 2, y: cy - c.height / 2 };
}

function tape(g: CanvasRenderingContext2D, x: number, y: number, w: number, deg: number, seed: number) {
  const r = seeded(seed);
  g.save();
  g.translate(x, y);
  g.rotate((deg * Math.PI) / 180);
  g.fillStyle = "rgba(244,240,226,0.72)";
  g.beginPath();
  g.moveTo(-w / 2, -21);
  for (let k = 0; k <= 6; k++) g.lineTo(-w / 2 + (k % 2 ? 4 : 0) + r() * 3, -21 + k * 7);
  for (let k = 0; k <= 6; k++) g.lineTo(w / 2 - (k % 2 ? 4 : 0) - r() * 3, 21 - k * 7);
  g.closePath();
  g.fill();
  g.fillStyle = "rgba(23,23,22,0.07)";
  g.fillRect(-w / 2, 19, w, 2);
  g.restore();
}

/** A small typed paper note: a pale strip with a hard shadow and one line of typewriter text. */
function note(g: CanvasRenderingContext2D, text: string, x: number, y: number, size: number, align: "left" | "right" | "center") {
  g.font = `400 ${size}px ${TYPED}`;
  const tw = g.measureText(text).width;
  const w = tw + size * 0.9, h = size * 1.45;
  const left = align === "left" ? x : align === "right" ? x - w : x - w / 2;
  g.fillStyle = "rgba(23,23,22,0.18)";
  g.fillRect(left + 3, y + 4, w, h);
  g.fillStyle = COLORS.edge;
  g.fillRect(left, y, w, h);
  g.fillStyle = COLORS.inkSoft;
  g.textBaseline = "middle";
  g.fillText(text, left + size * 0.45, y + h / 2 + 1);
  return h;
}

/** A taped halftone print: the treated still fitted to w x h, tilted by `deg`,
 *  with its "Illustration" note and an optional typed caption under it. The
 *  canvas is centred on the print's centre. */
export function paintPrint(img: HTMLImageElement, w: number, h: number, deg: number, caption: string | undefined, seed: number, small = false): HTMLCanvasElement {
  const capH = caption ? (small ? 50 : 66) : 0;
  const pad = 70;
  const [flat, g] = makeCanvas(w + 2 * pad, h + capH + 2 * pad);
  g.translate(pad, pad);
  g.fillStyle = "rgba(23,23,22,0.24)";
  g.fillRect(6, 9, w, h);
  g.drawImage(img, 0, 0, w, h);
  note(g, NOTES.print, w - 12, h - (small ? 20 : 26), small ? 17 : 22, "right");
  if (caption) note(g, caption, w / 2, h + (small ? 4 : 10), small ? 26 : 30, "center");
  const tw = small ? 90 : 150;
  tape(g, 18, 6, tw, -32, seed);
  tape(g, w - 18, 6, tw, 30, seed + 1);
  return rotated(flat, deg, 0, 0).canvas;
}

/** A cut-out sticker (the treated still already has its white edge and shadow), fitted to w x h. */
export function paintSticker(img: HTMLImageElement, w: number, h: number, caption?: string): HTMLCanvasElement {
  const capH = caption ? 56 : 0;
  const [c, g] = makeCanvas(w + 20, h + capH + 20);
  g.drawImage(img, 10, 10, w, h);
  if (caption) note(g, caption, (w + 20) / 2, h + 12, 26, "center");
  return c;
}

/** A ruled index card, w x h, with a red head rule, blue lines every `lineH`
 *  from `head`, a pin, and the note "Recreation" when it recreates a document. */
export function paintIndex(w: number, h: number, head: number, lineH: number, recreation: boolean): HTMLCanvasElement {
  const pad = 20;
  const [c, g] = makeCanvas(w + 2 * pad, h + 2 * pad);
  g.translate(pad, pad);
  g.fillStyle = "rgba(23,23,22,0.18)";
  g.fillRect(5, 8, w, h);
  g.fillStyle = COLORS.card;
  g.fillRect(0, 0, w, h);
  g.fillStyle = "rgba(182,82,85,0.55)";
  g.fillRect(0, head - 30, w, 3);
  g.fillStyle = "rgba(147,169,194,0.55)";
  for (let y = head - 30 + lineH; y < h - 20; y += lineH) g.fillRect(0, y, w, 2);
  g.fillStyle = "rgba(182,82,85,0.4)";
  g.fillRect(56, 0, 2, h);
  g.fillStyle = COLORS.red;
  g.beginPath();
  g.arc(w / 2, 32, 15, 0, Math.PI * 2);
  g.fill();
  g.fillStyle = "rgba(255,255,255,0.5)";
  g.beginPath();
  g.arc(w / 2 - 5, 27, 5, 0, Math.PI * 2);
  g.fill();
  if (recreation) {
    g.font = `400 22px ${TYPED}`;
    g.fillStyle = COLORS.inkSoft;
    g.textBaseline = "alphabetic";
    g.textAlign = "right";
    g.fillText(NOTES.recreation, w - 20, h - 18);
    g.textAlign = "left";
  }
  return c;
}

const ARROW: [number, number][] = [[8, 80], [104, 10], [108, 52], [250, 38], [256, 110], [110, 102], [104, 146]];

/** The hand-cut red paper arrow, its point at the right (or the left, `flip`). */
export function paintArrow(flip: boolean): HTMLCanvasElement {
  const [c, g] = makeCanvas(300, 190);
  g.translate(flip ? 22 : 278, 16);
  g.scale(flip ? 1 : -1, 1);
  const path = () => {
    g.beginPath();
    ARROW.forEach(([x, y], i) => (i ? g.lineTo(x, y) : g.moveTo(x, y)));
    g.closePath();
  };
  g.lineJoin = "round";
  g.save();
  g.translate(5, 7);
  path();
  g.fillStyle = "rgba(23,23,22,0.3)";
  g.strokeStyle = "rgba(23,23,22,0.3)";
  g.lineWidth = 20;
  g.stroke();
  g.fill();
  g.restore();
  path();
  g.strokeStyle = COLORS.edge;
  g.lineWidth = 20;
  g.stroke();
  g.fillStyle = COLORS.redDark;
  g.fill();
  g.strokeStyle = "rgba(122,51,47,0.5)";
  g.lineWidth = 6;
  g.beginPath();
  g.moveTo(30, 80);
  g.lineTo(250, 72);
  g.stroke();
  return c;
}

/** Where the arrow's point is within its canvas (x, y), unflipped (pointing right) and flipped. */
export const ARROW_TIP = { right: [270, 96] as const, left: [30, 96] as const };
