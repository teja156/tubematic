/*
 * The Process Cast look, as drawing helpers: the palette, seeded wobbly-ink
 * geometry (every path computed once per seed and cached, so outlines wobble
 * but never boil from frame to frame) and coloured-pencil hatching.
 *
 * Everything drawn with these helpers is rasterised once per look into a cached
 * sprite (../characterKit/sprite.tsx): the hatching patterns and clip paths
 * cost their paint once, never per frame. A drawing that hatches puts
 * <Hatches /> in its own SVG, since each sprite is its own document. An
 * agent's own prop (generated/<video_id>/prop-<name>.tsx) imports this file.
 */
import React from "react";
import { mix, rng, type Pt } from "../characterKit/geometry";

export type { Pt };

export const PAPER = "#E9E6DF";
export const INK = "#2B2521";
export const TEAL = "#2F8D89";
export const LIME = "#A6B23B";
export const CREAM = "#F4ECD9";
export const BEIGE = "#E3D2AE";
export const WOOD = "#B38957";
export const RED = "#CC5040";
export const GREEN = "#4E9A4A";
export const BLUSH = "#E58E7E";

export const MONO = "'JetBrains Mono', 'DejaVu Sans Mono', 'Courier New', monospace";
export const ROUNDED = "Nunito, 'Trebuchet MS', sans-serif";

/** A fill colour with the darker, lighter and shadow tones its hatching uses. */
export type Tone = { base: string; dark: string; light: string; shade: string };
export const tone = (base: string): Tone => ({
  base, dark: mix(base, INK, 0.3), light: mix(base, "#FFFFFF", 0.3), shade: mix(base, INK, 0.48),
});
export const WOOD_TONE = tone(WOOD);
export const CREAM_TONE = tone(CREAM);
export const BEIGE_TONE = tone(BEIGE);

/** The hatch and shade patterns for one tone, ids `hatch-<key>` and `shade-<key>`. */
export const Hatches: React.FC<{ tones: Record<string, Tone> }> = ({ tones }) => (
  <defs>
    {Object.entries(tones).map(([k, c]) => (
      <React.Fragment key={k}>
        <pattern id={`hatch-${k}`} width={15} height={15} patternUnits="userSpaceOnUse" patternTransform="rotate(38)">
          <line x1={0} y1={2.5} x2={15} y2={2.5} stroke={c.dark} strokeWidth={2.2} opacity={0.45} />
          <line x1={0} y1={7.5} x2={15} y2={7.5} stroke={c.light} strokeWidth={1.8} opacity={0.45} />
          <line x1={0} y1={11.5} x2={15} y2={11.5} stroke={c.dark} strokeWidth={1.4} opacity={0.3} />
        </pattern>
        <pattern id={`shade-${k}`} width={9} height={9} patternUnits="userSpaceOnUse" patternTransform="rotate(-48)">
          <line x1={0} y1={3} x2={9} y2={3} stroke={c.shade} strokeWidth={2.4} opacity={0.42} />
          <line x1={0} y1={7} x2={9} y2={7} stroke={c.shade} strokeWidth={1.4} opacity={0.25} />
        </pattern>
      </React.Fragment>
    ))}
  </defs>
);

/** A filled shape in the house look: flat tone, pencil hatching (pattern `hatch-<k>`, from <Hatches />), ink outline. */
export const Inked: React.FC<{ d: string; k: string; tone: Tone; sw?: number }> = ({ d, k, tone: t, sw = 5 }) => (
  <g>
    <path d={d} fill={t.base} />
    <path d={d} fill={`url(#hatch-${k})`} />
    <path d={d} fill="none" stroke={INK} strokeWidth={sw} strokeLinejoin="round" />
  </g>
);

const cache = new Map<string, string>();
const memo = (key: string, make: () => string) => {
  const hit = cache.get(key);
  if (hit) return hit;
  const v = make();
  cache.set(key, v);
  return v;
};

/** Closed Catmull-Rom curve through points, as cubic beziers. */
export const closedCurve = (p: Pt[]) => {
  const n = p.length;
  let d = `M${p[0][0].toFixed(1)} ${p[0][1].toFixed(1)}`;
  for (let i = 0; i < n; i++) {
    const p0 = p[(i - 1 + n) % n], p1 = p[i], p2 = p[(i + 1) % n], p3 = p[(i + 2) % n];
    const c1: Pt = [p1[0] + (p2[0] - p0[0]) / 6, p1[1] + (p2[1] - p0[1]) / 6];
    const c2: Pt = [p2[0] - (p3[0] - p1[0]) / 6, p2[1] - (p3[1] - p1[1]) / 6];
    d += `C${c1[0].toFixed(1)} ${c1[1].toFixed(1)} ${c2[0].toFixed(1)} ${c2[1].toFixed(1)} ${p2[0].toFixed(1)} ${p2[1].toFixed(1)}`;
  }
  return d + "Z";
};

