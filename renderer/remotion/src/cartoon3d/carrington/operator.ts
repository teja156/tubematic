// An original character: a young night-shift telegraph operator. Round head,
// green eyeshade, curly moustache, teal waistcoat, red sleeve garters. Drawn
// seated (the desk hides the stool), about 3.5 heads tall standing.
// Canvas space is 512 x 1024; the plane's bottom edge is the porch floor.
import type { DrawFn } from "../kit/Cutout";
import { armFK, type ArmPose, clamp01, fitArmX, ik, lerp, lerpDeg, lerpP, mixArmPose, smootherstep, wrapDeg, type P as RigP } from "../kit/rig";

export type Pose = "tap" | "recoil" | "reach" | "hold";
/** "grin" = delighted (wide open smile, teeth); "surprised" = brows up, round
 *  eyes, small "o" mouth: a quieter take than "amazed"'s saucer eyes. */
export type Expr = "focus" | "smile" | "shock" | "amazed" | "grin" | "surprised";

// INK: the reference cartoons carry a thick, clean, near-black outline on
// every character. All outline widths here are ~1.6x spike 2's (the face a
// little less, so it stays readable), and the ink is a touch darker.
export const INK = "#14102a";
export const SKIN = "#f6b98a";
export const SKIN_SHADE = "#e0906a";
const VEST = "#13a39b";
const SHIRT = "#fff3dc";
const GARTER = "#e8344a";
const TROUSER = "#5a3a8c";
const VISOR = "rgba(40, 210, 120, 0.82)";

type P = [number, number];

export const stroke = (ctx: CanvasRenderingContext2D, w = 10) => {
  ctx.lineWidth = w;
  ctx.strokeStyle = INK;
  ctx.lineJoin = "round";
  ctx.lineCap = "round";
  ctx.stroke();
};

export const limb = (ctx: CanvasRenderingContext2D, pts: P[], width: number, color: string) => {
  ctx.beginPath();
  ctx.moveTo(...pts[0]);
  for (const p of pts.slice(1)) ctx.lineTo(...p);
  ctx.lineCap = "round";
  ctx.lineJoin = "round";
  ctx.strokeStyle = INK;
  ctx.lineWidth = width + 18;
  ctx.stroke();
  ctx.strokeStyle = color;
  ctx.lineWidth = width;
  ctx.stroke();
};

/** A hand. `open` 0..1 = how far the fingers have spread out of the fist (so a
 *  gesture blend grows them instead of popping them on); `dir` = the degrees
 *  (canvas, 90 = up) the fingers fan around, default straight up; `r` = radius
 *  (a hand nearer the camera draws bigger). */
export const hand = (ctx: CanvasRenderingContext2D, p: P, open: number | boolean = 0, dir = 90, r = 22) => {
  const o = typeof open === "boolean" ? (open ? 1 : 0) : open;
  ctx.beginPath();
  ctx.arc(p[0], p[1], r, 0, Math.PI * 2);
  ctx.fillStyle = SKIN;
  ctx.fill();
  stroke(ctx, 8);
  if (o > 0.03) {
    const k = r / 22;
    const a0 = (-dir * Math.PI) / 180;
    for (let i = -1; i <= 1; i++) {
      ctx.beginPath();
      const a = a0 + i * 0.5;
      ctx.moveTo(p[0] + Math.cos(a) * 16 * k, p[1] + Math.sin(a) * 16 * k);
      ctx.lineTo(p[0] + Math.cos(a) * (16 + 20 * o) * k, p[1] + Math.sin(a) * (16 + 20 * o) * k);
      ctx.strokeStyle = INK;
      ctx.lineWidth = 22 * k;
      ctx.lineCap = "round";
      ctx.stroke();
      ctx.strokeStyle = SKIN;
      ctx.lineWidth = 10 * k;
      ctx.stroke();
    }
  }
};

/** Two-bone arm/leg solve for a GESTURE target. The hand is pulled back inside
 *  98.5 % of full reach (a straight limb never stretches past its bones), and of
 *  the two IK elbows the one nearest `hint` wins. Blending the hint between two
 *  poses (rather than switching a +-1 bend flag) is what keeps an elbow from
 *  flipping sides mid-gesture. */
