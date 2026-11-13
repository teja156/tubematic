/*
 * The Mid-century How-To presenter: one geometric figure in a 1950s
 * classroom-film look, built once and posed by data. His body holds; his
 * front arm, glove, eye, brow and mouth act. He never talks: the mouth shows
 * the face, never the words (the narrator is off screen).
 *
 * Drawn facing right with his feet at (0, 0); on the right of the stage the
 * scene mirrors the bitmap. Every distinct look is drawn once into a cached
 * sprite (../characterKit/sprite.tsx), so the drawing here is never on the
 * per-frame path.
 */
import React from "react";
import { ik, mix, smooth, tubeP, type Pt } from "../characterKit/geometry";
import type { SpriteBox } from "../characterKit/sprite";
import { CORAL, Cel, CREAM, GLOVE, INK, MUSTARD, NAVY, SKIN, TEAL, BLUE, ellP, polyP, rectP } from "./cel";
import { GEOMETRY, type Face, type Hair, type Outfit, type Pose } from "./contract";

export const OUTFIT_COLORS: Record<Outfit, string> = { coral: CORAL, teal: TEAL, mustard: MUSTARD, blue: BLUE };
export const HAIR_COLORS: Record<Hair, string> = { dark: "#3A2B23", red: "#A8472A", blond: "#D9A441", grey: "#8E8A84" };

export type GlovePose = "open" | "point" | "hold" | "thumb" | "fist";
export type ArmState = { wrist: Pt; glove: GlovePose; angle: number };
export type BackArm = "hang" | "hip" | "up";

/** Every pixel the presenter can reach, from his feet: a reach to the edge of GEOMETRY.armReach included. */
export const PRESENTER_BOX: SpriteBox = { left: -420, top: -1060, width: 960, height: 1090 };

/**
 * The box of one look: his body and back arm, grown to take in the front hand
 * wherever it is. A bitmap's cost per frame grows with its area on the CPU
 * renderer, and the full reach is three times the area of a standing pose.
 */
export function presenterBoxFor(arm: ArmState, back: BackArm): SpriteBox {
  let l = back === "up" ? -300 : -170, r = 180, t = -880, b = 30;
  const [wx, wy] = arm.wrist;
  l = Math.min(l, wx - 140);
  r = Math.max(r, wx + 140);
  t = Math.min(t, wy - 140);
  b = Math.max(b, wy + 140);
  return { left: Math.floor(l / 20) * 20, top: Math.floor(t / 20) * 20, width: Math.ceil((r - l) / 20) * 20 + 20, height: Math.ceil((b - t) / 20) * 20 + 20 };
}

const S: Pt = [GEOMETRY.shoulderDx, GEOMETRY.shoulderDy];
const UPPER = 172;
const LOWER = 162;
const HAND = 96;

/** The wrist and glove that put a pointing fingertip on `tip` (presenter coordinates). */
export function armToward(tip: Pt, glove: GlovePose = "point"): ArmState {
  const a = Math.atan2(tip[1] - S[1], tip[0] - S[0]);
  const reach = Math.min(Math.hypot(tip[0] - S[0], tip[1] - S[1]), UPPER + LOWER + HAND - 6);
  const t: Pt = [S[0] + Math.cos(a) * reach, S[1] + Math.sin(a) * reach];
  return { wrist: [t[0] - Math.cos(a) * HAND, t[1] - Math.sin(a) * HAND], glove, angle: (a * 180) / Math.PI };
}

