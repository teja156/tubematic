/*
 * Era costumes for the house puppet (./puppet.tsx). A costume fills the torso
 * (TORSO in puppet.tsx is the outline every torso keeps, from the shoulders at
 * y -240 down past the waist at 0), colours the sleeves, and may put a hat on
 * the head (drawn with the brim's centre at (0, 0), the head's top about 34
 * units below it) and something behind the head (a hood, long hair).
 *
 * Every costume is generic: no insignia, crest, flag, rank badge, logo or
 * feature that belongs to one person, army, country or faith. A historical
 * figure is this puppet in the costume of their era with a name plate, never a
 * likeness. Outlines are INK at the stroke width each part receives, fills are
 * flat warm colours from the house palette, no gradients and no filters.
 */
import React from "react";
import type { Costume } from "./contract";
import { BRASS, INK, inked } from "./ink";
import { TORSO } from "./torso";

export type CostumeDrawing = {
  /** The sleeves' colour, and a cuff band near the hand if the costume has one. */
  sleeve: string;
  cuff?: string;
  Torso: React.FC<{ sw: number }>;
  Hat?: React.FC<{ sw: number }>;
  /** Drawn behind the head (a hood, long hair): origin at the head's centre. */
  Back?: React.FC<{ sw: number }>;
};

const PLAIN = "#7FA0B8";
const plain: CostumeDrawing = {
  sleeve: PLAIN,
  Torso: ({ sw }) => (
    <g>
      <path d={TORSO} {...inked(PLAIN, sw)} />
      <path d="M -40 -240 L 0 -196 L 40 -240" fill="none" stroke={INK} strokeWidth={sw * 0.8} strokeLinejoin="round" />
    </g>
  ),
};

const KHAKI = "#B49D68";
const KHAKI_D = "#9A8455";
const BELT = "#6B4E31";
const soldier1910s: CostumeDrawing = {
  sleeve: KHAKI,
  Torso: ({ sw }) => (
    <g>
      <path d={TORSO} {...inked(KHAKI, sw)} />
      <g stroke={INK} strokeWidth={sw * 0.8} strokeLinejoin="round">
        <path d="M -44 -240 L 0 -200 L 44 -240 Z" fill={KHAKI_D} />
        <rect x={-76} y={-182} width={52} height={46} rx={6} fill={KHAKI_D} />
        <rect x={24} y={-182} width={52} height={46} rx={6} fill={KHAKI_D} />
        <circle cx={0} cy={-168} r={6} fill={BRASS} />
        <circle cx={0} cy={-128} r={6} fill={BRASS} />
        <rect x={-97} y={-72} width={194} height={30} fill={BELT} />
      </g>
    </g>
  ),
  // a shallow brimmed steel helmet, generic
  Hat: ({ sw }) => (
    <g>
      <ellipse cx={0} cy={6} rx={150} ry={22} {...inked("#7D7F70", sw)} />
      <path d="M -96 6 C -96 -82 96 -82 96 6 Z" {...inked("#8E907F", sw)} />
    </g>
  ),
};


/* ---- shared bits for the costumes below ---- */
const line = (sw: number, k = 0.7) => ({ fill: "none", stroke: INK, strokeWidth: sw * k, strokeLinecap: "round" as const, strokeLinejoin: "round" as const });
const CREAM_W = "#F3ECDD";
const WIDE = (w: number) => `M ${-w} 40 L -92 -205 Q -88 -238 -55 -240 L 55 -240 Q 88 -238 92 -205 L ${w} 40 Z`;
const buttons = (ys: number[], r = 6, fill = BRASS, sw = 5) =>
  ys.map((y) => <circle key={y} cx={0} cy={y} r={r} fill={fill} stroke={INK} strokeWidth={sw * 0.7} />);

