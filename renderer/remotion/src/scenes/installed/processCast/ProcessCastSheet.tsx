/*
 * Sheets of the Process Cast library, for a person to approve the look and for
 * an agent's own props to be compared against:
 * - ProcessCastSheet, one page per frame. Page 0: every body in a few tints,
 *   every face, the accessories, a units body growing, the marks. Page 1: the
 *   station furniture with a sign and the ground. Page 2: the props, each with
 *   its box outlined in red (ink outside it is a box too small).
 * - ProcessCastPropPreview: an agent's own props, the same way, for the
 *   render_style_props tool (character-tools/render-props.mjs).
 *
 * Drawn live (one still each), never in a video, so nothing here is cached.
 */
import React from "react";
import { AbsoluteFill, useCurrentFrame } from "remotion";
import { useStyleFonts } from "../characterKit/fonts";
import { Actor, type ActorLook } from "./actor";
import { ACCESSORIES, BODIES, FACES, PROPS, STATIONS, TINTS, type PCCustomProp, type PropId, type Tint } from "./contract";
import { FONTS } from "./fonts";
import { INK, MONO, PAPER } from "./ink";
import { PROP_DRAWINGS } from "./props";
import { FURNITURE, GroundStrip, Sign } from "./stations";

type PropDrawing = React.FC<{ text: string }>;
const RED = "#E0262B";
export const SHEET_PAGES = 3;

const base: ActorLook = {
  body: "bean", tint: "teal", units: 1, accessory: "none", face: "neutral", blink: false, look: 0, silhouette: false, holding: false, seed: 7,
};

const Label: React.FC<{ x: number; y: number; children: React.ReactNode; size?: number }> = ({ x, y, children, size = 24 }) => (
  <text x={x} y={y} textAnchor="middle" fontFamily={MONO} fontWeight={700} fontSize={size} fill={INK}>{children}</text>
);

const CastPage: React.FC = () => {
  const tints = Object.keys(TINTS) as Tint[];
  return (
    <svg width={1080} height={1920}>
      <Label x={540} y={70} size={34}>process cast: bodies, tints, faces</Label>
      {BODIES.filter((b) => b !== "units").map((b, i) => (
        <g key={b} transform={`translate(${150 + i * 260} 420) scale(0.8)`}>
          <Actor {...base} body={b} tint={tints[i % tints.length]} accessory={ACCESSORIES[i + 1] ?? "none"} />
          <Label x={0} y={50}>{`${b} · ${ACCESSORIES[i + 1] ?? "none"}`}</Label>
        </g>
      ))}
      {FACES.map((f, i) => (
        <g key={f} transform={`translate(${90 + i * 150} 760) scale(0.55)`}>
          <Actor {...base} face={f} tint={tints[(i + 1) % tints.length]} />
          <Label x={0} y={60} size={40}>{f}</Label>
        </g>
      ))}
      {[1, 4, 8, 16].map((n, i) => (
        <g key={n} transform={`translate(${170 + i * 250} 1140) scale(0.85)`}>
          <Actor {...base} body="units" units={n} tint={i % 2 ? "olive" : "teal"} face="happy" />
          <Label x={0} y={44}>{`units ${n}`}</Label>
        </g>
      ))}
      <g transform="translate(230 1480) scale(0.85)">
        <Actor {...base} silhouette />
        <Label x={0} y={44}>clone flash</Label>
      </g>
      <g transform="translate(540 1480) scale(0.85)">
        <Actor {...base} holding face="proud" tint="coral" />
        <Label x={0} y={44}>holding a card</Label>
      </g>
      <g transform="translate(850 1480) scale(0.85)">
        <Actor {...base} blink look={1} tint="sky" body="blob" />
        <Label x={0} y={44}>blink, looking right</Label>
      </g>
      {tints.map((t, i) => (
        <g key={t} transform={`translate(${110 + i * 145} 1800) scale(0.4)`}>
          <Actor {...base} tint={t} body="gem" />
          <Label x={0} y={70} size={48}>{t}</Label>
        </g>
      ))}
    </svg>
  );
};

