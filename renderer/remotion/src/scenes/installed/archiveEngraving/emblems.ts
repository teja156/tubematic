/*
 * The engraved roundels a person's name card carries: a coin-like ring with a
 * beaded border and a hatched field, holding one of ten emblems drawn in code
 * (or the person's initials, set in type by the component). A roundel never
 * shows a face: it stands for the person's work.
 *
 * Every shape is plain geometry in a 200 x 200 box, so a test can check that
 * each emblem stays inside the roundel's field, and the component draws them
 * as a static SVG (filled with the card's cream and stroked in ink, so the
 * hatching behind an emblem stops at its outline).
 */
import type { Emblem } from "./contract";

export type Shape =
  | { t: "poly"; pts: [number, number][]; closed: boolean; fill?: "card" | "ink"; w?: number }
  | { t: "circle"; cx: number; cy: number; r: number; fill?: "card" | "ink" | "none"; w?: number }
  | { t: "ellipse"; cx: number; cy: number; rx: number; ry: number; rot: number; fill?: "card" | "ink"; w?: number };

export const SIZE = 200;
export const C = 100;
// the emblem stays inside this radius; the hatched field reaches FIELD_R
export const EMBLEM_R = 64;
export const FIELD_R = 80;

const rad = (deg: number) => (deg * Math.PI) / 180;
const at = (r: number, deg: number, cx = C, cy = C): [number, number] => [cx + r * Math.cos(rad(deg)), cy + r * Math.sin(rad(deg))];
const mirror = (pts: [number, number][]): [number, number][] => pts.map(([x, y]) => [SIZE - x, y]);

/** The ring, the beads and the hatched field every roundel shares. */
export function roundelShapes(): Shape[] {
  const out: Shape[] = [{ t: "circle", cx: C, cy: C, r: 96, fill: "card", w: 3.2 }];
  for (let k = 0; k < 48; k++) {
    const [x, y] = at(89, k * 7.5);
    out.push({ t: "circle", cx: x, cy: y, r: 1.7, fill: "ink", w: 0 });
  }
  out.push({ t: "circle", cx: C, cy: C, r: 82, fill: "none", w: 1.4 });
  for (let y = C - FIELD_R + 4; y <= C + FIELD_R - 4; y += 7) {
    const half = Math.sqrt(FIELD_R * FIELD_R - (y - C) ** 2);
    out.push({ t: "poly", pts: [[C - half, y], [C + half, y]], closed: false, w: 0.7 });
  }
  return out;
}

function laurel(): Shape[] {
  const left: Shape[] = [];
  const stem: [number, number][] = [];
  for (let a = 100; a <= 245; a += 5) stem.push(at(50, a));
  left.push({ t: "poly", pts: stem, closed: false, w: 2.4 });
  let side = 1;
  for (let a = 112; a <= 236; a += 16) {
    const [x, y] = at(50 + side * 9, a);
    left.push({ t: "ellipse", cx: x, cy: y, rx: 11, ry: 4.6, rot: a + 90 + side * 28, fill: "card", w: 1.6 });
    side = -side;
  }
  const right: Shape[] = left.map((s) =>
    s.t === "poly" ? { ...s, pts: mirror(s.pts) } : s.t === "ellipse" ? { ...s, cx: SIZE - s.cx, rot: 180 - s.rot } : s,
  );
  return [...left, ...right, { t: "poly", pts: [[90, 148], [100, 154], [110, 148]], closed: false, w: 2 }];
}

function quill(): Shape[] {
  const a: [number, number] = [134, 48], b: [number, number] = [78, 146];
  const len = Math.hypot(b[0] - a[0], b[1] - a[1]);
  const ux = (b[0] - a[0]) / len, uy = (b[1] - a[1]) / len;
  const nx = -uy, ny = ux;
  const leftSide: [number, number][] = [], rightSide: [number, number][] = [];
  for (let i = 0; i <= 16; i++) {
    const t = (i / 16) * 0.82;
    const w = 20 * Math.sin(Math.PI * Math.min(1, t / 0.82)) ** 0.7;
    const px = a[0] + ux * len * t, py = a[1] + uy * len * t;
    leftSide.push([px + nx * w, py + ny * w]);
    rightSide.push([px - nx * w * 0.7, py - ny * w * 0.7]);
  }
  const feather: Shape = { t: "poly", pts: [...leftSide, ...rightSide.reverse()], closed: true, fill: "card", w: 2 };
  const barbs: Shape[] = [];
  for (let i = 2; i <= 13; i += 1) {
    const t = (i / 16) * 0.82;
    const w = 20 * Math.sin(Math.PI * Math.min(1, t / 0.82)) ** 0.7;
    const px = a[0] + ux * len * t, py = a[1] + uy * len * t;
    barbs.push({ t: "poly", pts: [[px, py], [px + nx * w * 0.9 + ux * 6, py + ny * w * 0.9 + uy * 6]], closed: false, w: 0.9 });
  }
  return [feather, ...barbs, { t: "poly", pts: [a, [b[0] - ux * 2, b[1] - uy * 2]], closed: false, w: 1.8 },
    { t: "poly", pts: [[b[0] - ux * len * 0.18, b[1] - uy * len * 0.18], [b[0] + ux * 10, b[1] + uy * 10]], closed: false, w: 3 }];
}