// dress: a long-sleeved dress with a cream collar and a ribboned bonnet
const DRESS = "#B5707A";
const dress: CostumeDrawing = {
  sleeve: DRESS,
  cuff: CREAM_W,
  Torso: ({ sw }) => (
    <g>
      <path d={WIDE(114)} {...inked(DRESS, sw)} />
      <rect x={-100} y={-86} width={200} height={26} {...inked("#8F4F5C", sw * 0.8)} />
      <path d="M -62 -240 L 0 -196 L 62 -240 L 44 -240 L 0 -214 L -44 -240 Z" {...inked(CREAM_W, sw * 0.8)} />
      <path d="M 0 -196 L 0 -90" {...line(sw)} />
      {buttons([-170, -140, -112], 5, CREAM_W, sw)}
    </g>
  ),
  Hat: ({ sw }) => (
    <g>
      <path d="M -94 4 C -106 -86 106 -86 94 4 Q 0 -14 -94 4 Z" {...inked(CREAM_W, sw)} />
      <path d="M -90 -4 Q 0 -22 90 -4" fill="none" stroke={DRESS} strokeWidth={14} strokeLinecap="round" />
      <path d="M -90 -4 Q 0 -22 90 -4" {...line(sw, 0.5)} strokeDasharray="1 24" />
      <ellipse cx={70} cy={-14} rx={20} ry={11} transform="rotate(-25 70 -14)" {...inked(DRESS, sw * 0.8)} />
      <ellipse cx={96} cy={-4} rx={20} ry={11} transform="rotate(25 96 -4)" {...inked(DRESS, sw * 0.8)} />
      <circle cx={82} cy={-10} r={8} {...inked("#8F4F5C", sw * 0.7)} />
    </g>
  ),
};

// peasant: a rough tunic, a rope belt and a plain cloth cap
const TUNIC = "#A58E64";
const peasant: CostumeDrawing = {
  sleeve: TUNIC,
  Torso: ({ sw }) => (
    <g>
      <path d={WIDE(104)} {...inked(TUNIC, sw)} />
      <path d="M -34 -240 L 0 -190 L 34 -240" {...inked("#8D7752", sw * 0.8)} />
      <path d="M -14 -214 L 14 -194 M 14 -214 L -14 -194 M -12 -188 L 12 -170 M 12 -188 L -12 -170" {...line(sw, 0.5)} />
      <path d="M -102 -64 Q 0 -44 102 -64" fill="none" stroke="#6B5A3C" strokeWidth={15} strokeLinecap="round" />
      <path d="M -102 -64 Q 0 -44 102 -64" {...line(sw, 0.45)} strokeDasharray="2 12" />
      <circle cx={34} cy={-52} r={13} {...inked("#6B5A3C", sw * 0.7)} />
      <path d="M 34 -42 L 28 -2 M 34 -42 L 50 -6" fill="none" stroke="#6B5A3C" strokeWidth={9} strokeLinecap="round" />
      <path d="M -60 -150 L -52 -128 M 54 -120 L 64 -100 M -30 -20 L -20 4" {...line(sw, 0.45)} />
    </g>
  ),
  Hat: ({ sw }) => (
    <g>
      <path d="M -94 2 C -100 -70 100 -70 94 2 Q 0 -10 -94 2 Z" {...inked("#7C6247", sw)} />
      <path d="M -90 -6 Q 0 -18 90 -6" {...line(sw, 0.6)} />
      <path d="M 0 -62 L 0 -10 M -44 -52 L -34 -10 M 44 -52 L 34 -10" {...line(sw, 0.45)} />
      <circle cx={0} cy={-62} r={8} {...inked("#7C6247", sw * 0.7)} />
    </g>
  ),
};

