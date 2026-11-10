/*
 * The house bean: one fixed character, drawn here and nowhere else. The agent
 * chooses a pose, a face, where it looks, an accessory and (for a second bean)
 * a tint; it never draws.
 *
 * Body coordinates: feet at (0, 0), +y down. One ink weight (LINE at scale 1),
 * flat fills, no shading. Poses are hand targets solved with two-bone IK, so
 * every pose shares one head, torso and line, and a swap reads as the same
 * character moving. Faces are lid, brow and mouth swaps. A pure function of
 * its props.
 */
import React from "react";
import { spring } from "remotion";
import type { Accessory, Face, Look, MarkType, Pose, Tint } from "./contract";

export const INK = "#1E1C1A";
export const LINE = 8;
export const RED = "#D0201C";
export const SKIN: Record<Tint, string> = {
  cream: "#FEF1D1",
  peach: "#FFD6BD",
  grey: "#DADADA",
  mint: "#D2F1DF",
  lilac: "#E5DAF7",
};

export type V = [number, number];
export type PoseSpec = {
  lean: number; // degrees, upper body about the hips
  lHand: V; rHand: V; // hand targets (body coords)
  lBend: number; rBend: number; // which side the elbow goes (+1 / -1)
  lFoot: number; rFoot: number; // foot x
  headTilt: number;
  drop: number; // hips drop (knee bend), px
  handsFront?: boolean; // hands drawn over the torso
  armsFront?: ("l" | "r")[]; // whole arms drawn over the torso (a hand at the chin or face)
};

const HIP_Y = -224;
const SHOULDER: V = [62, -432];
export const HEAD_C: V = [0, -578];
const HEAD_R = 120;
const UA = 120, FA = 114; // arm bones
const TH = 104, SH = 104; // leg bones
export const ARM_REACH = UA + FA;

export const POSES: Record<Pose, PoseSpec> = {
  stand: { lean: 0, lHand: [-112, -214], rHand: [112, -214], lBend: 1, rBend: -1, lFoot: -44, rFoot: 44, headTilt: 0, drop: 0 },
  point: { lean: 4, lHand: [-104, -300], rHand: [300, -470], lBend: 1, rBend: 1, lFoot: -50, rFoot: 46, headTilt: 4, drop: 4 },
  present: { lean: 3, lHand: [-112, -220], rHand: [250, -420], lBend: 1, rBend: -1, lFoot: -46, rFoot: 50, headTilt: 5, drop: 2 },
  wave: { lean: -2, lHand: [-112, -214], rHand: [196, -650], lBend: 1, rBend: 1, lFoot: -44, rFoot: 44, headTilt: -4, drop: 0 },
  cheer: { lean: 0, lHand: [-190, -690], rHand: [190, -690], lBend: -1, rBend: 1, lFoot: -64, rFoot: 64, headTilt: 0, drop: -6 },
  shrug: { lean: 0, lHand: [-214, -440], rHand: [214, -440], lBend: -1, rBend: 1, lFoot: -46, rFoot: 46, headTilt: 7, drop: 0 },
  think: { lean: 2, lHand: [66, -340], rHand: [44, -462], lBend: -1, rBend: -1, lFoot: -44, rFoot: 44, headTilt: 6, drop: 0, handsFront: true, armsFront: ["l", "r"] },
  facepalm: { lean: 6, lHand: [-112, -214], rHand: [0, -596], lBend: 1, rBend: -1, lFoot: -48, rFoot: 44, headTilt: -8, drop: 8, handsFront: true, armsFront: ["r"] },
  "hands-hips": { lean: 0, lHand: [-92, -236], rHand: [92, -236], lBend: 1, rBend: -1, lFoot: -58, rFoot: 58, headTilt: 0, drop: 0 },
  panic: { lean: 0, lHand: [-126, -612], rHand: [126, -612], lBend: -1, rBend: 1, lFoot: -70, rFoot: 70, headTilt: -3, drop: 18, handsFront: true },
  lean: { lean: 10, lHand: [-92, -250], rHand: [270, -380], lBend: 1, rBend: 1, lFoot: -58, rFoot: 62, headTilt: 8, drop: 14 },
};

