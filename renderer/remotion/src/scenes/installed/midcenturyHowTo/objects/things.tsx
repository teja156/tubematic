/*
 * Devices, paper, time and housekeeping: router, lock, key, shield, usb,
 * battery, envelope, document, checklist, card, sign, calendar, clock, bulb,
 * gear, magnifier, bell, cloud, trash, table. Each is centred on (0, 0) inside
 * its OBJECTS box (../contract.ts); an act plays over at most 20 frames and
 * then holds its last picture.
 */
import React from "react";
import {
  ALFA, Asterisk, BLUE, CORAL, CORAL_DK, CREAM, Cel, GREY, HAIR, INK, JOST, MUSTARD, NAVY, OLIVE, PAPER, Sparkle, TEAL,
  actProgress, cubic, ellP, fitFont, mix, polyP, rectP, tubeP, type ObjectDrawProps, type Pt,
} from "../cel";

const clamp01 = (v: number) => Math.max(0, Math.min(1, v));
const eOut = (t: number) => 1 - (1 - t) ** 3;
const eIn = (t: number) => t * t;
const eInOut = (t: number) => (t < 0.5 ? 4 * t * t * t : 1 - (-2 * t + 2) ** 3 / 2);
const RAD = Math.PI / 180;

/** An arc's path from angle a0 to a1 (degrees, clockwise on screen). */
const arcD = (cx: number, cy: number, r: number, a0: number, a1: number) =>
  `M${(cx + r * Math.cos(a0 * RAD)).toFixed(1)} ${(cy + r * Math.sin(a0 * RAD)).toFixed(1)} A${r} ${r} 0 ${a1 - a0 > 180 ? 1 : 0} 1 ${(cx + r * Math.cos(a1 * RAD)).toFixed(1)} ${(cy + r * Math.sin(a1 * RAD)).toFixed(1)}`;

/** A line's path length, for drawing it on with a dash. */
const polyLen = (pts: Pt[]) => pts.slice(1).reduce((s, q, i) => s + Math.hypot(q[0] - pts[i][0], q[1] - pts[i][1]), 0);

/** Words split into at most `n` lines of about equal length. */
function balance(words: string[], n: number): string[] {
  const target = words.join(" ").length / n;
  const out: string[] = [];
  let cur = "";
  for (const w of words) {
    if (cur && out.length < n - 1 && cur.length + 1 + w.length > target) {
      out.push(cur);
      cur = w;
    } else cur = cur ? `${cur} ${w}` : w;
  }
  if (cur) out.push(cur);
  return out;
}

const LH = 1.15;

/** The line split and font size (up to `max`) at which `text` fills a width x height area best. */
function wrapFit(text: string, width: number, height: number, max: number, maxLines: number, slab = false) {
  const words = text.trim().split(/\s+/).filter(Boolean);
  let best = { lines: [] as string[], size: 0 };
  for (let n = 1; n <= Math.min(maxLines, words.length); n++) {
    const lines = balance(words, n);
    const size = Math.min(height / (lines.length * LH), ...lines.map((l) => fitFont(l, width, max, slab)));
    if (size > best.size) best = { lines, size };
  }
  return best;
}

/** Lines of text set as a block centred on `cy`. */
const TextBlock: React.FC<{
  lines: string[]; size: number; x: number; cy: number; family: string; weight?: number; fill: string; anchor?: "start" | "middle";
}> = ({ lines, size, x, cy, family, weight = 400, fill, anchor = "start" }) => {
  const top = cy - (lines.length * size * LH) / 2;
  return (
    <g>
      {lines.map((l, i) => (
        <text key={i} x={x} y={top + size * (i * LH + (LH + 0.7) / 2)} textAnchor={anchor} fontFamily={family} fontWeight={weight} fontSize={size} fill={fill}>
          {l}
        </text>
      ))}
    </g>
  );
};

/** A stroke drawn on along its length as `k` goes 0 to 1, off-register colour under a thin ink line. */
const DrawOn: React.FC<{ d: string; len: number; k: number; color: string; width: number }> = ({ d, len, k, color, width }) =>
  k <= 0 ? null : (
    <g>
      <path d={d} stroke={color} strokeWidth={width} fill="none" strokeLinecap="round" strokeLinejoin="round" strokeDasharray={`${len * k} ${len + 20}`} transform="translate(4 3)" />
      <path d={d} stroke={INK} strokeWidth={4} fill="none" strokeLinecap="round" strokeLinejoin="round" strokeDasharray={`${len * k} ${len + 20}`} />
    </g>
  );

// ---------------------------------------------------------------- devices and security

const ROUTER_LIGHTS = [MUSTARD, TEAL, MUSTARD, CORAL];

