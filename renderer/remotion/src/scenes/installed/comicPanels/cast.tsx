/*
 * The Comic Panels cast, framed from the waist up as comic panels frame people:
 * - the house hero: a big round head, spot-black spiky hair, halftone cheeks;
 * - invented people, built from knobs (hair, outfit, skin), never a likeness
 *   of anyone real;
 * - the villain: a hooded silhouette with a grin, for an attacker or a threat.
 * The bust's bottom centre is (0, 0); it reaches up to ACTOR.h. Every look is
 * drawn once into a cached sprite (../characterKit/sprite.tsx); a pop, a
 * shake or a flip is a transform on the bitmap.
 */
import React from "react";
import type { SpriteBox } from "../characterKit/sprite";
import { ACTOR, type CastKind, type Face, type Pose } from "./contract";
import { BLUE, CYAN, Dots, GREEN, GREY, INK, MAG, RED, WHITE, YEL } from "./ink";

export const OUTFIT_COLORS = { blue: CYAN, red: RED, green: GREEN, yellow: YEL, purple: "#8a5cd0", grey: GREY } as const;
export const SKIN_COLORS = { light: "#fde3cf", tan: "#e8b98f", brown: "#b07a52", dark: "#6f4a32" } as const;

export type BustLook = {
  kind: CastKind;
  hair: string;
  outfit: keyof typeof OUTFIT_COLORS;
  skin: keyof typeof SKIN_COLORS;
  pose: Pose;
  face: Face;
  blink: boolean;
};

export function bustKey(l: BustLook): string {
  return ["cp-bust", l.kind, l.hair, l.outfit, l.skin, l.pose, l.face, l.blink ? 1 : 0].join("|");
}

/** Every pixel a bust can reach, from its bottom centre: raised hands and spiky hair included. */
export const BUST_BOX: SpriteBox = { left: -ACTOR.w / 2 - 60, top: -ACTOR.h - 70, width: ACTOR.w + 120, height: ACTOR.h + 74 };

// Head centre and radii, relative to the bust's bottom centre.
const HX = 0, HY = -190, RX = 92, RY = 102;

function Hair({ hair, kind }: { hair: string; kind: CastKind }) {
  if (kind === "hero" || hair === "spiky") {
    return <path d="M -86 -224 C -96 -270, -60 -300, -24 -296 L -14 -318 L 2 -298 L 22 -322 L 32 -298 L 54 -314 L 58 -288 C 84 -278, 102 -250, 94 -220 C 66 -244, 30 -256, 0 -254 C -34 -252, -62 -242, -86 -224 Z" fill={INK} />;
  }
  if (hair === "bob") return <path d="M -98 -150 C -112 -260, -40 -306, 10 -298 C 80 -290, 112 -240, 98 -150 L 84 -150 C 86 -220, 40 -246, 0 -244 C -44 -242, -84 -220, -82 -150 Z" fill={INK} />;
  if (hair === "bun") {
    return (
      <g fill={INK}>
        <circle cx={0} cy={-306} r={30} />
        <path d="M -90 -210 C -96 -270, -40 -296, 0 -294 C 44 -294, 96 -270, 90 -210 C 60 -240, 30 -250, 0 -250 C -32 -250, -62 -240, -90 -210 Z" />
      </g>
    );
  }
  if (hair === "short") return <path d="M -90 -214 C -94 -272, -40 -298, 0 -296 C 46 -296, 96 -272, 90 -214 C 62 -236, 30 -246, 0 -246 C -32 -246, -64 -236, -90 -214 Z" fill={INK} />;
  if (hair === "curly") {
    return (
      <g fill={INK}>
        {[-78, -50, -20, 12, 42, 72].map((x, i) => <circle key={i} cx={x} cy={-262 - (i % 2) * 14} r={28} />)}
        <path d="M -92 -222 C -70 -250, 70 -250, 92 -222 L 92 -244 L -92 -244 Z" />
      </g>
    );
  }
  return null; // bald
}

