/*
 * The Comic Panels prop library: one static drawing per prop id, centred on
 * (0, 0) with every pixel inside its PROPS box (../contract) and about 6 px of
 * room to spare. Same house look as the cast (../ink): heavy black ink (6-7 px
 * outlines, 4-5 px details), flat bright colour, fixed-grid halftone dots.
 *
 * Each drawing is rasterised once into its own cached sprite, so each defines
 * every dot pattern and clip path it uses, under ids prefixed with its prop id.
 * Text is Comic Neue 700, measured with the face's own advance widths and sized
 * so the whole text fits its area: it wraps at spaces onto the area's lines and
 * shrinks until the longest line fits, so it never runs outside the area.
 */
import React from "react";
import type { PropId } from "../contract";
import { BANG, BLUE, COMIC, CYAN, Dots, GREEN, GREY, INK, MAG, PAPER, RED, WHITE, YEL, starPoints, wrap, type PropDrawProps } from "../ink";

const GOLD = "#d99a00";
const LEAF = "#cfe6c4";
const SKY = "#d6eef8";
const WOOD = "#b07a52";
const PURPLE = "#8a5cd0";
const SOOT = "#30343f";

// ---- text -----------------------------------------------------------------

// Comic Neue Bold advance widths for " " to "~", in hundredths of an em.
const ADV = [
  36, 26, 32, 71, 60, 68, 62, 21, 36, 36, 38, 44, 19, 41, 18, 44, 57, 39, 50, 49, 47, 53, 52, 45, 51, 52, 21, 22, 54, 46, 54, 50,
  85, 55, 61, 60, 62, 59, 58, 71, 71, 40, 47, 56, 51, 81, 65, 64, 55, 70, 58, 55, 52, 67, 54, 85, 71, 58, 57, 34, 57, 34, 53, 52,
  20, 51, 52, 47, 52, 49, 32, 55, 53, 24, 26, 49, 24, 80, 54, 52, 52, 51, 40, 42, 33, 52, 42, 62, 49, 46, 43, 38, 22, 38, 61,
];
const SAFE = 1.06; // room for a fallback face or a rounding error
const LEAD = 1.15; // Comic Neue's ascent + descent

function emWidth(s: string): number {
  let w = 0;
  for (const ch of s) {
    const c = ch.codePointAt(0) ?? 0;
    w += c >= 32 && c <= 126 ? ADV[c - 32] / 100 : 0.86;
  }
  return w * SAFE;
}

/** The wrapping and size that set `text` largest inside a w x h area. */
function fit(text: string, w: number, h: number, maxLines: number, maxSize: number): { lines: string[]; size: number } {
  const t = text.trim();
  let best: { lines: string[]; size: number } = { lines: [], size: 0 };
  if (!t) return best;
  const n = maxLines > 1 ? t.length : 1;
  for (let per = 1; per <= n; per++) {
    const lines = maxLines > 1 ? wrap(t, per, maxLines) : [t.split(/\s+/).join(" ")];
    const widest = Math.max(...lines.map(emWidth));
    const size = Math.min(maxSize, w / widest, h / (lines.length * LEAD));
    if (size > best.size + 0.01) best = { lines, size };
  }
  return best;
}

/** `text` fitted inside the area (x, y, w, h), centred on it or set from its left edge. */
const FitText: React.FC<{
  text: string; x: number; y: number; w: number; h: number; lines?: number; max: number; fill?: string; align?: "middle" | "start";
}> = ({ text, x, y, w, h, lines = 1, max, fill = INK, align = "middle" }) => {
  const f = fit(text, w, h, lines, max);
  if (!f.lines.length) return null;
  const top = y + (h - f.lines.length * f.size * LEAD) / 2;
  const tx = align === "middle" ? x + w / 2 : x;
  return (
    <text fontFamily={COMIC} fontWeight={700} fontSize={f.size.toFixed(1)} fill={fill} textAnchor={align}>
      {f.lines.map((l, i) => (
        <tspan key={i} x={tx} y={(top + (i + 0.5) * f.size * LEAD + 0.325 * f.size).toFixed(1)}>{l}</tspan>
      ))}
    </text>
  );
};

// ---- small parts ----------------------------------------------------------

/** A closed shape filled flat, with an optional halftone pass and an ink outline. */
const Ink: React.FC<{ d: string; fill: string; dots?: string; dotsOpacity?: number; sw?: number }> = ({ d, fill, dots, dotsOpacity = 1, sw = 7 }) => (
  <g>
    <path d={d} fill={fill} />
    {dots ? <path d={d} fill={`url(#${dots})`} opacity={dotsOpacity} /> : null}
    <path d={d} fill="none" stroke={INK} strokeWidth={sw} strokeLinejoin="round" />
  </g>
);

const rr = (x: number, y: number, w: number, h: number, r = 0) => {
  const q = Math.min(r, w / 2, h / 2);
  return `M ${x + q} ${y} H ${x + w - q} Q ${x + w} ${y} ${x + w} ${y + q} V ${y + h - q} Q ${x + w} ${y + h} ${x + w - q} ${y + h} H ${x + q} Q ${x} ${y + h} ${x} ${y + h - q} V ${y + q} Q ${x} ${y} ${x + q} ${y} Z`;
};

