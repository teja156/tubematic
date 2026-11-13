/*
 * The Process Cast stations: the furniture each kind of station stands on the
 * ground, the hanging station sign and one station's stretch of the ground
 * line. All in the house look (./ink): seeded wobbly ink that never boils,
 * coloured-pencil hatching, cream and wood.
 *
 * Every drawing here is rasterised once into a cached sprite, so each one puts
 * its own <Hatches /> in its SVG. Furniture stands with its bottom centre on the
 * ground at (0, 0) inside its STATIONS box (x in [-w/2, w/2], y in [-h, 0]); a
 * soft ground shadow may reach y +12. A prop rests at y = -top on furniture with
 * a top, or is pinned over the middle of a board, a door or a cell, so those
 * keep their middle quiet.
 */
import React from "react";
import { mix, rng } from "../characterKit/geometry";
import { STATIONS } from "./contract";
import {
  BEIGE, BEIGE_TONE, CREAM, CREAM_TONE, GREEN, Hatches, INK, Inked, LIME, MONO, RED, TEAL, WOOD, WOOD_TONE,
  boxPath, closedCurve, inkLine, openCurve, polyPath, tone, wobbleLoop, type Pt, type Tone,
} from "./ink";

const MUSTARD = "#D9A93A";
const TEAL_TONE = tone(TEAL);
const LIME_TONE = tone(LIME);
const RED_TONE = tone(RED);
const SLATE_TONE = tone(mix(TEAL, INK, 0.55));
const CORK_TONE = tone("#D9C7A2");
const CELL_TONE = tone(mix(LIME, CREAM, 0.72));
const DARK_WOOD_TONE = tone(mix(WOOD, INK, 0.22));

/** Flat tone, pencil hatching, a shade pass, then the ink outline. */
const Shaded: React.FC<{ d: string; k: string; t: Tone; sw?: number; shade?: number }> = ({ d, k, t, sw = 5, shade = 0.5 }) => (
  <g>
    <path d={d} fill={t.base} />
    <path d={d} fill={`url(#hatch-${k})`} />
    {shade > 0 && <path d={d} fill={`url(#shade-${k})`} opacity={shade} />}
    <path d={d} fill="none" stroke={INK} strokeWidth={sw} strokeLinejoin="round" />
  </g>
);

/** A wobbly circle or ellipse outline. */
const oval = (cx: number, cy: number, rx: number, ry: number, seed: number, amp = 1.6, n = 32) => {
  const pts: Pt[] = [];
  for (let i = 0; i < n; i++) {
    const a = (i / n) * Math.PI * 2;
    pts.push([cx + Math.cos(a) * rx, cy + Math.sin(a) * ry]);
  }
  return closedCurve(wobbleLoop(pts, [cx, cy], seed, amp));
};

const Shadow: React.FC<{ rx: number }> = ({ rx }) => <ellipse cx={0} cy={3} rx={rx} ry={8} fill={INK} opacity={0.1} />;

const Knob: React.FC<{ x: number; y: number; r?: number }> = ({ x, y, r = 7 }) => (
  <circle cx={x} cy={y} r={r} fill={MUSTARD} stroke={INK} strokeWidth={3} />
);

const Desk: React.FC<{ seed: number }> = ({ seed }) => {
  const { top } = STATIONS.desk;
  const front = boxPath(0, -62, 262, 120, seed, 2.2);
  const slab = boxPath(0, -top + 13, 284, 26, seed + 1, 1.8);
  return (
    <g>
      <Hatches tones={{ wood: WOOD_TONE, cream: CREAM_TONE }} />
      <Shadow rx={144} />
      <Shaded d={front} k="wood" t={WOOD_TONE} />
      <path d={inkLine([-124, -96], [124, -96], seed + 2, 1.2, 6)} stroke={INK} strokeWidth={3} fill="none" opacity={0.75} />
      <path d={inkLine([0, -94], [0, -6], seed + 3, 1.2, 4)} stroke={INK} strokeWidth={3} fill="none" opacity={0.75} />
      <Knob x={0} y={-110} />
      <Knob x={-22} y={-50} r={6} />
      <Knob x={22} y={-50} r={6} />
      <Inked d={slab} k="cream" tone={CREAM_TONE} />
    </g>
  );
};