export const Router: React.FC<ObjectDrawProps> = (p) => {
  const k = p.act === "blink" ? actProgress(p.actT) : 0;
  return (
    <g>
      <ellipse cx={8} cy={112} rx={180} ry={9} fill={INK} opacity={0.14} />
      <Cel d={tubeP([[-128, -24], [-150, -104]], 16)} fill={GREY} phase={p.phase} seed={300} sw={4} broken={false} />
      <Cel d={tubeP([[128, -24], [150, -104]], 16)} fill={GREY} phase={p.phase} seed={301} sw={4} broken={false} />
      <Cel d={ellP(-150, -110, 13, 13)} fill={CORAL} phase={p.phase} seed={302} sw={3.5} broken={false} />
      <Cel d={ellP(150, -110, 13, 13)} fill={CORAL} phase={p.phase} seed={303} sw={3.5} broken={false} />
      <Cel d={rectP(-150, 84, 44, 18, 6)} fill={INK} phase={p.phase} seed={304} sw={3.5} broken={false} />
      <Cel d={rectP(106, 84, 44, 18, 6)} fill={INK} phase={p.phase} seed={305} sw={3.5} broken={false} />
      <Cel d={rectP(-190, -30, 380, 120, 30)} fill={BLUE} phase={p.phase} seed={306} sw={5} />
      {[-48, -16, 16, 48].map((x) => (
        <rect key={x} x={x - 6} y={-18} width={12} height={18} rx={6} fill={INK} opacity={0.5} />
      ))}
      <Cel d={rectP(-160, 8, 320, 56, 18)} fill={NAVY} phase={p.phase} seed={307} sw={4} broken={false} />
      {[-105, -35, 35, 105].map((x, i) => {
        const on = k >= 0.15 + i * 0.2;
        return (
          <g key={x}>
            {on && <circle cx={x} cy={36} r={22} fill={ROUTER_LIGHTS[i]} opacity={0.3} />}
            <Cel d={ellP(x, 36, 13, 13)} fill={on ? ROUTER_LIGHTS[i] : mix(NAVY, INK, 0.4)} phase={p.phase} seed={308 + i} sw={3.5} broken={false} />
          </g>
        );
      })}
      {[26, 50, 74].map((r, j) =>
        k >= 0.85 + j * 0.05 ? (
          <g key={r}>
            <path d={arcD(0, -40, r, 225, 315)} stroke={CORAL} strokeWidth={10} fill="none" strokeLinecap="round" transform="translate(4 3)" />
            <path d={arcD(0, -40, r, 225, 315)} stroke={INK} strokeWidth={4} fill="none" strokeLinecap="round" />
          </g>
        ) : null,
      )}
      {k >= 0.85 && <circle cx={0} cy={-40} r={7} fill={INK} />}
    </g>
  );
};

const SHACKLE: Pt[] = (() => {
  const pts: Pt[] = [[-44, 30], [-44, -50]];
  for (let i = 1; i < 16; i++) {
    const a = Math.PI + (i / 16) * Math.PI;
    pts.push([44 * Math.cos(a), -50 + 44 * Math.sin(a)]);
  }
  pts.push([44, -50], [44, 30]);
  return pts;
})();

export const Lock: React.FC<ObjectDrawProps> = (p) => {
  const k = p.act === "unlock" ? actProgress(p.actT) : 0;
  const lift = 20 * eOut(clamp01(k / 0.4));
  const swing = 20 * eOut(clamp01((k - 0.4) / 0.6));
  return (
    <g>
      <ellipse cx={6} cy={141} rx={100} ry={7} fill={INK} opacity={0.14} />
      <g transform={`translate(0 ${-lift}) rotate(${swing} 44 30)`}>
        <Cel d={tubeP(SHACKLE, 24)} fill={GREY} phase={p.phase} seed={330} sw={4.5} broken={false} />
      </g>
      <Cel d={rectP(-95, 20, 190, 115, 22)} fill={MUSTARD} phase={p.phase} seed={331} sw={5} />
      <rect x={-74} y={36} width={16} height={78} rx={8} fill={CREAM} opacity={0.55} />
      <Cel d={ellP(0, 62, 15, 15)} fill={INK} phase={p.phase} seed={332} sw={0} />
      <Cel d={polyP([[-8, 66], [8, 66], [13, 104], [-13, 104]])} fill={INK} phase={p.phase} seed={333} sw={0} />
    </g>
  );
};

export const Key: React.FC<ObjectDrawProps> = (p) => {
  const k = p.act === "turn" ? eInOut(actProgress(p.actT)) : 0;
  // A quarter turn about the shaft: the key foreshortens towards edge-on.
  const sy = 1 - 0.72 * k;
  const Y = (y: number) => y * sy;
  const teeth: Pt[] = [[56, 12], [136, 12], [136, 40], [122, 40], [116, 30], [104, 46], [92, 30], [80, 42], [68, 30], [56, 30]];
  const arrow: Pt[] = cubic([10, -44], [40, -63], [70, -63], [100, -44], 16);
  return (
    <g>
      <Cel d={polyP(teeth.map(([x, y]) => [x, Y(y)] as Pt))} fill={MUSTARD} phase={p.phase} seed={360} sw={4} broken={false} />
      <Cel d={rectP(-48, Y(-14), 184, 28 * sy, 8)} fill={MUSTARD} phase={p.phase} seed={361} sw={4.5} />
      <Cel d={rectP(-44, Y(-22), 18, 44 * sy, 6)} fill={mix(MUSTARD, INK, 0.3)} phase={p.phase} seed={362} sw={3.5} broken={false} />
      <Cel d={ellP(-92, 0, 54, 54 * sy)} fill={CORAL} phase={p.phase} seed={363} sw={5} />
      <Cel d={ellP(-110, 0, 15, 15 * sy)} fill={mix(CORAL, INK, 0.55)} phase={p.phase} seed={364} sw={3.5} broken={false} />
      <Asterisk x={-72} y={0} r={12} rot={0} color={CREAM} />
      {k > 0 && (
        <g>
          <DrawOn d={polyP(arrow, false)} len={polyLen(arrow)} k={clamp01(k / 0.85)} color={CORAL} width={9} />
          {k >= 0.85 && <Cel d={polyP([[111, -37], [94, -34], [106, -54]])} fill={CORAL} phase={p.phase} seed={365} sw={3.5} broken={false} />}
        </g>
      )}
    </g>
  );
};