const circ = (cx: number, cy: number, r: number) => `M ${cx - r} ${cy} A ${r} ${r} 0 1 0 ${cx + r} ${cy} A ${r} ${r} 0 1 0 ${cx - r} ${cy} Z`;

/** A small closed envelope icon, w x h, top-left at (x, y). */
const EnvIcon: React.FC<{ x: number; y: number; w: number; h: number; fill?: string; sw?: number }> = ({ x, y, w, h, fill = "none", sw = 4 }) => (
  <g>
    <rect x={x} y={y} width={w} height={h} fill={fill} stroke={INK} strokeWidth={sw} strokeLinejoin="round" />
    <polyline points={`${x},${y} ${x + w / 2},${y + h * 0.55} ${x + w},${y}`} fill="none" stroke={INK} strokeWidth={sw} strokeLinejoin="round" />
  </g>
);

/** A padlock glyph centred on (cx, cy), about `s` units tall. */
const Padlock: React.FC<{ cx: number; cy: number; s: number; fill?: string }> = ({ cx, cy, s, fill = INK }) => (
  <g>
    <path d={`M ${cx - s * 0.24} ${cy} V ${cy - s * 0.16} A ${s * 0.24} ${s * 0.24} 0 0 1 ${cx + s * 0.24} ${cy - s * 0.16} V ${cy}`} fill="none" stroke={INK} strokeWidth={s * 0.11} />
    <rect x={cx - s * 0.36} y={cy - s * 0.04} width={s * 0.72} height={s * 0.54} rx={s * 0.08} fill={fill} stroke={INK} strokeWidth={s * 0.07} />
  </g>
);

/** Window buttons: three dots in a row. */
const Lights: React.FC<{ x: number; y: number; r: number; gap: number }> = ({ x, y, r, gap }) => (
  <g>{[RED, YEL, GREEN].map((c, i) => <circle key={i} cx={x + i * gap} cy={y} r={r} fill={c} />)}</g>
);

// ---- screens --------------------------------------------------------------

const Phone: React.FC<PropDrawProps> = ({ text }) => (
  <g>
    <Dots id="phone-cy" color={CYAN} r={2.4} gap={10} />
    <rect x={-62} y={-120} width={124} height={240} rx={22} fill={INK} stroke={INK} strokeWidth={7} />
    <rect x={-51} y={-98} width={102} height={186} rx={6} fill={WHITE} />
    <rect x={-51} y={30} width={102} height={58} fill="url(#phone-cy)" opacity={0.55} />
    <rect x={-51} y={-98} width={102} height={22} fill={CYAN} />
    <rect x={-14} y={-111} width={28} height={6} rx={3} fill={GREY} />
    <circle cx={0} cy={104} r={8} fill="none" stroke={GREY} strokeWidth={4} />
    <FitText text={text} x={-44} y={-70} w={88} h={150} lines={5} max={30} />
  </g>
);

const Laptop: React.FC<PropDrawProps> = ({ text }) => (
  <g>
    <Dots id="laptop-grey" color={GREY} r={2.6} gap={10} />
    <Dots id="laptop-cy" color={CYAN} r={2.2} gap={10} />
    {/* lid */}
    <rect x={-118} y={-98} width={236} height={138} rx={12} fill={INK} stroke={INK} strokeWidth={7} />
    <rect x={-104} y={-86} width={208} height={114} rx={4} fill={WHITE} />
    <rect x={-104} y={-86} width={208} height={22} fill={CYAN} />
    <Lights x={-92} y={-75} r={5} gap={16} />
    <rect x={-104} y={6} width={208} height={22} fill="url(#laptop-cy)" opacity={0.5} />
    <FitText text={text} x={-96} y={-60} w={192} h={84} lines={3} max={36} />
    {/* base */}
    <Ink d="M -118 40 H 118 L 136 82 Q 138 92 128 92 H -128 Q -138 92 -136 82 Z" fill={WHITE} dots="laptop-grey" dotsOpacity={0.6} />
    {[-80, -48, -16, 16, 48].map((x) => <rect key={x} x={x} y={50} width={26} height={8} rx={2} fill={INK} />)}
    <rect x={-32} y={66} width={64} height={16} rx={4} fill={WHITE} stroke={INK} strokeWidth={4} />
  </g>
);