const rot = (p: V, c: V, deg: number): V => {
  const r = (deg * Math.PI) / 180, dx = p[0] - c[0], dy = p[1] - c[1];
  return [c[0] + dx * Math.cos(r) - dy * Math.sin(r), c[1] + dx * Math.sin(r) + dy * Math.cos(r)];
};

/** Two-bone IK: [elbow, hand]; the hand stops at the reach limit. */
export function ik(s: V, t: V, a: number, b: number, bend: number): [V, V] {
  const dx = t[0] - s[0], dy = t[1] - s[1];
  const d0 = Math.hypot(dx, dy) || 1;
  const d = Math.min(Math.max(d0, Math.abs(a - b) + 1), a + b - 0.5);
  const ux = dx / d0, uy = dy / d0;
  const h: V = [s[0] + ux * d, s[1] + uy * d];
  const x = (a * a - b * b + d * d) / (2 * d);
  const y = Math.sqrt(Math.max(0, a * a - x * x)) * bend;
  return [[s[0] + ux * x - uy * y, s[1] + uy * x + ux * y], h];
}

const Tube: React.FC<{ pts: V[]; w: number; skin: string }> = ({ pts, w, skin }) => {
  const d = "M " + pts.map((p) => `${p[0].toFixed(1)},${p[1].toFixed(1)}`).join(" L ");
  return (
    <>
      <path d={d} stroke={INK} strokeWidth={w + LINE * 2} fill="none" strokeLinecap="round" strokeLinejoin="round" />
      <path d={d} stroke={skin} strokeWidth={w} fill="none" strokeLinecap="round" strokeLinejoin="round" />
    </>
  );
};

// ── faces ─────────────────────────────────────────────────────────────────────
type FaceSpec = {
  lid: number; lidTilt: number; // 0 open .. 1 closed; +tilt: inner corner lower
  brow: [V, V]; browArch: number; // left brow inner/outer (mirrored for right) + arch
  browR?: [V, V];
  mouth: string; mouthFill?: boolean;
  pupil: number; bags: boolean;
};
const FACES: Record<Face, FaceSpec> = {
  neutral: { lid: 0.48, lidTilt: 0, brow: [[-18, -54], [-64, -52]], browArch: -3, mouth: "M -24,62 Q 0,55 24,62", pupil: 9, bags: true },
  happy: { lid: 0.3, lidTilt: 0, brow: [[-18, -64], [-64, -62]], browArch: -10, mouth: "M -32,54 Q 0,90 32,54", pupil: 9, bags: false },
  worried: { lid: 0.22, lidTilt: -10, brow: [[-16, -66], [-64, -48]], browArch: -4, mouth: "M -28,66 Q -19,56 -9,64 Q 0,72 9,64 Q 19,56 28,66", pupil: 9, bags: false },
  shocked: { lid: 0, lidTilt: 0, brow: [[-18, -70], [-64, -66]], browArch: -12, mouth: "M 0,44 C 22,44 22,88 0,88 C -22,88 -22,44 0,44 Z", mouthFill: true, pupil: 6, bags: false },
  squint: { lid: 0.66, lidTilt: 0, brow: [[-14, -40], [-64, -52]], browArch: 2, browR: [[14, -60], [64, -70]], mouth: "M -6,64 L 28,58", pupil: 9, bags: true },
  smug: { lid: 0.56, lidTilt: 6, brow: [[-16, -50], [-64, -60]], browArch: -3, mouth: "M -26,56 Q 6,78 32,52", pupil: 9, bags: false },
  sad: { lid: 0.4, lidTilt: -14, brow: [[-14, -64], [-64, -46]], browArch: 2, mouth: "M -28,74 Q 0,54 28,74", pupil: 9, bags: true },
  angry: { lid: 0.36, lidTilt: 14, brow: [[-12, -40], [-64, -62]], browArch: 4, mouth: "M -26,70 Q 0,60 26,70", pupil: 8, bags: false },
};
/** How long a wave keeps waving after its swap, in frames since the swap. */
export const WAVE_FRAMES = 30;

const LOOK_DX: Record<Look, number> = { front: 0, left: -1, right: 1 };

