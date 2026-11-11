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
import { HATCH, HATCH_LIGHT, LINES, Sh, circle, poly, rect, rounded } from "./ink";
import {
  BANDS, BEIGE, BLUEPRINT, CREAM, GOLD, H, INK, IVORY, NAVY, PINK, SAGE, SAND, SEAL, SLATE, STARGOLD, W, WOOD, WOOD_DARK,
} from "./palette";

export const BACKDROPS = ["study", "workshop", "nightsky"] as const;
export type Backdrop = (typeof BACKDROPS)[number];

/** Whether a backdrop is dark (the label and tags keep their ivory plate either way). */
export const DARK_BACKDROPS: ReadonlySet<Backdrop> = new Set(["nightsky"]);

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

const BODIES: Record<Backdrop, React.FC> = { study: Study, workshop: Workshop, nightsky: NightSky };

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