/** Paper scraps pinned round the edge of the board, leaving the middle for a pinned prop. */
const SCRAPS = [
  { x: -92, y: -290, w: 58, h: 38, rot: -6, fill: CREAM, pin: RED },
  { x: 88, y: -286, w: 52, h: 44, rot: 7, fill: "#CFE3DF", pin: TEAL },
  { x: 100, y: -97, w: 46, h: 32, rot: -4, fill: "#E2E6B8", pin: GREEN },
];

const Board: React.FC<{ seed: number }> = ({ seed }) => {
  const frame = boxPath(0, -196, 290, 258, seed, 2.4);
  const cork = boxPath(0, -196, 260, 228, seed + 1, 1.8);
  return (
    <g>
      <Hatches tones={{ wood: WOOD_TONE, cork: CORK_TONE }} />
      <Shadow rx={140} />
      {[-1, 1].map((s) => (
        <g key={s}>
          <path d={inkLine([s * 96, -90], [s * 124, -2], seed + 3 + s, 1.5, 4)} stroke={INK} strokeWidth={17} strokeLinecap="round" fill="none" />
          <path d={inkLine([s * 96, -90], [s * 124, -2], seed + 3 + s, 1.5, 4)} stroke={WOOD} strokeWidth={10} strokeLinecap="round" fill="none" />
        </g>
      ))}
      <Shaded d={frame} k="wood" t={WOOD_TONE} shade={0.35} />
      <Inked d={cork} k="cork" tone={CORK_TONE} sw={3} />
      {SCRAPS.map((c, i) => {
        const d = boxPath(0, 0, c.w, c.h, seed + 10 + i, 1.4);
        return (
          <g key={i} transform={`translate(${c.x} ${c.y}) rotate(${c.rot})`}>
            <path d={d} fill={c.fill} stroke={INK} strokeWidth={2.5} />
            <path d={inkLine([-c.w / 2 + 9, -1], [c.w / 2 - 12, -1], seed + 20 + i, 0.8, 3)} stroke={INK} strokeWidth={2} opacity={0.45} fill="none" />
            <path d={inkLine([-c.w / 2 + 9, 8], [c.w / 2 - 22, 8], seed + 30 + i, 0.8, 3)} stroke={INK} strokeWidth={2} opacity={0.35} fill="none" />
            <circle cx={0} cy={-c.h / 2 + 5} r={5} fill={c.pin} stroke={INK} strokeWidth={1.8} />
          </g>
        );
      })}
      <circle cx={-104} cy={-100} r={5} fill={TEAL} stroke={INK} strokeWidth={1.8} />
    </g>
  );
};

const Door: React.FC<{ seed: number }> = ({ seed }) => {
  const frame = boxPath(0, -187, 212, 370, seed, 1.8);
  const door = boxPath(0, -176, 172, 348, seed + 1, 1.8);
  const pane = boxPath(0, -298, 92, 58, seed + 2, 1.6);
  return (
    <g>
      <Hatches tones={{ frame: DARK_WOOD_TONE, wood: WOOD_TONE, cream: CREAM_TONE }} />
      <Shadow rx={108} />
      <Shaded d={frame} k="frame" t={DARK_WOOD_TONE} shade={0.4} />
      <Shaded d={door} k="wood" t={WOOD_TONE} shade={0.3} />
      <path d={pane} fill="#CFE3DF" />
      <path d={pane} fill="url(#hatch-cream)" opacity={0.7} />
      <path d={inkLine([0, -326], [0, -270], seed + 3, 1, 3)} stroke={INK} strokeWidth={3.5} fill="none" />
      <path d={inkLine([-44, -298], [44, -298], seed + 4, 1, 3)} stroke={INK} strokeWidth={3.5} fill="none" />
      <path d={pane} fill="none" stroke={INK} strokeWidth={4.5} strokeLinejoin="round" />
      {[[-200, 104], [-82, 104]].map(([cy, h], i) => (
        <path key={i} d={boxPath(0, cy, 124, h, seed + 5 + i, 1.4)} fill="none" stroke={INK} strokeWidth={3} opacity={0.55} />
      ))}
      {[-318, -58].map((y, i) => (
        <path key={i} d={boxPath(-86, y, 10, 28, seed + 8 + i, 0.8)} fill={INK} opacity={0.75} />
      ))}
      <Knob x={64} y={-168} r={10} />
    </g>
  );
};

