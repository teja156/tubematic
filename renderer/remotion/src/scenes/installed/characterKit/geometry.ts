/*
 * Shape and number helpers shared by the code-drawn character styles. Pure
 * functions: no React, no randomness except the seeded generator.
 */

export type Pt = [number, number];

/** Seeded random numbers (mulberry32). A drawing never calls Math.random(). */
export function rng(seed: number): () => number {
  let a = seed >>> 0;
  return () => {
    a |= 0;
    a = (a + 0x6d2b79f5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

/** A stable small number for a string, to seed a drawing by its id. */
export function hashSeed(s: string): number {
  let h = 2166136261;
  for (let i = 0; i < s.length; i++) h = Math.imul(h ^ s.charCodeAt(i), 16777619);
  return h >>> 0;
}

export const clamp01 = (v: number) => Math.max(0, Math.min(1, v));

export const ease = {
  out: (t: number) => 1 - (1 - t) ** 3,
  in: (t: number) => t * t * t,
  inOut: (t: number) => (t < 0.5 ? 4 * t * t * t : 1 - (-2 * t + 2) ** 3 / 2),
  outBack: (t: number) => 1 + 2.70158 * (t - 1) ** 3 + 1.70158 * (t - 1) ** 2,
};

/**
 * The frame stepped on twos, and which of `phases` wobble phases it shows. The
 * styles that animate on twos hold each picture for two frames and cycle a few
 * fixed wobble phases, so a held drawing has only `phases` looks to cache.
 */
export const onTwos = (frame: number) => Math.floor(frame / 2) * 2;
export const phaseOf = (frame: number, phases = 3) => Math.floor(frame / 2) % phases;

const hex = (c: string) => [1, 3, 5].map((i) => parseInt(c.slice(i, i + 2), 16));
/** Mix two #rrggbb colours: t = 0 gives a, 1 gives b. */
export function mix(a: string, b: string, t: number): string {
  const A = hex(a);
  const B = hex(b);
  return "#" + A.map((v, i) => Math.round(v + (B[i] - v) * t).toString(16).padStart(2, "0")).join("");
}

const f1 = (v: number) => (Math.round(v * 10) / 10).toString();

export const rectP = (x: number, y: number, w: number, h: number, r = 0): string => {
  const rr = Math.min(r, w / 2, h / 2);
  return `M${f1(x + rr)} ${f1(y)} H${f1(x + w - rr)} A${rr} ${rr} 0 0 1 ${f1(x + w)} ${f1(y + rr)} V${f1(y + h - rr)} A${rr} ${rr} 0 0 1 ${f1(x + w - rr)} ${f1(y + h)} H${f1(x + rr)} A${rr} ${rr} 0 0 1 ${f1(x)} ${f1(y + h - rr)} V${f1(y + rr)} A${rr} ${rr} 0 0 1 ${f1(x + rr)} ${f1(y)} Z`;
};

export const ellP = (cx: number, cy: number, rx: number, ry: number): string =>
  `M${f1(cx - rx)} ${f1(cy)} A${rx} ${ry} 0 1 0 ${f1(cx + rx)} ${f1(cy)} A${rx} ${ry} 0 1 0 ${f1(cx - rx)} ${f1(cy)} Z`;

export const polyP = (pts: Pt[], closed = true): string =>
  "M" + pts.map((p) => `${f1(p[0])} ${f1(p[1])}`).join(" L") + (closed ? " Z" : "");

/** Chaikin smoothing; keeps the end points. */
export function smooth(pts: Pt[], it = 3): Pt[] {
  let p = pts;
  for (let k = 0; k < it; k++) {
    const out: Pt[] = [p[0]];
    for (let i = 0; i < p.length - 1; i++) {
      const [ax, ay] = p[i];
      const [bx, by] = p[i + 1];
      out.push([ax * 0.75 + bx * 0.25, ay * 0.75 + by * 0.25], [ax * 0.25 + bx * 0.75, ay * 0.25 + by * 0.75]);
    }
    out.push(p[p.length - 1]);
    p = out;
  }
  return p;
}

/** Closed outline of a tube (a sleeve, a limb, a finger) along a polyline, with round caps. */
export function tubeP(pts: Pt[], w: number): string {
  const r = w / 2;
  const n = pts.length;
  const L: Pt[] = [];
  const R: Pt[] = [];
  for (let i = 0; i < n; i++) {
    const a = pts[Math.max(0, i - 1)];
    const b = pts[Math.min(n - 1, i + 1)];
    let tx = b[0] - a[0];
    let ty = b[1] - a[1];
    const len = Math.hypot(tx, ty) || 1;
    tx /= len;
    ty /= len;
    L.push([pts[i][0] - ty * r, pts[i][1] + tx * r]);
    R.push([pts[i][0] + ty * r, pts[i][1] - tx * r]);
  }
  const f = (p: Pt) => `${f1(p[0])} ${f1(p[1])}`;
  let d = `M${f(L[0])}`;
  for (let i = 1; i < n; i++) d += ` L${f(L[i])}`;
  d += ` A${r} ${r} 0 0 0 ${f(R[n - 1])}`;
  for (let i = n - 2; i >= 0; i--) d += ` L${f(R[i])}`;
  d += ` A${r} ${r} 0 0 0 ${f(L[0])} Z`;
  return d;
}

/** Points along a cubic Bezier. */
export function cubic(p0: Pt, c1: Pt, c2: Pt, p1: Pt, steps = 28): Pt[] {
  const out: Pt[] = [];
  for (let i = 0; i <= steps; i++) {
    const t = i / steps;
    const u = 1 - t;
    out.push([
      u * u * u * p0[0] + 3 * u * u * t * c1[0] + 3 * u * t * t * c2[0] + t * t * t * p1[0],
      u * u * u * p0[1] + 3 * u * u * t * c1[1] + 3 * u * t * t * c2[1] + t * t * t * p1[1],
    ]);
  }
  return out;
}

/** Two-bone IK: the elbow for a shoulder s reaching t with bones l1 and l2 (bends below the line, or above with `up`). */
export function ik(s: Pt, t: Pt, l1: number, l2: number, up = false): Pt {
  const dx = t[0] - s[0];
  const dy = t[1] - s[1];
  const d = Math.min(Math.max(Math.hypot(dx, dy), Math.abs(l1 - l2) + 1), l1 + l2 - 1);
  const a = Math.acos((l1 * l1 + d * d - l2 * l2) / (2 * l1 * d)) * (up ? -1 : 1);
  const base = Math.atan2(dy, dx);
  return [s[0] + Math.cos(base + a) * l1, s[1] + Math.sin(base + a) * l1];
}

/** [left, top, right, bottom] boxes overlap by more than `tol` pixels. */
export function overlaps(a: readonly number[], b: readonly number[], tol = 0): boolean {
  return a[0] < b[2] - tol && b[0] < a[2] - tol && a[1] < b[3] - tol && b[1] < a[3] - tol;
}
