// An original second character: a freckled newsboy with a purple flat cap, an
// oversized orange scarf and a satchel of papers. Standing, ~3.5 heads tall.
// Canvas 512 x 1024; the bottom edge is the ground.
//
// SPIKE 2: the body is now posed from continuous parameters every frame instead
// of flip-booking between a "walkA" and a "walkB" picture every 8 frames. Legs
// are solved with two-bone IK from where the foot needs to be, so the knees bend
// instead of the whole leg swinging rigidly, and the feet stop skating.
//
// PROBE 2 (acting): blendable gestures, a head turn, a talking mouth, and longer
// strides / a run. Every new field is OPTIONAL and, when absent, the drawing is
// pixel-identical to spike 2 (checked against a golden render of the old file).
import type { DrawFn } from "../kit/Cutout";
import { INK, limb, SKIN, SKIN_SHADE, stroke } from "./operator";
import { armFK, type ArmPose, bobAt, clamp01, fitArmX, type Foot, footAt, ik, leanAt, lerp, lerpDeg, lerpP, mixArmPose, smootherstep, type P } from "../kit/rig";

export type BoyExpr = "smile" | "awe";

/** Acting gestures. "none" = arms free (rest / walk swing / `point`). */
export type BoyGesture = "none" | "wave" | "cheer" | "shout" | "holdPaper" | "shrug" | "lookUp" | "think";
export const BOY_GESTURES: readonly BoyGesture[] = ["none", "wave", "cheer", "shout", "holdPaper", "shrug", "lookUp", "think"];

/** The widest stride (canvas units, same units as `stride`) the legs draw
 *  cleanly: at 800 units/m and 3 steps/s that is ~1.24 m/s, a brisk walk. Above
 *  170 the walk gains knee lift, arm swing and lean, and the pelvis drops just
 *  enough that neither leg ever over-reaches its bones. */
export const MAX_STRIDE_NEW = 330;

export type BoyParams = {
  /** walk cycle position, 0..1 — advanced by real elapsed time, never quantised */
  phase: number;
  /** 0 = standing still, 1 = full walk (bob, lean, swinging arms) */
  walk: number;
  /** horizontal foot travel in canvas units; the caller derives it from the
   *  character's world speed so the stance foot keeps pace with the ground.
   *  Clean up to MAX_STRIDE_NEW (330); negative walks toward canvas -x. */
  stride: number;
  expr: BoyExpr;
  /** eyelid, 0 open .. 1 shut */
  lid: number;
  /** 0 = arms at rest, 1 = right arm pointing up at the sky */
  point: number;
  /** head tilt in degrees, for acting beats */
  headTilt: number;

  // ---- PROBE 2 acting (all optional) ----
  /** gesture being moved TO (default "none") */
  gesture?: BoyGesture;
  /** gesture being moved FROM (default "none") */
  gestureFrom?: BoyGesture;
  /** 0 = fully `gestureFrom` .. 1 = fully `gesture` (default 1). Eased with
   *  smootherstep inside, so the caller can ramp it linearly over 7-20 frames. */
  gestureBlend?: number;
  /** free-running time in SECONDS (frame / 30) for the gestures' own motion:
   *  the wave's wag, the cheer's pump, the shout's paper bounce. Default 0. */
  beat?: number;
  /** -1 = face turned to canvas -x .. 1 = turned to canvas +x (default 0) */
  headTurn?: number;
  /** mouth open amount for speech, 0 closed .. 1 wide (default 0) */
  talk?: number;
  /** 0 = walk .. 1 = run: shorter ground contact with a flight phase, bent
   *  pumping arms, more lean. Pair it with a faster cycle (16 frames). Default 0. */
  run?: number;
  /** canvas foot travel per unit of `stride` (default 0.55 = spike 2's
   *  calibration). 1.0 is a truly planted foot when the walk crosses the camera
   *  side-on; scale by the cosine of the walk's angle to the image plane. */
  footScale?: number;
};

const CAP = "#7b3fc4";
const SHIRT = "#ffd84a";
const STRIPE = "#ff6a3d";
const PANTS = "#2f6fd6";
const SCARF = "#ff8a1f";
const BAG = "#c4733a";
const PAPER = "#f4f0e2";

// skeleton constants measured off the original fixed poses
const HIP_L: P = [232, 640];
const HIP_R: P = [280, 640];
const THIGH = 165;
const SHIN = 172;
const GROUND = 975;
const SHO_L: P = [196, 350];
const SHO_R: P = [316, 350];
const UPPER = 104;
const FORE = 99;
/** the head circle, for clipping turned features */
const HEAD_C: P = [256, 170];
const HEAD_R = 138;