const CHECK: Pt[] = [[-46, 6], [-14, 40], [50, -34]];

export const Shield: React.FC<ObjectDrawProps> = (p) => {
  const k = p.act === "glow" ? actProgress(p.actT) : 0;
  const draw = eOut(clamp01(k / 0.6));
  const spark = eOut(clamp01((k - 0.55) / 0.45));
  return (
    <g>
      <Cel d="M0 -124 L101 -87 Q106 41 0 129 Q-106 41 -101 -87 Z" fill={CORAL} phase={p.phase} seed={390} sw={5} />
      <Cel d="M0 -98 L76 -70 Q80 24 0 94 Q-80 24 -76 -70 Z" fill={CREAM} phase={p.phase} seed={391} sw={4} broken={false} />
      <Asterisk x={0} y={-62} r={13} rot={0} color={MUSTARD} />
      {draw > 0 && (
        <g>
          <path d={polyP(CHECK, false)} stroke={TEAL} strokeWidth={22} fill="none" strokeLinecap="round" strokeLinejoin="round" strokeDasharray={`${polyLen(CHECK) * draw} 400`} transform="translate(5 4)" />
          <path d={polyP(CHECK, false)} stroke={INK} strokeWidth={5} fill="none" strokeLinecap="round" strokeLinejoin="round" strokeDasharray={`${polyLen(CHECK) * draw} 400`} />
        </g>
      )}
      {spark > 0 && (
        <g>
          <Sparkle x={86} y={-110} r={18 * spark} color={TEAL} rot={10} />
          <Sparkle x={-90} y={-40} r={13 * spark} color={MUSTARD} />
          <Sparkle x={78} y={64} r={12 * spark} color={TEAL} rot={-12} />
        </g>
      )}
    </g>
  );
};

export const Usb: React.FC<ObjectDrawProps> = (p) => {
  const k = p.act === "plug" ? eInOut(actProgress(p.actT, 16)) : 0;
  const done = p.act === "plug" && p.actT >= 16;
  const px = -30 + 60 * k;
  const bl = px - 80;
  return (
    <g>
      <Cel d={tubeP(cubic([-138, 52], [-118, 52], [bl - 30, 0], [bl, 0], 14), 18)} fill={mix(INK, PAPER, 0.3)} phase={p.phase} seed={420} sw={4} broken={false} />
      <Cel d={rectP(px, -20, 54, 40, 4)} fill={GREY} phase={p.phase} seed={421} sw={3.5} broken={false} />
      <rect x={px + 14} y={-9} width={10} height={8} fill={INK} />
      <rect x={px + 32} y={-9} width={10} height={8} fill={INK} />
      <Cel d={rectP(bl, -34, 80, 68, 16)} fill={NAVY} phase={p.phase} seed={422} sw={4.5} />
      <rect x={bl + 16} y={-18} width={8} height={36} rx={4} fill={CREAM} opacity={0.4} />
      <Cel d={rectP(64, -58, 76, 116, 12)} fill={CREAM} phase={p.phase} seed={423} sw={5} />
      <rect x={60} y={-24} width={10} height={48} rx={3} fill={INK} />
      <Cel d={ellP(104, -32, 8, 8)} fill={done ? TEAL : mix(CREAM, INK, 0.3)} phase={p.phase} seed={424} sw={3} broken={false} />
      {done && <Sparkle x={104} y={-32} r={14} color={TEAL} rot={45} />}
    </g>
  );
};

export const Battery: React.FC<ObjectDrawProps> = (p) => {
  const k = p.act === "fill" ? eOut(actProgress(p.actT)) : 0;
  const level = 0.14 + 0.86 * k;
  return (
    <g>
      <ellipse cx={6} cy={72} rx={140} ry={7} fill={INK} opacity={0.14} />
      <Cel d={rectP(118, -26, 24, 52, 6)} fill={GREY} phase={p.phase} seed={450} sw={3.5} broken={false} />
      <Cel d={rectP(-140, -62, 262, 124, 22)} fill={NAVY} phase={p.phase} seed={451} sw={5} />
      <Cel d={rectP(-124, -46, 230, 92, 12)} fill={CREAM} phase={p.phase} seed={452} sw={3.5} broken={false} />
      <Cel d={rectP(-124, -46, 230 * level, 92, 12)} fill={k > 0 ? TEAL : CORAL} phase={p.phase} seed={453} sw={0} />
      {[-48, 30].map((x) => (
        <rect key={x} x={x} y={-40} width={4} height={80} rx={2} fill={INK} opacity={0.2} />
      ))}
      <Cel d={polyP([[4, -36], [-26, 6], [-4, 6], [-12, 36], [22, -8], [0, -8]])} fill={MUSTARD} phase={p.phase} seed={454} sw={3.5} broken={false} />
    </g>
  );
};

// ---------------------------------------------------------------- paper and mail

