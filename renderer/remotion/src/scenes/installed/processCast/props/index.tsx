/*
 * The Process Cast prop library: one static drawing per prop id, centred on
 * (0, 0) with every pixel inside its PROPS box (../contract) and about 6 px of
 * room to spare. Same house look as the cast (../ink): flat tone, pencil
 * hatching, seeded wobbly ink.
 *
 * Each drawing is rasterised once into a cached sprite, so each puts its own
 * <Hatches /> in its SVG. A label is JetBrains Mono 700, sized so the whole
 * text fits its label area: it may wrap onto up to three lines at a space or
 * after . / @ : - and never runs outside the area.
 */
import React from "react";
import { mix, rng, tubeP } from "../../characterKit/geometry";
import type { PropId } from "../contract";
import {
  BEIGE, CREAM, CREAM_TONE, BEIGE_TONE, GREEN, Hatches, INK, LIME, MONO, RED, TEAL, WOOD, WOOD_TONE,
  boxPath, closedCurve, inkLine, polyPath, tone, wobbleLoop, type Pt, type Tone,
} from "../ink";

const MUSTARD = "#D9A93A";
const T = {
  wood: WOOD_TONE,
  cream: CREAM_TONE,
  beige: BEIGE_TONE,
  teal: tone(TEAL),
  lime: tone(LIME),
  red: tone(RED),
  mustard: tone(MUSTARD),
  slate: tone(mix(TEAL, INK, 0.55)),
  steel: tone("#B4AEA3"),
  glass: tone("#F3E2A6"),
  lens: tone("#CFE3DF"),
};
type ToneKey = keyof typeof T;

const Defs: React.FC<{ k: ToneKey[] }> = ({ k }) => <Hatches tones={Object.fromEntries(k.map((x) => [x, T[x]])) as Record<string, Tone>} />;

/** Flat tone, hatching, an optional shade pass, ink outline. `evenOdd` cuts holes. */
const Shape: React.FC<{ d: string; k: ToneKey; sw?: number; shade?: number; evenOdd?: boolean }> = ({ d, k, sw = 5, shade = 0, evenOdd }) => {
  const rule = evenOdd ? "evenodd" : undefined;
  return (
    <g>
      <path d={d} fill={T[k].base} fillRule={rule} />
      <path d={d} fill={`url(#hatch-${k})`} fillRule={rule} />
      {shade > 0 && <path d={d} fill={`url(#shade-${k})`} fillRule={rule} opacity={shade} />}
      <path d={d} fill="none" stroke={INK} strokeWidth={sw} strokeLinejoin="round" />
    </g>
  );
};

/** A wobbly ellipse. */
const oval = (cx: number, cy: number, rx: number, ry: number, seed: number, amp = 1.4, n = 28) => {
  const pts: Pt[] = [];
  for (let i = 0; i < n; i++) {
    const a = (i / n) * Math.PI * 2;
    pts.push([cx + Math.cos(a) * rx, cy + Math.sin(a) * ry]);
  }
  return closedCurve(wobbleLoop(pts, [cx, cy], seed, amp));
};

const rect = (x0: number, y0: number, x1: number, y1: number): Pt[] => [[x0, y0], [x1, y0], [x1, y1], [x0, y1]];

// ---- labels ---------------------------------------------------------------

const ADVANCE = 0.61; // JetBrains Mono advances 0.6 em a character; a hair more for safety.
const LEADING = 1.2;

/** Pieces a label may break after: a space, or . / @ : - */
function pieces(text: string): string[] {
  const out: string[] = [];
  let cur = "";
  for (const ch of text) {
    cur += ch;
    if (" ./@:-".includes(ch)) {
      out.push(cur);
      cur = "";
    }
  }
  if (cur) out.push(cur);
  return out;
}

/** The text in 1 to 3 lines, and the largest size at which it fits w x h (capped at maxFs). */
export function fitLabel(text: string, w: number, h: number, maxFs: number): { lines: string[]; fs: number } {
  const p = pieces(text);
  const join = (a: number, b: number) => p.slice(a, b).join("").trim();
  const options: string[][] = [[text.trim()]];
  for (let i = 1; i < p.length; i++) {
    options.push([join(0, i), join(i, p.length)]);
    for (let j = i + 1; j < p.length; j++) options.push([join(0, i), join(i, j), join(j, p.length)]);
  }
  let best = { lines: [text.trim()], fs: 0 };
  for (const lines of options) {
    const longest = Math.max(1, ...lines.map((l) => l.length));
    const fs = Math.min(maxFs, w / (longest * ADVANCE), h / (lines.length * LEADING));
    if (fs > best.fs + 0.01) best = { lines, fs };
  }
  return best;
}