type FaceOpts = {
  /** feature offset (turn / look) */
  dx: number;
  dy: number;
  /** extra pupil offset (gaze) */
  gx: number;
  gy: number;
  turn: number;
  talk: number;
};
const NO_FACE: FaceOpts = { dx: 0, dy: 0, gx: 0, gy: 0, turn: 0, talk: 0 };

const face = (ctx: CanvasRenderingContext2D, expr: BoyExpr, lid: number, o: FaceOpts = NO_FACE) => {
  const ey = (expr === "awe" ? 168 : 182) + o.dy;
  for (const [i, x0] of [208, 304].entries()) {
    const x = x0 + o.dx;
    // the eye on the far side of a turn foreshortens
    const far = i === 0 ? Math.max(0, -o.turn) : Math.max(0, o.turn);
    const squash = 1 - 0.28 * far;
    // brows
    ctx.beginPath();
    const up = expr === "awe" ? -22 : 0;
    ctx.moveTo(x - 22 * squash, ey - 40 + up);
    ctx.quadraticCurveTo(x, ey - 52 + up, x + 22 * squash, ey - 40 + up);
    stroke(ctx, 9);
    if (lid >= 1) {
      // fully shut: the closed-eye arc
      ctx.beginPath();
      ctx.moveTo(x - 20 * squash, ey + 2);
      ctx.quadraticCurveTo(x, ey + 14, x + 20 * squash, ey + 2);
      stroke(ctx, 8);
      continue;
    }
    const rx = (expr === "awe" ? 26 : 22) * squash;
    const ry = (expr === "awe" ? 32 : 26) * (1 - 0.72 * lid); // half-lid squashes the eye
    ctx.beginPath();
    ctx.ellipse(x, ey, rx, ry, 0, 0, Math.PI * 2);
    ctx.fillStyle = "#ffffff";
    ctx.fill();
    stroke(ctx, 7);
    ctx.save();
    if (o.gx !== 0 || o.gy !== 0) {
      // a gazing pupil stays inside its eye
      ctx.beginPath();
      ctx.ellipse(x, ey, rx, ry, 0, 0, Math.PI * 2);
      ctx.clip();
    }
    ctx.beginPath();
    ctx.arc(
      x + (expr === "awe" ? 0 : 3) + o.gx,
      ey + (expr === "awe" ? -8 : 2) + o.gy,
      Math.min(expr === "awe" ? 12 : 11, ry),
      0,
      Math.PI * 2,
    );
    ctx.fillStyle = "#2a1650";
    ctx.fill();
    if (lid < 0.4) {
      ctx.beginPath();
      ctx.arc(x + 4 + o.gx, ey - 12 + o.gy, 4, 0, Math.PI * 2);
      ctx.fillStyle = "#ffffff";
      ctx.fill();
    }
    ctx.restore();
    if (lid > 0) {
      // a half-lid is a lid coming down over the top of the eye, not a smaller eye
      ctx.save();
      ctx.beginPath();
      ctx.ellipse(x, ey - ry - 2 + 2 * ry * lid, rx + 3, ry, 0, 0, Math.PI * 2);
      ctx.fillStyle = SKIN;
      ctx.fill();
      ctx.restore();
    }
  }
  // freckles
  ctx.fillStyle = "#c8643a";
  for (const [fx, fy] of [[176, 228], [190, 238], [168, 242], [336, 228], [322, 238], [344, 242]] as P[]) {
    ctx.beginPath();
    ctx.arc(fx + o.dx, fy + o.dy, 3.5, 0, Math.PI * 2);
    ctx.fill();
  }
  // button nose: sits proud of the face, so it slides further on a turn
  const nx = 256 + o.dx * 1.3;
  ctx.beginPath();
  ctx.arc(nx, 226 + o.dy, 11, 0, Math.PI * 2);
  ctx.fillStyle = "#f08a78";
  ctx.fill();
  stroke(ctx, 6);
  const mx = 256 + o.dx * 1.05;
  const my = o.dy;
  ctx.beginPath();
  if (expr === "smile" && o.talk > 0) {
    // the smile's D-shape opens downward; at talk 0 it is exactly the smile
    const t = o.talk;
    const w = 36 - 8 * t;
    const bot = 292 + 44 * t + my;
    const mouth = () => {
      ctx.beginPath();
      ctx.moveTo(mx - w, 256 + my);
      ctx.quadraticCurveTo(mx, bot, mx + w, 256 + my);
      ctx.quadraticCurveTo(mx, 256 - 6 * t + my, mx - w, 256 + my);
      ctx.closePath();
    };
    mouth();
    ctx.fillStyle = "#7a1d3a";
    ctx.fill();
    if (t > 0.25) {
      ctx.save();
      mouth();
      ctx.clip();
      ctx.beginPath();
      ctx.ellipse(mx, 256 + my + (bot - 256 - my) * 0.5, w * 0.6, 8 + 10 * t, 0, 0, Math.PI * 2);
      ctx.fillStyle = "#e0566e";
      ctx.fill();
      ctx.restore();
    }
    mouth();
    stroke(ctx, 7);
  } else if (expr === "smile") {
    ctx.moveTo(220 + o.dx * 1.05, 256 + my);
    ctx.quadraticCurveTo(mx, 292 + my, 292 + o.dx * 1.05, 256 + my);
    ctx.closePath();
    ctx.fillStyle = "#7a1d3a";
    ctx.fill();
    stroke(ctx, 7);
  } else {
    ctx.ellipse(mx, 270 + my + 4 * o.talk, 14 + 2 * o.talk, 20 + 12 * o.talk, 0, 0, Math.PI * 2);
    ctx.fillStyle = "#7a1d3a";
    ctx.fill();
    stroke(ctx, 7);
  }
};

