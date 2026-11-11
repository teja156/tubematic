/*
 * The guide: a small field mouse in a waistcoat who walks through the book
 * beside the story. It never speaks; it walks on twos (each drawing held for
 * two frames), points at what the narration names, looks up, thinks, starts
 * and hops.
 *
 * Drawn facing right with its feet at the origin, in a 360 x 380 box. Facing
 * left is the same bitmap mirrored. Each pose is one drawing, cached as a
 * bitmap by ./bitmap.tsx; the scene only moves it.
 */
import React from "react";
import type { Drawing } from "./bitmap";
import { FloorShadow, Sh, circle, ellipse } from "./ink";
import { COAT_COLORS, GOLD, INK, IVORY, MOUSE, PINK } from "./palette";

export const GUIDE_POSES = ["stand", "walk1", "walk2", "walk3", "walk4", "point", "look", "think", "surprised", "hop"] as const;
export type GuidePose = (typeof GUIDE_POSES)[number];
export type GuideCoat = keyof typeof COAT_COLORS;

/** The box every guide drawing fits in, and where its feet are in that box. */
export const GUIDE_BOX = { width: 360, height: 380, footX: 170, footY: 360 } as const;

type Arm = [upper: number, lower: number]; // degrees from straight down; positive swings forward (to the right)
type Pose = {
  legs: [back: number, front: number]; // hip angles, degrees from straight down, positive forward
  lift: [number, number]; // how far each foot is lifted (px)
  bob: number; // body offset (negative = up)
  lean: number; // body lean in degrees
  far: Arm;
  near: Arm;
  head: number; // head tilt in degrees (negative = up)
  ears: number; // ear scale
  eye: "dot" | "wide" | "shut" | "up";
};

const STAND: Pose = { legs: [-4, 4], lift: [0, 0], bob: 0, lean: 0, far: [8, 20], near: [4, 10], head: 0, ears: 1, eye: "dot" };

const POSES: Record<GuidePose, Pose> = {
  stand: STAND,
  // a four-drawing walk cycle, each held for two frames
  walk1: { ...STAND, legs: [-24, 22], lift: [0, 0], bob: 2, lean: 3, far: [22, 20], near: [-20, 10] },
  walk2: { ...STAND, legs: [-6, 8], lift: [0, 14], bob: -6, lean: 3, far: [8, 18], near: [-6, 12] },
  walk3: { ...STAND, legs: [22, -24], lift: [0, 0], bob: 2, lean: 3, far: [-20, 10], near: [22, 20] },
  walk4: { ...STAND, legs: [8, -6], lift: [14, 0], bob: -6, lean: 3, far: [-6, 12], near: [8, 18] },
  point: { ...STAND, near: [104, -8], far: [6, 22], head: -6 },
  look: { ...STAND, near: [-10, 40], far: [10, 30], head: -22, eye: "up", lean: -4 },
  think: { ...STAND, near: [83, 89], far: [14, 22], head: 10, eye: "shut" },
  surprised: { ...STAND, near: [-135, -15], far: [-160, 10], head: -8, ears: 1.16, eye: "wide", lean: -5, bob: -4 },
  hop: { legs: [-30, 40], lift: [10, 10], bob: -10, lean: 6, far: [120, 30], near: [-120, -30], head: -8, ears: 1.1, eye: "wide" },
};

const FUR = MOUSE;
const BELLY = "#CBC2B4";
const DARK = "#1C140E";

/** A two-segment limb drawn as a dark outline tube with a fur-coloured core. */
function limb(x: number, y: number, a: Arm, l1: number, l2: number) {
  const r1 = (a[0] * Math.PI) / 180;
  const ex = x + l1 * Math.sin(r1), ey = y + l1 * Math.cos(r1);
  const r2 = ((a[0] + a[1]) * Math.PI) / 180;
  const hx = ex + l2 * Math.sin(r2), hy = ey + l2 * Math.cos(r2);
  return { ex, ey, hx, hy };
}