const Eye: React.FC<{ cx: number; side: -1 | 1; f: FaceSpec; look: number; blink: number; skin: string; id: string }> = ({ cx, side, f, look, blink, skin, id }) => {
  const rx = 24, ry = f.lid === 0 ? 31 : 28, cy = -8;
  const top = cy - ry - 4;
  const lid = Math.max(f.lid, blink);
  const lidY = cy - ry + lid * ry * 2;
  const tilt = blink > 0.5 ? 0 : f.lidTilt;
  const xIn = cx - side * rx * 1.2, xOut = cx + side * rx * 1.2;
  const yIn = lidY + tilt / 2, yOut = lidY - tilt / 2;
  return (
    <g>
      <clipPath id={id}><ellipse cx={cx} cy={cy} rx={rx} ry={ry} /></clipPath>
      <ellipse cx={cx} cy={cy} rx={rx} ry={ry} fill="#FFFFFF" />
      <circle cx={cx + look * 9} cy={cy + 6 + lid * 6} r={f.pupil} fill={INK} />
      {lid > 0 && (
        <g clipPath={`url(#${id})`}>
          <path d={`M ${xIn},${top} L ${xOut},${top} L ${xOut},${yOut} L ${xIn},${yIn} Z`} fill={skin} />
          <path d={`M ${xIn},${yIn} L ${xOut},${yOut}`} stroke={INK} strokeWidth={7} />
        </g>
      )}
      <ellipse cx={cx} cy={cy} rx={rx} ry={ry} fill="none" stroke={INK} strokeWidth={6} />
      {f.bags && <path d={`M ${cx - 16},${cy + ry + 8} Q ${cx},${cy + ry + 15} ${cx + 16},${cy + ry + 8}`} stroke={INK} strokeWidth={4} fill="none" strokeLinecap="round" opacity={0.75} />}
    </g>
  );
};

const FaceView: React.FC<{ face: Face; look: number; blink: number; skin: string; uid: string }> = ({ face, look, blink, skin, uid }) => {
  const f = FACES[face];
  const browPath = (inner: V, outer: V, arch: number) => {
    const mx = (inner[0] + outer[0]) / 2, my = (inner[1] + outer[1]) / 2 + arch;
    return `M ${inner[0]},${inner[1]} Q ${mx},${my} ${outer[0]},${outer[1]}`;
  };
  const lb = f.brow;
  const rb: [V, V] = f.browR ?? [[-lb[0][0], lb[0][1]], [-lb[1][0], lb[1][1]]];
  return (
    <g>
      <Eye cx={-40} side={-1} f={f} look={look} blink={blink} skin={skin} id={`${uid}-el`} />
      <Eye cx={40} side={1} f={f} look={look} blink={blink} skin={skin} id={`${uid}-er`} />
      <path d={browPath(lb[0], lb[1], f.browArch)} stroke={INK} strokeWidth={9} fill="none" strokeLinecap="round" />
      <path d={browPath(rb[0], rb[1], f.browArch)} stroke={INK} strokeWidth={9} fill="none" strokeLinecap="round" />
      <path d="M 4,14 Q 18,24 4,32" stroke={INK} strokeWidth={5} fill="none" strokeLinecap="round" />
      {f.mouthFill ? (
        <g>
          <path d={f.mouth} fill={INK} />
          <ellipse cx={0} cy={78} rx={9} ry={6} fill="#E86A6A" />
        </g>
      ) : (
        <path d={f.mouth} stroke={INK} strokeWidth={7} fill="none" strokeLinecap="round" strokeLinejoin="round" />
      )}
      {face === "smug" && <path d="M 30,46 Q 38,52 36,60" stroke={INK} strokeWidth={4} fill="none" strokeLinecap="round" />}
      {face === "happy" && (
        <g fill="#F2A3A3" opacity={0.7}>
          <ellipse cx={-70} cy={34} rx={16} ry={9} />
          <ellipse cx={70} cy={34} rx={16} ry={9} />
        </g>
      )}
    </g>
  );
};

// ── marks: reactions that pop beside the head (head coordinates) ─────────────
const MARK_PLACE: Record<MarkType, { x: number; y: number; rot: number }> = {
  sweat: { x: -150, y: -30, rot: 0 },
  alarm: { x: 130, y: -140, rot: 20 },
  question: { x: 120, y: -190, rot: 12 },
  exclaim: { x: 120, y: -190, rot: 8 },
  sparkle: { x: -190, y: -60, rot: 0 },
  shock: { x: -150, y: -110, rot: -40 },
  anger: { x: 112, y: -112, rot: 0 },
  idea: { x: 118, y: -200, rot: 10 },
};

