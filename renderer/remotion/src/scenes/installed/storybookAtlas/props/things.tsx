/*
 * Props: things. Objects from the history of inventions and ideas, roughly
 * 1700 to 1980: books and letters, clocks and keys, ships and engines.
 * Each is drawn with its base at the origin (see ./types.ts).
 */
import React from "react";
import { Sh, circle, ellipse, poly, rect, rounded } from "../ink";
import {
  BEIGE, BLUEPRINT, CREAM, GARMENT_COLORS, GOLD, INK, IVORY, SAGE, SAND, SEAL, SEAL_DARK, SLATE, STARGOLD, WOOD, WOOD_DARK,
} from "../palette";
import type { PropEntry } from "./types";

// close tints of the house palette
const IRON = "#5F5A54";
const IRON_LIGHT = "#857E74";
const FLAME = "#E9A23B";
const SKY = "#D5DDD8";
const MOSS = GARMENT_COLORS.moss;
const BRICK = GARMENT_COLORS.brick;
const DARK = "#3B3A40";
const SANDGRAIN = "#CDA661";
const STONE = "#9C968B";

type Pt = [number, number];
const rad = (deg: number) => (deg * Math.PI) / 180;

/** An ink line. */
const Ln: React.FC<{ d: string; w?: number; op?: number; color?: string }> = ({ d, w = 2.5, op = 1, color = INK }) => (
  <path d={d} fill="none" stroke={color} strokeWidth={w} strokeLinecap="round" strokeLinejoin="round" opacity={op} />
);

/** A thick bar or rod: a coloured stroke inside an ink one. */
const Tube: React.FC<{ d: string; w: number; color: string }> = ({ d, w, color }) => (
  <g>
    <path d={d} fill="none" stroke={INK} strokeWidth={w + 5} strokeLinecap="round" strokeLinejoin="round" />
    <path d={d} fill="none" stroke={color} strokeWidth={w} strokeLinecap="round" strokeLinejoin="round" />
  </g>
);

/** A circle wound the other way, to cut a hole in a shape filled with the nonzero rule. */
const hole = (cx: number, cy: number, r: number) => `M${cx - r} ${cy}a${r} ${r} 0 1 1 ${2 * r} 0a${r} ${r} 0 1 1 ${-2 * r} 0Z`;

/** A lumpy outline (foliage, smoke, a wax seal): n round bumps around an ellipse. */
function scallop(cx: number, cy: number, rx: number, ry: number, n: number, bulge = 0.62, phase = -90): string {
  const pts: Pt[] = Array.from({ length: n }, (_, i) => {
    const a = rad(phase + (i * 360) / n);
    return [cx + rx * Math.cos(a), cy + ry * Math.sin(a)];
  });
  let d = `M${pts[0][0].toFixed(1)} ${pts[0][1].toFixed(1)}`;
  for (let i = 0; i < n; i++) {
    const [x0, y0] = pts[i];
    const [x1, y1] = pts[(i + 1) % n];
    const r = Math.hypot(x1 - x0, y1 - y0) * bulge;
    d += `A${r.toFixed(1)} ${r.toFixed(1)} 0 0 1 ${x1.toFixed(1)} ${y1.toFixed(1)}`;
  }
  return `${d}Z`;
}

/** An open polyline through the points. */
const line = (pts: Pt[]) => `M${pts.map(([x, y]) => `${x.toFixed(1)} ${y.toFixed(1)}`).join("L")}`;

/** A point rotated about a centre. */
const turn = ([x, y]: Pt, [cx, cy]: Pt, deg: number): Pt => {
  const a = rad(deg), c = Math.cos(a), s = Math.sin(a);
  return [cx + (x - cx) * c - (y - cy) * s, cy + (x - cx) * s + (y - cy) * c];
};

/** Lines of handwriting: short ink strokes, one row each. */
const Writing: React.FC<{ x: number; y: number; rows: number[]; gap?: number; op?: number }> = ({ x, y, rows, gap = 15, op = 0.55 }) => (
  <g>
    {rows.map((len, i) => (
      <Ln key={i} d={`M${x} ${y + i * gap}h${len}`} w={2.2} op={op} />
    ))}
  </g>
);

/** A teardrop flame standing at (x, y), leaning by `lean` px at the tip. */
const Flame: React.FC<{ x: number; y: number; h: number; lean?: number }> = ({ x, y, h, lean = 0 }) => {
  const w = h * 0.3;
  return (
    <g>
      <path d={`M${x} ${y}C${x - w} ${y - h * 0.15} ${x - w * 0.8 + lean * 0.4} ${y - h * 0.6} ${x + lean} ${y - h}C${x + w * 0.8 + lean * 0.4} ${y - h * 0.6} ${x + w} ${y - h * 0.15} ${x} ${y}Z`}
        fill={FLAME} stroke={INK} strokeWidth={2} strokeLinejoin="round" />
      <path d={`M${x} ${y - 3}C${x - w * 0.45} ${y - h * 0.15} ${x - w * 0.3 + lean * 0.3} ${y - h * 0.4} ${x + lean * 0.5} ${y - h * 0.62}C${x + w * 0.3 + lean * 0.3} ${y - h * 0.4} ${x + w * 0.45} ${y - h * 0.15} ${x} ${y - 3}Z`}
        fill={STARGOLD} />
    </g>
  );
};

/** A tuft of grass at the foot of something standing outdoors. */
const Grass: React.FC<{ x: number; w: number }> = ({ x, w }) => (
  <Ln d={`M${x - w / 2} -4 q4 -16 8 -20 M${x - w / 4} -4 q2 -22 -2 -28 M${x} -4 q1 -18 6 -24 M${x + w / 4} -4 q-2 -14 -8 -18 M${x + w / 2} -4 q-3 -18 2 -22`}
    w={2.2} op={0.7} />
);

// ── book ─────────────────────────────────────────────────────────────────────

/** A cloth-bound book standing up. State 1: lying open, its pages facing out. */
const Book: PropEntry["draw"] = ({ state }) =>
  state === 0 ? (
    <g>
      <Sh d={poly([[-72, -238], [-54, -248], [92, -248], [72, -238]])} fill={CREAM} pen="none" sw={2.5} />
      <Sh d={poly([[72, -238], [92, -248], [92, -12], [72, -3]])} fill={CREAM} pen="none" sw={2.5} />
      <Ln d="M77 -240 V-6 M82 -243 V-8 M87 -245 V-10" w={1.2} op={0.45} />
      <Sh d={rounded(-74, -238, 148, 235, 5)} fill={SEAL} pen="l" penOp={0.16} sw={3} />
      <Ln d="M-58 -236 V-5" w={2} op={0.55} />
      <path d={rounded(-46, -222, 106, 203, 4)} fill="none" stroke={GOLD} strokeWidth={3} />
      <path d={rounded(-40, -216, 94, 191, 3)} fill="none" stroke={GOLD} strokeWidth={1.4} opacity={0.8} />
      <Sh d={ellipse(7, -128, 28, 38)} fill={GOLD} pen="d" penOp={0.15} sw={2.5} />
      <path d={ellipse(7, -128, 18, 27)} fill="none" stroke={SEAL_DARK} strokeWidth={2} />
      <path d={poly([[7, -146], [12, -133], [25, -128], [12, -123], [7, -110], [2, -123], [-11, -128], [2, -133]])} fill={SEAL_DARK} />
      <Ln d="M-14 -190 H28 M-6 -180 H20 M-14 -66 H28" w={3} color={GOLD} />
    </g>
  ) : (
    <g>
      <Sh d="M-148 -194 Q-74 -214 0 -200 Q74 -214 148 -194 L148 -3 Q74 -20 0 -9 Q-74 -20 -148 -3Z" fill={SEAL} pen="l" penOp={0.16} sw={3} />
      <Sh d="M0 -14 Q-70 -30 -140 -12 L-140 -198 Q-70 -214 0 -202Z" fill={BEIGE} pen="none" sw={2.5} />
      <Sh d="M0 -14 Q70 -30 140 -12 L140 -198 Q70 -214 0 -202Z" fill={BEIGE} pen="none" sw={2.5} />
      <Sh d="M0 -22 Q-66 -38 -134 -20 L-134 -204 Q-66 -222 0 -208Z" fill={CREAM} penOp={0.1} sw={2.5} />
      <Sh d="M0 -22 Q66 -38 134 -20 L134 -204 Q66 -222 0 -208Z" fill={CREAM} penOp={0.1} sw={2.5} />
      <Writing x={-116} y={-180} rows={[70, 96, 92, 98, 60, 0, 94, 98, 88, 96, 50]} gap={13} />
      <Sh d={rect(20, -184, 96, 66)} fill={SKY} pen="none" sw={2} />
      <Sh d="M20 -118 L20 -138 Q48 -160 76 -140 Q96 -152 116 -136 L116 -118Z" fill={SAGE} penOp={0.18} sw={2} />
      <path d={circle(88, -166, 9)} fill={STARGOLD} stroke={INK} strokeWidth={1.8} />
      <Writing x={22} y={-100} rows={[90, 96, 80, 94, 56]} gap={13} />
      <Ln d="M0 -208 V-22" w={2.5} />
    </g>
  );

