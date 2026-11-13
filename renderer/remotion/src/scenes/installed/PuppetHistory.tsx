/*
 * PuppetHistory: the whole of a Puppet History video, as one scene.
 *
 * "You are now a..." history told by round-headed cut-out puppets in era
 * costumes, framed from the waist up on flat illustrated sets, in beats joined
 * by hard cuts: a set where puppets slide in, act, swap costumes, hold up props
 * and signs on the narrator's words; a document card where a red stamp lands
 * and a number is struck out and a new one scrawled; a flat map of today's
 * countries where regions fill in and arrows grow. The agent never writes this
 * file's kind of code: it writes `props.puppetHistory`, which the MCP server
 * validates against ./puppetHistory/contract.ts before render.
 *
 * Kept cheap on the CPU renderer (software GL): a set's big flat areas are
 * plain page boxes and its decor, every puppet look, prop, sign and stamp a
 * cached bitmap (./characterKit/sprite.tsx); the camera never moves, so a held
 * shot repaints only what changes.
 */
import React from "react";
import { AbsoluteFill, useCurrentFrame, useVideoConfig } from "remotion";
import { useCustomDrawings } from "./characterKit/customProps";
import { useStyleFonts } from "./characterKit/fonts";
import { hashSeed } from "./characterKit/geometry";
import { Sprite, type SpriteBox } from "./characterKit/sprite";
import { GEOMETRY, POSES, PROPS, signWidth, type PHBeat, type PuppetHistoryData } from "./puppetHistory/contract";
import { FONTS } from "./puppetHistory/fonts";
import { CREAM, HAND, INK, LW, PAPER, RED, ROUND, TYPE, WOOD, WOOD_LIGHT, inked, type PropDrawProps } from "./puppetHistory/ink";
import { MapView } from "./puppetHistory/map";
import { PROP_DRAWINGS } from "./puppetHistory/props";
import { Puppet, handAt, puppetKey, puppetSpriteBox } from "./puppetHistory/puppet";
import { SET_DRAWINGS } from "./puppetHistory/sets";
import { beatAt, beatEnd, dateAt, mapAt, puppetsAt, stampsAt, strikesAt, type PuppetState } from "./puppetHistory/stage";

type PropDrawing = React.FC<PropDrawProps>;
const S = GEOMETRY.puppetScale;
const STAMP_INK: Record<string, string> = { red: RED, green: "#3E8E41", blue: "#3A64A8" };

// ── pieces drawn into sprites ─────────────────────────────────────────────────
const SignBoard: React.FC<{ text: string }> = ({ text }) => {
  const w = signWidth(text), h = GEOMETRY.signH;
  const size = Math.min(60, (w - 50) / Math.max(1, text.length * 0.6));
  return (
    <g>
      <rect x={-w / 2} y={-h / 2} width={w} height={h} rx={10} {...inked(PAPER)} />
      <text x={0} y={size * 0.36} textAnchor="middle" fontFamily={ROUND} fontWeight={700} fontSize={size} fill={INK}>{text}</text>
    </g>
  );
};

const Stamp: React.FC<{ text: string; color: string }> = ({ text, color }) => {
  const size = Math.min(110, 560 / Math.max(1, text.length * 0.62));
  const w = Math.max(220, text.length * size * 0.62 + 90), h = size * 1.5;
  return (
    <g fill="none" stroke={color} strokeLinejoin="round">
      <rect x={-w / 2} y={-h / 2} width={w} height={h} rx={14} strokeWidth={10} />
      <rect x={-w / 2 + 16} y={-h / 2 + 16} width={w - 32} height={h - 32} rx={8} strokeWidth={4} />
      <text x={0} y={size * 0.36} textAnchor="middle" fontFamily={ROUND} fontWeight={700} fontSize={size} fill={color} stroke="none">{text}</text>
    </g>
  );
};
const stampBox = (text: string): SpriteBox => {
  const size = Math.min(110, 560 / Math.max(1, text.length * 0.62));
  const w = Math.max(220, text.length * size * 0.62 + 90), h = size * 1.5;
  return { left: -w / 2 - 12, top: -h / 2 - 12, width: w + 24, height: h + 24 };
};

// ── a puppet with its prop, sign and name plate ──────────────────────────────
// the right arm's raise per pose, for where a held prop sits
const POSE_R: Record<string, number> = Object.fromEntries(Object.entries(POSES).map(([k, v]) => [k, v.r]));