/** A label centred on (cx, cy) inside a w x h area. */
const Label: React.FC<{ text: string; cx: number; cy: number; w: number; h: number; maxFs: number; fill?: string }> = ({
  text, cx, cy, w, h, maxFs, fill = INK,
}) => {
  if (!text.trim()) return null;
  const { lines, fs } = fitLabel(text, w, h, maxFs);
  return (
    <text textAnchor="middle" fontFamily={MONO} fontWeight={700} fontSize={fs.toFixed(2)} fill={fill}>
      {lines.map((l, i) => (
        <tspan key={i} x={cx} y={(cy + (i - (lines.length - 1) / 2) * fs * LEADING + fs * 0.36).toFixed(1)}>
          {l}
        </tspan>
      ))}
    </text>
  );
};

// ---- the props ------------------------------------------------------------

const Card: React.FC<{ text: string }> = ({ text }) => {
  const d = boxPath(0, 0, 174, 96, 5101, 2);
  return (
    <g>
      <Defs k={["cream"]} />
      <Shape d={d} k="cream" sw={4.5} />
      <path d={boxPath(-66, -30, 16, 16, 5102, 0.8)} fill={CREAM} stroke={INK} strokeWidth={2.5} />
      <path d="M-72 -31L-67 -25L-58 -38" stroke={GREEN} strokeWidth={4} fill="none" strokeLinecap="round" strokeLinejoin="round" />
      <path d={inkLine([-50, -27], [74, -27], 5103, 1, 5)} stroke={RED} strokeWidth={2.5} opacity={0.6} fill="none" />
      <Label text={text} cx={0} cy={13} w={152} h={52} maxFs={34} />
    </g>
  );
};

const Envelope: React.FC<{ text: string }> = ({ text }) => {
  const body = boxPath(0, 0, 170, 104, 5201, 2);
  const flap = polyPath([[-80, -46], [80, -46], [0, -4]], 5202, 1.4, 4);
  return (
    <g>
      <Defs k={["cream", "beige", "red"]} />
      <Shape d={body} k="cream" sw={4.5} />
      <Shape d={flap} k="beige" sw={3.5} />
      <path d={oval(0, -8, 11, 11, 5203, 0.8)} fill={RED} stroke={INK} strokeWidth={3} />
      <Label text={text} cx={0} cy={27} w={138} h={34} maxFs={28} />
    </g>
  );
};

const Packet: React.FC<{ text: string }> = ({ text }) => {
  const front = polyPath(rect(-72, -34, 54, 52), 5301, 1.6, 4);
  const top = polyPath([[-72, -34], [54, -34], [72, -52], [-54, -52]], 5302, 1.2, 3);
  const side = polyPath([[54, -34], [72, -52], [72, 34], [54, 52]], 5303, 1.2, 3);
  const label = boxPath(-9, 12, 108, 54, 5304, 1.4);
  return (
    <g>
      <Defs k={["teal", "cream", "lime"]} />
      <Shape d={side} k="teal" sw={4.5} shade={0.8} />
      <Shape d={top} k="teal" sw={4.5} />
      <path d={top} fill={T.teal.light} opacity={0.35} />
      <path d={polyPath([[-20, -34], [0, -34], [18, -52], [-2, -52]], 5305, 0.6, 2)} fill={LIME} stroke={INK} strokeWidth={2.5} />
      <Shape d={front} k="teal" sw={5} />
      <path d={polyPath(rect(-20, -34, 0, -18), 5306, 0.6, 2)} fill={LIME} stroke={INK} strokeWidth={2.5} />
      <Shape d={label} k="cream" sw={3.5} />
      <Label text={text} cx={-9} cy={12} w={96} h={46} maxFs={30} />
    </g>
  );
};