// farmer: a checked shirt under denim overalls and a straw hat
const CHECK = "#B2543F";
const DENIM = "#5F7F9B";
const farmer: CostumeDrawing = {
  sleeve: CHECK,
  Torso: ({ sw }) => (
    <g>
      <path d={TORSO} {...inked(CHECK, sw)} />
      <path d="M -70 -170 H 70 M -80 -120 H 80 M -40 -236 V -70 M 40 -236 V -70" {...line(sw, 0.4)} stroke="#8A3A2B" />
      <path d="M -100 -72 L -64 -72 L -60 -200 L 60 -200 L 64 -72 L 100 -72 L 100 40 L -100 40 Z" {...inked(DENIM, sw)} />
      <path d="M -52 -202 L -50 -240 M 52 -202 L 50 -240" fill="none" stroke={INK} strokeWidth={sw * 2.6} strokeLinecap="round" />
      <path d="M -52 -202 L -50 -240 M 52 -202 L 50 -240" fill="none" stroke={DENIM} strokeWidth={sw * 1.4} strokeLinecap="round" />
      <rect x={-34} y={-166} width={68} height={42} rx={5} {...inked("#6E8EA9", sw * 0.7)} />
      {[-52, 52].map((x) => <circle key={x} cx={x} cy={-190} r={6} fill={BRASS} stroke={INK} strokeWidth={sw * 0.6} />)}
      <path d="M 0 -72 V 40" {...line(sw, 0.45)} />
    </g>
  ),
  Hat: ({ sw }) => (
    <g>
      <ellipse cx={0} cy={-2} rx={156} ry={16} {...inked("#D2B66A", sw)} />
      <path d="M -76 -4 C -80 -86 80 -86 76 -4 Z" {...inked("#DCC37C", sw)} />
      <path d="M -78 -20 Q 0 -34 78 -20 L 77 -6 Q 0 -18 -77 -6 Z" {...inked("#8A5A34", sw * 0.8)} />
      <path d="M -100 -2 L -90 2 M 100 -2 L 90 2 M -40 -60 L -30 -46 M 36 -62 L 28 -46" {...line(sw, 0.4)} />
    </g>
  ),
};

// worker: an industrial work jacket with pockets and a flat cap
const JACKET = "#6F7F86";
const worker: CostumeDrawing = {
  sleeve: JACKET,
  cuff: "#56646B",
  Torso: ({ sw }) => (
    <g>
      <path d={TORSO} {...inked(JACKET, sw)} />
      <path d="M -50 -240 L -8 -190 L 0 -240 L 8 -190 L 50 -240 L 56 -214 L 10 -172 L 0 -172 L -10 -172 L -56 -214 Z" {...inked("#56646B", sw * 0.8)} />
      <path d="M 0 -176 V 40" {...line(sw)} />
      <rect x={-76} y={-150} width={50} height={38} rx={5} {...inked("#5E6D74", sw * 0.8)} />
      <rect x={26} y={-150} width={50} height={38} rx={5} {...inked("#5E6D74", sw * 0.8)} />
      <rect x={-76} y={-62} width={152} height={22} {...inked("#56646B", sw * 0.8)} />
      {buttons([-130, -96, -62], 5, "#C7C2B2", sw)}
    </g>
  ),
  Hat: ({ sw }) => (
    <g>
      <path d="M 70 -8 L 140 8 Q 142 20 112 18 L 64 8 Z" {...inked("#4A4A50", sw)} />
      <path d="M -100 2 C -104 -40 -30 -62 40 -56 C 90 -50 108 -26 100 2 Q 0 12 -100 2 Z" {...inked("#5E5F66", sw)} />
      <path d="M -96 -8 Q 0 2 98 -8" {...line(sw, 0.5)} />
      <circle cx={-8} cy={-52} r={7} {...inked("#5E5F66", sw * 0.7)} />
    </g>
  ),
};

// clerk: a dark suit, white shirt, tie and a bowler hat
const SUIT = "#4A5262";
const clerk: CostumeDrawing = {
  sleeve: SUIT,
  cuff: CREAM_W,
  Torso: ({ sw }) => (
    <g>
      <path d={TORSO} {...inked(SUIT, sw)} />
      <path d="M -50 -240 L 0 -92 L 50 -240 Z" {...inked(CREAM_W, sw * 0.8)} />
      <path d="M -50 -240 L -14 -146 L -62 -96 L -92 -200 Z M 50 -240 L 14 -146 L 62 -96 L 92 -200 Z" {...inked("#3C4351", sw * 0.8)} />
      <path d="M -16 -230 L 16 -230 L 10 -206 L -10 -206 Z" {...inked("#9B3E33", sw * 0.7)} />
      <path d="M -10 -206 L 10 -206 L 20 -110 L 0 -88 L -20 -110 Z" {...inked("#9B3E33", sw * 0.8)} />
      {buttons([-60, -30], 5, "#2D323C", sw)}
    </g>
  ),
  Hat: ({ sw }) => (
    <g>
      <ellipse cx={0} cy={-4} rx={116} ry={13} {...inked("#33343B", sw)} />
      <path d="M -76 -4 C -82 -112 82 -112 76 -4 Z" {...inked("#3E3F47", sw)} />
      <path d="M -79 -26 Q 0 -38 79 -26 L 77 -12 Q 0 -24 -77 -12 Z" {...inked("#26272D", sw * 0.7)} />
    </g>
  ),
};