/** The front arm of each pose; `aim` (presenter coordinates) steers the aiming poses. */
export function poseArm(pose: Pose, aim: Pt | null, waveT = -1): { arm: ArmState; back: BackArm } {
  switch (pose) {
    case "present":
      return aim ? { arm: { ...armToward(aim, "open"), glove: "open" }, back: "hang" } : { arm: { wrist: [300, -560], glove: "open", angle: -10 }, back: "hang" };
    case "point":
      return { arm: armToward(aim ?? [440, -660], "point"), back: "hang" };
    case "thumbsup":
      return { arm: { wrist: [150, -560], glove: "thumb", angle: 0 }, back: "hang" };
    case "wave": {
      const swing = waveT >= 0 && waveT < 16 ? (Math.floor(waveT / 4) % 2 ? 12 : -12) : 0;
      return { arm: { wrist: [210, -790], glove: "open", angle: -80 + swing }, back: "hang" };
    }
    case "think":
      return { arm: { wrist: [92, -610], glove: "fist", angle: -70 }, back: "hip" };
    case "shrug":
      return { arm: { wrist: [240, -500], glove: "open", angle: -25 }, back: "up" };
    case "hips":
      return { arm: { wrist: [100, -420], glove: "fist", angle: 150 }, back: "hip" };
    case "stand":
    default:
      return { arm: { wrist: [70, -350], glove: "open", angle: 96 }, back: "hang" };
  }
}

/** A blend between two arm states, t from 0 to 1. */
export function blendArm(a: ArmState, b: ArmState, t: number): ArmState {
  if (t >= 1) return b;
  if (t <= 0) return a;
  return {
    wrist: [a.wrist[0] + (b.wrist[0] - a.wrist[0]) * t, a.wrist[1] + (b.wrist[1] - a.wrist[1]) * t],
    glove: t < 0.5 ? a.glove : b.glove,
    angle: a.angle + (b.angle - a.angle) * t,
  };
}

/** Four-finger cartoon glove. Origin = wrist, pointing along +x, rotated by `angle` degrees. */
export const Glove: React.FC<{ x: number; y: number; angle: number; pose: GlovePose; phase: number; seed: number; flip?: boolean; sc?: number }> = ({
  x, y, angle, pose, phase, seed, flip, sc = 1,
}) => {
  const parts: string[] = [];
  if (pose === "point") {
    parts.push(tubeP([[52, -4], [90, -4]], 19), ellP(36, 0, 27, 25), ellP(50, 14, 12, 10), tubeP([[30, -20], [48, -26]], 15));
  } else if (pose === "open") {
    parts.push(tubeP([[40, -14], [82, -30]], 18), tubeP([[44, -2], [90, -2]], 18), tubeP([[40, 12], [82, 26]], 18), ellP(34, 0, 27, 25), tubeP([[26, -18], [36, -48]], 16));
  } else if (pose === "thumb") {
    parts.push(ellP(38, 4, 30, 28), tubeP([[24, -14], [30, -66]], 20), tubeP([[50, -18], [70, -14]], 14));
  } else if (pose === "fist") {
    parts.push(ellP(36, 0, 30, 28), tubeP([[22, -20], [44, -26]], 14));
  } else {
    parts.push(ellP(34, 0, 27, 25), tubeP([[34, -14], [62, -34]], 16));
  }
  return (
    <g transform={`translate(${x} ${y}) rotate(${angle}) scale(${sc} ${flip ? -sc : sc})`}>
      <Cel d={rectP(-6, -22, 20, 44, 8)} fill={GLOVE} phase={phase} seed={seed} sw={4} broken={false} />
      {parts.map((d, i) => (
        <Cel key={i} d={d} fill={GLOVE} phase={phase} seed={seed + i + 1} sw={4} broken={false} />
      ))}
      {(pose === "open" || pose === "point") && (
        <g stroke={INK} strokeWidth={3} strokeLinecap="round" opacity={0.8}>
          <line x1={22} y1={-8} x2={30} y2={-8} />
          <line x1={22} y1={2} x2={30} y2={2} />
        </g>
      )}
    </g>
  );
};

export type PresenterLook = {
  arm: ArmState;
  back: BackArm;
  face: Face;
  blink: boolean;
  /** Eye shift toward what he looks at, in pixels. */
  look: Pt;
  outfit: Outfit;
  hair: Hair;
  phase: number;
};

