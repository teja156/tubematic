/*
 * The Process Cast actors: one body primitive per kind (bean, blob, block, gem,
 * or a grid of unit cubes) and one shared face kit. Feet at (0, 0). Faces show
 * a feeling only: no mouth moves to talk, ever.
 *
 * Every distinct look is drawn once into a cached sprite (../characterKit/
 * sprite.tsx); a hop, a squash or a pop is a transform on that bitmap.
 */
import React from "react";
import type { SpriteBox } from "../characterKit/sprite";
import { GEOMETRY, bodySize, TINTS, type Accessory, type Body, type Face, type Tint } from "./contract";
import { BLUSH, GREEN, Hatches, INK, bodyPath, inkLine, polyPath, tone, type Pt } from "./ink";

export type ActorLook = {
  body: Body;
  tint: Tint;
  units: number;
  accessory: Accessory;
  face: Face;
  blink: boolean;
  /** Eye shift toward what the actor looks at: -1 left, 0 front, 1 right. */
  look: -1 | 0 | 1;
  /** A clone in its first frames: a flat silhouette with no outline or face. */
  silhouette: boolean;
  /** An arm raised to hold a card over the head. */
  holding: boolean;
  seed: number;
};

export function actorKey(l: ActorLook): string {
  return ["pc-actor", l.body, l.tint, l.units, l.accessory, l.face, l.blink ? 1 : 0, l.look, l.silhouette ? 1 : 0, l.holding ? 1 : 0, l.seed].join("|");
}

/** Every pixel an actor can reach from its feet: the body, the accessory above it and a raised arm. */
export function actorBox(body: Body, units: number): SpriteBox {
  const { w, h } = bodySize(body, units);
  return { left: -w / 2 - 60, top: -h - 90, width: w + 120, height: h + 110 };
}

const gemCorners = (w: number, h: number): Pt[] => [
  [-0.3 * w, -h], [0.3 * w, -h], [0.5 * w, -0.66 * h], [0.42 * w, 0], [-0.42 * w, 0], [-0.5 * w, -0.66 * h],
];

function shapeOf(body: Body, w: number, h: number, seed: number): string {
  switch (body) {
    case "bean": return bodyPath(w, h, 2.5, 0.09, seed);
    case "block": return bodyPath(w, h, 5.2, 0.02, seed, 2.6);
    case "blob": return bodyPath(w, h, 2.15, 0.12, seed, 4);
    case "gem": return polyPath(gemCorners(w, h), seed, 2.6, 4);
    default: return bodyPath(w, h, 5.2, 0.02, seed, 2.6);
  }
}

