/*
 * The house puppet: one rig for every person in a Puppet History video. A big
 * round white head with dot eyes, brows, blush and a small mouth drawn as face
 * decals, a neck, a torso, pill arms on shoulder pivots and white mitten hands.
 * Costumes (./costumes.tsx) dress the torso and the sleeves and put a hat on
 * the head; the head and face never change, so a real person can never be
 * drawn with a likeness.
 *
 * The origin is the waist; the puppet reaches up to the hat (about y -540) and
 * is framed from the waist up, so nothing below the waist is ever seen. Every
 * look (costume, pose, face, blink) is drawn once into a cached sprite
 * (../characterKit/sprite.tsx); an entrance or a move is a transform on it.
 */
import React from "react";
import type { SpriteBox } from "../characterKit/sprite";
import { POSES, type Costume, type Face, type Pose } from "./contract";
import { COSTUME_DRAWINGS } from "./costumes";
import { BLUSH, HEAD, INK, LW, MOUTH, inked } from "./ink";

// Rig geometry at scale 1, from the waist.
export const RIG = {
  shoulderX: 86,
  shoulderY: -206,
  armLen: 150,
  handR: 30,
  headY: -345,
  headR: 112,
  brimY: -423,
} as const;

export { TORSO } from "./torso";

/** Where a hand is for an arm raised `a` degrees outward on side `side` (1 the puppet's right, -1 its left). */
export function handAt(side: 1 | -1, a: number): [number, number] {
  const r = (a * Math.PI) / 180;
  const len = RIG.armLen + RIG.handR * 0.4;
  return [side * (RIG.shoulderX + Math.sin(r) * len), RIG.shoulderY + Math.cos(r) * len];
}

/** The sprite box a pose needs: the body and hat, and both hands wherever they are. */
export function puppetSpriteBox(pose: Pose): SpriteBox {
  const p = POSES[pose];
  const hands = [handAt(-1, p.l), handAt(1, p.r)];
  const left = Math.min(-175, ...hands.map(([x]) => x - RIG.handR - 16));
  const right = Math.max(175, ...hands.map(([x]) => x + RIG.handR + 16));
  const top = Math.min(-560, ...hands.map(([, y]) => y - RIG.handR - 16));
  return { left: Math.floor(left), top: Math.floor(top), width: Math.ceil(right - left), height: Math.ceil(60 - top) };
}

const FaceDecal: React.FC<{ face: Face; blink: boolean }> = ({ face, blink }) => {
  const sw = LW;
  const eye = (x: number) =>
    blink ? (
      <path key={x} d={`M ${x - 13} -8 L ${x + 13} -8`} stroke={INK} strokeWidth={sw} strokeLinecap="round" />
    ) : face === "proud" || face === "happy" ? (
      <path key={x} d={`M ${x - 14} -2 Q ${x} -20 ${x + 14} -2`} fill="none" stroke={INK} strokeWidth={sw} strokeLinecap="round" />
    ) : (
      <circle key={x} cx={x} cy={-8} r={face === "shock" ? 14 : 11} fill={INK} />
    );
  const brows: Record<Face, string> = {
    stern: "M -62 -54 L -20 -42 M 62 -54 L 20 -42",
    happy: "M -60 -52 Q -40 -64 -20 -54 M 60 -52 Q 40 -64 20 -54",
    proud: "M -60 -50 Q -40 -64 -20 -52 M 60 -50 Q 40 -64 20 -52",
    worried: "M -60 -42 L -22 -58 M 60 -42 L 22 -58",
    shock: "M -60 -66 Q -40 -82 -20 -68 M 60 -66 Q 40 -82 20 -68",
    sad: "M -60 -44 L -22 -56 M 60 -44 L 22 -56",
    smug: "M -60 -50 L -20 -50 M 60 -58 Q 40 -66 20 -56",
    angry: "M -62 -60 L -18 -40 M 62 -60 L 18 -40",
  };
  const mouths: Record<Face, React.ReactNode> = {
    stern: <path d="M -22 50 L 22 50" stroke={INK} strokeWidth={sw} strokeLinecap="round" />,
    happy: <path d="M -30 40 Q 0 70 30 40" fill="none" stroke={INK} strokeWidth={sw} strokeLinecap="round" />,
    proud: <path d="M -34 36 Q 0 80 34 36 Z" {...inked(MOUTH, sw * 0.8)} />,
    worried: <path d="M -28 52 q 7 -8 14 0 q 7 8 14 0 q 7 -8 14 0 q 7 8 14 0" fill="none" stroke={INK} strokeWidth={sw * 0.8} strokeLinecap="round" />,
    shock: <ellipse cx={0} cy={50} rx={15} ry={21} {...inked(MOUTH, sw * 0.8)} />,
    sad: <path d="M -26 58 Q 0 36 26 58" fill="none" stroke={INK} strokeWidth={sw} strokeLinecap="round" />,
    smug: <path d="M -24 50 Q 8 60 30 40" fill="none" stroke={INK} strokeWidth={sw} strokeLinecap="round" />,
    angry: <path d="M -26 56 L 26 56" stroke={INK} strokeWidth={sw * 1.1} strokeLinecap="round" />,
  };
  return (
    <g>
      <ellipse cx={-66} cy={30} rx={19} ry={10} fill={BLUSH} opacity={face === "angry" ? 1 : 0.85} />
      <ellipse cx={66} cy={30} rx={19} ry={10} fill={BLUSH} opacity={face === "angry" ? 1 : 0.85} />
      {eye(-38)}
      {eye(38)}
      <path d={brows[face]} fill="none" stroke={INK} strokeWidth={sw * 0.9} strokeLinecap="round" />
      {mouths[face]}
    </g>
  );
};

