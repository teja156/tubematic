// The camera grammar, from mromidev/claude-animated-shorts (templates/bridge/story.ts, MIT) and its motion study:
// every move is a symmetric smootherstep glide of 18-40 f (peak speed = 1.875 x distance / dur, so dur >= 0.075 x the
// move in 720p px keeps the peak near the measured 14-25 px/f); a reframe bigger than about half a frame width or
// 40 % zoom is a hard cut on its key frame. Glides are centred on the old key frame, so a glide key starts dur/2
// earlier. Holds push in (dolly toward the look point, or a fov zoom next to walls): 0.15-0.35 %/f, ~0.6 %/f for
// ~35 f on the punch words. Rolls of 4-8 deg over >= 18 f on emphasis beats, held tilt <= 0.07 rad. Impacts are
// 7-frame kicks that flip sign every frame. No hand-held float. A video builds its camAt from these.
import { FPS, type ShotDef, type V3 } from "./video";

export type Cam = { pos: V3; look: V3; fov: number; roll: number };
export type Shot = Partial<Cam> & { pos: V3; look: V3 };
/** a camera key: from frame f, glide over dur frames (default 24) into s(f), or cut to it */
export type Key = { f: number; dur?: number; cut?: boolean; s: (f: number) => Shot };

export const clamp01 = (x: number) => Math.max(0, Math.min(1, x));
export const smooth = (x: number) => { const u = clamp01(x); return u * u * (3 - 2 * u); };
export const easeOut = (u: number) => 1 - (1 - clamp01(u)) ** 4;
/** piecewise-linear table lookup: [[x, y], ...] in x order */
export const lin = (pts: [number, number][], x: number) => {
  if (x <= pts[0][0]) return pts[0][1];
  for (let i = 1; i < pts.length; i++) if (x <= pts[i][0]) {
    const [x0, y0] = pts[i - 1], [x1, y1] = pts[i];
    return y0 + ((y1 - y0) * (x - x0)) / (x1 - x0);
  }
  return pts[pts.length - 1][1];
};
export const add = (a: V3, b: V3): V3 => [a[0] + b[0], a[1] + b[1], a[2] + b[2]];
/** reference camera ease: symmetric smootherstep (attack = release, ~10 f each on a 23 f move) */
export const glide = (u: number) => { const x = clamp01(u); return x * x * x * (x * (6 * x - 15) + 10); };

const mix = (a: Cam, b: Cam, k: number): Cam => ({
  pos: a.pos.map((v, i) => v + (b.pos[i] - v) * k) as V3, look: a.look.map((v, i) => v + (b.look[i] - v) * k) as V3,
  fov: a.fov + (b.fov - a.fov) * k, roll: a.roll + (b.roll - a.roll) * k,
});
const full = (c: Shot): Cam => ({ fov: 40, roll: 0, ...c });
/** the camera at frame f from a shot's keys: the first key holds, every later one glides (or cuts) in from its frame */
export const runKeys = (keys: Key[], f: number): Cam => {
  let cur = full(keys[0].s(f));
  for (let i = 1; i < keys.length; i++) {
    const k = keys[i];
    if (f < k.f) break;
    cur = k.cut ? full(k.s(f)) : mix(cur, full(k.s(f)), glide((f - k.f) / (k.dur ?? 24)));
  }
  return cur;
};
/** frame at which the current key's move has finished (for picking billboard views per key, not per frame) */
export const keyEnd = (keys: Key[], f: number) => {
  let e = 0;
  for (const k of keys) if (f >= k.f) e = k.f + (k.cut ? 0 : k.dur ?? 24);
  return Math.max(f, e);
};
/** push-in factor since f0: the subject grows ~rate per frame; `punch` raises it (with 8 f soft edges) for the first n frames */
export const pushK = (f: number, f0: number, rate: number, punch = 0, n = 35) => {
  const x = Math.max(0, f - f0);
  let s = rate * x;
  if (punch > rate) for (let i = 0; i < Math.min(x, n); i++) s += (punch - rate) * Math.max(0, Math.min(1, (i + 0.5) / 8, (n - i - 0.5) / 8));
  return Math.exp(-s);
};
/** dolly push: the camera slides toward the look point by factor k */
export const dolly = (pos: V3, look: V3, k: number, rest: Partial<Cam> = {}): Shot =>
  ({ pos: [look[0] + (pos[0] - look[0]) * k, look[1] + (pos[1] - look[1]) * k, look[2] + (pos[2] - look[2]) * k], look, ...rest });