// noble: a plum doublet with slashed gold braid, a ruff and a feathered beret
const PLUM = "#7D3F55";
const GOLD = "#B98A4A";
const noble: CostumeDrawing = {
  sleeve: PLUM,
  cuff: CREAM_W,
  Torso: ({ sw }) => (
    <g>
      <path d={TORSO} {...inked(PLUM, sw)} />
      <path d="M -70 -190 L -30 -150 M -76 -150 L -34 -110 M 70 -190 L 30 -150 M 76 -150 L 34 -110 M -70 -110 L -34 -76 M 70 -110 L 34 -76" fill="none" stroke={GOLD} strokeWidth={9} strokeLinecap="round" />
      <path d="M 0 -216 V 40" {...line(sw)} />
      {buttons([-190, -150, -110, -70, -30], 6, GOLD, sw)}
      {[-70, -49, -28, -7, 14, 35, 56, 77].map((a, i) => {
        const t = ((a + 70) / 147) * Math.PI;
        return <circle key={i} cx={-Math.cos(t) * 82} cy={-232 + Math.sin(t) * 24} r={15} {...inked(CREAM_W, sw * 0.7)} />;
      })}
    </g>
  ),
  Hat: ({ sw }) => (
    <g>
      <path d="M 20 -62 C 60 -134 124 -132 154 -92 C 114 -104 70 -90 20 -62 Z" {...inked(CREAM_W, sw * 0.8)} />
      <path d="M 24 -64 C 70 -110 110 -112 146 -94" {...line(sw, 0.5)} />
      <path d="M -102 4 C -112 -54 -44 -74 28 -66 C 92 -58 120 -22 104 4 Q 0 -14 -102 4 Z" {...inked("#3F5C70", sw)} />
      <path d="M -98 -6 Q 0 -22 100 -6" {...line(sw, 0.6)} stroke={GOLD} strokeWidth={sw * 0.9} />
      <circle cx={26} cy={-64} r={9} {...inked(GOLD, sw * 0.7)} />
    </g>
  ),
};

// royal: a red robe with white fur trim dotted black, and a plain gold crown
const ROBE = "#8E3A3A";
const royal: CostumeDrawing = {
  sleeve: ROBE,
  cuff: CREAM_W,
  Torso: ({ sw }) => (
    <g>
      <path d={WIDE(120)} {...inked(ROBE, sw)} />
      <rect x={-22} y={-196} width={44} height={236} fill="#6E2B2B" />
      <path d="M -52 -214 L -22 -196 L -22 40 L -56 40 Z M 52 -214 L 22 -196 L 22 40 L 56 40 Z" {...inked(CREAM_W, sw * 0.8)} />
      <path d="M -97 -212 Q -80 -246 -50 -240 L 50 -240 Q 80 -246 97 -212 L 58 -190 Q 0 -168 -58 -190 Z" {...inked(CREAM_W, sw * 0.8)} />
      {[[-76, -222], [-52, -208], [-26, -200], [0, -194], [26, -200], [52, -208], [76, -222], [-39, -160], [39, -160], [-39, -110], [39, -110], [-39, -60], [39, -60], [-39, -10], [39, -10]].map(([x, y], i) => (
        <g key={i}>
          <circle cx={x} cy={y} r={5} fill={INK} />
          <path d={`M ${x} ${y + 4} v 8`} stroke={INK} strokeWidth={4} strokeLinecap="round" />
        </g>
      ))}
    </g>
  ),
  Hat: ({ sw }) => (
    <g>
      <path d="M -82 4 L -82 -34 L -58 -78 L -34 -34 L 0 -94 L 34 -34 L 58 -78 L 82 -34 L 82 4 Q 0 -10 -82 4 Z" {...inked(BRASS, sw)} />
      <path d="M -82 -16 Q 0 -30 82 -16" {...line(sw, 0.6)} />
      {[-58, 0, 58].map((x) => <circle key={x} cx={x} cy={x === 0 ? -98 : -82} r={9} {...inked(BRASS, sw * 0.8)} />)}
      {[-44, 0, 44].map((x) => <circle key={x} cx={x} cy={-6} r={8} {...inked(x === 0 ? "#B04A4A" : "#5E8AA6", sw * 0.7)} />)}
    </g>
  ),
};

