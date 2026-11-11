/**
 * Marker strokes: polylines resampled once with a seeded hand wobble, and
 * drawn on by taking a prefix of their length (Whiteboard.tsx's paintInk).
 */
import { noise2D } from "@remotion/noise";

export type Pt = [number, number];
export type Ink = { pts: Pt[]; cum: number[]; len: number };

const STEP = 12;

/** Resample a polyline every STEP px and add a slow, static hand wobble. The
 *  same seed gives the same line on every frame, so nothing boils. */
export function inkStroke(points: Pt[], seed: string, amp = 2.2): Ink {
  const pts: Pt[] = [];
  let s = 0;
  for (let i = 0; i < points.length - 1; i++) {
    const [x0, y0] = points[i];
    const [x1, y1] = points[i + 1];
    const L = Math.hypot(x1 - x0, y1 - y0);
    const n = Math.max(1, Math.ceil(L / STEP));
    for (let k = i === 0 ? 0 : 1; k <= n; k++) {
      const t = k / n;
      const ss = s + L * t;
      const wx = noise2D(`x${seed}`, ss * 0.006, 0) * amp + noise2D(`fx${seed}`, ss * 0.05, 0) * amp * 0.25;
      const wy = noise2D(`y${seed}`, ss * 0.006, 0) * amp + noise2D(`fy${seed}`, ss * 0.05, 0) * amp * 0.25;
      pts.push([x0 + (x1 - x0) * t + wx, y0 + (y1 - y0) * t + wy]);
    }
    s += L;
  }
  if (pts.length === 1) pts.push([pts[0][0] + 0.5, pts[0][1]]);
  const cum = [0];
  for (let i = 1; i < pts.length; i++) cum.push(cum[i - 1] + Math.hypot(pts[i][0] - pts[i - 1][0], pts[i][1] - pts[i - 1][1]));
  return { pts, cum, len: cum[cum.length - 1] };
}

/** The point `at` px along a stroke. */
export function inkPoint(ink: Ink, at: number): Pt {
  if (at <= 0) return ink.pts[0];
  for (let i = 1; i < ink.pts.length; i++) {
    if (ink.cum[i] >= at) {
      const seg = ink.cum[i] - ink.cum[i - 1];
      const t = seg > 0 ? (at - ink.cum[i - 1]) / seg : 0;
      return [ink.pts[i - 1][0] + (ink.pts[i][0] - ink.pts[i - 1][0]) * t, ink.pts[i - 1][1] + (ink.pts[i][1] - ink.pts[i - 1][1]) * t];
    }
  }
  return ink.pts[ink.pts.length - 1];
}