const PuppetSprite: React.FC<{ p: PuppetState; custom: Record<string, PropDrawing>; frame: number }> = ({ p, custom, frame }) => {
  const look = { costume: p.costume, pose: p.pose, face: p.face, blink: p.blink };
  const sq = frame - p.since;
  const squash = sq >= 0 && sq < 2 && p.pop >= 1 ? (sq === 0 ? "scale(1.04, 0.96)" : "scale(1.02, 0.98)") : undefined;
  const pop = p.pop < 1 ? `scale(${p.pop.toFixed(3)})` : undefined;
  const transform = [pop, squash].filter(Boolean).join(" ") || undefined;
  const parts: React.ReactNode[] = [
    <Sprite key="body" id={puppetKey(look)} draw={() => <Puppet {...look} />} box={puppetSpriteBox(p.pose)} x={p.x} y={GEOMETRY.waistY}
      scale={S} transform={transform} flip={p.flip} />,
  ];
  if (p.prop && p.pop >= 1) {
    const Draw = (PROP_DRAWINGS as Record<string, PropDrawing>)[p.prop] ?? custom[p.prop];
    const box = (PROPS as Record<string, { w: number; h: number }>)[p.prop];
    if (Draw && box) {
      const [hx, hy] = handAt(1, POSE_R[p.pose] ?? -14);
      const x = p.x + (p.flip ? -hx : hx) * S, y = GEOMETRY.waistY + hy * S - (box.h * S) / 2 + 24;
      parts.push(<Sprite key="prop" id={`ph-prop|${p.prop}|${p.propText}`} draw={() => <Draw text={p.propText} />}
        box={{ left: -box.w / 2 - 8, top: -box.h / 2 - 8, width: box.w + 16, height: box.h + 16 }} x={x} y={y} scale={S} fonts={FONTS} />);
    }
  }
  if (p.sign && p.pop >= 1) {
    const w = signWidth(p.sign);
    parts.push(<Sprite key="sign" id={`ph-sign|${p.sign}`} draw={() => <SignBoard text={p.sign} />}
      box={{ left: -w / 2 - 8, top: -GEOMETRY.signH / 2 - 8, width: w + 16, height: GEOMETRY.signH + 16 }} x={p.x} y={GEOMETRY.signY} fonts={FONTS} />);
  }
  return <>{parts}</>;
};

const NamePlate: React.FC<{ x: number; text: string }> = ({ x, text }) => (
  <div style={{ position: "absolute", left: x - 230, width: 460, top: GEOMETRY.plateY - 34, display: "flex", justifyContent: "center" }}>
    <div style={{ background: CREAM, border: `5px solid ${INK}`, borderRadius: 10, padding: "4px 22px", fontFamily: ROUND, fontWeight: 700,
      fontSize: 38, lineHeight: 1.2, color: INK, whiteSpace: "nowrap" }}>{text}</div>
  </div>
);

// ── the three kinds of beat ──────────────────────────────────────────────────
const SetBack: React.FC<{ beat: Extract<PHBeat, { type: "set" }> }> = ({ beat }) => {
  const s = SET_DRAWINGS[beat.set];
  return (
    <>
      {s.bands.map((b, i) => (
        <div key={i} style={{ position: "absolute", left: 0, width: 1080, top: b.top, height: (s.bands[i + 1]?.top ?? GEOMETRY.frontY) - b.top, background: b.color }} />
      ))}
      {s.decor.map((d) => <Sprite key={d.id} id={`ph-decor|${d.id}`} draw={() => <d.Draw />} box={d.box} x={d.x} y={d.y} fonts={FONTS} />)}
    </>
  );
};

const Front: React.FC<{ color: string }> = ({ color }) => (
  <div style={{ position: "absolute", left: 0, width: 1080, top: GEOMETRY.frontY, height: 1920 - GEOMETRY.frontY, background: color, borderTop: `${LW}px solid ${INK}` }} />
);