export const solveArm = (s: P, h: P, hint: P, upper: number, fore: number): [P, P, P] => {
  const max = (upper + fore) * 0.985;
  const d = Math.hypot(h[0] - s[0], h[1] - s[1]);
  const hh: P = d > max ? [s[0] + ((h[0] - s[0]) * max) / d, s[1] + ((h[1] - s[1]) * max) / d] : h;
  const e1 = ik(s, hh, upper, fore, 1);
  const e2 = ik(s, hh, upper, fore, -1);
  const d1 = (e1[0] - hint[0]) ** 2 + (e1[1] - hint[1]) ** 2;
  const d2 = (e2[0] - hint[0]) ** 2 + (e2[1] - hint[1]) ** 2;
  return [s, d1 <= d2 ? e1 : e2, hh];
};

// arm: shoulder -> elbow -> hand, with a red garter on the upper arm
const arm = (ctx: CanvasRenderingContext2D, s: P, e: P, h: P, open: number | boolean = 0, dir = 90, r = 22, drawHand = true) => {
  limb(ctx, [s, e, h], 20, SHIRT);
  const g: P = [s[0] + (e[0] - s[0]) * 0.55, s[1] + (e[1] - s[1]) * 0.55];
  ctx.beginPath();
  ctx.arc(g[0], g[1], 12, 0, Math.PI * 2);
  ctx.fillStyle = GARTER;
  ctx.fill();
  stroke(ctx, 6);
  if (drawHand) hand(ctx, h, open, dir, r);
};

const ARMS: Record<Pose, { l: [P, P, P]; r: [P, P, P]; lean: number; lOpen?: boolean; rOpen?: boolean }> = {
  // viewer's left = his right hand on the key
  tap: { l: [[192, 362], [138, 446], [184, 508]], r: [[320, 362], [372, 470], [318, 548]], lean: 0 },
  recoil: { l: [[192, 362], [112, 330], [98, 236]], r: [[320, 362], [400, 330], [414, 236]], lean: -18, lOpen: true, rOpen: true },
  reach: { l: [[192, 362], [138, 446], [184, 508]], r: [[320, 362], [404, 414], [472, 392]], lean: 6 },
  hold: { l: [[192, 362], [140, 440], [176, 512]], r: [[320, 362], [418, 380], [448, 300]], lean: -6, lOpen: true },
};

type FaceOpts = { dx: number; turn: number; talk: number };
const NO_FACE: FaceOpts = { dx: 0, turn: 0, talk: 0 };