// ------------------------------------------------------------------ gestures
//
// Arms are authored as ANGLES (rig.ArmPose: upper-arm direction + elbow bend,
// degrees, 0 = viewer's right, 90 = up) and blended on arcs. The previous
// scheme blended hand positions in canvas space and re-solved the elbow with
// an IK hint each frame: the elbow flipped sides whenever the blended hint
// crossed the shoulder-hand line (the shrug's hands collapsed into the torso
// and its forearms folded back across the body; the wave chicken-winged).
type BoyArm = ArmPose & {
  /** 0..1 open palm (fingers spread) */
  open?: number;
  /** 0..1 cupped hand (shouting) */
  cup?: number;
  /** 0..1 raised index finger (thinking) */
  finger?: number;
  /** finger-fan direction, deg; default = along the forearm */
  dir?: number;
  /** drawn after the head / props (crosses in front of the face or paper) */
  front?: boolean;
};
type GSpec = {
  l: BoyArm | null;
  r: BoyArm | null;
  /** shoulder raise, canvas units */
  up: number;
  /** extra head tilt, degrees */
  tilt: number;
  /** -1 look up .. 1 look down: features slide on the face, pupils follow */
  look: number;
  gaze: P;
  /** extra body lean, degrees (negative leans back) */
  lean: number;
  prop?: "high" | "read";
};

const TAU = Math.PI * 2;
const NONE: GSpec = { l: null, r: null, up: 0, tilt: 0, look: 0, gaze: [0, 0], lean: 0 };

/** Each gesture's pose; `b` (seconds) drives the gesture's own cycle. */
const gspec = (g: BoyGesture, b: number): GSpec => {
  switch (g) {
    case "wave":
      // upper arm out to the side, forearm wagging at ~2.2 Hz beside the head
      return { ...NONE, r: { ua: 15, bend: 70 + 15 * Math.sin(TAU * 2.2 * b), open: 1, dir: 90 }, tilt: 4, lean: -1 };
    case "cheer": {
      // both arms straight up and out, open hands pumping at 2 Hz. Feet planted
      // and body leaning BACK so a two-arms-up pose reads as joy, never hanging.
      const pump = 7 * (0.5 - 0.5 * Math.cos(TAU * 2 * b));
      return {
        ...NONE,
        l: { ua: 160 - pump, bend: -62 + pump, open: 1, dir: 95 },
        r: { ua: 20 + pump, bend: 62 - pump, open: 1, dir: 85 },
        up: 16,
        look: -0.4,
        lean: -2,
      };
    }
    case "shout": {
      // "EXTRA!": paper thrust up high, other hand cupped at the mouth
      const bounce = 8 * Math.abs(Math.sin(TAU * 1.6 * b));
      return {
        ...NONE,
        r: { ua: 25 + bounce * 0.5, bend: 52 + bounce * 0.5 },
        l: { ua: 153, bend: -134, cup: 1, front: true },
        tilt: -5,
        look: -0.3,
        lean: -2,
        prop: "high",
      };
    }
    case "holdPaper":
      return {
        ...NONE,
        l: { ua: -141, bend: 109, front: true },
        r: { ua: -39, bend: -109, front: true },
        look: 0.85,
        tilt: 3,
        lean: 2,
        prop: "read",
      };
    case "shrug":
      // elbows in at the sides, forearms out and up, palms up, shoulders high
      return {
        ...NONE,
        l: { ua: -115, bend: -95, open: 1, dir: 125 },
        r: { ua: -65, bend: 95, open: 1, dir: 55 },
        up: 22,
        tilt: 8,
        lean: -1,
      };
    case "lookUp":
      return { ...NONE, look: -1, tilt: -4, lean: -3 };
    case "think":
      return {
        ...NONE,
        // the other arm stays free: a supporting arm across the belly made a
        // tangle of yellow that read as nothing at Shorts size
        r: { ua: -140 + 2 * Math.sin(TAU * 1.1 * b), bend: -154, finger: 1, dir: 100, front: true },
        tilt: -6,
        gaze: [-7, -8],
      };
    default:
      return NONE;
  }
};