const Shelf: React.FC<{ seed: number }> = ({ seed }) => {
  const { top } = STATIONS.shelf;
  const back = boxPath(0, -147, 236, 270, seed, 1.6);
  const plank = (y: number, w: number, h: number, s: number) => boxPath(0, y, w, h, s, 1.6);
  return (
    <g>
      <Hatches tones={{ wood: WOOD_TONE, beige: BEIGE_TONE }} />
      <Shadow rx={132} />
      <Inked d={back} k="beige" tone={BEIGE_TONE} sw={3.5} />
      <path d={back} fill="url(#shade-beige)" opacity={0.6} />
      {[-1, 1].map((s) => (
        <Shaded key={s} d={boxPath(s * 121, -146, 22, 290, seed + 2 + s, 1.6)} k="wood" t={WOOD_TONE} shade={s > 0 ? 0.5 : 0} />
      ))}
      {[-196, -102].map((y, i) => <Shaded key={i} d={plank(y, 236, 16, seed + 6 + i)} k="wood" t={WOOD_TONE} sw={4} shade={0} />)}
      <Shaded d={plank(-14, 258, 18, seed + 9)} k="wood" t={WOOD_TONE} sw={4.5} shade={0.3} />
      <Shaded d={plank(-top + 14, 264, 22, seed + 10)} k="wood" t={WOOD_TONE} shade={0} />
    </g>
  );
};

const Machine: React.FC<{ seed: number }> = ({ seed }) => {
  const { top } = STATIONS.machine;
  const body = boxPath(0, -top + 132, 272, 254, seed, 2.2);
  const panel = boxPath(0, -146, 226, 196, seed + 1, 1.8);
  return (
    <g>
      <Hatches tones={{ teal: TEAL_TONE, cream: CREAM_TONE, lime: LIME_TONE, red: RED_TONE }} />
      <Shadow rx={140} />
      {[-1, 1].map((s) => (
        <path key={s} d={boxPath(s * 92, -12, 34, 22, seed + 2 + s, 1)} fill={INK} />
      ))}
      <Shaded d={body} k="teal" t={TEAL_TONE} shade={0.45} />
      <Inked d={panel} k="cream" tone={CREAM_TONE} sw={4} />
      {/* the input slot */}
      <path d={boxPath(0, -218, 150, 22, seed + 4, 1.2)} fill={INK} />
      <path d={inkLine([-60, -244], [-20, -244], seed + 5, 0.8, 3)} stroke={INK} strokeWidth={3} fill="none" opacity={0.5} />
      {/* two dials */}
      {[-62, 0].map((x, i) => (
        <g key={i}>
          <path d={oval(x, -150, 26, 26, seed + 6 + i, 1.2)} fill={BEIGE} stroke={INK} strokeWidth={4} />
          {[-50, -10, 30].map((a) => {
            const r = (a - 90) * (Math.PI / 180);
            return <line key={a} x1={x + Math.cos(r) * 17} y1={-150 + Math.sin(r) * 17} x2={x + Math.cos(r) * 22} y2={-150 + Math.sin(r) * 22} stroke={INK} strokeWidth={2.5} />;
          })}
          <line x1={x} y1={-150} x2={x + (i ? 12 : -10)} y2={-164} stroke={RED} strokeWidth={4} strokeLinecap="round" />
          <circle cx={x} cy={-150} r={3.5} fill={INK} />
        </g>
      ))}
      {/* the lights */}
      <path d={oval(68, -160, 15, 15, seed + 9, 1)} fill={LIME} stroke={INK} strokeWidth={4} />
      <circle cx={63} cy={-165} r={4} fill="#FFFDF6" opacity={0.8} />
      <path d={oval(68, -122, 9, 9, seed + 10, 0.8)} fill={RED} stroke={INK} strokeWidth={3} />
      {/* the output chute */}
      <path d={boxPath(0, -84, 124, 30, seed + 11, 1.2)} fill={mix(INK, TEAL, 0.25)} stroke={INK} strokeWidth={4} />
      <path d={polyPath([[-70, -66], [70, -66], [62, -54], [-62, -54]], seed + 12, 1, 2)} fill={BEIGE} stroke={INK} strokeWidth={3.5} strokeLinejoin="round" />
      {[[-122, -260], [122, -260], [-122, -36], [122, -36]].map(([x, y], i) => (
        <circle key={i} cx={x} cy={y} r={3.5} fill={INK} opacity={0.6} />
      ))}
    </g>
  );
};