const Inbox: React.FC<PropDrawProps> = ({ text }) => (
  <g>
    <Dots id="inbox-red" color={RED} r={2.1} gap={11} />
    <Dots id="inbox-ink" color={INK} r={2.4} gap={10} />
    <rect x={-200} y={-100} width={400} height={200} rx={14} fill={WHITE} />
    <path d={rr(-200, -100, 400, 50, 14)} fill={CYAN} />
    <rect x={-200} y={-64} width={400} height={14} fill={CYAN} />
    <path d={rr(-200, -100, 400, 50, 14)} fill="url(#inbox-ink)" opacity={0.18} />
    <line x1={-200} y1={-50} x2={200} y2={-50} stroke={INK} strokeWidth={6} />
    <text x={-180} y={-60} fontFamily={BANG} fontSize={40} fill={WHITE} stroke={INK} strokeWidth={6} paintOrder="stroke" letterSpacing={2}>INBOX</text>
    <circle cx={-66} cy={-75} r={17} fill={RED} stroke={INK} strokeWidth={4} />
    <text x={-66} y={-63} textAnchor="middle" fontFamily={BANG} fontSize={32} fill={WHITE}>1</text>
    {/* the new message */}
    <rect x={-186} y={-38} width={372} height={92} fill={WHITE} />
    <rect x={-186} y={-38} width={372} height={92} fill="url(#inbox-red)" opacity={0.35} />
    <rect x={-186} y={-38} width={372} height={92} fill="none" stroke={INK} strokeWidth={6} />
    <rect x={-186} y={-38} width={12} height={92} fill={RED} stroke={INK} strokeWidth={5} />
    <EnvIcon x={-160} y={-14} w={54} h={40} fill={RED} sw={5} />
    <FitText text={text} x={-94} y={-32} w={272} h={80} lines={2} max={36} align="start" />
    {/* an ordinary message */}
    <g opacity={0.5}>
      <rect x={-186} y={64} width={372} height={26} fill="none" stroke={INK} strokeWidth={4} />
      <EnvIcon x={-152} y={69} w={24} h={16} sw={3} />
      <rect x={-94} y={71} width={170} height={12} rx={6} fill={GREY} />
    </g>
    <rect x={-200} y={-100} width={400} height={200} rx={14} fill="none" stroke={INK} strokeWidth={7} />
  </g>
);

const Login: React.FC<PropDrawProps> = ({ text }) => (
  <g>
    <Dots id="login-mag" color={MAG} r={2.4} gap={11} />
    <Dots id="login-cy" color={CYAN} r={2.2} gap={10} />
    <rect x={-160} y={-120} width={320} height={240} rx={16} fill={WHITE} />
    <rect x={-160} y={-120} width={320} height={240} rx={16} fill="url(#login-mag)" opacity={0.22} />
    <path d="M -160 -88 V -104 Q -160 -120 -144 -120 H 144 Q 160 -120 160 -104 V -88 Z" fill={INK} />
    <Lights x={-136} y={-104} r={7} gap={22} />
    {/* address bar */}
    <rect x={-148} y={-78} width={296} height={44} rx={22} fill={PAPER} stroke={INK} strokeWidth={5} />
    <Padlock cx={-122} cy={-56} s={28} />
    <FitText text={text} x={-102} y={-74} w={238} h={36} max={30} align="start" />
    {/* email */}
    <rect x={-134} y={-22} width={268} height={36} rx={7} fill={PAPER} stroke={INK} strokeWidth={5} />
    <EnvIcon x={-120} y={-13} w={26} h={18} sw={3.5} />
    <rect x={-82} y={-10} width={150} height={12} rx={6} fill={GREY} />
    {/* password */}
    <rect x={-134} y={24} width={268} height={38} rx={7} fill={WHITE} stroke={INK} strokeWidth={6} />
    <rect x={-134} y={24} width={268} height={38} rx={7} fill="url(#login-cy)" opacity={0.35} />
    {Array.from({ length: 8 }).map((_, i) => <circle key={i} cx={-110 + i * 28} cy={43} r={8} fill={INK} />)}
    {/* button */}
    <rect x={-90} y={74} width={180} height={36} rx={10} fill={BLUE} stroke={INK} strokeWidth={6} />
    <text x={0} y={104} textAnchor="middle" fontFamily={BANG} fontSize={32} fill={WHITE} stroke={INK} strokeWidth={6} paintOrder="stroke" letterSpacing={2}>LOG IN</text>
    <rect x={-160} y={-120} width={320} height={240} rx={16} fill="none" stroke={INK} strokeWidth={7} />
  </g>
);

const Browser: React.FC<PropDrawProps> = ({ text }) => (
  <g>
    <Dots id="browser-cy" color={CYAN} r={2.4} gap={10} />
    <rect x={-200} y={-50} width={400} height={100} rx={14} fill={WHITE} />
    <rect x={-200} y={-14} width={400} height={64} fill="url(#browser-cy)" opacity={0.35} />
    <path d="M -200 -18 V -36 Q -200 -50 -186 -50 H 186 Q 200 -50 200 -36 V -18 Z" fill={INK} />
    <Lights x={-178} y={-34} r={6} gap={19} />
    <path d="M -110 -18 L -100 -42 H 20 L 30 -18 Z" fill={WHITE} />
    <rect x={-186} y={-6} width={372} height={46} rx={23} fill={PAPER} stroke={INK} strokeWidth={5} />
    <Padlock cx={-160} cy={18} s={30} fill={GREEN} />
    <FitText text={text} x={-138} y={-2} w={312} h={38} max={32} align="start" />
    <rect x={-200} y={-50} width={400} height={100} rx={14} fill="none" stroke={INK} strokeWidth={7} />
  </g>
);