// ── letter ───────────────────────────────────────────────────────────────────

/** A sealed envelope, its flap closed with red wax. State 1: opened, a page drawn out. */
const Letter: PropEntry["draw"] = ({ state }) =>
  state === 0 ? (
    <g>
      <Sh d={rect(-120, -163, 240, 160)} fill={CREAM} penOp={0.13} sw={3} />
      <Ln d="M-118 -5 L-22 -84 M118 -5 L22 -84" w={2} op={0.5} />
      <Sh d={poly([[-120, -163], [120, -163], [0, -72]])} fill={BEIGE} penOp={0.16} sw={2.5} />
      <Sh d={scallop(0, -76, 22, 21, 9, 0.6)} fill={SEAL} pen="l" penOp={0.18} sw={2.5} />
      <path d={circle(0, -76, 12)} fill="none" stroke={SEAL_DARK} strokeWidth={2.5} />
      <path d={poly([[0, -84], [6, -76], [0, -68], [-6, -76]])} fill={SEAL_DARK} />
    </g>
  ) : (
    <g>
      <Sh d={poly([[-120, -163], [120, -163], [0, -246]])} fill={BEIGE} penOp={0.16} sw={2.5} />
      <path d={`M-10 -238 A11 11 0 0 0 10 -238 L0 -246Z`} fill={SEAL} stroke={INK} strokeWidth={2} />
      <Sh d={rect(-120, -163, 240, 160)} fill={BEIGE} pen="d" penOp={0.2} sw={3} />
      <Sh d={rect(-96, -262, 192, 210)} fill={CREAM} penOp={0.1} sw={2.5} />
      <Writing x={-76} y={-238} rows={[52, 140, 132, 146, 120, 138, 90]} gap={15} />
      <Sh d={poly([[-120, -163], [0, -96], [120, -163], [120, -3], [-120, -3]])} fill={CREAM} penOp={0.13} sw={3} />
      <Ln d="M-118 -5 L-26 -90 M118 -5 L26 -90" w={2} op={0.5} />
    </g>
  );

// ── candle ───────────────────────────────────────────────────────────────────

/** A candle in a brass chamberstick. States 1 and 2: the flame flickers. */
const Candle: PropEntry["draw"] = ({ state }) => (
  <g>
    <path d={circle(0, -194, 40)} fill={STARGOLD} opacity={0.32} />
    <Tube d="M52 -26 a16 16 0 1 1 22 12" w={6} color={GOLD} />
    <Sh d="M-66 -20 Q-62 -4 0 -4 Q62 -4 66 -20Z" fill={GOLD} pen="none" sw={3} />
    <Sh d={ellipse(0, -21, 66, 12)} fill="#C7A665" penOp={0.18} sw={3} />
    <Sh d={rounded(-22, -52, 44, 32, 4)} fill={GOLD} penOp={0.2} sw={2.5} />
    <Sh d={ellipse(0, -52, 30, 6)} fill="#C7A665" pen="none" sw={2.5} />
    <Sh d={rect(-16, -160, 32, 106)} fill={CREAM} penOp={0.12} sw={2.5} />
    <path d="M-16 -158 q-3 16 1 24 q4 6 3 -6 q0 -10 4 -18Z" fill={IVORY} stroke={INK} strokeWidth={1.8} />
    <Sh d={ellipse(0, -160, 16, 4)} fill={IVORY} pen="none" sw={2} />
    <Ln d="M0 -162 V-170" w={3} />
    <Flame x={0} y={-168} h={56} lean={[0, -9, 8][state]} />
  </g>
);

// ── clock ────────────────────────────────────────────────────────────────────

/** Hands of the clock in each state: [minute deg, hour deg, pendulum deg]. */
const CLOCK_HANDS: [number, number, number][] = [
  [60, 305, 0],
  [150, 312, -10],
  [240, 320, 10],
  [330, 327, -10],
  [60, 335, 10],
];

/** A schoolhouse wall clock with a pendulum. States 1 to 4: the hands go round, the pendulum swings. */
const Clock: PropEntry["draw"] = ({ state }) => {
  const [m, h, p] = CLOCK_HANDS[state];
  const cy = -240;
  const oct = Array.from({ length: 8 }, (_, i) => [90 * Math.cos(rad(22.5 + i * 45)), cy + 90 * Math.sin(rad(22.5 + i * 45))] as Pt);
  const pivot: Pt = [0, -176];
  const rodTop = turn([0, -150], pivot, p);
  const bob = turn([0, -72], pivot, p);
  const hand = (deg: number, len: number): Pt => [len * Math.sin(rad(deg)), cy - len * Math.cos(rad(deg))];
  return (
    <g>
      <Sh d={poly([[-30, -40], [30, -40], [0, -4]])} fill={WOOD_DARK} pen="l" penOp={0.15} sw={2.5} />
      <Sh d={rect(-54, -176, 108, 140)} fill={WOOD} pen="l" penOp={0.16} sw={3} />
      <Sh d={rounded(-35, -154, 70, 102, 8)} fill={BEIGE} pen="none" sw={2.5} />
      <Ln d={line([rodTop, bob])} w={3} />
      <path d={circle(bob[0], bob[1], 13)} fill={GOLD} stroke={INK} strokeWidth={2.5} />
      <Ln d="M-26 -146 l12 -6 M-28 -132 l18 -10" w={1.6} op={0.4} color={IVORY} />
      <Sh d={poly(oct)} fill={WOOD} pen="l" penOp={0.16} sw={3} />
      <Sh d={circle(0, cy, 68)} fill={GOLD} pen="none" sw={2.5} />
      <Sh d={circle(0, cy, 60)} fill={CREAM} penOp={0.08} sw={2.5} />
      {Array.from({ length: 12 }, (_, i) => {
        const a = rad(i * 30), q = i % 3 === 0;
        const r0 = q ? 44 : 49;
        return <Ln key={i} d={`M${r0 * Math.sin(a)} ${cy - r0 * Math.cos(a)}L${55 * Math.sin(a)} ${cy - 55 * Math.cos(a)}`} w={q ? 3.5 : 2} />;
      })}
      <Ln d={line([[0, cy], hand(h, 30)])} w={5} />
      <Ln d={line([[0, cy], hand(m, 44)])} w={3.5} />
      <path d={circle(0, cy, 5)} fill={GOLD} stroke={INK} strokeWidth={1.8} />
    </g>
  );
};

// ── map ──────────────────────────────────────────────────────────────────────

