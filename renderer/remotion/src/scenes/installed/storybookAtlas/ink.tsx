/*
 * The picture-book inks: hatch patterns and the hatched flat shape every
 * drawing in this style is made of.
 *
 * These use SVG patterns, which the CPU renderer pays for on every frame they
 * are drawn live. Nothing here is drawn live: every drawing is rasterised once
 * into a bitmap (./bitmap.tsx) and reused, so each pattern is paid for once.
 * Each rasterised drawing carries its own <InkDefs/>, because an SVG drawn as
 * an image cannot see the page's ids.
 */
import React from "react";
import { INK, IVORY } from "./palette";

/** Pattern ids. `pen`: short pencil strokes at 20 degrees over a fill; `hatch`: long diagonal hatch for paper and floors. */
export const PEN = "sa-pen";
export const PEN_LIGHT = "sa-penL";
export const HATCH = "sa-hatch";
export const HATCH_LIGHT = "sa-hatchL";
export const LINES = "sa-lines";

export const InkDefs: React.FC = () => (
  <defs>
    <pattern id={PEN} width={17} height={9} patternUnits="userSpaceOnUse" patternTransform="rotate(-20)">
      <line x1={2} y1={4.5} x2={12} y2={4.5} stroke={INK} strokeWidth={1.5} strokeLinecap="round" />
    </pattern>
    <pattern id={PEN_LIGHT} width={17} height={9} patternUnits="userSpaceOnUse" patternTransform="rotate(-20)">
      <line x1={2} y1={4.5} x2={12} y2={4.5} stroke={IVORY} strokeWidth={1.4} strokeLinecap="round" />
    </pattern>
    <pattern id={HATCH} width={15} height={15} patternUnits="userSpaceOnUse" patternTransform="rotate(-45)">
      <line x1={0} y1={0} x2={0} y2={15} stroke={INK} strokeWidth={1.3} />
    </pattern>
    <pattern id={HATCH_LIGHT} width={15} height={15} patternUnits="userSpaceOnUse" patternTransform="rotate(-45)">
      <line x1={0} y1={0} x2={0} y2={15} stroke={IVORY} strokeWidth={1.2} />
    </pattern>
    <pattern id={LINES} width={10} height={11} patternUnits="userSpaceOnUse">
      <line x1={0} y1={5} x2={10} y2={5} stroke={INK} strokeWidth={1} />
    </pattern>
  </defs>
);

/**
 * A flat filled shape with a thin dark outline and pencil hatching over the
 * fill: the one primitive the whole style is drawn with.
 * `pen`: "d" dark strokes (on light fills), "l" light strokes (on dark fills), "none".
 */
export const Sh: React.FC<{
  d: string;
  fill: string;
  pen?: "d" | "l" | "none";
  penOp?: number;
  sw?: number;
  stroke?: string;
  op?: number;
}> = ({ d, fill, pen = "d", penOp = 0.2, sw = 3, stroke = INK, op = 1 }) => (
  <g opacity={op}>
    <path d={d} fill={fill} />
    {pen !== "none" && <path d={d} fill={`url(#${pen === "d" ? PEN : PEN_LIGHT})`} opacity={penOp} />}
    {sw > 0 && <path d={d} fill="none" stroke={stroke} strokeWidth={sw} strokeLinejoin="round" strokeLinecap="round" />}
  </g>
);

// ── path helpers ──────────────────────────────────────────────────────────────
export const rect = (x: number, y: number, w: number, h: number) => `M${x} ${y}h${w}v${h}h${-w}Z`;
export const circle = (cx: number, cy: number, r: number) =>
  `M${cx - r} ${cy}a${r} ${r} 0 1 0 ${2 * r} 0a${r} ${r} 0 1 0 ${-2 * r} 0Z`;
export const ellipse = (cx: number, cy: number, rx: number, ry: number) =>
  `M${cx - rx} ${cy}a${rx} ${ry} 0 1 0 ${2 * rx} 0a${rx} ${ry} 0 1 0 ${-2 * rx} 0Z`;
/** A rectangle with rounded corners. */
export const rounded = (x: number, y: number, w: number, h: number, r: number) =>
  `M${x + r} ${y}h${w - 2 * r}q${r} 0 ${r} ${r}v${h - 2 * r}q0 ${r} ${-r} ${r}h${-(w - 2 * r)}q${-r} 0 ${-r} ${-r}v${-(h - 2 * r)}q0 ${-r} ${r} ${-r}Z`;
/** A closed polygon through the points. */
export const poly = (pts: [number, number][]) => `M${pts.map(([x, y]) => `${x} ${y}`).join("L")}Z`;

/** A soft flat shadow under something standing on the floor. */
export const FloorShadow: React.FC<{ cx: number; w: number }> = ({ cx, w }) => (
  <ellipse cx={cx} cy={4} rx={w / 2} ry={Math.max(6, w * 0.06)} fill={INK} opacity={0.16} />
);