const Monitor: React.FC<PropDrawProps> = ({ text }) => (
  <g>
    <Dots id="monitor-cy" color={CYAN} r={2.6} gap={11} />
    <Dots id="monitor-grey" color={GREY} r={2.4} gap={10} />
    <Ink d={rr(-22, 66, 44, 36)} fill={WHITE} dots="monitor-grey" sw={6} />
    <Ink d={rr(-72, 100, 144, 20, 6)} fill={WHITE} dots="monitor-grey" sw={6} />
    <rect x={-150} y={-118} width={300} height={186} rx={16} fill={INK} stroke={INK} strokeWidth={7} />
    <rect x={-134} y={-102} width={268} height={152} rx={4} fill={SKY} />
    <rect x={-134} y={10} width={268} height={40} fill="url(#monitor-cy)" opacity={0.5} />
    <FitText text={text} x={-122} y={-94} w={244} h={136} lines={3} max={44} />
    <circle cx={128} cy={59} r={4} fill={GREEN} />
  </g>
);

// ---- things ---------------------------------------------------------------

const Server: React.FC<PropDrawProps> = () => (
  <g>
    <Dots id="server-ink" color={INK} r={2.6} gap={10} />
    <clipPath id="server-clip"><path d={rr(-68, -116, 136, 232, 10)} /></clipPath>
    <path d={rr(-68, -116, 136, 232, 10)} fill={GREY} />
    <rect x={40} y={-116} width={30} height={232} fill="url(#server-ink)" opacity={0.45} clipPath="url(#server-clip)" />
    {[-100, -52, -4, 44].map((y, i) => (
      <g key={y}>
        <rect x={-54} y={y} width={108} height={38} rx={4} fill={WHITE} stroke={INK} strokeWidth={5} />
        <rect x={-42} y={y + 15} width={52} height={8} rx={4} fill={INK} />
        <circle cx={26} cy={y + 19} r={6} fill={GREEN} stroke={INK} strokeWidth={3} />
        <circle cx={42} cy={y + 19} r={6} fill={i === 1 ? RED : YEL} stroke={INK} strokeWidth={3} />
      </g>
    ))}
    {[-40, -24, -8, 8, 24, 40].map((x) => <rect key={x} x={x - 3} y={92} width={6} height={14} rx={3} fill={INK} />)}
    <path d={rr(-68, -116, 136, 232, 10)} fill="none" stroke={INK} strokeWidth={7} />
  </g>
);

const Lock: React.FC<PropDrawProps> = () => (
  <g>
    <Dots id="lock-gold" color={GOLD} r={2.8} gap={10} />
    <clipPath id="lock-clip"><path d={rr(-50, -18, 100, 88, 12)} /></clipPath>
    <path d="M -32 -14 V -28 A 32 32 0 0 1 32 -28 V -14" fill="none" stroke={INK} strokeWidth={24} />
    <path d="M -32 -14 V -28 A 32 32 0 0 1 32 -28 V -14" fill="none" stroke={GREY} strokeWidth={11} />
    <path d={rr(-50, -18, 100, 88, 12)} fill={YEL} />
    <rect x={10} y={-18} width={44} height={92} fill="url(#lock-gold)" clipPath="url(#lock-clip)" />
    <rect x={-38} y={-8} width={12} height={46} rx={6} fill={WHITE} opacity={0.85} />
    <circle cx={0} cy={16} r={12} fill={INK} />
    <path d="M -7 18 L -10 46 H 10 L 7 18 Z" fill={INK} />
    <path d={rr(-50, -18, 100, 88, 12)} fill="none" stroke={INK} strokeWidth={7} />
  </g>
);

const Key: React.FC<PropDrawProps> = () => (
  <g>
    <Dots id="key-gold" color={GOLD} r={2.4} gap={9} />
    <clipPath id="key-clip"><path d={circ(-46, 0, 28)} /></clipPath>
    <Ink d="M -24 -9 H 74 V 9 H 66 V 30 H 52 V 9 H 44 V 24 H 30 V 9 H -24 Z" fill={YEL} sw={6} />
    <path d={`${circ(-46, 0, 28)} ${circ(-52, 0, 10)}`} fill={YEL} fillRule="evenodd" />
    <rect x={-74} y={4} width={56} height={26} fill="url(#key-gold)" clipPath="url(#key-clip)" />
    <path d={`${circ(-46, 0, 28)} ${circ(-52, 0, 10)}`} fill="none" stroke={INK} strokeWidth={7} />
  </g>
);

const SHIELD = "M 0 -80 C 26 -66 46 -62 62 -64 V -12 C 62 32 34 60 0 80 C -34 60 -62 32 -62 -12 V -64 C -46 -62 -26 -66 0 -80 Z";
const Shield: React.FC<PropDrawProps> = () => (
  <g>
    <Dots id="shield-ink" color={INK} r={2.4} gap={10} />
    <clipPath id="shield-clip"><path d={SHIELD} /></clipPath>
    <path d={SHIELD} fill={BLUE} />
    <rect x={0} y={-82} width={66} height={164} fill="url(#shield-ink)" opacity={0.4} clipPath="url(#shield-clip)" />
    <path d={SHIELD} transform="scale(0.78)" fill="none" stroke={WHITE} strokeWidth={5} />
    <path d="M -28 0 L -8 22 L 30 -24" fill="none" stroke={INK} strokeWidth={24} strokeLinecap="round" strokeLinejoin="round" />
    <path d="M -28 0 L -8 22 L 30 -24" fill="none" stroke={YEL} strokeWidth={12} strokeLinecap="round" strokeLinejoin="round" />
    <path d={SHIELD} fill="none" stroke={INK} strokeWidth={7} strokeLinejoin="round" />
  </g>
);

