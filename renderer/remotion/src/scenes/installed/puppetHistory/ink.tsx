/*
 * The Puppet History look, as drawing helpers: the palette, the line weight
 * and the faces. Warm, desaturated flat colour under a dark brown ink line of
 * about 7 px at full size, round joins, no gradients.
 *
 * Everything drawn with these helpers is rasterised once per look into a cached
 * sprite (../characterKit/sprite.tsx), so a drawing costs its paint once, never
 * per frame. An agent's own prop (generated/<video_id>/prop-<name>.tsx)
 * imports this file.
 */
import React from "react";

export const INK = "#3B2A20";
export const LW = 7;
export const HEAD = "#FBF8F2";
export const PAPER = "#F3EADF";
export const CREAM = "#E9DBBA";
export const SKY = "#89A9C4";
export const GRASS = "#5F8C47";
export const DADO = "#66845F";
export const WOOD = "#8A5A34";
export const WOOD_LIGHT = "#A97E52";
export const STONE = "#B9B2A3";
export const RED = "#E53935";
export const BLUSH = "#F2A9A0";
export const MOUTH = "#7A2E2A";
export const SWEAT = "#8EC5E8";
export const BRASS = "#C9A24A";
export const SEA = "#A9C3D6";
export const LAND = "#EADFC4";

export const ROUND = "Fredoka, 'Arial Rounded MT Bold', sans-serif";
export const HAND = "Kalam, 'Comic Sans MS', cursive";
export const TYPE = "'IBM Plex Mono', 'Courier New', monospace";

/** Common props for an inked shape: a fill, the house outline and round joins. */
export const inked = (fill: string, sw = LW) => ({ fill, stroke: INK, strokeWidth: sw, strokeLinejoin: "round" as const, strokeLinecap: "round" as const });

/** A pill (a rounded bar) from (0, 0) downwards, `w` wide and `h` long. */
export const Pill: React.FC<{ w: number; h: number; fill: string; sw?: number }> = ({ w, h, fill, sw = LW }) => (
  <rect x={-w / 2} y={-w / 2} width={w} height={h + w / 2} rx={w / 2} {...inked(fill, sw)} />
);

/** What every prop drawing receives: its text. */
export type PropDrawProps = { text: string };
