// PROBE 2 camera grammar: the reference's measured camera, as a pure function
// of the frame number. Replaces kit/cameraPath.ts's poseAt/applyPose for the
// probe (that file is left alone).
//
// Source: github.com/mromidev/claude-animated-shorts,
// references/reports/motion.md (20 animated shorts measured frame by frame).
// Numbers taken from it:
//   - glides: "symmetric smootherstep", ~10 f in, ~10 f out, ~23 f total;
//     proposed 18-40 f for moves up to ~360 px; bigger reframes are hard cuts;
//     "start each glide about half its duration early" so the fastest frame
//     lands where the old snap was.                         -> GLIDE_* below
//   - holds: the camera is "almost never dead still"; quiet frames keep a
//     dolly push toward the look point, median 0.14 %/f, p75 0.34; proposed
//     hold rate 0.0015-0.0035 per frame of distance (default 0.0025), punch
//     words ~0.006 per frame for ~35 f.                     -> CREEP_* below
//   - the push "stops on an impact".                        -> KICK_CREEP_PAUSE
//   - impact kick: 7 frames, offset flips sign every frame (odd frames
//     negative, even positive), decay (1 - n/7)^1.5, ~3 px at 720p,
//     roll ~0.004 rad (~0.23 deg) per unit.                 -> KICK_* below
//   - emphasis rolls: 3.6-8 deg over >= 18 f (reference median 3.6 deg over
//     18 f).                                                 -> ROLL_MIN_FRAMES
//   - hand-held float: none (the report says to delete it). So there is none.
//
// TIMING RULES (what this file implements):
//   1. A beat is a shot. Its BASE pose eases from `from` to `to` over
//      [start, end] with smoothstep (was linear), clamped outside that range.
//   2. CREEP: on top of the base, the camera dollies toward the target by
//      `creep` (default 0.0025) of the current distance every frame, for the
//      whole time the shot is on screen, including its glide halves. Inside an
//      `emphasis` range the rate eases up to CREEP_EMPHASIS (0.006) over
//      CREEP_EASE frames each side. The rate drops to 0 for KICK_CREEP_PAUSE
//      frames from each kick, then eases back in over CREEP_EASE frames.
//      Creep is multiplicative (distance * exp(-sum of rates)), so it can
//      never reach or pass the target.
//   3. GLIDE vs CUT between consecutive beats a, b:
//      - b.cut: a hard cut at b.start. Shot a keeps creeping through any gap.
//      - else a glide, centred on the boundary c = (a.end + b.start) / 2, of
//        length L = max(G, gap) clamped to [GLIDE_MIN, GLIDE_MAX], where G is
//        `glideFrames` if given, else timed by move size: the report gives
//        smootherstep peak = 1.875 * distance / duration and a reference peak
//        of ~14-16 px/f, so G = 1.875 * movePx / 15 (movePx = median image
//        displacement of points around and behind the two targets, see movePx()). A move
//        over ~360 px at 720p (540 px here) should be a cut; glidePlan() flags
//        it, it is not converted silently. L is then
//        shrunk so it takes at most half of either beat, and shrunk
//        further if that leaves under 2 frames (then it is a cut). Inside the
//        window the state is mix(shotA(f), shotB(f), smootherstep(t)), where
//        both shots keep their own creep and drift running. smootherstep has
//        zero 1st and 2nd derivative at both ends, so position, speed and
//        acceleration are continuous at the window edges. b.via / b.viaTarget
//        bend the mixed path through a Catmull-Rom curve built per frame.
//   4. ROLLS: `rolls` are absolute roll targets in degrees, applied in `at`
//      order; each eases from the previous value with smootherstep over
//      max(dur ?? ROLL_MIN_FRAMES, ROLL_MIN_FRAMES) frames. {at, deg: 0}
//      returns to level.
//   5. KICKS: each kick at frame k adds, for n = f - k in [0, 7), a camera-space
//      offset whose sideways part is +a on even n and -a on odd n, with
//      a = KICK_PX * (1 - n/7)^1.5 converted to world units at the subject's
//      distance, a small upward lift, and a matching roll of KICK_ROLL rad.
//      Overlapping kicks add.
//   6. Pose.focus is always |pos - target| after creep and glide (the kick's
//      offset is a few millimetres and is left out), so depth of field tracks
//      the real distance.
//
// DETERMINISM: no Math.random, no Date, no state kept between calls. Creep is
// re-integrated from the shot's start on every call (a loop over at most the
// shot's length), so any frame can be rendered alone, in any order.
import * as THREE from "three";
import type { Beat, Pose } from "../kit/cameraPath";

