/*
 * The Under the Hood presenter: one house character, drawn in code.
 *
 * An original character (never a real creator's likeness): a young bench
 * technician with short dark hair, amber goggles pushed up on the forehead and
 * a mustard work jacket with a screwdriver in the chest pocket, in a flat
 * cartoon line with a thick dark outline. Drawn waist-up; the frame's bottom
 * edge cuts the body.
 *
 * The look is whole-pose swaps (no limb tween), so a pose is a fixed table of
 * shoulder, elbow and hand points plus a hand shape and a face. The mouth has
 * three shapes and moves only while the narration speaks; it never
 * lip-syncs. The scene never draws this live: sprite.tsx rasterises each
 * distinct (pose, mouth, blink) once and reuses the bitmap.
 *
 * Coordinates: a 440 x 620 body box; the drawing may reach VIEW's margin
 * around it (raised hands, a pointing arm).
 */
import React from "react";
import type { Pose } from "./contract";

export const VIEW = { left: -70, top: -40, width: 580, height: 680 } as const;

const INK = "#15161A";
const SKIN = "#D9A06E";
const SKIN_SHADE = "#C08655";
const HAIR = "#2B211D";
const JACKET = "#E2A93B";
const JACKET_SHADE = "#C48E28";
const SHIRT = "#2E3440";
const AMBER = "#F2B544";
const LINE = 7;

type P = [number, number];
type Hand = "open" | "point" | "fist" | "thumb";
type Face = { eyes: "open" | "wide" | "half"; brows: "neutral" | "up" | "knit" | "tilt"; look: P; mouth: "smile" | "flat" | "o" | "grin" };

interface Arm { shoulder: P; elbow: P; hand: P; shape: Hand }
interface PoseDef { left: Arm; right: Arm; face: Face; lean: number }

const DOWN_L: Arm = { shoulder: [118, 432], elbow: [96, 540], hand: [112, 650], shape: "fist" };
const DOWN_R: Arm = { shoulder: [322, 432], elbow: [344, 540], hand: [328, 650], shape: "fist" };

export const POSE_TABLE: Record<Pose, PoseDef> = {
  idle: { left: DOWN_L, right: DOWN_R, face: { eyes: "open", brows: "neutral", look: [0, 0], mouth: "smile" }, lean: 0 },
  point: {
    left: DOWN_L,
    right: { shoulder: [322, 432], elbow: [400, 352], hand: [372, 238], shape: "point" },
    face: { eyes: "open", brows: "up", look: [-6, -5], mouth: "smile" }, lean: -2,
  },
  present: {
    left: { shoulder: [118, 432], elbow: [40, 470], hand: [-14, 404], shape: "open" },
    right: DOWN_R,
    face: { eyes: "open", brows: "neutral", look: [-7, -3], mouth: "smile" }, lean: -3,
  },
  think: {
    left: DOWN_L,
    right: { shoulder: [322, 432], elbow: [318, 528], hand: [252, 368], shape: "fist" },
    face: { eyes: "half", brows: "knit", look: [6, -7], mouth: "flat" }, lean: 2,
  },
  surprise: {
    left: { shoulder: [118, 432], elbow: [30, 392], hand: [36, 282], shape: "open" },
    right: { shoulder: [322, 432], elbow: [410, 392], hand: [404, 282], shape: "open" },
    face: { eyes: "wide", brows: "up", look: [0, 0], mouth: "o" }, lean: 0,
  },
  hands_on_head: {
    left: { shoulder: [118, 432], elbow: [24, 300], hand: [118, 152], shape: "open" },
    right: { shoulder: [322, 432], elbow: [416, 300], hand: [322, 152], shape: "open" },
    face: { eyes: "wide", brows: "tilt", look: [0, 2], mouth: "o" }, lean: 0,
  },
  thumbs: {
    left: DOWN_L,
    right: { shoulder: [322, 432], elbow: [398, 470], hand: [392, 356], shape: "thumb" },
    face: { eyes: "open", brows: "up", look: [-3, 0], mouth: "grin" }, lean: 0,
  },
  shrug: {
    left: { shoulder: [118, 426], elbow: [44, 494], hand: [18, 408], shape: "open" },
    right: { shoulder: [322, 426], elbow: [396, 494], hand: [422, 408], shape: "open" },
    face: { eyes: "half", brows: "tilt", look: [0, 0], mouth: "flat" }, lean: 0,
  },
  explain: {
    left: { shoulder: [118, 432], elbow: [104, 530], hand: [190, 470], shape: "open" },
    right: DOWN_R,
    face: { eyes: "open", brows: "neutral", look: [-4, -2], mouth: "smile" }, lean: -1,
  },
};

const pts = (p: P[]) => p.map(([x, y]) => `${x},${y}`).join(" ");