function Eyes({ face, blink, villain }: { face: Face; blink: boolean; villain: boolean }) {
  if (villain) {
    return (
      <g fill={face === "angry" || face === "grin" ? RED : WHITE}>
        <path d="M -48 -204 L -14 -194 L -46 -184 Z" />
        <path d="M 48 -204 L 14 -194 L 46 -184 Z" />
      </g>
    );
  }
  const shocked = face === "shocked" || face === "worried";
  return (
    <g>
      {[-34, 34].map((ex) => (
        <g key={ex} transform={`translate(${ex} ${HY}) scale(1 ${blink ? 0.12 : 1})`}>
          <ellipse cx={0} cy={0} rx={shocked ? 26 : 22} ry={shocked ? 32 : 27} fill={WHITE} stroke={INK} strokeWidth={5} />
          <circle cx={face === "smug" ? 6 : 0} cy={4} r={shocked ? 6 : 9} fill={INK} />
        </g>
      ))}
    </g>
  );
}

function Brows({ face }: { face: Face }) {
  const up: Record<Face, [string, string]> = {
    neutral: ["M -60 -238 L -14 -232", "M 14 -232 L 60 -238"],
    happy: ["M -60 -244 Q -36 -256 -14 -244", "M 14 -244 Q 36 -256 60 -244"],
    shocked: ["M -60 -252 L -14 -258", "M 14 -258 L 60 -252"],
    worried: ["M -60 -236 L -14 -254", "M 14 -254 L 60 -236"],
    angry: ["M -60 -252 L -14 -232", "M 14 -232 L 60 -252"],
    smug: ["M -60 -238 L -14 -238", "M 14 -244 L 60 -250"],
    sad: ["M -60 -232 L -14 -248", "M 14 -248 L 60 -232"],
    grin: ["M -60 -248 L -14 -236", "M 14 -236 L 60 -248"],
  };
  return <g stroke={INK} strokeWidth={9} strokeLinecap="round">{up[face].map((d) => <path key={d} d={d} />)}</g>;
}

function Mouth({ face, villain }: { face: Face; villain: boolean }) {
  if (villain) {
    return face === "grin" || face === "happy" || face === "smug"
      ? <path d="M -40 -150 Q 0 -120 40 -150 Q 0 -138 -40 -150 Z" fill={WHITE} stroke={WHITE} strokeWidth={3} />
      : <path d="M -26 -146 L 26 -146" stroke={WHITE} strokeWidth={5} strokeLinecap="round" />;
  }
  switch (face) {
    case "happy":
    case "grin":
      return (
        <g>
          <path d="M -40 -150 Q 0 -100 40 -150 Z" fill={INK} />
          <path d="M -20 -122 Q 0 -134 20 -122 Q 10 -114 0 -114 Q -10 -114 -20 -122 Z" fill={RED} />
        </g>
      );
    case "shocked":
      return (
        <g>
          <path d="M -26 -156 Q 0 -168 26 -156 Q 32 -112 0 -110 Q -32 -112 -26 -156 Z" fill={INK} />
          <path d="M -14 -120 Q 0 -134 14 -120 Q 8 -112 0 -112 Q -8 -112 -14 -120 Z" fill={RED} />
        </g>
      );
    case "worried":
    case "sad":
      return <path d="M -30 -132 Q 0 -156 30 -132" stroke={INK} strokeWidth={7} fill="none" strokeLinecap="round" />;
    case "angry":
      return <path d="M -30 -140 L 30 -140" stroke={INK} strokeWidth={8} strokeLinecap="round" />;
    case "smug":
      return <path d="M -26 -146 Q 6 -132 32 -152" stroke={INK} strokeWidth={7} fill="none" strokeLinecap="round" />;
    default:
      return <ellipse cx={0} cy={-142} rx={12} ry={9} fill={INK} />;
  }
}