const FaceKit: React.FC<{ w: number; fy: number; look: number; blink: boolean; face: Face; glasses: boolean; seed: number }> = ({
  w, fy, look, blink, face, glasses, seed,
}) => {
  const ex = Math.max(22, w * 0.16);
  const dx = look * 9;
  const lift = { neutral: 0, happy: -5, curious: 0, proud: -4, surprised: -10, worried: -6, sad: 2 }[face];
  const brows = [-1, 1].map((s) => {
    let l = lift;
    let tilt = 0;
    if (face === "curious") { l += s < 0 ? -9 : 1; tilt = s < 0 ? -3 : 2; }
    if (face === "proud") tilt = 3;
    if (face === "happy") tilt = 1;
    if (face === "worried" || face === "sad") tilt = -5;
    const by = fy - 27 + l;
    const x0 = s * ex - 11 + dx * 0.5, x1 = s * ex + 11 + dx * 0.5;
    const yIn = s < 0 ? by + tilt : by - tilt;
    const yOut = s < 0 ? by - tilt : by + tilt;
    return <path key={s} d={inkLine([x0, s < 0 ? yOut : yIn], [x1, s < 0 ? yIn : yOut], seed + s * 7, 1.2, 3)} stroke={INK} strokeWidth={5} strokeLinecap="round" fill="none" />;
  });
  const eyes = [-1, 1].map((s) => {
    const cx = s * ex + dx, cy = fy;
    if (blink) return <path key={s} d={`M${cx - 9} ${cy + 1}Q${cx} ${cy + 5} ${cx + 9} ${cy + 1}`} stroke={INK} strokeWidth={4.5} strokeLinecap="round" fill="none" />;
    if (face === "happy" || face === "proud") return <path key={s} d={`M${cx - 9} ${cy + 4}Q${cx} ${cy - 9} ${cx + 9} ${cy + 4}`} stroke={INK} strokeWidth={5} strokeLinecap="round" fill="none" />;
    const r = face === "surprised" ? 1.15 : 1;
    return (
      <g key={s}>
        <ellipse cx={cx} cy={cy} rx={8.5 * r} ry={11 * r} fill={INK} />
        <circle cx={cx + 2.5} cy={cy - 4} r={2.6} fill="#FFFDF6" />
      </g>
    );
  });
  const my = fy + 24;
  const mx = dx * 0.6;
  let mouth: React.ReactNode;
  if (face === "happy") mouth = <path d={`M${mx - 13} ${my - 2}Q${mx} ${my + 17} ${mx + 13} ${my - 2}Z`} fill="#7A3A30" stroke={INK} strokeWidth={4} strokeLinejoin="round" />;
  else if (face === "surprised") mouth = <ellipse cx={mx} cy={my + 3} rx={6} ry={8} fill="#7A3A30" stroke={INK} strokeWidth={3.5} />;
  else if (face === "curious") mouth = <path d={`M${mx - 7} ${my + 2}Q${mx + 2} ${my - 1} ${mx + 8} ${my + 1}`} stroke={INK} strokeWidth={4} strokeLinecap="round" fill="none" />;
  else if (face === "proud") mouth = <path d={`M${mx - 9} ${my}Q${mx + 1} ${my + 8} ${mx + 11} ${my - 3}`} stroke={INK} strokeWidth={4} strokeLinecap="round" fill="none" />;
  else if (face === "worried") mouth = <path d={`M${mx - 9} ${my + 3}Q${mx - 4} ${my - 2} ${mx} ${my + 2}Q${mx + 4} ${my + 6} ${mx + 9} ${my + 1}`} stroke={INK} strokeWidth={4} strokeLinecap="round" fill="none" />;
  else if (face === "sad") mouth = <path d={`M${mx - 9} ${my + 5}Q${mx} ${my - 4} ${mx + 9} ${my + 5}`} stroke={INK} strokeWidth={4} strokeLinecap="round" fill="none" />;
  else mouth = <path d={`M${mx - 8} ${my}Q${mx} ${my + 7} ${mx + 8} ${my}`} stroke={INK} strokeWidth={4} strokeLinecap="round" fill="none" />;
  return (
    <g>
      {[-1, 1].map((s) => (
        <ellipse key={s} cx={s * (ex + 20) + dx * 0.4} cy={fy + 17} rx={13} ry={7} fill={BLUSH} opacity={0.55} />
      ))}
      {eyes}
      {glasses && [-1, 1].map((s) => <circle key={s} cx={s * ex + dx * 0.4} cy={fy} r={18} fill="none" stroke={INK} strokeWidth={3.5} />)}
      {glasses && <path d={`M${-ex + 18 + dx * 0.4} ${fy - 2}Q${dx * 0.4} ${fy - 9} ${ex - 18 + dx * 0.4} ${fy - 2}`} stroke={INK} strokeWidth={3} fill="none" />}
      {brows}
      {mouth}
    </g>
  );
};

/** A raised stub arm holding a card above the head; the card itself is drawn by the scene. */
const RaisedArm: React.FC<{ w: number; h: number; base: string; seed: number }> = ({ w, h, base, seed }) => {
  const d = bodyPath(24, w * 0.4, 2.4, 0, seed, 1.4);
  return (
    <g transform={`translate(${w * 0.36} ${-h * 0.6}) rotate(20)`}>
      <path d={d} fill={base} stroke={INK} strokeWidth={5} strokeLinejoin="round" />
    </g>
  );
};

function UnitsBody({ units, k, seed }: { units: number; k: string; seed: number }) {
  const n = Math.max(1, units);
  const cols = Math.ceil(Math.sqrt(n));
  const u = GEOMETRY.unitPx;
  const rows = Math.ceil(n / cols);
  const cubes: React.ReactNode[] = [];
  for (let i = 0; i < n; i++) {
    const c = i % cols, r = rows - 1 - Math.floor(i / cols);
    const x = -((cols * u) / 2) + c * u, y = -(r + 1) * u;
    const d = polyPath([[x, y], [x + u, y], [x + u, y + u], [x, y + u]], seed + i, 1.6, 3);
    cubes.push(
      <g key={i}>
        <path d={d} fill={`url(#base-${k})`} />
        <path d={d} fill={`url(#hatch-${k})`} />
        <path d={d} fill="none" stroke={INK} strokeWidth={4} strokeLinejoin="round" />
      </g>,
    );
  }
  return <g>{cubes}</g>;
}