/** the right arm pointing at the sky (the old `point` param), straight up-right */
const POINT_ARM: BoyArm = { ua: 60, bend: -4, finger: 1, dir: 62 };

type HandW = { open: number; cup: number; finger: number; dir: number };

/** The newsboy's hand: a fist that can be opened (fingers spread), cupped to
 *  the mouth, or raise an index finger, each CONTINUOUSLY so a gesture blend
 *  morphs the hand instead of popping its shape at the halfway point. */
const boyHand = (ctx: CanvasRenderingContext2D, p: P, w: HandW) => {
  ctx.save();
  ctx.translate(p[0], p[1]);
  ctx.rotate(-0.35 * w.cup);
  ctx.beginPath();
  ctx.ellipse(0, 0, 22 - 3 * w.cup, 22 + 6 * w.cup, 0, 0, TAU);
  ctx.fillStyle = SKIN;
  ctx.fill();
  stroke(ctx, 8);
  if (w.cup > 0.3) {
    // the curl of the fingers, open toward the mouth
    ctx.beginPath();
    ctx.arc(6, 0, 14, -1.5, 1.5);
    stroke(ctx, 6 * clamp01((w.cup - 0.3) / 0.5));
  }
  ctx.restore();
  if (w.open > 0.03) {
    const a0 = (-w.dir * Math.PI) / 180;
    for (let i = -1; i <= 1; i++) {
      const a = a0 + i * 0.5;
      ctx.beginPath();
      ctx.moveTo(p[0] + Math.cos(a) * 16, p[1] + Math.sin(a) * 16);
      ctx.lineTo(p[0] + Math.cos(a) * (16 + 20 * w.open), p[1] + Math.sin(a) * (16 + 20 * w.open));
      ctx.strokeStyle = INK;
      ctx.lineWidth = 22;
      ctx.lineCap = "round";
      ctx.stroke();
      ctx.strokeStyle = SKIN;
      ctx.lineWidth = 10;
      ctx.stroke();
    }
  }
  if (w.finger > 0.03) {
    const a = (w.dir * Math.PI) / 180;
    const len = 14 + 32 * w.finger;
    ctx.beginPath();
    ctx.moveTo(p[0], p[1]);
    ctx.lineTo(p[0] + Math.cos(a) * len, p[1] - Math.sin(a) * len);
    ctx.strokeStyle = INK;
    ctx.lineWidth = 22;
    ctx.lineCap = "round";
    ctx.stroke();
    ctx.strokeStyle = SKIN;
    ctx.lineWidth = 10;
    ctx.stroke();
  }
};

const paperHigh = (ctx: CanvasRenderingContext2D, h: P, k: number) => {
  ctx.save();
  ctx.translate(h[0], h[1]);
  ctx.scale(k, k);
  ctx.translate(-10, -70);
  ctx.rotate(-0.14);
  ctx.beginPath();
  ctx.rect(-68, -50, 136, 100);
  ctx.fillStyle = PAPER;
  ctx.fill();
  stroke(ctx, 7);
  ctx.fillStyle = "#c0262d";
  ctx.font = "900 38px sans-serif";
  ctx.textAlign = "center";
  ctx.textBaseline = "middle";
  ctx.fillText("EXTRA!", 0, -20, 124);
  for (let i = 0; i < 3; i++) {
    ctx.beginPath();
    ctx.moveTo(-54, 10 + i * 13);
    ctx.lineTo(54, 10 + i * 13);
    ctx.strokeStyle = "#8a8aa8";
    ctx.lineWidth = 4;
    ctx.stroke();
  }
  ctx.restore();
};

const paperRead = (ctx: CanvasRenderingContext2D, hl: P, hr: P, k: number) => {
  const w = Math.hypot(hr[0] - hl[0], hr[1] - hl[1]) + 40;
  ctx.save();
  ctx.translate((hl[0] + hr[0]) / 2, (hl[1] + hr[1]) / 2);
  ctx.rotate(Math.atan2(hr[1] - hl[1], hr[0] - hl[0]));
  ctx.scale(k, k);
  ctx.beginPath();
  ctx.rect(-w / 2, -78, w, 140);
  ctx.fillStyle = PAPER;
  ctx.fill();
  stroke(ctx, 7);
  // centre fold, a headline bar, columns of text
  ctx.beginPath();
  ctx.moveTo(0, -78);
  ctx.lineTo(0, 62);
  ctx.strokeStyle = "#b8b4a6";
  ctx.lineWidth = 3;
  ctx.stroke();
  ctx.fillStyle = "#3a3450";
  ctx.fillRect(-w / 2 + 14, -66, w / 2 - 26, 14);
  ctx.fillRect(12, -66, w / 2 - 26, 14);
  for (let i = 0; i < 6; i++) {
    for (const x0 of [-w / 2 + 14, 12]) {
      ctx.beginPath();
      ctx.moveTo(x0, -38 + i * 15);
      ctx.lineTo(x0 + w / 2 - 26, -38 + i * 15);
      ctx.strokeStyle = "#8a8aa8";
      ctx.lineWidth = 4;
      ctx.stroke();
    }
  }
  ctx.restore();
};