const Box: React.FC<{ text: string }> = ({ text }) => {
  const front = polyPath(rect(-66, -22, 66, 60), 5401, 1.6, 4);
  const left = polyPath([[-66, -22], [-8, -22], [-22, -56], [-72, -44]], 5402, 1.2, 3);
  const right = polyPath([[8, -22], [66, -22], [72, -44], [22, -56]], 5403, 1.2, 3);
  const label = boxPath(0, 20, 104, 50, 5404, 1.4);
  return (
    <g>
      <Defs k={["wood", "beige"]} />
      <path d={polyPath([[-58, -22], [58, -22], [50, -34], [-50, -34]], 5405, 0.8, 2)} fill={mix(WOOD, INK, 0.55)} stroke={INK} strokeWidth={3.5} />
      <Shape d={left} k="wood" sw={4} shade={0.6} />
      <Shape d={right} k="wood" sw={4} shade={0.6} />
      <Shape d={front} k="wood" sw={5} />
      <Shape d={label} k="beige" sw={3.5} />
      <Label text={text} cx={0} cy={20} w={94} h={40} maxFs={30} />
    </g>
  );
};

const File: React.FC<{ text: string }> = ({ text }) => {
  const sheet = polyPath([[-56, -76], [30, -76], [56, -50], [56, 76], [-56, 76]], 5501, 1.4, 4);
  const fold = polyPath([[30, -76], [30, -50], [56, -50]], 5502, 0.6, 2);
  return (
    <g>
      <Defs k={["cream", "beige"]} />
      <Shape d={sheet} k="cream" sw={4.5} />
      <Shape d={fold} k="beige" sw={3} />
      <Label text={text} cx={-2} cy={-26} w={92} h={52} maxFs={30} />
      {[16, 32, 48, 62].map((y, i) => (
        <path key={i} d={inkLine([-40, y], [i === 3 ? 10 : 40, y], 5503 + i, 0.8, 4)} stroke={INK} strokeWidth={2.5} opacity={0.4} fill="none" />
      ))}
    </g>
  );
};

const Folder: React.FC<{ text: string }> = ({ text }) => {
  const back = polyPath([[-82, -48], [-82, -60], [-30, -60], [-20, -48], [82, -48], [82, 62], [-82, 62]], 5601, 1.4, 3);
  const paper = polyPath(rect(-68, -56, 70, -30), 5602, 1, 3);
  const front = polyPath([[-82, -32], [78, -36], [82, 62], [-82, 62]], 5603, 1.6, 4);
  const label = boxPath(0, 14, 124, 48, 5604, 1.4);
  return (
    <g>
      <Defs k={["mustard", "cream"]} />
      <Shape d={back} k="mustard" sw={4.5} shade={0.6} />
      <path d={paper} fill={CREAM} stroke={INK} strokeWidth={3} />
      <Shape d={front} k="mustard" sw={5} />
      <Shape d={label} k="cream" sw={3.5} />
      <Label text={text} cx={0} cy={14} w={112} h={38} maxFs={30} />
    </g>
  );
};

const Key: React.FC = () => {
  const bow = oval(-46, 0, 28, 28, 5701, 1.2) + oval(-46, 0, 11, 11, 5702, 0.6);
  const blade = polyPath(
    [[-20, -9], [72, -9], [72, 30], [62, 30], [62, 20], [54, 20], [54, 32], [44, 32], [44, 9], [-20, 9]],
    5703, 1, 2,
  );
  return (
    <g>
      <Defs k={["mustard"]} />
      <Shape d={blade} k="mustard" sw={4.5} />
      <Shape d={bow} k="mustard" sw={5} evenOdd shade={0.4} />
      <circle cx={-56} cy={-12} r={4} fill="#FFFDF6" opacity={0.7} />
    </g>
  );
};

const Lock: React.FC = () => {
  const arc: Pt[] = [];
  for (let i = 0; i <= 16; i++) {
    const a = Math.PI + (i / 16) * Math.PI;
    arc.push([Math.cos(a) * 28, -34 + Math.sin(a) * 28]);
  }
  const shackle = tubeP([[-28, -8], ...arc, [28, -8]], 15);
  const body = boxPath(0, 27, 96, 82, 5801, 2);
  return (
    <g>
      <Defs k={["steel", "mustard"]} />
      <Shape d={shackle} k="steel" sw={4.5} />
      <Shape d={body} k="mustard" sw={5} shade={0.35} />
      <circle cx={0} cy={18} r={10} fill={INK} />
      <path d="M-5 22L-8 44H8L5 22Z" fill={INK} />
    </g>
  );
};

