/*
 * Props: science. Instruments, machines and discoveries from roughly 1800 to
 * 1980: bulbs and batteries, the telegraph and the telephone, relay computers
 * and terminals, the bench, the sky and the forge.
 * Each is drawn with its base at the origin (see ./types.ts).
 */
import React from "react";
import { Sh, circle, ellipse, poly, rect, rounded } from "../ink";
import { BLUEPRINT, CREAM, GOLD, INK, NAVY, SAGE, SAND, SEAL, SLATE, STARGOLD, WOOD, WOOD_DARK } from "../palette";
import type { PropEntry } from "./types";

// close tints of the house palette
const BLACK = "#3B3A40"; // japanned iron, bakelite, enamel
const STEEL = "#8E938F";
const IRON = "#4E4A47";
const COPPER = "#A8704A";
const GLASS = "#DFE5DD";
const LIT = "#F7E6AE";
const FLAME = "#E9A23B";
const PANEL = "#2E3440"; // the dark inside of a machine
const OCEAN = "#A9BBC3";
const BRASS_DARK = "#94753E";
const WOOD_LIGHT = "#A47E5C";
const PHOSPHOR = "#A9DB91";
const SHINE = "#FBF8EF";

type Pt = [number, number];
const rad = (deg: number) => (deg * Math.PI) / 180;
const pt = (cx: number, cy: number, r: number, deg: number): Pt => [cx + r * Math.cos(rad(deg)), cy + r * Math.sin(rad(deg))];