const face = (ctx: CanvasRenderingContext2D, expr: Expr, lid: number, o: FaceOpts = NO_FACE) => {
  const blink = lid >= 1;
  const ey = 212;
  const ex = [204 + o.dx, 308 + o.dx];
  // the eye on the far side of a turn foreshortens
  const sq = (i: number) => 1 - 0.28 * (i === 0 ? Math.max(0, -o.turn) : Math.max(0, o.turn));
  const big = expr === "shock" || expr === "amazed";
  // brows
  for (const [i, x] of ex.entries()) {
    ctx.beginPath();
    const up = big ? -26 : expr === "surprised" ? -20 : expr === "grin" ? -12 : expr === "focus" ? 2 : -8;
    const tilt = expr === "focus" ? (i === 0 ? 6 : -6) : 0;
    ctx.moveTo(x - 26 * sq(i), ey - 46 + up + tilt);
    ctx.quadraticCurveTo(x, ey - 60 + up, x + 26 * sq(i), ey - 46 + up - tilt);
    stroke(ctx, 10);
  }
  for (const [i, x] of ex.entries()) {
    if (blink) {
      ctx.beginPath();
      ctx.moveTo(x - 24 * sq(i), ey + 4);
      ctx.quadraticCurveTo(x, ey + 18, x + 24 * sq(i), ey + 4);
      stroke(ctx, 8);
      continue;
    }
    const ry = big ? 40 : expr === "focus" ? 22 : expr === "surprised" ? 33 : 30;
    const rx = (big ? 31 : expr === "surprised" ? 28 : 26) * sq(i);
    ctx.beginPath();
    ctx.ellipse(x, ey, rx, ry, 0, 0, Math.PI * 2);
    ctx.fillStyle = "#ffffff";
    ctx.fill();
    stroke(ctx, 7);
    const pr = expr === "shock" ? 8 : expr === "amazed" ? 15 : expr === "surprised" ? 11 : 12;
    const py = expr === "focus" ? ey + 8 : expr === "amazed" ? ey - 6 : expr === "grin" ? ey - 3 : ey;
    ctx.beginPath();
    ctx.arc(x + (expr === "focus" ? -4 : 0) + o.turn * 6, py, pr, 0, Math.PI * 2);
    ctx.fillStyle = "#2a1650";
    ctx.fill();
    if (expr === "amazed" || expr === "grin") {
      ctx.beginPath();
      ctx.arc(x + 5 + o.turn * 6, py - 6, 5, 0, Math.PI * 2);
      ctx.fillStyle = "#ffffff";
      ctx.fill();
    }
    if (expr === "focus") {
      // heavy upper lid
      ctx.beginPath();
      ctx.ellipse(x, ey - 8, rx + 2, ry - 6, 0, Math.PI, Math.PI * 2);
      ctx.fillStyle = SKIN_SHADE;
      ctx.fill();
      stroke(ctx, 7);
    }
    if (lid > 0 && lid < 1) {
      // a half-open lid: skin coming down over the eye, which is what makes a
      // blink read as 4 shaped frames instead of an on/off pop
      ctx.beginPath();
      ctx.ellipse(x, ey - ry - 3 + 2 * ry * lid, rx + 4, ry, 0, 0, Math.PI * 2);
      ctx.fillStyle = SKIN;
      ctx.fill();
    }
  }
  // nose
  ctx.beginPath();
  const nx = 256 + o.dx * 1.3;
  ctx.ellipse(nx, 262, 20, 16, 0, 0, Math.PI * 2);
  ctx.fillStyle = "#f08a78";
  ctx.fill();
  stroke(ctx, 7);
  // curly moustache
  const m = o.dx * 1.15;
  ctx.beginPath();
  ctx.moveTo(256 + m, 280);
  ctx.bezierCurveTo(230 + m, 300, 196 + m, 300, 190 + m, 278);
  ctx.bezierCurveTo(186 + m, 266, 200 + m, 262, 204 + m, 272);
  ctx.moveTo(256 + m, 280);
  ctx.bezierCurveTo(282 + m, 300, 316 + m, 300, 322 + m, 278);
  ctx.bezierCurveTo(326 + m, 266, 312 + m, 262, 308 + m, 272);
  ctx.strokeStyle = "#7a3d1f";
  ctx.lineWidth = 12;
  ctx.stroke();
  stroke(ctx, 4);
  // mouth
  ctx.beginPath();
  const mx = 256 + m;
  if (expr === "grin") {
    // a delighted open grin: wide D under the moustache with a band of teeth;
    // speech only opens it a little further
    const t = 0.55 + 0.45 * o.talk;
    const w = 42;
    const bot = 322 + 34 * t;
    const shape = () => {
      ctx.beginPath();
      ctx.moveTo(mx - w, 304);
      ctx.quadraticCurveTo(mx, 310, mx + w, 304);
      ctx.quadraticCurveTo(mx + w * 0.7, bot, mx, bot);
      ctx.quadraticCurveTo(mx - w * 0.7, bot, mx - w, 304);
      ctx.closePath();
    };
    shape();
    ctx.fillStyle = "#7a1d3a";
    ctx.fill();
    ctx.save();
    shape();
    ctx.clip();
    ctx.fillStyle = "#ffffff";
    ctx.fillRect(mx - w, 300, 2 * w, 13);
    ctx.beginPath();
    ctx.ellipse(mx, bot - 4, w * 0.5, 7 + 4 * t, 0, 0, Math.PI * 2);
    ctx.fillStyle = "#e0566e";
    ctx.fill();
    ctx.restore();
    shape();
    stroke(ctx, 7);
    return;
  }
  if (o.talk > 0 && expr !== "shock" && expr !== "amazed" && expr !== "surprised") {
    // speech: an open mouth under the moustache, wider for a smile
    const t = o.talk;
    const w = (expr === "smile" ? 27 : 19) - 3 * t;
    const bot = 314 + 40 * t;
    const shape = () => {
      ctx.beginPath();
      ctx.moveTo(mx - w, 306);
      ctx.quadraticCurveTo(mx, expr === "smile" ? 312 : 304, mx + w, 306);
      ctx.quadraticCurveTo(mx, bot, mx - w, 306);
      ctx.closePath();
    };
    shape();
    ctx.fillStyle = "#7a1d3a";
    ctx.fill();
    if (t > 0.3) {
      ctx.save();
      shape();
      ctx.clip();
      ctx.beginPath();
      ctx.ellipse(mx, bot - 6, w * 0.6, 6 + 6 * t, 0, 0, Math.PI * 2);
      ctx.fillStyle = "#e0566e";
      ctx.fill();
      ctx.restore();
    }
    shape();
    stroke(ctx, 7);
    return;
  }
  if (expr === "smile") {
    ctx.moveTo(232 + m, 306);
    ctx.quadraticCurveTo(256 + m, 328, 280 + m, 306);
    stroke(ctx, 8);
  } else if (expr === "focus") {
    ctx.moveTo(244 + m, 312);
    ctx.lineTo(268 + m, 310);
    stroke(ctx, 8);
  } else if (expr === "shock") {
    const jaw = 14 * o.talk;
    ctx.moveTo(228 + m, 312);
    for (let i = 0; i <= 6; i++) ctx.lineTo(228 + m + i * 9, 312 + (i % 2 ? 14 : 0));
    ctx.lineTo(282 + m, 340 + jaw);
    ctx.lineTo(228 + m, 340 + jaw);
    ctx.closePath();
    ctx.fillStyle = "#7a1d3a";
    ctx.fill();
    stroke(ctx, 7);
  } else if (expr === "surprised") {
    // a small round "oh"
    ctx.ellipse(mx, 320 + 4 * o.talk, 12 + 2 * o.talk, 15 + 10 * o.talk, 0, 0, Math.PI * 2);
    ctx.fillStyle = "#7a1d3a";
    ctx.fill();
    stroke(ctx, 7);
  } else {
    ctx.ellipse(mx, 322 + 5 * o.talk, 16 + 2 * o.talk, 22 + 12 * o.talk, 0, 0, Math.PI * 2);
    ctx.fillStyle = "#7a1d3a";
    ctx.fill();
    stroke(ctx, 7);
  }
};