export interface CameraMotion {
  /** frames where an impact kick starts */
  kicks?: number[];
  /** frame ranges [from, to] with faster creep (punch words) */
  emphasis?: [number, number][];
  /** eased roll changes: absolute target roll in degrees, reached over dur frames */
  rolls?: { at: number; deg: number; dur?: number }[];
  /** glide length when beats ask for a glide (clamped 18-40). Leave unset to
   *  time each glide by its move size (rule 3) — the recommended setting. */
  glideFrames?: number;
  /** hold creep, fraction of distance per frame (default 0.0025, source 0.0015-0.0035) */
  creep?: number;
}

export interface CameraState {
  pose: Pose;
  /** radians, about the view axis */
  roll: number;
  /** camera-space offset (kick): x right, y up, z back */
  offset: [number, number, number];
}

// ---------------------------------------------------------------- constants

export const GLIDE_DEFAULT = 24;
export const GLIDE_MIN = 18;
export const GLIDE_MAX = 40;
export const CREEP_HOLD = 0.0025;
export const CREEP_EMPHASIS = 0.006;
/** the creep's fraction applies to at most this much of the aim distance (m) */
export const CREEP_REF_M = 10;
/** frames the creep rate takes to ease between levels */
export const CREEP_EASE = 6;
/** frames the push stops for at each kick */
export const KICK_CREEP_PAUSE = 4;
export const KICK_FRAMES = 7;
/** 3 px at 720 px wide, scaled to our 1080 px wide frame */
export const KICK_PX = 3 * (1080 / 720);
export const KICK_LIFT = 0.4; // vertical part, as a fraction of the sideways part
export const KICK_ROLL = 0.004; // rad
export const ROLL_MIN_FRAMES = 18;
const FRAME_W = 1080;
const ASPECT = 1080 / 1920;
/** creep keeps running at most this long after the last beat ends */
const TAIL = 300;

// ------------------------------------------------------------------ helpers

const clamp01 = (x: number) => (x <= 0 ? 0 : x >= 1 ? 1 : x);
const smoothstep = (x: number) => {
  const t = clamp01(x);
  return t * t * (3 - 2 * t);
};
const smootherstep = (x: number) => {
  const t = clamp01(x);
  return t * t * t * (t * (t * 6 - 15) + 10);
};
type V3 = [number, number, number];
const lerp = (a: number, b: number, t: number) => a + (b - a) * t;
const lerp3 = (a: V3, b: V3, t: number): V3 => [lerp(a[0], b[0], t), lerp(a[1], b[1], t), lerp(a[2], b[2], t)];
const fin = (x: number, d = 0) => (Number.isFinite(x) ? x : d);

/** 0..1 envelope: 1 inside [a, b], eased to 0 over CREEP_EASE frames outside */
const envelope = (g: number, a: number, b: number) => {
  if (g >= a && g <= b) return 1;
  if (g < a) return smoothstep(1 - (a - g) / CREEP_EASE);
  return smoothstep(1 - (g - b) / CREEP_EASE);
};

const creepRate = (g: number, m: CameraMotion) => {
  const base = m.creep ?? CREEP_HOLD;
  let emph = 0;
  for (const [a, b] of m.emphasis ?? []) emph = Math.max(emph, envelope(g, Math.min(a, b), Math.max(a, b)));
  let rate = lerp(base, Math.max(base, CREEP_EMPHASIS), emph);
  // the push stops at the hit, then eases back in
  for (const k of m.kicks ?? []) {
    if (g >= k && g < k + KICK_CREEP_PAUSE) rate = 0;
    else if (g >= k + KICK_CREEP_PAUSE && g < k + KICK_CREEP_PAUSE + CREEP_EASE)
      rate *= smoothstep((g - (k + KICK_CREEP_PAUSE) + 1) / (CREEP_EASE + 1));
  }
  return rate;
};

