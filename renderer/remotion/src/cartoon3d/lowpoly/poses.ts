// Low-Poly Skit poses (TMDEV-250): a pose is plain numbers (radians), applied to a Figure's joints. Semantic axes, so a
// pose reads the same on both sides of the body: `fwd` raises or swings forward, `out` moves away from the body,
// `bend` folds a knee or elbow. A snap is 2 to 6 frames with no anticipation (the reference's strikes land in 2 to 6
// frames at 60 fps; here at 30 fps), and a fall or a switch is a pose change, not a simulation.
import type { Figure } from "./figure";

type Pair = [fwd: number, out: number];
export type Pose = {
  /** the whole body, in the figure root's frame: lift (m), forward lean, roll */
  y?: number; pitch?: number; roll?: number;
  /** the torso above the hips */
  lean?: number; twist?: number; side?: number;
  /** the head on the neck: nod (down), turn, tilt */
  nod?: number; turn?: number; tilt?: number;
  shL?: Pair; shR?: Pair; elL?: number; elR?: number;
  hipL?: Pair; hipR?: Pair; knL?: number; knR?: number;
};
const KEYS: (keyof Pose)[] = ["y", "pitch", "roll", "lean", "twist", "side", "nod", "turn", "tilt", "shL", "shR", "elL", "elR", "hipL", "hipR", "knL", "knR"];

/** put a figure in a pose; anything a pose leaves out is at rest */
export function applyPose(fig: Figure, p: Pose): void {
  const j = fig.joints, v = <K extends keyof Pose>(k: K) => (p[k] ?? 0) as number;
  const pr = (k: "shL" | "shR" | "hipL" | "hipR"): Pair => p[k] ?? [0, 0];
  fig.body.position.y = v("y");
  fig.body.rotation.set(v("pitch"), 0, v("roll"));
  j.spine.rotation.set(v("lean"), v("twist"), v("side"));
  j.neck.rotation.set(v("nod"), v("turn"), v("tilt"));
  j.shoulderL.rotation.set(-pr("shL")[0], 0, pr("shL")[1]);
  j.shoulderR.rotation.set(-pr("shR")[0], 0, -pr("shR")[1]);
  j.elbowL.rotation.set(-v("elL"), 0, 0);
  j.elbowR.rotation.set(-v("elR"), 0, 0);
  j.hipL.rotation.set(-pr("hipL")[0], 0, pr("hipL")[1]);
  j.hipR.rotation.set(-pr("hipR")[0], 0, -pr("hipR")[1]);
  j.kneeL.rotation.set(v("knL"), 0, 0);
  j.kneeR.rotation.set(v("knR"), 0, 0);
}

/** the pose a fraction k of the way from a to b */
export function lerpPose(a: Pose, b: Pose, k: number): Pose {
  const out: Pose = {};
  for (const key of KEYS) {
    const x = a[key], y = b[key];
    if (x === undefined && y === undefined) continue;
    if (Array.isArray(x) || Array.isArray(y)) {
      const xa = (x as Pair | undefined) ?? [0, 0], ya = (y as Pair | undefined) ?? [0, 0];
      (out as Record<string, unknown>)[key] = [xa[0] + (ya[0] - xa[0]) * k, xa[1] + (ya[1] - xa[1]) * k];
    } else (out as Record<string, unknown>)[key] = ((x as number) ?? 0) + (((y as number) ?? 0) - ((x as number) ?? 0)) * k;
  }
  return out;
}

/** a snap: ease-out over `dur` frames from frame f0 (0 before f0, 1 from f0 + dur) */
export const snapK = (f: number, f0: number, dur = 4) => {
  const u = Math.max(0, Math.min(1, (f - f0) / Math.max(1, dur)));
  return 1 - (1 - u) ** 3;
};

/** a timeline of poses: each key snaps in from its frame over `dur` frames (default 4); before the first key it holds the first */
export type PoseKey = { f: number; pose: Pose; dur?: number };
export function poseTrack(keys: PoseKey[], f: number): Pose {
  let cur = keys[0].pose;
  for (let i = 1; i < keys.length; i++) {
    const k = keys[i];
    if (f < k.f) break;
    cur = lerpPose(cur, k.pose, snapK(f, k.f, k.dur ?? 4));
  }
  return cur;
}

// ---- the named poses ----
const SIDEARMS: Pose = { shL: [0, 0.12], shR: [0, 0.12] };
export const POSES = {
  stand: { ...SIDEARMS, elL: 0.12, elR: 0.12 },
  /** on a seat 0.4 m up; feet on the floor */
  sit: { y: -0.183, hipL: [1.5, 0.05], hipR: [1.5, 0.05], knL: 1.5, knR: 1.5, shL: [0.5, 0.1], shR: [0.5, 0.1], elL: 1.1, elR: 1.1 },
  /** on the back, face up, head toward -z */
  lie: { y: 0.075, pitch: -Math.PI / 2, shL: [0, 0.35], shR: [0, 0.35], elL: 0.1, elR: 0.1, hipL: [0, 0.12], hipR: [0, 0.12] },
  /** flat on the back, limbs flung out (the result of a hit) */
  fall: { y: 0.075, pitch: -Math.PI / 2, shL: [0.4, 1.3], shR: [0.2, 1.1], hipL: [0, 0.5], hipR: [0, 0.4], elL: 0.3, elR: 0.5, nod: -0.2 },
  /** one arm straight up */
  thrust: { shL: [3.05, 0.1], shR: [0, 0.12], elL: 0.05, lean: -0.05 },
  /** both arms up and forward, gripping a tool (a broom) */
  bang: { shL: [2.7, 0.15], shR: [2.7, 0.15], elL: 0.25, elR: 0.25, lean: -0.1, nod: -0.15 },
  point: { shR: [1.55, 0.1], elR: 0.05, shL: [0, 0.12], turn: 0.15 },
  /** both hands out in front, holding something */
  hold: { shL: [1.0, 0.1], shR: [1.0, 0.1], elL: 1.2, elR: 1.2 },
  cheer: { shL: [2.7, 0.7], shR: [2.7, 0.7], elL: 0.2, elR: 0.2, nod: -0.2, hipL: [0, 0.12], hipR: [0, 0.12] },
  shrug: { shL: [0.2, 0.55], shR: [0.2, 0.55], elL: 1.3, elR: 1.3, tilt: 0.18 },
  slump: { lean: 0.35, nod: 0.45, shL: [0.1, 0.1], shR: [0.1, 0.1], elL: 0.2, elR: 0.2, knL: 0.15, knR: 0.15 },
  /** one foot driven forward and down (a stomp, a kick) */
  stomp: { hipR: [1.1, 0.05], knR: 0.2, lean: -0.15, shL: [0.5, 0.5], shR: [0.4, 0.4], elL: 0.4, elR: 0.4, hipL: [0, 0.05], knL: 0.1 },
  /** hands up, head back: a flinch */
  flinch: { lean: -0.25, nod: -0.25, shL: [1.9, 0.3], shR: [1.9, 0.3], elL: 1.6, elR: 1.6, knL: 0.3, knR: 0.3 },
} satisfies Record<string, Pose>;
export type PoseName = keyof typeof POSES;