/** One arm: a sleeve tube from the shoulder to the hand, the hand a mitten. */
function Arm({ from, to, color, skin, flip }: { from: [number, number]; to: [number, number]; color: string; skin: string; flip?: boolean }) {
  return (
    <g>
      <path d={`M ${from[0]} ${from[1]} Q ${(from[0] + to[0]) / 2 + (flip ? -20 : 20)} ${(from[1] + to[1]) / 2 + 30} ${to[0]} ${to[1]}`} stroke={INK} strokeWidth={46} fill="none" strokeLinecap="round" />
      <path d={`M ${from[0]} ${from[1]} Q ${(from[0] + to[0]) / 2 + (flip ? -20 : 20)} ${(from[1] + to[1]) / 2 + 30} ${to[0]} ${to[1]}`} stroke={color} strokeWidth={34} fill="none" strokeLinecap="round" />
      <circle cx={to[0]} cy={to[1]} r={26} fill={skin} stroke={INK} strokeWidth={6} />
    </g>
  );
}

// Hand positions per pose (right hand, left hand), relative to the bust's bottom centre; null = down out of frame.
const HANDS: Record<Pose, [[number, number] | null, [number, number] | null]> = {
  stand: [null, null],
  point: [[150, -170], null],
  panic: [[120, -290], [-120, -290]],
  cheer: [[110, -330], [-110, -330]],
  think: [[40, -120], null],
  type: [[90, -20], [-90, -20]],
  shrug: [[150, -110], [-150, -110]],
  facepalm: [[10, -200], null],
};

/** A cast member's bust. */
export const Bust: React.FC<BustLook> = ({ kind, hair, outfit, skin, pose, face, blink }) => {
  const villain = kind === "villain";
  const body = villain ? "#23252c" : OUTFIT_COLORS[outfit];
  const skinC = villain ? "#16171c" : SKIN_COLORS[skin];
  const [right, left] = HANDS[pose];
  const shoulders = "M -128 0 C -112 -78, -60 -100, 0 -100 C 60 -100, 112 -78, 128 0 Z";
  return (
    <g>
      <Dots id="cp-cheek" color={MAG} r={4.2} gap={11} />
      <Dots id="cp-shirt" color={INK} r={2.4} gap={11} />
      <path d={shoulders} fill={body} stroke={INK} strokeWidth={7} />
      {!villain && <path d={shoulders} fill="url(#cp-shirt)" opacity={0.18} />}
      {left && <Arm from={[-96, -60]} to={left} color={body} skin={skinC} flip />}
      {villain ? (
        <g>
          <path d="M -112 -96 C -130 -230, -70 -312, 0 -312 C 70 -312, 130 -230, 112 -96 Z" fill="#23252c" stroke={INK} strokeWidth={7} />
          <ellipse cx={HX} cy={HY + 12} rx={RX - 18} ry={RY - 14} fill={skinC} />
        </g>
      ) : (
        <ellipse cx={HX} cy={HY} rx={RX} ry={RY} fill={skinC} stroke={INK} strokeWidth={7} />
      )}
      {!villain && <Hair hair={hair} kind={kind} />}
      {!villain && [-58, 58].map((cx) => <circle key={cx} cx={cx} cy={-150} r={18} fill="url(#cp-cheek)" />)}
      <Eyes face={face} blink={blink} villain={villain} />
      {!villain && <Brows face={face} />}
      <Mouth face={face} villain={villain} />
      {right && <Arm from={[96, -60]} to={right} color={body} skin={skinC} />}
      {pose === "point" && right && <path d={`M ${right[0] + 16} ${right[1] - 6} L ${right[0] + 56} ${right[1] - 16}`} stroke={INK} strokeWidth={14} strokeLinecap="round" />}
      {kind === "hero" && <path d="M -40 -96 L 0 -60 L 40 -96" fill="none" stroke={INK} strokeWidth={6} strokeLinejoin="round" />}
      {pose === "type" && <rect x={-150} y={-30} width={300} height={30} rx={8} fill={BLUE} stroke={INK} strokeWidth={6} />}
    </g>
  );
};