/** Everything that changes his drawing, as a sprite key. */
export function presenterKey(l: PresenterLook): string {
  const r = (v: number) => Math.round(v / 2) * 2;
  return [
    "mc-presenter", r(l.arm.wrist[0]), r(l.arm.wrist[1]), l.arm.glove, Math.round(l.arm.angle), l.back, l.face,
    l.blink ? 1 : 0, Math.round(l.look[0]), Math.round(l.look[1]), l.outfit, l.hair, l.phase,
  ].join("|");
}

function FaceParts({ face, blink, look }: { face: Face; blink: boolean; look: Pt }) {
  const ex = 44 + look[0];
  const ey = -722 + look[1];
  const closed = blink || face === "proud";
  const browLift = face === "surprised" ? 12 : face === "worried" ? 6 : 0;
  const browTilt = face === "worried" ? 6 : 0;
  const eye = closed ? (
    <path d={`M${ex - 9} ${ey + 2} Q${ex} ${face === "proud" && !blink ? ey - 8 : ey + 8} ${ex + 9} ${ey + 2}`} stroke={INK} strokeWidth={4.5} fill="none" strokeLinecap="round" />
  ) : (
    <ellipse cx={ex} cy={ey} rx={face === "surprised" ? 9.5 : 7.5} ry={face === "surprised" ? 13 : 10.5} fill={INK} />
  );
  let mouth: React.ReactNode;
  if (face === "grin") {
    mouth = (
      <g>
        <path d="M44 -684 Q63 -646 82 -686 Z" fill={INK} />
        <path d="M54 -668 Q63 -656 72 -670 Z" fill={CORAL} />
      </g>
    );
  } else if (face === "surprised") {
    mouth = <ellipse cx={62} cy={-676} rx={9} ry={12} fill={INK} />;
  } else if (face === "worried") {
    mouth = <path d="M46 -676 Q54 -684 62 -676 Q70 -668 78 -678" stroke={INK} strokeWidth={4.5} fill="none" strokeLinecap="round" />;
  } else {
    const curve = face === "neutral" ? -676 : -664;
    mouth = <path d={`M46 -682 Q62 ${curve} 78 -684`} stroke={INK} strokeWidth={4.5} fill="none" strokeLinecap="round" />;
  }
  return (
    <g>
      {eye}
      <path d={`M30 ${-748 - browLift + browTilt} Q44 ${-756 - browLift} 58 ${-750 - browLift - browTilt}`} stroke={INK} strokeWidth={5} fill="none" strokeLinecap="round" />
      {mouth}
    </g>
  );
}

function BackArmParts({ back, outfit, phase }: { back: BackArm; outfit: string; phase: number }) {
  const sleeve = mix(outfit, INK, 0.18);
  if (back === "hip") {
    return (
      <g>
        <Cel d={tubeP(smooth([[-58, -575], [-120, -480], [-70, -410]], 3), 40)} fill={sleeve} phase={phase} seed={21} />
        <Glove x={-70} y={-410} angle={20} pose="fist" phase={phase} seed={70} />
      </g>
    );
  }
  if (back === "up") {
    return (
      <g>
        <Cel d={tubeP(smooth([[-58, -575], [-150, -540], [-210, -505]], 3), 40)} fill={sleeve} phase={phase} seed={21} />
        <Glove x={-210} y={-505} angle={200} pose="open" phase={phase} seed={70} flip />
      </g>
    );
  }
  return (
    <g>
      <Cel d={tubeP(smooth([[-58, -575], [-84, -455], [-76, -350]], 3), 40)} fill={sleeve} phase={phase} seed={21} />
      <Glove x={-76} y={-350} angle={96} pose="open" phase={phase} seed={70} />
    </g>
  );
}