// knight: plate armour, and a helmet with its visor pushed up
const STEEL = "#9EA5A8";
const STEEL_D = "#7C8387";
const knight: CostumeDrawing = {
  sleeve: STEEL,
  cuff: STEEL_D,
  Torso: ({ sw }) => (
    <g>
      <path d={TORSO} {...inked(STEEL, sw)} />
      <path d="M -92 -226 Q 0 -190 92 -226 L 92 -196 Q 0 -160 -92 -196 Z" {...inked(STEEL_D, sw * 0.8)} />
      <path d="M 0 -176 V -70 M -70 -170 Q -30 -120 0 -140 M 70 -170 Q 30 -120 0 -140" {...line(sw, 0.8)} />
      <path d="M -97 -70 Q 0 -50 97 -70 M -99 -34 Q 0 -14 99 -34 M -100 0 Q 0 20 100 0" {...line(sw, 0.8)} />
      {[[-80, -184], [80, -184], [-60, -70], [60, -70], [-60, -32], [60, -32]].map(([x, y], i) => <circle key={i} cx={x} cy={y} r={4.5} fill={INK} />)}
    </g>
  ),
  Hat: ({ sw }) => (
    <g>
      <path d="M -100 8 L -108 44 L -88 48 L -84 6 Z M 100 8 L 108 44 L 88 48 L 84 6 Z" {...inked(STEEL_D, sw * 0.9)} />
      <path d="M -100 6 C -104 -96 104 -96 100 6 Q 0 -8 -100 6 Z" {...inked(STEEL, sw)} />
      <path d="M 0 -92 L 0 -52" {...line(sw, 0.8)} />
      <path d="M -74 -42 Q 0 -96 74 -42 L 82 -20 Q 0 -70 -82 -20 Z" {...inked(STEEL_D, sw * 0.9)} />
      <circle cx={-80} cy={-30} r={7} {...inked(BRASS, sw * 0.6)} />
      <circle cx={80} cy={-30} r={7} {...inked(BRASS, sw * 0.6)} />
    </g>
  ),
};

// legionary: a red tunic under segmented plate bands and a crested helmet
const LEG_RED = "#A8453A";
const BRONZE = "#B79F5A";
const legionary: CostumeDrawing = {
  sleeve: LEG_RED,
  Torso: ({ sw }) => (
    <g>
      <path d={TORSO} {...inked(LEG_RED, sw)} />
      {[-226, -192, -158, -124, -90].map((y, i) => (
        <path key={y} d={`M -${94 - i * 2} ${y} Q 0 ${y + 16} ${94 - i * 2} ${y} L ${96 - i * 2} ${y + 30} Q 0 ${y + 46} -${96 - i * 2} ${y + 30} Z`} {...inked(i % 2 ? "#A7A9A5" : "#B3B5B0", sw * 0.8)} />
      ))}
      <rect x={-98} y={-56} width={196} height={24} {...inked("#6B4E31", sw * 0.8)} />
      <circle cx={0} cy={-44} r={9} {...inked(BRONZE, sw * 0.7)} />
      <path d="M -70 -22 V 40 M -36 -22 V 40 M 0 -22 V 40 M 36 -22 V 40 M 70 -22 V 40" {...line(sw, 0.5)} />
    </g>
  ),
  Hat: ({ sw }) => (
    <g>
      <path d="M -70 -50 Q 0 -140 70 -50 L 60 -44 Q 0 -102 -60 -44 Z" {...inked(LEG_RED, sw)} />
      <path d="M -40 -64 L -36 -48 M -16 -78 L -12 -50 M 12 -78 L 8 -50 M 36 -64 L 32 -46" {...line(sw, 0.5)} />
      <path d="M -102 8 L -106 42 L -86 46 L -84 6 Z M 102 8 L 106 42 L 86 46 L 84 6 Z" {...inked(BRONZE, sw * 0.9)} />
      <path d="M -94 6 C -98 -66 98 -66 94 6 Q 0 -8 -94 6 Z" {...inked(BRONZE, sw)} />
      <path d="M -92 -8 Q 0 -20 92 -8" {...line(sw, 0.7)} />
    </g>
  ),
};