/** An actor, feet at (0, 0). */
export const Actor: React.FC<ActorLook> = ({ body, tint, units, accessory, face, blink, look, silhouette, holding, seed }) => {
  const t = tone(TINTS[tint]);
  const { w, h } = bodySize(body, units);
  const k = "a";
  const fy = body === "units" ? -h + Math.min(h, 52) * 0.55 : body === "gem" || body === "blob" ? -h * 0.55 : -h * 0.6;
  const faceW = body === "units" ? Math.max(w, 104) : w;
  const scale = faceW / 180;
  if (body === "units") {
    return (
      <g>
        <Hatches tones={{ [k]: t }} />
        <defs><pattern id={`base-${k}`} width={4} height={4} patternUnits="userSpaceOnUse"><rect width={4} height={4} fill={t.base} /></pattern></defs>
        {silhouette ? (
          <rect x={-w / 2} y={-h} width={w} height={h} rx={8} fill={t.base} />
        ) : (
          <>
            {holding && <RaisedArm w={w} h={h} base={t.base} seed={seed + 51} />}
            <UnitsBody units={units} k={k} seed={seed} />
            <g transform={`translate(0 ${fy}) scale(${Math.min(1, scale)}) translate(0 ${-fy})`}>
              <FaceKit w={faceW / Math.min(1, scale)} fy={fy} look={look} blink={blink} face={face} glasses={accessory === "glasses"} seed={seed + 9} />
            </g>
          </>
        )}
      </g>
    );
  }
  const shape = shapeOf(body, w, h, seed);
  const sketch = shapeOf(body, w + 3, h + 2, seed + 101);
  return (
    <g>
      <Hatches tones={{ [k]: t }} />
      <defs>
        <clipPath id="pc-body"><path d={shape} /></clipPath>
        <clipPath id="pc-shade"><path d={shape} transform={`translate(${w * 0.3} ${-h * 0.04})`} /></clipPath>
      </defs>
      <path d={shape} fill={t.base} />
      {!silhouette && (
        <>
          <g clipPath="url(#pc-body)">
            <rect x={-w} y={-h - 20} width={w * 2} height={h + 40} fill={`url(#hatch-${k})`} />
            <g clipPath="url(#pc-shade)">
              <rect x={-w} y={-h - 20} width={w * 2} height={h + 40} fill={`url(#shade-${k})`} />
            </g>
            <ellipse cx={-w * 0.22} cy={-h * 0.78} rx={w * 0.16} ry={h * 0.1} fill={t.light} opacity={0.35} />
          </g>
          <path d={shape} fill="none" stroke={INK} strokeWidth={6.5} strokeLinejoin="round" />
          <path d={sketch} fill="none" stroke={INK} strokeWidth={2} opacity={0.4} strokeDasharray="60 24 140 18" />
          {body === "gem" && (
            <g stroke={INK} strokeWidth={3.5} fill="none" strokeLinecap="round" opacity={0.75}>
              <path d={inkLine([-0.5 * w, -0.66 * h], [0.5 * w, -0.66 * h], seed + 3, 1.5)} />
              <path d={inkLine([-0.3 * w, -h], [-0.12 * w, -0.66 * h], seed + 4, 1)} />
              <path d={inkLine([0.3 * w, -h], [0.12 * w, -0.66 * h], seed + 5, 1)} />
            </g>
          )}
          {accessory === "tuft" && (
            <g stroke={INK} strokeWidth={4} fill="none" strokeLinecap="round">
              {[-2, -1, 0, 1, 2].map((q) => (
                <path key={q} d={`M${q * 13} ${-h + 4}Q${q * 16 + 5} ${-h - 18} ${q * 21 + 2} ${-h - 32 + Math.abs(q) * 4}`} />
              ))}
            </g>
          )}
          {accessory === "sprout" && (
            <g>
              <path d={`M0 ${-h + 4}Q-4 ${-h - 22} 4 ${-h - 40}`} stroke={INK} strokeWidth={4.5} fill="none" strokeLinecap="round" />
              {[-1, 1].map((s) => (
                <g key={s} transform={`translate(${4 + s * 2} ${-h - 38}) rotate(${s * 38})`}>
                  <ellipse cx={s * 20} cy={0} rx={21} ry={11} fill={GREEN} stroke={INK} strokeWidth={4} />
                </g>
              ))}
            </g>
          )}
          {accessory === "cap" && (
            <g>
              <path d={`M${-w * 0.3} ${-h + 18}Q0 ${-h - 40} ${w * 0.3} ${-h + 18}Z`} fill={t.shade} stroke={INK} strokeWidth={5} strokeLinejoin="round" />
              <path d={`M${w * 0.2} ${-h + 14}L${w * 0.55} ${-h + 22}`} stroke={INK} strokeWidth={9} strokeLinecap="round" />
            </g>
          )}
          <g transform={`translate(0 ${fy}) scale(${scale}) translate(0 ${-fy})`}>
            <FaceKit w={w / scale} fy={fy} look={look} blink={blink} face={face} glasses={accessory === "glasses"} seed={seed + 9} />
          </g>
          {holding && <RaisedArm w={w} h={h} base={t.base} seed={seed + 51} />}
        </>
      )}
    </g>
  );
};