export const Envelope: React.FC<ObjectDrawProps> = (p) => {
  const k = p.act === "open" ? actProgress(p.actT) : 0;
  const flapY = 40 - 152 * eInOut(clamp01(k / 0.55));
  const rise = eOut(clamp01((k - 0.5) / 0.5));
  const ly = -20 - 74 * rise;
  const flapUp = flapY < -62;
  const flap = <Cel d={polyP([[-156, -62], [144, -62], [-6, flapY]])} fill={flapUp ? mix(MUSTARD, CREAM, 0.55) : mix(MUSTARD, CREAM, 0.25)} phase={p.phase} seed={480} sw={4} broken={false} />;
  const addr = wrapFit(p.text.slice(0, 20), 210, 44, 34, 2);
  return (
    <g>
      <Cel d={rectP(-160, -64, 308, 168, 14)} fill={mix(MUSTARD, INK, 0.18)} phase={p.phase} seed={481} sw={5} />
      {flapUp && flap}
      {k > 0 && (
        <g>
          <Cel d={rectP(-118, ly, 220, 120, 6)} fill={CREAM} phase={p.phase} seed={482} sw={3.5} broken={false} />
          {[150, 170, 110].map((w, i) => (
            <rect key={i} x={-96} y={ly + 20 + i * 20} width={w} height={7} rx={3.5} fill={INK} opacity={0.3} />
          ))}
        </g>
      )}
      <Cel d="M-160 -58 L-6 38 L148 -58 V90 A14 14 0 0 1 134 104 H-146 A14 14 0 0 1 -160 90 Z" fill={MUSTARD} phase={p.phase} seed={483} sw={4.5} />
      <Cel d={rectP(-118, 48, 226, 50, 8)} fill={CREAM} phase={p.phase} seed={484} sw={3.5} broken={false} />
      {addr.lines.length > 0 && <TextBlock lines={addr.lines} size={addr.size} x={-5} cy={73} family={JOST} weight={600} fill={INK} anchor="middle" />}
      {!flapUp && flap}
      {!flapUp && flapY > -30 && (
        <g>
          <Cel d={ellP(-6, flapY - 18, 15, 15)} fill={CORAL} phase={p.phase} seed={485} sw={3.5} broken={false} />
          <Asterisk x={-6} y={flapY - 18} r={8} rot={0} color={CREAM} />
        </g>
      )}
    </g>
  );
};

/** The rubber-stamp seal: a ring of dots round a check, in coral ink. */
const Seal: React.FC<{ r: number }> = ({ r }) => (
  <g opacity={0.88}>
    <circle cx={0} cy={0} r={r} fill="none" stroke={CORAL} strokeWidth={7} strokeDasharray="60 6 90 5 40 7" />
    <circle cx={0} cy={0} r={r - 14} fill="none" stroke={CORAL} strokeWidth={3} />
    {Array.from({ length: 12 }, (_, i) => (
      <circle key={i} cx={(r - 7) * Math.cos(i * 30 * RAD)} cy={(r - 7) * Math.sin(i * 30 * RAD)} r={2.4} fill={CORAL} />
    ))}
    <path d={`M${-r * 0.4} ${r * 0.02} L${-r * 0.12} ${r * 0.3} L${r * 0.42} ${-r * 0.3}`} stroke={CORAL} strokeWidth={9} fill="none" strokeLinecap="round" strokeLinejoin="round" />
  </g>
);

export const DocumentSheet: React.FC<ObjectDrawProps> = (p) => {
  const t = p.act === "stamp" && p.actT >= 0 ? actProgress(p.actT, 8) : -1;
  const body = wrapFit(p.text.slice(0, 40), 196, 96, 44, 3);
  return (
    <g>
      <Cel d={polyP([[-128, -172], [78, -172], [118, -132], [118, 160], [-128, 160]])} fill={CREAM} phase={p.phase} seed={510} sw={5} />
      <Cel d={polyP([[78, -172], [78, -132], [118, -132]])} fill={mix(CREAM, INK, 0.18)} phase={p.phase} seed={511} sw={3.5} broken={false} />
      {body.lines.length > 0 && <TextBlock lines={body.lines} size={body.size} x={-104} cy={-74} family={JOST} weight={600} fill={INK} />}
      {[196, 170, 190, 120].map((w, i) => (
        <rect key={i} x={-104} y={-6 + i * 26} width={w} height={10} rx={5} fill={mix(CREAM, INK, 0.22)} />
      ))}
      <path d="M-104 132 Q-92 112 -82 130 T-60 128 Q-50 116 -40 132 T-14 126" stroke={NAVY} strokeWidth={4} fill="none" strokeLinecap="round" />
      {t >= 0 && (
        <g transform={`translate(46 104) rotate(-14) scale(${1 + 0.45 * (1 - eOut(t))})`}>
          <Seal r={46} />
        </g>
      )}
    </g>
  );
};

const TICK: Pt[] = [[-104, 0], [-92, 14], [-62, -26]];