/** An old sea chart pinned to the wall. State 1: a voyage is marked on it. */
const MapProp: PropEntry["draw"] = ({ state }) => (
  <g>
    <Sh d="M-162 -206 Q-80 -200 0 -208 Q80 -214 158 -210 Q164 -110 162 -4 Q80 -10 0 -4 Q-80 -3 -160 -6 Q-166 -100 -162 -206Z"
      fill={BEIGE} penOp={0.14} sw={3} />
    <path d={rect(-146, -194, 294, 176)} fill="none" stroke={INK} strokeWidth={1.5} opacity={0.5} />
    <Sh d="M-146 -194 L-60 -194 Q-48 -176 -64 -160 Q-44 -146 -58 -124 Q-80 -110 -70 -88 Q-90 -70 -110 -76 Q-130 -60 -146 -64Z"
      fill={SAGE} penOp={0.2} sw={2.5} />
    <Sh d="M58 -150 Q80 -170 106 -158 Q132 -164 140 -140 Q150 -114 126 -100 Q118 -76 92 -84 Q66 -78 60 -100 Q40 -118 58 -150Z"
      fill={SAGE} penOp={0.2} sw={2.5} />
    <Sh d="M10 -60 Q24 -72 38 -62 Q46 -48 30 -42 Q12 -40 10 -60Z" fill={SAGE} penOp={0.2} sw={2} />
    <Ln d="M-30 -170 q6 -5 12 0 q6 5 12 0 M20 -186 q6 -5 12 0 q6 5 12 0 M-40 -110 q6 -5 12 0 q6 5 12 0 M80 -44 q6 -5 12 0 q6 5 12 0 M-10 -138 q6 -5 12 0 q6 5 12 0"
      w={1.8} op={0.5} />
    <g>
      <path d={circle(-106, -40, 18)} fill="none" stroke={INK} strokeWidth={1.5} opacity={0.6} />
      <path d={poly([[-106, -66], [-100, -46], [-80, -40], [-100, -34], [-106, -14], [-112, -34], [-132, -40], [-112, -46]])}
        fill={GOLD} stroke={INK} strokeWidth={1.8} strokeLinejoin="round" />
    </g>
    {state === 1 && (
      <g>
        <path d="M-74 -118 Q-30 -150 0 -110 Q30 -70 66 -112" fill="none" stroke={SEAL} strokeWidth={4} strokeDasharray="1 11" strokeLinecap="round" />
        <path d={circle(-74, -118, 6)} fill={SEAL} stroke={INK} strokeWidth={1.8} />
        <path d={circle(80, -118, 11)} fill="none" stroke={SEAL} strokeWidth={4} />
        <path d={circle(80, -118, 4)} fill={SEAL} />
      </g>
    )}
    <path d={circle(-148, -198, 8)} fill={SEAL} stroke={INK} strokeWidth={2} />
    <path d={circle(146, -200, 8)} fill={SEAL} stroke={INK} strokeWidth={2} />
    <path d={circle(-150, -200, 2.5)} fill={IVORY} />
    <path d={circle(144, -202, 2.5)} fill={IVORY} />
  </g>
);

// ── scroll ───────────────────────────────────────────────────────────────────

/** A scroll on two wooden rods. State 0: rolled and tied; state 1: hanging open. */
const Scroll: PropEntry["draw"] = ({ state }) => {
  const roll = (y: number) => (
    <g>
      <path d={circle(-106, y, 11)} fill={WOOD} stroke={INK} strokeWidth={2.5} />
      <path d={circle(106, y, 11)} fill={WOOD} stroke={INK} strokeWidth={2.5} />
      <Sh d={rounded(-96, y - 13, 192, 26, 12)} fill={CREAM} penOp={0.15} sw={2.5} />
      <Ln d={`M-80 ${y - 5}H80 M-80 ${y + 5}H80`} w={1.2} op={0.35} />
    </g>
  );
  return state === 0 ? (
    <g>
      <path d={circle(-108, -26, 12)} fill={WOOD} stroke={INK} strokeWidth={2.5} />
      <path d={circle(108, -26, 12)} fill={WOOD} stroke={INK} strokeWidth={2.5} />
      <Sh d={rounded(-98, -50, 196, 46, 22)} fill={CREAM} penOp={0.15} sw={3} />
      <Ln d="M-84 -38 H84 M-84 -18 H84" w={1.2} op={0.35} />
      <Sh d={rect(-8, -51, 16, 48)} fill={SEAL} pen="l" penOp={0.15} sw={2.2} />
      <Sh d="M0 -30 Q-24 -50 -30 -36 Q-26 -24 0 -30Z" fill={SEAL} pen="none" sw={2} />
      <Sh d="M0 -30 Q24 -50 30 -36 Q26 -24 0 -30Z" fill={SEAL} pen="none" sw={2} />
    </g>
  ) : (
    <g>
      <Sh d="M-86 -296 H86 V-44 Q60 -36 40 -46 Q0 -56 -40 -44 Q-64 -36 -86 -44Z" fill={CREAM} penOp={0.1} sw={2.5} />
      <Ln d="M-30 -262 H30" w={3} op={0.6} />
      <Writing x={-66} y={-238} rows={[126, 110, 130, 124, 70]} gap={16} />
      <path d={circle(0, -122, 22)} fill="none" stroke={INK} strokeWidth={2} opacity={0.55} />
      <Ln d="M-22 -122 H22 M0 -144 V-100" w={1.6} op={0.45} />
      <Writing x={-66} y={-84} rows={[120, 128, 60]} gap={16} />
      {roll(-298)}
      {roll(-26)}
    </g>
  );
};

// ── quill ────────────────────────────────────────────────────────────────────

/** A feather quill standing in a glass inkwell. */
const Quill: PropEntry["draw"] = () => (
  <g>
    <g transform="translate(-2 -90) rotate(20)">
      <Sh d="M0 -36 C-30 -70 -28 -150 2 -172 C16 -150 20 -80 0 -36Z" fill={IVORY} penOp={0.18} sw={2.5} />
      <Ln d="M-6 -60 L-20 -74 M-8 -84 L-24 -100 M-8 -108 L-22 -124 M-4 -132 L-14 -146 M2 -64 L12 -74 M4 -92 L14 -104 M4 -120 L12 -132" w={1.4} op={0.5} />
      <path d="M-19 -100 L-12 -98 L-21 -94" fill={IVORY} stroke={INK} strokeWidth={1.6} strokeLinejoin="round" />
      <Ln d="M0 0 C0 -60 0 -120 2 -170" w={2.2} />
    </g>
    <Sh d="M-58 -3 L58 -3 Q70 -44 42 -64 L-42 -64 Q-70 -44 -58 -3Z" fill={DARK} pen="l" penOp={0.18} sw={3} />
    <Ln d="M-40 -50 Q-52 -30 -46 -14" w={3} op={0.45} color={IVORY} />
    <Sh d={rect(-22, -84, 44, 22)} fill={DARK} pen="l" penOp={0.18} sw={2.5} />
    <Sh d={rounded(-28, -96, 56, 14, 4)} fill={GOLD} penOp={0.18} sw={2.5} />
  </g>
);

// ── key ──────────────────────────────────────────────────────────────────────

/** An old iron key with a four-lobed bow. */
const Key: PropEntry["draw"] = () => (
  <g>
    <Sh d={`${scallop(-84, -48, 22, 22, 4, 0.52, -45)}${hole(-84, -48, 10)}`} fill={IRON} pen="l" penOp={0.2} sw={3} />
    <Sh d={rounded(-58, -60, 16, 24, 4)} fill={IRON} pen="l" penOp={0.2} sw={2.5} />
    <Sh d={rect(-42, -54, 150, 12)} fill={IRON} pen="l" penOp={0.2} sw={2.5} />
    <Sh d={rounded(-24, -58, 8, 20, 3)} fill={IRON_LIGHT} pen="none" sw={2} />
    <Sh d={poly([[70, -44], [104, -44], [104, -8], [96, -8], [96, -20], [88, -20], [88, -6], [78, -6], [78, -24], [70, -24]])}
      fill={IRON} pen="l" penOp={0.2} sw={2.5} />
    <path d={circle(110, -48, 7)} fill={IRON} stroke={INK} strokeWidth={2.5} />
  </g>
);

// ── lock ─────────────────────────────────────────────────────────────────────

/** A brass padlock with an iron shackle. State 1: unlocked, the shackle up and turned. */
const Lock: PropEntry["draw"] = ({ state }) => (
  <g>
    {state === 0 ? (
      <Tube d="M-38 -130 V-186 A38 38 0 0 1 38 -186 V-130" w={18} color={IRON} />
    ) : (
      <Tube d="M-38 -130 V-220 A38 38 0 0 1 38 -220 V-196" w={18} color={IRON} />
    )}
    <Sh d={rounded(-64, -144, 128, 141, 20)} fill={GOLD} penOp={0.2} sw={3} />
    <Ln d="M-62 -122 H62 M-62 -26 H62" w={2} op={0.45} />
    <Sh d={rounded(-22, -102, 44, 60, 10)} fill="#C7A665" pen="none" sw={2} />
    <path d={`${circle(0, -82, 8)}`} fill={INK} />
    <path d={poly([[-5, -80], [5, -80], [8, -56], [-8, -56]])} fill={INK} />
    {[[-50, -132], [50, -132], [-50, -16], [50, -16]].map(([x, y], i) => (
      <path key={i} d={circle(x, y, 3.5)} fill={IRON} stroke={INK} strokeWidth={1.4} />
    ))}
  </g>
);

