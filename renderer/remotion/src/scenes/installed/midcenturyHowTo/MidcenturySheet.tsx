/*
 * Sheets of the Mid-century How-To library, for a person to approve the look
 * and for an agent's own props to be compared against:
 * - MidcenturySheet, one page per frame. Page 0: the presenter in every pose (top) and every face (bottom).
 * - pages 1-3: the objects, each at rest and at the end of its first act, its
 *   OBJECTS box outlined in red (ink outside it is a box too small).
 * - MidcenturyPropPreview: an agent's own props, the same way, for the
 *   render_style_props tool (character-tools/render-props.mjs).
 *
 * Drawn live (one still each), never in a video, so nothing here is cached.
 */
import React from "react";
import { AbsoluteFill, useCurrentFrame } from "remotion";
import { useStyleFonts } from "../characterKit/fonts";
import { FONTS } from "./fonts";
import { CORAL, INK, JOST, PAPER, type ObjectDrawProps } from "./cel";
import { FACES, GROUNDS, OBJECTS, POSES, type MCCustomProp, type ObjectId } from "./contract";
import { DRAWINGS } from "./objects";
import { Presenter, poseArm } from "./presenter";

type Drawing = React.FC<ObjectDrawProps>;
const RED = "#E0262B";

const SAMPLE_TEXT: Partial<Record<ObjectId, string>> = {
  phone: "Settings|Profile|Security|Privacy", laptop: "Backup|Photos|Files", window: "Sign in|Email|Password",
  keypad: "481297", password: "hunter2!", button: "START", app: "Vault", envelope: "To: you", document: "Terms of use, page 1",
  checklist: "Update|Back up|Restart|Check", card: "4321 •••• 8765", sign: "WAIT HERE", calendar: "MON",
};

export const SHEET_PAGES = 4;
const PER_PAGE = 10;

const Cell: React.FC<{ Draw: Drawing; w: number; h: number; text: string; act: string; cx: number; cy: number; k: number }> = ({ Draw, w, h, text, act, cx, cy, k }) => (
  <g>
    <g transform={`translate(${cx} ${cy}) scale(${k})`}>
      <Draw phase={0} act={act} actT={act ? 40 : -1} text={text} />
    </g>
    <rect x={cx - (w * k) / 2} y={cy - (h * k) / 2} width={w * k} height={h * k} fill="none" stroke={RED} strokeWidth={2.5} />
  </g>
);

const ObjectGrid: React.FC<{ items: { id: string; Draw: Drawing; w: number; h: number; text: string; acts: readonly string[] }[]; title: string }> = ({ items, title }) => (
  <svg width={1080} height={1920}>
    <text x={40} y={80} fontFamily={JOST} fontWeight={600} fontSize={44} fill={INK}>{title}</text>
    <text x={40} y={124} fontFamily={JOST} fontSize={26} fill={INK}>left: at rest · right: after its first act · red: the declared box</text>
    {items.map((it, i) => {
      const y0 = 160 + i * 172;
      const k = Math.min(0.62, 150 / it.h, 230 / it.w);
      const act = it.acts[0] ?? "";
      return (
        <g key={it.id}>
          <line x1={30} x2={1050} y1={y0 + 166} y2={y0 + 166} stroke={INK} strokeOpacity={0.15} />
          <text x={40} y={y0 + 90} fontFamily={JOST} fontWeight={600} fontSize={30} fill={INK}>{it.id}</text>
          <text x={40} y={y0 + 126} fontFamily={JOST} fontSize={22} fill={INK}>{`${it.w}x${it.h} · ${it.acts.join(", ") || "no acts"}`}</text>
          <Cell Draw={it.Draw} w={it.w} h={it.h} text={it.text} act="" cx={520} cy={y0 + 84} k={k} />
          {act && <Cell Draw={it.Draw} w={it.w} h={it.h} text={it.text} act={act} cx={850} cy={y0 + 84} k={k} />}
        </g>
      );
    })}
  </svg>
);

const PresenterPage: React.FC = () => (
  <svg width={1080} height={1920}>
    <text x={40} y={80} fontFamily={JOST} fontWeight={600} fontSize={44} fill={INK}>presenter: poses (aimed at the red dot) and faces</text>
    {[0, 1].map((r) => <circle key={r} cx={1040} cy={330 + r * 520} r={10} fill={RED} />)}
    {POSES.map((pose, i) => {
      const x = 130 + (i % 4) * 250, y = 760 + Math.floor(i / 4) * 520;
      const aim: [number, number] = [(1040 - x) / 0.52, (330 + Math.floor(i / 4) * 520 - y) / 0.52];
      const { arm, back } = poseArm(pose, aim, 4);
      return (
        <g key={pose} transform={`translate(${x} ${y}) scale(0.52)`}>
          <Presenter arm={arm} back={back} face="smile" blink={false} look={[3, 0]} outfit="coral" hair="dark" phase={0} />
          <text x={0} y={70} textAnchor="middle" fontFamily={JOST} fontWeight={600} fontSize={52} fill={INK}>{pose}</text>
        </g>
      );
    })}
    {FACES.map((face, i) => {
      const x = 95 + i * 178;
      return (
        <g key={face}>
          <text x={x} y={1500} textAnchor="middle" fontFamily={JOST} fontWeight={600} fontSize={28} fill={INK}>{face}</text>
          <g transform={`translate(${x - 20} 1640) translate(0 714)`}>
            <Presenter {...poseArm("stand", null)} face={face} blink={false} look={[3, 0]} outfit={(["coral", "teal", "mustard", "blue"] as const)[i % 4]} hair={(["dark", "red", "blond", "grey"] as const)[i % 4]} phase={0} />
          </g>
        </g>
      );
    })}
  </svg>
);

export const MidcenturySheet: React.FC = () => {
  const page = useCurrentFrame();
  useStyleFonts("MidcenturySheet", FONTS);
  const ids = Object.keys(OBJECTS) as ObjectId[];
  const items = ids.slice((page - 1) * PER_PAGE, page * PER_PAGE).map((id) => ({
    id, Draw: DRAWINGS[id], w: OBJECTS[id].w, h: OBJECTS[id].h, text: SAMPLE_TEXT[id] ?? "", acts: OBJECTS[id].acts,
  }));
  return (
    <AbsoluteFill style={{ background: page === 0 ? PAPER : GROUNDS.blue }}>
      {page === 0 ? <PresenterPage /> : <ObjectGrid items={items} title={`objects ${page} of ${SHEET_PAGES - 1}`} />}
    </AbsoluteFill>
  );
};

export type PreviewSpec = MCCustomProp & { sample?: string };

/** An agent's own props: each at rest and after its first act, box outlined, a library phone for scale. */
export const MidcenturyPropPreview: React.FC<{ specs: PreviewSpec[]; drawings: Record<string, Drawing> }> = ({ specs, drawings }) => {
  useStyleFonts("MidcenturyPropPreview", FONTS);
  const items = specs.map((s) => ({
    id: s.id, Draw: drawings[s.id] ?? (() => <text fill={CORAL} fontSize={40}>no drawing loaded</text>),
    w: s.w, h: s.h, text: s.text ? s.sample || "Sample text" : "", acts: s.acts ?? [],
  }));
  return (
    <AbsoluteFill style={{ background: GROUNDS.blue }}>
      <ObjectGrid items={[...items, { id: "library phone", Draw: DRAWINGS.phone, w: OBJECTS.phone.w, h: OBJECTS.phone.h, text: SAMPLE_TEXT.phone ?? "", acts: [] }]} title="this video's props" />
    </AbsoluteFill>
  );
};