const Coin: React.FC = () => (
  <g>
    <Defs k={["mustard"]} />
    <Shape d={oval(0, 0, 46, 46, 5901, 1.2)} k="mustard" sw={5} shade={0.3} />
    <path d={oval(0, 0, 35, 35, 5902, 1)} fill="none" stroke={INK} strokeWidth={2.5} opacity={0.6} />
    <path d="M13 -15C8 -23 -14 -23 -13 -10C-12 0 14 -1 14 11C14 23 -8 25 -15 15" stroke={INK} strokeWidth={5.5} fill="none" strokeLinecap="round" />
    <path d="M0 -27V27" stroke={INK} strokeWidth={5} strokeLinecap="round" />
  </g>
);

const Cookie: React.FC = () => {
  const bc: Pt = [40, -40];
  const br = 26;
  const pts: Pt[] = [];
  for (let i = 0; i < 48; i++) {
    const a = (i / 48) * Math.PI * 2;
    let p: Pt = [Math.cos(a) * 51, Math.sin(a) * 51];
    const dx = p[0] - bc[0], dy = p[1] - bc[1];
    const dist = Math.hypot(dx, dy);
    if (dist < br) p = [bc[0] + (dx / dist) * br, bc[1] + (dy / dist) * br];
    pts.push(p);
  }
  const d = closedCurve(wobbleLoop(pts, [0, 0], 6001, 1.6));
  const r = rng(6002);
  const chips: Pt[] = [];
  while (chips.length < 6) {
    const x = (r() * 2 - 1) * 34, y = (r() * 2 - 1) * 34;
    if (Math.hypot(x - bc[0], y - bc[1]) > br + 12 && Math.hypot(x, y) < 38 && chips.every((c) => Math.hypot(c[0] - x, c[1] - y) > 18)) chips.push([x, y]);
  }
  return (
    <g>
      <Defs k={["wood"]} />
      <Shape d={d} k="wood" sw={5} shade={0.3} />
      {chips.map(([x, y], i) => (
        <path key={i} d={oval(x, y, 6.5, 5.5, 6010 + i, 1, 10)} fill={mix(WOOD, INK, 0.62)} />
      ))}
      <circle cx={46} cy={-8} r={3} fill={BEIGE} stroke={INK} strokeWidth={1.5} />
      <circle cx={8} cy={-48} r={2.5} fill={BEIGE} stroke={INK} strokeWidth={1.5} />
    </g>
  );
};

const Gear: React.FC = () => {
  const pts: Pt[] = [];
  const teeth = 8;
  for (let i = 0; i < teeth; i++) {
    const a = (i / teeth) * Math.PI * 2;
    for (const [da, r] of [[-0.3, 46], [-0.17, 57], [0.17, 57], [0.3, 46]] as const) {
      pts.push([Math.cos(a + da) * r, Math.sin(a + da) * r]);
    }
  }
  const d = polyPath(pts, 6101, 0.8, 2) + oval(0, 0, 15, 15, 6102, 0.6);
  return (
    <g>
      <Defs k={["teal"]} />
      <Shape d={d} k="teal" sw={5} evenOdd shade={0.35} />
      <path d={oval(0, 0, 30, 30, 6103, 1)} fill="none" stroke={INK} strokeWidth={2.5} opacity={0.55} />
    </g>
  );
};

