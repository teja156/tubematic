/*
 * Sheets of the Comic Panels library, for a person to approve the look and for
 * an agent's own props to be compared against:
 * - ComicPanelsSheet, one page per frame. Page 0: the hero, the invented
 *   people's knobs and the villain, every pose and every face. Page 1: the
 *   props, each with its box outlined in red (ink outside it is a box too small).
 * - ComicPanelsPropPreview: an agent's own props, the same way, for the
 *   render_style_props tool (character-tools/render-props.mjs).
 *
 * Drawn live (one still each), never in a video, so nothing here is cached.
 */
import React from "react";
import { AbsoluteFill, useCurrentFrame } from "remotion";
import { useStyleFonts } from "../characterKit/fonts";
import { Bust, type BustLook } from "./cast";
import { FACES, HAIRS, OUTFITS, POSES, PROPS, SKINS, type PropId } from "./contract";
import { FONTS } from "./fonts";
import { COMIC, INK, PAPER } from "./ink";
import { PROP_DRAWINGS } from "./props";

type PropDrawing = React.FC<{ text: string }>;
const RED = "#E0262B";
export const SHEET_PAGES = 2;

const base: BustLook = { kind: "hero", hair: "spiky", outfit: "blue", skin: "light", pose: "stand", face: "neutral", blink: false };

const Label: React.FC<{ x: number; y: number; children: React.ReactNode; size?: number }> = ({ x, y, children, size = 24 }) => (
  <text x={x} y={y} textAnchor="middle" fontFamily={COMIC} fontWeight={700} fontSize={size} fill={INK}>{children}</text>
);

const CastPage: React.FC = () => (
  <svg width={1080} height={1920}>
    <Label x={540} y={60} size={34}>comic panels: cast, poses, faces</Label>
    {[
      { ...base, label: "hero" },
      ...HAIRS.slice(0, 3).map((h, i) => ({ ...base, kind: "person" as const, hair: h, outfit: OUTFITS[i + 1], skin: SKINS[i + 1], label: `person · ${h}` })),
      { ...base, kind: "villain" as const, face: "grin" as const, label: "villain" },
    ].map(({ label, ...l }, i) => (
      <g key={label} transform={`translate(${120 + i * 210} 420) scale(0.62)`}>
        <Bust {...l} />
        <Label x={0} y={50} size={38}>{label}</Label>
      </g>
    ))}
    {HAIRS.slice(3).map((h, i) => (
      <g key={h} transform={`translate(${200 + i * 340} 770) scale(0.62)`}>
        <Bust {...base} kind="person" hair={h} outfit={OUTFITS[(i + 4) % OUTFITS.length]} skin={SKINS[(i + 2) % SKINS.length]} />
        <Label x={0} y={50} size={38}>{`person · ${h}`}</Label>
      </g>
    ))}
    {POSES.map((p, i) => (
      <g key={p} transform={`translate(${135 + (i % 4) * 270} ${1150 + Math.floor(i / 4) * 330}) scale(0.62)`}>
        <Bust {...base} pose={p} />
        <Label x={0} y={50} size={38}>{p}</Label>
      </g>
    ))}
    {FACES.map((f, i) => (
      <g key={f} transform={`translate(${70 + i * 134} 1860) scale(0.36)`}>
        <Bust {...base} face={f} />
        <Label x={0} y={70} size={56}>{f}</Label>
      </g>
    ))}
  </svg>
);

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
  phone: "UNKNOWN", laptop: "LOGIN", inbox: "URGENT: verify now", login: "bank.example", browser: "example.com",
  monitor: "ERROR 404", money: "$500", document: "INVOICE", envelope: "TO: YOU", sign: "EXIT",
};

export const ComicPanelsSheet: React.FC = () => {
  const page = useCurrentFrame();
  useStyleFonts("ComicPanelsSheet", FONTS);
  const items = (Object.keys(PROPS) as PropId[]).map((id) => ({ id, Draw: PROP_DRAWINGS[id], w: PROPS[id].w, h: PROPS[id].h, text: SAMPLE[id] ?? "" }));
  return (
    <AbsoluteFill style={{ background: PAPER }}>
      {page === 0 ? <CastPage /> : <PropGrid items={items} title="props · red: the declared box" />}
    </AbsoluteFill>
  );
};

export type PreviewSpec = { id: string; src: string; w: number; h: number; text?: number; sample?: string };

/** An agent's own props: each with its box outlined, a library phone for scale. */
export const ComicPanelsPropPreview: React.FC<{ specs: PreviewSpec[]; drawings: Record<string, PropDrawing> }> = ({ specs, drawings }) => {
  useStyleFonts("ComicPanelsPropPreview", FONTS);
  const items = specs.map((s) => ({
    id: s.id, Draw: drawings[s.id] ?? (() => <text fill={RED} fontSize={30}>no drawing loaded</text>), w: s.w, h: s.h,
    text: s.text ? s.sample || "SAMPLE" : "",
  }));
  return (
    <AbsoluteFill style={{ background: PAPER }}>
      <PropGrid items={[...items, { id: "library phone", Draw: PROP_DRAWINGS.phone, w: PROPS.phone.w, h: PROPS.phone.h, text: "UNKNOWN" }]} title="this video's props" />
    </AbsoluteFill>
  );
};
