/*
 * The Comic Panels look, as drawing helpers: the palette, the faces, fixed-grid
 * Ben-Day dots, burst stars, speed and focus lines, balloons and drawn sound
 * effects.
 *
 * Everything drawn with these helpers is rasterised once per look into a cached
 * sprite (../characterKit/sprite.tsx): a dot pattern costs its paint once,
 * never per frame, and the dots stay on a fixed grid, so a push-in never makes
 * them crawl. A drawing that uses dots puts <Dots /> in its own SVG, since each
 * sprite is its own document. An agent's own prop
 * (generated/<video_id>/prop-<name>.tsx) imports this file.
 */
import React from "react";
import { rng } from "../characterKit/geometry";

export const INK = "#141414";
export const PAPER = "#f4ecd6";
export const WHITE = "#fffaf0";
export const RED = "#e0442a";
export const YEL = "#FFD616";
export const CYAN = "#1696CD";
export const MAG = "#DE2C70";
export const BLUE = "#3b6fd0";
export const GREEN = "#3f9a48";
export const GREY = "#8e939c";

export const BANG = "Bangers, Impact, 'Arial Black', sans-serif";
export const COMIC = "'Comic Neue', 'Comic Sans MS', 'Chalkboard SE', sans-serif";

/** A fixed-grid 45-degree Ben-Day dot pattern with id `id`. */
export const Dots: React.FC<{ id: string; color: string; r?: number; gap?: number; bg?: string }> = ({ id, color, r = 3, gap = 13, bg }) => (
  <defs>
    <pattern id={id} width={gap} height={gap} patternUnits="userSpaceOnUse" patternTransform="rotate(45)">
      {bg ? <rect width={gap} height={gap} fill={bg} /> : null}
      <circle cx={gap / 2} cy={gap / 2} r={r} fill={color} />
    </pattern>
  </defs>
);

/** The points of a jagged burst star. */
export function starPoints(cx: number, cy: number, n: number, r1: number, r2: number, seed: number, ys = 0.78): string {
  const R = rng(seed);
  const pts: string[] = [];
  for (let i = 0; i < n * 2; i++) {
    const a = (i / (n * 2)) * Math.PI * 2 - Math.PI / 2;
    const r = i % 2 === 0 ? r2 * (0.85 + R() * 0.3) : r1 * (0.9 + R() * 0.2);
    pts.push(`${(cx + Math.cos(a) * r).toFixed(1)},${(cy + Math.sin(a) * r * ys).toFixed(1)}`);
  }
  return pts.join(" ");
}

/** Radiating focus or speed lines (thin wedges), seeded so they never boil. */
export const SpeedLines: React.FC<{ cx: number; cy: number; n: number; ri: number; ro: number; seed: number; color?: string; width?: number }> = ({
  cx, cy, n, ri, ro, seed, color = INK, width = 0.022,
}) => {
  const R = rng(seed);
  const polys: React.ReactNode[] = [];
  for (let i = 0; i < n; i++) {
    const a = (i / n) * Math.PI * 2 + (R() - 0.5) * 0.12;
    const w = width * (0.5 + R());
    const rin = ri * (0.85 + R() * 0.45);
    const p = [
      [cx + Math.cos(a - w) * ro, cy + Math.sin(a - w) * ro],
      [cx + Math.cos(a + w) * ro, cy + Math.sin(a + w) * ro],
      [cx + Math.cos(a) * rin, cy + Math.sin(a) * rin],
    ];
    polys.push(<polygon key={i} points={p.map((q) => q.map((v) => v.toFixed(1)).join(",")).join(" ")} fill={color} />);
  }
  return <g>{polys}</g>;
};

/** Greedy wrap into at most `max` lines of about `per` characters. */
export function wrap(text: string, per: number, max: number): string[] {
  const lines: string[] = [];
  for (const word of text.split(/\s+/).filter(Boolean)) {
    const last = lines[lines.length - 1];
    if (last !== undefined && last.length + 1 + word.length <= per) lines[lines.length - 1] = `${last} ${word}`;
    else lines.push(word);
  }
  return lines.length <= max ? lines : [...lines.slice(0, max - 1), lines.slice(max - 1).join(" ")];
}

/** What every prop drawing receives: its text. */
export type PropDrawProps = { text: string };