const Tube: React.FC<{ pts: [number, number][]; w: number; color: string }> = ({ pts, w, color }) => {
  const d = `M${pts.map(([x, y]) => `${x} ${y}`).join("L")}`;
  return (
    <g>
      <path d={d} fill="none" stroke={INK} strokeWidth={w + 6} strokeLinecap="round" strokeLinejoin="round" />
      <path d={d} fill="none" stroke={color} strokeWidth={w} strokeLinecap="round" strokeLinejoin="round" />
    </g>
  );
};

const ArmView: React.FC<{ x: number; y: number; a: Arm; color: string }> = ({ x, y, a, color }) => {
  const { ex, ey, hx, hy } = limb(x, y, a, 34, 30);
  return (
    <g>
      <Tube pts={[[x, y], [ex, ey], [hx, hy]]} w={11} color={color} />
      <path d={circle(hx, hy, 7.5)} fill={PINK} stroke={INK} strokeWidth={2.5} />
    </g>
  );
};

const LegView: React.FC<{ x: number; y: number; a: number; lift: number; color: string }> = ({ x, y, a, lift, color }) => {
  const r = (a * Math.PI) / 180;
  const L = 46 - lift * 0.3;
  const fx = x + L * Math.sin(r), fy = Math.min(-2, y + L * Math.cos(r) - lift);
  return (
    <g>
      <Tube pts={[[x, y], [fx, fy]]} w={12} color={color} />
      <path d={`M${fx - 6} ${fy + 1}h22`} stroke={INK} strokeWidth={10} strokeLinecap="round" />
      <path d={`M${fx - 6} ${fy + 1}h22`} stroke={PINK} strokeWidth={4} strokeLinecap="round" />
    </g>
  );
};