const MARK_SETTLE = 30;

const MarkShape: React.FC<{ type: MarkType; t: number; font: string }> = ({ type, t, font }) => {
  switch (type) {
    case "sweat":
      return (
        <g transform={`translate(0 ${Math.min(t, 1) * 10})`}>
          <path d="M 0,-30 C 11,-10 18,2 18,12 A 18,18 0 0 1 -18,12 C -18,2 -11,-10 0,-30 Z" fill="#7FD0F2" stroke={INK} strokeWidth={5} strokeLinejoin="round" />
          <path d="M -8,8 Q -8,0 -3,-6" stroke="#FFFFFF" strokeWidth={4} fill="none" strokeLinecap="round" />
        </g>
      );
    case "alarm": {
      const pulse = t >= 1 ? 1 : 1 + 0.06 * Math.sin(t * 18);
      const arm = "M 7,-24 Q 7,-7 24,-7";
      return (
        <g transform={`scale(${pulse})`}>
          {[0, 90, 180, 270].map((a) => (
            <g key={a} transform={`rotate(${a})`}>
              <path d={arm} stroke={INK} strokeWidth={15} fill="none" strokeLinecap="round" />
              <path d={arm} stroke="#E2302B" strokeWidth={8} fill="none" strokeLinecap="round" />
            </g>
          ))}
        </g>
      );
    }
    case "question":
    case "exclaim":
      return (
        <text x={0} y={36} textAnchor="middle" fontSize={118} fontWeight={700} fill={type === "exclaim" ? RED : INK} stroke={INK} strokeWidth={type === "exclaim" ? 5 : 2}
          paintOrder="stroke" style={{ fontFamily: font }}>{type === "question" ? "?" : "!"}</text>
      );
    case "sparkle": {
      const s = t >= 1 ? 1 : 1 + 0.08 * Math.sin(t * 10);
      return (
        <g transform={`scale(${s})`}>
          <path d="M 0,-30 Q 4,-4 30,0 Q 4,4 0,30 Q -4,4 -30,0 Q -4,-4 0,-30 Z" fill="#FFFFFF" stroke={INK} strokeWidth={5} strokeLinejoin="round" />
          <path transform="translate(-44 40) scale(0.5)" d="M 0,-30 Q 4,-4 30,0 Q 4,4 0,30 Q -4,4 -30,0 Q -4,-4 0,-30 Z" fill="#FFFFFF" stroke={INK} strokeWidth={8} strokeLinejoin="round" />
        </g>
      );
    }
    case "anger": {
      const s = t >= 1 ? 1 : 1 + 0.1 * Math.max(0, Math.sin(t * 14));
      const arc = "M -6,-26 Q -6,-6 -26,-6";
      return (
        <g transform={`scale(${s})`}>
          {[0, 90, 180, 270].map((a) => (
            <path key={a} transform={`rotate(${a})`} d={arc} stroke={RED} strokeWidth={9} fill="none" strokeLinecap="round" />
          ))}
        </g>
      );
    }
    case "idea":
      return (
        <g>
          {[-50, -25, 0, 25, 50].map((a) => (
            <path key={a} transform={`rotate(${a})`} d="M 0,-58 L 0,-74" stroke={INK} strokeWidth={6} strokeLinecap="round" />
          ))}
          <path d="M -26,10 C -40,-6 -36,-42 0,-44 C 36,-42 40,-6 26,10 L 22,24 L -22,24 Z" fill="#FFE45C" stroke={INK} strokeWidth={6} strokeLinejoin="round" />
          <rect x={-18} y={24} width={36} height={16} rx={5} fill="#BFBFBF" stroke={INK} strokeWidth={6} />
        </g>
      );
    default:
      // shock: radiating lines
      return (
        <g>
          {[-30, 0, 30].map((a) => (
            <path key={a} transform={`rotate(${a})`} d="M 0,-14 L 0,-50" stroke={INK} strokeWidth={9} strokeLinecap="round" />
          ))}
        </g>
      );
  }
};