export const Checklist: React.FC<ObjectDrawProps> = (p) => {
  const rows = p.text.split("|").map((s) => s.trim()).filter(Boolean).slice(0, 4);
  const n = rows.length || 3;
  const slot = 260 / Math.max(n, 3);
  const m = /^tick([1-4])$/.exec(p.act);
  const upto = m && p.actT >= 0 ? Math.min(Number(m[1]), n) : 0;
  const last = actProgress(p.actT, 12);
  const tickLen = polyLen(TICK);
  // Every row is set at the size of the tightest one, so the list reads as one list.
  const labels = rows.map((r) => wrapFit(r, 158, Math.min(slot - 14, 70), 34, 2));
  const size = Math.min(...labels.map((l) => l.size), 34);
  return (
    <g>
      <Cel d={rectP(-152, -172, 290, 356, 20)} fill={mix(MUSTARD, HAIR, 0.45)} phase={p.phase} seed={540} sw={5} />
      <Cel d={rectP(-130, -140, 246, 308, 8)} fill={CREAM} phase={p.phase} seed={541} sw={4} broken={false} />
      <Cel d={rectP(-52, -196, 104, 48, 14)} fill={GREY} phase={p.phase} seed={542} sw={4} broken={false} />
      <ellipse cx={0} cy={-180} rx={12} ry={7} fill={INK} />
      {Array.from({ length: n }, (_, i) => {
        const cy = -110 + slot * (i + 0.5);
        const label = labels[i];
        const k = i < upto - 1 ? 1 : i === upto - 1 ? last : 0;
        return (
          <g key={i}>
            <Cel d={rectP(-112, cy - 20, 40, 40, 8)} fill={PAPER} phase={p.phase} seed={543 + i} sw={3.5} broken={false} />
            {label ? (
              <TextBlock lines={label.lines} size={size} x={-56} cy={cy} family={JOST} weight={500} fill={INK} />
            ) : (
              <rect x={-56} y={cy - 6} width={[150, 120, 140][i % 3]} height={12} rx={6} fill={mix(CREAM, INK, 0.22)} />
            )}
            {k > 0 && (
              <g transform={`translate(0 ${cy})`}>
                <path d={polyP(TICK, false)} stroke={TEAL} strokeWidth={11} fill="none" strokeLinecap="round" strokeLinejoin="round" strokeDasharray={`${tickLen * k} 200`} transform="translate(4 3)" />
                <path d={polyP(TICK, false)} stroke={INK} strokeWidth={4} fill="none" strokeLinecap="round" strokeLinejoin="round" strokeDasharray={`${tickLen * k} 200`} />
              </g>
            )}
          </g>
        );
      })}
    </g>
  );
};

export const Card: React.FC<ObjectDrawProps> = (p) => {
  const name = wrapFit(p.text.slice(0, 16), 290, 80, 44, 2);
  return (
    <g>
      <Cel d={rectP(-172, -108, 334, 204, 24)} fill={BLUE} phase={p.phase} seed={580} sw={5} />
      <Cel d={rectP(-140, -70, 64, 50, 10)} fill={MUSTARD} phase={p.phase} seed={581} sw={3.5} broken={false} />
      <path d="M-140 -54 H-118 M-98 -54 H-76 M-140 -36 H-118 M-98 -36 H-76 M-108 -70 V-20" stroke={INK} strokeWidth={3} fill="none" opacity={0.6} />
      {[16, 30, 44].map((r) => (
        <path key={r} d={arcD(-62, -45, r, -40, 40)} stroke={CREAM} strokeWidth={5} fill="none" strokeLinecap="round" />
      ))}
      <Asterisk x={122} y={-66} r={18} rot={10} color={CORAL} />
      {name.lines.length > 0 && <TextBlock lines={name.lines} size={name.size} x={-140} cy={46} family={JOST} weight={600} fill={CREAM} />}
    </g>
  );
};

export const Sign: React.FC<ObjectDrawProps> = (p) => {
  const t = p.act === "wobble" ? actProgress(p.actT) : 1;
  const angle = 4 * Math.sin(t * Math.PI * 3) * (1 - t);
  const words = wrapFit(p.text.slice(0, 24), 230, 96, 60, 2, true);
  return (
    <g>
      <circle cx={0} cy={-118} r={8} fill={INK} />
      <g transform={`rotate(${angle} 0 -118)`}>
        <path d="M0 -118 L-118 -50 M0 -118 L108 -50" stroke={INK} strokeWidth={4} fill="none" strokeLinecap="round" />
        <Cel d={rectP(-150, -50, 290, 150, 18)} fill={CORAL} phase={p.phase} seed={610} sw={5} />
        <Cel d={rectP(-134, -34, 258, 118, 10)} fill={CREAM} phase={p.phase} seed={611} sw={3.5} broken={false} />
        {words.lines.length > 0 && <TextBlock lines={words.lines} size={words.size} x={-5} cy={25} family={ALFA} fill={INK} anchor="middle" />}
      </g>
      <circle cx={0} cy={-118} r={4} fill={GREY} />
    </g>
  );
};

export const Calendar: React.FC<ObjectDrawProps> = (p) => {
  const k = p.act === "flip" ? eInOut(actProgress(p.actT, 14)) : 0;
  const s = 1 - k;
  const Y = (y: number) => -66 + (y + 66) * s;
  const day = wrapFit(p.text.slice(0, 6), 200, 140, 120, 1, true);
  return (
    <g>
      <Cel d={rectP(-128, -124, 246, 262, 20)} fill={CREAM} phase={p.phase} seed={640} sw={5} />
      <Cel d="M-108 -124 H98 A20 20 0 0 1 118 -104 V-66 H-128 V-104 A20 20 0 0 1 -108 -124 Z" fill={CORAL} phase={p.phase} seed={641} sw={4} broken={false} />
      {[-62, 52].map((x, i) => (
        <g key={x}>
          <ellipse cx={x} cy={-104} rx={9} ry={6} fill={INK} />
          <Cel d={rectP(x - 9, -150, 18, 46, 9)} fill={GREY} phase={p.phase} seed={642 + i} sw={3.5} broken={false} />
        </g>
      ))}
      {k > 0 && day.lines.length > 0 && <TextBlock lines={day.lines} size={day.size} x={-5} cy={36} family={ALFA} fill={INK} anchor="middle" />}
      {s > 0.02 && (
        <g>
          <Cel d={rectP(-122, Y(-60), 234, 190 * s, 12)} fill={k > 0 ? mix(CREAM, INK, 0.06 + 0.1 * k) : CREAM} phase={p.phase} seed={644} sw={3.5} broken={false} />
          {Array.from({ length: 35 }, (_, i) => (
            <rect key={i} x={-102 + (i % 7) * 28} y={Y(-40 + Math.floor(i / 7) * 32)} width={20} height={20 * s} rx={4} fill={i === 17 ? CORAL : mix(CREAM, INK, 0.18)} />
          ))}
        </g>
      )}
    </g>
  );
};