function gear(): Shape[] {
  const pts: [number, number][] = [];
  for (let k = 0; k < 10; k++) {
    const base = k * 36;
    pts.push(at(44, base - 13), at(56, base - 7), at(56, base + 7), at(44, base + 13));
  }
  return [
    { t: "poly", pts, closed: true, fill: "card", w: 2.2 },
    { t: "circle", cx: C, cy: C, r: 30, fill: "none", w: 1.6 },
    { t: "circle", cx: C, cy: C, r: 14, fill: "ink", w: 1.6 },
  ];
}

function compass(): Shape[] {
  const star: [number, number][] = [];
  for (let k = 0; k < 8; k++) {
    star.push(at(k % 2 === 0 ? 60 : 30, k * 45 - 90), at(10, k * 45 - 90 + 22.5));
  }
  const halves: Shape[] = [];
  for (let k = 0; k < 4; k++) {
    halves.push({ t: "poly", pts: [[C, C], at(60, k * 90 - 90), at(10, k * 90 - 90 + 22.5)], closed: true, fill: "ink", w: 1 });
  }
  return [{ t: "circle", cx: C, cy: C, r: 36, fill: "card", w: 1.6 }, { t: "poly", pts: star, closed: true, fill: "card", w: 2 }, ...halves,
    { t: "circle", cx: C, cy: C, r: 4, fill: "ink", w: 1 }];
}

function scroll(): Shape[] {
  const lines: Shape[] = [];
  for (let y = 84; y <= 116; y += 8) lines.push({ t: "poly", pts: [[74, y], [y % 16 === 0 ? 118 : 126, y]], closed: false, w: 1.2 });
  return [
    { t: "poly", pts: [[58, 72], [142, 72], [142, 128], [58, 128]], closed: true, fill: "card", w: 2 },
    { t: "ellipse", cx: 58, cy: 100, rx: 8, ry: 30, rot: 0, fill: "card", w: 2 },
    { t: "ellipse", cx: 142, cy: 100, rx: 8, ry: 30, rot: 0, fill: "card", w: 2 },
    { t: "ellipse", cx: 142, cy: 100, rx: 3, ry: 12, rot: 0, fill: "ink", w: 1 },
    ...lines,
  ];
}

function book(): Shape[] {
  const page: [number, number][] = [[100, 80], [54, 70], [54, 132], [100, 142]];
  const lines: Shape[] = [];
  for (let k = 0; k < 5; k++) {
    const y0 = 84 + k * 10;
    lines.push({ t: "poly", pts: [[62, y0 - 6], [94, y0 + 1]], closed: false, w: 1 });
    lines.push({ t: "poly", pts: [[138, y0 - 6], [106, y0 + 1]], closed: false, w: 1 });
  }
  return [
    { t: "poly", pts: [[46, 74], [46, 138], [100, 150], [154, 138], [154, 74]], closed: false, w: 2.4 },
    { t: "poly", pts: page, closed: true, fill: "card", w: 2 },
    { t: "poly", pts: mirror(page), closed: true, fill: "card", w: 2 },
    ...lines,
  ];
}

function anchor(): Shape[] {
  const arm: [number, number][] = [];
  for (let a = 20; a <= 160; a += 10) arm.push(at(42, a, C, 112));
  return [
    { t: "circle", cx: C, cy: 50, r: 9, fill: "card", w: 2.4 },
    { t: "poly", pts: [[C, 59], [C, 155]], closed: false, w: 5 },
    { t: "poly", pts: [[74, 74], [126, 74]], closed: false, w: 4 },
    { t: "poly", pts: arm, closed: false, w: 4 },
    { t: "poly", pts: [arm[0], [arm[0][0] + 4, arm[0][1] - 16], [arm[0][0] - 8, arm[0][1] - 6]], closed: true, fill: "ink", w: 1 },
    { t: "poly", pts: [arm[arm.length - 1], [arm[arm.length - 1][0] - 4, arm[arm.length - 1][1] - 16], [arm[arm.length - 1][0] + 8, arm[arm.length - 1][1] - 6]], closed: true, fill: "ink", w: 1 },
  ];
}