const HandShape: React.FC<{ at: P; from: P; shape: Hand }> = ({ at, from, shape }) => {
  const ang = (Math.atan2(at[1] - from[1], at[0] - from[0]) * 180) / Math.PI;
  const finger = (len: number, w: number, rot: number, key: string) => (
    <g key={key} transform={`rotate(${rot})`}>
      <rect x={12} y={-w / 2} width={len} height={w} rx={w / 2} fill={SKIN} stroke={INK} strokeWidth={LINE} />
    </g>
  );
  let fingers: React.ReactNode = null;
  if (shape === "open") fingers = [-36, -12, 12, 36].map((r, i) => finger(44 - Math.abs(r) * 0.15, 22, r, `f${i}`));
  if (shape === "point") fingers = finger(62, 20, 0, "p");
  return (
    <g transform={`translate(${at[0]} ${at[1]}) rotate(${ang})`}>
      {shape === "thumb" ? null : fingers}
      <circle cx={0} cy={0} r={29} fill={SKIN} stroke={INK} strokeWidth={LINE} />
      {shape === "thumb" && (
        <g transform={`rotate(${-ang})`}>
          <rect x={-11} y={-66} width={22} height={50} rx={11} fill={SKIN} stroke={INK} strokeWidth={LINE} />
        </g>
      )}
      {shape !== "open" && <path d="M -6,-14 Q 6,-4 -6,8" fill="none" stroke={SKIN_SHADE} strokeWidth={4} strokeLinecap="round" />}
    </g>
  );
};

const ArmShape: React.FC<{ arm: Arm }> = ({ arm }) => (
  <g>
    <polyline points={pts([arm.shoulder, arm.elbow, arm.hand])} fill="none" stroke={INK} strokeWidth={56} strokeLinecap="round" strokeLinejoin="round" />
    <polyline points={pts([arm.shoulder, arm.elbow, arm.hand])} fill="none" stroke={JACKET} strokeWidth={42} strokeLinecap="round" strokeLinejoin="round" />
    <HandShape at={arm.hand} from={arm.elbow} shape={arm.shape} />
  </g>
);

const Eyes: React.FC<{ face: Face; blink: boolean }> = ({ face, blink }) => {
  const [lx, ly] = face.look;
  const ry = face.eyes === "wide" ? 25 : face.eyes === "half" ? 13 : 20;
  return (
    <g>
      {[178, 262].map((cx, i) =>
        blink ? (
          <path key={i} d={`M ${cx - 17},264 Q ${cx},272 ${cx + 17},264`} fill="none" stroke={INK} strokeWidth={6} strokeLinecap="round" />
        ) : (
          <g key={i}>
            <ellipse cx={cx} cy={262} rx={17} ry={ry} fill="#FFFFFF" stroke={INK} strokeWidth={5} />
            <circle cx={cx + lx} cy={264 + ly} r={face.eyes === "wide" ? 7 : 9} fill={INK} />
            {face.eyes === "half" && <rect x={cx - 19} y={262 - ry - 2} width={38} height={ry - 2} fill={SKIN} stroke="none" />}
            {face.eyes === "half" && <line x1={cx - 18} y1={262 - 3} x2={cx + 18} y2={262 - 3} stroke={INK} strokeWidth={5} strokeLinecap="round" />}
          </g>
        ),
      )}
    </g>
  );
};

const BROWS: Record<Face["brows"], [P, P, P, P]> = {
  neutral: [[160, 226], [194, 224], [246, 224], [280, 226]],
  up: [[160, 214], [194, 208], [246, 208], [280, 214]],
  knit: [[160, 222], [196, 230], [244, 230], [280, 222]],
  tilt: [[160, 226], [196, 212], [244, 212], [280, 226]],
};

const Mouth: React.FC<{ face: Face; open: number }> = ({ face, open }) => {
  const cx = 220, cy = 322;
  if (face.mouth === "o" || open === 2) {
    const r = face.mouth === "o" ? 22 : 19;
    return <ellipse cx={cx} cy={cy + 2} rx={r * 0.8} ry={r} fill="#5A1E22" stroke={INK} strokeWidth={6} />;
  }
  if (open === 1) {
    return <path d={`M ${cx - 30},${cy - 6} Q ${cx},${cy + 34} ${cx + 30},${cy - 6} Z`} fill="#5A1E22" stroke={INK} strokeWidth={6} strokeLinejoin="round" />;
  }
  if (face.mouth === "flat") return <line x1={cx - 18} y1={cy} x2={cx + 18} y2={cy} stroke={INK} strokeWidth={6} strokeLinecap="round" />;
  if (face.mouth === "grin") {
    return (
      <g>
        <path d={`M ${cx - 32},${cy - 8} Q ${cx},${cy + 30} ${cx + 32},${cy - 8} Z`} fill="#FFFFFF" stroke={INK} strokeWidth={6} strokeLinejoin="round" />
        <line x1={cx - 28} y1={cy - 2} x2={cx + 28} y2={cy - 2} stroke={INK} strokeWidth={3} />
      </g>
    );
  }
  return <path d={`M ${cx - 26},${cy - 6} Q ${cx},${cy + 18} ${cx + 26},${cy - 6}`} fill="none" stroke={INK} strokeWidth={6} strokeLinecap="round" />;
};

