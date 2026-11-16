// Low-Poly Skit cycles (TMDEV-250): a walk, a dance and an idle as pure functions of the frame, so a still, the gate and
// the render agree. A step lands every STEP_FRAMES (the reference steps every 22 frames at 60 fps, 11 at 30); a
// whole gait is two steps. Footfalls are listed so the camera can jolt on each one.
import type { Pose } from "./poses";

export const STEP_FRAMES = 11;
const TAU = Math.PI * 2;

/** a walk: `f` frames since the walk began, `speed` stride scale (1 = a brisk walk) */
export function walkPose(f: number, speed = 1): Pose {
  const ph = (TAU * f) / (STEP_FRAMES * 2);
  const s = Math.sin(ph), c = Math.cos(ph);
  const a = 0.55 * speed;
  return {
    y: Math.abs(Math.cos(ph)) * -0.012 + 0.006,
    hipL: [a * s, 0.04], hipR: [-a * s, 0.04],
    knL: 0.08 + 0.7 * speed * Math.max(0, c), knR: 0.08 + 0.7 * speed * Math.max(0, -c),
    shL: [-a * 0.8 * s, 0.1], shR: [a * 0.8 * s, 0.1], elL: 0.25, elR: 0.25,
    twist: 0.08 * s * speed, lean: 0.05 * speed,
  };
}
/** the frames, from f0 up to (not including) f1, on which a foot lands: the camera jolts and the boom plays there */
export function footfalls(f0: number, f1: number, startedAt = f0): number[] {
  const out: number[] = [];
  const first = startedAt + STEP_FRAMES / 2;
  for (let k = Math.ceil((f0 - first) / STEP_FRAMES); first + k * STEP_FRAMES < f1; k++) {
    const t = Math.round(first + k * STEP_FRAMES);
    if (t >= f0 && t < f1) out.push(t);
  }
  return out;
}

/** a jig: alternating knee lifts every 5 frames, arms locked at the sides, a small bob; loops every 10 frames */
export function dancePose(f: number): Pose {
  const beat = Math.floor(f / 5) % 2;
  const k = (f % 5) / 5;
  const lift = Math.sin(Math.PI * k);
  return {
    y: 0.012 * Math.abs(Math.sin((Math.PI * f) / 5)),
    hipL: [beat === 0 ? 0.9 * lift : 0, 0.05], hipR: [beat === 1 ? 0.9 * lift : 0, 0.05],
    knL: beat === 0 ? 1.1 * lift : 0.1, knR: beat === 1 ? 1.1 * lift : 0.1,
    shL: [0, 0.08], shR: [0, 0.08], elL: 0.1, elR: 0.1, lean: 0.03,
  };
}

/** a slow breathing sway; `seed` offsets a crowd so nobody breathes in step */
export function idlePose(f: number, seed = 0): Pose {
  const s = Math.sin(((f + seed * 7) * TAU) / 60);
  return { y: 0.004 * s, shL: [0.02 * s, 0.12], shR: [-0.02 * s, 0.12], elL: 0.12, elR: 0.12, nod: 0.02 * s };
}