const Bug: React.FC = () => {
  const legs: [Pt, Pt][] = [
    [[30, -10], [58, -26]],
    [[36, 12], [62, 12]],
    [[30, 36], [56, 54]],
  ];
  return (
    <g>
      <Defs k={["red"]} />
      {legs.flatMap(([a, b], i) =>
        [-1, 1].map((s) => (
          <path key={`${i}${s}`} d={inkLine([s * a[0], a[1]], [s * b[0], b[1]], 6201 + i * 2 + s, 1.2, 3)} stroke={INK} strokeWidth={5} strokeLinecap="round" fill="none" />
        )),
      )}
      {[-1, 1].map((s) => (
        <g key={s}>
          <path d={`M${s * 7} -50Q${s * 12} -60 ${s * 22} -58`} stroke={INK} strokeWidth={3.5} fill="none" strokeLinecap="round" />
          <circle cx={s * 23} cy={-58} r={3.5} fill={INK} />
        </g>
      ))}
      <path d={oval(0, -38, 18, 16, 6210, 1)} fill={INK} />
      <Shape d={oval(0, 12, 38, 46, 6211, 1.4)} k="red" sw={5} shade={0.3} />
      <path d={inkLine([0, -32], [0, 56], 6212, 1, 4)} stroke={INK} strokeWidth={3.5} fill="none" />
      {[[-18, -8, 8], [17, 4, 7], [-16, 30, 7], [18, 34, 6]].map(([x, y, r], i) => (
        <circle key={i} cx={x} cy={y} r={r} fill={INK} />
      ))}
    </g>
  );
};

const Shield: React.FC = () => {
  const outline: Pt[] = [[54, -56], [53, -18], [45, 14], [27, 42], [0, 64], [-27, 42], [-45, 14], [-53, -18], [-54, -56], [-22, -60], [0, -67], [22, -60]];
  const d = closedCurve(wobbleLoop(outline, [0, -2], 6301, 1.4));
  const inner = closedCurve(outline.map(([x, y]) => [x * 0.76, y * 0.76 - 1] as Pt));
  return (
    <g>
      <Defs k={["teal"]} />
      <Shape d={d} k="teal" sw={5} shade={0.3} />
      <path d={inner} fill="none" stroke={CREAM} strokeWidth={4} opacity={0.8} />
      <path d="M-20 0L-4 17L24 -16" stroke={INK} strokeWidth={15} fill="none" strokeLinecap="round" strokeLinejoin="round" />
      <path d="M-20 0L-4 17L24 -16" stroke={LIME} strokeWidth={8} fill="none" strokeLinecap="round" strokeLinejoin="round" />
    </g>
  );
};

const Stamp: React.FC = () => (
  <g>
    <Defs k={["wood", "red"]} />
    <Shape d={polyPath([[-50, 38], [50, 38], [46, 60], [-46, 60]], 6401, 1, 3)} k="red" sw={4.5} shade={0.5} />
    <Shape d={boxPath(0, 18, 108, 40, 6402, 1.6)} k="wood" sw={5} />
    <Shape d={polyPath(rect(-12, -30, 12, -2), 6403, 0.8, 2)} k="wood" sw={4.5} shade={0.4} />
    <Shape d={oval(0, -46, 22, 22, 6404, 1)} k="red" sw={5} />
    <circle cx={-7} cy={-53} r={5} fill="#FFFDF6" opacity={0.6} />
  </g>
);

const Clock: React.FC = () => {
  const ticks = Array.from({ length: 12 }, (_, i) => {
    const a = (i / 12) * Math.PI * 2;
    const r0 = i % 3 === 0 ? 30 : 34;
    return <line key={i} x1={Math.cos(a) * r0} y1={4 + Math.sin(a) * r0} x2={Math.cos(a) * 38} y2={4 + Math.sin(a) * 38} stroke={INK} strokeWidth={i % 3 === 0 ? 3.5 : 2.5} />;
  });
  return (
    <g>
      <Defs k={["red", "cream"]} />
      {[-1, 1].map((s) => (
        <path key={s} d={`M${s * 30} 46L${s * 40} 62`} stroke={INK} strokeWidth={6} strokeLinecap="round" />
      ))}
      <path d="M0 -46V-58" stroke={INK} strokeWidth={4} />
      <circle cx={0} cy={-59} r={4.5} fill={INK} />
      {[-1, 1].map((s) => (
        <Shape key={s} d={oval(s * 36, -42, 16, 16, 6501 + s, 0.8)} k="red" sw={4.5} shade={0.4} />
      ))}
      <Shape d={oval(0, 4, 50, 50, 6505, 1.2)} k="red" sw={5} />
      <Shape d={oval(0, 4, 40, 40, 6506, 1)} k="cream" sw={3} />
      {ticks}
      <path d="M0 4L-15 -6" stroke={INK} strokeWidth={5} strokeLinecap="round" />
      <path d="M0 4L4 -26" stroke={INK} strokeWidth={4} strokeLinecap="round" />
      <circle cx={0} cy={4} r={4} fill={RED} stroke={INK} strokeWidth={2} />
    </g>
  );
};

