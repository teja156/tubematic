/*
 * What every prop shares: the palette, the line, and how a text slot fits its
 * box. A prop is drawn centred on (0, 0) inside its PROPS box (contract.ts),
 * at scale 1, in the bean's 8 px ink line and flat fills.
 */
import React from "react";
import { INK, LINE, RED } from "../bean";

export { INK, LINE, RED };
export const CREAM = "#FEF1D1";
export const WHITE = "#FFFFFF";
export const PAPER = "#FFFDF4";
export const GREY = "#9AA3AE";
export const DARK = "#34343A";
export const BLUE = "#3B7DD8";
export const GREEN = "#2FA866";
export const ORANGE = "#F08A24";
export const YELLOW = "#FFD84A";
export const PINK = "#F2A3B8";
export const BROWN = "#9B6A43";

export type PropDrawProps = {
  frame: number;
  /** Frames since this prop's act started, or -1 when it has none (yet). */
  actT: number;
  text: string;
  /** Rounded caps face (screen text) and the hand face (notes, signs). */
  round: string;
  hand: string;
};

export const ink = { stroke: INK, strokeWidth: LINE, strokeLinejoin: "round" as const, strokeLinecap: "round" as const };

/** Greedy wrap of `text` into at most `maxLines` lines of about `perLine` characters. */
export function wrapTo(text: string, perLine: number, maxLines: number): string[] {
  const lines: string[] = [];
  for (const word of text.split(/\s+/).filter(Boolean)) {
    const last = lines[lines.length - 1];
    if (last !== undefined && last.length + 1 + word.length <= perLine) lines[lines.length - 1] = `${last} ${word}`;
    else lines.push(word);
  }
  if (lines.length <= maxLines) return lines;
  return [...lines.slice(0, maxLines - 1), lines.slice(maxLines - 1).join(" ")];
}

/**
 * Width of `text` in ems, from per-character classes sized at or above the
 * widest glyph of each class in Fredoka and Patrick Hand (W and M are the
 * widest capitals). Over-estimating is the safe side: a fitted line may end a
 * little short of its box, but never runs past it.
 */
export function textEms(text: string): number {
  let em = 0;
  for (const ch of text) {
    if (ch === "W" || ch === "M" || ch === "m" || ch === "w") em += 0.98;
    else if (/[A-Z0-9@#%&$]/.test(ch)) em += 0.74;
    else if (/[iIl1.,:;'!|]/.test(ch)) em += 0.32;
    else if (ch === " ") em += 0.28;
    else em += 0.6;
  }
  return em;
}

/** Line spacing of a text slot: wider than the faces' glyph boxes, or the text-layout
 *  audit reads two lines of one sign as overlapping text (seen in a live run). */
const LINE_HEIGHT = 1.25;

/**
 * A text slot fitted to a box: wrapped to at most `maxLines` lines, then sized
 * so its widest line (by textEms) fits `width` and the block fits `height`,
 * never above `maxPx`.
 */
export const FitText: React.FC<{
  text: string; x?: number; y?: number; width: number; height: number; maxPx: number;
  maxLines?: number; font: string; weight?: number; fill?: string; anchor?: "middle" | "start";
}> = ({ text, x = 0, y = 0, width, height, maxPx, maxLines = 2, font, weight = 700, fill = INK, anchor = "middle" }) => {
  if (!text) return null;
  const perLine = Math.max(6, Math.round(width / (maxPx * 0.62)));
  const lines = wrapTo(text, perLine, maxLines);
  const widest = Math.max(...lines.map(textEms), 0.5);
  const px = Math.min(maxPx, width / widest, height / (lines.length * LINE_HEIGHT));
  const top = y - ((lines.length - 1) * px * LINE_HEIGHT) / 2 + px * 0.36;
  return (
    <text x={x} y={top} textAnchor={anchor} fontSize={px} fontWeight={weight} fill={fill} style={{ fontFamily: font }}>
      {lines.map((l, i) => (
        <tspan key={i} x={x} dy={i === 0 ? 0 : px * LINE_HEIGHT}>{l}</tspan>
      ))}
    </text>
  );
};

/** 0..1 ramp over `dur` frames from the act's start; 0 before it. */
export const actRamp = (actT: number, dur: number) => (actT < 0 ? 0 : Math.min(1, actT / dur));

/** Wavy "vibration" lines either side of a prop, for buzz and ring acts. */
export const Vibration: React.FC<{ hw: number; y: number; on: number }> = ({ hw, y, on }) =>
  on <= 0 ? null : (
    <g opacity={on} stroke={INK} strokeWidth={7} strokeLinecap="round" fill="none">
      <path d={`M ${-hw - 18},${y - 40} Q ${-hw - 34},${y} ${-hw - 18},${y + 40}`} />
      <path d={`M ${-hw - 42},${y - 60} Q ${-hw - 66},${y} ${-hw - 42},${y + 60}`} />
      <path d={`M ${hw + 18},${y - 40} Q ${hw + 34},${y} ${hw + 18},${y + 40}`} />
      <path d={`M ${hw + 42},${y - 60} Q ${hw + 66},${y} ${hw + 42},${y + 60}`} />
    </g>
  );

/** A drop shadow as a flat translucent shape: cheaper than any filter. */
export const Shadow: React.FC<{ d: string }> = ({ d }) => <path d={d} fill={INK} opacity={0.16} transform="translate(0 8)" />;