const LIGHTS = [LIME, GREEN, RED, TEAL, MUSTARD];

const Server: React.FC<{ seed: number }> = ({ seed }) => {
  const { top } = STATIONS.server;
  const rack = boxPath(0, -top / 2 - 5, 206, top - 22, seed, 1.8);
  const r = rng(seed + 1);
  const rows = [-318, -268, -218, -168, -118, -68];
  return (
    <g>
      <Hatches tones={{ slate: SLATE_TONE, cream: CREAM_TONE, beige: BEIGE_TONE }} />
      <Shadow rx={102} />
      {[-1, 1].map((s) => <path key={s} d={boxPath(s * 76, -9, 30, 18, seed + 2 + s, 1)} fill={INK} />)}
      <Shaded d={rack} k="slate" t={SLATE_TONE} shade={0.35} />
      {rows.map((cy, i) => {
        const unit = boxPath(0, cy, 176, 40, seed + 10 + i, 1.4);
        const lights = [0, 1, 2].map(() => LIGHTS[Math.floor(r() * LIGHTS.length)]);
        const k = i % 2 ? "beige" : "cream";
        return (
          <g key={i}>
            <Inked d={unit} k={k} tone={i % 2 ? BEIGE_TONE : CREAM_TONE} sw={3.5} />
            {lights.map((c, j) => (
              <circle key={j} cx={-66 + j * 17} cy={cy} r={5.5} fill={c} stroke={INK} strokeWidth={2} />
            ))}
            <path d={inkLine([-6, cy], [26, cy], seed + 20 + i, 0.6, 3)} stroke={INK} strokeWidth={3} fill="none" opacity={0.6} />
            {[0, 1, 2, 3].map((j) => (
              <line key={j} x1={42 + j * 11} y1={cy - 10} x2={42 + j * 11} y2={cy + 10} stroke={INK} strokeWidth={2.5} opacity={0.5} />
            ))}
          </g>
        );
      })}
      {[0, 1, 2, 3, 4, 5].map((j) => (
        <line key={j} x1={-50 + j * 20} y1={-36} x2={-50 + j * 20 + 8} y2={-26} stroke={CREAM} strokeWidth={3} opacity={0.55} strokeLinecap="round" />
      ))}
    </g>
  );
};

