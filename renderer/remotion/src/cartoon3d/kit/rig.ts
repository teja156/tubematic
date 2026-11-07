// SPIKE 2: character motion mechanics, shared by every cutout.
//
// Every number here is from the measured reference reports in
// github.com/mromidev/claude-animated-shorts (references/reports/motion.md),
// which measured 20 shorts frame by frame. The point of the module is that a
// character is DRAWN FROM CONTINUOUS VALUES each frame, so the animation is
// "on ones" with no flip-booking between fixed poses.
//
// Measured targets this implements:
//   - a step takes 9-12 frames (2.5-3.3 steps/s); ours was 15-38
//   - body bob 3-7 % of height, LOWEST AT CONTACT; ours was 1.7 %
//   - lean swings 1 deg at passing to 7 deg at contact, in phase with the bob
//   - the stance foot is PLANTED: it tracks the ground, it does not skate
//   - blinks every 0.5-2.3 s, shaped over 4 frames (half / shut / shut / half)
//   - a reaction lands 0-3 frames BEFORE its word, never after

export type P = [number, number];

export const FPS = 30;
/** reactions land this many frames before the beat they belong to */
export const LEAD = 2;

export const clamp01 = (x: number) => Math.max(0, Math.min(1, x));
export const smoothstep = (x: number) => {
  const t = clamp01(x);
  return t * t * (3 - 2 * t);
};
/** Ken Perlin's smootherstep: zero first AND second derivative at both ends, so
 *  a camera or limb move starts and stops with no visible corner */
export const smootherstep = (x: number) => {
  const t = clamp01(x);
  return t * t * t * (t * (t * 6 - 15) + 10);
};
export const lerp = (a: number, b: number, t: number) => a + (b - a) * t;
export const lerpP = (a: P, b: P, t: number): P => [lerp(a[0], b[0], t), lerp(a[1], b[1], t)];

/** deterministic per-character noise in [0, 1) — same character, same frame, same value */
export const rnd = (seed: number, k: number) => {
  const x = Math.sin(seed * 127.1 + k * 311.7) * 43758.5453;
  return x - Math.floor(x);
};

/** Two-bone IK in canvas space. Given the hip and the foot, place the knee so the
 *  thigh and shin keep their lengths. `bend` = +1 knee forward, -1 knee back.
 *  This is what stops the legs stretching when the stride changes: the foot is
 *  placed where the GROUND needs it and the knee follows, rather than the foot
 *  hanging off a fixed-angle thigh (which is what makes feet skate). */
export const ik = (hip: P, foot: P, thigh: number, shin: number, bend = 1): P => {
  const dx = foot[0] - hip[0];
  const dy = foot[1] - hip[1];
  const reach = Math.hypot(dx, dy);
  const d = Math.max(1e-3, Math.min(reach, thigh + shin - 0.001));
  const a = (thigh * thigh - shin * shin + d * d) / (2 * d);
  const h = Math.sqrt(Math.max(0, thigh * thigh - a * a));
  const mx = hip[0] + (dx * a) / d;
  const my = hip[1] + (dy * a) / d;
  // perpendicular to the hip->foot line
  return [mx + ((h * dy) / d) * bend, my - ((h * dx) / d) * bend];
};

export type Foot = { pos: P; planted: boolean };

/** One leg of a walk cycle with a PLANTED stance foot.
 *  phase 0..1. Stance is the first half: the foot sits on the ground and travels
 *  straight backwards at constant speed, exactly cancelling the character's
 *  forward motion. Swing is the second half: it lifts and eases forward.
 *  `stride` is the total horizontal travel in canvas units, which the caller
 *  derives from the character's real world speed — that is the tie between
 *  stride and speed the reference report asks for. */
export const footAt = (phase: number, stride: number, lift: number, groundY: number): Foot => {
  const p = ((phase % 1) + 1) % 1;
  if (p < 0.5) {
    const s = p / 0.5; // 0 at contact -> 1 at toe-off
    return { pos: [stride / 2 - stride * s, groundY], planted: true };
  }
  const s = (p - 0.5) / 0.5;
  return { pos: [-stride / 2 + stride * smootherstep(s), groundY - lift * Math.sin(Math.PI * s)], planted: false };
};

/** Vertical body offset (canvas units, +down). Lowest at contact (phase 0 and 0.5),
 *  highest at mid-stance — the reference measures 3-7 % of figure height. */
export const bobAt = (phase: number, amp: number) => (amp / 2) * Math.cos(4 * Math.PI * phase);

/** Forward lean in degrees, in phase with the bob: ~1 deg passing, ~7 deg contact. */
export const leanAt = (phase: number, base = 4, swing = 3) => base + swing * Math.cos(4 * Math.PI * phase);

/** Eyelid 0 = open .. 1 = shut, shaped over 4 frames (half / shut / shut / half).
 *  Gaps are 0.5-2.3 s, deterministic per character. Any time in `swaps` (seconds)
 *  forces a blink across it, because the reference hides every expression change
 *  inside a blink rather than cutting the face. */
const LID = [0.5, 1, 1, 0.5];
export const lidAt = (t: number, seed: number, swaps: number[] = []) => {
  for (const ts of swaps) {
    const k = Math.floor((t - ts + LEAD / FPS) * FPS) + 1;
    if (k >= 0 && k < 4) return LID[k];
  }
  let s = -2 * rnd(seed, 9);
  for (let n = 0; s <= t && n < 500; n++) {
    const k = Math.floor((t - s) * FPS);
    if (k >= 0 && k < 4) return LID[k];
    s += 0.5 + 1.8 * rnd(seed * 31 + n, 13);
  }
  return 0;
};