export type OpParams = {
  /** current pose and the pose being moved toward, with 0..1 between them.
   *  Poses are BLENDED, not switched: the reference never snaps a body from one
   *  attitude to another, it glides over 18-40 frames. */
  pose: Pose;
  poseTo?: Pose;
  blend: number;
  expr: Expr;
  /** eyelid, 0 open .. 1 shut */
  lid: number;
  /** telegraph key tapping, 0 = hand down on the key .. 1 = wound up */
  tap: number;
  /** head tilt in degrees */
  headTilt: number;

  // ---- PROBE 2 acting (all optional; absent = spike 2's desk drawing exactly) ----
  /** "desk" (default) = seated at the key, pose/blend/tap apply. "stand" = on his
   *  feet outdoors; pose/blend/tap are ignored and `gesture` drives the arms. */
  stance?: "desk" | "stand";
  /** standing gesture moved TO (default "idle") */
  gesture?: OpGesture;
  /** standing gesture moved FROM (default "idle") */
  gestureFrom?: OpGesture;
  /** 0 = fully `gestureFrom` .. 1 = fully `gesture` (default 1), eased inside */
  gestureBlend?: number;
  /** "point" direction in degrees: 0 = canvas +x (his left, viewer's right),
   *  90 = straight up, 180 = canvas -x, negative = downward. Default 30. The arm
   *  is held to a reachable, unoccluded angle; the FINGER takes the exact angle. */
  pointAngle?: number;
  /** free-running time in SECONDS (frame / 30): the wave's wag, the talk
   *  gestures' cycle, the idle sway. Default 0. */
  beat?: number;
  /** -1 = face turned to canvas -x .. 1 = to canvas +x (default 0); both stances */
  headTurn?: number;
  /** mouth open amount for speech, 0 .. 1 (default 0); both stances. In "talk"
   *  it also scales how big the hand gestures are. */
  talk?: number;
};

export type OpGesture = "idle" | "wave" | "point" | "armsCrossed" | "handsOnHips" | "talk";
export const OP_GESTURES: readonly OpGesture[] = ["idle", "wave", "point", "armsCrossed", "handsOnHips", "talk"];

/** blend two arm poses */
const mixPose = (a: (typeof ARMS)[Pose], b: (typeof ARMS)[Pose], t: number) => ({
  l: [lerpP(a.l[0], b.l[0], t), lerpP(a.l[1], b.l[1], t), lerpP(a.l[2], b.l[2], t)] as [RigP, RigP, RigP],
  r: [lerpP(a.r[0], b.r[0], t), lerpP(a.r[1], b.r[1], t), lerpP(a.r[2], b.r[2], t)] as [RigP, RigP, RigP],
  lean: a.lean + (b.lean - a.lean) * t,
  lOpen: lerp(a.lOpen ? 1 : 0, b.lOpen ? 1 : 0, t),
  rOpen: lerp(a.rOpen ? 1 : 0, b.rOpen ? 1 : 0, t),
});