// soldier_1940s: an olive tunic with flapped pockets and a round steel helmet
const OLIVE = "#6F7545";
const soldier1940s: CostumeDrawing = {
  sleeve: OLIVE,
  Torso: ({ sw }) => (
    <g>
      <path d={TORSO} {...inked(OLIVE, sw)} />
      <path d="M -52 -240 L -8 -194 L 0 -240 L 8 -194 L 52 -240 L 60 -214 L 12 -164 L -12 -164 L -60 -214 Z" {...inked("#5C6238", sw * 0.8)} />
      <rect x={-78} y={-150} width={52} height={44} rx={5} {...inked("#5C6238", sw * 0.8)} />
      <rect x={26} y={-150} width={52} height={44} rx={5} {...inked("#5C6238", sw * 0.8)} />
      <path d="M -78 -136 H -26 M 26 -136 H 78" {...line(sw, 0.5)} />
      <path d="M 0 -164 V 40" {...line(sw, 0.8)} />
      {buttons([-130, -96], 5, "#B9B38A", sw)}
      <rect x={-97} y={-62} width={194} height={26} {...inked(BELT, sw * 0.8)} />
      <rect x={-14} y={-60} width={28} height={22} rx={3} {...inked("#B9B38A", sw * 0.7)} />
    </g>
  ),
  Hat: ({ sw }) => (
    <g>
      <ellipse cx={0} cy={-4} rx={122} ry={15} {...inked("#5E6350", sw)} />
      <path d="M -102 -4 C -108 -108 108 -108 102 -4 Z" {...inked("#6C7159", sw)} />
      <path d="M -90 -34 Q 0 -60 90 -34 M -60 -62 Q 0 -80 60 -62" {...line(sw, 0.35)} />
    </g>
  ),
};

// sailor: a navy top with white stripes, a square back collar and a white cap
const NAVY = "#3F5A78";
const sailor: CostumeDrawing = {
  sleeve: NAVY,
  cuff: CREAM_W,
  Torso: ({ sw }) => (
    <g>
      <path d={TORSO} {...inked(NAVY, sw)} />
      <path d="M -96 -150 H 96 M -98 -112 H 98 M -99 -74 H 99 M -100 -36 H 100" fill="none" stroke={CREAM_W} strokeWidth={9} />
      <path d="M -92 -226 L -44 -240 L 44 -240 L 92 -226 L 80 -176 L 0 -108 L -80 -176 Z" {...inked("#2F4A66", sw * 0.9)} />
      <path d="M -86 -216 L 0 -120 L 86 -216" {...line(sw, 0.5)} stroke={CREAM_W} strokeWidth={6} />
      <path d="M -40 -238 L 0 -190 L 40 -238 Z" {...inked(CREAM_W, sw * 0.6)} />
      <path d="M -26 -166 L 0 -190 L 26 -166 L 18 -134 L -18 -134 Z" {...inked("#B04A4A", sw * 0.7)} />
    </g>
  ),
  Hat: ({ sw }) => (
    <g>
      <path d="M -88 -30 L -100 -74 Q 0 -102 100 -74 L 88 -30 Z" {...inked(CREAM_W, sw)} />
      <path d="M -94 4 Q 0 -10 94 4 L 90 -34 Q 0 -46 -90 -34 Z" {...inked(CREAM_W, sw)} />
      <path d="M -92 -14 Q 0 -26 92 -14" {...line(sw, 0.7)} stroke={NAVY} strokeWidth={sw} />
    </g>
  ),
};