/** The presenter, feet at (0, 0), facing right. */
export const Presenter: React.FC<PresenterLook> = ({ arm, back, face, blink, look, outfit, hair, phase }) => {
  const shirt = OUTFIT_COLORS[outfit];
  const hairC = HAIR_COLORS[hair];
  const E = ik(S, arm.wrist, UPPER, LOWER);
  const sleeve = tubeP(smooth([S, E, arm.wrist], 3), 42);
  return (
    <g>
      <ellipse cx={10} cy={4} rx={140} ry={16} fill={INK} opacity={0.18} />
      <BackArmParts back={back} outfit={shirt} phase={phase} />
      <Cel d={polyP([[-60, -372], [-12, -372], [-18, -40], [-58, -40]])} fill={NAVY} phase={phase} seed={22} />
      <Cel d={polyP([[-8, -372], [42, -372], [50, -40], [6, -40]])} fill={NAVY} phase={phase} seed={23} />
      <Cel d={ellP(-30, -24, 46, 20)} fill={INK} phase={phase} seed={24} broken={false} />
      <Cel d={ellP(40, -22, 50, 21)} fill={INK} phase={phase} seed={25} broken={false} />
      <Cel d="M-72 -598 Q-20 -626 62 -606 L82 -580 L66 -362 L-68 -362 L-86 -576 Z" fill={shirt} phase={phase} seed={26} />
      <path d="M-30 -604 Q8 -588 40 -604" stroke={INK} strokeWidth={4} fill="none" />
      <Cel d={rectP(-70, -392, 138, 30, 4)} fill={outfit === "mustard" ? CORAL : MUSTARD} phase={phase} seed={27} broken={false} />
      <Cel d={rectP(-12, -396, 30, 38, 6)} fill={CREAM} phase={phase} seed={28} broken={false} sw={3.5} />
      <Cel d={rectP(-2, -650, 38, 52, 6)} fill={SKIN} phase={phase} seed={29} broken={false} />
      <Cel d={ellP(18, -714, 60, 72)} fill={SKIN} phase={phase} seed={30} />
      <Cel
        d="M64 -750 C52 -804 -32 -810 -56 -748 C-64 -716 -66 -684 -58 -662 Q-42 -648 -24 -660 C-18 -690 -12 -716 6 -734 C26 -746 46 -748 64 -750 Z"
        fill={hairC} phase={phase} seed={31}
      />
      <path d="M-44 -760 Q8 -812 60 -772" stroke={mix(hairC, CREAM, 0.35)} strokeWidth={13} fill="none" strokeLinecap="round" />
      <Cel d={ellP(-4, -704, 12, 17)} fill={SKIN} phase={phase} seed={32} broken={false} sw={3.5} />
      <Cel d="M70 -730 L132 -706 Q124 -694 72 -696 Z" fill={SKIN} phase={phase} seed={33} broken={false} />
      <circle cx={42} cy={-690} r={13} fill={CORAL} opacity={0.35} />
      <FaceParts face={face} blink={blink} look={look} />
      <Cel d={sleeve} fill={shirt} phase={phase} seed={40} />
      <Glove x={arm.wrist[0]} y={arm.wrist[1]} angle={arm.angle} pose={arm.glove} phase={phase} seed={50} />
    </g>
  );
};

/** The rubber-hose arm that presses from the frame's edge when the presenter is not in the shot or cannot reach. */
export const HoseArm: React.FC<{ from: Pt; tip: Pt; phase: number; outfit: Outfit }> = ({ from, tip, phase, outfit }) => {
  const a = Math.atan2(tip[1] - from[1], tip[0] - from[0]);
  const GS = 1.4;
  const wrist: Pt = [tip[0] - Math.cos(a) * HAND * GS, tip[1] - Math.sin(a) * HAND * GS];
  const mid: Pt = [(from[0] + wrist[0]) / 2, (from[1] + wrist[1]) / 2 + 60];
  return (
    <g>
      <Cel d={tubeP(smooth([from, mid, wrist], 4), 56)} fill={OUTFIT_COLORS[outfit]} phase={phase} seed={150} sw={5} />
      <Glove x={wrist[0]} y={wrist[1]} angle={(a * 180) / Math.PI} pose="point" phase={phase} seed={152} sc={GS} />
    </g>
  );
};