/** The mouse in a pose, feet at (0, 0), facing right. */
export const GuideFigure: React.FC<{ pose: GuidePose; coat: GuideCoat }> = ({ pose, coat }) => {
  const p = POSES[pose];
  const vest = COAT_COLORS[coat];
  const hipY = -44;
  return (
    <g>
      <FloorShadow cx={4} w={150} />
      <g transform={`translate(0 ${p.bob}) rotate(${p.lean} 0 ${hipY})`}>
        {/* tail */}
        <path d={`M-30 ${hipY - 16} C-90 ${hipY - 4} -118 ${hipY + 30} -142 ${hipY - 10} S-150 ${hipY - 70} -124 ${hipY - 74}`}
          fill="none" stroke={INK} strokeWidth={6} strokeLinecap="round" />
        <path d={`M-30 ${hipY - 16} C-90 ${hipY - 4} -118 ${hipY + 30} -142 ${hipY - 10} S-150 ${hipY - 70} -124 ${hipY - 74}`}
          fill="none" stroke={PINK} strokeWidth={2.2} strokeLinecap="round" />
        {/* far leg and arm, darker */}
        <LegView x={-12} y={hipY} a={p.legs[0]} lift={p.lift[0]} color="#8E8578" />
        <ArmView x={-4} y={hipY - 92} a={p.far} color="#8E8578" />
        {/* body: a pear with a pale belly */}
        <Sh d={`M-44 ${hipY} Q-58 ${hipY - 60} -36 ${hipY - 104} Q-10 ${hipY - 128} 22 ${hipY - 112} Q48 ${hipY - 90} 40 ${hipY - 30} Q34 ${hipY + 4} 0 ${hipY + 6} Q-36 ${hipY + 6} -44 ${hipY}Z`}
          fill={FUR} penOp={0.16} sw={3.5} />
        <Sh d={ellipse(16, hipY - 34, 22, 34)} fill={BELLY} pen="none" sw={0} />
        {/* waistcoat: an open vest over the chest with two brass buttons */}
        <Sh d={`M-34 ${hipY - 100} Q-8 ${hipY - 122} 22 ${hipY - 110} L30 ${hipY - 62} L14 ${hipY - 20} Q-20 ${hipY - 8} -42 ${hipY - 22} Q-52 ${hipY - 62} -34 ${hipY - 100}Z`}
          fill={vest} pen="l" penOp={0.22} sw={3} />
        <path d={`M22 ${hipY - 110} L4 ${hipY - 66} L14 ${hipY - 20}`} fill="none" stroke={INK} strokeWidth={2.5} strokeLinejoin="round" />
        <path d={circle(10, hipY - 74, 4.5)} fill={GOLD} stroke={INK} strokeWidth={1.6} />
        <path d={circle(10, hipY - 50, 4.5)} fill={GOLD} stroke={INK} strokeWidth={1.6} />
        <path d={`M-30 ${hipY - 48} q14 10 30 2`} fill="none" stroke={GOLD} strokeWidth={2.4} />
        {/* near leg */}
        <LegView x={16} y={hipY} a={p.legs[1]} lift={p.lift[1]} color={FUR} />
        {/* head, tilted about the neck */}
        <g transform={`rotate(${p.head} 8 ${hipY - 112})`}>
          <g transform={`translate(-10 ${hipY - 196}) scale(${p.ears}) translate(10 ${-(hipY - 196)})`}>
            <path d={circle(-10, hipY - 196, 26)} fill={FUR} stroke={INK} strokeWidth={3.5} />
          </g>
          <Sh d={`M-24 ${hipY - 128} Q-36 ${hipY - 172} -2 ${hipY - 186} Q34 ${hipY - 196} 54 ${hipY - 160} L92 ${hipY - 138} Q100 ${hipY - 130} 88 ${hipY - 126} L46 ${hipY - 118} Q8 ${hipY - 108} -24 ${hipY - 128}Z`}
            fill={FUR} penOp={0.16} sw={3.5} />
          <path d={circle(91, hipY - 134, 7)} fill={PINK} stroke={INK} strokeWidth={2.2} />
          {p.eye === "dot" && (
            <g>
              <path d={circle(38, hipY - 158, 6.5)} fill={DARK} />
              <path d={circle(40, hipY - 160, 1.9)} fill={IVORY} />
            </g>
          )}
          {p.eye === "up" && (
            <g>
              <path d={circle(40, hipY - 162, 6.5)} fill={DARK} />
              <path d={circle(42, hipY - 166, 1.9)} fill={IVORY} />
            </g>
          )}
          {p.eye === "wide" && (
            <g>
              <path d={circle(38, hipY - 158, 10)} fill={IVORY} stroke={INK} strokeWidth={2.4} />
              <path d={circle(40, hipY - 158, 5)} fill={DARK} />
            </g>
          )}
          {p.eye === "shut" && <path d={`M30 ${hipY - 156} q8 6 16 0`} fill="none" stroke={DARK} strokeWidth={3.5} strokeLinecap="round" />}
          <path d={`M78 ${hipY - 128} L118 ${hipY - 138} M78 ${hipY - 124} L118 ${hipY - 122}`} stroke={INK} strokeWidth={1.6} />
          <g transform={`translate(-2 ${hipY - 188}) scale(${p.ears}) translate(2 ${-(hipY - 188)})`}>
            <path d={circle(-2, hipY - 192, 32)} fill={FUR} stroke={INK} strokeWidth={3.5} />
            <path d={circle(-1, hipY - 191, 19)} fill={PINK} />
          </g>
        </g>
        {/* near arm over everything */}
        <ArmView x={2} y={hipY - 96} a={p.near} color={FUR} />
      </g>
    </g>
  );
};

/** The guide in a pose as a cached drawing (its feet at GUIDE_BOX.footX/footY). */
export function guideDrawing(pose: GuidePose, coat: GuideCoat): Drawing {
  return {
    key: `guide:${pose}:${coat}`,
    width: GUIDE_BOX.width,
    height: GUIDE_BOX.height,
    render: () => (
      <g transform={`translate(${GUIDE_BOX.footX} ${GUIDE_BOX.footY})`}>
        <GuideFigure pose={pose} coat={coat} />
      </g>
    ),
  };
}