// ---------------------------------------------------------------- time, ideas and housekeeping

/** A clock-face point: `a` degrees clockwise from twelve. */
const dial = (a: number, r: number, cy: number): Pt => [Math.sin(a * RAD) * r, cy - Math.cos(a * RAD) * r];

export const Clock: React.FC<ObjectDrawProps> = (p) => {
  const k = p.act === "spin" ? eInOut(actProgress(p.actT)) : 0;
  const hour = dial(300 + 30 * k, 46, 10);
  const minute = dial(60 + 360 * k, 70, 10);
  return (
    <g>
      <ellipse cx={6} cy={134} rx={110} ry={6} fill={INK} opacity={0.14} />
      <path d="M-40 -110 Q0 -144 40 -110" stroke={INK} strokeWidth={8} fill="none" strokeLinecap="round" />
      <Cel d="M-106 -84 A34 34 0 0 1 -38 -84 Z" fill={MUSTARD} phase={p.phase} seed={670} sw={4} broken={false} />
      <Cel d="M38 -84 A34 34 0 0 1 106 -84 Z" fill={MUSTARD} phase={p.phase} seed={671} sw={4} broken={false} />
      <Cel d={tubeP([[-60, 100], [-80, 122]], 14)} fill={INK} phase={p.phase} seed={672} sw={3} broken={false} />
      <Cel d={tubeP([[60, 100], [80, 122]], 14)} fill={INK} phase={p.phase} seed={673} sw={3} broken={false} />
      <Cel d={ellP(0, 10, 112, 112)} fill={CORAL} phase={p.phase} seed={674} sw={5} />
      <Cel d={ellP(0, 10, 90, 90)} fill={CREAM} phase={p.phase} seed={675} sw={4} broken={false} />
      {Array.from({ length: 12 }, (_, i) => {
        const [x0, y0] = dial(i * 30, i % 3 === 0 ? 66 : 72, 10);
        const [x1, y1] = dial(i * 30, 80, 10);
        return <line key={i} x1={x0} y1={y0} x2={x1} y2={y1} stroke={INK} strokeWidth={i % 3 === 0 ? 7 : 4} strokeLinecap="round" />;
      })}
      <line x1={0} y1={10} x2={hour[0]} y2={hour[1]} stroke={INK} strokeWidth={12} strokeLinecap="round" />
      <line x1={0} y1={10} x2={minute[0]} y2={minute[1]} stroke={NAVY} strokeWidth={8} strokeLinecap="round" />
      <Cel d={ellP(0, 10, 9, 9)} fill={CORAL} phase={p.phase} seed={676} sw={3.5} broken={false} />
    </g>
  );
};

export const Bulb: React.FC<ObjectDrawProps> = (p) => {
  const k = p.act === "light" ? eOut(actProgress(p.actT)) : 0;
  const rays = clamp01((k - 0.3) / 0.7);
  return (
    <g>
      {rays > 0 &&
        [-180, -157.5, -135, -112.5, -90, -67.5, -45, -22.5, 0].map((a) => {
          const r0 = 90;
          const r1 = 90 + 12 * rays;
          return (
            <line
              key={a}
              x1={r0 * Math.cos(a * RAD)} y1={-52 + r0 * Math.sin(a * RAD)}
              x2={r1 * Math.cos(a * RAD)} y2={-52 + r1 * Math.sin(a * RAD)}
              stroke={CORAL} strokeWidth={7} strokeLinecap="round"
            />
          );
        })}
      <Cel
        d="M-36 40 C-36 14 -80 -4 -80 -52 A80 80 0 1 1 80 -52 C80 -4 36 14 36 40 Z"
        fill={mix(CREAM, MUSTARD, k)} phase={p.phase} seed={700} sw={5}
      />
      {k > 0 && <path d="M-58 -70 A60 60 0 0 1 -26 -108" stroke={CREAM} strokeWidth={9} fill="none" strokeLinecap="round" />}
      <path d="M-18 40 L-18 -10 Q-14 -36 -6 -16 Q0 -36 6 -16 Q14 -36 18 -10 L18 40" stroke={k > 0 ? CORAL_DK : INK} strokeWidth={4} fill="none" strokeLinejoin="round" />
      <Cel d={rectP(-40, 40, 80, 62, 10)} fill={GREY} phase={p.phase} seed={701} sw={4.5} broken={false} />
      <path d="M-40 60 H40 M-40 80 H40" stroke={INK} strokeWidth={4} />
      <Cel d="M-22 102 Q0 128 22 102 Z" fill={INK} phase={p.phase} seed={702} sw={3.5} broken={false} />
      {rays >= 1 && (
        <g>
          <Sparkle x={-92} y={-120} r={12} color={CREAM} />
          <Sparkle x={88} y={-128} r={10} color={MUSTARD} rot={20} />
        </g>
      )}
    </g>
  );
};