const Phone: React.FC<{ text: string }> = ({ text }) => (
  <g>
    <Defs k={["slate", "cream"]} />
    <Shape d={boxPath(0, 0, 86, 166, 6601, 1.8)} k="slate" sw={5} />
    <Shape d={boxPath(0, -6, 68, 124, 6602, 1.2)} k="cream" sw={3} />
    <path d="M-12 -76H12" stroke={INK} strokeWidth={3.5} strokeLinecap="round" />
    <circle cx={0} cy={70} r={6} fill={CREAM} stroke={INK} strokeWidth={2.5} />
    {[0, 1, 2].map((i) => <circle key={i} cx={-24 + i * 7} cy={-59} r={2} fill={INK} opacity={0.5} />)}
    <Label text={text} cx={0} cy={-2} w={58} h={100} maxFs={24} />
  </g>
);

const Laptop: React.FC<{ text: string }> = ({ text }) => (
  <g>
    <Defs k={["slate", "cream", "steel"]} />
    <Shape d={boxPath(0, -14, 176, 108, 6701, 2)} k="slate" sw={5} />
    <Shape d={boxPath(0, -16, 152, 84, 6702, 1.4)} k="cream" sw={3} />
    <Shape d={polyPath([[-88, 40], [88, 40], [102, 62], [-102, 62]], 6703, 1, 3)} k="steel" sw={4.5} />
    {[-60, -36, -12, 12, 36, 60].map((x) => <path key={x} d={`M${x - 8} 47H${x + 8}`} stroke={INK} strokeWidth={2.5} opacity={0.5} />)}
    <path d="M-16 56H16" stroke={INK} strokeWidth={3} opacity={0.6} />
    <Label text={text} cx={0} cy={-16} w={138} h={72} maxFs={30} />
  </g>
);

const Bulb: React.FC = () => {
  const pts: Pt[] = [];
  for (let i = 0; i <= 20; i++) {
    const a = (130 - (i / 20) * 260) * (Math.PI / 180) + Math.PI / 2;
    pts.push([Math.cos(a) * 42, -22 - Math.sin(a) * 42]);
  }
  pts.push([16, 12], [18, 24], [-18, 24], [-16, 12]);
  const glass = closedCurve(wobbleLoop(pts, [0, -18], 6801, 1.2));
  return (
    <g>
      <Defs k={["glass", "steel"]} />
      <Shape d={glass} k="glass" sw={5} />
      <path d="M-9 22V2L-14 -16M9 22V2L14 -16" stroke={INK} strokeWidth={2.5} fill="none" opacity={0.7} />
      <path d="M-14 -16L-7 -26L0 -16L7 -26L14 -16" stroke={RED} strokeWidth={3.5} fill="none" strokeLinejoin="round" />
      <path d="M-26 -42Q-30 -28 -24 -16" stroke="#FFFDF6" strokeWidth={5} fill="none" strokeLinecap="round" opacity={0.8} />
      {[30, 41, 52].map((y, i) => <Shape key={i} d={boxPath(0, y, 40 - i * 4, 12, 6802 + i, 0.8)} k="steel" sw={3.5} />)}
      <path d="M-9 59Q0 70 9 59Z" fill={INK} />
    </g>
  );
};

const Magnifier: React.FC = () => {
  const ring = oval(-16, -16, 50, 50, 6901, 1.2) + oval(-16, -16, 37, 37, 6902, 0.8);
  return (
    <g>
      <Defs k={["wood", "steel", "lens"]} />
      <Shape d={tubeP([[24, 24], [56, 56]], 18)} k="wood" sw={4.5} shade={0.3} />
      <Shape d={tubeP([[16, 16], [27, 27]], 21)} k="steel" sw={4} />
      <path d={oval(-16, -16, 37, 37, 6903, 0.8)} fill={T.lens.base} opacity={0.75} />
      <path d={oval(-16, -16, 37, 37, 6903, 0.8)} fill="url(#hatch-lens)" />
      <path d="M-40 -24Q-36 -42 -20 -46" stroke="#FFFDF6" strokeWidth={5} fill="none" strokeLinecap="round" opacity={0.85} />
      <Shape d={ring} k="steel" sw={4.5} evenOdd />
    </g>
  );
};