const Bug: React.FC<PropDrawProps> = () => (
  <g>
    <Dots id="bug-green" color="#256b2e" r={2.6} gap={10} />
    <clipPath id="bug-clip"><ellipse cx={0} cy={14} rx={40} ry={46} /></clipPath>
    {[-22, 6, 34].map((y, i) => (
      <g key={y} stroke={INK} strokeWidth={7} strokeLinecap="round" fill="none">
        <path d={`M -30 ${y} L -54 ${y - 10 + i * 8} L -68 ${y + i * 10}`} />
        <path d={`M 30 ${y} L 54 ${y - 10 + i * 8} L 68 ${y + i * 10}`} />
      </g>
    ))}
    <path d="M -10 -50 Q -22 -66 -34 -58" fill="none" stroke={INK} strokeWidth={5} strokeLinecap="round" />
    <path d="M 10 -50 Q 22 -66 34 -58" fill="none" stroke={INK} strokeWidth={5} strokeLinecap="round" />
    <circle cx={-34} cy={-58} r={6} fill={INK} />
    <circle cx={34} cy={-58} r={6} fill={INK} />
    <ellipse cx={0} cy={14} rx={40} ry={46} fill={GREEN} />
    <rect x={8} y={-34} width={36} height={96} fill="url(#bug-green)" clipPath="url(#bug-clip)" />
    <line x1={0} y1={-26} x2={0} y2={58} stroke={INK} strokeWidth={5} />
    {[[-18, 2, 7], [18, 2, 7], [-16, 30, 6], [16, 30, 6]].map(([x, y, r], i) => <circle key={i} cx={x} cy={y} r={r} fill={INK} />)}
    <ellipse cx={0} cy={14} rx={40} ry={46} fill="none" stroke={INK} strokeWidth={7} />
    <circle cx={0} cy={-36} r={22} fill={INK} />
    <circle cx={-9} cy={-38} r={7} fill={WHITE} />
    <circle cx={9} cy={-38} r={7} fill={WHITE} />
    <circle cx={-8} cy={-37} r={3} fill={INK} />
    <circle cx={10} cy={-37} r={3} fill={INK} />
  </g>
);

const Virus: React.FC<PropDrawProps> = () => {
  const spikes = Array.from({ length: 10 }, (_, i) => (i / 10) * Math.PI * 2 + 0.2);
  return (
    <g>
      <Dots id="virus-mag" color="#a8184f" r={2.6} gap={10} />
      <clipPath id="virus-clip"><circle cx={0} cy={0} r={46} /></clipPath>
      {spikes.map((a, i) => (
        <g key={i}>
          <line x1={Math.cos(a) * 40} y1={Math.sin(a) * 40} x2={Math.cos(a) * 60} y2={Math.sin(a) * 60} stroke={INK} strokeWidth={8} strokeLinecap="round" />
          <circle cx={Math.cos(a) * 60} cy={Math.sin(a) * 60} r={8} fill={YEL} stroke={INK} strokeWidth={5} />
        </g>
      ))}
      <circle cx={0} cy={0} r={46} fill={MAG} />
      <rect x={-6} y={6} width={56} height={44} fill="url(#virus-mag)" clipPath="url(#virus-clip)" />
      <circle cx={0} cy={0} r={46} fill="none" stroke={INK} strokeWidth={7} />
      <circle cx={-26} cy={-24} r={6} fill={WHITE} opacity={0.8} />
      {/* a mischievous face */}
      <ellipse cx={-15} cy={-6} rx={10} ry={12} fill={WHITE} stroke={INK} strokeWidth={4} />
      <ellipse cx={15} cy={-6} rx={10} ry={12} fill={WHITE} stroke={INK} strokeWidth={4} />
      <circle cx={-13} cy={-3} r={4.5} fill={INK} />
      <circle cx={17} cy={-3} r={4.5} fill={INK} />
      <path d="M -27 -22 L -6 -16" stroke={INK} strokeWidth={5} strokeLinecap="round" />
      <path d="M 27 -22 L 6 -16" stroke={INK} strokeWidth={5} strokeLinecap="round" />
      <path d="M -16 14 Q 2 30 20 12 Q 2 20 -16 14 Z" fill={INK} stroke={INK} strokeWidth={4} strokeLinejoin="round" />
    </g>
  );
};