/** A ten-toothed gear's outline turned `rot` degrees. */
function gearPts(rot: number): Pt[] {
  const pts: Pt[] = [];
  for (let i = 0; i < 10; i++) {
    const c = rot + i * 36;
    for (const [da, r] of [[-10, 96], [-6, 118], [6, 118], [10, 96]] as const) {
      pts.push([r * Math.cos((c + da) * RAD), r * Math.sin((c + da) * RAD)]);
    }
  }
  return pts;
}

export const Gear: React.FC<ObjectDrawProps> = (p) => {
  const rot = p.act === "turn" ? 45 * eInOut(actProgress(p.actT)) : 0;
  return (
    <g>
      <Cel d={polyP(gearPts(rot - 90))} fill={MUSTARD} phase={p.phase} seed={730} sw={5} />
      {Array.from({ length: 5 }, (_, i) => {
        const a = (rot - 54 + i * 72) * RAD;
        return <Cel key={i} d={ellP(70 * Math.cos(a), 70 * Math.sin(a), 13, 13)} fill={mix(MUSTARD, INK, 0.35)} phase={p.phase} seed={731 + i} sw={3.5} broken={false} />;
      })}
      <Cel d={ellP(0, 0, 46, 46)} fill={CREAM} phase={p.phase} seed={736} sw={4} broken={false} />
      <Cel d={ellP(0, 0, 18, 18)} fill={INK} phase={p.phase} seed={737} sw={0} />
      <circle cx={32 * Math.cos((rot - 90) * RAD)} cy={32 * Math.sin((rot - 90) * RAD)} r={6} fill={CORAL} />
    </g>
  );
};

export const Magnifier: React.FC<ObjectDrawProps> = (p) => {
  const t = p.act === "scan" ? actProgress(p.actT) : 0;
  const dx = -18 * Math.sin(t * Math.PI * 2);
  return (
    <g transform={`translate(${dx.toFixed(2)} 0)`}>
      <Cel d={tubeP([[40, 34], [90, 86]], 34)} fill={CORAL} phase={p.phase} seed={760} sw={5} />
      <Cel d={tubeP([[30, 22], [50, 42]], 30)} fill={GREY} phase={p.phase} seed={761} sw={4} broken={false} />
      <Cel d={ellP(-22, -30, 88, 88)} fill={NAVY} phase={p.phase} seed={762} sw={5} />
      <Cel d={ellP(-22, -30, 66, 66)} fill={mix(BLUE, CREAM, 0.55)} phase={p.phase} seed={763} sw={4} broken={false} />
      <path d={arcD(-22, -30, 48, 200, 250)} stroke={CREAM} strokeWidth={9} fill="none" strokeLinecap="round" />
    </g>
  );
};

const BELL_RAYS: [Pt, Pt][] = [
  [[-84, -84], [-106, -100]], [[-92, -48], [-118, -52]], [[-88, -12], [-112, -2]],
  [[84, -84], [106, -100]], [[92, -48], [118, -52]], [[88, -12], [112, -2]],
];

export const Bell: React.FC<ObjectDrawProps> = (p) => {
  const t = p.act === "ring" ? actProgress(p.actT) : 0;
  const angle = 7 * Math.sin(t * Math.PI * 4) * (1 - t);
  const rays = p.act === "ring" && p.actT >= 0 ? eOut(clamp01(t / 0.3)) : 0;
  return (
    <g>
      {rays > 0 &&
        BELL_RAYS.map(([a, b], i) => (
          <line key={i} x1={a[0]} y1={a[1]} x2={a[0] + (b[0] - a[0]) * rays} y2={a[1] + (b[1] - a[1]) * rays} stroke={CORAL} strokeWidth={7} strokeLinecap="round" />
        ))}
      <g transform={`rotate(${angle.toFixed(2)} 0 -108)`}>
        <Cel d={ellP(0, 84, 16, 16)} fill={GREY} phase={p.phase} seed={790} sw={3.5} broken={false} />
        <Cel d={ellP(0, -108, 13, 13)} fill={MUSTARD} phase={p.phase} seed={791} sw={3.5} broken={false} />
        <Cel
          d="M-80 56 C-66 42 -62 18 -60 -18 C-58 -70 -34 -100 0 -100 C34 -100 58 -70 60 -18 C62 18 66 42 80 56 Z"
          fill={MUSTARD} phase={p.phase} seed={792} sw={5}
        />
        <path d="M-36 -70 C-44 -50 -46 -20 -46 10" stroke={CREAM} strokeWidth={10} fill="none" strokeLinecap="round" opacity={0.7} />
        <Cel d={rectP(-86, 50, 172, 22, 11)} fill={CORAL} phase={p.phase} seed={793} sw={4} broken={false} />
      </g>
    </g>
  );
};

