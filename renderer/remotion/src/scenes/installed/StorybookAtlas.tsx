/*
 * StorybookAtlas: the whole of a Storybook Atlas video, as one scene.
 *
 * A vintage picture book told in 3 to 5 chapters. Each chapter opens with a
 * plaque (numeral, title, byline, wax seal) over a backdrop; a small mouse
 * guide walks beside the story while flat picture-book people and hatched
 * props arrive on the narrator's words, and plates (constellation lettering,
 * a sprung gauge, an ink-dot morph) open over the stage behind brass shutters.
 * Chapters change by a push through a door or porthole into white, or a
 * hatched diagonal wipe. The agent never writes this file's kind of code: it
 * writes `props.storybookAtlas` (chapters and events timed to the narration,
 * props from a fixed library or drawn for the video), which the MCP server
 * validates against ./storybookAtlas/contract.ts before the video can render.
 *
 * Kept cheap on the CPU renderer (software GL), measured in CPU-seconds per
 * frame (see the measurements below):
 * - Every drawing (backdrop, prop state, look of the guide or a person) is a
 *   bitmap drawn once (./storybookAtlas/bitmap.tsx); a frame only moves,
 *   scales and fades bitmaps.
 * - The backdrop is the one full-frame picture: a canvas painted once, with
 *   the book's frame drawn into it. Each extra full-frame textured layer cost
 *   about 0.13 per frame; noise grain over the hatching cost 0.18 by itself,
 *   so there is none.
 * - Plates repaint their canvas only while something on them moves.
 * - No live SVG filter, gradient, pattern or stroke-dasharray.
 */
import React, { useEffect, useState } from "react";
import { AbsoluteFill, cancelRender, continueRender, delayRender, useCurrentFrame } from "remotion";
import { Bitmap, CanvasBitmap, type Drawing } from "./storybookAtlas/bitmap";
import { backdropDrawing } from "./storybookAtlas/backdrops";
import { PROPS, STAGE, TIMING, W, H, wrapTitle, type CastMember, type Chapter, type CustomProp, type PropSpec, type StorybookAtlasData } from "./storybookAtlas/contract";
import { PERSON_BOX, personDrawing, type PersonPose } from "./storybookAtlas/figure";
import { NUMERALS, Plaque } from "./storybookAtlas/frame";
import { useStorybookFonts } from "./storybookAtlas/fonts";
import { GUIDE_BOX, guideDrawing, type GuidePose } from "./storybookAtlas/guide";
import { BEIGE, INK, IVORY, SERIF, STARGOLD, TEXT } from "./storybookAtlas/palette";
import { Constellation, Gauge, Morph, Plate } from "./storybookAtlas/plates";
import { PROPS as DRAWINGS } from "./storybookAtlas/props";
import { propDrawing } from "./storybookAtlas/props/draw";
import type { PropDrawing, PropEntry } from "./storybookAtlas/props/types";
import {
  actMotion, actorAt, chapterIndexAt, clamp01, ease, movesOf, plateAt, portalOf, propsAt, transitionAt,
  type ActorState, type PropState,
} from "./storybookAtlas/stage";

// ── the kit: library props plus the video's own ─────────────────────────────
type Kit = { specs: Record<string, PropSpec>; drawing: (prop: string, state: number) => Drawing | null };

function makeKit(custom: CustomProp[], draws: Record<string, PropDrawing>): Kit {
  const specs: Record<string, PropSpec> = { ...PROPS };
  const entries: Record<string, PropEntry> = {};
  for (const id of Object.keys(PROPS)) {
    const d = DRAWINGS[id];
    if (d) entries[id] = { ...PROPS[id], label: d.label, draw: d.draw };
  }
  for (const c of custom) {
    specs[c.id] = c;
    if (draws[c.id]) entries[c.id] = { ...c, label: c.id, draw: draws[c.id] };
  }
  return { specs, drawing: (prop, state) => (entries[prop] ? propDrawing(prop, entries[prop], state) : null) };
}