// ── chest ────────────────────────────────────────────────────────────────────

/** A wooden chest with a domed lid and iron straps. State 1: open, gold inside. */
const Chest: PropEntry["draw"] = ({ state }) => {
  const body = (
    <g>
      <Sh d={rect(-128, -24, 30, 21)} fill={WOOD_DARK} pen="l" penOp={0.15} sw={2.5} />
      <Sh d={rect(98, -24, 30, 21)} fill={WOOD_DARK} pen="l" penOp={0.15} sw={2.5} />
      <Sh d={rect(-136, -154, 272, 132)} fill={WOOD} pen="l" penOp={0.16} sw={3} />
      <Ln d="M-134 -110 H134 M-134 -66 H134" w={2} op={0.5} />
      <Sh d={rect(-108, -154, 18, 132)} fill={IRON} pen="l" penOp={0.18} sw={2.5} />
      <Sh d={rect(90, -154, 18, 132)} fill={IRON} pen="l" penOp={0.18} sw={2.5} />
      {[-128, -96, -62, -40].map((y) => (
        <React.Fragment key={y}>
          <path d={circle(-99, y, 3)} fill={IRON_LIGHT} stroke={INK} strokeWidth={1.3} />
          <path d={circle(99, y, 3)} fill={IRON_LIGHT} stroke={INK} strokeWidth={1.3} />
        </React.Fragment>
      ))}
    </g>
  );
  if (state === 0) {
    return (
      <g>
        {body}
        <Sh d="M-140 -150 V-188 C-140 -248 140 -248 140 -188 V-150Z" fill={WOOD} pen="l" penOp={0.16} sw={3} />
        <Ln d="M-138 -196 C-110 -222 110 -222 138 -196" w={2} op={0.45} />
        <Sh d="M-108 -150 V-210 L-90 -219 V-150Z" fill={IRON} pen="l" penOp={0.18} sw={2.5} />
        <Sh d="M108 -150 V-210 L90 -219 V-150Z" fill={IRON} pen="l" penOp={0.18} sw={2.5} />
        <Sh d={rect(-142, -160, 284, 14)} fill={WOOD_DARK} pen="l" penOp={0.15} sw={2.5} />
        <Sh d="M-20 -168 H20 V-130 Q20 -112 0 -104 Q-20 -112 -20 -130Z" fill={GOLD} penOp={0.18} sw={2.5} />
        <path d={circle(0, -140, 5)} fill={INK} />
        <path d={poly([[-3, -138], [3, -138], [5, -122], [-5, -122]])} fill={INK} />
      </g>
    );
  }
  return (
    <g>
      <path d={ellipse(0, -184, 128, 70)} fill={STARGOLD} opacity={0.4} />
      <Sh d={poly([[-136, -160], [136, -160], [124, -296], [-124, -296]])} fill={WOOD_DARK} pen="l" penOp={0.15} sw={3} />
      <Ln d="M-130 -206 H130 M-127 -250 H127" w={2} op={0.4} color={IVORY} />
      <Sh d={poly([[-108, -160], [-90, -160], [-90, -296], [-106, -296]])} fill={IRON} pen="l" penOp={0.18} sw={2.5} />
      <Sh d={poly([[108, -160], [90, -160], [90, -296], [106, -296]])} fill={IRON} pen="l" penOp={0.18} sw={2.5} />
      <Sh d={rect(-132, -170, 264, 18)} fill={INK} pen="none" sw={2.5} />
      {[[-70, -166], [-44, -176], [-16, -170], [12, -180], [40, -168], [66, -176], [-30, -186], [28, -190], [90, -164], [-96, -164]].map(([x, y], i) => (
        <path key={i} d={ellipse(x, y, 14, 9)} fill={i % 3 === 0 ? STARGOLD : GOLD} stroke={INK} strokeWidth={2} />
      ))}
      {body}
      <Sh d="M-20 -154 H20 V-120 Q20 -104 0 -98 Q-20 -104 -20 -120Z" fill={GOLD} penOp={0.18} sw={2.5} />
      <path d={circle(0, -132, 5)} fill={INK} />
    </g>
  );
};

// ── porthole ─────────────────────────────────────────────────────────────────

/** A brass porthole looking out on the sea. */
const Porthole: PropEntry["draw"] = () => {
  const cy = -132, r = 86, hz = cy + 12;
  const s = Math.sqrt(r * r - (hz - cy) ** 2);
  return (
    <g>
      <Sh d={rounded(-142, cy - 22, 30, 44, 6)} fill={GOLD} penOp={0.18} sw={2.5} />
      <Sh d={rounded(112, cy - 16, 30, 32, 6)} fill={GOLD} penOp={0.18} sw={2.5} />
      <Sh d={circle(0, cy, 124)} fill={GOLD} penOp={0.2} sw={3} />
      <path d={circle(0, cy, 98)} fill="#8F7340" stroke={INK} strokeWidth={2.5} />
      {Array.from({ length: 8 }, (_, i) => {
        const a = rad(i * 45 + 22.5);
        return <path key={i} d={circle(111 * Math.cos(a), cy + 111 * Math.sin(a), 6)} fill="#C7A665" stroke={INK} strokeWidth={1.8} />;
      })}
      <path d={circle(0, cy, r)} fill={SKY} />
      <path d={`M${-s} ${hz}L${s} ${hz}A${r} ${r} 0 0 1 ${-s} ${hz}Z`} fill={SLATE} />
      <Ln d={`M-60 ${hz + 18} q8 -6 16 0 q8 6 16 0 M10 ${hz + 30} q8 -6 16 0 q8 6 16 0 M-30 ${hz + 48} q8 -6 16 0 q8 6 16 0 M30 ${hz + 8} q8 -6 16 0`}
        w={2} op={0.55} color={IVORY} />
      <Sh d={scallop(-28, cy - 40, 26, 11, 6, 0.7)} fill={CREAM} pen="none" sw={2} />
      <Ln d={`M36 ${cy - 46} q6 -6 10 0 q4 -6 10 0`} w={2} op={0.8} />
      <Ln d={`M-50 ${cy - 6} L-8 ${cy - 58} M-40 ${cy + 8} L-22 ${cy - 14}`} w={4} op={0.55} color={IVORY} />
      <path d={circle(0, cy, r)} fill="none" stroke={INK} strokeWidth={3} />
    </g>
  );
};

// ── window ───────────────────────────────────────────────────────────────────

