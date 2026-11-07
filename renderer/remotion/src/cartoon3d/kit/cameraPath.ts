// Gliding camera: a list of beats. Inside a beat the camera drifts slowly from
// `from` to `to` (a push-in or a crab). Between beats it glides with a cubic
// Hermite curve whose end tangents match the drifts on both sides, so speed is
// continuous (never a snap) and the move eases in and out over the whole glide.
// A beat may be marked `cut: true` to start with a hard cut instead of a glide.
import * as THREE from "three";

export interface Pose {
  pos: [number, number, number];
  target: [number, number, number];
  fov: number;
  focus: number;
}

export interface Beat {
  start: number; // first frame of the drift
  end: number; // last frame of the drift
  from: Pose;
  to: Pose;
  cut?: boolean;
  /** multiplier on the hold creep for this shot (default 1; 0 = none, a shot that follows a prop keeps its framing) */
  creep?: number;
  // optional extra control points the glide INTO this beat passes through
  via?: [number, number, number][];
  // optional look-at points the glide's target passes through
  viaTarget?: [number, number, number][];
}

type Vec = number[];
const flat = (p: Pose): Vec => [...p.pos, ...p.target, p.fov, p.focus];
const toPose = (v: Vec): Pose => ({
  pos: [v[0], v[1], v[2]],
  target: [v[3], v[4], v[5]],
  fov: v[6],
  focus: v[7],
});
const lerpV = (a: Vec, b: Vec, t: number) => a.map((x, i) => x + (b[i] - x) * t);

const hermite = (p0: Vec, m0: Vec, p1: Vec, m1: Vec, t: number) => {
  const t2 = t * t;
  const t3 = t2 * t;
  const h00 = 2 * t3 - 3 * t2 + 1;
  const h10 = t3 - 2 * t2 + t;
  const h01 = -2 * t3 + 3 * t2;
  const h11 = t3 - t2;
  return p0.map((_, i) => h00 * p0[i] + h10 * m0[i] + h01 * p1[i] + h11 * m1[i]);
};

export const poseAt = (beats: Beat[], f: number): Pose => {
  if (f <= beats[0].start) return beats[0].from;
  for (let i = 0; i < beats.length; i++) {
    const b = beats[i];
    if (f >= b.start && f <= b.end) {
      return toPose(lerpV(flat(b.from), flat(b.to), (f - b.start) / Math.max(1, b.end - b.start)));
    }
    const n = beats[i + 1];
    if (n && f > b.end && f < n.start) {
      if (n.cut) return b.to;
      const dur = n.start - b.end;
      const a0 = flat(b.to);
      const a1 = flat(n.from);
      const fromV = flat(b.from);
      const v0 = a0.map((x, k) => (x - fromV[k]) / Math.max(1, b.end - b.start));
      const v1 = flat(n.to).map((x, k) => (x - a1[k]) / Math.max(1, n.end - n.start));
      const m0 = v0.map((x) => x * dur);
      const m1 = v1.map((x) => x * dur);
      const t = (f - b.end) / dur;
      const base = toPose(hermite(a0, m0, a1, m1, t));
      // Through via points: a Catmull-Rom curve, walked with a Hermite parameter
      // whose end speeds match the drifts, so speed stays continuous.
      type V3 = [number, number, number];
      const along = (a: V3, vias: V3[], b: V3, vs: number, ve: number): V3 => {
        const curve = new THREE.CatmullRomCurve3([a, ...vias, b].map((p) => new THREE.Vector3(...p)), false, "centripetal");
        const len = Math.max(1e-3, curve.getLength());
        const u = hermite([0], [(vs * dur) / len], [1], [(ve * dur) / len], t)[0];
        const p = curve.getPointAt(Math.min(1, Math.max(0, u)));
        return [p.x, p.y, p.z];
      };
      let out = base;
      if (n.via && n.via.length) {
        out = { ...out, pos: along(b.to.pos, n.via, n.from.pos, Math.hypot(v0[0], v0[1], v0[2]), Math.hypot(v1[0], v1[1], v1[2])) };
      }
      if (n.viaTarget && n.viaTarget.length) {
        out = { ...out, target: along(b.to.target, n.viaTarget, n.from.target, Math.hypot(v0[3], v0[4], v0[5]), Math.hypot(v1[3], v1[4], v1[5])) };
      }
      return out;
    }
  }
  return beats[beats.length - 1].to;
};

export const applyPose = (cam: THREE.PerspectiveCamera, p: Pose) => {
  cam.position.set(...p.pos);
  cam.fov = p.fov;
  cam.lookAt(new THREE.Vector3(...p.target));
  cam.updateProjectionMatrix();
  cam.updateMatrixWorld(true);
};

// Count hard cuts and moving frames, for the report.
export const pathStats = (beats: Beat[], frames: number) => {
  let moving = 0;
  let prev = flat(poseAt(beats, 0));
  for (let f = 1; f < frames; f++) {
    const cur = flat(poseAt(beats, f));
    const d = Math.hypot(cur[0] - prev[0], cur[1] - prev[1], cur[2] - prev[2], cur[3] - prev[3], cur[4] - prev[4], cur[5] - prev[5]);
    if (d > 0.0015 || Math.abs(cur[6] - prev[6]) > 0.005) moving++;
    prev = cur;
  }
  return { moving, cuts: beats.filter((b) => b.cut).length };
};
