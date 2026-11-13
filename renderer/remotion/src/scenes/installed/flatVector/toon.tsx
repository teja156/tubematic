/*
 * Flat Vector Science's drawing helpers: flat two-tone shapes with no
 * outlines, the way the style shades everything, and soft glows for lights.
 * Library props (./props.tsx) and the props an agent draws for one video are
 * both built from these.
 *
 * A Toon is one path drawn three times inside its own outline: a lighter rim
 * along the lit edge, the base shifted down a little, and a darker copy (or a
 * given shadow path) for the shadow plane. Every drawing is static: it is
 * rasterised once to a bitmap (./sprites.ts) and moved as a whole, so its
 * clip paths cost nothing per frame.
 */
import React from "react";

let seq = 0;
/** A fresh id for a clip or a gradient inside one drawing (each drawing is its own SVG document). */
export const uid = (p: string) => `${p}${++seq}`;

export type Glow = { cx: number; cy: number; r: number; color: string; opacity: number };

/** Two-tone flat shape: rim (top edge), base, shadow plane, optional inner glow, optional details. */
export const Toon: React.FC<{
  d: string; base: string; shade: string; rim?: string; shadeD?: string;
  rimDy?: number; shadeDx?: number; shadeDy?: number; glow?: Glow; children?: React.ReactNode;
}> = ({ d, base, shade, rim, shadeD, rimDy = 5, shadeDx = 0, shadeDy = 0, glow, children }) => {
  const id = uid("t");
  return (
    <g>
      <defs>
        <clipPath id={id}><path d={d} /></clipPath>
        {glow ? (
          <radialGradient id={`${id}g`}>
            <stop offset="0" stopColor={glow.color} stopOpacity={glow.opacity} />
            <stop offset="1" stopColor={glow.color} stopOpacity={0} />
          </radialGradient>
        ) : null}
      </defs>
      <path d={d} fill={rim ?? base} />
      <g clipPath={`url(#${id})`}>
        <path d={d} fill={base} transform={`translate(0 ${rimDy})`} />
        <path d={shadeD ?? d} fill={shade} transform={shadeD ? undefined : `translate(${shadeDx} ${shadeDy})`} />
        {children}
        {glow ? <circle cx={glow.cx} cy={glow.cy} r={glow.r} fill={`url(#${id}g)`} /> : null}
      </g>
    </g>
  );
};

/** A circle as a Toon path. */
export const circleD = (cx: number, cy: number, r: number) =>
  `M ${cx - r} ${cy} A ${r} ${r} 0 1 1 ${cx + r} ${cy} A ${r} ${r} 0 1 1 ${cx - r} ${cy} Z`;

/** A rounded rectangle as a Toon path. */
export const rrectD = (x: number, y: number, w: number, h: number, r: number) => {
  const k = Math.min(r, w / 2, h / 2);
  return `M ${x + k} ${y} H ${x + w - k} A ${k} ${k} 0 0 1 ${x + w} ${y + k} V ${y + h - k} A ${k} ${k} 0 0 1 ${x + w - k} ${y + h} ` +
    `H ${x + k} A ${k} ${k} 0 0 1 ${x} ${y + h - k} V ${y + k} A ${k} ${k} 0 0 1 ${x + k} ${y} Z`;
};

/** An ellipse as a Toon path. */
export const ellipseD = (cx: number, cy: number, rx: number, ry: number) =>
  `M ${cx - rx} ${cy} A ${rx} ${ry} 0 1 1 ${cx + rx} ${cy} A ${rx} ${ry} 0 1 1 ${cx - rx} ${cy} Z`;

/** A radial glow disc for lights (a torch, a lure, a sun). */
export const GlowDot: React.FC<{ x: number; y: number; r: number; color: string; core?: string; coreR?: number; opacity?: number }> = ({
  x, y, r, color, core, coreR = 0, opacity = 1,
}) => {
  const id = uid("g");
  return (
    <g opacity={opacity}>
      <defs>
        <radialGradient id={id}>
          <stop offset="0" stopColor={color} stopOpacity={0.75} />
          <stop offset="0.35" stopColor={color} stopOpacity={0.28} />
          <stop offset="1" stopColor={color} stopOpacity={0} />
        </radialGradient>
      </defs>
      <circle cx={x} cy={y} r={r} fill={`url(#${id})`} />
      {core ? <circle cx={x} cy={y} r={coreR} fill={core} /> : null}
    </g>
  );
};

/** A small eye: dark disc with a white glint. */
export const Eye: React.FC<{ x: number; y: number; r?: number }> = ({ x, y, r = 8 }) => (
  <g>
    <circle cx={x} cy={y} r={r} fill="#141818" />
    <circle cx={x + r * 0.3} cy={y - r * 0.3} r={r * 0.33} fill="#F9FCFB" />
  </g>
);
