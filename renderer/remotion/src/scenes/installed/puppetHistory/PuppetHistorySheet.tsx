/*
 * Sheets of the Puppet History library, for a person to approve the look and
 * for an agent's own props to be compared against:
 * - PuppetHistorySheet, one page per frame. Page 0: every costume. Page 1:
 *   every pose and every face. Pages 2 to 4: the sets, four to a page. Page 5:
 *   the hand props, each with its box outlined in red (ink outside it is a box
 *   too small).
 * - PuppetHistoryPropPreview: an agent's own props, the same way, for the
 *   render_style_props tool (character-tools/render-props.mjs).
 *
 * Drawn live (one still each), never in a video, so nothing here is cached.
 */
import React from "react";
import { AbsoluteFill, useCurrentFrame } from "remotion";
import { useStyleFonts } from "../characterKit/fonts";
import { COSTUMES, FACES, POSES, PROPS, SETS, type Pose, type PropId } from "./contract";
import { COSTUME_DRAWINGS } from "./costumes";
import { FONTS } from "./fonts";
import { INK, PAPER, ROUND } from "./ink";
import { PROP_DRAWINGS } from "./props";
import { Puppet } from "./puppet";
import { SET_DRAWINGS, SetSvg } from "./sets";

type PropDrawing = React.FC<{ text: string }>;
const RED = "#E0262B";
export const SHEET_PAGES = 6;

const Label: React.FC<{ x: number; y: number; children: React.ReactNode; size?: number }> = ({ x, y, children, size = 26 }) => (
  <text x={x} y={y} textAnchor="middle" fontFamily={ROUND} fontWeight={700} fontSize={size} fill={INK}>{children}</text>
);

const CostumePage: React.FC = () => (
  <svg width={1080} height={1920}>
    <Label x={540} y={60} size={34}>puppet history: costumes</Label>
    {COSTUMES.map((c, i) => (
      <g key={c} transform={`translate(${135 + (i % 4) * 270} ${450 + Math.floor(i / 4) * 330}) scale(0.5)`}>
        {COSTUME_DRAWINGS[c] ? <Puppet costume={c} pose="stand" face="happy" blink={false} /> : <text fill={RED} fontSize={40}>missing</text>}
        <Label x={0} y={70} size={46}>{c}</Label>
      </g>
    ))}
  </svg>
);

const PosePage: React.FC = () => (
  <svg width={1080} height={1920}>
    <Label x={540} y={60} size={34}>poses and faces</Label>
    {(Object.keys(POSES) as Pose[]).map((p, i) => (
      <g key={p} transform={`translate(${135 + (i % 4) * 270} ${430 + Math.floor(i / 4) * 340}) scale(0.5)`}>
        <Puppet costume="plain" pose={p} face="stern" blink={false} />
        <Label x={0} y={70} size={46}>{p}</Label>
      </g>
    ))}
    {FACES.map((f, i) => (
      <g key={f} transform={`translate(${135 + (i % 4) * 270} ${1540 + Math.floor(i / 4) * 300}) scale(0.42)`}>
        <Puppet costume="plain" pose="stand" face={f} blink={false} />
        <Label x={0} y={80} size={54}>{f}</Label>
      </g>
    ))}
  </svg>
);

const SetPage: React.FC<{ from: number }> = ({ from }) => (
  <svg width={1080} height={1920}>
    {SETS.slice(from, from + 4).map((s, i) => (
      <g key={s} transform={`translate(${30 + (i % 2) * 530} ${40 + Math.floor(i / 2) * 950}) scale(0.47)`}>
        {SET_DRAWINGS[s] ? <SetSvg set={s} /> : <text y={200} fill={RED} fontSize={80}>missing</text>}
        <rect width={1080} height={1920} fill="none" stroke={INK} strokeWidth={4} />
        <Label x={540} y={1990} size={60}>{s}</Label>
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

const SAMPLE: Partial<Record<PropId, string>> = { scroll: "DECREE", letter: "ORDERS", flag: "HOME" };

export const PuppetHistorySheet: React.FC = () => {
  const page = useCurrentFrame();
  useStyleFonts("PuppetHistorySheet", FONTS);
  const items = (Object.keys(PROPS) as PropId[])
    .filter((id) => PROP_DRAWINGS[id])
    .map((id) => ({ id, Draw: PROP_DRAWINGS[id], w: PROPS[id].w, h: PROPS[id].h, text: SAMPLE[id] ?? "" }));
  return (
    <AbsoluteFill style={{ background: PAPER }}>
      {page === 0 ? <CostumePage /> : page === 1 ? <PosePage /> : page <= 4 ? <SetPage from={(page - 2) * 4} /> : <PropGrid items={items} title="hand props · red: the declared box" />}
    </AbsoluteFill>
  );
};

export type PreviewSpec = { id: string; src: string; w: number; h: number; text?: number; sample?: string };

/** An agent's own props: each with its box outlined, a library scroll for scale. */
export const PuppetHistoryPropPreview: React.FC<{ specs: PreviewSpec[]; drawings: Record<string, PropDrawing> }> = ({ specs, drawings }) => {
  useStyleFonts("PuppetHistoryPropPreview", FONTS);
  const items = specs.map((s) => ({
    id: s.id, Draw: drawings[s.id] ?? (() => <text fill={RED} fontSize={30}>no drawing loaded</text>), w: s.w, h: s.h,
    text: s.text ? s.sample || "SAMPLE" : "",
  }));
  return (
    <AbsoluteFill style={{ background: PAPER }}>
      <PropGrid items={[...items, { id: "library scroll", Draw: PROP_DRAWINGS.scroll, w: PROPS.scroll.w, h: PROPS.scroll.h, text: "DECREE" }]} title="this video's props" />
    </AbsoluteFill>
  );
};