/** sum of creep rates over frames [from, f), with a fractional last frame */
const creepSum = (from: number, f: number, m: CameraMotion) => {
  if (!(f > from)) return 0;
  let s = 0;
  const whole = Math.floor(f - from);
  for (let i = 0; i < whole; i++) s += creepRate(from + i, m);
  const frac = f - from - whole;
  if (frac > 0) s += frac * creepRate(from + whole, m);
  return s;
};

// ------------------------------------------------------------- the schedule

interface Window {
  a: number; // first frame of the glide
  b: number; // last frame (state is fully the next shot here)
}

// --- move size, in pixels of a 1080x1920 frame, for timing a glide by its size
const _camA = new THREE.PerspectiveCamera(40, ASPECT, 0.1, 1000);
const _camB = new THREE.PerspectiveCamera(40, ASPECT, 0.1, 1000);
const _v = new THREE.Vector3();
const placeCam = (cam: THREE.PerspectiveCamera, p: Pose) => {
  cam.position.set(...p.pos);
  cam.fov = fin(p.fov, 40);
  cam.up.set(0, 1, 0);
  cam.lookAt(_v.set(...p.target));
  cam.updateProjectionMatrix();
  cam.updateMatrixWorld(true);
};
const toPx = (cam: THREE.PerspectiveCamera, w: THREE.Vector3) => {
  const v = w.clone().applyMatrix4(cam.matrixWorldInverse);
  if (v.z > -0.05) return null; // behind the camera
  v.applyMatrix4(cam.projectionMatrix);
  return new THREE.Vector2((v.x * 0.5 + 0.5) * FRAME_W, (v.y * 0.5 + 0.5) * (FRAME_W / ASPECT));
};
/** Median image displacement of points around both look targets and behind
 *  them, from pose a
 *  to pose b. The same kind of number the reference report measures (px/f of
 *  image motion), so the glide length can follow the report's rule. */
export const movePx = (a: Pose, b: Pose) => {
  placeCam(_camA, a);
  placeCam(_camB, b);
  const ds: number[] = [];
  // the subject region, plus a background point as far behind each target as
  // its camera is in front (an orbit barely moves the subject but sweeps the
  // background, which is most of the image)
  const behind = (p: Pose): V3 => [2 * p.target[0] - p.pos[0], 2 * p.target[1] - p.pos[1], 2 * p.target[2] - p.pos[2]];
  for (const t of [a.target, b.target, behind(a), behind(b)]) {
    for (const o of [[0, 0, 0], [1.5, 0, 0], [-1.5, 0, 0], [0, 1.5, 0], [0, -1, 0], [0, 0, 1.5], [0, 0, -1.5]]) {
      const w = new THREE.Vector3(t[0] + o[0], t[1] + o[1], t[2] + o[2]);
      const pa = toPx(_camA, w);
      const pb = toPx(_camB, w);
      if (pa && pb) ds.push(pa.distanceTo(pb));
    }
  }
  if (!ds.length) return Infinity;
  ds.sort((x, y) => x - y);
  return ds[Math.floor(ds.length / 2)];
};

/** Glide length by move size (rule 3): smootherstep's peak speed is
 *  1.875 * distance / duration, and the reference's median move peaks at
 *  ~14-16 px/f, so L = 1.875 * px / GLIDE_PEAK_PX, clamped to 18-40 f. */
export const GLIDE_PEAK_PX = 15;
/** the report's limit for a glide; bigger moves should be cuts */
export const GLIDE_MAX_PX = 360 * (FRAME_W / 720);
const autoGlide = (px: number) =>
  Math.min(GLIDE_MAX, Math.max(GLIDE_MIN, Number.isFinite(px) ? (1.875 * px) / GLIDE_PEAK_PX : GLIDE_MAX));