/** one leg of a walk/run with a planted stance foot and a duty factor. At
 *  duty 0.5 this is exactly rig.footAt; below it, the stance shortens and the
 *  swing covers the difference, which leaves a flight phase between steps. */
const footDuty = (phase: number, stride: number, lift: number, groundY: number, duty: number): Foot => {
  const p = ((phase % 1) + 1) % 1;
  const travel = stride * 2 * duty;
  if (p < duty) {
    const s = p / duty;
    return { pos: [travel / 2 - travel * s, groundY], planted: true };
  }
  const s = (p - duty) / (1 - duty);
  return { pos: [-travel / 2 + travel * smootherstep(s), groundY - lift * Math.sin(Math.PI * s)], planted: false };
};

export const drawNewsboy =
  (q: BoyParams): DrawFn =>
  (ctx) => {
    const walk = Math.max(0, Math.min(1, q.walk));
    const fs = q.footScale ?? 0.55;
    const absStride = Math.abs(q.stride);
    const run = clamp01(q.run ?? 0);
    // ext: how far past spike 2's cap the stride is; 0 for every old caller
    const ext = clamp01((absStride - 170) / 170);
    const fast = absStride > 170 || run > 0;
    // --- body mechanics -------------------------------------------------
    let bob: number;
    let lean: number;
    let fL: Foot;
    let fR: Foot;
    let footL: P;
    let footR: P;
    // swing-leg foreshortening (fast path only): 1 = full bone lengths
    let sL = 1;
    let sR = 1;
    // when standing, the feet sit flat and splayed as before
    const restL: P = [176, GROUND];
    const restR: P = [340, GROUND];
    if (!fast) {
      // bob: 5 % of a ~830 unit figure = ~42 units peak to peak, lowest at contact
      bob = bobAt(q.phase, 42) * walk;
      lean = leanAt(q.phase, 4, 3) * walk;
      // feet: left leg leads, right leg is half a cycle behind
      fL = footAt(q.phase, q.stride, 62, GROUND);
      fR = footAt(q.phase + 0.5, q.stride, 62, GROUND);
      footL = lerpP(restL, [232 + fL.pos[0] * fs - 44, fL.pos[1]], walk);
      footR = lerpP(restR, [280 + fR.pos[0] * fs + 44, fR.pos[1]], walk);
    } else {
      // Longer strides and the run. More knee lift, a narrower track, more lean.
      // A run shortens ground contact (duty 0.5 -> 0.36), which opens a flight
      // phase, and moves the bob's low point from contact to mid-stance.
      const duty = 0.5 - 0.14 * run;
      const lift = 62 + 30 * ext + 30 * run;
      const splay = 44 - 22 * ext - 10 * run;
      const walkBob = bobAt(q.phase, 42 + 6 * ext);
      const runBob = 26 * Math.cos(4 * Math.PI * (q.phase - duty / 2));
      bob = lerp(walkBob, runBob, run) * walk;
      lean = lerp(leanAt(q.phase, 4 + 3 * ext, 3), 12 + 3 * Math.cos(4 * Math.PI * (q.phase - duty / 2)), run) * walk;
      fL = footDuty(q.phase, q.stride, lift, GROUND, duty);
      fR = footDuty(q.phase + 0.5, q.stride, lift, GROUND, duty);
      footL = lerpP(restL, [232 + fL.pos[0] * fs - splay, fL.pos[1]], walk);
      footR = lerpP(restR, [280 + fR.pos[0] * fs + splay, fR.pos[1]], walk);
      // The pelvis drops exactly as far as the longer of the two legs needs, so
      // no leg is ever asked to reach past its bones (which is what broke the
      // figure past 170: the IK clamps, and the shin is drawn stretched). Faded
      // in over 170..200 so a character speeding up does not hop.
      const reach = 0.975 * (THIGH + SHIN);
      const need = (hx: number, f: P) => {
        const dx = f[0] - hx;
        return f[1] - Math.sqrt(Math.max(0, reach * reach - dx * dx)) - (HIP_L[1] + bob);
      };
      const k = clamp01(Math.max((absStride - 170) / 30, run * 3));
      bob += Math.max(0, need(HIP_L[0], footL), need(HIP_R[0], footR)) * k;
      // A lifted knee on a front-facing figure comes TOWARD the camera, so in
      // the picture the thigh and shin shorten instead of the knee kicking out
      // sideways (which, at this lift, read as a figure-4 / donkey kick). The
      // bones shrink to just over the hip-foot distance during swing only.
      const fore = (hx: number, f: P) => {
        const up = clamp01((GROUND - f[1]) / lift);
        if (up <= 0) return 1;
        const d = Math.hypot(f[0] - hx, f[1] - (HIP_L[1] + bob));
        const tight = Math.min(1, d / ((THIGH + SHIN) * 0.94));
        return lerp(1, tight, up * clamp01(ext * 2 + run * 2));
      };
      sL = fore(HIP_L[0], footL);
      sR = fore(HIP_R[0], footR);
    }
    // hips ride the bob
    const hipL: P = [HIP_L[0], HIP_L[1] + bob];
    const hipR: P = [HIP_R[0], HIP_R[1] + bob];
    // knees: IK, splayed outward so a front-on walk reads correctly
    const kneeL = ik(hipL, footL, THIGH * sL, SHIN * sL, -1);
    const kneeR = ik(hipR, footR, THIGH * sR, SHIN * sR, 1);
    const legL: [P, P, P] = [hipL, kneeL, footL];
    const legR: [P, P, P] = [hipR, kneeR, footR];

    // --- gestures ---------------------------------------------------------
    const gTo = q.gesture ?? "none";
    const gFrom = q.gestureFrom ?? "none";
    const gestured = gTo !== "none" || gFrom !== "none";
    const gt = smootherstep(q.gestureBlend ?? 1);
    const b = q.beat ?? 0;
    const A = gspec(gFrom, b);
    const B = gspec(gTo, b);
    const up = lerp(A.up, B.up, gt);
    const gTilt = lerp(A.tilt, B.tilt, gt);
    const look = lerp(A.look, B.look, gt);
    const gLean = lerp(A.lean, B.lean, gt);
    const turn = Math.max(-1, Math.min(1, q.headTurn ?? 0));
    const talk = clamp01(q.talk ?? 0);

    // Arms swing opposite the legs. These are LOCAL coordinates: the whole upper
    // body is drawn inside one transform that carries the bob and the lean, so
    // adding bob here too would apply it twice (and detach the head from the
    // torso, which it did).
    const shoL: P = gestured ? [SHO_L[0], SHO_L[1] - up] : SHO_L;
    const shoR: P = gestured ? [SHO_R[0], SHO_R[1] - up] : SHO_R;
    // Walk swing. The old swing rotated each whole arm +-17 deg about the
    // shoulder in opposite senses, which brought BOTH hands together in front of
    // the belly every half cycle (a clasped-hands walk). Now: a small sideways
    // swing (the hand ahead in the walk direction), and the forward arm BENDS,
    // its forearm lifting and foreshortening toward the camera, while the back
    // arm straightens. A run keeps both elbows bent and the hands high.
    const sgn = q.stride < 0 ? -1 : 1;
    const c = Math.cos(TAU * q.phase);
    const fwdL = 0.5 - 0.5 * c;
    const fwdR = 1 - fwdL;
    const sway = (8 + 2 * ext + 4 * run) * walk;
    const bendOf = (fwd: number) =>
      lerp(16 + (36 * fwd * fwd - 14 * (1 - fwd) + 22 * ext) * walk, 78 + 18 * fwd, run * walk);
    const freeL: BoyArm = { ua: -100 - sway * c * sgn, bend: bendOf(fwdL), sf: 1 - 0.3 * fwdL * walk };
    const freeR: BoyArm = { ua: -80 - sway * c * sgn, bend: -bendOf(fwdR), sf: 1 - 0.3 * fwdR * walk };
    type ArmMix = { pose: ArmPose; w: HandW; front: boolean };
    const mix = (x: BoyArm | null, y: BoyArm | null, free: BoyArm, t: number): ArmMix => {
      const X = x ?? free;
      const Y = y ?? free;
      const pose = mixArmPose(X, Y, t);
      const dX = X.dir ?? X.ua + X.bend;
      const dY = Y.dir ?? Y.ua + Y.bend;
      return {
        pose,
        w: {
          open: lerp(X.open ?? 0, Y.open ?? 0, t),
          cup: lerp(X.cup ?? 0, Y.cup ?? 0, t),
          finger: lerp(X.finger ?? 0, Y.finger ?? 0, t),
          dir: lerpDeg(dX, dY, t),
        },
        // an arm that crosses the face/paper at either end of the blend is drawn
        // in front throughout: at the rest end it overlaps nothing but the
        // torso, so there is no draw-order pop at any blend value
        front: !!(X.front || Y.front),
      };
    };
    const ml = mix(A.l, B.l, freeL, gt);
    // `point` (the right arm at the sky) still overrides the right arm on top of
    // any gesture, blending on arcs like everything else
    const mrG = mix(A.r, B.r, freeR, gt);
    const pt = smootherstep(q.point);
    const mrP: ArmMix = {
      pose: mixArmPose(mrG.pose, POINT_ARM, pt),
      w: {
        open: mrG.w.open * (1 - pt),
        cup: mrG.w.cup * (1 - pt),
        finger: lerp(mrG.w.finger, 1, pt),
        dir: lerpDeg(mrG.w.dir, POINT_ARM.dir!, pt),
      },
      front: mrG.front && q.point < 0.5,
    };
    // a hand swinging past the canvas edge mid-blend comes toward the camera
    const armL = armFK(shoL, fitArmX(shoL, ml.pose, UPPER, FORE, 46, 466), UPPER, FORE);
    const armR = armFK(shoR, fitArmX(shoR, mrP.pose, UPPER, FORE, 46, 466), UPPER, FORE);
    const wL = ml.w;
    const wR = mrP.w;
    const frontL = gestured && ml.front;
    const frontR = gestured && mrP.front;
    const propW = (p: GSpec["prop"]) => lerp(A.prop === p ? 1 : 0, B.prop === p ? 1 : 0, gt);
    const highW = propW("high");
    const readW = propW("read");

    const drawArm = (arm: [P, P, P], w: HandW) => {
      limb(ctx, arm, 20, SHIRT);
      boyHand(ctx, arm[2], w);
    };

    // --- draw ------------------------------------------------------------
    // legs + shoes (drawn in world space: they are NOT affected by the lean)
    limb(ctx, legL, 30, PANTS);
    limb(ctx, legR, 30, PANTS);
    for (const [f, lifted] of [
      [footL, walk > 0.5 && !fL.planted],
      [footR, walk > 0.5 && !fR.planted],
    ] as [P, boolean][]) {
      ctx.beginPath();
      // a lifted foot tips forward instead of staying a flat oval
      ctx.ellipse(f[0], f[1] + 14, 32, 15, lifted ? -0.3 : 0, 0, Math.PI * 2);
      ctx.fillStyle = "#8a3a2a";
      ctx.fill();
      stroke(ctx, 8);
    }

    // ONE transform for everything above the hips: ride the bob, then lean about
    // the hip joint. Torso, arms, scarf and head all sit inside it, so they move
    // as one body.
    ctx.save();
    ctx.translate(0, bob);
    ctx.translate(256, 640);
    ctx.rotate((lean * Math.PI) / 180 / 3 + (gLean * Math.PI) / 180);
    ctx.translate(-256, -640);

    // satchel strap + bag behind the arm
    ctx.beginPath();
    ctx.moveTo(206, 340);
    ctx.lineTo(330, 560);
    ctx.strokeStyle = INK;
    ctx.lineWidth = 24;
    ctx.stroke();
    ctx.strokeStyle = BAG;
    ctx.lineWidth = 10;
    ctx.stroke();
    // body: striped shirt
    ctx.save();
    ctx.beginPath();
    ctx.moveTo(190, 340);
    ctx.quadraticCurveTo(256, 318, 322, 340);
    ctx.lineTo(312, 650);
    ctx.quadraticCurveTo(256, 664, 200, 650);
    ctx.closePath();
    ctx.fillStyle = SHIRT;
    ctx.fill();
    ctx.clip();
    ctx.fillStyle = STRIPE;
    for (let y = 360; y < 660; y += 44) ctx.fillRect(150, y, 220, 16);
    ctx.restore();
    ctx.beginPath();
    ctx.moveTo(190, 340);
    ctx.quadraticCurveTo(256, 318, 322, 340);
    ctx.lineTo(312, 650);
    ctx.quadraticCurveTo(256, 664, 200, 650);
    ctx.closePath();
    stroke(ctx, 10);
    // bag with newspapers
    ctx.beginPath();
    ctx.roundRect(296, 520, 92, 86, 12);
    ctx.fillStyle = BAG;
    ctx.fill();
    stroke(ctx, 8);
    ctx.beginPath();
    ctx.rect(306, 498, 70, 30);
    ctx.fillStyle = PAPER;
    ctx.fill();
    stroke(ctx, 6);
    for (let i = 0; i < 3; i++) {
      ctx.beginPath();
      ctx.moveTo(312, 506 + i * 8);
      ctx.lineTo(368, 506 + i * 8);
      ctx.strokeStyle = "#8a8aa8";
      ctx.lineWidth = 2;
      ctx.stroke();
    }

    if (!frontL) drawArm(armL, wL);
    if (!frontR) drawArm(armR, wR);

    // neck + scarf
    ctx.beginPath();
    ctx.rect(240, 290, 32, 40);
    ctx.fillStyle = SKIN_SHADE;
    ctx.fill();
    stroke(ctx, 8);
    ctx.beginPath();
    ctx.ellipse(256, 334, 80, 30, 0, 0, Math.PI * 2);
    ctx.fillStyle = SCARF;
    ctx.fill();
    stroke(ctx, 8);
    // the loose scarf tail trails behind the walk (and streams back on a run)
    const tail = (14 + 16 * ext + 16 * run) * walk * Math.sin(2 * Math.PI * q.phase + 1.0) + 14 * run * walk;
    ctx.beginPath();
    ctx.moveTo(218, 344);
    ctx.lineTo(198 - tail, 450);
    ctx.lineTo(232 - tail, 446);
    ctx.lineTo(244, 350);
    ctx.closePath();
    ctx.fillStyle = SCARF;
    ctx.fill();
    stroke(ctx, 8);

    // head (tilts on acting beats), ears
    // A turn slides the features across the face and the ears the other way
    // (we see more of the back of the head on the side turned away).
    const fdx = turn * 34;
    const fdy = look * 16;
    ctx.save();
    ctx.translate(256, 300);
    ctx.rotate(((q.headTilt + gTilt) * Math.PI) / 180);
    ctx.translate(-256, -300 + look * 4);
    for (const x of [120, 392]) {
      ctx.beginPath();
      ctx.arc(x - turn * 16, 196, 26, 0, Math.PI * 2);
      ctx.fillStyle = SKIN_SHADE;
      ctx.fill();
      stroke(ctx, 8);
    }
    ctx.beginPath();
    ctx.arc(HEAD_C[0], HEAD_C[1], HEAD_R, 0, Math.PI * 2);
    ctx.fillStyle = SKIN;
    ctx.fill();
    stroke(ctx, 11);
    const moved = fdx !== 0 || fdy !== 0;
    if (moved) {
      // turned features never spill past the head's outline
      ctx.save();
      ctx.beginPath();
      ctx.arc(HEAD_C[0], HEAD_C[1], HEAD_R - 3, 0, Math.PI * 2);
      ctx.clip();
    }
    ctx.fillStyle = "rgba(240, 110, 120, 0.35)";
    for (const x of [172, 340]) {
      ctx.beginPath();
      ctx.ellipse(x + fdx, 236 + fdy, 20, 12, 0, 0, Math.PI * 2);
      ctx.fill();
    }
    const gaze: P = lerpP(A.gaze, B.gaze, gt);
    face(
      ctx,
      q.expr,
      q.lid,
      moved || talk > 0 || gaze[0] !== 0 || gaze[1] !== 0 || look !== 0
        ? { dx: fdx, dy: fdy, gx: gaze[0] + turn * 7, gy: gaze[1] + look * 9, turn, talk }
        : NO_FACE,
    );
    if (moved) ctx.restore();
    // flat cap with a stubby peak (the peak swings with the turn)
    const cx = turn * 10;
    ctx.beginPath();
    ctx.moveTo(112 + cx, 128);
    ctx.quadraticCurveTo(140 + cx, 28, 262 + cx, 26);
    ctx.quadraticCurveTo(392 + cx, 30, 404 + cx, 118);
    ctx.quadraticCurveTo(256 + cx, 92, 112 + cx, 128);
    ctx.closePath();
    ctx.fillStyle = CAP;
    ctx.fill();
    stroke(ctx, 10);
    const px = turn * 28;
    ctx.beginPath();
    ctx.moveTo(150 + px, 118);
    ctx.quadraticCurveTo(250 + px, 82, 350 + px, 112);
    ctx.quadraticCurveTo(370 + px, 140, 330 + px, 138);
    ctx.quadraticCurveTo(250 + px, 116, 168 + px, 142);
    ctx.quadraticCurveTo(130 + px, 138, 150 + px, 118);
    ctx.closePath();
    ctx.fillStyle = "#5a2a9a";
    ctx.fill();
    stroke(ctx, 8);
    ctx.beginPath();
    ctx.arc(262 + turn * 14, 34, 10, 0, Math.PI * 2);
    ctx.fillStyle = "#ffd84a";
    ctx.fill();
    stroke(ctx, 6);
    ctx.restore();

    // props and the arms that cross IN FRONT of the face / paper. The papers
    // grow out of the hands with the blend instead of popping in halfway.
    if (readW > 0.02) paperRead(ctx, armL[2], armR[2], readW);
    if (frontL) drawArm(armL, wL);
    if (frontR) drawArm(armR, wR);
    if (highW > 0.02) {
      paperHigh(ctx, armR[2], highW);
      boyHand(ctx, armR[2], wR); // the fist gripping the paper's edge
    }

    ctx.restore();
  };

export const boyRest = (): BoyParams => ({
  phase: 0,
  walk: 0,
  stride: 0,
  expr: "smile",
  lid: 0,
  point: 0,
  headTilt: 0,
});