function useKit(list: CustomProp[]): Kit | null {
  const [draws, setDraws] = useState<Record<string, PropDrawing> | null>(list.length ? null : {});
  const [handle] = useState(() => (list.length ? delayRender("StorybookAtlas: loading the video's own props") : null));
  useEffect(() => {
    if (handle === null) return;
    Promise.all(list.map((c) => import(`../generated/${c.src}.tsx`).then((m: { default: PropDrawing }) => [c.id, m.default] as const)))
      .then((pairs) => {
        setDraws(Object.fromEntries(pairs));
        continueRender(handle);
      })
      .catch((err) => cancelRender(err));
    // The props are static for the whole render.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [handle]);
  return draws === null ? null : makeKit(list, draws);
}

// ── pieces on stage ──────────────────────────────────────────────────────────
const GLOW: Drawing = {
  key: "glow",
  width: 300,
  height: 300,
  render: () => (
    <g>
      <defs>
        <radialGradient id="g" cx="50%" cy="50%" r="50%">
          <stop offset="0%" stopColor={STARGOLD} stopOpacity={0.9} />
          <stop offset="55%" stopColor={STARGOLD} stopOpacity={0.35} />
          <stop offset="100%" stopColor={STARGOLD} stopOpacity={0} />
        </radialGradient>
      </defs>
      <circle cx={150} cy={150} r={150} fill="url(#g)" />
    </g>
  ),
};

function entranceOf(p: PropState, frame: number, side: number): { dx: number; dy: number; s: number; op: number } {
  const t = clamp01((frame - p.since) / TIMING.propIn);
  if (t >= 1) return { dx: 0, dy: 0, s: 1, op: 1 };
  switch (p.enter) {
    case "drop":
      return { dx: 0, dy: -700 * (1 - ease.out(t)) - 10 * Math.sin(t * Math.PI), s: 1, op: 1 };
    case "slide":
      return { dx: side * 700 * (1 - ease.out(t)), dy: 0, s: 1, op: 1 };
    case "rise":
      return { dx: 0, dy: 60 * (1 - ease.out(t)), s: 1, op: t };
    case "fade":
      return { dx: 0, dy: 0, s: 1, op: t };
    default: {
      const k = t < 0.7 ? ease.out(t / 0.7) * 1.08 : 1.08 - 0.08 * ((t - 0.7) / 0.3);
      return { dx: 0, dy: 0, s: k, op: 1 };
    }
  }
}

const PropView: React.FC<{ p: PropState; kit: Kit; frame: number }> = ({ p, kit, frame }) => {
  const spec = kit.specs[p.prop];
  const d = kit.drawing(p.prop, p.state);
  if (!spec || !d) return null;
  const [w, h] = spec.box;
  const left = p.x - w / 2, top = p.y - h;
  const en = entranceOf(p, frame, p.x < W / 2 ? -1 : 1);
  const m = p.motion ? actMotion(p.motion.act, p.motion.t) : { dx: 0, dy: 0, rot: 0, s: 1, pivot: "base" as const };
  const origin: [number, number] = m.pivot === "centre" ? [w / 2, h / 2] : m.pivot === "top" ? [w / 2, 0] : [w / 2, h];
  const parts = [`translate(${(en.dx + m.dx).toFixed(1)}px, ${(en.dy + m.dy).toFixed(1)}px)`];
  // scale about the base, then the act's rotation about its own pivot
  const s = p.scale * en.s * m.s;
  if (s !== 1) parts.push(`translate(${w / 2 - origin[0]}px, ${h - origin[1]}px) scale(${s}) translate(${origin[0] - w / 2}px, ${origin[1] - h}px)`);
  if (m.rot) parts.push(`rotate(${m.rot.toFixed(2)}deg)`);
  const still = parts.length === 1 && en.dx + m.dx === 0 && en.dy + m.dy === 0;
  const transform = still ? undefined : parts.join(" ");
  const from = p.from !== null ? kit.drawing(p.prop, p.from) : null;
  const glowSize = Math.max(w, h) * p.scale * 1.5;
  return (
    <>
      {p.glow > 0 && (
        <Bitmap d={GLOW} left={p.x - 150} top={p.y - (h * p.scale) / 2 - 150} transform={`scale(${glowSize / 300})`} origin={[150, 150]} opacity={p.glow * 0.85} />
      )}
      {from && <Bitmap d={from} left={left} top={top} transform={transform} origin={origin} opacity={(1 - p.fade) * en.op} />}
      <Bitmap d={d} left={left} top={top} transform={transform} origin={origin} opacity={en.op * (from ? p.fade : 1)} />
    </>
  );
};

const GUIDE_WALK: GuidePose[] = ["walk1", "walk2", "walk3", "walk4"];
const PERSON_WALK: PersonPose[] = ["walk1", "walk2"];
const HOP_FRAMES = 16;

const GuideView: React.FC<{ a: ActorState; coat: StorybookAtlasData["guide"]["coat"]; frame: number }> = ({ a, coat, frame }) => {
  if (!a.visible) return null;
  let pose = (a.walking ? GUIDE_WALK[a.step % 4] : a.pose) as GuidePose;
  let dy = 0;
  if (!a.walking && pose === "hop") {
    const u = (frame - a.posedAt) / HOP_FRAMES;
    if (u >= 1) pose = "stand";
    else dy = -46 * Math.sin(Math.PI * clamp01(u));
  }
  const flip = a.facing === "left";
  const transform = flip || dy ? `translateY(${dy}px)${flip ? " scaleX(-1)" : ""}` : undefined;
  return (
    <Bitmap d={guideDrawing(pose, coat)} left={a.x - GUIDE_BOX.footX} top={STAGE.floor - GUIDE_BOX.footY}
      transform={transform} origin={[GUIDE_BOX.footX, GUIDE_BOX.footY]} />
  );
};

const PersonView: React.FC<{ a: ActorState; who: CastMember }> = ({ a, who }) => {
  if (!a.visible) return null;
  const pose = (a.walking ? PERSON_WALK[a.step % 2] : a.pose) as PersonPose;
  return (
    <Bitmap d={personDrawing(who, pose)} left={a.x - PERSON_BOX.footX} top={STAGE.floor - PERSON_BOX.footY}
      transform={a.facing === "left" ? "scaleX(-1)" : undefined} origin={[PERSON_BOX.footX, PERSON_BOX.footY]} />
  );
};

/** A small printed tag under whatever it names (a museum label): centred on x, its top at y. */
export const Tag: React.FC<{ x: number; y: number; text: string; op?: number }> = ({ x, y, text, op = 1 }) => (
  <div style={{ position: "absolute", left: x - 300, top: y, width: 600, display: "flex", justifyContent: "center", opacity: op }}>
    <div style={{ background: IVORY, color: TEXT, fontFamily: SERIF, fontStyle: "italic", fontSize: 32, lineHeight: 1.1,
      padding: "4px 14px 6px", border: `1.5px solid ${INK}`, whiteSpace: "nowrap" }}>{text}</div>
  </div>
);

/** Everything in one chapter at `frame`. */
const ChapterView: React.FC<{ data: StorybookAtlasData; i: number; frame: number; kit: Kit; cast: Map<string, CastMember> }> = ({
  data, i, frame, kit, cast,
}) => {
  const c = data.chapters[i];
  const moves = movesOf(c.events);
  const guide = actorAt(moves.guide, frame, STAGE.guideHome);
  const props = propsAt(c.events, frame, kit.specs);
  const wall = props.filter((p) => kit.specs[p.prop]?.place === "wall");
  const floor = props.filter((p) => kit.specs[p.prop]?.place !== "wall");
  const people = [...moves.people.entries()].map(([id, m]) => ({ id, a: actorAt(m, frame, null) }));
  // tags: a person's name while it stands still, and every tag event so far
  const tags: { key: string; x: number; y: number; text: string; op: number }[] = [];
  for (const { id, a } of people) {
    const who = cast.get(id);
    if (who && a.visible && !a.walking) tags.push({ key: `n-${id}`, x: a.x, y: STAGE.floor + 14, text: who.name, op: 1 });
  }
  for (const e of c.events) {
    if (e.type !== "tag" || e.at > frame) continue;
    const p = props.find((q) => q.id === e.on);
    const op = clamp01((frame - e.at) / TIMING.tagIn);
    if (p) {
      const spec = kit.specs[p.prop];
      tags.push({ key: `t-${e.at}`, x: p.x, y: spec.place === "wall" ? p.y + 12 : STAGE.floor + 14, text: e.text, op });
    }
  }
  const title = wrapTitle(c.title).join("\n");
  return (
    <AbsoluteFill>
      <CanvasBitmap d={backdropDrawing(c.backdrop)} />
      {wall.map((p) => <PropView key={p.id} p={p} kit={kit} frame={frame} />)}
      {floor.map((p) => <PropView key={p.id} p={p} kit={kit} frame={frame} />)}
      {people.map(({ id, a }) => {
        const who = cast.get(id);
        return who ? <PersonView key={id} a={a} who={who} /> : null;
      })}
      <GuideView a={guide} coat={data.guide.coat} frame={frame} />
      {tags.map((t) => <Tag key={t.key} x={t.x} y={t.y} text={t.text} op={t.op} />)}
      <Plaque t={frame - c.start} numeral={NUMERALS[i]} title={title} byline={c.byline} />
    </AbsoluteFill>
  );
};

/** The camera for a push: scale towards the portal and bring it to the centre of the frame. */
function pushTransform(c: Chapter, kit: Kit, t: number): { transform: string; origin: string } | null {
  const portal = portalOf(c, kit.specs);
  if (!portal) return null;
  const spec = kit.specs[portal.prop];
  const s = portal.scale ?? 1;
  const base = spec.place === "floor" ? STAGE.floor : portal.y ?? 900;
  const px = portal.x + (spec.portal?.[0] ?? 0) * s, py = base + (spec.portal?.[1] ?? 0) * s;
  const e = ease.in(t);
  const k = 1 + (TIMING.pushScale - 1) * e;
  return { transform: `translate(${((W / 2 - px) * e).toFixed(1)}px, ${((H / 2 - py) * e).toFixed(1)}px) scale(${k.toFixed(3)})`, origin: `${px}px ${py}px` };
}

/** The hatched band of a wipe, its leading edge at p (px along the top edge). */
const WipeBand: React.FC<{ p: number }> = ({ p }) => {
  const band = 80, slope = 0.5 * H;
  return (
    <svg width={W} height={H} style={{ position: "absolute", inset: 0 }}>
      <path d={`M${p - band} 0L${p} 0L${p - slope} ${H}L${p - slope - band} ${H}Z`} fill={BEIGE} stroke={INK} strokeWidth={3} />
      {Array.from({ length: 6 }, (_, k) => {
        const o = (k + 1) * (band / 7);
        return <path key={k} d={`M${p - o} 0L${p - o - slope} ${H}`} stroke={INK} strokeWidth={2} opacity={0.5} />;
      })}
    </svg>
  );
};

export default function StorybookAtlas({ storybookAtlas }: { storybookAtlas?: StorybookAtlasData }) {
  const frame = useCurrentFrame();
  useStorybookFonts("StorybookAtlas");
  const data = storybookAtlas;
  const kit = useKit(data?.customProps ?? []);
  if (!data || !kit || data.chapters.length === 0) return <AbsoluteFill style={{ background: IVORY }} />;
  const cast = new Map(data.cast.map((m) => [m.id, m]));
  const i = chapterIndexAt(data.chapters, frame);
  const tr = transitionAt(data, frame);

  let body: React.ReactNode;
  if (tr?.kind === "push") {
    const cam = pushTransform(data.chapters[tr.from], kit, tr.t);
    const white = clamp01((tr.t - 0.55) / 0.45);
    body = (
      <>
        <AbsoluteFill style={cam ? { transform: cam.transform, transformOrigin: cam.origin } : undefined}>
          <ChapterView data={data} i={tr.from} frame={frame} kit={kit} cast={cast} />
        </AbsoluteFill>
        {white > 0 && <AbsoluteFill style={{ background: "#FFFDF6", opacity: white }} />}
      </>
    );
  } else if (tr?.kind === "wipe") {
    const p = ease.in(tr.t) * (W + 0.5 * H + 80);
    const slope = 0.5 * H;
    body = (
      <>
        <ChapterView data={data} i={tr.from} frame={frame} kit={kit} cast={cast} />
        <AbsoluteFill style={{ clipPath: `polygon(0 0, ${p}px 0, ${p - slope}px ${H}px, 0 ${H}px)` }}>
          <ChapterView data={data} i={tr.to} frame={frame} kit={kit} cast={cast} />
        </AbsoluteFill>
        <WipeBand p={p} />
      </>
    );
  } else {
    const plate = plateAt(data.chapters[i].events, frame);
    body = (
      <>
        <ChapterView data={data} i={i} frame={frame} kit={kit} cast={cast} />
        {plate && (
          <Plate kind={plate.e.type} open={plate.open}>
            {plate.e.type === "constellation" && <Constellation e={plate.e} frame={frame} />}
            {plate.e.type === "gauge" && <Gauge e={plate.e} frame={frame} />}
            {plate.e.type === "morph" && (
              <Morph e={plate.e} frame={frame} drawing={plate.e.prop ? kit.drawing(plate.e.prop, 0) : null} spec={plate.e.prop ? kit.specs[plate.e.prop] ?? null : null} />
            )}
          </Plate>
        )}
        {tr?.kind === "white" && <AbsoluteFill style={{ background: "#FFFDF6", opacity: 1 - tr.t }} />}
      </>
    );
  }
  return <AbsoluteFill style={{ background: IVORY }}>{body}</AbsoluteFill>;
}
