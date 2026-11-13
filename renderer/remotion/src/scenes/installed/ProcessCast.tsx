/*
 * ProcessCast: the whole of a Process Cast video, as one scene.
 *
 * An invisible process acted out by a cast of drawn parts with faces (beans,
 * blobs, gems, blocks, a byte made of unit cubes) on warm grey paper: they
 * stand at stations along one ground line, carry task cards, split into
 * clones and merge back, hop from station to station, and react with their
 * faces and small marks, while the camera travels the line. Nobody talks: a
 * face shows a feeling, never the words. The agent never writes this file's
 * kind of code: it writes `props.processCast` (the cast, the stations and
 * events timed to the narration), which the MCP server validates against
 * ./processCast/contract.ts before render.
 *
 * Kept cheap on the CPU renderer (software GL): every actor, station piece,
 * sign, card, mark and prop is a cached bitmap (./characterKit/sprite.tsx), the
 * wobble is seeded once and never boils, the camera moves bitmaps by their
 * position, and the paper is one flat colour (a full-frame image layer of any
 * kind cost about 0.2 CPU-seconds per frame when measured).
 */
import React from "react";
import { AbsoluteFill, useCurrentFrame } from "remotion";
import { useCustomDrawings } from "./characterKit/customProps";
import { useStyleFonts } from "./characterKit/fonts";
import { clamp01, ease, hashSeed } from "./characterKit/geometry";
import { Sprite, type SpriteBox } from "./characterKit/sprite";
import { Actor, actorBox, actorKey, type ActorLook } from "./processCast/actor";
import {
  GEOMETRY, H, STATIONS, TIMING, W, bodySize, stationX, type Mark, type ProcessCastData,
} from "./processCast/contract";
import { FONTS } from "./processCast/fonts";
import { CREAM, GREEN, INK, MONO, PAPER, RED, boxPath } from "./processCast/ink";
import { PROP_DRAWINGS } from "./processCast/props";
import { castAt, blinkAt, propBoxSize, toScreen, type ActorState } from "./processCast/stage";
import { FURNITURE, GroundStrip, Sign, signBox } from "./processCast/stations";

type PropDrawing = React.FC<{ text: string }>;
const G = GEOMETRY.groundY;
const VIEW = W / 2 + 600;

// ── a carried card, a mark ────────────────────────────────────────────────────
export function cardBox(text: string): SpriteBox {
  const w = Math.max(text.length, 3) * 19 + 44;
  return { left: -w / 2 - 6, top: -38, width: w + 16, height: 84 };
}

export const Card: React.FC<{ text: string; seed: number }> = ({ text, seed }) => {
  const w = Math.max(text.length, 3) * 19 + 44;
  return (
    <g>
      <path d={boxPath(0, 0, w, 60, seed, 1.6)} fill={INK} />
      <text x={0} y={11} textAnchor="middle" fontFamily={MONO} fontWeight={700} fontSize={30} fill={CREAM}>{text}</text>
    </g>
  );
};

const MARK_BOX: SpriteBox = { left: -40, top: -50, width: 80, height: 100 };
const MarkDrawing: React.FC<{ mark: Mark }> = ({ mark }) => {
  switch (mark) {
    case "question":
      return <text x={0} y={30} textAnchor="middle" fontFamily={MONO} fontWeight={700} fontSize={84} fill={INK}>?</text>;
    case "exclaim":
      return <text x={0} y={30} textAnchor="middle" fontFamily={MONO} fontWeight={700} fontSize={84} fill={RED}>!</text>;
    case "sweat":
      return <path d="M0 -30 Q-22 6 -12 22 Q0 34 12 22 Q22 6 0 -30Z" fill="#8FC3E8" stroke={INK} strokeWidth={4} />;
    case "check":
      return <path d="M-26 0 L-8 20 L28 -24" stroke={GREEN} strokeWidth={11} fill="none" strokeLinecap="round" strokeLinejoin="round" />;
    case "cross":
      return <path d="M-22 -22 L22 22 M22 -22 L-22 22" stroke={RED} strokeWidth={11} fill="none" strokeLinecap="round" />;
    case "idea":
      return (
        <g>
          <circle cx={0} cy={-6} r={20} fill="#F2D267" stroke={INK} strokeWidth={4} />
          <rect x={-9} y={14} width={18} height={12} rx={3} fill={CREAM} stroke={INK} strokeWidth={3.5} />
        </g>
      );
    default:
      return <g />;
  }
};