function membrane(): string {
  const pts: string[] = [];
  for (let i = 0; i < 72; i++) {
    const a = (i / 72) * Math.PI * 2;
    const r = 75 + 3 * Math.sin(a * 5) + 1.5 * Math.sin(a * 3 + 1);
    pts.push(`${(Math.cos(a) * r).toFixed(1)},${(Math.sin(a) * r).toFixed(1)}`);
  }
  return `M ${pts.join(" L ")} Z`;
}
const MEMBRANE = membrane();
const Cell: React.FC<PropDrawProps> = () => (
  <g>
    <Dots id="cell-green" color={GREEN} r={2.2} gap={11} />
    <Dots id="cell-purple" color="#5b3696" r={2.4} gap={9} />
    <clipPath id="cell-nclip"><ellipse cx={-8} cy={-6} rx={30} ry={26} /></clipPath>
    <path d={MEMBRANE} fill={LEAF} />
    <path d={MEMBRANE} fill="url(#cell-green)" opacity={0.45} />
    <path d={MEMBRANE} transform="scale(0.9)" fill="none" stroke={GREEN} strokeWidth={4} />
    {/* nucleus */}
    <ellipse cx={-8} cy={-6} rx={30} ry={26} fill={PURPLE} />
    <rect x={0} y={-6} width={30} height={30} fill="url(#cell-purple)" clipPath="url(#cell-nclip)" />
    <ellipse cx={-8} cy={-6} rx={30} ry={26} fill="none" stroke={INK} strokeWidth={6} />
    <circle cx={-14} cy={-12} r={8} fill={INK} />
    {/* mitochondria */}
    {[[34, 38, 25], [38, -36, -30], [-40, 40, -15]].map(([x, y, rot], i) => (
      <g key={i} transform={`translate(${x} ${y}) rotate(${rot})`}>
        <rect x={-18} y={-9} width={36} height={18} rx={9} fill={RED} stroke={INK} strokeWidth={4} />
        <path d="M -11 0 L -6 -4 L -1 4 L 4 -4 L 9 4 L 12 0" fill="none" stroke={YEL} strokeWidth={2.5} strokeLinejoin="round" />
      </g>
    ))}
    {[[-46, -30, 6], [10, -50, 5], [52, 2, 6], [-4, 50, 5], [-58, 6, 4]].map(([x, y, r], i) => (
      <circle key={i} cx={x} cy={y} r={r} fill={CYAN} stroke={INK} strokeWidth={3} />
    ))}
    <path d={MEMBRANE} fill="none" stroke={INK} strokeWidth={7} strokeLinejoin="round" />
  </g>
);

const Bomb: React.FC<PropDrawProps> = () => (
  <g>
    <Dots id="bomb-grey" color="#5d6474" r={3} gap={10} />
    <clipPath id="bomb-clip"><circle cx={-6} cy={16} r={56} /></clipPath>
    <path d="M 24 -38 Q 34 -56 50 -50" fill="none" stroke={INK} strokeWidth={9} strokeLinecap="round" />
    <path d="M 24 -38 Q 34 -56 50 -50" fill="none" stroke={WOOD} strokeWidth={4} strokeLinecap="round" />
    <circle cx={-6} cy={16} r={56} fill={SOOT} />
    <circle cx={14} cy={36} r={52} fill="url(#bomb-grey)" clipPath="url(#bomb-clip)" />
    <circle cx={-6} cy={16} r={56} fill="none" stroke={INK} strokeWidth={7} />
    <g transform="rotate(38 22 -30)">
      <rect x={6} y={-44} width={32} height={22} rx={3} fill={GREY} stroke={INK} strokeWidth={6} />
    </g>
    <ellipse cx={-28} cy={-8} rx={11} ry={18} transform="rotate(35 -28 -8)" fill={WHITE} />
    <circle cx={-40} cy={16} r={5} fill={WHITE} />
    <polygon points={starPoints(52, -52, 8, 8, 18, 61)} fill={YEL} stroke={INK} strokeWidth={4} strokeLinejoin="round" />
    <polygon points={starPoints(52, -52, 6, 4, 9, 62)} fill={RED} />
  </g>
);

const Money: React.FC<PropDrawProps> = ({ text }) => (
  <g>
    <Dots id="money-green" color={GREEN} r={2.2} gap={10} />
    <rect x={-92} y={-50} width={184} height={100} rx={6} fill="#bfe3a8" />
    <rect x={-92} y={-50} width={184} height={100} rx={6} fill="url(#money-green)" opacity={0.55} />
    <rect x={-82} y={-40} width={164} height={80} rx={3} fill="none" stroke={GREEN} strokeWidth={4} />
    {[[-70, -28], [70, -28], [-70, 28], [70, 28]].map(([x, y], i) => <circle key={i} cx={x} cy={y} r={7} fill={GREEN} stroke={INK} strokeWidth={3} />)}
    <ellipse cx={0} cy={0} rx={54} ry={34} fill={WHITE} stroke={INK} strokeWidth={5} />
    <FitText text={text} x={-46} y={-24} w={92} h={48} max={42} fill="#1e5a26" />
    <rect x={-92} y={-50} width={184} height={100} rx={6} fill="none" stroke={INK} strokeWidth={6} />
  </g>
);

const Document: React.FC<PropDrawProps> = ({ text }) => {
  const page = "M -66 -92 H 38 L 66 -64 V 92 H -66 Z";
  return (
    <g>
      <Dots id="document-grey" color={GREY} r={2.2} gap={9} />
      <path d={page} fill={WHITE} />
      <path d="M -66 52 V 92 H 66 V 52 Z" fill="url(#document-grey)" opacity={0.45} />
      <FitText text={text} x={-56} y={-82} w={100} h={74} lines={3} max={30} />
      <line x1={-50} y1={-2} x2={50} y2={-2} stroke={INK} strokeWidth={4} />
      {[14, 30, 46, 62, 78].map((y, i) => <rect key={y} x={-50} y={y - 4} width={i === 4 ? 60 : 100} height={8} rx={4} fill={GREY} />)}
      <path d={page} fill="none" stroke={INK} strokeWidth={6} strokeLinejoin="round" />
      <path d="M 38 -92 V -64 H 66 Z" fill={PAPER} stroke={INK} strokeWidth={5} strokeLinejoin="round" />
    </g>
  );
};

