/*
 * Backdrops: the room or landscape each chapter happens in, full frame, drawn
 * once and cached as a bitmap. The floor line is BANDS.floor; props, people
 * and the guide stand on it. Decoration keeps to the sides and the upper wall
 * so the middle of the stage stays open for what the narration is about, and
 * the plaque and caption bands stay calm enough to read over.
 */
import React from "react";
import type { Drawing } from "./bitmap";
import { FrameInk } from "./frame";
import { HATCH, HATCH_LIGHT, LINES, Sh, circle, ellipse, poly, rect, rounded } from "./ink";
import {
  BANDS, BEIGE, BLUEPRINT, CREAM, GOLD, H, INK, IVORY, NAVY, PINK, SAGE, SAND, SEAL, SLATE, STARGOLD, W, WOOD, WOOD_DARK,
} from "./palette";

export const BACKDROPS = [
  "study", "workshop", "nightsky", "laboratory", "street", "countryside", "harbour", "blueprint", "factory", "maproom",
] as const;
export type Backdrop = (typeof BACKDROPS)[number];

/** Whether a backdrop is dark (the label and tags keep their ivory plate either way). */
export const DARK_BACKDROPS: ReadonlySet<Backdrop> = new Set(["nightsky", "blueprint"]);

/** A small deterministic random sequence (mulberry32). */
export function rng(seed: number) {
  let a = seed >>> 0;
  return () => {
    a = (a + 0x6d2b79f5) >>> 0;
    let t = a;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

const F = BANDS.floor;

/** Wooden planks from the floor line down, with hatch and a few joints. */
const PlankFloor: React.FC<{ color: string; seed: number }> = ({ color, seed }) => {
  const r = rng(seed);
  const rows = [F, F + 70, F + 160, F + 280, F + 430, H];
  return (
    <g>
      <rect x={0} y={F} width={W} height={H - F} fill={color} />
      <rect x={0} y={F} width={W} height={H - F} fill={`url(#${HATCH})`} opacity={0.12} />
      {rows.slice(0, -1).map((y, i) => (
        <g key={y}>
          <line x1={0} x2={W} y1={y} y2={y} stroke={INK} strokeWidth={i === 0 ? 4 : 1.6} opacity={i === 0 ? 1 : 0.4} />
          {Array.from({ length: 3 }, (_, k) => {
            const x = 80 + r() * 920;
            return <line key={k} x1={x} x2={x} y1={y} y2={rows[i + 1]} stroke={INK} strokeWidth={1.4} opacity={0.3} />;
          })}
        </g>
      ))}
    </g>
  );
};

const Study: React.FC = () => {
  const r = rng(11);
  const bookColors = [SEAL, BLUEPRINT, SAGE, GOLD, "#6A4560", "#8A4529", SLATE];
  const shelves = [560, 760, 960, 1160];
  return (
    <g>
      {/* wallpaper: ivory with faint stripes, a wooden dado below */}
      <rect width={W} height={F} fill={IVORY} />
      <rect width={W} height={F} fill={`url(#${HATCH})`} opacity={0.06} />
      {Array.from({ length: 14 }, (_, i) => (
        <line key={i} x1={40 + i * 76} x2={40 + i * 76} y1={0} y2={1120} stroke={PINK} strokeWidth={6} opacity={0.18} />
      ))}
      <Sh d={rect(0, 1120, W, F - 1120)} fill={WOOD} pen="l" penOp={0.14} sw={3} />
      <line x1={0} x2={W} y1={1140} y2={1140} stroke={INK} strokeWidth={2} opacity={0.5} />
      {[0, 1, 2, 3, 4].map((i) => (
        <path key={i} d={rect(30 + i * 210, 1170, 180, 140)} fill="none" stroke={INK} strokeWidth={2} opacity={0.35} />
      ))}
      {/* bookcase, left */}
      <Sh d={rect(40, 470, 230, F - 470)} fill={WOOD_DARK} pen="l" penOp={0.14} />
      {shelves.map((y) => (
        <g key={y}>
          {(() => {
            let x = 58;
            const out: React.ReactNode[] = [];
            while (x < 248) {
              const w = 14 + Math.floor(r() * 14);
              const h = 120 + Math.floor(r() * 50);
              if (x + w > 252) break;
              out.push(<Sh key={x} d={rect(x, y + 180 - h, w, h)} fill={bookColors[Math.floor(r() * bookColors.length)]} pen="l" penOp={0.15} sw={2} />);
              x += w + 2;
            }
            return out;
          })()}
          <Sh d={rect(40, y + 180, 230, 18)} fill={WOOD} pen="none" sw={2.5} />
        </g>
      ))}
      {/* window, right: night-blue panes, curtains */}
      <Sh d={rect(800, 480, 220, 380)} fill={BLUEPRINT} pen="l" penOp={0.18} sw={4} />
      <path d={`M910 480V860M800 670H1020`} stroke={CREAM} strokeWidth={10} />
      <path d={`M910 480V860M800 670H1020`} stroke={INK} strokeWidth={2} opacity={0.5} />
      <path d={circle(968, 560, 22)} fill={STARGOLD} opacity={0.85} />
      <Sh d={`M780 450 Q790 700 772 900 L830 900 Q820 700 840 450Z`} fill={SEAL} pen="l" penOp={0.2} />
      <Sh d={`M1040 450 Q1030 700 1050 900 L1062 900 L1062 450Z`} fill={SEAL} pen="l" penOp={0.2} />
      <Sh d={rect(770, 436, 300, 18)} fill={GOLD} pen="none" sw={2.5} />
      <PlankFloor color={SAND} seed={3} />
      {/* rug edge */}
      <Sh d={poly([[180, F + 120], [900, F + 120], [960, F + 300], [120, F + 300]])} fill="#9A4A36" penOp={0.18} sw={3} op={0.85} />
      <path d={poly([[200, F + 140], [880, F + 140], [928, F + 280], [152, F + 280]])} fill="none" stroke={GOLD} strokeWidth={4} opacity={0.8} />
    </g>
  );
};

const Workshop: React.FC = () => {
  const r = rng(29);
  return (
    <g>
      <rect width={W} height={F} fill={BEIGE} />
      <rect width={W} height={F} fill={`url(#${HATCH})`} opacity={0.07} />
      {/* pegboard, upper left, with hanging tools */}
      <Sh d={rect(40, 470, 330, 470)} fill="#C7AE86" penOp={0.14} sw={3} />
      {Array.from({ length: 9 }, (_, i) =>
        Array.from({ length: 12 }, (_, j) => <circle key={`${i}-${j}`} cx={62 + i * 36} cy={492 + j * 38} r={3} fill={INK} opacity={0.4} />),
      )}
      <g>
        {/* saw */}
        <Sh d={poly([[80, 560], [210, 560], [230, 640], [80, 640]])} fill="#B9BDC2" pen="d" penOp={0.15} sw={2.5} />
        <Sh d={rounded(60, 548, 40, 104, 12)} fill={WOOD} pen="l" penOp={0.15} sw={2.5} />
        {/* hammer */}
        <Sh d={rect(280, 540, 14, 150)} fill={WOOD} pen="l" penOp={0.15} sw={2.5} />
        <Sh d={rect(250, 530, 74, 30)} fill="#6E7378" pen="l" penOp={0.15} sw={2.5} />
        {/* wrench */}
        <Sh d={`M120 740 l120 120 l-16 16 l-120 -120z`} fill="#8D9298" pen="l" penOp={0.15} sw={2.5} />
        <Sh d={circle(112, 734, 22)} fill="#8D9298" pen="none" sw={2.5} />
        <path d={circle(112, 734, 9)} fill="#C7AE86" stroke={INK} strokeWidth={2} />
        {/* coil of wire */}
        <path d={circle(300, 820, 46)} fill="none" stroke={SEAL} strokeWidth={9} />
        <path d={circle(300, 820, 34)} fill="none" stroke={SEAL} strokeWidth={9} />
        <path d={circle(300, 820, 46)} fill="none" stroke={INK} strokeWidth={1.5} />
      </g>
      {/* shelf with jars, right */}
      {[620, 860].map((y) => (
        <g key={y}>
          <Sh d={rect(780, y, 260, 18)} fill={WOOD} pen="l" penOp={0.15} sw={2.5} />
          {Array.from({ length: 4 }, (_, i) => {
            const h = 60 + Math.floor(r() * 50);
            const x = 800 + i * 60;
            return (
              <g key={i}>
                <Sh d={rounded(x, y - h, 44, h, 8)} fill={[SAGE, GOLD, "#B9BDC2", PINK][i]} pen="d" penOp={0.15} sw={2.5} />
                <Sh d={rect(x + 6, y - h - 12, 32, 12)} fill={WOOD_DARK} pen="none" sw={2} />
              </g>
            );
          })}
        </g>
      ))}
      {/* a lamp hanging from the ceiling */}
      <line x1={540} x2={540} y1={0} y2={170} stroke={INK} strokeWidth={3} opacity={0.6} />
      <Sh d={`M480 230 Q540 150 600 230Z`} fill={SLATE} pen="l" penOp={0.15} sw={3} />
      {/* a low workbench against the left wall */}
      <Sh d={rect(30, 1150, 300, 30)} fill={WOOD} pen="l" penOp={0.14} />
      <Sh d={rect(50, 1180, 26, F - 1180)} fill={WOOD_DARK} pen="l" penOp={0.14} />
      <Sh d={rect(280, 1180, 26, F - 1180)} fill={WOOD_DARK} pen="l" penOp={0.14} />
      <Sh d={rect(120, 1100, 60, 50)} fill="#B9BDC2" pen="d" penOp={0.15} sw={2.5} />
      {/* stone floor */}
      <rect x={0} y={F} width={W} height={H - F} fill="#BDB2A0" />
      <rect x={0} y={F} width={W} height={H - F} fill={`url(#${HATCH})`} opacity={0.14} />
      <line x1={0} x2={W} y1={F} y2={F} stroke={INK} strokeWidth={4} />
      {[F + 110, F + 260, F + 450].map((y, i) => (
        <g key={y}>
          <line x1={0} x2={W} y1={y} y2={y} stroke={INK} strokeWidth={1.5} opacity={0.3} />
          {Array.from({ length: 4 }, (_, k) => {
            const x = (k * 290 + (i % 2) * 145) % W;
            return <line key={k} x1={x} x2={x} y1={i === 0 ? F : [F, F + 110, F + 260][i]} y2={y} stroke={INK} strokeWidth={1.5} opacity={0.3} />;
          })}
        </g>
      ))}
    </g>
  );
};

const NightSky: React.FC = () => {
  const r = rng(7);
  return (
    <g>
      <rect width={W} height={H} fill={NAVY} />
      <rect width={W} height={F} fill={`url(#${HATCH_LIGHT})`} opacity={0.05} />
      {Array.from({ length: 110 }, (_, i) => {
        const x = 40 + r() * 1000, y = 40 + r() * (F - 160);
        const big = r() > 0.88;
        return <circle key={i} cx={x} cy={y} r={big ? 3.2 : 1.6} fill={STARGOLD} opacity={big ? 0.9 : 0.5 + r() * 0.3} />;
      })}
      {/* a soft pool of lantern light behind the stage, so dark coats still read against the night */}
      <defs>
        <radialGradient id="pool" cx="50%" cy="50%" r="50%">
          <stop offset="0%" stopColor="#56607A" stopOpacity={0.95} />
          <stop offset="70%" stopColor="#3A4560" stopOpacity={0.55} />
          <stop offset="100%" stopColor={NAVY} stopOpacity={0} />
        </radialGradient>
      </defs>
      <ellipse cx={540} cy={1040} rx={470} ry={430} fill="url(#pool)" />
      {/* a crescent moon, upper right */}
      <path d={circle(930, 590, 64)} fill={STARGOLD} />
      <path d={circle(958, 572, 58)} fill={NAVY} />
      {/* rolling hills to the floor line, then a darker meadow */}
      <Sh d={`M0 ${F - 120} Q220 ${F - 230} 470 ${F - 120} T 1080 ${F - 150} V${F} H0Z`} fill="#33405A" pen="l" penOp={0.1} sw={2.5} />
      <Sh d={`M0 ${F - 40} Q300 ${F - 110} 620 ${F - 40} T 1080 ${F - 60} V${F} H0Z`} fill="#2D3A40" pen="l" penOp={0.1} sw={2.5} />
      <rect x={0} y={F} width={W} height={H - F} fill="#273036" />
      <rect x={0} y={F} width={W} height={H - F} fill={`url(#${HATCH_LIGHT})`} opacity={0.07} />
      <line x1={0} x2={W} y1={F} y2={F} stroke={IVORY} strokeWidth={2} opacity={0.35} />
      {/* a few grass tufts */}
      {Array.from({ length: 14 }, (_, i) => {
        const x = 30 + r() * 1020, y = F + 40 + r() * 420;
        return <path key={i} d={`M${x} ${y} l-6 -18 M${x} ${y} l2 -22 M${x} ${y} l9 -16`} stroke={SAGE} strokeWidth={2.5} opacity={0.45} />;
      })}
    </g>
  );
};

// ── shared bits ──────────────────────────────────────────────────────────────

/** A plain wall or sky from the top to `to`, with the house's faint hatch. */
const Wall: React.FC<{ color: string; to?: number; op?: number }> = ({ color, to = F, op = 0.06 }) => (
  <g>
    <rect width={W} height={to} fill={color} />
    <rect width={W} height={to} fill={`url(#${HATCH})`} opacity={op} />
  </g>
);

/** Ground from the floor line down: a flat colour, hatch and the floor line. */
const Ground: React.FC<{ color: string; op?: number; line?: string; lineOp?: number }> = ({ color, op = 0.12, line = INK, lineOp = 1 }) => (
  <g>
    <rect x={0} y={F} width={W} height={H - F} fill={color} />
    <rect x={0} y={F} width={W} height={H - F} fill={`url(#${HATCH})`} opacity={op} />
    <line x1={0} x2={W} y1={F} y2={F} stroke={line} strokeWidth={4} opacity={lineOp} />
  </g>
);

/** An irregular smooth outline (a coast, a crown of leaves) around (cx, cy). */
function blob(cx: number, cy: number, rx: number, ry: number, n: number, seed: number, wobble = 0.35) {
  const r = rng(seed);
  const pts = Array.from({ length: n }, (_, i) => {
    const a = (i / n) * Math.PI * 2;
    const k = 1 - wobble / 2 + r() * wobble;
    return [cx + rx * k * Math.cos(a), cy + ry * k * Math.sin(a)] as const;
  });
  const mid = (i: number) => {
    const [x1, y1] = pts[i % n], [x2, y2] = pts[(i + 1) % n];
    return [(x1 + x2) / 2, (y1 + y2) / 2] as const;
  };
  let d = `M${mid(0)[0]} ${mid(0)[1]}`;
  for (let i = 1; i <= n; i++) {
    const [px, py] = pts[i % n], [mx, my] = mid(i);
    d += `Q${px} ${py} ${mx} ${my}`;
  }
  return `${d}Z`;
}

/** A bumpy outline (a cloud, a crown of leaves): arcs bulging out between points round an ellipse. */
function bumps(cx: number, cy: number, rx: number, ry: number, n: number) {
  const pts = Array.from({ length: n }, (_, i) => {
    const a = (i / n) * Math.PI * 2;
    return [cx + rx * Math.cos(a), cy + ry * Math.sin(a)] as const;
  });
  let d = `M${pts[0][0]} ${pts[0][1]}`;
  for (let i = 1; i <= n; i++) {
    const [x0, y0] = pts[i - 1], [x1, y1] = pts[i % n];
    const c = Math.hypot(x1 - x0, y1 - y0) * 0.62;
    d += `A${c} ${c} 0 0 1 ${x1} ${y1}`;
  }
  return `${d}Z`;
}

/** A flat-bottomed cloud. */
function cloud(cx: number, cy: number, w: number, h: number) {
  const p = [
    [cx - w / 2, cy], [cx - w * 0.26, cy - h * 0.55], [cx + w * 0.08, cy - h], [cx + w * 0.34, cy - h * 0.5], [cx + w / 2, cy],
  ];
  let d = `M${p[0][0]} ${p[0][1]}`;
  for (let i = 1; i < p.length; i++) {
    const c = Math.hypot(p[i][0] - p[i - 1][0], p[i][1] - p[i - 1][1]) * 0.6;
    d += `A${c} ${c} 0 0 1 ${p[i][0]} ${p[i][1]}`;
  }
  return `${d}Z`;
}

/** An arched window: a round head on a rectangle, with mullions. */
const ArchWindow: React.FC<{ x: number; y: number; w: number; h: number; glass: string; rows?: number }> = ({ x, y, w, h, glass, rows = 3 }) => {
  const d = `M${x} ${y + h}V${y + w / 2}A${w / 2} ${w / 2} 0 0 1 ${x + w} ${y + w / 2}V${y + h}Z`;
  return (
    <g>
      <Sh d={d} fill={glass} pen="d" penOp={0.08} sw={0} />
      {Array.from({ length: rows - 1 }, (_, i) => {
        const yy = y + w / 2 + ((h - w / 2) * (i + 1)) / rows;
        return <line key={i} x1={x} x2={x + w} y1={yy} y2={yy} stroke={INK} strokeWidth={3} opacity={0.7} />;
      })}
      <line x1={x + w / 2} x2={x + w / 2} y1={y} y2={y + h} stroke={INK} strokeWidth={3} opacity={0.7} />
      <path d={d} fill="none" stroke={INK} strokeWidth={4} strokeLinejoin="round" />
      <Sh d={rect(x - 10, y + h, w + 20, 14)} fill={CREAM} pen="none" sw={2.5} />
    </g>
  );
};

/** Writing shown as short strokes (fonts do not load in these bitmaps). */
const Scribble: React.FC<{ x: number; y: number; w: number; lines: number; gap?: number; color?: string; op?: number; seed: number; sw?: number }> = ({
  x, y, w, lines, gap = 14, color = INK, op = 0.55, seed, sw = 2.2,
}) => {
  const r = rng(seed);
  const out: React.ReactNode[] = [];
  for (let l = 0; l < lines; l++) {
    let xx = x;
    const end = x + w * (l === lines - 1 ? 0.6 : 1);
    while (xx < end) {
      const len = Math.min(10 + r() * 26, end - xx);
      out.push(<line key={`${l}-${xx}`} x1={xx} x2={xx + len} y1={y + l * gap} y2={y + l * gap} stroke={color} strokeWidth={sw} strokeLinecap="round" />);
      xx += len + 7;
    }
  }
  return <g opacity={op}>{out}</g>;
};

// ── laboratory ───────────────────────────────────────────────────────────────

const GLASS = "#D3DCD6";

/** A glass vessel standing at (x, y): a round flask, a conical flask or a stoppered bottle, part filled. */
const Vessel: React.FC<{ kind: "flask" | "cone" | "bottle"; x: number; y: number; s?: number; liquid: string }> = ({ kind, x, y, s = 1, liquid }) => {
  let glass: string, fill: string, extra: React.ReactNode = null;
  if (kind === "flask") {
    const r = 26 * s, cy = y - r, hw = 0.95 * r, y0 = cy + 0.3 * r;
    glass = `${circle(x, cy, r)}${rect(x - 7 * s, cy - r - 40 * s, 14 * s, 42 * s)}`;
    fill = `M${x - hw} ${y0}A${r} ${r} 0 0 0 ${x + hw} ${y0}Z`;
  } else if (kind === "cone") {
    glass = poly([[x - 8 * s, y - 72 * s], [x + 8 * s, y - 72 * s], [x + 8 * s, y - 46 * s], [x + 30 * s, y], [x - 30 * s, y], [x - 8 * s, y - 46 * s]]);
    fill = poly([[x - 20 * s, y - 22 * s], [x + 20 * s, y - 22 * s], [x + 30 * s, y], [x - 30 * s, y]]);
  } else {
    glass = `${rounded(x - 18 * s, y - 62 * s, 36 * s, 62 * s, 7 * s)}${rect(x - 7 * s, y - 78 * s, 14 * s, 18 * s)}`;
    fill = rounded(x - 18 * s, y - 36 * s, 36 * s, 36 * s, 7 * s);
    extra = <Sh d={rect(x - 9 * s, y - 88 * s, 18 * s, 12 * s)} fill={WOOD_DARK} pen="none" sw={2} />;
  }
  return (
    <g>
      <path d={glass} fill={GLASS} />
      <Sh d={fill} fill={liquid} pen="d" penOp={0.14} sw={0} />
      <path d={glass} fill="none" stroke={INK} strokeWidth={2.5} strokeLinejoin="round" />
      {extra}
    </g>
  );
};

const Laboratory: React.FC = () => {
  const shelves: { y: number; items: [kind: "flask" | "cone" | "bottle", x: number, liquid: string][] }[] = [
    { y: 680, items: [["bottle", 82, SEAL], ["flask", 128, SAGE], ["bottle", 176, GOLD], ["cone", 220, BLUEPRINT]] },
    { y: 870, items: [["cone", 88, GOLD], ["bottle", 138, SLATE], ["flask", 188, PINK], ["bottle", 228, SAGE]] },
    { y: 1050, items: [["flask", 86, BLUEPRINT], ["bottle", 132, "#8A4529"], ["cone", 182, SAGE], ["bottle", 226, GOLD]] },
  ];
  return (
    <g>
      <Wall color="#DEDFCF" />
      {/* white tiles to shoulder height, a green trim along their top */}
      <rect x={0} y={1040} width={W} height={F - 1040} fill="#E9E6DA" />
      {Array.from({ length: 14 }, (_, i) => (
        <line key={i} x1={36 + i * 78} x2={36 + i * 78} y1={1040} y2={F} stroke={INK} strokeWidth={1.4} opacity={0.2} />
      ))}
      {[1116, 1192, 1268].map((y) => <line key={y} x1={0} x2={W} y1={y} y2={y} stroke={INK} strokeWidth={1.4} opacity={0.2} />)}
      <Sh d={rect(-4, 1026, W + 8, 16)} fill={SAGE} pen="none" sw={2.5} />
      {/* a brass gas pipe along the top of the wall, down to the bench */}
      <path d={`M0 452H1040V1150`} fill="none" stroke={INK} strokeWidth={13} strokeLinejoin="round" />
      <path d={`M0 452H1040V1150`} fill="none" stroke={GOLD} strokeWidth={8} strokeLinejoin="round" />
      {[160, 420, 680, 940].map((x) => <Sh key={x} d={rect(x, 440, 14, 24)} fill={WOOD_DARK} pen="none" sw={2} />)}
      {/* a glass-fronted cabinet of flasks, left */}
      <Sh d={rect(40, 490, 220, F - 490)} fill={WOOD_DARK} pen="l" penOp={0.14} />
      <rect x={56} y={506} width={188} height={560} fill="#CBD3CB" />
      {shelves.map(({ y, items }) => (
        <g key={y}>
          {items.map(([k, x, c]) => <Vessel key={x} kind={k} x={x} y={y} s={k === "flask" ? 1 : 0.95} liquid={c} />)}
          <Sh d={rect(56, y, 188, 12)} fill={WOOD} pen="none" sw={2} />
        </g>
      ))}
      <line x1={150} x2={150} y1={506} y2={1066} stroke={WOOD_DARK} strokeWidth={8} />
      <path d={`M70 600l40 -60M168 640l50 -70`} stroke={IVORY} strokeWidth={4} opacity={0.5} strokeLinecap="round" />
      <path d={rect(56, 506, 188, 560)} fill="none" stroke={INK} strokeWidth={2.5} />
      {[56, 152].map((x) => (
        <g key={x}>
          <path d={rect(x, 1086, 92, 236)} fill="none" stroke={INK} strokeWidth={2} opacity={0.5} />
          <path d={circle(x + (x === 56 ? 80 : 12), 1200, 5)} fill={GOLD} stroke={INK} strokeWidth={1.5} />
        </g>
      ))}
      {/* a framed chart of a molecule, upper right */}
      <Sh d={rect(806, 500, 224, 220)} fill={WOOD_DARK} pen="l" penOp={0.14} />
      <Sh d={rect(820, 514, 196, 192)} fill={CREAM} pen="d" penOp={0.06} sw={2} />
      <path d={`M862 586L926 556L986 600L950 652L880 648Z M926 556L950 652`} fill="none" stroke={INK} strokeWidth={3} opacity={0.7} />
      {([[862, 586, SEAL], [926, 556, BLUEPRINT], [986, 600, IVORY], [950, 652, SEAL], [880, 648, SAGE]] as const).map(([x, y, c]) => (
        <Sh key={`${x}`} d={circle(x, y, 13)} fill={c} pen="d" penOp={0.12} sw={2.5} />
      ))}
      <Scribble x={850} y={682} w={130} lines={1} seed={41} />
      {/* a bench along the right wall: a retort over a spirit lamp, a receiving flask */}
      <Sh d={rect(806, 1176, 254, F - 1176)} fill="#7A5A40" pen="l" penOp={0.14} />
      <path d={`M933 1190V${F - 14}`} stroke={INK} strokeWidth={2} opacity={0.5} />
      <path d={`${rect(820, 1190, 100, F - 1206)}${rect(946, 1190, 100, F - 1206)}`} fill="none" stroke={INK} strokeWidth={2} opacity={0.45} />
      <Sh d={rect(796, 1150, 280, 26)} fill={WOOD} pen="l" penOp={0.14} />
      <Sh d={rect(818, 1140, 64, 10)} fill="#3B3A40" pen="none" sw={2} />
      <Sh d={rect(834, 960, 8, 182)} fill="#6E7378" pen="none" sw={2} />
      <line x1={838} x2={880} y1={1096} y2={1096} stroke={INK} strokeWidth={3} />
      <Sh d={rounded(862, 1118, 42, 32, 6)} fill={SAGE} pen="d" penOp={0.14} sw={2.5} />
      <path d={`M883 1116q-10 -14 0 -24q10 10 0 24z`} fill={STARGOLD} stroke={INK} strokeWidth={1.8} />
      <path d={`${circle(883, 1056, 38)}`} fill={GLASS} />
      <Sh d={`M847 1068A38 38 0 0 0 919 1068Z`} fill={SEAL} pen="d" penOp={0.14} sw={0} />
      <path d={`M896 1021L1006 1088L1000 1098L908 1044`} fill={GLASS} stroke={INK} strokeWidth={2.5} strokeLinejoin="round" />
      <path d={circle(883, 1056, 38)} fill="none" stroke={INK} strokeWidth={2.5} />
      <ellipse cx={883} cy={1096} rx={34} ry={5} fill="none" stroke={INK} strokeWidth={2.5} />
      <Vessel kind="flask" x={1012} y={1150} s={1.15} liquid={GOLD} />
      {/* a tiled floor */}
      <rect x={0} y={F} width={W} height={H - F} fill="#DAD1BC" />
      {Array.from({ length: 5 }, (_, j) =>
        Array.from({ length: 9 }, (_, i) => ((i + j) % 2 === 0 ? <rect key={`${i}-${j}`} x={i * 120} y={F + j * 120} width={120} height={120} fill="#BDB2A0" /> : null)),
      )}
      <rect x={0} y={F} width={W} height={H - F} fill={`url(#${HATCH})`} opacity={0.12} />
      <line x1={0} x2={W} y1={F} y2={F} stroke={INK} strokeWidth={4} />
    </g>
  );
};

// ── street ───────────────────────────────────────────────────────────────────

/** A gas lamp on its post, foot at (x, F). */
const GasLamp: React.FC<{ x: number }> = ({ x }) => (
  <g>
    <Sh d={rect(x - 6, 856, 12, F - 900)} fill="#3B3A40" pen="none" sw={2.5} />
    <Sh d={poly([[x - 18, F], [x + 18, F], [x + 12, F - 46], [x - 12, F - 46]])} fill="#3B3A40" pen="none" sw={2.5} />
    <line x1={x - 24} x2={x + 24} y1={884} y2={884} stroke={INK} strokeWidth={4} />
    <Sh d={rect(x - 12, 846, 24, 12)} fill="#3B3A40" pen="none" sw={2} />
    <Sh d={poly([[x - 24, 776], [x + 24, 776], [x + 17, 846], [x - 17, 846]])} fill="#EFE0AE" pen="d" penOp={0.08} sw={3} />
    <line x1={x} x2={x} y1={776} y2={846} stroke={INK} strokeWidth={2} opacity={0.6} />
    <Sh d={poly([[x - 32, 778], [x, 744], [x + 32, 778]])} fill="#3B3A40" pen="none" sw={2.5} />
    <path d={circle(x, 738, 6)} fill="#3B3A40" stroke={INK} strokeWidth={2} />
  </g>
);

/** A striped shop awning from x0 to x1, its top edge at y. */
const Awning: React.FC<{ x0: number; x1: number; y: number; a: string; b: string }> = ({ x0, x1, y, a, b }) => {
  const n = 7, sw = (x1 - x0) / n, drop = 54;
  return (
    <g>
      {Array.from({ length: n }, (_, i) => {
        const xa = x0 + i * sw;
        return (
          <g key={i}>
            <Sh d={poly([[xa, y], [xa + sw, y], [xa + sw, y + drop], [xa, y + drop]])} fill={i % 2 ? b : a} pen="d" penOp={0.1} sw={0} />
            <Sh d={`M${xa} ${y + drop}A${sw / 2} ${sw / 2} 0 0 0 ${xa + sw} ${y + drop}Z`} fill={i % 2 ? b : a} pen="none" sw={0} />
          </g>
        );
      })}
      <path d={`M${x0} ${y}H${x1}V${y + drop}${Array.from({ length: n }, (_, i) => `A${sw / 2} ${sw / 2} 0 0 1 ${x1 - (i + 1) * sw} ${y + drop}`).join("")}Z`}
        fill="none" stroke={INK} strokeWidth={3} strokeLinejoin="round" />
    </g>
  );
};

/** A shop: upper storey with two windows, a sign board, an awning, a window of wares and a door. */
const Shop: React.FC<{ x: number; w: number; plaster: string; front: string; awning: [string, string]; doorLeft: boolean; wares: React.ReactNode; seed: number }> = ({
  x, w, plaster, front, awning, doorLeft, wares, seed,
}) => {
  const doorX = doorLeft ? x + 12 : x + w - 70;
  const winX = doorLeft ? x + 84 : x + 14;
  return (
    <g>
      <Sh d={rect(x, 430, w, 530)} fill={plaster} pen="d" penOp={0.1} />
      <Sh d={rect(x - 10, 414, w + 20, 22)} fill={WOOD} pen="l" penOp={0.14} />
      {[0, 1].map((i) => {
        const wx = x + 34 + i * (w - 138);
        return (
          <g key={i}>
            <Sh d={rect(wx, 510, 70, 150)} fill="#8FA3A8" pen="d" penOp={0.12} />
            <path d={`M${wx + 35} 510V660M${wx} 585H${wx + 70}`} stroke={CREAM} strokeWidth={6} />
            <Sh d={rect(wx - 8, 660, 86, 12)} fill={CREAM} pen="none" sw={2.5} />
          </g>
        );
      })}
      {[0, 1].map((i) => {
        const wx = x + 34 + i * (w - 138);
        return <Sh key={i} d={rect(wx, 750, 70, 120)} fill="#8FA3A8" pen="d" penOp={0.12} />;
      })}
      <Sh d={rect(x, 958, w, F - 958)} fill={front} pen="l" penOp={0.14} />
      <Sh d={rect(x + 10, 970, w - 20, 54)} fill="#2F3A33" pen="l" penOp={0.1} sw={2.5} />
      <Scribble x={x + 36} y={997} w={w - 72} lines={1} color={GOLD} op={0.9} seed={seed} sw={4} />
      <Awning x0={x} x1={x + w} y={1034} a={awning[0]} b={awning[1]} />
      <Sh d={rect(winX, 1110, w - 98, 200)} fill="#C6D0CB" pen="d" penOp={0.06} sw={3} />
      {wares}
      <path d={`M${winX + (w - 98) / 2} 1110V1310M${winX} 1200H${winX + w - 98}`} stroke={front} strokeWidth={6} />
      <path d={rect(winX, 1110, w - 98, 200)} fill="none" stroke={INK} strokeWidth={3} />
      <Sh d={rect(doorX, 1100, 58, F - 1100)} fill={WOOD_DARK} pen="l" penOp={0.14} />
      <path d={rect(doorX + 10, 1114, 38, 90)} fill="none" stroke={INK} strokeWidth={2} opacity={0.5} />
      <path d={circle(doorX + (doorLeft ? 48 : 10), 1236, 4)} fill={GOLD} stroke={INK} strokeWidth={1.5} />
    </g>
  );
};

const Street: React.FC = () => {
  const r = rng(53);
  const lower = "#7F8A8C";
  return (
    <g>
      <Wall color="#D5DBD6" op={0.05} />
      {/* the far end of the street: low, pale rooftops and a spire */}
      <Sh d={poly([[548, 1080], [560, 950], [572, 1080]])} fill="#BCC2BF" pen="none" sw={2} stroke={lower} />
      <Sh d={poly([
        [230, F], [230, 1104], [300, 1104], [300, 1066], [340, 1036], [380, 1066], [380, 1092], [452, 1092], [452, 1120], [520, 1120], [520, 1080],
        [600, 1080], [600, 1104], [676, 1104], [676, 1060], [716, 1030], [756, 1060], [756, 1112], [850, 1112], [850, F],
      ])} fill="#BCC2BF" pen="d" penOp={0.06} sw={2} stroke={lower} />
      {[[318, 1030], [470, 1090], [620, 1074], [780, 1088]].map(([x, y]) => (
        <Sh key={x} d={rect(x, y, 14, 26)} fill="#BCC2BF" pen="none" sw={2} stroke={lower} />
      ))}
      {[[256, 1150], [400, 1140], [560, 1150], [700, 1146], [800, 1160]].map(([x, y]) => (
        <path key={x} d={rect(x, y, 20, 28)} fill="#9EA8A8" stroke={lower} strokeWidth={1.5} />
      ))}
      {/* two shops, left and right */}
      <Shop x={0} w={250} plaster="#C9A57F" front="#4F6650" awning={[SEAL, CREAM]} doorLeft={false} seed={61}
        wares={<g>
          <Sh d={`M40 1196h70l-8 -40h-54z`} fill="#3B3A40" pen="none" sw={2} />
          <Sh d={rect(30, 1194, 90, 8)} fill="#3B3A40" pen="none" sw={2} />
          <Sh d={rounded(40, 1250, 30, 46, 6)} fill={GOLD} pen="d" penOp={0.12} sw={2} />
          <Sh d={rounded(86, 1240, 30, 56, 6)} fill={SAGE} pen="d" penOp={0.12} sw={2} />
        </g>} />
      <Shop x={830} w={250} plaster="#BDA98C" front="#34476A" awning={[GOLD, CREAM]} doorLeft={true} seed={67}
        wares={<g>
          <Sh d={circle(964, 1156, 26)} fill={CREAM} pen="d" penOp={0.08} sw={2.5} />
          <path d={`M964 1156v-16M964 1156h12`} stroke={INK} strokeWidth={2.5} strokeLinecap="round" />
          <Sh d={rect(944, 1182, 40, 14)} fill={WOOD} pen="none" sw={2} />
          <Sh d={ellipse(940, 1280, 30, 16)} fill="#B5824A" pen="d" penOp={0.14} sw={2} />
          <Sh d={ellipse(1000, 1282, 26, 14)} fill="#B5824A" pen="d" penOp={0.14} sw={2} />
        </g>} />
      <GasLamp x={226} />
      <GasLamp x={854} />
      {/* a flagstone pavement, a kerb, then the cobbled road */}
      <rect x={0} y={F} width={W} height={70} fill="#CBBFA8" />
      {Array.from({ length: 9 }, (_, i) => (
        <line key={i} x1={60 + i * 124} x2={60 + i * 124} y1={F} y2={F + 70} stroke={INK} strokeWidth={1.5} opacity={0.3} />
      ))}
      <Sh d={rect(-4, F + 70, W + 8, 16)} fill="#9C9282" pen="none" sw={2.5} />
      <rect x={0} y={F + 86} width={W} height={H - F - 86} fill="#948A79" />
      {(() => {
        const out: React.ReactNode[] = [];
        let y = F + 92;
        for (let row = 0; y < H; row++) {
          const h = 38 + row * 5;
          const w = h * 1.5;
          let x = -((row * 37) % w);
          while (x < W) {
            const ww = w * (0.75 + r() * 0.5), dy = (r() - 0.5) * 6;
            out.push(<Sh key={`${row}-${x}`} d={ellipse(x + ww / 2, y + h / 2 + dy, ww / 2 - 4, h / 2 - 4)} fill="#B4A994" pen="none" sw={1.6} stroke="#5E5446" />);
            x += ww;
          }
          y += h;
        }
        return out;
      })()}
      <rect x={0} y={F + 86} width={W} height={H - F - 86} fill={`url(#${HATCH})`} opacity={0.1} />
      <rect x={0} y={F} width={W} height={70} fill={`url(#${HATCH})`} opacity={0.1} />
      <line x1={0} x2={W} y1={F} y2={F} stroke={INK} strokeWidth={4} />
    </g>
  );
};

// ── countryside ──────────────────────────────────────────────────────────────

/** A scalloped hedge top from x 0 to W, its base at y, `h` tall. */
function hedge(y: number, h: number, step: number) {
  let d = `M0 ${y}V${y - h}`;
  for (let x = 0; x < W; x += step) d += `A${step / 2} ${step / 2.4} 0 0 1 ${Math.min(W, x + step)} ${y - h}`;
  return `${d}V${y}Z`;
}

const Countryside: React.FC = () => {
  const r = rng(71);
  return (
    <g>
      <Wall color="#D6DFDA" op={0.05} />
      <Sh d={circle(900, 540, 46)} fill="#EFD99C" pen="none" sw={2.5} />
      <Sh d={cloud(380, 520, 200, 64)} fill={CREAM} pen="d" penOp={0.06} sw={2.5} />
      <Sh d={cloud(930, 740, 190, 58)} fill={CREAM} pen="d" penOp={0.06} sw={2.5} />
      {/* far hills, then nearer fields cut by a hedgerow */}
      <Sh d={`M0 1060Q180 960 380 1040T760 1010T1080 990V${F}H0Z`} fill="#BBC5B1" pen="d" penOp={0.06} sw={2} stroke="#7F8A75" />
      {/* a windmill on the far hill, right */}
      <Sh d={poly([[912, 1004], [952, 1004], [946, 916], [918, 916]])} fill={CREAM} pen="d" penOp={0.08} sw={2.5} />
      <Sh d={poly([[912, 918], [932, 896], [952, 918]])} fill={WOOD} pen="none" sw={2.5} />
      {[20, 110, 200, 290].map((a) => (
        <g key={a} transform={`rotate(${a} 932 904)`}>
          <Sh d={rect(926, 834, 12, 70)} fill="#E6DCC4" pen="none" sw={2} />
          <line x1={932} x2={932} y1={834} y2={904} stroke={INK} strokeWidth={1.5} opacity={0.6} />
        </g>
      ))}
      <path d={circle(932, 904, 5)} fill={WOOD_DARK} stroke={INK} strokeWidth={2} />
      <Sh d={`M0 1150Q260 1090 540 1140T1080 1116V${F}H0Z`} fill="#AAB68F" pen="d" penOp={0.08} sw={2.5} />
      <Sh d={`M560 1142Q760 1110 1080 1122V1236Q820 1226 600 1250Z`} fill="#CDB97E" pen="d" penOp={0.1} sw={2} />
      <Sh d={`M0 1180Q200 1150 400 1176Q446 1198 384 1222Q200 1250 0 1262Z`} fill="#9BAA7E" pen="d" penOp={0.1} sw={2} />
      <Sh d={hedge(1268, 18, 26)} fill="#6F8360" pen="d" penOp={0.12} sw={2} />
      {/* an oak, left */}
      <Sh d={poly([[88, F - 20], [140, F - 20], [128, 840], [102, 840]])} fill={WOOD_DARK} pen="l" penOp={0.14} />
      <path d={`M116 900l-36 -50M122 880l34 -44`} stroke={INK} strokeWidth={9} strokeLinecap="round" />
      <path d={`M116 900l-36 -50M122 880l34 -44`} stroke={WOOD_DARK} strokeWidth={5} strokeLinecap="round" />
      <Sh d={bumps(120, 710, 150, 150, 11)} fill="#6F8360" pen="d" penOp={0.15} />
      <path d={`M60 700a40 40 0 0 1 50 -30M150 760a40 40 0 0 1 50 -20M100 620a36 36 0 0 1 44 -10`} fill="none" stroke={INK} strokeWidth={2} opacity={0.4} />
      {/* the hedge along the lane, at the floor line */}
      <Sh d={hedge(F, 46, 40)} fill="#5F7048" pen="l" penOp={0.12} sw={2.5} />
      {/* a fence, right foreground */}
      {[880, 960, 1040].map((x) => <Sh key={x} d={rect(x, F - 110, 14, 110)} fill={WOOD} pen="none" sw={2.5} />)}
      {[F - 92, F - 52].map((y) => <Sh key={y} d={rect(860, y, 230, 12)} fill={WOOD} pen="none" sw={2.5} />)}
      {/* two birds */}
      <path d={`M300 640q12 -12 22 0q10 -12 22 0M700 590q10 -10 18 0q8 -10 18 0`} fill="none" stroke={INK} strokeWidth={2.5} opacity={0.6} />
      {/* the meadow */}
      <Ground color="#A9B58A" op={0.1} />
      {Array.from({ length: 16 }, (_, i) => {
        const x = 30 + r() * 1020, y = F + 40 + r() * 480;
        return <path key={i} d={`M${x} ${y} l-6 -18 M${x} ${y} l2 -22 M${x} ${y} l9 -16`} stroke="#5F7048" strokeWidth={2.5} opacity={0.5} />;
      })}
      {Array.from({ length: 8 }, (_, i) => {
        const x = 40 + r() * 1000, y = F + 60 + r() * 500;
        return <circle key={i} cx={x} cy={y} r={4} fill={i % 2 ? CREAM : "#C98F5A"} opacity={0.8} />;
      })}
    </g>
  );
};

// ── harbour ──────────────────────────────────────────────────────────────────

const Harbour: React.FC = () => {
  const r = rng(83);
  const sea = 1130;
  return (
    <g>
      <Wall color="#D5DCDA" to={sea} op={0.05} />
      {/* a headland with a lighthouse, far left */}
      <Sh d={`M0 ${sea}V1086Q110 1052 210 1088Q262 1108 330 ${sea}Z`} fill="#A9AF9B" pen="d" penOp={0.08} sw={2} stroke="#6F7768" />
      <Sh d={poly([[100, 1076], [140, 1076], [134, 900], [106, 900]])} fill={CREAM} pen="d" penOp={0.08} sw={2.5} />
      <Sh d={poly([[102, 1030], [138, 1030], [137, 1004], [103, 1004]])} fill={SEAL} pen="none" sw={0} />
      <Sh d={poly([[104, 966], [136, 966], [135, 942], [105, 942]])} fill={SEAL} pen="none" sw={0} />
      <path d={poly([[100, 1076], [140, 1076], [134, 900], [106, 900]])} fill="none" stroke={INK} strokeWidth={2.5} />
      <Sh d={rect(98, 890, 44, 10)} fill="#3B3A40" pen="none" sw={2} />
      <Sh d={rect(108, 862, 24, 28)} fill={STARGOLD} pen="none" sw={2} />
      <Sh d={poly([[102, 864], [120, 844], [138, 864]])} fill={SEAL} pen="none" sw={2} />
      {/* the water */}
      <Sh d={rect(0, sea, W, F - sea)} fill="#6F8C97" pen="l" penOp={0.1} sw={0} />
      <line x1={0} x2={W} y1={sea} y2={sea} stroke={INK} strokeWidth={2.5} opacity={0.7} />
      {Array.from({ length: 16 }, (_, i) => {
        const x = 20 + r() * 1000, y = sea + 24 + r() * (F - sea - 40);
        return <path key={i} d={`M${x} ${y}q12 -9 24 0q12 -9 24 0`} fill="none" stroke={IVORY} strokeWidth={2.5} opacity={0.45} />;
      })}
      {/* a ship moored at the quay, right: hull, two masts with furled sails, rigging */}
      <g>
        <path d={`M770 1196L870 470M870 470L1010 430M1010 430L1084 1180M870 470L930 1196M1010 430L960 1196M870 470L800 1196`} fill="none" stroke={INK} strokeWidth={1.8} opacity={0.5} />
        {([[870, 470, [600, 760, 920], 70], [1010, 430, [560, 720, 880], 76]] as const).map(([x, top, yards, half]) => (
          <g key={x}>
            <Sh d={rect(x - 6, top, 12, 1196 - top)} fill={WOOD} pen="l" penOp={0.14} sw={2.5} />
            {yards.map((y, k) => {
              const hw = half + [-14, 0, 10][k];
              return (
                <g key={y}>
                  <Sh d={rect(x - hw, y, hw * 2, 8)} fill={WOOD_DARK} pen="none" sw={2} />
                  <Sh d={rounded(x - hw + 8, y + 8, hw * 2 - 16, 18, 9)} fill={CREAM} pen="d" penOp={0.1} sw={2} />
                </g>
              );
            })}
          </g>
        ))}
        <Sh d={poly([[1016, 432], [1064, 446], [1016, 460]])} fill={SEAL} pen="none" sw={2} />
        <Sh d={`M752 1190H1090V1296H800Q770 1250 752 1190Z`} fill="#4A3A30" pen="l" penOp={0.14} />
        <Sh d={`M757 1206H1090V1222H762Z`} fill={GOLD} pen="none" sw={2} />
        {[850, 930, 1010].map((x) => <path key={x} d={circle(x, 1256, 9)} fill={CREAM} stroke={INK} strokeWidth={2} />)}
      </g>
      {/* the quay: coping stones along the edge, then courses of stone */}
      <rect x={0} y={F} width={W} height={H - F} fill="#B8AD9A" />
      <rect x={0} y={F} width={W} height={H - F} fill={`url(#${HATCH})`} opacity={0.13} />
      <Sh d={rect(-4, F, W + 8, 40)} fill="#A39885" pen="d" penOp={0.08} sw={3} />
      {Array.from({ length: 8 }, (_, i) => <line key={i} x1={60 + i * 135} x2={60 + i * 135} y1={F} y2={F + 40} stroke={INK} strokeWidth={1.8} opacity={0.5} />)}
      {[F + 150, F + 290, F + 460].map((y, i) => (
        <g key={y}>
          <line x1={0} x2={W} y1={y} y2={y} stroke={INK} strokeWidth={1.5} opacity={0.3} />
          {Array.from({ length: 4 }, (_, k) => {
            const x = (k * 290 + (i % 2) * 145 + 70) % W;
            return <line key={k} x1={x} x2={x} y1={[F + 40, F + 150, F + 290][i]} y2={y} stroke={INK} strokeWidth={1.5} opacity={0.3} />;
          })}
        </g>
      ))}
      {/* a bollard */}
      <Sh d={rounded(940, F - 70, 44, 70, 8)} fill="#3B3A40" pen="l" penOp={0.12} />
      <Sh d={rounded(930, F - 84, 64, 20, 9)} fill="#3B3A40" pen="none" sw={3} />
      {/* gulls */}
      <path d={`M300 560q12 -12 22 0q10 -12 22 0M380 610q10 -10 18 0q8 -10 18 0M640 520q10 -10 18 0q8 -10 18 0`} fill="none" stroke={INK} strokeWidth={2.5} opacity={0.6} />
    </g>
  );
};

// ── blueprint ────────────────────────────────────────────────────────────────

const PALE = IVORY;

/** A gear outline: `n` teeth between radii r1 (root) and r2 (tip). */
function gear(cx: number, cy: number, r1: number, r2: number, n: number) {
  const pts: [number, number][] = [];
  for (let i = 0; i < n; i++) {
    const a = (i / n) * Math.PI * 2, s = (Math.PI * 2) / n;
    for (const [da, rr] of [[0, r1], [s * 0.15, r2], [s * 0.45, r2], [s * 0.6, r1]] as const) {
      pts.push([cx + rr * Math.cos(a + da), cy + rr * Math.sin(a + da)]);
    }
  }
  return poly(pts);
}

/** A small arrowhead at (x, y) pointing along angle a (radians). */
const arrow = (x: number, y: number, a: number) =>
  poly([[x, y], [x - 16 * Math.cos(a) + 6 * Math.sin(a), y - 16 * Math.sin(a) - 6 * Math.cos(a)], [x - 16 * Math.cos(a) - 6 * Math.sin(a), y - 16 * Math.sin(a) + 6 * Math.cos(a)]]);

const Blueprint: React.FC = () => {
  const line = { fill: "none", stroke: PALE, strokeWidth: 2.6, strokeLinejoin: "round" as const };
  const centre = { stroke: PALE, strokeWidth: 1.6, strokeDasharray: "26 7 4 7", opacity: 0.7 };
  return (
    <g>
      <rect width={W} height={H} fill={BLUEPRINT} />
      <defs>
        <radialGradient id="bp-pool" cx="50%" cy="50%" r="50%">
          <stop offset="0%" stopColor="#6A87A6" stopOpacity={0.9} />
          <stop offset="70%" stopColor="#557392" stopOpacity={0.45} />
          <stop offset="100%" stopColor={BLUEPRINT} stopOpacity={0} />
        </radialGradient>
      </defs>
      <ellipse cx={540} cy={1010} rx={480} ry={450} fill="url(#bp-pool)" />
      {/* the drafting grid */}
      {Array.from({ length: 21 }, (_, i) => (
        <line key={`v${i}`} x1={i * 54} x2={i * 54} y1={0} y2={F} stroke={PALE} strokeWidth={i % 4 === 0 ? 1.6 : 1} opacity={i % 4 === 0 ? 0.2 : 0.1} />
      ))}
      {Array.from({ length: 25 }, (_, j) => (
        <line key={`h${j}`} x1={0} x2={W} y1={j * 54 + 48} y2={j * 54 + 48} stroke={PALE} strokeWidth={j % 4 === 0 ? 1.6 : 1} opacity={j % 4 === 0 ? 0.2 : 0.1} />
      ))}
      <rect x={46} y={46} width={W - 92} height={H - 92} fill="none" stroke={PALE} strokeWidth={2} opacity={0.45} />
      <g opacity={0.85}>
        {/* a gear, upper left */}
        <path d={gear(150, 610, 80, 96, 14)} {...line} />
        <path d={circle(150, 610, 26)} {...line} />
        <path d={circle(150, 610, 52)} {...line} strokeDasharray="10 8" />
        <path d={`M30 610H270M150 490V730`} {...centre} />
        <Scribble x={92} y={758} w={110} lines={2} color={PALE} op={0.7} seed={91} />
        {/* a flywheel, upper right */}
        <path d={circle(930, 630, 100)} {...line} />
        <path d={circle(930, 630, 84)} {...line} />
        <path d={circle(930, 630, 18)} {...line} />
        {Array.from({ length: 6 }, (_, i) => {
          const a = (i / 6) * Math.PI * 2 + 0.3;
          return <line key={i} x1={930 + 18 * Math.cos(a)} y1={630 + 18 * Math.sin(a)} x2={930 + 84 * Math.cos(a)} y2={630 + 84 * Math.sin(a)} stroke={PALE} strokeWidth={2.6} />;
        })}
        <path d={`M810 630H1050M930 510V750`} {...centre} />
        <path d={`M830 780H1030`} stroke={PALE} strokeWidth={1.6} />
        <path d={`${arrow(830, 780, Math.PI)}${arrow(1030, 780, 0)}`} fill={PALE} />
        <Scribble x={892} y={806} w={80} lines={1} color={PALE} op={0.7} seed={93} />
        {/* a cylinder and piston in section, lower left */}
        <path d={rect(70, 960, 150, 250)} {...line} />
        <rect x={70} y={960} width={22} height={250} fill={`url(#${HATCH_LIGHT})`} opacity={0.6} />
        <rect x={198} y={960} width={22} height={250} fill={`url(#${HATCH_LIGHT})`} opacity={0.6} />
        <path d={`M92 960V1210M198 960V1210`} {...line} />
        <path d={rect(96, 1030, 98, 64)} {...line} />
        <path d={`M145 1094L120 1254`} {...line} />
        <path d={circle(145, 1270, 30)} {...line} />
        <path d={`M145 930V1310`} {...centre} />
        <path d={`M48 960V1210`} stroke={PALE} strokeWidth={1.6} />
        <path d={`${arrow(48, 960, -Math.PI / 2)}${arrow(48, 1210, Math.PI / 2)}`} fill={PALE} />
        {/* a bolt and nut, lower right */}
        <path d={`${rect(900, 990, 92, 46)}M900 1013H992M930 990V1036M962 990V1036`} {...line} />
        <path d={rect(924, 1036, 44, 210)} {...line} />
        {Array.from({ length: 9 }, (_, i) => <line key={i} x1={924} x2={968} y1={1130 + i * 13} y2={1122 + i * 13} stroke={PALE} strokeWidth={1.8} />)}
        <path d={`M946 960V1290`} {...centre} />
        <path d={`M1010 990V1246`} stroke={PALE} strokeWidth={1.6} />
        <path d={`${arrow(1010, 990, -Math.PI / 2)}${arrow(1010, 1246, Math.PI / 2)}`} fill={PALE} />
      </g>
      {/* the ground line, with the drafter's hatch under it, and a title block in the corner */}
      <rect x={0} y={F} width={W} height={H - F} fill="#2F4A68" />
      <rect x={0} y={F} width={W} height={H - F} fill={`url(#${HATCH_LIGHT})`} opacity={0.05} />
      <line x1={0} x2={W} y1={F} y2={F} stroke={PALE} strokeWidth={3.5} opacity={0.85} />
      {Array.from({ length: 36 }, (_, i) => (
        <line key={i} x1={14 + i * 30} x2={i * 30 - 4} y1={F + 2} y2={F + 22} stroke={PALE} strokeWidth={1.8} opacity={0.55} />
      ))}
      <g opacity={0.75}>
        <path d={`${rect(680, 1700, 340, 150)}M680 1750H1020M680 1800H1020M820 1700V1850`} fill="none" stroke={PALE} strokeWidth={2.2} />
        <Scribble x={700} y={1726} w={100} lines={1} color={PALE} op={0.8} seed={95} />
        <Scribble x={840} y={1726} w={160} lines={1} color={PALE} op={0.8} seed={96} />
        <Scribble x={700} y={1776} w={100} lines={1} color={PALE} op={0.8} seed={97} />
        <Scribble x={840} y={1776} w={160} lines={1} color={PALE} op={0.8} seed={98} />
        <Scribble x={700} y={1826} w={100} lines={1} color={PALE} op={0.8} seed={99} />
      </g>
    </g>
  );
};

// ── factory ──────────────────────────────────────────────────────────────────

/** A spoked wheel (a pulley or a flywheel). */
const Wheel: React.FC<{ cx: number; cy: number; r: number; spokes?: number }> = ({ cx, cy, r, spokes = 6 }) => (
  <g>
    <Sh d={`${circle(cx, cy, r)}${circle(cx, cy, r * 0.8)}`} fill="#6E7378" pen="l" penOp={0.12} sw={3} />
    {Array.from({ length: spokes }, (_, i) => {
      const a = (i / spokes) * Math.PI * 2;
      return <line key={i} x1={cx} y1={cy} x2={cx + r * 0.8 * Math.cos(a)} y2={cy + r * 0.8 * Math.sin(a)} stroke={INK} strokeWidth={5} strokeLinecap="round" />;
    })}
    <path d={circle(cx, cy, r * 0.16)} fill="#3B3A40" stroke={INK} strokeWidth={2.5} />
  </g>
);

/** A drive belt between two wheels, outer tangents approximated by their left and right edges. */
const Belt: React.FC<{ x1: number; y1: number; r1: number; x2: number; y2: number; r2: number }> = ({ x1, y1, r1, x2, y2, r2 }) => {
  const d = `M${x1 - r1} ${y1}L${x2 - r2} ${y2}M${x1 + r1} ${y1}L${x2 + r2} ${y2}`;
  return (
    <g>
      <path d={d} stroke={INK} strokeWidth={10} />
      <path d={d} stroke="#6B4A33" strokeWidth={6} />
    </g>
  );
};

const Factory: React.FC = () => {
  const iron = "#4A505A";
  return (
    <g>
      <Wall color="#D6C9AF" op={0.07} />
      {/* clerestory windows high up, tall windows at the sides */}
      {[90, 300, 510, 720, 930].map((x) => <ArchWindow key={x} x={x - 2} y={66} w={64} h={120} glass="#CBD6D4" rows={2} />)}
      <ArchWindow x={58} y={500} w={150} h={400} glass="#CBD6D4" rows={4} />
      <ArchWindow x={872} y={500} w={150} h={400} glass="#CBD6D4" rows={4} />
      {/* a painted lower wall */}
      <Sh d={rect(-4, 1110, W + 8, F - 1110)} fill="#A99677" pen="d" penOp={0.1} sw={2.5} />
      {/* the line shaft across the hall, carried on the columns */}
      <path d={`M0 446H${W}`} stroke={INK} strokeWidth={15} />
      <path d={`M0 446H${W}`} stroke="#8D9298" strokeWidth={9} />
      {/* belts down to the machines at either side */}
      <Belt x1={140} y1={446} r1={38} x2={130} y2={1060} r2={34} />
      <Belt x1={950} y1={446} r1={38} x2={955} y2={1040} r2={62} />
      <Wheel cx={140} cy={446} r={38} />
      <Wheel cx={950} cy={446} r={38} />
      {/* cast-iron columns framing the stage */}
      {[218, 832].map((x) => (
        <g key={x}>
          <Sh d={rect(x, 0, 30, F)} fill={iron} pen="l" penOp={0.15} />
          <Sh d={poly([[x - 26, 420], [x + 56, 420], [x + 36, 470], [x - 6, 470]])} fill={iron} pen="l" penOp={0.15} />
          <Sh d={rect(x - 10, F - 34, 50, 34)} fill={iron} pen="l" penOp={0.15} />
        </g>
      ))}
      {/* a lathe, left */}
      <Sh d={rect(40, 1180, 190, F - 1180)} fill="#4F6650" pen="l" penOp={0.14} />
      <path d={rect(58, 1200, 154, 120)} fill="none" stroke={INK} strokeWidth={2} opacity={0.45} />
      <Sh d={rect(28, 1150, 216, 30)} fill="#6E7378" pen="l" penOp={0.12} />
      <Sh d={rect(86, 1094, 80, 56)} fill="#4F6650" pen="l" penOp={0.14} />
      <Sh d={rect(196, 1112, 36, 38)} fill="#4F6650" pen="l" penOp={0.14} />
      <line x1={166} x2={196} y1={1126} y2={1126} stroke={INK} strokeWidth={5} />
      <Wheel cx={130} cy={1060} r={34} spokes={5} />
      {/* a steam press, right */}
      <Sh d={rect(870, 1110, 176, F - 1110)} fill="#4F6650" pen="l" penOp={0.14} />
      <path d={`${rect(886, 1170, 64, 150)}${rect(964, 1170, 64, 150)}`} fill="none" stroke={INK} strokeWidth={2} opacity={0.45} />
      <Sh d={rect(860, 1096, 196, 18)} fill="#6E7378" pen="none" sw={2.5} />
      <Wheel cx={955} cy={1040} r={62} />
      {/* floorboards */}
      <PlankFloor color="#B1A084" seed={5} />
    </g>
  );
};

// ── map room ─────────────────────────────────────────────────────────────────

const MapRoom: React.FC = () => {
  const parchment = "#E7DCBC";
  const land = "#C4C59B";
  return (
    <g>
      <Wall color="#D3CFB3" op={0.07} />
      {/* panelled wainscot */}
      <Sh d={rect(-4, 1150, W + 8, F - 1150)} fill={WOOD} pen="l" penOp={0.14} sw={2.5} />
      {Array.from({ length: 11 }, (_, i) => (
        <line key={i} x1={50 + i * 98} x2={50 + i * 98} y1={1166} y2={F} stroke={INK} strokeWidth={1.8} opacity={0.35} />
      ))}
      <Sh d={rect(-4, 1138, W + 8, 16)} fill={WOOD_DARK} pen="none" sw={2.5} />
      {/* a big wall map on rollers, hung from a nail */}
      <path d={`M190 444L540 424L890 444`} fill="none" stroke={INK} strokeWidth={2.5} opacity={0.7} />
      <path d={circle(540, 422, 5)} fill={GOLD} stroke={INK} strokeWidth={2} />
      <Sh d={rect(150, 452, 780, 358)} fill={parchment} pen="d" penOp={0.05} sw={2.5} />
      <g>
        {Array.from({ length: 12 }, (_, i) => {
          // rhumb lines from the compass rose, run to the edge of the sheet
          const a = (i / 12) * Math.PI * 2 + 0.01, dx = Math.cos(a), dy = Math.sin(a);
          const t = Math.min(dx > 0 ? (926 - 810) / dx : (154 - 810) / dx, dy > 0 ? (806 - 730) / dy : (456 - 730) / dy);
          return <line key={i} x1={810} y1={730} x2={810 + t * dx} y2={730 + t * dy} stroke={INK} strokeWidth={1.2} opacity={0.2} />;
        })}
        <Sh d={blob(300, 640, 130, 120, 12, 5, 0.45)} fill={land} pen="d" penOp={0.08} sw={2.2} />
        <Sh d={blob(700, 560, 170, 90, 12, 9, 0.45)} fill={land} pen="d" penOp={0.08} sw={2.2} />
        <Sh d={blob(520, 740, 40, 24, 8, 13, 0.4)} fill={land} pen="d" penOp={0.08} sw={2.2} />
      </g>
      <path d={`M380 690Q480 640 560 690T760 640`} fill="none" stroke={SEAL} strokeWidth={3} strokeDasharray="9 9" opacity={0.8} />
      <Sh d={`${poly(Array.from({ length: 16 }, (_, i) => {
        const a = (i / 16) * Math.PI * 2 - Math.PI / 2, rr = i % 4 === 0 ? 40 : i % 2 === 0 ? 24 : 9;
        return [810 + rr * Math.cos(a), 730 + rr * Math.sin(a)] as [number, number];
      }))}`} fill={SEAL} pen="none" sw={2} />
      <path d={circle(810, 730, 16)} fill="none" stroke={INK} strokeWidth={1.8} />
      <Sh d={rect(172, 474, 130, 58)} fill={CREAM} pen="none" sw={2} />
      <Scribble x={186} y={494} w={100} lines={2} gap={18} seed={103} />
      <path d={rect(162, 464, 756, 334)} fill="none" stroke={INK} strokeWidth={1.4} opacity={0.5} />
      {[442, 812].map((y) => (
        <g key={y}>
          <Sh d={rounded(132, y - 10, 816, 20, 10)} fill={WOOD_DARK} pen="l" penOp={0.14} sw={2.5} />
          <path d={`${circle(128, y, 13)}${circle(952, y, 13)}`} fill={GOLD} stroke={INK} strokeWidth={2.5} />
        </g>
      ))}
      {/* a plan chest of wide shallow drawers, rolled charts on top, left */}
      <Sh d={rect(34, 1070, 230, F - 1070)} fill={WOOD_DARK} pen="l" penOp={0.14} />
      {Array.from({ length: 5 }, (_, i) => (
        <g key={i}>
          <Sh d={rect(48, 1086 + i * 50, 202, 42)} fill={WOOD} pen="l" penOp={0.12} sw={2} />
          <Sh d={rounded(131, 1102 + i * 50, 36, 10, 4)} fill={GOLD} pen="none" sw={1.8} />
        </g>
      ))}
      <Sh d={rounded(48, 1038, 176, 32, 16)} fill={CREAM} pen="d" penOp={0.08} sw={2.5} />
      <path d={ellipse(208, 1054, 8, 16)} fill={PINK} stroke={INK} strokeWidth={2} />
      <Sh d={rounded(70, 1012, 150, 28, 14)} fill="#D9C9A0" pen="d" penOp={0.08} sw={2.5} />
      <path d={ellipse(206, 1026, 7, 14)} fill={PINK} stroke={INK} strokeWidth={2} />
      {/* a globe on its stand, right */}
      <path d={`M950 1200L898 ${F}M950 1200L1002 ${F}`} stroke={INK} strokeWidth={10} strokeLinecap="round" />
      <path d={`M950 1200L898 ${F}M950 1200L1002 ${F}`} stroke={WOOD_DARK} strokeWidth={6} strokeLinecap="round" />
      <Sh d={rect(943, 1176, 14, 32)} fill={WOOD_DARK} pen="none" sw={2.5} />
      <Sh d={circle(950, 1090, 86)} fill="#8FA6A8" pen="d" penOp={0.12} sw={0} />
      <Sh d={blob(935, 1075, 32, 36, 9, 21, 0.3)} fill="#CDBA88" pen="d" penOp={0.1} sw={2} />
      <Sh d={blob(985, 1122, 24, 18, 8, 23, 0.3)} fill="#CDBA88" pen="d" penOp={0.1} sw={2} />
      <path d={circle(950, 1090, 86)} fill="none" stroke={INK} strokeWidth={3} />
      <path d={`M950 992A98 98 0 0 1 950 1188`} fill="none" stroke={INK} strokeWidth={11} />
      <path d={`M950 992A98 98 0 0 1 950 1188`} fill="none" stroke={GOLD} strokeWidth={6} />
      <Sh d={`${ellipse(950, 1112, 112, 18)}${ellipse(950, 1112, 100, 12)}`} fill={GOLD} pen="none" sw={2.5} />
      <PlankFloor color="#CDB892" seed={17} />
    </g>
  );
};

const BODIES: Record<Backdrop, React.FC> = {
  study: Study, workshop: Workshop, nightsky: NightSky, laboratory: Laboratory, street: Street, countryside: Countryside,
  harbour: Harbour, blueprint: Blueprint, factory: Factory, maproom: MapRoom,
};

/** The backdrop as a cached full-frame drawing, at `density` pixels per px (above 1 when the camera pushes in). */
export function backdropDrawing(b: Backdrop, density = 1): Drawing {
  const Body = BODIES[b];
  return {
    key: `backdrop:${b}:${density}`, width: W, height: H, density,
    render: () => (
      <g>
        <Body />
        <FrameInk />
      </g>
    ),
  };
}

/** The paper texture on its own (blank pages, the white of a door push settles onto this). */
export function paperDrawing(): Drawing {
  return {
    key: "paper",
    width: W,
    height: H,
    render: () => (
      <g>
        <rect width={W} height={H} fill={IVORY} />
        <rect width={W} height={H} fill={`url(#${HATCH})`} opacity={0.07} />
        <rect width={W} height={H} fill={`url(#${LINES})`} opacity={0.03} />
        <FrameInk />
      </g>
    ),
  };
}