// ── accessories ───────────────────────────────────────────────────────────────
/** Drawn in head coordinates (centre of the head at 0,0), over the face. */
const HeadAccessory: React.FC<{ a: Accessory }> = ({ a }) => {
  switch (a) {
    case "glasses":
      return (
        <g fill="none" stroke={INK} strokeWidth={7}>
          <circle cx={-40} cy={-8} r={36} fill="#FFFFFF" fillOpacity={0.15} />
          <circle cx={40} cy={-8} r={36} fill="#FFFFFF" fillOpacity={0.15} />
          <path d="M -4,-12 Q 0,-18 4,-12" />
          <path d="M -76,-12 L -112,-20 M 76,-12 L 112,-20" strokeLinecap="round" />
        </g>
      );
    case "cap":
      return (
        <g stroke={INK} strokeWidth={LINE} strokeLinejoin="round">
          <path d="M -112,-50 C -110,-150 110,-150 112,-50 Z" fill="#3B7DD8" />
          <path d="M 40,-56 C 120,-64 176,-56 186,-40 C 150,-30 90,-34 40,-40 Z" fill="#2E63B0" />
          <circle cx={0} cy={-120} r={9} fill="#2E63B0" />
        </g>
      );
    case "headset":
      return (
        <g stroke={INK} strokeWidth={LINE} strokeLinejoin="round" strokeLinecap="round">
          <path d="M -118,-10 C -120,-170 120,-170 118,-10" fill="none" strokeWidth={16} />
          <path d="M -118,-10 C -120,-170 120,-170 118,-10" fill="none" stroke="#555" strokeWidth={6} />
          <rect x={-140} y={-34} width={38} height={64} rx={14} fill="#555" />
          <rect x={102} y={-34} width={38} height={64} rx={14} fill="#555" />
          <path d="M -122,20 Q -110,80 -40,78" fill="none" strokeWidth={6} />
          <circle cx={-36} cy={78} r={10} fill="#555" />
        </g>
      );
    case "hardhat":
      return (
        <g stroke={INK} strokeWidth={LINE} strokeLinejoin="round">
          <path d="M -150,-52 L 150,-52 L 150,-36 L -150,-36 Z" fill="#F5C518" />
          <path d="M -108,-52 C -108,-170 108,-170 108,-52 Z" fill="#F5C518" />
          <path d="M -10,-150 L 10,-150 L 10,-52 L -10,-52 Z" fill="#E0AE00" />
        </g>
      );
    case "beanie":
      return (
        <g stroke={INK} strokeWidth={LINE} strokeLinejoin="round">
          <path d="M -114,-46 C -116,-170 116,-170 114,-46 Z" fill="#E2302B" />
          <path d="M -120,-60 L 120,-60 L 120,-30 L -120,-30 Z" fill="#B82420" />
          <circle cx={0} cy={-150} r={22} fill="#FFFFFF" />
        </g>
      );
    default:
      return null;
  }
};

/** The tie hangs from the neck, in torso coordinates. */
const Tie: React.FC = () => (
  <g stroke={INK} strokeWidth={6} strokeLinejoin="round">
    <path d="M -14,-462 L 14,-462 L 8,-440 L -8,-440 Z" fill="#E2302B" />
    <path d="M -8,-440 L 8,-440 L 22,-300 L 0,-276 L -22,-300 Z" fill="#E2302B" />
  </g>
);

/** Blink weight 0..1 at a frame: 3-4 frame blinks at irregular 2.4-4.2 s gaps, fixed per seed. */
export function blinkAt(frame: number, seed: number): number {
  let t = 40 + (seed * 29) % 50;
  let k = seed;
  while (t <= frame) {
    const d = frame - t;
    if (d < 4) return d === 0 || d === 3 ? 0.6 : 1;
    k = (k * 1103515245 + 12345) & 0x7fffffff;
    t += 72 + (k % 54);
  }
  return 0;
}