/** Seeded random numbers, so a drawing is the same every time it is drawn. */
function rng(seed: number) {
  let s = seed >>> 0;
  return () => {
    s = (s + 0x6d2b79f5) >>> 0;
    let t = s;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

/** An ink line. */
const Ln: React.FC<{ d: string; w?: number; op?: number; c?: string }> = ({ d, w = 2, op = 1, c = INK }) => (
  <path d={d} fill="none" stroke={c} strokeWidth={w} strokeLinecap="round" strokeLinejoin="round" opacity={op} />
);

/** A line with a coloured core inside an ink edge: rods, levers, wires. */
const Rod: React.FC<{ d: string; w: number; c: string }> = ({ d, w, c }) => (
  <g>
    <path d={d} fill="none" stroke={INK} strokeWidth={w + 4} strokeLinecap="round" strokeLinejoin="round" />
    <path d={d} fill="none" stroke={c} strokeWidth={w} strokeLinecap="round" strokeLinejoin="round" />
  </g>
);

/** "Writing": a row of short ink words from x0 to x1. */
function words(x0: number, x1: number, y: number, rand: () => number, min = 6, max = 18) {
  let d = "";
  let x = x0;
  while (x < x1 - min) {
    const len = Math.min(x1 - x, min + rand() * (max - min));
    d += `M${x.toFixed(1)} ${y}h${len.toFixed(1)}`;
    x += len + 5;
  }
  return d;
}

// ── lightbulb ─────────────────────────────────────────────────────────────────
const BULB = "M-22 -74 C-22 -100 -58 -112 -58 -152 A58 58 0 0 1 58 -152 C58 -112 22 -100 22 -74 Z";
const FILAMENT = "M-18 -160 q4.5 -12 9 0 q4.5 12 9 0 q4.5 -12 9 0 q4.5 12 9 0";

/** An early carbon-filament bulb standing on its screw base. State 1: lit. */
const Lightbulb: PropEntry["draw"] = ({ state }) => {
  const on = state === 1;
  return (
    <g>
      {on && <path d={circle(0, -148, 74)} fill={STARGOLD} opacity={0.35} />}
      <Sh d={BULB} fill={on ? LIT : GLASS} penOp={0.12} op={on ? 1 : 0.95} />
      {on && <path d={circle(0, -158, 30)} fill="#FFF3CF" opacity={0.9} />}
      <Ln d="M-7 -80 L-5 -112 L5 -112 L7 -80" w={1.6} op={0.55} />
      <Ln d="M-3 -112 L-18 -160 M3 -112 L18 -160" w={1.8} />
      {on ? <Rod d={FILAMENT} w={2.6} c={FLAME} /> : <Ln d={FILAMENT} w={2.2} />}
      <Ln d="M-40 -170 Q-42 -192 -24 -200" w={6} c={SHINE} op={0.9} />
      <Sh d={rect(-25, -82, 50, 44)} fill={GOLD} penOp={0.2} />
      <Ln d="M-25 -48 L25 -54 M-25 -58 L25 -64 M-25 -68 L25 -74" w={2} op={0.7} />
      <Sh d={rect(-17, -40, 34, 12)} fill={BLACK} pen="l" penOp={0.15} sw={2.5} />
      <Sh d="M-11 -29 L11 -29 L7 -9 Q0 3 -7 -9 Z" fill={GOLD} pen="none" sw={2.5} />
    </g>
  );
};

// ── battery ───────────────────────────────────────────────────────────────────
/** A dry cell with a carbon post and a zinc post, a lightning bolt on its label. */
const Battery: PropEntry["draw"] = () => (
  <g>
    <Sh d="M-48 -170 L-48 -12 A48 9 0 0 0 48 -12 L48 -170 Z" fill={BLUEPRINT} pen="l" penOp={0.15} />
    <Ln d="M-48 -28 A48 9 0 0 0 48 -28" w={2} op={0.6} />
    <Sh d="M-48 -134 A48 9 0 0 0 48 -134 L48 -62 A48 9 0 0 1 -48 -62 Z" fill={CREAM} penOp={0.14} sw={2.5} />
    <Sh d={poly([[8, -118], [-14, -92], [-2, -92], [-10, -62], [16, -98], [3, -98], [12, -118]])} fill={SEAL} pen="none" sw={2.5} />
    <Ln d="M-40 -100 h14 M-40 -88 h10 M24 -100 h14 M28 -88 h10" w={2.2} op={0.6} />
    <Sh d={ellipse(0, -170, 48, 11)} fill={STEEL} penOp={0.15} />
    <Sh d={ellipse(0, -170, 35, 7)} fill={BLACK} pen="l" penOp={0.15} sw={2} />
    <Sh d={rect(-6, -196, 12, 28)} fill={BLACK} pen="none" sw={2.5} />
    <Sh d={rounded(-15, -208, 30, 14, 4)} fill={GOLD} pen="none" sw={2.5} />
    <Ln d="M-9 -206 v10 M-4.5 -206 v10 M0 -206 v10 M4.5 -206 v10 M9 -206 v10" w={1.2} op={0.55} />
    <Sh d={rect(28, -186, 8, 16)} fill={STEEL} pen="none" sw={2.5} />
    <Sh d={rounded(22, -196, 20, 11, 3)} fill={GOLD} pen="none" sw={2.5} />
  </g>
);

// ── gears ─────────────────────────────────────────────────────────────────────
function gearOutline(cx: number, cy: number, ro: number, ri: number, n: number, phase: number) {
  const step = 360 / n;
  const pts: Pt[] = [];
  for (let k = 0; k < n; k++) {
    const a = phase + k * step;
    pts.push(pt(cx, cy, ri, a - 0.3 * step), pt(cx, cy, ro, a - 0.16 * step), pt(cx, cy, ro, a + 0.16 * step), pt(cx, cy, ri, a + 0.3 * step));
  }
  return poly(pts);
}

function sector(cx: number, cy: number, r1: number, r2: number, a1: number, a2: number) {
  const [x1, y1] = pt(cx, cy, r1, a1), [x2, y2] = pt(cx, cy, r2, a1);
  const [x3, y3] = pt(cx, cy, r2, a2), [x4, y4] = pt(cx, cy, r1, a2);
  return `M${x1} ${y1}L${x2} ${y2}A${r2} ${r2} 0 0 1 ${x3} ${y3}L${x4} ${y4}A${r1} ${r1} 0 0 0 ${x1} ${y1}Z`;
}

const Gear: React.FC<{ cx: number; cy: number; ro: number; ri: number; n: number; phase: number; fill: string; spokes: number }> = ({
  cx, cy, ro, ri, n, phase, fill, spokes,
}) => {
  const hub = Math.max(12, ri * 0.28);
  const holes = spokes
    ? Array.from({ length: spokes }, (_, k) => {
        const s = 360 / spokes, a = phase + k * s;
        return sector(cx, cy, hub + 6, ri - 12, a + 0.17 * s, a + 0.83 * s);
      }).join("")
    : [0, 120, 240].map((a) => { const [x, y] = pt(cx, cy, ri * 0.55, phase + a); return circle(x, y, ri * 0.16); }).join("");
  return (
    <g>
      <g fillRule="evenodd">
        <Sh d={gearOutline(cx, cy, ro, ri, n, phase) + holes} fill={fill} penOp={0.2} />
      </g>
      <path d={circle(cx, cy, ri - 6)} fill="none" stroke={INK} strokeWidth={1.6} opacity={0.35} />
      <Sh d={circle(cx, cy, hub * 0.6)} fill={WOOD_DARK} pen="none" sw={2.5} />
      <path d={circle(cx, cy, hub * 0.22)} fill={INK} />
    </g>
  );
};

/** Three meshing gears: brass, steel and copper. */
const Gears: PropEntry["draw"] = () => (
  <g>
    <Gear cx={-40} cy={-160} ro={92} ri={78} n={14} phase={14.286} fill={GOLD} spokes={5} />
    <Gear cx={62.6} cy={-73.9} ro={56} ri={44} n={8} phase={17.5} fill={STEEL} spokes={4} />
    <Gear cx={60.4} cy={-236.1} ro={44} ri={34} n={6} phase={52.86} fill={COPPER} spokes={0} />
  </g>
);

// ── telegraph key ─────────────────────────────────────────────────────────────
/** A Morse key and a sounder on one board, wired together. States 1 and 2 tap: 1 the key down (a spark, the sounder bar pulled down), 2 up. */
const Telegraph: PropEntry["draw"] = ({ state }) => {
  const down = state === 1;
  return (
    <g>
      <Sh d={rect(-125, -38, 250, 10)} fill={WOOD_LIGHT} pen="none" sw={2.5} />
      <Sh d={rect(-125, -30, 250, 27)} fill={WOOD} pen="l" penOp={0.16} />
      {/* wires from the key's posts to the sounder */}
      <Ln d="M2 -54 C8 -74 30 -72 42 -52" w={2.5} />
      <Ln d="M14 -54 C20 -66 34 -64 46 -52" w={2.5} />
      {[2, 14].map((x) => (
        <g key={x}>
          <Sh d={rect(x - 3, -50, 6, 13)} fill={GOLD} pen="none" sw={1.8} />
          <Sh d={rounded(x - 7, -56, 14, 7, 3)} fill={GOLD} pen="none" sw={1.8} />
        </g>
      ))}
      {/* the key */}
      <Sh d={rect(-92, -54, 12, 16)} fill={GOLD} pen="none" sw={2.5} />
      <Sh d={rect(-89, -58, 6, 4)} fill={STEEL} pen="none" sw={1.5} />
      <Ln d="M-24 -38 l-5 -3 l10 -4 l-10 -4 l10 -4 l-10 -4 l10 -4 l-5 -3" w={2} />
      <g transform={`rotate(${down ? -8 : 0} -46 -74)`}>
        <Sh d={rect(-20, -90, 7, 12)} fill={STEEL} pen="none" sw={1.8} />
        <Sh d={rounded(-24, -95, 15, 7, 3)} fill={GOLD} pen="none" sw={1.8} />
        <Sh d={rounded(-112, -79, 104, 10, 5)} fill={GOLD} penOp={0.2} sw={2.5} />
        <Sh d={rect(-89, -69, 6, 6)} fill={STEEL} pen="none" sw={1.8} />
        <Sh d={rect(-104, -96, 8, 18)} fill={BLACK} pen="none" sw={2.5} />
        <Sh d="M-124 -98 Q-124 -114 -100 -116 Q-76 -114 -76 -98 Z" fill={BLACK} pen="l" penOp={0.15} sw={2.5} />
        <Sh d={rounded(-126, -101, 52, 7, 3)} fill={BLACK} pen="none" sw={2.5} />
      </g>
      <Sh d={poly([[-62, -38], [-30, -38], [-38, -80], [-54, -80]])} fill={GOLD} penOp={0.2} sw={2.5} />
      <path d={circle(-46, -74, 5)} fill={BLACK} stroke={INK} strokeWidth={2} />
      {/* the sounder: a coil under a brass bar pivoted on a tall post */}
      <Sh d={rect(34, -50, 88, 13)} fill={WOOD_DARK} pen="l" penOp={0.15} sw={2.5} />
      <Sh d={rect(40, -128, 8, 80)} fill={GOLD} pen="none" sw={2} />
      <Sh d={rounded(36, -134, 16, 8, 3)} fill={GOLD} pen="none" sw={2} />
      <Sh d={rect(56, -90, 32, 40)} fill={COPPER} penOp={0.25} sw={2.5} />
      <Ln d="M56 -80 h32 M56 -70 h32 M56 -60 h32" w={1.2} op={0.5} />
      <Sh d={rounded(52, -96, 40, 7, 2)} fill={BLACK} pen="none" sw={2} />
      <Sh d={rounded(52, -54, 40, 6, 2)} fill={BLACK} pen="none" sw={2} />
      <g transform={`rotate(${down ? -4 : 0} 112 -108)`}>
        <Sh d={rounded(42, -112, 80, 8, 4)} fill={GOLD} penOp={0.2} sw={2.5} />
        <Sh d={rect(64, -104, 16, 5)} fill={STEEL} pen="none" sw={1.5} />
      </g>
      <Sh d={rect(106, -118, 12, 70)} fill={GOLD} penOp={0.2} sw={2.5} />
      <path d={circle(112, -108, 4)} fill={BLACK} stroke={INK} strokeWidth={1.8} />
      {down && (
        <g>
          {[200, 245, 295, 340].map((a) => {
            const [x1, y1] = pt(-86, -58, 8, a), [x2, y2] = pt(-86, -58, 17, a);
            const d = `M${x1} ${y1}L${x2} ${y2}`;
            return (
              <g key={a}>
                <Ln d={d} w={5} />
                <Ln d={d} w={2.4} c={STARGOLD} />
              </g>
            );
          })}
          <Ln d="M28 -118 l-9 -4 M28 -108 l-10 0 M28 -98 l-9 4" w={2.5} />
        </g>
      )}
    </g>
  );
};

// ── telephone ─────────────────────────────────────────────────────────────────
/** A candlestick telephone with a dial, its earpiece on the hook. States 1 and 2 ring. */
const Telephone: PropEntry["draw"] = ({ state }) => (
  <g>
    <Ln d="M-50 -98 C-52 -60 -92 -58 -88 -28 C-86 -10 -70 -8 -58 -12" w={3.5} />
    <Ln d="M60 -10 C76 -10 90 -16 92 -5" w={3.5} />
    <Sh d="M-66 -3 L66 -3 Q64 -26 36 -36 L-36 -36 Q-64 -26 -66 -3 Z" fill={BLACK} pen="l" penOp={0.15} />
    <Sh d={ellipse(0, -18, 24, 12)} fill={STEEL} penOp={0.15} sw={2.5} />
    {Array.from({ length: 8 }, (_, k) => {
      const a = 150 + k * 32;
      return <path key={k} d={circle(16 * Math.cos(rad(a)), -18 + 7.5 * Math.sin(rad(a)), 2.6)} fill={CREAM} stroke={INK} strokeWidth={1.2} />;
    })}
    <path d={ellipse(0, -18, 8, 4)} fill={CREAM} stroke={INK} strokeWidth={1.5} />
    <Sh d={rect(-10, -210, 20, 174)} fill={BLACK} pen="l" penOp={0.15} />
    <Sh d={rounded(-16, -46, 32, 12, 4)} fill={GOLD} pen="none" sw={2.5} />
    <Sh d={rounded(-14, -214, 28, 10, 4)} fill={GOLD} pen="none" sw={2.5} />
    <Rod d="M-10 -188 L-40 -188 L-46 -200" w={4} c={GOLD} />
    <Sh d={rounded(-56, -186, 12, 88, 6)} fill={BLACK} pen="l" penOp={0.15} sw={2.5} />
    <Sh d={poly([[-68, -204], [-32, -204], [-40, -182], [-60, -182]])} fill={BLACK} pen="l" penOp={0.15} sw={2.5} />
    <Sh d={ellipse(-50, -204, 18, 5)} fill="#5A5860" pen="none" sw={2.5} />
    <Sh d={circle(0, -242, 34)} fill={BLACK} pen="l" penOp={0.15} />
    <Sh d={circle(0, -242, 22)} fill="#5A5860" pen="none" sw={2} />
    {[[0, 0], [-8, -6], [8, -6], [-8, 6], [8, 6], [0, -12], [0, 12]].map(([x, y], k) => (
      <path key={k} d={circle(x, -242 + y, 2.4)} fill={INK} />
    ))}
    {state === 1 && <Ln d="M-44 -266 Q-54 -246 -44 -226 M44 -266 Q54 -246 44 -226" w={3} />}
    {state === 2 && <Ln d="M-56 -276 Q-70 -246 -56 -216 M56 -276 Q70 -246 56 -216 M-24 -290 l-6 -8 M24 -290 l6 -8" w={3} />}
  </g>
);

// ── radio ─────────────────────────────────────────────────────────────────────
const lancet = (xc: number, w: number, yb: number, ys: number) => {
  const l = xc - w / 2, r = xc + w / 2, apex = ys - w * 1.15;
  return `M${l} ${yb}L${l} ${ys}Q${l} ${ys - w * 0.7} ${xc} ${apex}Q${r} ${ys - w * 0.7} ${r} ${ys}L${r} ${yb}Z`;
};
const GRILLE = "M-66 -108 L-66 -168 Q-66 -232 0 -236 Q66 -232 66 -168 L66 -108 Z";

/** A cathedral valve radio: a gothic arched cabinet, cloth grille, dial and knobs. State 1: on. */
const Radio: PropEntry["draw"] = ({ state }) => {
  const on = state === 1;
  const ticks = Array.from({ length: 9 }, (_, k) => {
    const [x1, y1] = pt(0, -76, 10, 200 + k * 17.5), [x2, y2] = pt(0, -76, 14, 200 + k * 17.5);
    return `M${x1} ${y1}L${x2} ${y2}`;
  }).join("");
  const [px, py] = pt(0, -76, 12, on ? 300 : 230);
  return (
    <g>
      <Sh d="M-108 -22 L-108 -172 Q-108 -280 0 -284 Q108 -280 108 -172 L108 -22 Z" fill={WOOD} pen="l" penOp={0.15} />
      <Ln d="M-96 -30 L-96 -172 Q-96 -268 0 -272 Q96 -268 96 -172 L96 -30" w={2} op={0.45} />
      <Sh d="M-82 -100 L-82 -170 Q-82 -250 0 -254 Q82 -250 82 -170 L82 -100 Z" fill={WOOD_LIGHT} pen="l" penOp={0.15} sw={2.5} />
      <Sh d={GRILLE} fill={SAND} penOp={0.25} sw={2} />
      <g fillRule="evenodd">
        <Sh d={GRILLE + lancet(-36, 24, -116, -168) + lancet(0, 24, -116, -180) + lancet(36, 24, -116, -168) + circle(0, -222, 6)}
          fill={WOOD} pen="l" penOp={0.15} sw={2.5} />
      </g>
      {on && <path d={circle(0, -76, 34)} fill={STARGOLD} opacity={0.4} />}
      <Sh d={circle(0, -76, 21)} fill={GOLD} pen="none" sw={2.5} />
      <Sh d={circle(0, -76, 15)} fill={on ? "#F6DFA0" : CREAM} pen="none" sw={2} />
      <Ln d={ticks} w={1.4} op={0.8} />
      <Ln d={`M0 -76 L${px} ${py}`} w={2} c={SEAL} />
      {[-50, 50].map((x) => (
        <g key={x}>
          <Sh d={circle(x, -64, 12)} fill={WOOD_DARK} pen="l" penOp={0.15} sw={2.5} />
          <Ln d={`M${x} -64 L${x} -74`} w={2} c={CREAM} />
        </g>
      ))}
      <Sh d={circle(0, -40, 8)} fill={WOOD_DARK} pen="none" sw={2.5} />
      <Sh d={rect(-114, -24, 228, 21)} fill={WOOD_DARK} pen="l" penOp={0.15} />
    </g>
  );
};

// ── typewriter ────────────────────────────────────────────────────────────────
const KEY_ROWS: [y: number, n: number, half: number][] = [[-102, 8, 76], [-84, 9, 84], [-66, 10, 92], [-48, 10, 98]];
const PRESSED: Record<number, [number, number][]> = { 1: [[2, 3], [1, 6], [3, 1]], 2: [[0, 5], [2, 7], [3, 4]] };

/** A typewriter seen from the front, a sheet in the roller. States 1 and 2: keys going down in turn. */
const Typewriter: PropEntry["draw"] = ({ state }) => {
  const rand = rng(7);
  const text = [-220, -210, -200, -190].map((y, i) => words(-56, i === 3 ? 10 : 56, y, rand)).join("");
  const pressed = PRESSED[state] ?? [];
  const typebars = Array.from({ length: 15 }, (_, k) => {
    const a = 192 + k * 11.2;
    const [x1, y1] = pt(0, -118, 14, a), [x2, y2] = pt(0, -118, 38, a);
    return `M${x1} ${y1}L${x2} ${y2}`;
  }).join("");
  return (
    <g>
      <Sh d={rect(-68, -232, 136, 64)} fill={CREAM} penOp={0.1} sw={2.5} />
      <Ln d={text} w={2} op={0.7} />
      <Sh d="M-108 -168 Q-104 -128 -84 -116 L84 -116 Q104 -128 108 -168 Z" fill={BLACK} pen="l" penOp={0.15} />
      <Sh d="M-46 -118 A46 40 0 0 1 46 -118 Z" fill="#26252A" pen="none" sw={2} />
      <Ln d={typebars} w={2} c={STEEL} />
      {state === 1 && <Rod d="M0 -118 L0 -168" w={3} c={STEEL} />}
      <Sh d={rounded(-120, -190, 240, 22, 11)} fill={BLACK} pen="l" penOp={0.15} />
      <Sh d={rounded(-76, -198, 152, 6, 3)} fill={STEEL} pen="none" sw={2} />
      {[-128, 128].map((x) => (
        <g key={x}>
          <Sh d={circle(x, -179, 12)} fill={BLACK} pen="l" penOp={0.15} sw={2.5} />
          <path d={circle(x, -179, 5)} fill={STEEL} stroke={INK} strokeWidth={1.5} />
        </g>
      ))}
      <Rod d="M-114 -192 L-130 -208 L-138 -208" w={4} c={STEEL} />
      <Sh d={poly([[-124, -28], [124, -28], [106, -118], [-106, -118]])} fill={BLACK} pen="l" penOp={0.15} />
      {KEY_ROWS.map(([y, n, half], r) =>
        Array.from({ length: n }, (_, c) => {
          const x = -half + (c * 2 * half) / (n - 1);
          const down = pressed.some(([pr, pc]) => pr === r && pc === c);
          return <Sh key={`${r}-${c}`} d={circle(x, y + (down ? 3 : 0), 8)} fill={down ? GOLD : CREAM} pen="none" sw={2} />;
        }),
      )}
      <Sh d={rounded(-132, -30, 264, 27, 6)} fill="#2F2E33" pen="l" penOp={0.15} />
      <Sh d={rounded(-58, -26, 116, 9, 4)} fill={CREAM} pen="none" sw={2} />
    </g>
  );
};

// ── punch card ────────────────────────────────────────────────────────────────
/** A punched card: a grid of printed marks with holes punched through it. */
const Punchcard: PropEntry["draw"] = () => {
  const rand = rng(11);
  let marks = "", holes = "";
  for (let c = 0; c < 38; c++) {
    const x = -148 + c * 8;
    const picks = new Set<number>();
    const count = 1 + Math.floor(rand() * 2.4);
    for (let k = 0; k < count; k++) picks.add(Math.floor(rand() * 12));
    for (let r = 0; r < 12; r++) {
      const y = -138 + r * 10.6;
      if (picks.has(r)) holes += rect(x - 2.2, y - 4.5, 4.4, 9);
      else marks += `M${x - 1.3} ${y.toFixed(1)}h2.6`;
    }
  }
  return (
    <g>
      <Sh d={poly([[-140, -150], [159, -150], [159, -3], [-159, -3], [-159, -131]])} fill="#EADFBF" penOp={0.1} sw={2.5} />
      <Ln d={marks} w={1.6} op={0.3} />
      <path d={holes} fill={INK} opacity={0.85} />
    </g>
  );
};

// ── relay cabinet ─────────────────────────────────────────────────────────────
const Relay: React.FC<{ x: number; y: number }> = ({ x, y }) => (
  <g>
    <Sh d={rounded(x - 12, y - 8, 24, 16, 4)} fill={COPPER} penOp={0.25} sw={1.8} />
    <Ln d={`M${x - 6} ${y - 8}v16M${x} ${y - 8}v16M${x + 6} ${y - 8}v16`} w={1.1} op={0.5} />
    <Sh d={rect(x - 14, y - 13, 28, 4)} fill={STEEL} pen="none" sw={1.5} />
  </g>
);

/** A tall relay computer cabinet: indicator lamps, rows of relays, a brass porthole. State 1 on; states 1 and 2 flicker. */
const RelayCabinet: PropEntry["draw"] = ({ state }) => {
  const rand = rng(state === 2 ? 23 : 5);
  const lamps: React.ReactNode[] = [];
  for (let r = 0; r < 3; r++) {
    for (let c = 0; c < 10; c++) {
      const x = -153 + c * 34, y = -476 + r * 27;
      const lit = state > 0 && rand() < 0.5;
      const color = (r * 10 + c) % 4 === 1 ? SEAL : STARGOLD;
      lamps.push(
        <g key={`${r}-${c}`}>
          {lit && <path d={circle(x, y, 13)} fill={color} opacity={0.35} />}
          <path d={circle(x, y, 8)} fill={lit ? color : "#5E5446"} stroke={INK} strokeWidth={2} />
        </g>,
      );
    }
  }
  const sideRelays: React.ReactNode[] = [];
  for (const x0 of [-141, 141]) {
    for (let r = 0; r < 4; r++) for (const dx of [-22, 22]) sideRelays.push(<Relay key={`${x0}-${r}-${dx}`} x={x0 + dx} y={-370 + r * 38} />);
  }
  const rackRelays: React.ReactNode[] = [];
  for (let r = 0; r < 3; r++) for (let c = 0; c < 8; c++) rackRelays.push(<Relay key={`${r}-${c}`} x={-147 + c * 42} y={-198 + r * 36} />);
  const rivets = Array.from({ length: 12 }, (_, k) => { const [x, y] = pt(0, -313, 73, k * 30); return circle(x, y, 3); }).join("");
  return (
    <g>
      <Sh d={rect(-196, -510, 392, 482)} fill={SLATE} pen="l" penOp={0.15} />
      <Sh d={rect(-206, -534, 412, 28)} fill="#465366" pen="l" penOp={0.15} />
      <Ln d="M-200 -514 H200" w={2} op={0.5} />
      <Sh d={rect(-176, -494, 352, 90)} fill={PANEL} pen="l" penOp={0.12} sw={2.5} />
      {lamps}
      <Sh d={rect(-186, -396, 90, 160)} fill={PANEL} pen="l" penOp={0.12} sw={2.5} />
      <Sh d={rect(96, -396, 90, 160)} fill={PANEL} pen="l" penOp={0.12} sw={2.5} />
      {sideRelays}
      <Sh d={circle(0, -313, 82)} fill={GOLD} penOp={0.2} />
      <path d={rivets} fill={BRASS_DARK} stroke={INK} strokeWidth={1.2} />
      <Sh d={circle(0, -313, 62)} fill={NAVY} pen="l" penOp={0.12} />
      <path d={circle(0, -313, 54)} fill="none" stroke={BLUEPRINT} strokeWidth={2} opacity={0.6} />
      <Ln d="M-40 -342 Q-30 -362 -8 -366" w={6} c={SHINE} op={0.45} />
      <Sh d={rect(-176, -226, 352, 136)} fill={PANEL} pen="l" penOp={0.12} sw={2.5} />
      {rackRelays}
      <Sh d={rect(-176, -82, 352, 40)} fill="#465366" pen="l" penOp={0.12} sw={2.5} />
      {Array.from({ length: 8 }, (_, k) => {
        const x = -147 + k * 42;
        return (
          <g key={k}>
            <Rod d={`M${x} -62 L${x - 6} ${state > 0 && k % 3 !== 2 ? -76 : -48}`} w={2.5} c={STEEL} />
            <path d={circle(x, -62, 6)} fill={STEEL} stroke={INK} strokeWidth={2} />
          </g>
        );
      })}
      <Sh d={rect(-204, -30, 408, 27)} fill={WOOD_DARK} pen="l" penOp={0.15} />
    </g>
  );
};

// ── terminal ──────────────────────────────────────────────────────────────────
/** A 1970s CRT terminal on its keyboard. State 1: on with a cursor; state 2: on, the cursor off. */
const Terminal: PropEntry["draw"] = ({ state }) => {
  const on = state > 0;
  const rand = rng(31);
  const lines = [-254, -240, -226, -212, -198, -184].map((y) => words(-80, -80 + 70 + rand() * 90, y, rand, 8, 22)).join("");
  const keys: string[] = [];
  [-58, -46, -34].forEach((y, r) => {
    for (let c = 0; c < 14; c++) keys.push(rounded(-118 + r * 4 + c * 16.6, y, 13, 9, 2));
  });
  for (const x of [-120, -103, -86, 64, 81, 98]) keys.push(rounded(x, -22, 13, 9, 2));
  keys.push(rounded(-68, -22, 126, 9, 2));
  return (
    <g>
      <Sh d={poly([[-152, -3], [152, -3], [138, -72], [-138, -72]])} fill="#D9CDB2" penOp={0.15} />
      <Sh d={poly([[-134, -12], [134, -12], [126, -64], [-126, -64]])} fill="#5B5A5E" pen="l" penOp={0.12} sw={2.5} />
      <path d={keys.join("")} fill="#E4DCCB" stroke={INK} strokeWidth={1.5} />
      <Sh d={poly([[-70, -70], [70, -70], [60, -100], [-60, -100]])} fill="#C9BC9F" penOp={0.15} sw={2.5} />
      <Sh d={rounded(-132, -304, 264, 206, 20)} fill="#D9CDB2" penOp={0.15} />
      <Ln d="M-112 -114 h28 M-112 -108 h28 M-112 -102 h28" w={2} op={0.5} />
      <Sh d={rounded(-110, -288, 220, 164, 24)} fill="#3A3A3E" pen="l" penOp={0.1} sw={2.5} />
      <Sh d={rounded(-98, -278, 196, 144, 34)} fill={on ? "#21362B" : "#33403A"} pen="none" sw={2.5} />
      {on && (
        <g>
          <path d={rounded(-98, -278, 196, 144, 34)} fill={PHOSPHOR} opacity={0.1} />
          <Ln d={lines} w={3.2} c={PHOSPHOR} />
          <Ln d={state === 1 ? "M-80 -170 h30 M-45 -170 h16" : "M-80 -170 h30 M-45 -170 h16 M-24 -170 h12"} w={3.2} c={PHOSPHOR} />
          {state === 1 && <path d={rect(-24, -177, 9, 13)} fill={PHOSPHOR} />}
        </g>
      )}
      <Ln d="M-80 -262 Q-62 -270 -34 -270" w={4} c={SHINE} op={on ? 0.15 : 0.3} />
      <path d={circle(110, -110, 5)} fill={on ? PHOSPHOR : "#3A3A3E"} stroke={INK} strokeWidth={2} />
    </g>
  );
};

// ── microscope ────────────────────────────────────────────────────────────────
/** A brass and black microscope of the 1800s: horseshoe foot, curved arm, mirror under the stage. */
const Microscope: PropEntry["draw"] = () => (
  <g>
    <Sh d="M-78 -3 L78 -3 Q74 -20 56 -24 L-56 -24 Q-74 -20 -78 -3 Z" fill={BLACK} pen="l" penOp={0.15} />
    <Sh d={rect(-44, -114, 22, 92)} fill={BLACK} pen="l" penOp={0.15} />
    <Rod d="M-24 -66 L8 -66" w={3} c={GOLD} />
    <Sh d={ellipse(24, -66, 17, 7)} fill={GOLD} pen="none" sw={2.5} />
    <path d={ellipse(24, -67, 11, 3.5)} fill={GLASS} stroke={INK} strokeWidth={1.5} />
    <Sh d="M-46 -118 C-62 -164 -50 -212 -12 -230 L-2 -212 C-30 -198 -36 -160 -22 -120 Z" fill={BLACK} pen="l" penOp={0.15} />
    <Sh d={rect(-30, -132, 104, 10)} fill={BLACK} pen="l" penOp={0.15} sw={2.5} />
    <Sh d={rect(16, -136, 28, 4)} fill={GLASS} pen="none" sw={1.5} />
    <Rod d="M4 -134 L16 -137 M56 -134 L44 -137" w={2} c={GOLD} />
    <Sh d={circle(-33, -120, 12)} fill={GOLD} pen="none" sw={2.5} />
    <path d={circle(-33, -120, 4)} fill={BLACK} />
    <Sh d={rect(-8, -238, 26, 46)} fill={BRASS_DARK} penOp={0.2} sw={2.5} />
    <Sh d={circle(-10, -214, 13)} fill={GOLD} pen="none" sw={2.5} />
    <path d={circle(-10, -214, 6)} fill="none" stroke={INK} strokeWidth={1.5} opacity={0.6} />
    <Sh d={rect(16, -246, 28, 94)} fill={GOLD} penOp={0.2} />
    <Ln d="M16 -230 h28 M16 -172 h28" w={2} op={0.6} />
    <Sh d={poly([[19, -152], [41, -152], [35, -138], [25, -138]])} fill={GOLD} pen="none" sw={2.5} />
    <Sh d={rect(26, -140, 8, 4)} fill={STEEL} pen="none" sw={1.8} />
    <Sh d={rect(21, -262, 18, 18)} fill={GOLD} pen="none" sw={2.5} />
    <Sh d={rounded(18, -268, 24, 8, 3)} fill={BLACK} pen="none" sw={2.5} />
  </g>
);

// ── test tubes ────────────────────────────────────────────────────────────────
const TUBES: [x: number, level: number, color: string][] = [[-66, -128, SEAL], [-22, -108, SAGE], [22, -140, BLUEPRINT], [66, -118, "#C99A3E"]];
const BUBBLES: Record<number, [number, number, number][]> = {
  1: [[-66, -118, 4], [-62, -100, 3], [22, -128, 4], [24, -110, 3], [66, -106, 3.5], [-22, -96, 3]],
  2: [[-68, -110, 3.5], [-64, -124, 3], [20, -118, 3.5], [24, -134, 3], [64, -112, 4], [-20, -104, 3.5]],
};

/** A wooden rack of four test tubes. States 1 and 2: the liquids bubble. */
const Testtubes: PropEntry["draw"] = ({ state }) => (
  <g>
    <Sh d={rect(-110, -118, 14, 98)} fill={WOOD} pen="l" penOp={0.15} sw={2.5} />
    <Sh d={rect(96, -118, 14, 98)} fill={WOOD} pen="l" penOp={0.15} sw={2.5} />
    <Sh d={rect(-104, -118, 208, 14)} fill={WOOD_DARK} pen="l" penOp={0.15} sw={2.5} />
    {TUBES.map(([x]) => <path key={x} d={ellipse(x, -114, 15, 4)} fill={INK} opacity={0.7} />)}
    {TUBES.map(([x, level, color]) => (
      <g key={x}>
        <Sh d={`M${x - 12} -172 L${x - 12} -46 A12 12 0 0 0 ${x + 12} -46 L${x + 12} -172 Z`} fill={GLASS} penOp={0.08} sw={0} op={0.9} />
        <Sh d={`M${x - 12} ${level} L${x - 12} -46 A12 12 0 0 0 ${x + 12} -46 L${x + 12} ${level} Z`} fill={color} pen="l" penOp={0.15} sw={0} />
        <Ln d={`M${x - 12} ${level} h24`} w={1.6} op={0.7} />
        <path d={`M${x - 12} -172 L${x - 12} -46 A12 12 0 0 0 ${x + 12} -46 L${x + 12} -172`} fill="none" stroke={INK} strokeWidth={2.5} />
        <Sh d={rounded(x - 15, -177, 30, 6, 3)} fill={GLASS} pen="none" sw={2} />
        <Ln d={`M${x - 6} -164 v40`} w={3} c={SHINE} op={0.7} />
      </g>
    ))}
    {(BUBBLES[state] ?? []).map(([x, y, r], k) => <path key={k} d={circle(x, y, r)} fill={SHINE} stroke={INK} strokeWidth={1.2} opacity={0.9} />)}
    {state === 1 && <Ln d="M22 -184 q-6 -6 0 -12 q6 -6 0 -12" w={2.2} op={0.6} />}
    {state === 2 && <Ln d="M-66 -184 q6 -6 0 -12 q-6 -6 0 -12" w={2.2} op={0.6} />}
    <Sh d={rect(-112, -22, 224, 19)} fill={WOOD} pen="l" penOp={0.15} />
    <Sh d={rect(-104, -62, 208, 10)} fill={WOOD_DARK} pen="l" penOp={0.15} sw={2.5} />
  </g>
);

// ── magnifier ─────────────────────────────────────────────────────────────────
/** A magnifying glass with a brass rim and a wooden handle. */
const Magnifier: PropEntry["draw"] = () => (
  <g>
    <g transform="translate(-24 -176) rotate(55)">
      <Sh d={rounded(104, -11, 98, 22, 11)} fill={WOOD} pen="l" penOp={0.16} />
      <Ln d="M124 -11 v22 M182 -11 v22" w={2} op={0.5} />
      <Sh d={rect(76, -10, 30, 20)} fill={GOLD} penOp={0.2} sw={2.5} />
      <Ln d="M90 -10 v20" w={1.6} op={0.6} />
    </g>
    <g fillRule="evenodd">
      <Sh d={circle(-24, -176, 80) + circle(-24, -176, 66)} fill={GOLD} penOp={0.2} />
    </g>
    <Sh d={circle(-24, -176, 66)} fill={GLASS} penOp={0.08} op={0.92} sw={2} />
    <Ln d="M-70 -196 Q-66 -228 -36 -236" w={7} c={SHINE} op={0.9} />
    <Ln d="M-74 -170 Q-74 -180 -72 -186" w={5} c={SHINE} op={0.8} />
  </g>
);

// ── telescope ─────────────────────────────────────────────────────────────────
/** A brass telescope on a wooden tripod, aimed at the sky. */
const Telescope: PropEntry["draw"] = () => (
  <g>
    <Sh d={poly([[-4, -194], [4, -194], [16, -10], [4, -10]])} fill={WOOD_DARK} pen="l" penOp={0.15} sw={2.5} />
    <Sh d={poly([[-8, -196], [4, -196], [-116, -3], [-132, -3]])} fill={WOOD} pen="l" penOp={0.15} sw={2.5} />
    <Sh d={poly([[-4, -196], [8, -196], [132, -3], [116, -3]])} fill={WOOD} pen="l" penOp={0.15} sw={2.5} />
    <Sh d={poly([[-16, -206], [16, -206], [12, -188], [-12, -188]])} fill={GOLD} pen="none" sw={2.5} />
    <g transform="translate(0 -222) rotate(-28)">
      <Sh d={rect(-142, -7, 32, 14)} fill={GOLD} pen="none" sw={2.5} />
      <Sh d={rounded(-146, -9, 8, 18, 3)} fill={BLACK} pen="none" sw={2} />
      <Sh d={rect(-112, -11, 44, 22)} fill={GOLD} penOp={0.2} sw={2.5} />
      <Sh d={rect(-70, -16, 190, 32)} fill={GOLD} penOp={0.2} />
      <Sh d={rect(118, -21, 40, 42)} fill={BRASS_DARK} penOp={0.2} />
      <Ln d="M-40 -16 v32 M60 -16 v32" w={2} op={0.55} />
      <Sh d={ellipse(158, 0, 5, 19)} fill="#AFC3C8" pen="none" sw={2} />
      <Sh d={rect(-14, 14, 28, 8)} fill={BRASS_DARK} pen="none" sw={2} />
      <Ln d="M-50 -10 h150" w={4} c={SHINE} op={0.4} />
    </g>
    <path d={circle(0, -218, 5)} fill={BLACK} stroke={INK} strokeWidth={2} />
  </g>
);

// ── compass ───────────────────────────────────────────────────────────────────
const NEEDLE = [0, 18, -14];

/** A pocket compass: brass case, a rose with no letters, a red and steel needle. States 1 and 2: the needle swings. */
const Compass: PropEntry["draw"] = ({ state }) => {
  const cy = -87;
  const ticks = Array.from({ length: 32 }, (_, k) => {
    const [x1, y1] = pt(0, cy, k % 4 === 0 ? 55 : 59, k * 11.25), [x2, y2] = pt(0, cy, 64, k * 11.25);
    return `M${x1} ${y1}L${x2} ${y2}`;
  }).join("");
  const point = (deg: number, len: number, w: number, a: string, b: string) => {
    const tip = pt(0, cy, len, deg), l = pt(0, cy, w, deg - 90), r = pt(0, cy, w, deg + 90), c: Pt = [0, cy];
    return (
      <g key={deg}>
        <path d={poly([c, l, tip])} fill={a} stroke={INK} strokeWidth={1.5} strokeLinejoin="round" />
        <path d={poly([c, tip, r])} fill={b} stroke={INK} strokeWidth={1.5} strokeLinejoin="round" />
      </g>
    );
  };
  return (
    <g>
      <path d={circle(0, -191, 11) + circle(0, -191, 6)} fill={GOLD} fillRule="evenodd" stroke={INK} strokeWidth={2.5} />
      <Sh d={rounded(-9, -183, 18, 14, 3)} fill={GOLD} pen="none" sw={2.5} />
      <Sh d={circle(0, cy, 84)} fill={GOLD} penOp={0.2} />
      <Sh d={circle(0, cy, 72)} fill={BRASS_DARK} pen="none" sw={2} />
      <Sh d={circle(0, cy, 66)} fill={CREAM} penOp={0.1} sw={2} />
      <Ln d={ticks} w={1.6} op={0.7} />
      {[45, 135, 225, 315].map((d) => point(d - 90, 32, 6, SAND, CREAM))}
      {[0, 90, 180, 270].map((d) => point(d - 90, 50, 8, GOLD, SAND))}
      <g transform={`rotate(${NEEDLE[state] ?? 0} 0 ${cy})`}>
        <path d={poly([[0, cy - 56], [8, cy], [-8, cy]])} fill={SEAL} stroke={INK} strokeWidth={2.2} strokeLinejoin="round" />
        <path d={poly([[0, cy + 56], [8, cy], [-8, cy]])} fill={BLACK} stroke={INK} strokeWidth={2.2} strokeLinejoin="round" />
      </g>
      <path d={circle(0, cy, 6)} fill={GOLD} stroke={INK} strokeWidth={2} />
      <Ln d="M-46 -128 Q-30 -142 -10 -144" w={5} c={SHINE} op={0.6} />
    </g>
  );
};

// ── globe ─────────────────────────────────────────────────────────────────────
/** Coarse coastlines, as [longitude, latitude]. */
const LANDS: Pt[][] = [
  // North America
  [[-165, 65], [-150, 71], [-125, 70], [-95, 72], [-80, 68], [-65, 60], [-55, 52], [-66, 45], [-75, 38], [-80, 30], [-81, 25], [-90, 29], [-97, 26],
    [-97, 19], [-88, 16], [-83, 9], [-79, 8], [-86, 13], [-95, 16], [-106, 23], [-112, 30], [-118, 34], [-124, 41], [-124, 48], [-133, 56], [-145, 60], [-158, 58]],
  // South America
  [[-79, 8], [-72, 12], [-60, 10], [-50, 0], [-35, -6], [-39, -15], [-48, -26], [-58, -36], [-65, -42], [-68, -52], [-72, -50], [-74, -40], [-71, -30],
    [-70, -18], [-76, -12], [-81, -4], [-79, 2]],
  // Greenland
  [[-50, 60], [-42, 60], [-22, 70], [-20, 80], [-60, 82], [-70, 77], [-55, 68]],
  // Africa
  [[-17, 21], [-10, 30], [-6, 36], [10, 37], [20, 32], [32, 31], [34, 28], [43, 12], [51, 12], [42, -2], [40, -15], [35, -25], [20, -35], [18, -28],
    [12, -17], [9, -1], [5, 5], [-8, 5], [-15, 11]],
  // Eurasia
  [[-10, 36], [-9, 43], [-2, 44], [-5, 48], [0, 50], [5, 54], [10, 58], [5, 62], [15, 69], [30, 71], [60, 70], [80, 73], [110, 77], [140, 72], [170, 69],
    [180, 66], [160, 60], [143, 52], [140, 43], [128, 35], [121, 30], [117, 23], [108, 21], [106, 10], [100, 13], [98, 8], [93, 20], [80, 15], [77, 8],
    [72, 20], [57, 25], [56, 25], [59, 22], [52, 16], [43, 13], [35, 30], [28, 37], [26, 40], [18, 40], [12, 44], [13, 38], [8, 44],
    [3, 43]],
  // Britain, Japan, Madagascar, Borneo
  [[-5, 50], [1, 51], [-2, 56], [-5, 58], [-6, 55]],
  [[130, 31], [136, 34], [141, 36], [142, 41], [140, 40], [135, 36]],
  [[44, -13], [50, -15], [48, -25], [44, -24]],
  [[109, 1], [117, 7], [119, 1], [116, -4], [110, -3]],
  // Australia
  [[114, -22], [122, -18], [131, -12], [137, -12], [142, -11], [146, -19], [153, -25], [150, -37], [140, -38], [132, -32], [115, -34]],
];

const GLOBE_R = 100;
const GLOBE_Y = -210;
const TILT = -23; // the axis leans this many degrees

/** A point on the globe's face (centre at the origin, north up) placed in the prop, its axis tilted. */
const tilt = ([x, y]: Pt): Pt => {
  const c = Math.cos(rad(TILT)), s = Math.sin(rad(TILT));
  return [x * c - y * s, GLOBE_Y + x * s + y * c];
};
const at = (p: Pt) => tilt(p).map((v) => v.toFixed(1)).join(" ");

/** A coastline seen on the globe turned to `lon0`, cut at the rim (orthographic). */
function landPath(coast: Pt[], lon0: number): string {
  const R = GLOBE_R;
  const pts: Pt[] = [];
  coast.forEach(([a, b], i) => {
    const [c, d] = coast[(i + 1) % coast.length];
    for (let s = 0; s < 4; s++) pts.push([a + ((c - a) * s) / 4, b + ((d - b) * s) / 4]);
  });
  const facing = ([lo, la]: Pt) => Math.cos(rad(la)) * Math.cos(rad(lo - lon0));
  const xy = ([lo, la]: Pt): Pt => [R * Math.cos(rad(la)) * Math.sin(rad(lo - lon0)), -R * Math.sin(rad(la))];
  const start = pts.findIndex((p) => facing(p) >= 0);
  if (start < 0) return "";
  const seq = [...pts.slice(start), ...pts.slice(0, start)];
  const out: Pt[] = [];
  let exit: Pt | null = null;
  seq.forEach((p, i) => {
    const q = seq[(i + 1) % seq.length];
    const fp = facing(p), fq = facing(q);
    if (fp >= 0) out.push(xy(p));
    if (fp >= 0 !== fq >= 0) {
      const t = fp / (fp - fq);
      const m = xy([p[0] + (q[0] - p[0]) * t, p[1] + (q[1] - p[1]) * t]);
      if (fp >= 0) {
        out.push(m);
        exit = m;
      } else {
        if (exit) {
          // round the hidden stretch along the rim, the short way
          const e: Pt = exit;
          const a1 = Math.atan2(e[1], e[0]);
          let dA = Math.atan2(m[1], m[0]) - a1;
          while (dA > Math.PI) dA -= 2 * Math.PI;
          while (dA < -Math.PI) dA += 2 * Math.PI;
          const n = Math.ceil(Math.abs(dA) / 0.08);
          for (let k = 1; k < n; k++) out.push([R * Math.cos(a1 + (dA * k) / n), R * Math.sin(a1 + (dA * k) / n)]);
        }
        out.push(m);
      }
    }
  });
  return `M${out.map((q) => tilt(q).map((v) => v.toFixed(1)).join(" ")).join("L")}Z`;
}

function graticule(lon0: number): string {
  const R = GLOBE_R;
  let d = "";
  for (const lat of [-60, -30, 0, 30, 60]) {
    const y = -R * Math.sin(rad(lat)), hw = R * Math.cos(rad(lat));
    d += `M${at([-hw, y])}L${at([hw, y])}`;
  }
  for (let lon = -180; lon < 180; lon += 30) {
    let l = lon - lon0;
    while (l > 180) l -= 360;
    while (l <= -180) l += 360;
    if (Math.abs(l) > 90) continue;
    const rx = Math.abs(R * Math.sin(rad(l)));
    d += rx < 0.5 ? `M${at([0, -R])}L${at([0, R])}` : `M${at([0, -R])}A${rx.toFixed(1)} ${R} ${TILT} 0 ${l > 0 ? 1 : 0} ${at([0, R])}`;
  }
  return d;
}

/** The longitude facing the viewer in each state: 0 rests on the Atlantic, 1 to 4 turn the globe a quarter at a time. */
const GLOBE_TURN = [-20, -20, 70, 160, 250];

/** A tilted globe in a brass meridian on a turned wooden stand. States 1 to 4: it turns. */
const Globe: PropEntry["draw"] = ({ state }) => {
  const lon0 = GLOBE_TURN[state] ?? -20;
  const R = GLOBE_R;
  return (
    <g>
      <Sh d="M-80 -3 L80 -3 Q76 -24 40 -30 L-40 -30 Q-76 -24 -80 -3 Z" fill={WOOD} pen="l" penOp={0.15} />
      <Sh d="M-12 -28 Q-26 -54 -8 -72 L-8 -94 L8 -94 L8 -72 Q26 -54 12 -28 Z" fill={WOOD} pen="l" penOp={0.15} sw={2.5} />
      <Sh d="M-8 -90 Q0 -110 34 -114 L50 -104 Q14 -98 8 -90 Z" fill={GOLD} pen="none" sw={2.5} />
      <Sh d={circle(0, GLOBE_Y, R)} fill={OCEAN} penOp={0.12} />
      <Ln d={graticule(lon0)} w={1.4} op={0.3} />
      {LANDS.map((coast, k) => {
        const d = landPath(coast, lon0);
        return d ? <Sh key={k} d={d} fill={SAGE} penOp={0.18} sw={2} /> : null;
      })}
      <path d={circle(0, GLOBE_Y, R)} fill="none" stroke={INK} strokeWidth={3} />
      <Ln d={`M${at([-62, -54])}Q${at([-46, -74])} ${at([-20, -82])}`} w={7} c={SHINE} op={0.45} />
      <Sh d={`M${at([0, -R - 16])}A${R + 16} ${R + 16} 0 0 1 ${at([0, R + 16])}L${at([0, R + 6])}A${R + 6} ${R + 6} 0 0 0 ${at([0, -R - 6])}Z`}
        fill={GOLD} pen="none" sw={2.5} />
      <path d={circle(...tilt([0, -R - 11]), 6) + circle(...tilt([0, R + 11]), 6)} fill={BRASS_DARK} stroke={INK} strokeWidth={2} />
    </g>
  );
};

// ── rocket ────────────────────────────────────────────────────────────────────
/** A 1950s storybook rocket standing on its fins. State 1: ignition, flame and smoke at its feet. */
const Rocket: PropEntry["draw"] = ({ state }) => {
  const fire = state === 1;
  const puffs: [number, number, number][] = [[-96, -24, 21], [-66, -19, 16], [-112, -40, 14], [96, -24, 21], [66, -19, 16], [112, -40, 14], [-40, -16, 13], [40, -16, 13]];
  return (
    <g>
      <Sh d="M-58 -250 C-90 -200 -118 -120 -122 -3 L-100 -3 C-90 -50 -70 -90 -48 -112 Z" fill={SEAL} pen="l" penOp={0.15} />
      <Sh d="M58 -250 C90 -200 118 -120 122 -3 L100 -3 C90 -50 70 -90 48 -112 Z" fill={SEAL} pen="l" penOp={0.15} />
      {fire && (
        <g>
          <Sh d="M-30 -72 Q-36 -40 0 -8 Q36 -40 30 -72 Z" fill={FLAME} pen="none" sw={2.5} />
          <path d="M-14 -72 Q-16 -48 0 -26 Q16 -48 14 -72 Z" fill={STARGOLD} />
        </g>
      )}
      <Sh d={poly([[-30, -112], [30, -112], [38, -70], [-38, -70]])} fill={STEEL} penOp={0.15} />
      <Sh d={ellipse(0, -70, 38, 7)} fill={BLACK} pen="none" sw={2.5} />
      <Sh d="M-46 -400 L46 -400 C52 -372 62 -340 62 -300 C62 -220 56 -150 48 -110 L-48 -110 C-56 -150 -62 -220 -62 -300 C-62 -340 -52 -372 -46 -400 Z"
        fill={CREAM} penOp={0.14} />
      <Sh d="M0 -490 C28 -470 42 -436 46 -400 L-46 -400 C-42 -436 -28 -470 0 -490 Z" fill={SEAL} pen="l" penOp={0.15} />
      <Sh d={poly([[-55.5, -168], [55.5, -168], [53, -146], [-53, -146]])} fill={SEAL} pen="l" penOp={0.15} sw={2.5} />
      <Ln d="M-58 -256 Q0 -248 58 -256" w={2} op={0.5} />
      <Sh d={circle(0, -330, 27)} fill={GOLD} penOp={0.2} />
      <Sh d={circle(0, -330, 18)} fill={BLUEPRINT} pen="l" penOp={0.15} sw={2} />
      <Ln d="M-10 -338 Q-6 -344 2 -345" w={4} c={SHINE} op={0.7} />
      <Sh d={poly([[-7, -160], [7, -160], [6, -3], [-6, -3]])} fill={SEAL} pen="l" penOp={0.15} />
      <path d={[-34, 34].map((x) => circle(x, -330, 2.5)).join("") + [-205, -195].map((y) => circle(-44, y, 2.5) + circle(44, y, 2.5)).join("")} fill={INK} opacity={0.6} />
      {fire && puffs.map(([x, y, r], k) => <Sh key={k} d={circle(x, y, r)} fill={k % 2 ? "#E4D9C3" : CREAM} penOp={0.12} sw={2.5} />)}
    </g>
  );
};

// ── star chart ────────────────────────────────────────────────────────────────
type Star = [x: number, y: number];
const CONSTELLATIONS: { stars: Star[]; lines: [number, number][] }[] = [
  { stars: [[-70, -40], [-50, -46], [-32, -40], [-16, -30], [-14, -8], [10, -4], [12, -26]], lines: [[0, 1], [1, 2], [2, 3], [3, 4], [4, 5], [5, 6], [6, 3]] },
  { stars: [[6, -78], [20, -62], [34, -76], [48, -60], [60, -74]], lines: [[0, 1], [1, 2], [2, 3], [3, 4]] },
  { stars: [[30, 10], [64, 6], [40, 34], [48, 36], [56, 38], [28, 64], [68, 66]], lines: [[0, 2], [1, 4], [2, 3], [3, 4], [2, 5], [4, 6]] },
  { stars: [[-66, 14], [-58, 30], [-46, 26], [-40, 42], [-52, 46]], lines: [[0, 1], [1, 2], [2, 3], [3, 4], [4, 1]] },
];
const TWINKLE: Record<number, [number, number][]> = { 1: [[0, 0], [2, 0], [3, 0], [1, 4]], 2: [[0, 5], [2, 6], [3, 3], [1, 1]] };

const star4 = (x: number, y: number, r: number) =>
  poly([[x, y - r], [x + r * 0.28, y - r * 0.28], [x + r, y], [x + r * 0.28, y + r * 0.28], [x, y + r], [x - r * 0.28, y + r * 0.28], [x - r, y], [x - r * 0.28, y - r * 0.28]]);

/** A framed star chart: a planisphere of constellations on a night-blue ground. States 1 and 2: stars twinkle. */
const Starchart: PropEntry["draw"] = ({ state }) => {
  const cx = 0, cy = -186;
  const rand = rng(41);
  let dust = "";
  for (let k = 0; k < 46; k++) {
    const a = rand() * 360, r = Math.sqrt(rand()) * 94;
    const [x, y] = pt(cx, cy, r, a);
    dust += circle(x, y, 0.8 + rand() * 1.4);
  }
  const ticks = Array.from({ length: 72 }, (_, k) => {
    const [x1, y1] = pt(cx, cy, 101, k * 5), [x2, y2] = pt(cx, cy, k % 6 === 0 ? 108 : 105, k * 5);
    return `M${x1} ${y1}L${x2} ${y2}`;
  }).join("");
  const lines = CONSTELLATIONS.map((c) => c.lines.map(([a, b]) => `M${c.stars[a][0]} ${cy + c.stars[a][1]}L${c.stars[b][0]} ${cy + c.stars[b][1]}`).join("")).join("");
  const bright = TWINKLE[state] ?? [];
  const corners = [[-104, -308], [104, -308], [-104, -44], [104, -44]].map(([x, y]) => star4(x, y, 6)).join("");
  return (
    <g>
      <Sh d={rect(-140, -344, 280, 341)} fill={WOOD} pen="l" penOp={0.15} />
      <path d={rect(-127, -331, 254, 315)} fill={WOOD_DARK} stroke={INK} strokeWidth={2} />
      <Sh d={rect(-120, -324, 240, 301)} fill={NAVY} pen="l" penOp={0.08} sw={2} />
      <path d={rect(-124, -328, 248, 309)} fill="none" stroke={GOLD} strokeWidth={2} />
      <Sh d={circle(cx, cy, 109)} fill={BLUEPRINT} pen="none" sw={2} />
      <path d={circle(cx, cy, 100)} fill="#2F3A52" stroke={INK} strokeWidth={1.5} />
      <Ln d={ticks} w={1.2} c={STARGOLD} op={0.8} />
      <path d={dust} fill={STARGOLD} opacity={0.6} />
      <Ln d={lines} w={1.6} c={STARGOLD} op={0.65} />
      {CONSTELLATIONS.map((c, ci) =>
        c.stars.map(([x, y], si) => {
          const big = bright.some(([bc, bs]) => bc === ci && bs === si);
          return <path key={`${ci}-${si}`} d={star4(x, cy + y, big ? 10 : 5)} fill={big ? SHINE : STARGOLD} />;
        }),
      )}
      <path d={corners} fill={STARGOLD} opacity={0.8} />
      <Sh d={rect(-56, -66, 112, 24)} fill={CREAM} penOp={0.1} sw={2} />
      <Ln d="M-42 -54 h20 M-14 -54 h30 M24 -54 h18" w={2.2} op={0.7} />
    </g>
  );
};

// ── coin ──────────────────────────────────────────────────────────────────────
const BUST =
  "M-6 -46 C18 -46 26 -30 24 -14 L32 -2 L24 2 L26 8 L22 12 L24 18 C18 26 10 26 6 28 L8 40 L-26 40 C-20 30 -22 20 -30 10 C-38 -6 -34 -40 -6 -46 Z";
const HAIR = "M-8 -47 C12 -49 24 -38 23 -24 Q10 -30 -2 -27 Q-18 -22 -24 -4 L-31 8 C-38 -8 -36 -42 -8 -47 Z";
const DRAPE = "M-34 40 Q-8 48 18 40 L26 54 Q-6 64 -42 54 Z";
/** Laurel leaves along the hairline, from the brow round to the back of the head. */
const LAUREL: [x: number, y: number, deg: number][] = [[16, -36, -20], [6, -40, -5], [-4, -40, 10], [-14, -36, 30], [-22, -28, 50], [-27, -18, 70]];

/** A gold coin with a laureate head in profile and a beaded rim. */
const Coin: PropEntry["draw"] = () => {
  const cy = -80;
  const beads = Array.from({ length: 40 }, (_, k) => { const [x, y] = pt(0, cy, 70, k * 9); return circle(x, y, 1.8); }).join("");
  const legend = Array.from({ length: 13 }, (_, k) => {
    const a1 = 200 + k * 11.2, a2 = a1 + 7;
    const [x1, y1] = pt(0, cy, 58, a1), [x2, y2] = pt(0, cy, 58, a2);
    return `M${x1} ${y1}A58 58 0 0 1 ${x2} ${y2}`;
  }).join("");
  return (
    <g>
      <Sh d={circle(0, cy, 76)} fill={GOLD} penOp={0.18} />
      <path d={circle(0, cy, 64)} fill="none" stroke={INK} strokeWidth={1.8} opacity={0.6} />
      <path d={beads} fill={BRASS_DARK} />
      <Ln d={legend} w={2.4} op={0.5} />
      <g transform={`translate(0 ${cy + 2}) scale(0.92)`}>
        <Sh d={DRAPE} fill={BRASS_DARK} penOp={0.15} sw={2.2} />
        <Sh d={BUST} fill={BRASS_DARK} penOp={0.15} sw={2.2} />
        <Sh d={HAIR} fill="#7A5E30" pen="l" penOp={0.2} sw={2.2} />
        {LAUREL.map(([x, y, a], k) => (
          <path key={k} d={ellipse(x, y, 6, 2.6)} transform={`rotate(${a} ${x} ${y})`} fill={STARGOLD} stroke={INK} strokeWidth={1.2} />
        ))}
        <Ln d="M-30 -6 q-8 4 -6 12 M-30 -6 q-4 8 0 14" w={1.8} c={STARGOLD} />
        <path d={circle(15, -17, 2)} fill={INK} />
        <Ln d="M10 -24 q4 -2 8 0" w={1.6} op={0.7} />
        <Ln d="M-6 -12 q-6 4 -2 10" w={1.8} op={0.7} />
      </g>
      <Ln d="M-44 -118 Q-30 -130 -12 -132" w={4} c={SHINE} op={0.35} />
    </g>
  );
};

// ── anvil ─────────────────────────────────────────────────────────────────────
/** A blacksmith's anvil on a wooden stump. */
const Anvil: PropEntry["draw"] = () => (
  <g>
    <Sh d={poly([[-62, -96], [62, -96], [68, -3], [-68, -3]])} fill={WOOD} pen="l" penOp={0.16} />
    <Ln d="M-40 -90 L-42 -12 M-14 -88 L-14 -20 M18 -90 L20 -10 M44 -86 L46 -16" w={2} op={0.4} />
    <Rod d="M-64 -60 L64 -60" w={4} c={IRON} />
    <Sh d="M-134 -188 Q-90 -204 -50 -204 L128 -204 L128 -176 Q100 -172 66 -164 L56 -128 Q64 -108 76 -98 L76 -96 L-76 -96 L-76 -98 Q-64 -108 -56 -128 L-50 -160 Q-90 -168 -134 -188 Z"
      fill={IRON} pen="l" penOp={0.16} />
    <Sh d={rect(-50, -204, 178, 8)} fill={STEEL} pen="none" sw={2.5} />
    <Ln d="M-120 -190 Q-90 -198 -54 -198" w={3} c={STEEL} op={0.8} />
  </g>
);

export const SCIENCE_PROPS: Record<string, PropEntry> = {
  lightbulb: { label: "light bulb", box: [160, 228], place: "floor", states: 2, acts: ["switch", "glow", "pulse", "wobble"], draw: Lightbulb },
  battery: { label: "battery", box: [140, 214], place: "floor", states: 1, acts: ["wobble", "bounce", "pulse", "glow"], draw: Battery },
  gears: { label: "gears", box: [290, 290], place: "wall", states: 1, acts: ["spin", "wobble", "pulse"], draw: Gears },
  telegraph: { label: "telegraph key", box: [270, 140], place: "floor", states: 3, acts: ["cycle", "wobble", "bounce"], draw: Telegraph },
  telephone: { label: "candlestick telephone", box: [200, 302], place: "floor", states: 3, acts: ["cycle", "shake", "wobble"], draw: Telephone },
  radio: { label: "valve radio", box: [240, 290], place: "floor", states: 2, acts: ["switch", "glow", "shake", "wobble"], draw: Radio },
  typewriter: { label: "typewriter", box: [290, 238], place: "floor", states: 3, acts: ["cycle", "shake", "wobble"], draw: Typewriter },
  punchcard: { label: "punched card", box: [324, 154], place: "wall", states: 1, acts: ["wobble", "bounce", "pulse"], draw: Punchcard },
  relaycabinet: {
    label: "relay computer", box: [420, 540], place: "floor", states: 3, acts: ["switch", "cycle", "shake", "glow"], portal: [0, -313], draw: RelayCabinet,
  },
  terminal: { label: "computer terminal", box: [320, 310], place: "floor", states: 3, acts: ["switch", "cycle", "glow", "wobble"], draw: Terminal },
  microscope: { label: "microscope", box: [190, 274], place: "floor", states: 1, acts: ["wobble", "glow", "pulse"], draw: Microscope },
  testtubes: { label: "test tubes", box: [240, 214], place: "floor", states: 3, acts: ["cycle", "shake", "glow", "wobble"], draw: Testtubes },
  magnifier: { label: "magnifying glass", box: [214, 262], place: "wall", states: 1, acts: ["wobble", "pulse", "bounce", "glow"], draw: Magnifier },
  telescope: { label: "telescope", box: [320, 330], place: "floor", states: 1, acts: ["wobble", "pulse"], draw: Telescope },
  compass: { label: "compass", box: [180, 208], place: "wall", states: 3, acts: ["cycle", "wobble", "pulse", "glow"], draw: Compass },
  globe: { label: "globe", box: [250, 340], place: "floor", states: 5, acts: ["cycle", "wobble", "pulse"], draw: Globe },
  rocket: { label: "rocket", box: [260, 500], place: "floor", states: 2, acts: ["switch", "shake", "wobble", "glow"], draw: Rocket },
  starchart: { label: "star chart", box: [290, 350], place: "wall", states: 3, acts: ["cycle", "glow", "wobble", "swing"], draw: Starchart },
  coin: { label: "coin", box: [160, 160], place: "wall", states: 1, acts: ["spin", "bounce", "glow", "pulse"], draw: Coin },
  anvil: { label: "anvil", box: [280, 214], place: "floor", states: 1, acts: ["shake", "wobble", "pulse"], draw: Anvil },
};