/** Glide window into beat i (i >= 1), or null for a cut. See rule 3. */
const glideInto = (beats: Beat[], i: number, m: CameraMotion): Window | null => {
  const prev = beats[i - 1];
  const next = beats[i];
  if (next.cut) return null;
  const gap = Math.max(0, next.start - prev.end);
  const base = m.glideFrames !== undefined ? fin(m.glideFrames, GLIDE_DEFAULT) : autoGlide(movePx(prev.to, next.from));
  let len = Math.min(GLIDE_MAX, Math.max(GLIDE_MIN, Math.max(base, gap)));
  const c = (prev.end + next.start) / 2;
  // take at most half of either beat (plus the gap), so a short beat still
  // gets a moment of its own and two glides never overlap
  const room = (beat: Beat) => Math.max(0, beat.end - beat.start) / 2;
  const half = Math.min(len / 2, gap / 2 + room(prev), gap / 2 + room(next));
  len = 2 * half;
  if (len < 2) return null;
  return { a: c - half, b: c + half };
};

/** For QA / the lead: how each boundary will be played. `tooBig` flags a glide
 *  whose move exceeds the report's ~360 px (at 720p) glide limit — the report
 *  says to make those hard cuts (set cut: true on the beat). */
export const glidePlan = (beats: Beat[], motion: CameraMotion) =>
  beats.slice(1).map((b, k) => {
    const i = k + 1;
    const w = glideInto(beats, i, motion ?? {});
    const px = movePx(beats[i - 1].to, b.from);
    return { beat: i, cut: !w, from: w?.a ?? b.start, to: w?.b ?? b.start, frames: w ? w.b - w.a : 0, movePx: px, tooBig: !!w && px > GLIDE_MAX_PX };
  });

interface Segment {
  beat: number;
  live: number; // frame from which this shot's creep integrates
  until: number; // frame after which this shot is no longer on screen
}

const schedule = (beats: Beat[], m: CameraMotion) => {
  const wins: (Window | null)[] = beats.map((_, i) => (i === 0 ? null : glideInto(beats, i, m)));
  const segs: Segment[] = beats.map((b, i) => {
    const w = wins[i];
    const live = i === 0 ? b.start : w ? w.a : b.start;
    const nw = wins[i + 1];
    const until = i + 1 < beats.length ? (nw ? nw.b : beats[i + 1].start) : b.end + TAIL;
    return { beat: i, live, until };
  });
  return { wins, segs };
};

// ------------------------------------------------------------- shot states

/** One shot's own pose at frame f: eased drift + multiplicative creep. */
const shotPose = (beats: Beat[], segs: Segment[], i: number, f: number, m: CameraMotion) => {
  const b = beats[i];
  const span = b.end - b.start;
  const u = span > 0 ? smoothstep((f - b.start) / span) : f >= b.start ? 1 : 0;
  const pos = lerp3(b.from.pos, b.to.pos, u);
  const target = lerp3(b.from.target, b.to.target, u);
  const fov = lerp(b.from.fov, b.to.fov, u);
  const s = segs[i];
  const fc = Math.min(Math.max(f, s.live), s.until);
  const k = Math.exp(-creepSum(s.live, fc, m) * (b.creep ?? 1));
  // the creep is a fraction of the distance to the aim point, but of at most CREEP_REF_M of it: a shot aimed at a
  // boat 78 m away used to drive the lens 8 m forward, through whoever stood in front
  const d = Math.hypot(pos[0] - target[0], pos[1] - target[1], pos[2] - target[2]);
  const travel = d > 1e-6 ? ((1 - k) * Math.min(d, CREEP_REF_M)) / d : 0;
  const p: V3 = [
    pos[0] - (pos[0] - target[0]) * travel,
    pos[1] - (pos[1] - target[1]) * travel,
    pos[2] - (pos[2] - target[2]) * travel,
  ];
  return { pos: p, target, fov };
};

const along = (a: V3, vias: V3[], b: V3, t: number): V3 => {
  const pts = [a, ...vias, b].map((p) => new THREE.Vector3(...p));
  const curve = new THREE.CatmullRomCurve3(pts, false, "centripetal");
  if (curve.getLength() < 1e-6) return lerp3(a, b, t);
  const p = curve.getPointAt(clamp01(t));
  return [p.x, p.y, p.z];
};

// ------------------------------------------------------------------- rolls

const rollAt = (f: number, m: CameraMotion) => {
  const rs = [...(m.rolls ?? [])].sort((x, y) => x.at - y.at);
  let v = 0;
  for (const r of rs) {
    if (f <= r.at) break;
    const dur = Math.max(ROLL_MIN_FRAMES, fin(r.dur ?? ROLL_MIN_FRAMES, ROLL_MIN_FRAMES));
    v = lerp(v, (fin(r.deg) * Math.PI) / 180, smootherstep((f - r.at) / dur));
  }
  return v;
};