// ── an actor ─────────────────────────────────────────────────────────────────
function lookOf(a: ActorState, all: ActorState[], data: ProcessCastData): -1 | 0 | 1 {
  if (!a.lookAt || a.lookAt === "front") return 0;
  const other = all.find((q) => q.id === a.lookAt);
  const st = data.stations.findIndex((s) => s.id === a.lookAt);
  const tx = other ? other.x : st >= 0 ? stationX(st) + GEOMETRY.furnitureX : a.x;
  return tx > a.x + 10 ? 1 : tx < a.x - 10 ? -1 : 0;
}

/** Squash on landing: volume-preserving, about 8 frames. */
const landSquash = (dt: number) => (dt < 0 || dt > 14 ? 0 : 0.14 * Math.exp(-dt / 3) * Math.cos(dt * 0.9));

const ActorSprite: React.FC<{ a: ActorState; all: ActorState[]; data: ProcessCastData; camX: number; frame: number }> = ({ a, all, data, camX, frame }) => {
  const seed = hashSeed(a.base.id) % 997;
  const look: ActorLook = {
    body: a.base.body, tint: a.base.tint, units: a.units, accessory: a.base.accessory ?? "none", face: a.face,
    blink: blinkAt(frame, seed + a.id.length * 13), look: lookOf(a, all, data), silhouette: a.silhouette, holding: a.card !== "", seed,
  };
  const x = toScreen(a.x, camX);
  const t = frame - a.enterAt;
  let dy = a.lift, dx = 0, s = a.scale;
  if (t < TIMING.enter) {
    const k = clamp01(t / TIMING.enter);
    if (a.from === "drop") dy += -900 * (1 - k * k);
    else if (a.from === "slide") dx = (a.x > camX ? 1 : -1) * 700 * (1 - ease.out(k));
    else s *= Math.max(0.01, ease.outBack(k));
  }
  if (a.exitAt >= 0) s *= Math.max(0.01, 1 - clamp01((frame - a.exitAt) / TIMING.enter));
  if (a.vanish > 0) s *= Math.max(0.01, 1 - a.vanish);
  const sq = a.from === "drop" && t >= TIMING.enter ? landSquash(t - TIMING.enter) : landSquash(a.landed);
  const sx = s * (1 + sq), sy = s * (1 - sq);
  const transform = dx || dy || sx !== 1 || sy !== 1 ? `translate(${dx}px, ${dy}px) scale(${sx}, ${sy})` : undefined;
  return (
    <Sprite id={actorKey(look)} draw={() => <Actor {...look} />} box={actorBox(a.base.body, a.units)} x={x} y={G}
      transform={transform} fonts={FONTS} />
  );
};

const Overheads: React.FC<{ a: ActorState; camX: number; frame: number }> = ({ a, camX, frame }) => {
  const { h } = bodySize(a.base.body, a.units);
  const x = toScreen(a.x, camX);
  const top = G + a.lift - h * a.scale;
  const out: React.ReactNode[] = [];
  const label = a.card || (a.silhouette || a.vanish > 0 ? "" : a.base.name ?? "");
  if (label) {
    const seed = hashSeed(label) % 991;
    const k = a.card ? ease.outBack(clamp01((frame - Math.max(a.enterAt, 0)) / 8)) : 1;
    out.push(
      <Sprite key="tag" id={`pc-card|${label}|${a.card ? 1 : 0}|${seed}`} box={cardBox(label)} x={x}
        y={top - (a.card ? 70 : 52) - (a.slot % 2 ? GEOMETRY.tagStagger : 0)}
        draw={() => (a.card ? <Card text={label} seed={seed} /> : <NameTag text={label} seed={seed} />)} fonts={FONTS}
        transform={k < 1 ? `scale(${Math.max(0.01, k)})` : undefined} />,
    );
  }
  if (a.mark) {
    const k = clamp01((frame - a.markAt) / 8);
    const wob = frame - a.markAt < 30 ? Math.sin((frame - a.markAt) * 0.5) * 3 * (1 - (frame - a.markAt) / 30) : 0;
    out.push(
      <Sprite key="mark" id={`pc-mark|${a.mark}`} box={MARK_BOX} x={x + bodySize(a.base.body, a.units).w * 0.45 * a.scale} y={top - 20}
        draw={() => <MarkDrawing mark={a.mark as Mark} />} fonts={FONTS}
        transform={k < 1 || wob ? `scale(${Math.max(0.01, ease.outBack(k))}) rotate(${wob}deg)` : undefined} />,
    );
  }
  return <>{out}</>;
};