const Envelope: React.FC<PropDrawProps> = ({ text }) => (
  <g>
    <Dots id="envelope-yel" color={GOLD} r={2.2} gap={10} />
    <Dots id="envelope-red" color="#a92a17" r={1.8} gap={7} />
    <rect x={-88} y={-58} width={176} height={116} rx={4} fill={WHITE} />
    <path d="M -88 -58 L 0 -6 L 88 -58 Z" fill="#fbe9a0" />
    <path d="M -88 -58 L 0 -6 L 88 -58 Z" fill="url(#envelope-yel)" opacity={0.6} />
    <path d="M -88 -58 L 0 -6 L 88 -58" fill="none" stroke={INK} strokeWidth={5} strokeLinejoin="round" />
    <rect x={54} y={-50} width={26} height={30} fill={RED} stroke={INK} strokeWidth={4} />
    <rect x={54} y={-50} width={26} height={30} fill="url(#envelope-red)" />
    <FitText text={text} x={-58} y={0} w={132} h={50} lines={2} max={28} align="start" />
    <rect x={-88} y={-58} width={176} height={116} rx={4} fill="none" stroke={INK} strokeWidth={7} />
  </g>
);

const ROCKET = "M 0 -118 C 26 -100 34 -66 34 -30 V 62 H -34 V -30 C -34 -66 -26 -100 0 -118 Z";
const Rocket: React.FC<PropDrawProps> = () => (
  <g>
    <Dots id="rocket-grey" color={GREY} r={2.6} gap={10} />
    <Dots id="rocket-cy" color={BLUE} r={2.2} gap={8} />
    <clipPath id="rocket-clip"><path d={ROCKET} /></clipPath>
    {/* flame */}
    <path d="M -22 78 Q -26 100 0 122 Q 26 100 22 78 Z" fill={RED} stroke={INK} strokeWidth={5} strokeLinejoin="round" />
    <path d="M -11 80 Q -12 96 0 108 Q 12 96 11 80 Z" fill={YEL} />
    {/* fins */}
    <Ink d="M -32 14 L -60 62 V 86 L -32 66 Z" fill={RED} sw={6} />
    <Ink d="M 32 14 L 60 62 V 86 L 32 66 Z" fill={RED} sw={6} />
    <Ink d="M -22 62 H 22 L 28 80 H -28 Z" fill={GREY} sw={6} />
    <path d={ROCKET} fill={WHITE} />
    <g clipPath="url(#rocket-clip)">
      <rect x={-40} y={-120} width={80} height={56} fill={RED} />
      <rect x={14} y={-64} width={24} height={130} fill="url(#rocket-grey)" opacity={0.7} />
    </g>
    <line x1={-31} y1={-64} x2={31} y2={-64} stroke={INK} strokeWidth={5} />
    <circle cx={0} cy={-18} r={17} fill={CYAN} stroke={INK} strokeWidth={6} />
    <circle cx={0} cy={-18} r={13} fill="url(#rocket-cy)" opacity={0.6} />
    <circle cx={-6} cy={-24} r={4} fill={WHITE} />
    <path d={ROCKET} fill="none" stroke={INK} strokeWidth={7} strokeLinejoin="round" />
  </g>
);

const RING = `${"M -100 0 A 100 26 0 1 0 100 0 A 100 26 0 1 0 -100 0 Z"} M -74 0 A 74 15 0 1 1 74 0 A 74 15 0 1 1 -74 0 Z`;
const Planet: React.FC<PropDrawProps> = () => (
  <g>
    <Dots id="planet-ink" color={INK} r={2.6} gap={10} />
    <Dots id="planet-gold" color={GOLD} r={2} gap={9} />
    <clipPath id="planet-clip"><circle cx={0} cy={0} r={62} /></clipPath>
    <clipPath id="planet-front"><rect x={-110} y={0} width={220} height={40} /></clipPath>
    <g transform="rotate(-18)">
      <path d={RING} fill={YEL} fillRule="evenodd" stroke={INK} strokeWidth={5} />
    </g>
    <circle cx={0} cy={0} r={62} fill={CYAN} />
    <g clipPath="url(#planet-clip)">
      <path d="M -70 -30 Q 0 -14 70 -38 V -22 Q 0 2 -70 -14 Z" fill={BLUE} />
      <path d="M -70 22 Q 0 38 70 14 V 30 Q 0 54 -70 38 Z" fill={BLUE} />
      <circle cx={26} cy={26} r={60} fill="url(#planet-ink)" opacity={0.35} />
    </g>
    <circle cx={0} cy={0} r={62} fill="none" stroke={INK} strokeWidth={7} />
    <ellipse cx={-26} cy={-30} rx={9} ry={14} transform="rotate(40 -26 -30)" fill={WHITE} opacity={0.85} />
    <g transform="rotate(-18)" clipPath="url(#planet-front)">
      <path d={RING} fill={YEL} fillRule="evenodd" />
      <path d={RING} fill="url(#planet-gold)" fillRule="evenodd" opacity={0.6} />
      <path d={RING} fill="none" stroke={INK} strokeWidth={5} />
    </g>
  </g>
);