// ------------------------------------------------------------------- kicks

/** signed unit kick at frame f (sum of all kicks), sign flips every frame */
export const kickAt = (f: number, m: CameraMotion) => {
  let s = 0;
  for (const k of m.kicks ?? []) {
    const n = Math.floor(f - k);
    if (n < 0 || n >= KICK_FRAMES) continue;
    s += (n % 2 === 0 ? 1 : -1) * Math.pow(1 - n / KICK_FRAMES, 1.5);
  }
  return s;
};

const kickMagnitude = (f: number, m: CameraMotion) => {
  let s = 0;
  for (const k of m.kicks ?? []) {
    const n = Math.floor(f - k);
    if (n >= 0 && n < KICK_FRAMES) s += Math.pow(1 - n / KICK_FRAMES, 1.5);
  }
  return s;
};

// --------------------------------------------------------------------- API

const FALLBACK: Pose = { pos: [0, 1.6, 8], target: [0, 1.2, 0], fov: 40, focus: 8 };

export const cameraStateAt = (beats: Beat[], f: number, motion: CameraMotion): CameraState => {
  const m = motion ?? {};
  f = fin(f);
  if (!beats.length) return { pose: FALLBACK, roll: rollAt(f, m), offset: [0, 0, 0] };
  const { wins, segs } = schedule(beats, m);

  // which shot is on screen: the last one whose glide (or cut) has begun
  let pos: V3;
  let target: V3;
  let fov: number;
  let idx = 0;
  for (let i = 1; i < beats.length; i++) {
    const w = wins[i];
    const switchAt = w ? w.a : beats[i].start;
    if (f >= switchAt) idx = i;
  }
  // mid-glide into shot idx: mix the outgoing and incoming shots
  const w = wins[idx];
  if (w && f < w.b) {
    const t = smootherstep((f - w.a) / (w.b - w.a));
    const A = shotPose(beats, segs, idx - 1, f, m);
    const B = shotPose(beats, segs, idx, f, m);
    const nb = beats[idx];
    pos = nb.via && nb.via.length ? along(A.pos, nb.via, B.pos, t) : lerp3(A.pos, B.pos, t);
    target = nb.viaTarget && nb.viaTarget.length ? along(A.target, nb.viaTarget, B.target, t) : lerp3(A.target, B.target, t);
    fov = lerp(A.fov, B.fov, t);
  } else {
    const S = shotPose(beats, segs, idx, f, m);
    pos = S.pos;
    target = S.target;
    fov = S.fov;
  }

  const focus = Math.max(1e-3, Math.hypot(pos[0] - target[0], pos[1] - target[1], pos[2] - target[2]));
  // kick: KICK_PX on a FRAME_W-wide frame, as world units at the subject's distance
  const vfov = (fin(fov, 40) * Math.PI) / 180;
  const worldPerPx = (2 * focus * Math.tan(vfov / 2) * ASPECT) / FRAME_W;
  const kx = kickAt(f, m) * KICK_PX * worldPerPx;
  const ky = kickMagnitude(f, m) * KICK_PX * KICK_LIFT * worldPerPx;
  const roll = rollAt(f, m) + kickAt(f, m) * KICK_ROLL;
  return {
    pose: { pos, target, fov: fin(fov, 40), focus },
    roll: fin(roll),
    offset: [fin(kx), fin(ky), 0],
  };
};

const _t = new THREE.Vector3();

export const applyCameraState = (cam: THREE.PerspectiveCamera, s: CameraState) => {
  const p = s.pose;
  cam.position.set(...p.pos);
  cam.fov = p.fov;
  cam.up.set(0, 1, 0);
  cam.lookAt(_t.set(...p.target));
  cam.rotateZ(s.roll); // about the view axis
  // camera-space offset AFTER the look-at, so it translates rather than re-aims
  cam.translateX(s.offset[0]);
  cam.translateY(s.offset[1]);
  cam.translateZ(s.offset[2]);
  cam.updateProjectionMatrix();
  cam.updateMatrixWorld(true);
};
