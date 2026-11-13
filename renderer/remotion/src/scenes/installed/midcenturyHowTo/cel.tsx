/*
 * The Mid-century How-To look, as drawing helpers: the palette, and the
 * off-register cel (a flat fill printed a few pixels off a broken ink line,
 * its offset stepping through a few phases on twos).
 *
 * Everything drawn with these helpers is rasterised once per look into a
 * cached sprite (../characterKit/sprite.tsx), so a broken line drawn with a
 * dash pattern costs its paint once, never per frame. An agent's own object
 * (generated/<video_id>/prop-<name>.tsx) imports this file.
 */
import React from "react";
import { rng, type Pt } from "../characterKit/geometry";

export { ellP, polyP, rectP, smooth, tubeP, cubic, mix, type Pt } from "../characterKit/geometry";

export const PAPER = "#F4EAD5";
export const INK = "#2B2420";
export const CORAL = "#E4613F";
export const CORAL_DK = "#C24F31";
export const MUSTARD = "#E8B43A";
export const TEAL = "#3FA7A0";
export const BLUE = "#7F9CC0";
export const OLIVE = "#A7AE5B";
export const CREAM = "#FBF4E3";
export const SKIN = "#F2C79E";
export const NAVY = "#3B4F78";
export const HAIR = "#3A2B23";
export const GLOVE = "#FFF9EC";
export const GREY = "#B9AE98";

export const ALFA = "'Alfa Slab One', Rockwell, Georgia, serif";
export const JOST = "Jost, Futura, 'Helvetica Neue', Arial, sans-serif";
export const OLEO = "'Oleo Script', Georgia, serif";

/** The off-register print offset of a fill against its ink line. */
export const REG: Pt = [6, 5];

/** A cel's small offset for one wobble phase, different for each element. */
export function jitter(seed: number, phase: number, amp = 1.6): Pt {
  const r = rng(seed * 7919 + phase * 104729 + 13);
  return [(r() - 0.5) * 2 * amp, (r() - 0.5) * 2 * amp];
}

const DASHES = ["210 10 80 7 150 12 60 6", "140 8 230 11 90 9", "260 12 70 8 120 7"];

/**
 * One flat shape printed the mid-century way: the fill sits a few pixels off a
 * breaking ink line and moves with the phase; the ink line stays put.
 */
export const Cel: React.FC<{
  d: string;
  fill: string;
  phase: number;
  seed: number;
  sw?: number;
  broken?: boolean;
  noFill?: boolean;
  fillOpacity?: number;
}> = ({ d, fill, phase, seed, sw = 4.5, broken = true, noFill, fillOpacity = 1 }) => {
  const [jx, jy] = jitter(seed, phase);
  return (
    <g>
      {!noFill && <path d={d} fill={fill} fillOpacity={fillOpacity} transform={`translate(${REG[0] + jx} ${REG[1] + jy})`} />}
      {sw > 0 && (
        <path
          d={d}
          fill="none"
          stroke={INK}
          strokeWidth={sw}
          strokeLinejoin="round"
          strokeLinecap="round"
          strokeDasharray={broken ? DASHES[seed % DASHES.length] : undefined}
          strokeDashoffset={broken ? (seed * 53) % 300 : undefined}
        />
      )}
    </g>
  );
};

/** A four-point atomic-age sparkle. */
export const Sparkle: React.FC<{ x: number; y: number; r: number; color: string; rot?: number }> = ({ x, y, r, color, rot = 0 }) => {
  const k = r * 0.22;
  const d = `M0 ${-r} Q${k} ${-k} ${r} 0 Q${k} ${k} 0 ${r} Q${-k} ${k} ${-r} 0 Q${-k} ${-k} 0 ${-r} Z`;
  return <path d={d} fill={color} transform={`translate(${x} ${y}) rotate(${rot})`} />;
};

/** The eight-arm asterisk star on tags and labels. */
export const Asterisk: React.FC<{ x: number; y: number; r: number; rot: number; color?: string }> = ({ x, y, r, rot, color = CORAL }) => (
  <g transform={`translate(${x} ${y}) rotate(${rot})`}>
    {[0, 45, 90, 135].map((a) => (
      <rect key={a} x={-r} y={-r * 0.2} width={r * 2} height={r * 0.4} rx={r * 0.2} fill={color} transform={`rotate(${a})`} />
    ))}
  </g>
);

/** What every object drawing receives. */
export type ObjectDrawProps = {
  /** The wobble phase (0, 1 or 2), stepping on twos. */
  phase: number;
  /** The act playing or played last ("" when none), and frames since it started (-1 when none). */
  act: string;
  actT: number;
  /** The object's text: a screen's "Title|row|row|row", a sign's words, a code. */
  text: string;
};

/** How far an act has played, 0 to 1, over `frames` frames. */
export const actProgress = (actT: number, frames = 20) => (actT < 0 ? 0 : Math.min(1, actT / frames));

/** Width of `text` in ems for Jost and Alfa Slab One, sized at or above the widest glyph of each class. */
export function textEms(text: string, slab = false): number {
  let em = 0;
  for (const ch of text) {
    if (ch === "W" || ch === "M" || ch === "m" || ch === "w") em += slab ? 1.05 : 0.9;
    else if (/[A-Z0-9@#%&$]/.test(ch)) em += slab ? 0.8 : 0.68;
    else if (/[iIl1.,:;'!|]/.test(ch)) em += 0.32;
    else if (ch === " ") em += 0.28;
    else em += slab ? 0.66 : 0.56;
  }
  return em;
}

/** The largest font size up to `max` at which `text` fits `width` pixels. */
export const fitFont = (text: string, width: number, max: number, slab = false) =>
  Math.min(max, width / Math.max(textEms(text, slab), 0.5));