const Clock: React.FC<PropDrawProps> = () => (
  <g>
    <Dots id="clock-red" color="#a92a17" r={2.4} gap={9} />
    <clipPath id="clock-clip"><circle cx={0} cy={8} r={60} /></clipPath>
    <path d="M -34 56 L -46 68" stroke={INK} strokeWidth={8} strokeLinecap="round" />
    <path d="M 34 56 L 46 68" stroke={INK} strokeWidth={8} strokeLinecap="round" />
    <circle cx={-42} cy={-48} r={18} fill={YEL} stroke={INK} strokeWidth={6} />
    <circle cx={42} cy={-48} r={18} fill={YEL} stroke={INK} strokeWidth={6} />
    <line x1={0} y1={-52} x2={0} y2={-64} stroke={INK} strokeWidth={6} />
    <circle cx={0} cy={-64} r={5} fill={INK} />
    <circle cx={0} cy={8} r={60} fill={RED} />
    <rect x={10} y={-52} width={56} height={124} fill="url(#clock-red)" clipPath="url(#clock-clip)" />
    <circle cx={0} cy={8} r={60} fill="none" stroke={INK} strokeWidth={7} />
    <circle cx={0} cy={8} r={47} fill={WHITE} stroke={INK} strokeWidth={5} />
    {Array.from({ length: 12 }).map((_, i) => {
      const a = (i / 12) * Math.PI * 2;
      const r1 = i % 3 === 0 ? 33 : 37;
      return <line key={i} x1={Math.sin(a) * r1} y1={8 - Math.cos(a) * r1} x2={Math.sin(a) * 42} y2={8 - Math.cos(a) * 42} stroke={INK} strokeWidth={i % 3 === 0 ? 5 : 3} strokeLinecap="round" />;
    })}
    <line x1={0} y1={8} x2={-18} y2={-6} stroke={INK} strokeWidth={7} strokeLinecap="round" />
    <line x1={0} y1={8} x2={20} y2={-18} stroke={INK} strokeWidth={5} strokeLinecap="round" />
    <circle cx={0} cy={8} r={5} fill={RED} stroke={INK} strokeWidth={3} />
  </g>
);

const Sign: React.FC<PropDrawProps> = ({ text }) => (
  <g>
    <Dots id="sign-wood" color="#7a4f30" r={2.4} gap={9} />
    <Dots id="sign-red" color={RED} r={2.2} gap={10} />
    {[-72, 72].map((x) => (
      <g key={x}>
        <rect x={x - 9} y={20} width={18} height={50} fill={WOOD} />
        <rect x={x - 9} y={20} width={18} height={50} fill="url(#sign-wood)" opacity={0.7} />
        <rect x={x - 9} y={20} width={18} height={50} fill="none" stroke={INK} strokeWidth={6} />
      </g>
    ))}
    <rect x={-116} y={-70} width={232} height={104} rx={8} fill={YEL} />
    <rect x={-116} y={20} width={232} height={14} fill="url(#sign-red)" opacity={0.55} />
    <rect x={-106} y={-60} width={212} height={84} rx={4} fill="none" stroke={INK} strokeWidth={3} />
    <FitText text={text} x={-100} y={-56} w={200} h={76} lines={2} max={48} />
    <rect x={-116} y={-70} width={232} height={104} rx={8} fill="none" stroke={INK} strokeWidth={7} />
  </g>
);

const Door: React.FC<PropDrawProps> = () => (
  <g>
    <Dots id="door-red" color="#9e2a17" r={2.6} gap={10} />
    <Dots id="door-wood" color="#7a4f30" r={2.4} gap={9} />
    <rect x={-76} y={-136} width={152} height={272} fill={WOOD} />
    <rect x={-76} y={-136} width={152} height={272} fill="url(#door-wood)" opacity={0.5} />
    <rect x={-76} y={-136} width={152} height={272} fill="none" stroke={INK} strokeWidth={7} />
    <rect x={-60} y={-120} width={120} height={256} fill={RED} stroke={INK} strokeWidth={6} />
    {[[-104, 84], [0, 116]].map(([y, h]) => (
      <g key={y}>
        <rect x={-42} y={y} width={84} height={h} fill="url(#door-red)" />
        <rect x={-42} y={y} width={84} height={h} fill="none" stroke={INK} strokeWidth={5} />
      </g>
    ))}
    <circle cx={42} cy={-8} r={9} fill={YEL} stroke={INK} strokeWidth={5} />
    <line x1={-76} y1={136} x2={76} y2={136} stroke={INK} strokeWidth={7} />
  </g>
);

/** Every library prop by id; a prop with no text slot ignores its text. */
export const PROP_DRAWINGS: Record<PropId, React.FC<PropDrawProps>> = {
  phone: Phone,
  laptop: Laptop,
  inbox: Inbox,
  login: Login,
  browser: Browser,
  monitor: Monitor,
  server: Server,
  lock: Lock,
  key: Key,
  shield: Shield,
  bug: Bug,
  virus: Virus,
  cell: Cell,
  bomb: Bomb,
  money: Money,
  document: Document,
  envelope: Envelope,
  rocket: Rocket,
  planet: Planet,
  clock: Clock,
  sign: Sign,
  door: Door,
};