const Cell: React.FC<{ seed: number }> = ({ seed }) => {
  const cy = -150;
  const outer = oval(0, cy, 162, 144, seed, 3, 40);
  const inner = oval(0, cy, 144, 127, seed + 1, 2.4, 40);
  const r = rng(seed + 2);
  const ticks: React.ReactNode[] = [];
  for (let i = 0; i < 64; i++) {
    const a = (i / 64) * Math.PI * 2;
    const c = Math.cos(a), s = Math.sin(a);
    ticks.push(
      <g key={i}>
        <line x1={c * 147} y1={cy + s * 130} x2={c * 156} y2={cy + s * 138} stroke={INK} strokeWidth={2} opacity={0.45} />
        <circle cx={c * 157} cy={cy + s * 139.5} r={3} fill={mix(LIME, INK, 0.25)} opacity={0.7} />
      </g>,
    );
  }
  // Ribosome dots round the rim, outside the middle where a prop is pinned.
  const dots: Pt[] = [];
  while (dots.length < 16) {
    const x = (r() * 2 - 1) * 128, y = cy + (r() * 2 - 1) * 112;
    const inCell = (x / 132) ** 2 + ((y - cy) / 116) ** 2 < 1;
    const inMiddle = Math.abs(x) < 104 && Math.abs(y + 165) < 78;
    if (inCell && !inMiddle) dots.push([x, y]);
  }
  return (
    <g>
      <Hatches tones={{ lime: LIME_TONE, cell: CELL_TONE, teal: TEAL_TONE, red: RED_TONE }} />
      <Shadow rx={150} />
      <Inked d={outer} k="lime" tone={LIME_TONE} sw={6} />
      {ticks}
      <Inked d={inner} k="cell" tone={CELL_TONE} sw={3.5} />
      {/* nucleus, upper left */}
      <Shaded d={oval(-50, -212, 36, 28, seed + 3, 2)} k="teal" t={TEAL_TONE} sw={4.5} shade={0.35} />
      <path d={oval(-46, -214, 10, 8, seed + 4, 1)} fill={mix(TEAL, INK, 0.45)} />
      {/* mitochondrion, lower right */}
      <g transform="translate(60 -74) rotate(-18)">
        <Shaded d={oval(0, 0, 36, 17, seed + 5, 1.4)} k="red" t={RED_TONE} sw={4} shade={0} />
        <path d={openCurve([[-24, 0], [-16, -8], [-8, 7], [0, -8], [8, 7], [16, -8], [24, 0]])} stroke={INK} strokeWidth={2.5} fill="none" opacity={0.7} />
      </g>
      {/* a fold of membrane inside, lower left */}
      <path d={openCurve([[-108, -112], [-90, -96], [-100, -80], [-80, -66], [-88, -50]])} stroke={mix(LIME, INK, 0.35)} strokeWidth={6} fill="none" strokeLinecap="round" />
      {dots.map(([x, y], i) => <circle key={i} cx={x} cy={y} r={4} fill={mix(LIME, INK, 0.5)} opacity={0.75} />)}
    </g>
  );
};

/** Station furniture by kind; a stage has none. */
export const FURNITURE: Record<"desk" | "board" | "door" | "shelf" | "machine" | "server" | "cell", React.FC<{ seed: number }>> = {
  desk: Desk,
  board: Board,
  door: Door,
  shelf: Shelf,
  machine: Machine,
  server: Server,
  cell: Cell,
};

const SIGN_H = 86;
const SIGN_STRING = 180;

/** The sign's font size and board width for a text: up to 14 characters fit within 560 px. */
function signSize(text: string): { fs: number; w: number } {
  const n = Math.max(1, text.length);
  const fs = Math.min(52, 560 / (n * 0.6));
  return { fs, w: Math.max(180, n * fs * 0.6 + 64) };
}

/**
 * Every pixel of a sign, strings included, around its centre (0, 0). The board
 * is `w` = max(180, chars x fs x 0.6 + 64) wide (fs = min(52, 560 / (chars x 0.6)),
 * so at most 624 for an over-long text) and 86 tall; the strings go 180 px up
 * from its top edge. 8 px of room covers the wobble and the outline.
 */
export function signBox(text: string): { left: number; top: number; width: number; height: number } {
  const { w } = signSize(text);
  return { left: -w / 2 - 8, top: -SIGN_H / 2 - SIGN_STRING - 4, width: w + 16, height: SIGN_H + SIGN_STRING + 12 };
}