/** zoom push (the camera stays put, for lenses next to walls): tan(fov/2) shrinks by k */
export const zoom = (pos: V3, look: V3, fov: number, k: number, rest: Partial<Cam> = {}): Shot =>
  ({ pos, look, fov: (360 / Math.PI) * Math.atan(Math.tan((fov * Math.PI) / 360) * k), ...rest });
/** a roll-only move on top of an existing framing */
export const rolled = (s: (f: number) => Shot, roll: number) => (f: number): Shot => ({ ...s(f), roll });

/** impact kicks: [[seconds, gain], ...]. The image offset flips sign every frame (~3 px at 720p per unit), decays to 0
 *  in 7 f, roll +-0.23 deg per unit; a kick starts on the first frame at/after its event. */
export const kicksAt = (kicks: [number, number][], t: number) => {
  let a = 0;
  for (const [t0, g] of kicks) {
    const n = Math.floor((t - t0) * FPS + 1e-6);
    if (n >= 0 && n < 7) a += g * (n % 2 ? -1 : 1) * (1 - n / 7) ** 1.5;
  }
  return a;
};
/** the camera with a kick of amplitude a applied */
export const kicked = (c: Cam, a: number): Cam => {
  if (!a) return c;
  const d: V3 = [c.look[0] - c.pos[0], c.look[1] - c.pos[1], c.look[2] - c.pos[2]];
  const L = Math.hypot(...d), h = Math.hypot(d[0], d[2]) || 1;
  const m = (3 / 640) * Math.tan((c.fov * Math.PI) / 360) * L * a; // metres at the look distance for 3 px x a
  return { ...c, look: [c.look[0] - (d[2] / h) * m, c.look[1] + 0.6 * m, c.look[2] + (d[0] / h) * m], roll: c.roll + a * 0.004 };
};
/** the usual camAt: keys per shot id, plus the kicks */
export const makeCamAt = (cams: Record<number, Key[]>, kicks: [number, number][] = []) =>
  (id: number, f: number): Cam => kicked(runKeys(cams[id], f), kicksAt(kicks, f / FPS));

// ---------------- shots in time ----------------
export const shotAt = (shots: ShotDef[], f: number) => shots.find((s) => f >= s.a && f < s.b) ?? shots[shots.length - 1];
/** layers to draw at frame f: the base shot, plus the next shot fading in during a crossfade */
export const layersAt = (shots: ShotDef[], xfade: Record<number, number>, f: number): { id: number; alpha: number }[] => {
  for (const s of shots) {
    const x = xfade[s.id];
    if (x && f >= s.a - x / 2 && f < s.a + x / 2) return [{ id: s.id - 1, alpha: 1 }, { id: s.id, alpha: (f - (s.a - x / 2) + 1) / (x + 1) }];
  }
  return [{ id: shotAt(shots, f).id, alpha: 1 }];
};

// ---------------- lens ----------------
/** depth of field per shot (thin lens). cInf = blur-disc radius in px at 1080x1920 for things at infinity; 0 = all
 *  sharp. The reference has DOF on in ~1/3 of shots: close-ups 12-16, medium 10-12; establishing and wide shots
 *  stay sharp. focus = a world point (else the camera's look point). dur: frames to ease in from the previous. */
export type Dof = { f: number; dur?: number; cInf: number; focus?: (f: number) => V3 };
export const dofAtOf = (table: Dof[], f: number) => {
  let i = 0; while (i + 1 < table.length && f >= table[i + 1].f) i++;
  const d = table[i], p = table[Math.max(0, i - 1)];
  const k = d.dur ? Math.min(1, (f - d.f) / d.dur) : 1;
  return { cInf: p.cInf + (d.cInf - p.cInf) * k, focus: d.focus };
};