// pilot: an early aviator in a leather jacket with a fleece collar and goggles
const LEATHER = "#7A5233";
const pilot: CostumeDrawing = {
  sleeve: LEATHER,
  cuff: "#E3D6B8",
  Torso: ({ sw }) => (
    <g>
      <path d={TORSO} {...inked(LEATHER, sw)} />
      <path d="M -34 -196 L 30 40" {...line(sw, 0.9)} />
      <path d="M -62 -150 L -34 -120 M -70 -100 L -40 -70" {...line(sw, 0.5)} />
      <rect x={30} y={-130} width={54} height={30} rx={5} {...inked("#6A4529", sw * 0.7)} />
      <rect x={-97} y={-52} width={194} height={22} {...inked("#5E3C24", sw * 0.8)} />
      {[-78, -52, -26, 0, 26, 52, 78].map((a, i) => {
        const t = ((a + 78) / 156) * Math.PI;
        return <circle key={i} cx={-Math.cos(t) * 80} cy={-232 + Math.sin(t) * 22} r={15} {...inked("#E3D6B8", sw * 0.7)} />;
      })}
    </g>
  ),
  Hat: ({ sw }) => (
    <g>
      <path d="M 98 8 L 114 42 L 94 48 L 84 4 Z M -98 8 L -114 42 L -94 48 L -84 4 Z" {...inked("#6A4529", sw * 0.9)} />
      <path d="M -98 6 C -104 -80 104 -80 98 6 Q 60 -4 0 -2 Q -60 -4 -98 6 Z" {...inked(LEATHER, sw)} />
      <path d="M 0 -76 V -34 M -44 -64 Q -40 -48 -30 -34 M 44 -64 Q 40 -48 30 -34" {...line(sw, 0.5)} />
      <path d="M -100 -22 Q 0 -34 100 -22" {...line(sw, 0.9)} strokeWidth={9} stroke="#3B2A20" />
      {[-34, 34].map((x) => (
        <g key={x}>
          <circle cx={x} cy={-24} r={22} {...inked("#B08A3E", sw * 0.9)} />
          <circle cx={x} cy={-24} r={14} {...inked("#BFD5E0", sw * 0.6)} />
        </g>
      ))}
    </g>
  ),
};

// explorer: a khaki bush shirt with pockets and a pith helmet
const BUSH = "#C2AA73";
const explorer: CostumeDrawing = {
  sleeve: BUSH,
  cuff: "#A8905C",
  Torso: ({ sw }) => (
    <g>
      <path d={TORSO} {...inked(BUSH, sw)} />
      <path d="M -50 -240 L -8 -192 L 0 -240 L 8 -192 L 50 -240 L 56 -214 L 10 -170 L -10 -170 L -56 -214 Z" {...inked("#A8905C", sw * 0.8)} />
      <path d="M 0 -170 V 40" {...line(sw, 0.8)} />
      {[-80, 30].map((x) => (
        <g key={x}>
          <rect x={x} y={-150} width={50} height={46} rx={5} {...inked("#A8905C", sw * 0.8)} />
          <path d={`M ${x} -136 H ${x + 50}`} {...line(sw, 0.5)} />
        </g>
      ))}
      {buttons([-128, -90], 5, "#6B5A3C", sw)}
      <rect x={-97} y={-62} width={194} height={22} {...inked(BELT, sw * 0.8)} />
    </g>
  ),
  Hat: ({ sw }) => (
    <g>
      <ellipse cx={0} cy={-2} rx={142} ry={16} {...inked("#DDD0AC", sw)} />
      <path d="M -98 -2 C -102 -122 102 -122 98 -2 Z" {...inked("#E5D8B6", sw)} />
      <path d="M -99 -20 Q 0 -34 99 -20 L 97 -6 Q 0 -20 -97 -6 Z" {...inked("#A8905C", sw * 0.8)} />
      <path d="M 0 -104 V -34 M -48 -92 Q -44 -60 -40 -34 M 48 -92 Q 44 -60 40 -34" {...line(sw, 0.4)} />
      <circle cx={0} cy={-98} r={7} {...inked("#A8905C", sw * 0.7)} />
    </g>
  ),
};