export type BeanProps = {
  frame: number;
  fps: number;
  x: number; y: number; scale: number;
  pose: Pose; prevPose: Pose; poseT: number; // blend 0..1 from prevPose to pose
  face: Face;
  look: Look;
  swapFrame: number; // frame of the last swap, for the squash
  aim?: V; // body-coord target for the right hand (point / present at a prop)
  marks: { type: MarkType; start: number }[];
  enter: number; // 0..1 pop-in scale
  accessory: Accessory;
  tint: Tint;
  seed: number;
  font: string;
  uid: string;
  /** Lid closure 0..1; computed from frame and seed when absent. */
  blink?: number;
  /** The frame the current pose began (the wave counts from it); 0 when absent. */
  poseAt?: number;
};

/** The pose at a moment: the blend of two table poses, the aim and the wave applied. */
export function blendedPose(p: Pick<BeanProps, "pose" | "prevPose" | "poseT" | "aim" | "frame" | "poseAt">): PoseSpec {
  const pa = { ...POSES[p.prevPose] }, pb = { ...POSES[p.pose] };
  if (p.aim && (p.pose === "point" || p.pose === "present" || p.pose === "lean")) pb.rHand = p.aim;
  // waves for a second after the swap, then holds like every other pose
  if (p.pose === "wave") pb.rHand = [pb.rHand[0] + Math.sin(Math.max(0, Math.min(p.frame - (p.poseAt ?? 0), WAVE_FRAMES)) / 3) * 26, pb.rHand[1]];
  const t = p.poseT;
  const lerp = (a: number, b: number) => a + (b - a) * t;
  const lerpV = (a: V, b: V): V => [lerp(a[0], b[0]), lerp(a[1], b[1])];
  return {
    lean: lerp(pa.lean, pb.lean), lHand: lerpV(pa.lHand, pb.lHand), rHand: lerpV(pa.rHand, pb.rHand),
    lBend: t < 0.5 ? pa.lBend : pb.lBend, rBend: t < 0.5 ? pa.rBend : pb.rBend,
    lFoot: lerp(pa.lFoot, pb.lFoot), rFoot: lerp(pa.rFoot, pb.rFoot),
    headTilt: lerp(pa.headTilt, pb.headTilt), drop: lerp(pa.drop, pb.drop),
    handsFront: t < 0.5 ? pa.handsFront : pb.handsFront,
    armsFront: t < 0.5 ? pa.armsFront : pb.armsFront,
  };
}

/** Where the head is, in body coordinates, and how far it is turned (degrees). */
export function headPlace(pose: PoseSpec): { at: V; rot: number } {
  const hip: V = [0, HIP_Y + pose.drop];
  return { at: rot([HEAD_C[0], HEAD_C[1] + pose.drop], hip, pose.lean), rot: pose.lean * 0.6 + pose.headTilt };
}

/** The squash after a swap: [sx, sy] about the feet, back to 1 within about 7 frames. */
export function squashAt(frame: number, swapFrame: number): [number, number] {
  const k = frame - swapFrame;
  const amt = k >= 0 && k < 10 ? 0.075 * Math.exp(-k / 2.3) * Math.cos(k * 0.8) : 0;
  return [1 + amt * 0.8, 1 - amt];
}

/** The reaction marks beside the head, in head coordinates. */
export const BeanMarks: React.FC<{ marks: BeanProps["marks"]; frame: number; fps: number; font: string }> = ({ marks, frame, fps, font }) => (
  <>
    {marks.map((m, i) => {
      const tt = frame - m.start;
      if (tt < 0) return null;
      const at = MARK_PLACE[m.type];
      // pop, wiggle for a second, then hold (a mark that never settles repaints its layer every frame)
      const sc = tt >= MARK_SETTLE ? 1 : spring({ frame: tt, fps, config: { stiffness: 320, damping: 15, mass: 0.55 } });
      return (
        <g key={i} transform={`translate(${at.x} ${at.y}) rotate(${at.rot * sc}) scale(${sc})`}>
          <MarkShape type={m.type} t={Math.min(tt, MARK_SETTLE) / fps} font={font} />
        </g>
      );
    })}
  </>
);