/** A held wind-up then a 1-frame strike, as the reference does an impact.
 *  Returns 0 = fully wound up .. 1 = at rest. `hit` is the contact frame; contact
 *  lands exactly on the beat, the wind-up is 4 frames and is HELD for 7. */
export const strikeAt = (frame: number, hits: number[]) => {
  let k = 1;
  for (const h of hits) {
    const n = frame - h;
    if (n >= -11 && n < -7) k = Math.min(k, 1 - smoothstep((n + 11) / 4));
    else if (n >= -7 && n < 0) k = 0;
  }
  return k;
};

// ------------------------------------------------------------------ FK arms
//
// PROBE 2 fix: an arm pose is two bone DIRECTIONS, not two end points. Blending
// hand positions in canvas space and re-solving the elbow with IK every frame
// is what made the elbows flip sides and the hands fold through the torso mid
// gesture (the IK hint drifted across the shoulder-hand line). Angles blend on
// arcs, so a hand swings out and up the way an arm really moves, the elbow is a
// continuous function of the blend, and nothing can ever stretch past its bones.

/** degrees, canvas convention: 0 = +x (viewer's right), 90 = straight UP */
export type ArmPose = {
  /** upper arm direction */
  ua: number;
  /** elbow bend: forearm direction = ua + bend, in (-180, 180] */
  bend: number;
  /** bone length scales (foreshortening toward the camera); default 1 */
  su?: number;
  sf?: number;
};

export const dirOf = (deg: number): P => [Math.cos((deg * Math.PI) / 180), -Math.sin((deg * Math.PI) / 180)];
export const degOf = (dx: number, dy: number) => (Math.atan2(-dy, dx) * 180) / Math.PI;
/** wrap to (-180, 180] */
export const wrapDeg = (a: number) => {
  let x = ((a + 180) % 360) - 180;
  if (x <= -180) x += 360;
  return x;
};
/** shortest-arc lerp between two angles */
export const lerpDeg = (a: number, b: number, t: number) => a + wrapDeg(b - a) * t;

/** an arm as angles, from drawn points (used for the walk swing, which is
 *  authored as a hand position) */
export const armPose = (s: P, e: P, h: P, upper: number, fore: number): ArmPose => {
  const ua = degOf(e[0] - s[0], e[1] - s[1]);
  const fa = degOf(h[0] - e[0], h[1] - e[1]);
  return { ua, bend: wrapDeg(fa - ua), su: Math.hypot(e[0] - s[0], e[1] - s[1]) / upper, sf: Math.hypot(h[0] - e[0], h[1] - e[1]) / fore };
};

/** shoulder -> elbow -> hand from an ArmPose */
export const armFK = (s: P, a: ArmPose, upper: number, fore: number): [P, P, P] => {
  const u = dirOf(a.ua);
  const f = dirOf(a.ua + a.bend);
  const lu = upper * (a.su ?? 1);
  const lf = fore * (a.sf ?? 1);
  const e: P = [s[0] + u[0] * lu, s[1] + u[1] * lu];
  return [s, e, [e[0] + f[0] * lf, e[1] + f[1] * lf]];
};

/** blend two arm poses on arcs. A forearm that has to swing more than ~100 deg
 *  dips in length through the middle of the move (it is folding through depth,
 *  toward the camera) rather than sweeping a full circle across the body. */
export const mixArmPose = (a: ArmPose, b: ArmPose, t: number): ArmPose => {
  const db = wrapDeg(b.bend - a.bend);
  const fold = clamp01((Math.abs(db) - 100) / 80) * 0.45 * Math.sin(Math.PI * t);
  return {
    ua: lerpDeg(a.ua, b.ua, t),
    bend: a.bend + db * t,
    su: lerp(a.su ?? 1, b.su ?? 1, t),
    sf: lerp(a.sf ?? 1, b.sf ?? 1, t) * (1 - fold),
  };
};

/** Keep the hand inside x = [minX, maxX] (the 512 canvas, less a hand). A
 *  hand that would leave the canvas mid-blend comes TOWARD the camera instead:
 *  the bones foreshorten, the angles stay, so the move stays continuous. */
export const fitArmX = (s: P, a: ArmPose, upper: number, fore: number, minX: number, maxX: number): ArmPose => {
  const u = dirOf(a.ua);
  const f = dirOf(a.ua + a.bend);
  let su = a.su ?? 1;
  let sf = a.sf ?? 1;
  const ex = s[0] + u[0] * upper * su;
  if (ex > maxX && u[0] > 0) su *= (maxX - s[0]) / (ex - s[0]);
  else if (ex < minX && u[0] < 0) su *= (minX - s[0]) / (ex - s[0]);
  const ex2 = s[0] + u[0] * upper * su;
  const hx = ex2 + f[0] * fore * sf;
  if (hx > maxX && f[0] > 0) sf *= (maxX - ex2) / (hx - ex2);
  else if (hx < minX && f[0] < 0) sf *= (minX - ex2) / (hx - ex2);
  return { ...a, su: Math.max(0.3, su), sf: Math.max(0.3, sf) };
};