// scientist: a white lab coat over a shirt and tie; bareheaded
const scientist: CostumeDrawing = {
  sleeve: CREAM_W,
  cuff: "#D8D0BE",
  Torso: ({ sw }) => (
    <g>
      <path d={TORSO} {...inked(CREAM_W, sw)} />
      <path d="M -44 -240 L 0 -100 L 44 -240 Z" {...inked("#8FA9BC", sw * 0.8)} />
      <path d="M -10 -222 L 10 -222 L 18 -112 L 0 -96 L -18 -112 Z" {...inked("#7A4B5E", sw * 0.8)} />
      <path d="M -52 -240 L -14 -150 L -64 -116 L -90 -204 Z M 52 -240 L 14 -150 L 64 -116 L 90 -204 Z" {...inked("#E5DECE", sw * 0.8)} />
      <path d="M 0 -100 V 40" {...line(sw, 0.8)} />
      <rect x={30} y={-118} width={54} height={42} rx={5} {...inked("#E5DECE", sw * 0.8)} />
      <path d="M 50 -118 L 48 -142 M 62 -118 L 62 -140" fill="none" stroke="#B04A4A" strokeWidth={6} strokeLinecap="round" />
      <path d="M 62 -118 L 62 -140" fill="none" stroke="#3F5C70" strokeWidth={6} strokeLinecap="round" />
      {buttons([-72, -36], 5, "#B9B2A3", sw)}
    </g>
  ),
};

// monk: a brown habit with a rope belt; the hood hangs behind the head
const HABIT = "#7D5C3C";
const monk: CostumeDrawing = {
  sleeve: HABIT,
  Torso: ({ sw }) => (
    <g>
      <path d={WIDE(110)} {...inked(HABIT, sw)} />
      <path d="M -40 -240 L 0 -176 L 40 -240" {...inked("#5E4429", sw * 0.8)} />
      <path d="M -50 -170 L -60 40 M 50 -170 L 60 40 M 0 -176 V -70" {...line(sw, 0.5)} />
      <path d="M -108 -66 Q 0 -44 108 -66" fill="none" stroke="#D2C29A" strokeWidth={14} strokeLinecap="round" />
      <path d="M -108 -66 Q 0 -44 108 -66" {...line(sw, 0.45)} strokeDasharray="2 11" />
      <circle cx={24} cy={-52} r={13} {...inked("#D2C29A", sw * 0.7)} />
      <path d="M 24 -42 L 18 20 M 24 -42 L 42 14" fill="none" stroke="#D2C29A" strokeWidth={9} strokeLinecap="round" />
      <path d="M 18 20 L 14 32 M 42 14 L 46 26" {...line(sw, 0.5)} />
    </g>
  ),
  Back: ({ sw }) => (
    <g>
      <path d="M -122 90 C -142 -70 -84 -152 0 -152 C 84 -152 142 -70 122 90 Z" {...inked(HABIT, sw)} />
      <path d="M -96 40 C -108 -50 -60 -118 0 -118 C 60 -118 108 -50 96 40 Z" {...inked("#5B4129", sw * 0.8)} />
      <path d="M -112 20 Q -100 60 -116 84 M 112 20 Q 100 60 116 84" {...line(sw, 0.45)} />
    </g>
  ),
};

export const COSTUME_DRAWINGS: Record<Costume, CostumeDrawing> = {
  plain,
  dress,
  peasant,
  farmer,
  worker,
  clerk,
  noble,
  royal,
  knight,
  legionary,
  soldier_1910s: soldier1910s,
  soldier_1940s: soldier1940s,
  sailor,
  pilot,
  explorer,
  scientist,
  monk,
};