const NameTag: React.FC<{ text: string; seed: number }> = ({ text, seed }) => {
  const w = Math.max(text.length, 3) * 19 + 44;
  return (
    <g>
      <path d={boxPath(0, 0, w, 52, seed, 1.4)} fill={CREAM} stroke={INK} strokeWidth={4} />
      <text x={0} y={10} textAnchor="middle" fontFamily={MONO} fontWeight={700} fontSize={28} fill={INK}>{text}</text>
    </g>
  );
};

// ── the scene ─────────────────────────────────────────────────────────────────
export default function ProcessCast({ processCast }: { processCast?: ProcessCastData; durationInFrames: number }) {
  const frame = useCurrentFrame();
  useStyleFonts("ProcessCast", FONTS);
  const data: ProcessCastData = processCast ?? { cast: [], stations: [], events: [] };
  const customSpecs = data.customProps ?? [];
  const custom = useCustomDrawings<{ text: string }>("ProcessCast", customSpecs) ?? {};
  const state = castAt(data, frame);
  const camX = state.camX;
  const visible = (worldX: number) => Math.abs(worldX - camX) < VIEW;
  return (
    <AbsoluteFill style={{ background: PAPER, width: W, height: H, overflow: "hidden" }}>
      {data.stations.map((st, i) => {
        const cx = stationX(i);
        if (!visible(cx)) return null;
        const seed = 31 + i * 17;
        const furn = STATIONS[st.kind];
        const Furniture = st.kind === "stage" ? null : FURNITURE[st.kind];
        return (
          <React.Fragment key={st.id}>
            <Sprite id={`pc-ground|${seed}`} box={{ left: -546, top: -46, width: 1092, height: 112 }} x={toScreen(cx, camX)} y={G}
              draw={() => <GroundStrip seed={seed} />} />
            {Furniture && (
              <Sprite id={`pc-furn|${st.kind}|${seed}`} box={{ left: -furn.w / 2 - 12, top: -furn.h - 12, width: furn.w + 24, height: furn.h + 30 }}
                x={toScreen(cx + GEOMETRY.furnitureX, camX)} y={G} draw={() => <Furniture seed={seed} />} />
            )}
            <Sprite id={`pc-sign|${st.sign}|${seed}`} box={signBox(st.sign)} x={toScreen(cx, camX)} y={GEOMETRY.signY}
              draw={() => <Sign text={st.sign} seed={seed} />} fonts={FONTS} />
          </React.Fragment>
        );
      })}
      {state.props.map((p) => {
        if (!visible(p.x)) return null;
        const Draw: PropDrawing | undefined = (PROP_DRAWINGS as Record<string, PropDrawing>)[p.prop] ?? custom[p.prop];
        if (!Draw) return null;
        const box = propBoxSize(p.prop, customSpecs);
        const k = ease.outBack(clamp01((frame - p.since) / 8));
        return (
          <Sprite key={`prop-${p.station}`} id={`pc-prop|${p.prop}|${p.text}`} box={{ left: -box.w / 2 - 8, top: -box.h / 2 - 8, width: box.w + 16, height: box.h + 16 }}
            x={toScreen(p.x, camX)} y={p.y} scale={GEOMETRY.propScale} draw={() => <Draw text={p.text} />} fonts={FONTS}
            transform={k < 1 ? `scale(${Math.max(0.01, k)})` : undefined} />
        );
      })}
      {state.actors.filter((a) => visible(a.x)).map((a) => (
        <ActorSprite key={a.id} a={a} all={state.actors} data={data} camX={camX} frame={frame} />
      ))}
      {state.actors.filter((a) => visible(a.x)).map((a) => <Overheads key={`o-${a.id}`} a={a} camX={camX} frame={frame} />)}
      {state.flying.map((c, i) => {
        const x = c.from[0] + (c.to[0] - c.from[0]) * ease.inOut(c.t);
        const y = c.from[1] + (c.to[1] - c.from[1]) * ease.inOut(c.t) - Math.sin(c.t * Math.PI) * 120;
        const seed = hashSeed(c.text) % 991;
        return (
          <Sprite key={`fly-${i}`} id={`pc-card|${c.text}|1|${seed}`} box={cardBox(c.text)} x={toScreen(x, camX)} y={y}
            draw={() => <Card text={c.text} seed={seed} />} fonts={FONTS} />
        );
      })}
    </AbsoluteFill>
  );
}