export const openCurve = (p: Pt[]) => {
  const n = p.length;
  let d = `M${p[0][0].toFixed(1)} ${p[0][1].toFixed(1)}`;
  for (let i = 0; i < n - 1; i++) {
    const p0 = p[Math.max(0, i - 1)], p1 = p[i], p2 = p[i + 1], p3 = p[Math.min(n - 1, i + 2)];
    const c1: Pt = [p1[0] + (p2[0] - p0[0]) / 6, p1[1] + (p2[1] - p0[1]) / 6];
    const c2: Pt = [p2[0] - (p3[0] - p1[0]) / 6, p2[1] - (p3[1] - p1[1]) / 6];
    d += `C${c1[0].toFixed(1)} ${c1[1].toFixed(1)} ${c2[0].toFixed(1)} ${c2[1].toFixed(1)} ${p2[0].toFixed(1)} ${p2[1].toFixed(1)}`;
  }
  return d;
};

/** Smoothed seeded jitter values (low frequency, so lines wobble rather than zig-zag). */
const smoothNoise = (n: number, seed: number, closed: boolean) => {
  const r = rng(seed);
  const raw = Array.from({ length: n }, () => r() * 2 - 1);
  return raw.map((_, i) => {
    const a = raw[closed ? (i - 1 + n) % n : Math.max(0, i - 1)];
    const b = raw[closed ? (i + 1) % n : Math.min(n - 1, i + 1)];
    return (a + raw[i] * 2 + b) / 4;
  });
};

/** Jitter a closed loop radially from its centre. */
export const wobbleLoop = (pts: Pt[], c: Pt, seed: number, amp: number) => {
  const nz = smoothNoise(pts.length, seed, true);
  return pts.map(([x, y], i) => {
    const dx = x - c[0], dy = y - c[1];
    const len = Math.hypot(dx, dy) || 1;
    return [x + (dx / len) * nz[i] * amp, y + (dy / len) * nz[i] * amp] as Pt;
  });
};

/** Superellipse body with the feet at (0,0); widen > 0 makes the bottom fuller (a bean). */
export const bodyPath = (w: number, h: number, n: number, widen: number, seed: number, amp = 3.2) =>
  memo(`b${w}|${h}|${n}|${widen}|${seed}|${amp}`, () => {
    const N = 40, rx = w / 2, ry = h / 2, cy = -h / 2;
    const pts: Pt[] = [];
    for (let k = 0; k < N; k++) {
      const t = (k / N) * Math.PI * 2;
      const c = Math.cos(t), s = Math.sin(t);
      let x = rx * Math.sign(c) * Math.pow(Math.abs(c), 2 / n);
      const y = ry * Math.sign(s) * Math.pow(Math.abs(s), 2 / n);
      x *= 1 + widen * (y / ry);
      pts.push([x, cy + y]);
    }
    return closedCurve(wobbleLoop(pts, [0, cy], seed, amp));
  });

/** Polygon with subdivided, jittered edges, softly rounded by the curve. */
export const polyPath = (corners: Pt[], seed: number, amp = 3, sub = 4) =>
  memo(`p${corners.flat().join(",")}|${seed}|${amp}`, () => {
    const pts: Pt[] = [];
    const n = corners.length;
    for (let i = 0; i < n; i++) {
      const a = corners[i], b = corners[(i + 1) % n];
      for (let k = 0; k < sub; k++) {
        const t = k / sub;
        pts.push([a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t]);
      }
    }
    const cx = corners.reduce((s, p) => s + p[0], 0) / n;
    const cy = corners.reduce((s, p) => s + p[1], 0) / n;
    return closedCurve(wobbleLoop(pts, [cx, cy], seed, amp));
  });

/** A hand-drawn straight-ish line between two points. */
export const inkLine = (a: Pt, b: Pt, seed: number, amp = 2, segs = 6) =>
  memo(`l${a.join(",")}|${b.join(",")}|${seed}|${amp}|${segs}`, () => {
    const nz = smoothNoise(segs + 1, seed, false);
    const dx = b[0] - a[0], dy = b[1] - a[1];
    const len = Math.hypot(dx, dy) || 1;
    const nx = -dy / len, ny = dx / len;
    const pts: Pt[] = [];
    for (let k = 0; k <= segs; k++) {
      const t = k / segs;
      const e = k === 0 || k === segs ? 0.3 : 1;
      pts.push([a[0] + dx * t + nx * nz[k] * amp * e, a[1] + dy * t + ny * nz[k] * amp * e]);
    }
    return openCurve(pts);
  });

/** Rounded rectangle with wobble, centred at (cx, cy). */
export const boxPath = (cx: number, cy: number, w: number, h: number, seed: number, amp = 2.4) => {
  const r = Math.min(14, h / 4);
  const corners: Pt[] = [
    [cx - w / 2 + r, cy - h / 2], [cx + w / 2 - r, cy - h / 2], [cx + w / 2, cy - h / 2 + r],
    [cx + w / 2, cy + h / 2 - r], [cx + w / 2 - r, cy + h / 2], [cx - w / 2 + r, cy + h / 2],
    [cx - w / 2, cy + h / 2 - r], [cx - w / 2, cy - h / 2 + r],
  ];
  return polyPath(corners, seed, amp, 3);
};