export const Cloud: React.FC<ObjectDrawProps> = (p) => {
  const k = p.act === "upload" ? actProgress(p.actT) : 0;
  const on = p.act === "upload" && p.actT >= 0;
  const ay = 14 - 80 * eOut(k);
  return (
    <g>
      <Cel d="M-130 70 A55 55 0 0 1 -110 -30 A75 75 0 0 1 20 -80 A65 65 0 0 1 130 -20 A50 50 0 0 1 130 70 Z" fill={CREAM} phase={p.phase} seed={820} sw={5} />
      <path d="M-100 52 H96" stroke={mix(CREAM, INK, 0.2)} strokeWidth={6} strokeLinecap="round" />
      {on && (
        <g>
          {k < 1 && [-10, 10].map((x) => (
            <line key={x} x1={x} y1={ay + 96} x2={x} y2={Math.min(ay + 120, 104)} stroke={INK} strokeWidth={4} strokeLinecap="round" opacity={0.5} />
          ))}
          <Cel d={rectP(-18, ay + 40, 36, 50, 6)} fill={TEAL} phase={p.phase} seed={821} sw={4} broken={false} />
          <Cel d={polyP([[-44, ay + 44], [0, ay], [44, ay + 44]])} fill={TEAL} phase={p.phase} seed={822} sw={4} broken={false} />
          {k >= 1 && <Sparkle x={108} y={-78} r={14} color={MUSTARD} rot={15} />}
        </g>
      )}
    </g>
  );
};

const PAPER_BALL: Pt[] = [[0, -27], [12, -20], [26, -16], [22, -2], [27, 12], [12, 20], [4, 27], [-10, 22], [-25, 18], [-22, 2], [-27, -10], [-14, -18]];

export const Trash: React.FC<ObjectDrawProps> = (p) => {
  const k = p.act === "drop" ? actProgress(p.actT) : 0;
  const on = p.act === "drop" && p.actT >= 0;
  const fall = clamp01(k / 0.7);
  const by = -110 + 80 * eIn(fall) - (k > 0.7 ? 8 * Math.sin((Math.PI * (k - 0.7)) / 0.3) : 0);
  const spin = 200 * fall;
  return (
    <g>
      <ellipse cx={6} cy={138} rx={82} ry={6} fill={INK} opacity={0.14} />
      <Cel d={ellP(0, -40, 90, 22)} fill={mix(OLIVE, INK, 0.5)} phase={p.phase} seed={850} sw={5} />
      {on && (
        <g transform={`translate(0 ${by.toFixed(2)}) rotate(${spin.toFixed(1)})`}>
          <Cel d={polyP(PAPER_BALL)} fill={CREAM} phase={p.phase} seed={851} sw={3.5} broken={false} />
          <path d="M-12 -8 L2 0 L-4 12 M8 -14 L4 -2 L16 6" stroke={INK} strokeWidth={2.5} fill="none" opacity={0.6} />
        </g>
      )}
      <Cel d="M-90 -40 A90 22 0 0 0 90 -40 L70 126 Q0 140 -70 126 Z" fill={OLIVE} phase={p.phase} seed={852} sw={5} />
      {[-45, 0, 45].map((x) => (
        <line key={x} x1={x} y1={-40 + 22 * Math.sqrt(1 - (x / 90) ** 2) + 8} x2={x * 0.78} y2={124} stroke={INK} strokeWidth={4} opacity={0.3} strokeLinecap="round" />
      ))}
      <Cel d={ellP(0, -40, 90, 22)} fill={OLIVE} phase={p.phase} seed={853} sw={5} noFill />
    </g>
  );
};

export const Table: React.FC<ObjectDrawProps> = (p) => (
  <g>
    <ellipse cx={8} cy={134} rx={220} ry={8} fill={INK} opacity={0.14} />
    <Cel d={polyP([[-172, -80], [-146, -80], [-178, 128], [-196, 128]])} fill={HAIR} phase={p.phase} seed={880} sw={4} broken={false} />
    <Cel d={polyP([[146, -80], [172, -80], [196, 128], [178, 128]])} fill={HAIR} phase={p.phase} seed={881} sw={4} broken={false} />
    <Cel d={polyP([[-193.7, 108], [-174.9, 108], [-178, 128], [-196, 128]])} fill={MUSTARD} phase={p.phase} seed={882} sw={3.5} broken={false} />
    <Cel d={polyP([[174.9, 108], [193.7, 108], [196, 128], [178, 128]])} fill={MUSTARD} phase={p.phase} seed={883} sw={3.5} broken={false} />
    <Cel d={rectP(-180, -86, 360, 18, 6)} fill={mix(CORAL, INK, 0.35)} phase={p.phase} seed={884} sw={3.5} broken={false} />
    <Cel d={rectP(-214, -112, 428, 28, 10)} fill={CORAL} phase={p.phase} seed={885} sw={5} />
  </g>
);

export const THINGS: Record<
  | "router" | "lock" | "key" | "shield" | "usb" | "battery" | "envelope" | "document" | "checklist" | "card"
  | "sign" | "calendar" | "clock" | "bulb" | "gear" | "magnifier" | "bell" | "cloud" | "trash" | "table",
  React.FC<ObjectDrawProps>
> = {
  router: Router,
  lock: Lock,
  key: Key,
  shield: Shield,
  usb: Usb,
  battery: Battery,
  envelope: Envelope,
  document: DocumentSheet,
  checklist: Checklist,
  card: Card,
  sign: Sign,
  calendar: Calendar,
  clock: Clock,
  bulb: Bulb,
  gear: Gear,
  magnifier: Magnifier,
  bell: Bell,
  cloud: Cloud,
  trash: Trash,
  table: Table,
};