/** A wall window onto a pale sky. State 1: its casements swung open. */
const Window: PropEntry["draw"] = ({ state }) => (
  <g>
    <Sh d={rect(-150, -352, 300, 324)} fill={WOOD} pen="l" penOp={0.16} sw={3} />
    <Sh d={rect(-124, -328, 248, 296)} fill={SKY} pen="none" sw={2.5} />
    <Sh d={scallop(-40, -262, 46, 16, 7, 0.7)} fill={CREAM} pen="none" sw={2} />
    <Sh d={scallop(70, -210, 32, 11, 6, 0.7)} fill={CREAM} pen="none" sw={2} />
    <Sh d="M-124 -32 V-80 Q-80 -116 -30 -92 Q20 -124 70 -96 Q100 -108 124 -98 V-32Z" fill={SAGE} penOp={0.2} sw={2.5} />
    <Ln d="M20 -160 q7 -6 12 0 q5 -6 12 0" w={2} op={0.8} />
    {state === 0 ? (
      <g>
        <Ln d="M-124 -230 H124 M-124 -132 H124" w={8} color={WOOD} />
        <Ln d="M-124 -230 H124 M-124 -132 H124" w={1.6} />
        <Sh d={rect(-7, -328, 14, 296)} fill={WOOD} pen="l" penOp={0.15} sw={2.5} />
        <Ln d="M-100 -258 L-80 -284 M-92 -250 L-84 -260 M30 -160 L50 -186 M38 -152 L46 -162" w={3} op={0.6} color={IVORY} />
      </g>
    ) : (
      <g>
        <Sh d={poly([[-124, -328], [-78, -342], [-78, -22], [-124, -32]])} fill={WOOD} pen="l" penOp={0.16} sw={2.5} />
        <Sh d={poly([[-118, -318], [-84, -328], [-84, -34], [-118, -40]])} fill={SKY} pen="none" sw={2} />
        <Ln d="M-118 -225 L-84 -228 M-118 -132 L-84 -130" w={4} color={WOOD} />
        <Sh d={poly([[124, -328], [78, -342], [78, -22], [124, -32]])} fill={WOOD} pen="l" penOp={0.16} sw={2.5} />
        <Sh d={poly([[118, -318], [84, -328], [84, -34], [118, -40]])} fill={SKY} pen="none" sw={2} />
        <Ln d="M118 -225 L84 -228 M118 -132 L84 -130" w={4} color={WOOD} />
      </g>
    )}
    <Sh d={rect(-172, -36, 344, 18)} fill={WOOD} pen="l" penOp={0.16} sw={3} />
    <Sh d={poly([[-150, -18], [150, -18], [140, -4], [-140, -4]])} fill={WOOD_DARK} pen="l" penOp={0.15} sw={2.5} />
  </g>
);

// ── hourglass ────────────────────────────────────────────────────────────────

const HG_TOP = -210, HG_NECK = -118, HG_BOTTOM = -24;
/** Half the glass's width at height y. */
function hgWidth(y: number): number {
  const top = y < HG_NECK;
  const u = top ? (y - HG_TOP) / (HG_NECK - HG_TOP) : (HG_BOTTOM - y) / (HG_BOTTOM - HG_NECK);
  return 5 + 41 * Math.pow(Math.sin(Math.PI * (0.18 + 0.82 * u)), 0.75);
}
/** The glass's profile between two heights, down its right side. */
const hgSide = (y0: number, y1: number, sign: number, n = 14): Pt[] =>
  Array.from({ length: n + 1 }, (_, i) => {
    const y = y0 + ((y1 - y0) * i) / n;
    return [sign * hgWidth(y), y] as Pt;
  });

/** How full the top is (0..1 of its height, from the neck) and how high the heap below stands, per state. */
const HG_SAND: [number, number][] = [[0.55, 30], [0.68, 20], [0.48, 34], [0.3, 46]];

/** An hourglass in a turned wooden frame. States 1 to 3: the sand runs down. */
const Hourglass: PropEntry["draw"] = ({ state }) => {
  const [fill, heap] = HG_SAND[state];
  const level = HG_NECK - (HG_NECK - HG_TOP) * fill;
  const topSand = [...hgSide(level, HG_NECK - 2, 1), ...hgSide(HG_NECK - 2, level, -1)];
  const hy = HG_BOTTOM - heap;
  const right = hgSide(HG_BOTTOM, hy, 1, 8);
  const left = hgSide(hy, HG_BOTTOM, -1, 8);
  const heapPath = `${line(right)}Q${(right[right.length - 1][0] / 2).toFixed(1)} ${hy - 4} 0 ${hy - 14}Q${(left[0][0] / 2).toFixed(1)} ${hy - 4} ${left[0][0].toFixed(1)} ${left[0][1].toFixed(1)}${line(left).replace("M", "L")}Z`;
  const glass = `${line([...hgSide(HG_TOP, HG_BOTTOM, 1, 40)])}${line(hgSide(HG_BOTTOM, HG_TOP, -1, 40)).replace("M", "L")}Z`;
  const post = (x: number) => (
    <g>
      <Sh d={rect(x - 5, -212, 10, 192)} fill={WOOD} pen="none" sw={2.2} />
      <Sh d={ellipse(x, -116, 9, 14)} fill={WOOD} pen="none" sw={2.2} />
      <Sh d={ellipse(x, -196, 8, 7)} fill={WOOD} pen="none" sw={2.2} />
      <Sh d={ellipse(x, -38, 8, 7)} fill={WOOD} pen="none" sw={2.2} />
    </g>
  );
  return (
    <g>
      {post(-58)}
      <path d={glass} fill={CREAM} opacity={0.75} />
      <Sh d={poly(topSand)} fill={SANDGRAIN} penOp={0.2} sw={2} />
      <Ln d={`M0 ${HG_NECK}V${hy - 14}`} w={2.5} color={SANDGRAIN} />
      <Sh d={heapPath} fill={SANDGRAIN} penOp={0.2} sw={2} />
      <path d={glass} fill="none" stroke={INK} strokeWidth={2.5} strokeLinejoin="round" />
      <Ln d="M-30 -196 Q-38 -176 -28 -158" w={3} op={0.6} color={IVORY} />
      {post(58)}
      <Sh d={rounded(-72, -232, 144, 20, 6)} fill={WOOD} pen="l" penOp={0.16} sw={2.5} />
      <Sh d={rounded(-72, -24, 144, 21, 6)} fill={WOOD} pen="l" penOp={0.16} sw={2.5} />
    </g>
  );
};

// ── ship ─────────────────────────────────────────────────────────────────────

/** A billowing square sail hung from a yard. */
const sail = (cx: number, top: number, bottom: number, ht: number, hb: number) => {
  const mid = (top + bottom) / 2;
  return `M${cx - ht} ${top}L${cx + ht} ${top}Q${cx + hb + 10} ${mid} ${cx + hb} ${bottom}Q${cx} ${bottom - 16} ${cx - hb} ${bottom}Q${cx - hb - 10} ${mid} ${cx - ht} ${top}Z`;
};

/** A two-masted sailing ship riding a wave. */
const Ship: PropEntry["draw"] = () => (
  <g>
    <Ln d="M-10 -466 L-170 -206 M-10 -466 L100 -414 M100 -414 L230 -236 M-10 -340 L-150 -206 M100 -310 L170 -196" w={1.6} op={0.55} />
    <Tube d="M176 -196 L230 -236" w={6} color={WOOD_DARK} />
    <Sh d={poly([[100, -406], [224, -238], [120, -214]])} fill={CREAM} penOp={0.14} sw={2.5} />
    <Tube d="M-10 -180 V-466" w={8} color={WOOD_DARK} />
    <Tube d="M100 -180 V-414" w={7} color={WOOD_DARK} />
    <Sh d={poly([[-10, -472], [-10, -452], [44, -466]])} fill={SEAL} pen="l" penOp={0.15} sw={2.2} />
    <Sh d={sail(-10, -438, -344, 64, 82)} fill={CREAM} penOp={0.14} sw={2.5} />
    <Sh d={sail(-10, -330, -200, 88, 104)} fill={CREAM} penOp={0.14} sw={2.5} />
    <Sh d={sail(100, -398, -316, 50, 64)} fill={CREAM} penOp={0.14} sw={2.5} />
    <Sh d={sail(100, -304, -200, 68, 80)} fill={CREAM} penOp={0.14} sw={2.5} />
    <Ln d="M-76 -438 H56 M-100 -330 H80 M48 -398 H152 M30 -304 H170" w={5} color={WOOD_DARK} />
    <Sh d="M-178 -210 L-150 -210 L-140 -178 L120 -178 Q150 -180 176 -198 L186 -202 Q152 -110 110 -66 L-150 -66 Q-182 -120 -178 -210Z"
      fill={WOOD} pen="l" penOp={0.16} sw={3} />
    <Ln d="M-168 -146 L160 -146" w={10} color={GOLD} />
    <Ln d="M-168 -152 L162 -152 M-166 -140 L156 -140" w={2} />
    {[-110, -60, -10, 40, 90].map((x) => (
      <path key={x} d={circle(x, -114, 7)} fill={DARK} stroke={GOLD} strokeWidth={2.5} />
    ))}
    <Sh d="M-226 -3 L-226 -76 Q-202 -100 -172 -82 Q-150 -68 -126 -86 Q-98 -104 -70 -84 Q-46 -68 -20 -88 Q8 -106 36 -86 Q60 -70 86 -88 Q114 -106 142 -86 Q166 -70 190 -88 Q212 -102 226 -90 L226 -3Z"
      fill={BLUEPRINT} pen="l" penOp={0.2} sw={3} />
    <Sh d="M-226 -3 L-226 -40 Q-196 -58 -164 -42 Q-136 -30 -106 -46 Q-74 -62 -44 -44 Q-16 -30 14 -46 Q46 -62 76 -44 Q104 -30 134 -46 Q166 -62 196 -46 Q214 -38 226 -46 L226 -3Z"
      fill={SLATE} pen="l" penOp={0.2} sw={2.5} />
    <Ln d="M-196 -94 q10 -4 16 4 M-96 -98 q10 -4 16 4 M8 -100 q10 -4 16 4 M114 -100 q10 -4 16 4 M-140 -50 q10 -4 16 4 M-26 -52 q10 -4 16 4 M90 -52 q10 -4 16 4"
      w={3} color={CREAM} />
  </g>
);