const drawTorso = (ctx: CanvasRenderingContext2D) => {
  // arms behind the body for poses where they hang back
  // torso: shirt + waistcoat
  ctx.beginPath();
  ctx.moveTo(180, 352);
  ctx.quadraticCurveTo(256, 334, 332, 352);
  ctx.lineTo(320, 640);
  ctx.quadraticCurveTo(256, 656, 192, 640);
  ctx.closePath();
  ctx.fillStyle = SHIRT;
  ctx.fill();
  stroke(ctx);
  ctx.beginPath();
  ctx.moveTo(186, 362);
  ctx.lineTo(236, 372);
  ctx.lineTo(256, 470);
  ctx.lineTo(276, 372);
  ctx.lineTo(326, 362);
  ctx.lineTo(318, 640);
  ctx.quadraticCurveTo(256, 656, 194, 640);
  ctx.closePath();
  ctx.fillStyle = VEST;
  ctx.fill();
  stroke(ctx, 8);
  ctx.fillStyle = "#ffd34d";
  for (let i = 0; i < 4; i++) {
    ctx.beginPath();
    ctx.arc(256, 500 + i * 36, 7, 0, Math.PI * 2);
    ctx.fill();
    stroke(ctx, 5);
  }
  // watch chain
  ctx.beginPath();
  ctx.moveTo(256, 540);
  ctx.quadraticCurveTo(290, 570, 312, 548);
  ctx.strokeStyle = "#ffd34d";
  ctx.lineWidth = 4;
  ctx.stroke();

  // neck + bow tie
  ctx.beginPath();
  ctx.rect(238, 300, 36, 52);
  ctx.fillStyle = SKIN_SHADE;
  ctx.fill();
  stroke(ctx, 8);
  ctx.beginPath();
  ctx.moveTo(256, 360);
  ctx.lineTo(224, 344);
  ctx.lineTo(224, 378);
  ctx.closePath();
  ctx.moveTo(256, 360);
  ctx.lineTo(288, 344);
  ctx.lineTo(288, 378);
  ctx.closePath();
  ctx.fillStyle = GARTER;
  ctx.fill();
  stroke(ctx, 6);

};

const drawHead = (ctx: CanvasRenderingContext2D, q: OpParams, turn: number, talk: number) => {
  for (const x of [116, 396]) {
    ctx.beginPath();
    ctx.arc(x - turn * 16, 222, 30, 0, Math.PI * 2);
    ctx.fillStyle = SKIN_SHADE;
    ctx.fill();
    stroke(ctx, 8);
  }
  ctx.beginPath();
  ctx.arc(256, 196, 140, 0, Math.PI * 2);
  ctx.fillStyle = SKIN;
  ctx.fill();
  stroke(ctx, 11);
  // hair tufts at the sides
  ctx.fillStyle = "#c2552b";
  for (const s of [-1, 1]) {
    const hx = 256 - turn * 16;
    ctx.beginPath();
    ctx.moveTo(hx + s * 132, 150);
    ctx.quadraticCurveTo(hx + s * 162, 180, hx + s * 140, 226);
    ctx.quadraticCurveTo(hx + s * 122, 190, hx + s * 112, 150);
    ctx.closePath();
    ctx.fill();
    stroke(ctx, 6);
  }
  // features slide across the face on a turn, clipped to the head outline
  const dx = turn * 34;
  if (dx !== 0) {
    ctx.save();
    ctx.beginPath();
    ctx.arc(256, 196, 137, 0, Math.PI * 2);
    ctx.clip();
  }
  // cheeks
  ctx.fillStyle = "rgba(240, 110, 120, 0.35)";
  for (const x of [176, 336]) {
    ctx.beginPath();
    ctx.ellipse(x + dx, 262, 22, 14, 0, 0, Math.PI * 2);
    ctx.fill();
  }
  face(ctx, q.expr, q.lid, dx !== 0 || talk > 0 ? { dx, turn, talk } : undefined);
  if (dx !== 0) ctx.restore();
  // eyeshade: band + translucent bill
  ctx.beginPath();
  const bx = turn * 8;
  ctx.moveTo(118 + bx, 136);
  ctx.quadraticCurveTo(256 + bx, 96, 394 + bx, 136);
  ctx.lineTo(394 + bx, 112);
  ctx.quadraticCurveTo(256 + bx, 70, 118 + bx, 112);
  ctx.closePath();
  ctx.fillStyle = "#1e7f4f";
  ctx.fill();
  stroke(ctx, 8);
  ctx.beginPath();
  const vx = turn * 22;
  ctx.moveTo(100 + vx, 140);
  ctx.quadraticCurveTo(256 + vx, 100, 412 + vx, 140);
  ctx.quadraticCurveTo(420 + vx, 172, 380 + vx, 176);
  ctx.quadraticCurveTo(256 + vx, 150, 132 + vx, 176);
  ctx.quadraticCurveTo(92 + vx, 172, 100 + vx, 140);
  ctx.closePath();
  ctx.fillStyle = VISOR;
  ctx.fill();
  stroke(ctx, 8);
};