const Card: React.FC<{ beat: Extract<PHBeat, { type: "card" }>; frame: number }> = ({ beat, frame }) => {
  const [x, y, w, h] = GEOMETRY.card;
  const strikes = strikesAt(beat, frame);
  return (
    <div style={{ position: "absolute", left: x, top: y, width: w, height: h, background: PAPER, border: `${LW}px solid ${INK}`, borderRadius: 8,
      transform: "rotate(-1.5deg)", padding: "56px 60px", boxSizing: "border-box", fontFamily: TYPE, fontWeight: 700, color: INK }}>
      <div style={{ fontSize: 50, lineHeight: 1.2, borderBottom: `4px solid ${INK}`, paddingBottom: 22, marginBottom: 40, whiteSpace: "nowrap" }}>{beat.title}</div>
      {beat.lines.map((line, i) => {
        const st = strikes.get(i);
        return (
          <div key={i} style={{ fontSize: 40, lineHeight: 1.25, marginBottom: 64, whiteSpace: "nowrap" }}>
            <span style={{ position: "relative" }}>
              {line}
              {st ? <span style={{ position: "absolute", left: -6, top: "52%", height: 7, width: `calc(${(st.strike * 100).toFixed(1)}% + 12px)`, background: RED, borderRadius: 4 }} /> : null}
              {/* the new value is scrawled just under the struck one, where the next line leaves room */}
              {st && st.scrawl > 0 ? (
                <span style={{ position: "absolute", left: "38%", top: "88%", fontFamily: HAND, fontSize: 50, lineHeight: 1, color: RED, transform: "rotate(-4deg)",
                  clipPath: `inset(-20% ${((1 - st.scrawl) * 100).toFixed(1)}% -20% -5%)` }}>{st.text}</span>
              ) : null}
            </span>
          </div>
        );
      })}
    </div>
  );
};

export type PuppetHistoryProps = { puppetHistory: PuppetHistoryData };

export const PuppetHistory: React.FC<PuppetHistoryProps> = ({ puppetHistory: data }) => {
  const frame = useCurrentFrame();
  const { durationInFrames } = useVideoConfig();
  useStyleFonts("PuppetHistory", FONTS);
  const custom = useCustomDrawings<PropDrawProps>("PuppetHistory", data.customProps ?? []) ?? {};
  const bi = beatAt(data, frame);
  if (bi < 0) return null;
  const beat = data.beats[bi];
  void beatEnd(data, bi, durationInFrames);
  const names = new Map(data.cast.map((a) => [a.id, a.name ?? ""]));
  const puppets = beat.type === "card" ? [] : puppetsAt(data, beat, frame);
  const date = dateAt(beat, frame);
  return (
    <AbsoluteFill style={{ background: CREAM, overflow: "hidden" }}>
      {beat.type === "set" ? <SetBack beat={beat} /> : null}
      {beat.type === "map" ? (
        <>
          <div style={{ position: "absolute", inset: 0, background: CREAM }} />
          <MapView focus={beat.focus} state={mapAt(beat, frame)} />
        </>
      ) : null}
      {beat.type === "card" ? <div style={{ position: "absolute", inset: 0, background: WOOD_LIGHT }} /> : null}
      {puppets.map((p) => <PuppetSprite key={p.id} p={p} custom={custom} frame={frame} />)}
      {beat.type !== "card" ? <Front color={beat.type === "set" ? SET_DRAWINGS[beat.set].front : WOOD} /> : null}
      {puppets.filter((p) => names.get(p.id) && p.pop >= 1).map((p) => <NamePlate key={`n-${p.id}`} x={p.x} text={names.get(p.id)!} />)}
      {beat.type === "card" ? <Card beat={beat} frame={frame} /> : null}
      {stampsAt(beat, frame).map((s, i) => {
        const rot = -12 + (hashSeed(`${s.text}${s.seed}`) % 10);
        return (
          <Sprite key={`s-${i}`} id={`ph-stamp|${s.text}|${s.color}`} draw={() => <Stamp text={s.text} color={STAMP_INK[s.color] ?? RED} />}
            box={stampBox(s.text)} x={540} y={beat.type === "card" ? GEOMETRY.cardStampY : GEOMETRY.stampY} transform={`rotate(${rot}deg) scale(${(1 + 0.18 * s.kick).toFixed(3)})`} fonts={FONTS} />
        );
      })}
      {date ? (
        <div style={{ position: "absolute", left: GEOMETRY.dateX, top: GEOMETRY.dateY, fontFamily: HAND, fontWeight: 700, fontSize: 70, color: INK,
          transform: "rotate(-4deg)", whiteSpace: "nowrap", textShadow: `0 0 6px ${PAPER}` }}>{date}</div>
      ) : null}
    </AbsoluteFill>
  );
};

export default PuppetHistory;