// ── train ────────────────────────────────────────────────────────────────────

const PUFFS: [number, number, number][][] = [
  [[166, -358, 22], [134, -378, 16]],
  [[166, -358, 24], [128, -376, 20], [90, -384, 15]],
  [[170, -356, 20], [136, -374, 25], [94, -384, 19], [60, -386, 13]],
  [[162, -360, 26], [122, -378, 21], [84, -386, 16]],
];

/** One wheel with its spokes turned to `phase` degrees. */
const Wheel: React.FC<{ x: number; y: number; r: number; phase: number }> = ({ x, y, r, phase }) => (
  <g>
    <Sh d={circle(x, y, r)} fill={BRICK} pen="l" penOp={0.15} sw={3} />
    <path d={circle(x, y, r - 7)} fill="none" stroke={INK} strokeWidth={2} />
    {Array.from({ length: r > 40 ? 10 : 8 }, (_, i) => {
      const a = rad(phase + (i * 360) / (r > 40 ? 10 : 8));
      return <Ln key={i} d={`M${x + 7 * Math.cos(a)} ${y + 7 * Math.sin(a)}L${x + (r - 8) * Math.cos(a)} ${y + (r - 8) * Math.sin(a)}`} w={2.5} />;
    })}
    <path d={circle(x, y, 8)} fill={GOLD} stroke={INK} strokeWidth={2} />
  </g>
);

/** A steam locomotive with a balloon stack and a cowcatcher. States 1 to 3: wheels turn, smoke rolls. */
const Train: PropEntry["draw"] = ({ state }) => {
  const phase = [30, 0, 120, 240][state];
  const pin = (cx: number): Pt => [cx + 26 * Math.cos(rad(phase)), -64 + 26 * Math.sin(rad(phase))];
  const [a, b] = [pin(-96), pin(12)];
  return (
    <g>
      {PUFFS[state].map(([x, y, r], i) => (
        <Sh key={i} d={scallop(x, y, r, r * 0.8, 6, 0.66)} fill={CREAM} penOp={0.1} sw={2.5} />
      ))}
      <Sh d={rect(-268, -14, 536, 10)} fill={IRON} pen="l" penOp={0.15} sw={2.5} />
      <Sh d={rect(-250, -292, 104, 172)} fill={MOSS} pen="l" penOp={0.18} sw={3} />
      <Sh d={rounded(-234, -272, 66, 60, 8)} fill={CREAM} penOp={0.1} sw={2.5} />
      <Sh d={rounded(-264, -308, 132, 20, 6)} fill={DARK} pen="l" penOp={0.15} sw={2.5} />
      <Sh d={rect(-148, -134, 352, 18)} fill={BRICK} pen="l" penOp={0.15} sw={2.5} />
      <Sh d={rounded(-148, -248, 304, 116, 22)} fill={MOSS} pen="l" penOp={0.18} sw={3} />
      {[-90, -20, 50, 116].map((x) => (
        <Sh key={x} d={rect(x - 4, -246, 8, 112)} fill={GOLD} pen="none" sw={2} />
      ))}
      <Sh d={rect(152, -252, 44, 120)} fill={DARK} pen="l" penOp={0.15} sw={3} />
      <Sh d="M156 -252 L150 -302 L130 -334 L198 -334 L184 -302 L190 -252Z" fill={DARK} pen="l" penOp={0.15} sw={3} />
      <Sh d={rounded(126, -342, 76, 12, 4)} fill={DARK} pen="none" sw={2.5} />
      <Sh d="M-4 -248 Q-4 -286 20 -288 Q44 -286 44 -248Z" fill={GOLD} penOp={0.18} sw={2.5} />
      <Sh d="M-100 -248 Q-100 -270 -90 -272 Q-80 -270 -80 -248Z" fill={GOLD} penOp={0.18} sw={2.2} />
      <Sh d={rect(198, -292, 32, 30)} fill={GOLD} penOp={0.18} sw={2.5} />
      <path d={circle(230, -277, 10)} fill={STARGOLD} stroke={INK} strokeWidth={2} />
      <Sh d={rounded(70, -116, 76, 44, 6)} fill={DARK} pen="l" penOp={0.15} sw={2.5} />
      <Sh d={poly([[196, -132], [226, -132], [262, -16], [196, -16]])} fill={BRICK} pen="l" penOp={0.15} sw={2.5} />
      <Ln d="M208 -128 V-18 M222 -128 V-18 M236 -102 V-18 M250 -60 V-18" w={2} op={0.6} />
      <Wheel x={-96} y={-64} r={50} phase={phase} />
      <Wheel x={12} y={-64} r={50} phase={phase} />
      <Wheel x={112} y={-42} r={28} phase={phase * 1.8} />
      <Wheel x={170} y={-42} r={28} phase={phase * 1.8} />
      <Tube d={line([a, b])} w={7} color={IRON_LIGHT} />
      <Tube d={line([[110, -94], b])} w={6} color={IRON_LIGHT} />
      <path d={circle(a[0], a[1], 5)} fill={GOLD} stroke={INK} strokeWidth={1.8} />
      <path d={circle(b[0], b[1], 5)} fill={GOLD} stroke={INK} strokeWidth={1.8} />
    </g>
  );
};

// ── lighthouse ───────────────────────────────────────────────────────────────

/** Half the tower's width at height y. */
const towerW = (y: number) => 44 + 26 * ((y + 404) / 344);
const band = (y0: number, y1: number) => poly([[-towerW(y0), y0], [towerW(y0), y0], [towerW(y1), y1], [-towerW(y1), y1]]);

/** A striped lighthouse on its rock. State 1: lit, its beams thrown out. */
const Lighthouse: PropEntry["draw"] = ({ state }) => (
  <g>
    {state === 1 && (
      <g>
        <path d={poly([[30, -462], [196, -520], [196, -416]])} fill={STARGOLD} opacity={0.55} />
        <path d={poly([[-30, -462], [-196, -520], [-196, -416]])} fill={STARGOLD} opacity={0.55} />
        <path d={circle(0, -456, 62)} fill={STARGOLD} opacity={0.4} />
      </g>
    )}
    <Sh d={band(-404, -60)} fill={CREAM} penOp={0.12} sw={3} />
    <Sh d={band(-370, -320)} fill={SEAL} pen="l" penOp={0.15} sw={2.5} />
    <Sh d={band(-260, -206)} fill={SEAL} pen="l" penOp={0.15} sw={2.5} />
    <Sh d={band(-146, -92)} fill={SEAL} pen="l" penOp={0.15} sw={2.5} />
    <Sh d={rounded(-9, -296, 18, 26, 9)} fill={DARK} pen="none" sw={2} />
    <Sh d={rounded(-9, -186, 18, 26, 9)} fill={DARK} pen="none" sw={2} />
    <Sh d="M-20 -60 V-94 Q-20 -112 0 -112 Q20 -112 20 -94 V-60Z" fill={WOOD_DARK} pen="l" penOp={0.15} sw={2.5} />
    <Sh d="M-146 -3 Q-152 -40 -112 -56 Q-82 -78 -30 -66 Q20 -84 70 -64 Q120 -64 138 -30 L144 -3Z" fill={STONE} penOp={0.2} sw={3} />
    <Ln d="M-90 -40 l20 -10 l6 12 M40 -36 l24 -8 M-20 -20 l14 -10 l12 4" w={2} op={0.5} />
    <Sh d={rect(-38, -490, 76, 76)} fill={state === 1 ? STARGOLD : SKY} pen="none" sw={2.5} />
    <Ln d="M-14 -490 V-414 M14 -490 V-414" w={3} />
    <Sh d={rect(-70, -416, 140, 14)} fill={DARK} pen="l" penOp={0.15} sw={2.5} />
    <Ln d="M-66 -416 V-446 M-44 -416 V-446 M44 -416 V-446 M66 -416 V-446 M-68 -446 H-38 M38 -446 H68" w={2.5} />
    <Sh d="M-50 -488 Q-50 -536 0 -544 Q50 -536 50 -488Z" fill={SEAL_DARK} pen="l" penOp={0.15} sw={2.5} />
    <Ln d="M0 -544 V-556" w={3} />
    <path d={circle(0, -548, 5)} fill={GOLD} stroke={INK} strokeWidth={1.8} />
  </g>
);