// ------------------------------------------------------------ standing rig
//
// Every standing gesture is authored as ARM ANGLES (rig.ArmPose): the upper
// arm's direction and the elbow bend, degrees, 0 = viewer's right, 90 = up.
// Gestures blend on arcs (mixArmPose), so an arm swings out and up the way an
// arm moves; the end points + IK-hint scheme this replaces flipped the elbow
// whenever the blended hint crossed the shoulder-hand line (the "talk" beat
// chicken-winged every few frames) and folded forearms through the chest.
const ST_SHO_L: P = [192, 362];
const ST_SHO_R: P = [320, 362];
const ST_UPPER = 112;
const ST_FORE = 100;
const TAU = Math.PI * 2;

type OpArm = ArmPose & {
  /** 0 = fist .. 1 = open palm */
  open?: number;
  /** finger fan direction (deg); default = along the forearm */
  dir?: number;
  /** pointing index finger, this many degrees */
  finger?: number;
  /** the hand is drawn BEFORE both arms (tucked under the other arm) */
  under?: boolean;
};
type OpSpec = { l: OpArm; r: OpArm; lean: number; tilt: number };

// hanging arms: a little bend at the elbow, hands beside the thighs, slow sway
const IDLE_L = (b: number): OpArm => ({ ua: -108 + 2 * Math.sin(TAU * 0.3 * b), bend: 28 });
const IDLE_R = (b: number): OpArm => ({ ua: -72 - 2 * Math.sin(TAU * 0.3 * b), bend: -28 });

/** A straight arm aimed along `deg` with the index finger out. The arm must
 *  stay inside the 512 wide canvas and clear of the big head, so the ARM angle
 *  is held to a window that keeps it long (a shallow angle would end at the
 *  canvas edge as a stubby bent arm that read as a salute); the finger then
 *  bends the wrist toward the exact angle, up to 20 deg. */
const aim = (deg: number): { isR: boolean; arm: OpArm } => {
  const isR = Math.cos((deg * Math.PI) / 180) >= 0;
  let a = isR ? Math.max(-70, Math.min(55, deg)) : Math.max(125, Math.min(250, deg));
  // steepen shallow angles so the arm is at least ~175 of its 212 reach
  const fl = isR ? a : wrapDeg(180 - a);
  if (Math.abs(fl) < 42) {
    const steep = fl >= 0 ? 42 : -42;
    a = isR ? steep : 180 - steep;
  }
  const sho = isR ? ST_SHO_R : ST_SHO_L;
  const ux = Math.cos((a * Math.PI) / 180);
  let r = (ST_UPPER + ST_FORE) * 0.97;
  // keep hand + finger inside the canvas
  if (ux > 0) r = Math.min(r, (452 - sho[0]) / ux);
  if (ux < 0) r = Math.min(r, (60 - sho[0]) / ux);
  const sc = r / (ST_UPPER + ST_FORE);
  const finger = a + Math.max(-20, Math.min(20, wrapDeg(deg - a)));
  return { isR, arm: { ua: a, bend: isR ? -4 : 4, su: sc, sf: sc, finger, open: 0 } };
};