const Arm: React.FC<{ side: 1 | -1; a: number; sleeve: string; cuff?: string }> = ({ side, a, sleeve, cuff }) => (
  <g transform={`translate(${side * RIG.shoulderX} ${RIG.shoulderY}) rotate(${-side * a})`}>
    <rect x={-24} y={-24} width={48} height={RIG.armLen} rx={24} {...inked(sleeve)} />
    {cuff ? <rect x={-24} y={RIG.armLen - 52} width={48} height={18} {...inked(cuff, LW * 0.7)} /> : null}
    <ellipse cx={-side * 22} cy={RIG.armLen - 14} rx={13} ry={11} {...inked(HEAD)} />
    <ellipse cx={0} cy={RIG.armLen} rx={RIG.handR} ry={RIG.handR + 2} {...inked(HEAD)} />
  </g>
);

const behind = (a: number) => a > 120 && a < 165;

export type PuppetLook = { costume: Costume; pose: Pose; face: Face; blink: boolean };

export const puppetKey = (l: PuppetLook) => ["ph-puppet", l.costume, l.pose, l.face, l.blink ? 1 : 0].join("|");

/** The puppet, facing right (the scene mirrors it to face left). */
export const Puppet: React.FC<PuppetLook> = ({ costume, pose, face, blink }) => {
  const c = COSTUME_DRAWINGS[costume];
  const p = POSES[pose];
  const { Torso, Hat } = c;
  return (
    <g>
      {/* an arm raised beside the head goes behind it; a low arm, or one reaching the head itself, in front */}
      {behind(p.l) ? <Arm side={-1} a={p.l} sleeve={c.sleeve} cuff={c.cuff} /> : null}
      {behind(p.r) ? <Arm side={1} a={p.r} sleeve={c.sleeve} cuff={c.cuff} /> : null}
      <rect x={-22} y={-262} width={44} height={40} {...inked(HEAD)} />
      <Torso sw={LW} />
      <g transform={`translate(0 ${RIG.headY}) rotate(${p.head})`}>
        {c.Back ? <c.Back sw={LW} /> : null}
        <circle r={RIG.headR} {...inked(HEAD)} />
        <FaceDecal face={face} blink={blink} />
        {Hat ? (
          <g transform={`translate(0 ${RIG.brimY - RIG.headY})`}>
            <Hat sw={LW} />
          </g>
        ) : null}
      </g>
      {!behind(p.l) ? <Arm side={-1} a={p.l} sleeve={c.sleeve} cuff={c.cuff} /> : null}
      {!behind(p.r) ? <Arm side={1} a={p.r} sleeve={c.sleeve} cuff={c.cuff} /> : null}
    </g>
  );
};