// ── house ────────────────────────────────────────────────────────────────────

/** A small cottage. State 1: evening, its windows lit and the chimney smoking. */
const House: PropEntry["draw"] = ({ state }) => {
  const lit = state === 1;
  const win = (x: number) => (
    <g>
      {lit && <path d={circle(x, -130, 52)} fill={STARGOLD} opacity={0.35} />}
      <Sh d={rect(x - 40, -168, 80, 74)} fill={WOOD} pen="l" penOp={0.15} sw={2.5} />
      <Sh d={rect(x - 32, -160, 64, 58)} fill={lit ? STARGOLD : SLATE} pen={lit ? "d" : "l"} penOp={0.12} sw={2} />
      <Ln d={`M${x} -160 V-102 M${x - 32} -131 H${x + 32}`} w={4} color={WOOD} />
      <Ln d={`M${x} -160 V-102 M${x - 32} -131 H${x + 32}`} w={1.2} />
      <Sh d={rect(x - 44, -96, 88, 16)} fill={WOOD_DARK} pen="l" penOp={0.15} sw={2.2} />
      {[-30, -14, 2, 18, 32].map((dx, i) => (
        <path key={i} d={circle(x + dx, -100 - (i % 2) * 4, 5)} fill={i % 2 ? SEAL : STARGOLD} stroke={INK} strokeWidth={1.5} />
      ))}
    </g>
  );
  return (
    <g>
      {lit && [[98, -380, 14], [80, -396, 10]].map(([x, y, r], i) => (
        <Sh key={i} d={scallop(x, y, r, r * 0.8, 6, 0.66)} fill={CREAM} penOp={0.1} sw={2.2} />
      ))}
      <Sh d={rect(78, -366, 40, 80)} fill={BRICK} pen="l" penOp={0.15} sw={2.5} />
      <Sh d={rect(72, -372, 52, 12)} fill={BRICK} pen="l" penOp={0.15} sw={2.5} />
      <Sh d={rect(-168, -206, 336, 203)} fill={CREAM} penOp={0.12} sw={3} />
      <Sh d={poly([[-194, -196], [-128, -334], [128, -334], [194, -196]])} fill={BRICK} pen="l" penOp={0.18} sw={3} />
      <Ln d="M-178 -230 H178 M-162 -264 H162 M-146 -298 H146" w={2} op={0.5} />
      {win(-104)}
      {win(104)}
      <Sh d="M-30 -3 V-100 Q-30 -132 0 -132 Q30 -132 30 -100 V-3Z" fill={WOOD} pen="l" penOp={0.16} sw={2.5} />
      <Ln d="M-30 -66 H30 M0 -132 V-3" w={1.5} op={0.4} />
      <path d={circle(18, -60, 4)} fill={GOLD} stroke={INK} strokeWidth={1.5} />
      <Grass x={-150} w={30} />
      <Grass x={150} w={30} />
    </g>
  );
};

// ── tree ─────────────────────────────────────────────────────────────────────

/** A round apple tree. */
const Tree: PropEntry["draw"] = () => (
  <g>
    <Sh d="M-30 -3 Q-18 -10 -18 -60 Q-20 -130 -24 -176 L-70 -240 L-56 -250 L-12 -200 L-10 -268 L10 -268 L12 -206 L56 -258 L70 -248 L22 -178 Q18 -120 20 -60 Q20 -10 34 -3Z"
      fill={WOOD} pen="l" penOp={0.16} sw={3} />
    <Sh d={scallop(0, -350, 168, 150, 15, 0.62)} fill={SAGE} penOp={0.22} sw={3} />
    <Sh d={scallop(60, -300, 84, 58, 8, 0.6, -70)} fill="#8A9979" pen="d" penOp={0.18} sw={0} />
    <Ln d="M-110 -410 q8 8 16 0 M-40 -450 q8 8 16 0 M60 -440 q8 8 16 0 M110 -370 q8 8 16 0 M-120 -300 q8 8 16 0 M30 -280 q8 8 16 0 M80 -310 q8 8 16 0 M-20 -380 q8 8 16 0"
      w={2} op={0.45} />
    {[[-90, -370], [40, -400], [100, -330], [-30, -300], [-120, -260], [130, -260], [10, -340]].map(([x, y], i) => (
      <g key={i}>
        <path d={circle(x, y, 9)} fill={SEAL} stroke={INK} strokeWidth={2} />
        <Ln d={`M${x} ${y - 8} l2 -6`} w={1.8} />
      </g>
    ))}
    <Grass x={-48} w={26} />
    <Grass x={50} w={26} />
  </g>
);

// ── printing press ───────────────────────────────────────────────────────────

/** [platen y, bar end] per state: resting, half pulled, pulled home. */
const PRESS: [number, Pt][] = [[-330, [196, -380]], [-290, [150, -280]], [-248, [-150, -300]]];

/** A wooden hand press: two cheeks, a threaded screw and a bar. States 1 and 2: the bar pulled, the platen pressing down. */
const PrintingPress: PropEntry["draw"] = ({ state }) => {
  const [py, end] = PRESS[state];
  const top = -420, collar = py - 40;
  const pivot: Pt = [0, collar + 10];
  const len = Math.hypot(end[0] - pivot[0], end[1] - pivot[1]);
  const grip: Pt = [pivot[0] + ((end[0] - pivot[0]) * (len - 44)) / len, pivot[1] + ((end[1] - pivot[1]) * (len - 44)) / len];
  return (
    <g>
      <Sh d={poly([[-206, -26], [-150, -120], [-150, -26]])} fill={WOOD} pen="l" penOp={0.16} sw={2.5} />
      <Sh d={poly([[206, -26], [150, -120], [150, -26]])} fill={WOOD} pen="l" penOp={0.16} sw={2.5} />
      <Sh d={rect(-214, -30, 140, 27)} fill={WOOD_DARK} pen="l" penOp={0.15} sw={2.5} />
      <Sh d={rect(74, -30, 140, 27)} fill={WOOD_DARK} pen="l" penOp={0.15} sw={2.5} />
      <Sh d={rect(-152, -480, 46, 452)} fill={WOOD} pen="l" penOp={0.16} sw={3} />
      <Sh d={rect(106, -480, 46, 452)} fill={WOOD} pen="l" penOp={0.16} sw={3} />
      <Sh d={rect(-182, -506, 364, 60)} fill={WOOD} pen="l" penOp={0.16} sw={3} />
      <Sh d={rect(-196, -522, 392, 18)} fill={WOOD_DARK} pen="l" penOp={0.15} sw={2.5} />
      <Ln d="M-176 -490 H176" w={2} op={0.4} />
      <Sh d={rect(-106, -166, 212, 30)} fill={WOOD} pen="l" penOp={0.16} sw={2.5} />
      <Sh d={rect(-23, top, 46, collar - top)} fill={IRON} pen="l" penOp={0.15} sw={2.5} />
      {Array.from({ length: Math.floor((collar - top - 6) / 13) }, (_, i) => (
        <Ln key={i} d={`M-21 ${top + 14 + i * 13}q21 4 42 -9`} w={2} op={0.75} />
      ))}
      <Sh d={rect(-46, -448, 92, 34)} fill={WOOD_DARK} pen="l" penOp={0.15} sw={2.5} />
      <Sh d={rect(-14, collar, 28, py - collar)} fill={IRON} pen="l" penOp={0.15} sw={2.2} />
      <Sh d={rounded(-32, collar - 4, 64, 22, 6)} fill={GOLD} penOp={0.18} sw={2.5} />
      <Tube d={line([pivot, grip])} w={11} color={IRON_LIGHT} />
      <Tube d={line([grip, end])} w={17} color={WOOD} />
      <Sh d={rect(-96, py, 192, 26)} fill={GOLD} penOp={0.18} sw={2.5} />
      <Sh d={rect(-214, -200, 428, 32)} fill={WOOD_DARK} pen="l" penOp={0.15} sw={2.5} />
      <Sh d={rect(-86, -222, 172, 22)} fill={DARK} pen="l" penOp={0.15} sw={2.5} />
      {[-214, -206].map((y) => (
        <Ln key={y} d={`M-76 ${y}h22 m8 0h30 m8 0h18 m8 0h34 m8 0h22`} w={2} op={0.6} color={IVORY} />
      ))}
    </g>
  );
};