/** The presenter in `pose`, with mouth shape 0 (rest), 1 (open) or 2 (round), eyes shut when `blink`. */
export const Presenter: React.FC<{ pose: Pose; mouth: 0 | 1 | 2; blink: boolean }> = ({ pose, mouth, blink }) => {
  const def = POSE_TABLE[pose] ?? POSE_TABLE.idle;
  const { face } = def;
  const raised = (a: Arm) => a.hand[1] < 420;
  const behind = (a: Arm) => !raised(a);
  return (
    <g>
      {/* body */}
      <path d="M 70,680 L 92,470 Q 100,412 160,404 L 280,404 Q 340,412 348,470 L 370,680 Z" fill={JACKET} stroke={INK} strokeWidth={LINE} strokeLinejoin="round" />
      <path d="M 176,404 L 220,480 L 264,404 Z" fill={SHIRT} stroke={INK} strokeWidth={LINE} strokeLinejoin="round" />
      <path d="M 176,404 L 206,500 L 186,520 L 150,410 Z" fill={JACKET_SHADE} stroke={INK} strokeWidth={LINE} strokeLinejoin="round" />
      <path d="M 264,404 L 234,500 L 254,520 L 290,410 Z" fill={JACKET_SHADE} stroke={INK} strokeWidth={LINE} strokeLinejoin="round" />
      <line x1={220} y1={520} x2={220} y2={680} stroke={INK} strokeWidth={5} />
      {/* chest pocket with a screwdriver */}
      <rect x={258} y={552} width={58} height={50} rx={6} fill={JACKET_SHADE} stroke={INK} strokeWidth={5} />
      <rect x={278} y={508} width={14} height={50} rx={5} fill="#D9473B" stroke={INK} strokeWidth={5} />
      {/* arms that hang beside the body are drawn before the head */}
      {behind(def.left) && <ArmShape arm={def.left} />}
      {behind(def.right) && <ArmShape arm={def.right} />}
      <g transform={`rotate(${def.lean} 220 400)`}>
        {/* neck and head */}
        <rect x={194} y={340} width={52} height={70} fill={SKIN_SHADE} stroke={INK} strokeWidth={LINE} />
        <circle cx={112} cy={268} r={22} fill={SKIN} stroke={INK} strokeWidth={LINE} />
        <circle cx={328} cy={268} r={22} fill={SKIN} stroke={INK} strokeWidth={LINE} />
        <ellipse cx={220} cy={258} rx={106} ry={116} fill={SKIN} stroke={INK} strokeWidth={LINE} />
        {/* hair */}
        <path d="M 116,236 Q 112,138 214,132 Q 318,130 326,232 Q 300,180 250,176 Q 188,170 160,196 Q 132,210 116,236 Z" fill={HAIR} stroke={INK} strokeWidth={LINE} strokeLinejoin="round" />
        {/* goggles pushed up on the forehead */}
        <path d="M 118,196 Q 220,168 322,196" fill="none" stroke={INK} strokeWidth={16} strokeLinecap="round" />
        {[180, 260].map((cx) => (
          <g key={cx}>
            <circle cx={cx} cy={180} r={30} fill={INK} />
            <circle cx={cx} cy={180} r={21} fill={AMBER} />
            <path d={`M ${cx - 10},${170} Q ${cx - 4},${164} ${cx + 4},${166}`} fill="none" stroke="#FFF3D6" strokeWidth={5} strokeLinecap="round" />
          </g>
        ))}
        {BROWS[face.brows].reduce<React.ReactNode[]>((acc, _, i, b) => {
          if (i % 2 === 0) acc.push(<line key={i} x1={b[i][0]} y1={b[i][1]} x2={b[i + 1][0]} y2={b[i + 1][1]} stroke={INK} strokeWidth={8} strokeLinecap="round" />);
          return acc;
        }, [])}
        <Eyes face={face} blink={blink} />
        <path d="M 218,276 Q 210,298 224,300" fill="none" stroke={SKIN_SHADE} strokeWidth={5} strokeLinecap="round" />
        <circle cx={150} cy={300} r={14} fill="#E58C7A" opacity={0.5} />
        <circle cx={290} cy={300} r={14} fill="#E58C7A" opacity={0.5} />
        <Mouth face={face} open={mouth} />
      </g>
      {/* raised arms go over the head */}
      {raised(def.left) && <ArmShape arm={def.left} />}
      {raised(def.right) && <ArmShape arm={def.right} />}
    </g>
  );
};

/** A standalone SVG of the presenter, sized to VIEW, for rasterising. */
export const PresenterSvg: React.FC<{ pose: Pose; mouth: 0 | 1 | 2; blink: boolean; scale?: number }> = ({ pose, mouth, blink, scale = 1 }) => (
  <svg xmlns="http://www.w3.org/2000/svg" width={VIEW.width * scale} height={VIEW.height * scale} viewBox={`${VIEW.left} ${VIEW.top} ${VIEW.width} ${VIEW.height}`}>
    <Presenter pose={pose} mouth={mouth} blink={blink} />
  </svg>
);