export const Bean: React.FC<BeanProps> = (p) => {
  const skin = SKIN[p.tint];
  const pose = blendedPose(p);
  // Snap, squash, hold: between swaps every pixel of the bean holds still.
  const [sx, sy] = squashAt(p.frame, p.swapFrame);
  const s = p.scale * p.enter;

  const hip: V = [0, HIP_Y + pose.drop];
  const up = (q: V): V => rot([q[0], q[1] + pose.drop], hip, pose.lean);
  const lSh = up([-SHOULDER[0], SHOULDER[1]]);
  const rSh = up(SHOULDER);
  const head = up(HEAD_C);
  const [lEl, lH] = ik(lSh, pose.lHand, UA, FA, pose.lBend);
  const [rEl, rH] = ik(rSh, pose.rHand, UA, FA, pose.rBend);
  const lHip: V = [-36, hip[1] + 4], rHip: V = [36, hip[1] + 4];
  const [lKn, lFt] = ik(lHip, [pose.lFoot, -14], TH, SH, 1);
  const [rKn, rFt] = ik(rHip, [pose.rFoot, -14], TH, SH, -1);
  const torso = "M -76,-210 C -92,-300 -82,-420 -44,-466 Q 0,-492 44,-466 C 82,-420 92,-300 76,-210 Q 0,-188 -76,-210 Z";
  const hat = p.accessory === "cap" || p.accessory === "hardhat" || p.accessory === "beanie" || p.accessory === "headset";

  const front = (side: "l" | "r") => (pose.armsFront ?? []).includes(side);
  const arm = (sh: V, el: V, h: V) => <Tube pts={[sh, el, h]} w={30} skin={skin} />;
  const hand = (h: V) => <circle cx={h[0]} cy={h[1]} r={23} fill={skin} stroke={INK} strokeWidth={LINE} />;

  return (
    <g transform={`translate(${p.x} ${p.y}) scale(${s * sx} ${s * sy})`}>
      <ellipse cx={0} cy={6} rx={130} ry={16} fill="#000" opacity={0.13} />
      <Tube pts={[lHip, lKn, lFt]} w={36} skin={skin} />
      <Tube pts={[rHip, rKn, rFt]} w={36} skin={skin} />
      <ellipse cx={lFt[0] - 14} cy={-6} rx={38} ry={17} fill={skin} stroke={INK} strokeWidth={LINE} />
      <ellipse cx={rFt[0] + 14} cy={-6} rx={38} ry={17} fill={skin} stroke={INK} strokeWidth={LINE} />
      {!front("l") && arm(lSh, lEl, lH)}
      {!front("r") && arm(rSh, rEl, rH)}
      {!pose.handsFront && hand(lH)}
      {!pose.handsFront && hand(rH)}
      <g transform={`translate(0 ${pose.drop}) rotate(${pose.lean} ${hip[0]} ${hip[1] - pose.drop})`}>
        <path d={torso} fill={skin} stroke={INK} strokeWidth={LINE} strokeLinejoin="round" />
        {p.accessory === "tie" && <Tie />}
      </g>
      <g transform={`translate(${head[0]} ${head[1]}) rotate(${headPlace(pose).rot})`}>
        <circle cx={-HEAD_R + 4} cy={6} r={22} fill={skin} stroke={INK} strokeWidth={LINE} />
        <circle cx={HEAD_R - 4} cy={6} r={22} fill={skin} stroke={INK} strokeWidth={LINE} />
        <circle cx={0} cy={0} r={HEAD_R} fill={skin} stroke={INK} strokeWidth={LINE} />
        {!hat && <path d="M -22,-117 Q -34,-150 -6,-158 M 2,-119 Q 4,-156 32,-152 M 26,-114 Q 44,-138 66,-128" stroke={INK} strokeWidth={6} fill="none" strokeLinecap="round" />}
        <FaceView face={p.face} look={LOOK_DX[p.look]} blink={p.blink ?? blinkAt(p.frame, p.seed)} skin={skin} uid={p.uid} />
        <HeadAccessory a={p.accessory} />
        <BeanMarks marks={p.marks} frame={p.frame} fps={p.fps} font={p.font} />
      </g>
      {front("l") && arm(lSh, lEl, lH)}
      {front("r") && arm(rSh, rEl, rH)}
      {pose.handsFront && hand(lH)}
      {pose.handsFront && hand(rH)}
    </g>
  );
};

/** Frame coordinates of a body-coordinate point, and back. */
export const toFrame = (x: number, y: number, s: number, q: V): V => [x + q[0] * s, y + q[1] * s];
export const toBody = (x: number, y: number, s: number, q: V): V => [(q[0] - x) / s, (q[1] - y) / s];