// ── signpost ─────────────────────────────────────────────────────────────────

/** An arrow-shaped board on the post, pointing right (dir 1) or left (-1). */
const Board: React.FC<{ y: number; dir: 1 | -1; tilt: number; len: number }> = ({ y, dir, tilt, len }) => {
  const pts: Pt[] = [[-22, -20], [len, -20], [len + 30, 0], [len, 20], [-22, 20]];
  return (
    <g transform={`translate(0 ${y}) rotate(${tilt}) scale(${dir} 1)`}>
      <Sh d={poly(pts)} fill={SAND} penOp={0.18} sw={2.5} />
      <Ln d={`M4 -6 h${len * 0.55} M4 6 h${len * 0.75}`} w={2.5} op={0.6} />
      <path d={circle(-10, 0, 2.5)} fill={INK} />
    </g>
  );
};

/** A wooden fingerpost at a crossroads. */
const Signpost: PropEntry["draw"] = () => (
  <g>
    <Sh d={rect(-14, -420, 28, 417)} fill={WOOD} pen="l" penOp={0.16} sw={3} />
    <Sh d={poly([[-18, -418], [0, -438], [18, -418]])} fill={WOOD_DARK} pen="l" penOp={0.15} sw={2.5} />
    <Board y={-378} dir={1} tilt={-4} len={116} />
    <Board y={-306} dir={-1} tilt={5} len={120} />
    <Board y={-234} dir={1} tilt={7} len={96} />
    <Sh d="M-40 -3 Q-36 -22 -16 -22 L16 -22 Q36 -22 40 -3Z" fill={STONE} penOp={0.2} sw={2.5} />
    <Grass x={-60} w={30} />
    <Grass x={62} w={30} />
  </g>
);

// ── lantern ──────────────────────────────────────────────────────────────────

/** A hanging lantern on a chain from a hook. State 1: lit. */
const Lantern: PropEntry["draw"] = ({ state }) => {
  const lit = state === 1;
  return (
    <g>
      {lit && <path d={circle(0, -112, 80)} fill={STARGOLD} opacity={0.3} />}
      <Tube d="M0 -296 a9 9 0 1 1 9 -8" w={4} color={IRON} />
      <path d={ellipse(0, -270, 6, 12)} fill="none" stroke={INK} strokeWidth={5} />
      <Ln d="M0 -260 V-238" w={5} />
      <path d={circle(0, -228, 10)} fill="none" stroke={INK} strokeWidth={5} />
      <Sh d={poly([[-58, -176], [0, -220], [58, -176]])} fill={IRON} pen="l" penOp={0.18} sw={2.5} />
      <Sh d={rect(-62, -180, 124, 12)} fill={IRON} pen="l" penOp={0.18} sw={2.5} />
      <Sh d={rect(-46, -168, 92, 116)} fill={lit ? STARGOLD : "#DCD5C2"} pen="none" sw={2.5} />
      <Sh d={rect(-9, -100, 18, 44)} fill={CREAM} pen="none" sw={2} />
      {lit ? <Flame x={0} y={-104} h={34} /> : <Ln d="M0 -102 V-110" w={2.5} />}
      <Ln d="M-46 -168 V-52 M-16 -168 V-52 M16 -168 V-52 M46 -168 V-52" w={6} color={INK} />
      <Ln d="M-46 -168 V-52 M-16 -168 V-52 M16 -168 V-52 M46 -168 V-52" w={2.5} color={IRON} />
      {!lit && <Ln d="M-36 -150 L-24 -164 M28 -88 L38 -100" w={2.5} op={0.6} color={IVORY} />}
      <Sh d={rect(-58, -54, 116, 12)} fill={IRON} pen="l" penOp={0.18} sw={2.5} />
      <Sh d="M-42 -42 L42 -42 L18 -16 L-18 -16Z" fill={IRON} pen="l" penOp={0.18} sw={2.5} />
      <path d={circle(0, -11, 6)} fill={IRON} stroke={INK} strokeWidth={2.2} />
    </g>
  );
};

export const THINGS_PROPS: Record<string, PropEntry> = {
  book: { label: "book", box: [304, 254], place: "floor", states: 2, acts: ["switch", "wobble", "glow"], portal: [0, -112], draw: Book },
  letter: { label: "letter", box: [252, 270], place: "wall", states: 2, acts: ["switch", "bounce", "wobble"], draw: Letter },
  candle: { label: "candle", box: [180, 240], place: "floor", states: 3, acts: ["glow", "cycle", "wobble"], draw: Candle },
  clock: { label: "wall clock", box: [200, 334], place: "wall", states: 5, acts: ["cycle", "wobble", "pulse"], draw: Clock },
  map: { label: "map", box: [340, 222], place: "wall", states: 2, acts: ["switch", "pulse", "glow", "wobble"], draw: MapProp },
  scroll: { label: "scroll", box: [250, 318], place: "wall", states: 2, acts: ["switch", "wobble", "glow"], draw: Scroll },
  quill: { label: "quill and inkwell", box: [160, 268], place: "floor", states: 1, acts: ["wobble", "bounce"], draw: Quill },
  key: { label: "iron key", box: [250, 96], place: "wall", states: 1, acts: ["spin", "glow", "bounce", "wobble"], draw: Key },
  lock: { label: "padlock", box: [140, 272], place: "wall", states: 2, acts: ["switch", "shake", "bounce"], draw: Lock },
  chest: { label: "chest", box: [292, 302], place: "floor", states: 2, acts: ["switch", "shake", "glow", "wobble"], draw: Chest },
  porthole: { label: "porthole", box: [292, 266], place: "wall", states: 1, acts: ["pulse", "glow", "wobble"], portal: [0, -132], draw: Porthole },
  window: { label: "window", box: [350, 356], place: "wall", states: 2, acts: ["switch", "glow"], portal: [0, -184], draw: Window },
  hourglass: { label: "hourglass", box: [152, 238], place: "floor", states: 4, acts: ["cycle", "spin", "wobble"], draw: Hourglass },
  ship: { label: "sailing ship", box: [480, 480], place: "floor", states: 1, acts: ["wobble", "bounce"], draw: Ship },
  train: { label: "steam locomotive", box: [548, 404], place: "floor", states: 4, acts: ["cycle", "shake"], draw: Train },
  lighthouse: { label: "lighthouse", box: [400, 562], place: "floor", states: 2, acts: ["switch", "glow"], draw: Lighthouse },
  house: { label: "cottage", box: [400, 412], place: "floor", states: 2, acts: ["switch", "glow", "wobble"], draw: House },
  tree: { label: "tree", box: [400, 530], place: "floor", states: 1, acts: ["wobble", "shake"], draw: Tree },
  printingpress: { label: "printing press", box: [440, 540], place: "floor", states: 3, acts: ["cycle", "shake"], draw: PrintingPress },
  signpost: { label: "signpost", box: [340, 446], place: "floor", states: 1, acts: ["wobble", "shake"], draw: Signpost },
  lantern: { label: "hanging lantern", box: [170, 320], place: "wall", states: 2, acts: ["swing", "switch", "glow"], draw: Lantern },
};