/** The hanging station sign: a cream board on two strings, the name in mono ink. Centre at (0, 0). */
export const Sign: React.FC<{ text: string; seed: number }> = ({ text, seed }) => {
  const { fs, w } = signSize(text);
  const h = SIGN_H;
  const d = boxPath(0, 0, w, h, seed, 2.6);
  const sx = w / 2 - 34;
  return (
    <g>
      <Hatches tones={{ cream: CREAM_TONE }} />
      {[-1, 1].map((s) => (
        <path key={s} d={inkLine([s * sx, -h / 2 - SIGN_STRING], [s * sx, -h / 2 + 4], seed + 1 + s, 1.2, 5)} stroke={INK} strokeWidth={3} fill="none" opacity={0.8} />
      ))}
      <Inked d={d} k="cream" tone={CREAM_TONE} />
      {[-1, 1].map((s) => <circle key={s} cx={s * sx} cy={-h / 2 + 12} r={5} fill={INK} />)}
      <text x={0} y={fs * 0.36} textAnchor="middle" fontFamily={MONO} fontWeight={700} fontSize={fs} fill={INK}>
        {text}
      </text>
    </g>
  );
};

const STRIP = 540;

/** A wobbly rule across the strip; its ends sit on the line so neighbouring strips join. */
const rulePath = (seed: number, amp: number) => {
  const r = rng(seed);
  const pts: Pt[] = [];
  for (let x = -STRIP; x <= STRIP; x += 60) pts.push([x, x === -STRIP || x === STRIP ? 0 : (r() - 0.5) * amp]);
  return openCurve(pts);
};

/**
 * One station's stretch of the ground line, x -540 to 540 at y 0, every pixel
 * within y [-40, 60]. The band's hatching repeats every 12 px and the teal
 * dashes every 36 px, both whole divisors of 1080, so strips side by side join
 * without a seam.
 */
export const GroundStrip: React.FC<{ seed: number }> = ({ seed }) => {
  const r = rng(seed + 7);
  const tufts: { x: number; s: number; flip: number }[] = [];
  for (let x = -490 + r() * 90; x < 470; x += 150 + r() * 170) tufts.push({ x, s: 0.75 + r() * 0.45, flip: r() > 0.5 ? 1 : -1 });
  const dark = mix(WOOD, INK, 0.3), light = mix(WOOD, "#FFFFFF", 0.3);
  return (
    <g>
      <defs>
        <pattern id="pc-ground-hatch" width={12} height={12} patternUnits="userSpaceOnUse">
          <line x1={-3} y1={3} x2={3} y2={-3} stroke={dark} strokeWidth={2.2} opacity={0.45} />
          <line x1={0} y1={12} x2={12} y2={0} stroke={dark} strokeWidth={2.2} opacity={0.45} />
          <line x1={9} y1={15} x2={15} y2={9} stroke={dark} strokeWidth={2.2} opacity={0.45} />
          <line x1={0} y1={6} x2={6} y2={0} stroke={light} strokeWidth={1.6} opacity={0.45} />
          <line x1={6} y1={12} x2={12} y2={6} stroke={light} strokeWidth={1.6} opacity={0.45} />
        </pattern>
      </defs>
      <rect x={-STRIP} y={3} width={STRIP * 2} height={19} fill={WOOD} />
      <rect x={-STRIP} y={3} width={STRIP * 2} height={19} fill="url(#pc-ground-hatch)" />
      <path d={rulePath(seed, 3.4)} stroke={INK} strokeWidth={5} fill="none" />
      <g transform="translate(0 22)"><path d={rulePath(seed + 1, 2.6)} stroke={INK} strokeWidth={3.2} fill="none" /></g>
      <line x1={-STRIP} y1={36} x2={STRIP} y2={36} stroke={TEAL} strokeWidth={3.5} strokeDasharray="22 14" opacity={0.85} />
      <g transform="translate(0 50)"><path d={rulePath(seed + 2, 2.6)} stroke={INK} strokeWidth={2} fill="none" opacity={0.5} /></g>
      {tufts.map((t, i) => (
        <g key={i} transform={`translate(${t.x.toFixed(1)} 0) scale(${(t.s * t.flip).toFixed(2)} ${t.s.toFixed(2)})`} stroke={INK} strokeWidth={3} fill="none" strokeLinecap="round" opacity={0.8}>
          <path d="M0 0Q-3 -14 -10 -22" />
          <path d="M5 0Q6 -18 3 -30" />
          <path d="M10 0Q14 -10 22 -15" />
        </g>
      ))}
    </g>
  );
};