const opSpec = (g: OpGesture, b: number, q: OpParams): OpSpec => {
  const base: OpSpec = { l: IDLE_L(b), r: IDLE_R(b), lean: 0.6 * Math.sin(TAU * 0.2 * b), tilt: 0 };
  switch (g) {
    case "wave":
      // upper arm out to the side, forearm wagging up beside (not over) the head
      return { ...base, r: { ua: 12, bend: 73 + 15 * Math.sin(TAU * 2.2 * b), open: 1, dir: 90 }, tilt: 4 };
    case "point": {
      const { isR, arm } = aim(q.pointAngle ?? 30);
      return isR ? { ...base, r: arm, lean: 2, tilt: 3 } : { ...base, l: arm, lean: -2, tilt: -3 };
    }
    case "armsCrossed":
      // forearms folded across the chest, R over L, both hands tucked under the
      // opposite upper arm (drawn first), chin up a touch
      return {
        ...base,
        l: { ua: -75, bend: 72, sf: 0.6, under: true },
        r: { ua: -112, bend: -76, sf: 0.68, under: true },
        lean: -1.5,
        tilt: -3,
      };
    case "handsOnHips":
      return { ...base, l: { ua: -130, bend: 88 }, r: { ua: -50, bend: -88 }, lean: -1, tilt: 2 };
    case "talk": {
      // explaining: elbows at the sides, open palms out at waist-to-chest
      // height, each hand on its own rhythm; the right leads, the left answers
      // ~half a beat later; everything scales with how hard he is talking.
      // The hands never rise above the chin line (the head is huge).
      const k = 0.35 + 0.65 * clamp01(q.talk ?? 0);
      const acc = (ph: number) => Math.max(0, Math.sin(TAU * b + ph)) ** 2;
      const slow = Math.sin(TAU * 0.5 * b);
      return {
        ...base,
        r: { ua: -58 + 8 * k * slow, bend: 82 + 26 * k * acc(0) + 6 * k * Math.sin(TAU * 0.5 * b + 1.0), sf: 0.85, open: 1 },
        l: { ua: -122 + 8 * k * Math.sin(TAU * 0.5 * b + 1.3), bend: -78 - 26 * k * acc(2.4) - 6 * k * slow, sf: 0.85, open: 1 },
        tilt: 2.5 * k * slow,
      };
    }
    default:
      return base;
  }
};

/** blend two OpArms: angles on arcs, hand state continuously */
const mixOpArm = (x: OpArm, y: OpArm, t: number): OpArm & { fingerW: number; underW: number } => {
  const pose = mixArmPose(x, y, t);
  const fx = x.finger !== undefined;
  const fy = y.finger !== undefined;
  const finger = fx && fy ? lerpDeg(x.finger!, y.finger!, t) : fx ? x.finger! : fy ? y.finger! : undefined;
  const dx = x.dir ?? pose.ua + pose.bend;
  const dy = y.dir ?? pose.ua + pose.bend;
  return {
    ...pose,
    open: lerp(x.open ?? 0, y.open ?? 0, t),
    dir: lerpDeg(dx, dy, t),
    finger,
    fingerW: lerp(fx ? 1 : 0, fy ? 1 : 0, t),
    underW: lerp(x.under ? 1 : 0, y.under ? 1 : 0, t),
  };
};