const Molecule: React.FC = () => {
  const centre: Pt = [-8, 4];
  const atoms: { p: Pt; r: number; k: ToneKey }[] = [
    { p: [52, -36], r: 18, k: "red" },
    { p: [-56, -38], r: 18, k: "lime" },
    { p: [40, 44], r: 20, k: "cream" },
    { p: [-50, 46], r: 14, k: "mustard" },
  ];
  return (
    <g>
      <Defs k={["teal", "red", "lime", "cream", "mustard"]} />
      {atoms.map(({ p }, i) => (
        <g key={i}>
          <path d={inkLine(centre, p, 7001 + i, 0.8, 3)} stroke={INK} strokeWidth={11} strokeLinecap="round" fill="none" />
          <path d={inkLine(centre, p, 7001 + i, 0.8, 3)} stroke={BEIGE} strokeWidth={5} strokeLinecap="round" fill="none" />
        </g>
      ))}
      {[...atoms, { p: centre, r: 27, k: "teal" as ToneKey }].map(({ p, r, k }, i) => (
        <g key={i}>
          <Shape d={oval(p[0], p[1], r, r, 7010 + i, 1, 20)} k={k} sw={4.5} shade={0.3} />
          <circle cx={p[0] - r * 0.35} cy={p[1] - r * 0.38} r={r * 0.22} fill="#FFFDF6" opacity={0.55} />
        </g>
      ))}
    </g>
  );
};

const Virus: React.FC = () => {
  const n = 9;
  const stalks = Array.from({ length: n }, (_, i) => {
    const a = (i / n) * Math.PI * 2 + 0.2;
    const c = Math.cos(a), s = Math.sin(a);
    return (
      <g key={i}>
        <line x1={c * 38} y1={s * 38} x2={c * 54} y2={s * 54} stroke={INK} strokeWidth={5} strokeLinecap="round" />
        <path d={oval(c * 57, s * 57, 7, 7, 7101 + i, 0.5, 12)} fill={MUSTARD} stroke={INK} strokeWidth={3} />
      </g>
    );
  });
  return (
    <g>
      <Defs k={["lime"]} />
      {stalks}
      <Shape d={oval(0, 0, 42, 42, 7120, 1.4)} k="lime" sw={5} shade={0.3} />
      {[[-14, -12, 7], [15, -4, 5], [-4, 18, 6], [20, 18, 4]].map(([x, y, r], i) => (
        <path key={i} d={oval(x, y, r, r, 7130 + i, 0.5, 10)} fill={mix(LIME, INK, 0.3)} opacity={0.7} />
      ))}
      <circle cx={-18} cy={-24} r={5} fill="#FFFDF6" opacity={0.55} />
    </g>
  );
};

const Battery: React.FC = () => (
  <g>
    <Defs k={["steel", "cream", "lime"]} />
    <Shape d={boxPath(72, 0, 14, 30, 7201, 0.8)} k="steel" sw={4} />
    <Shape d={boxPath(-6, 0, 144, 76, 7202, 1.8)} k="cream" sw={5} />
    {[0, 1, 2, 3].map((i) => {
      const x = -60 + i * 33;
      const d = boxPath(x, 0, 26, 50, 7210 + i, 0.8);
      return i < 3 ? <Shape key={i} d={d} k="lime" sw={3} /> : <path key={i} d={d} fill="none" stroke={INK} strokeWidth={2.5} strokeDasharray="6 5" opacity={0.6} />;
    })}
  </g>
);

/** Every library prop by id; a prop with no label ignores its text. */
export const PROP_DRAWINGS: Record<PropId, React.FC<{ text: string }>> = {
  card: Card,
  envelope: Envelope,
  packet: Packet,
  box: Box,
  file: File,
  folder: Folder,
  key: Key,
  lock: Lock,
  coin: Coin,
  cookie: Cookie,
  gear: Gear,
  bug: Bug,
  shield: Shield,
  stamp: Stamp,
  clock: Clock,
  phone: Phone,
  laptop: Laptop,
  bulb: Bulb,
  magnifier: Magnifier,
  molecule: Molecule,
  virus: Virus,
  battery: Battery,
};