const StationPage: React.FC = () => {
  const kinds = (Object.keys(STATIONS) as (keyof typeof STATIONS)[]).filter((k) => k !== "stage");
  return (
    <svg width={1080} height={1920}>
      <Label x={540} y={70} size={34}>stations: furniture, sign, ground</Label>
      {kinds.map((k, i) => {
        const x = 280 + (i % 2) * 520, y = 520 + Math.floor(i / 2) * 420;
        const F = FURNITURE[k as keyof typeof FURNITURE];
        const s = STATIONS[k];
        return (
          <g key={k}>
            <g transform={`translate(${x} ${y}) scale(0.48)`}><GroundStrip seed={i * 7 + 3} /></g>
            <g transform={`translate(${x} ${y}) scale(0.8)`}>
              <F seed={i * 11 + 5} />
              <rect x={-s.w / 2} y={-s.h} width={s.w} height={s.h} fill="none" stroke={RED} strokeWidth={2.5} />
            </g>
            <Label x={x} y={y + 50}>{`${k} · top ${s.top}`}</Label>
          </g>
        );
      })}
      <g transform="translate(540 1830) scale(0.7)"><Sign text="EXAMPLE.COM" seed={4} /></g>
    </svg>
  );
};

const PropGrid: React.FC<{ items: { id: string; Draw: PropDrawing; w: number; h: number; text: string }[]; title: string }> = ({ items, title }) => (
  <svg width={1080} height={1920}>
    <Label x={540} y={70} size={34}>{title}</Label>
    {items.map((it, i) => {
      const cx = 140 + (i % 4) * 267, cy = 230 + Math.floor(i / 4) * 290;
      const k = Math.min(1, 200 / it.w, 200 / it.h);
      return (
        <g key={it.id}>
          <g transform={`translate(${cx} ${cy}) scale(${k})`}>
            <it.Draw text={it.text} />
            <rect x={-it.w / 2} y={-it.h / 2} width={it.w} height={it.h} fill="none" stroke={RED} strokeWidth={2.5 / k} />
          </g>
          <Label x={cx} y={cy + 130}>{`${it.id} ${it.w}x${it.h}`}</Label>
        </g>
      );
    })}
  </svg>
);

const SAMPLE: Partial<Record<PropId, string>> = {
  card: "A = 01000001", envelope: "TO: SERVER", packet: "GET /", box: "SHIPPED", file: "index.html", folder: "/home",
  phone: "LOGIN", laptop: "localhost",
};

export const ProcessCastSheet: React.FC = () => {
  const page = useCurrentFrame();
  useStyleFonts("ProcessCastSheet", FONTS);
  const items = (Object.keys(PROPS) as PropId[]).map((id) => ({ id, Draw: PROP_DRAWINGS[id], w: PROPS[id].w, h: PROPS[id].h, text: SAMPLE[id] ?? "" }));
  return (
    <AbsoluteFill style={{ background: PAPER }}>
      {page === 0 ? <CastPage /> : page === 1 ? <StationPage /> : <PropGrid items={items} title="props · red: the declared box" />}
    </AbsoluteFill>
  );
};

export type PreviewSpec = PCCustomProp & { sample?: string };

/** An agent's own props: each with its box outlined, a library card for scale. */
export const ProcessCastPropPreview: React.FC<{ specs: PreviewSpec[]; drawings: Record<string, PropDrawing> }> = ({ specs, drawings }) => {
  useStyleFonts("ProcessCastPropPreview", FONTS);
  const items = specs.map((s) => ({
    id: s.id, Draw: drawings[s.id] ?? (() => <text fill={RED} fontSize={30}>no drawing loaded</text>), w: s.w, h: s.h,
    text: s.text ? s.sample || "SAMPLE" : "",
  }));
  return (
    <AbsoluteFill style={{ background: PAPER }}>
      <PropGrid items={[...items, { id: "library card", Draw: PROP_DRAWINGS.card, w: PROPS.card.w, h: PROPS.card.h, text: "A = 01000001" }]} title="this video's props" />
    </AbsoluteFill>
  );
};