const drawStanding = (ctx: CanvasRenderingContext2D, q: OpParams, turn: number, talk: number) => {
  const b = q.beat ?? 0;
  const t = smootherstep(clamp01(q.gestureBlend ?? 1));
  const A = opSpec(q.gestureFrom ?? "idle", b, q);
  const B = opSpec(q.gesture ?? "idle", b, q);
  const L = { ...mixOpArm(A.l, B.l, t) };
  const R = { ...mixOpArm(A.r, B.r, t) };
  // a hand swinging past the canvas edge mid-blend comes toward the camera
  Object.assign(L, fitArmX(ST_SHO_L, L, ST_UPPER, ST_FORE, 46, 466));
  Object.assign(R, fitArmX(ST_SHO_R, R, ST_UPPER, ST_FORE, 46, 466));
  const lean = lerp(A.lean, B.lean, t);
  const tilt = lerp(A.tilt, B.tilt, t);
  const armL = armFK(ST_SHO_L, L, ST_UPPER, ST_FORE);
  const armR = armFK(ST_SHO_R, R, ST_UPPER, ST_FORE);

  // legs: planted, a little apart, NOT leaning with the body (the feet carry
  // the weight; a leaning leg reads as sliding)
  limb(ctx, [[226, 630], [216, 815], [206, 990]], 30, TROUSER);
  limb(ctx, [[286, 630], [296, 815], [306, 990]], 30, TROUSER);
  for (const x of [196, 316]) {
    ctx.beginPath();
    ctx.ellipse(x + (x < 256 ? -8 : 8), 996, 36, 16, 0, 0, Math.PI * 2);
    ctx.fillStyle = "#6b2e2e";
    ctx.fill();
    stroke(ctx, 7);
  }
  ctx.save();
  ctx.translate(256, 640);
  ctx.rotate((lean * Math.PI) / 180);
  ctx.translate(-256, -640);
  drawTorso(ctx);
  // a foreshortened (toward-camera) hand draws a little bigger
  const radius = (p: OpArm) => 22 + 10 * (1 - Math.min(1, p.sf ?? 1));
  const arms: [OpArm & { fingerW: number; underW: number }, [P, P, P]][] = [
    [L, armL],
    [R, armR],
  ];
  // hands tucked under the other arm go down first
  for (const [p, a] of arms) if (p.underW > 0.5) hand(ctx, a[2], p.open, p.dir, radius(p));
  for (const [p, a] of arms) {
    const h = a[2];
    if (p.finger !== undefined && p.fingerW > 0.02) {
      // index finger, growing out of the fist as the point blends in
      const ang = (p.finger * Math.PI) / 180;
      const len = 58 * p.fingerW;
      ctx.beginPath();
      ctx.moveTo(h[0], h[1]);
      ctx.lineTo(h[0] + Math.cos(ang) * len, h[1] - Math.sin(ang) * len);
      ctx.strokeStyle = INK;
      ctx.lineWidth = 26;
      ctx.lineCap = "round";
      ctx.stroke();
      ctx.strokeStyle = SKIN;
      ctx.lineWidth = 12;
      ctx.stroke();
    }
    arm(ctx, a[0], a[1], a[2], p.open, p.dir, radius(p), p.underW <= 0.5);
  }
  ctx.save();
  ctx.translate(256, 330);
  ctx.rotate(((q.headTilt + tilt) * Math.PI) / 180);
  ctx.translate(-256, -330);
  drawHead(ctx, q, turn, talk);
  ctx.restore(); // head tilt
  ctx.restore(); // body lean
};

export const drawOperator =
  (q: OpParams): DrawFn =>
  (ctx) => {
    const turn = Math.max(-1, Math.min(1, q.headTurn ?? 0));
    const talk = clamp01(q.talk ?? 0);
    if (q.stance === "stand") {
      drawStanding(ctx, q, turn, talk);
      return;
    }
    const from = ARMS[q.pose];
    const to = ARMS[q.poseTo ?? q.pose];
    const a = mixPose(from, to, smootherstep(q.blend));
    // the tapping hand rides up and down on the key: a held wind-up and a quick
    // strike, rather than a smooth sine that reads as waving
    const lift = 34 * q.tap;
    const l: [P, P, P] = [a.l[0], [a.l[1][0], a.l[1][1] - lift * 0.5], [a.l[2][0], a.l[2][1] - lift]];
    ctx.save();
    // lean: rotate the upper body about the hips
    ctx.translate(256, 640);
    ctx.rotate((a.lean * Math.PI) / 180 / 4);
    ctx.translate(-256, -640);

    // legs (seated, knees forward, mostly hidden by the desk)
    limb(ctx, [[226, 630], [214, 820], [210, 990]], 30, TROUSER);
    limb(ctx, [[286, 630], [298, 820], [302, 990]], 30, TROUSER);
    for (const x of [200, 312]) {
      ctx.beginPath();
      ctx.ellipse(x, 996, 34, 16, 0, 0, Math.PI * 2);
      ctx.fillStyle = "#6b2e2e";
      ctx.fill();
      stroke(ctx, 7);
    }

    drawTorso(ctx);

    arm(ctx, ...l, a.lOpen);
    arm(ctx, ...a.r, a.rOpen);

    // head (tilts on acting beats)
    ctx.save();
    ctx.translate(256, 330);
    ctx.rotate((q.headTilt * Math.PI) / 180);
    ctx.translate(-256, -330);
    drawHead(ctx, q, turn, talk);
    ctx.restore(); // head tilt
    ctx.restore(); // body lean
  };

export const opRest = (): OpParams => ({
  pose: "tap",
  blend: 0,
  expr: "focus",
  lid: 0,
  tap: 0,
  headTilt: 0,
});