function telescope(): Shape[] {
  const a: [number, number] = [58, 116], b: [number, number] = [148, 72];
  const len = Math.hypot(b[0] - a[0], b[1] - a[1]);
  const ux = (b[0] - a[0]) / len, uy = (b[1] - a[1]) / len;
  const nx = -uy, ny = ux;
  const tube = (t0: number, t1: number, w0: number, w1: number): [number, number][] => [
    [a[0] + ux * len * t0 + nx * w0, a[1] + uy * len * t0 + ny * w0],
    [a[0] + ux * len * t1 + nx * w1, a[1] + uy * len * t1 + ny * w1],
    [a[0] + ux * len * t1 - nx * w1, a[1] + uy * len * t1 - ny * w1],
    [a[0] + ux * len * t0 - nx * w0, a[1] + uy * len * t0 - ny * w0],
  ];
  const mid: [number, number] = [a[0] + ux * len * 0.55, a[1] + uy * len * 0.55];
  return [
    { t: "poly", pts: [mid, [76, 160]], closed: false, w: 2.2 },
    { t: "poly", pts: [mid, [mid[0], 162]], closed: false, w: 2.2 },
    { t: "poly", pts: [mid, [136, 158]], closed: false, w: 2.2 },
    { t: "poly", pts: tube(0, 0.3, 6, 7), closed: true, fill: "card", w: 2 },
    { t: "poly", pts: tube(0.3, 0.62, 9, 10), closed: true, fill: "card", w: 2 },
    { t: "poly", pts: tube(0.62, 1, 12, 14), closed: true, fill: "card", w: 2 },
  ];
}

function scales(): Shape[] {
  const pan = (cx: number): [number, number][] => {
    const pts: [number, number][] = [];
    for (let k = 0; k <= 8; k++) pts.push([cx - 16 + (32 * k) / 8, 112 + 10 * Math.sin((Math.PI * k) / 8)]);
    return pts;
  };
  return [
    { t: "poly", pts: [[C, 50], [C, 152]], closed: false, w: 3 },
    { t: "poly", pts: [[76, 152], [124, 152], [118, 160], [82, 160]], closed: true, fill: "card", w: 2 },
    { t: "poly", pts: [[56, 62], [144, 62]], closed: false, w: 3 },
    { t: "circle", cx: C, cy: 47, r: 5, fill: "card", w: 2 },
    { t: "poly", pts: [[56, 62], [40, 112]], closed: false, w: 1.2 },
    { t: "poly", pts: [[56, 62], [72, 112]], closed: false, w: 1.2 },
    { t: "poly", pts: [[144, 62], [128, 112]], closed: false, w: 1.2 },
    { t: "poly", pts: [[144, 62], [160, 112]], closed: false, w: 1.2 },
    { t: "poly", pts: pan(56), closed: true, fill: "card", w: 2 },
    { t: "poly", pts: pan(144), closed: true, fill: "card", w: 2 },
  ];
}

function lamp(): Shape[] {
  return [
    { t: "circle", cx: 56, cy: 114, r: 11, fill: "none", w: 2.4 },
    { t: "poly", pts: [[62, 126], [70, 110], [108, 106], [132, 98], [146, 92], [142, 104], [126, 120], [114, 130], [70, 132]], closed: true, fill: "card", w: 2.2 },
    { t: "poly", pts: [[86, 132], [104, 132], [110, 144], [80, 144]], closed: true, fill: "card", w: 2 },
    { t: "poly", pts: [[84, 106], [92, 94], [100, 106]], closed: true, fill: "card", w: 1.8 },
    { t: "poly", pts: [[147, 88], [141, 76], [147, 60], [153, 76]], closed: true, fill: "ink", w: 1 },
  ];
}

const DRAW: Record<Emblem, () => Shape[]> = { laurel, quill, gear, compass, scroll, book, anchor, telescope, scales, lamp };

export function emblemShapes(name: Emblem): Shape[] {
  return DRAW[name]();
}

/** Every point a shape reaches, for the bounds test. */
export function shapePoints(s: Shape): [number, number][] {
  if (s.t === "poly") return s.pts;
  const r = s.t === "circle" ? s.r : Math.max(s.rx, s.ry);
  const cx = s.cx, cy = s.cy;
  return [[cx - r, cy], [cx + r, cy], [cx, cy - r], [cx, cy + r]];
}
