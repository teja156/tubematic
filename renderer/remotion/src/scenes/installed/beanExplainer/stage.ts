/*
 * What is on stage at a frame: a pure function of the data, so the scene, the
 * prop sheet and the tests read the same answer.
 *
 * A shot is a cut. Inside a shot nothing leaves: every event up to the frame
 * is on stage (the additive build), and the next shot starts empty. A section
 * is a run of shots under one header and badge; with `list` on, each section
 * after the first opens with the badge carousel.
 */
import {
  BADGE, GEOMETRY, H, TIMING, W, beanScale, propInstanceId,
  type BECast, type BEEvent, type BESection, type BEShot, type BeanExplainerData, type CastId, type Face, type Look,
  type MarkType, type Pose,
} from "./contract";

export type Window = { start: number; end: number };

export type BeanState = {
  id: CastId;
  cast: BECast;
  x: number; // frame pixels, after any hop
  hopY: number;
  pose: Pose; prevPose: Pose; poseT: number; swapFrame: number; poseAt: number;
  face: Face; look: Look;
  enter: number;
  aimAt: string | undefined;
  marks: { type: MarkType; start: number }[];
  scale: number;
  seed: number;
};

export type PropState = { key: string; prop: string; x: number; y: number; scale: number; since: number; enter: string; text: string; act: string; actAt: number };
export type LabelState = { key: string; text: string; x: number; y: number; red: boolean; since: number };
export type StrikeState = { target: string; since: number };
export type ArrowState = { from: string; to: string; since: number };

export type StageState = {
  shot: number; section: number;
  shotWindow: Window;
  carousel: { from: number; to: number; t: number } | null;
  beans: BeanState[];
  props: PropState[];
  labels: LabelState[];
  strikes: StrikeState[];
  arrows: ArrowState[];
  impacts: { frame: number; strength: number }[];
};

export const ease = {
  outBack: (t: number) => 1 + 2.2 * (t - 1) ** 3 + 1.2 * (t - 1) ** 2,
  inOut: (t: number) => (t < 0.5 ? 4 * t * t * t : 1 - (-2 * t + 2) ** 3 / 2),
  out: (t: number) => 1 - (1 - t) ** 3,
};
export const clamp01 = (v: number) => Math.max(0, Math.min(1, v));

/** A spring value that is exactly 1 from TIMING.settle frames on, so a settled element stops changing. */
export const settled = (value: number, t: number) => (t >= TIMING.settle ? 1 : value);

export function shotWindows(data: BeanExplainerData, total: number): Window[] {
  return data.shots.map((s, i) => ({ start: s.start, end: i + 1 < data.shots.length ? data.shots[i + 1].start : total }));
}

const indexAt = (starts: number[], frame: number) => {
  let i = -1;
  for (let k = 0; k < starts.length; k++) if (starts[k] <= frame) i = k;
  return i;
};

/** The frame a section's content may start: after the carousel when it plays. */
export const sectionContentStart = (data: BeanExplainerData, i: number) =>
  data.sections[i].start + (data.list && i > 0 ? TIMING.carousel : 0);

function castOf(data: BeanExplainerData, id: CastId): BECast {
  return data.cast.find((c) => c.id === id) ?? { id };
}

export function stageAt(data: BeanExplainerData, total: number, frame: number): StageState | null {
  const windows = shotWindows(data, total);
  const shot = indexAt(windows.map((w) => w.start), frame);
  if (shot < 0) return null;
  const section = indexAt(data.sections.map((s) => s.start), frame);
  const win = windows[shot];
  const events: BEEvent[] = (data.shots[shot] as BEShot).events.filter((e) => e.frame <= frame);

  let carousel: StageState["carousel"] = null;
  if (data.list && section > 0) {
    const t = frame - data.sections[section].start;
    if (t < TIMING.carousel) carousel = { from: section - 1, to: section, t };
  }

  // beans: the ones with a pose in this shot so far
  const beanIds = Array.from(new Set((data.shots[shot] as BEShot).events.filter((e) => e.type === "pose").map((e) => (e as { who: CastId }).who)));
  const scale = beanScale(beanIds.length);
  const beans: BeanState[] = [];
  beanIds.forEach((id, n) => {
    const poses = events.filter((e): e is Extract<BEEvent, { type: "pose" }> => e.type === "pose" && e.who === id);
    if (!poses.length) return;
    const cur = poses[poses.length - 1];
    const prev = poses.length > 1 ? poses[poses.length - 2] : cur;
    const xs = poses.filter((p) => p.x !== undefined);
    const xNow = (xs.length ? xs[xs.length - 1].x! : 0.5) * W;
    const xBefore = (xs.length > 1 ? xs[xs.length - 2].x! : xs.length ? xs[0].x! : 0.5) * W;
    const moved = cur.x !== undefined && poses.length > 1 && xBefore !== xNow;
    const hopT = moved ? clamp01((frame - cur.frame) / 8) : 1;
    const x = moved ? xBefore + (xNow - xBefore) * ease.inOut(hopT) : xNow;
    const hopY = moved && hopT < 1 ? -Math.sin(hopT * Math.PI) * 40 : 0;
    const first = poses[0].frame;
    const enterT = clamp01((frame - first) / 8);
    const enter = first <= win.start + 2 ? 1 : ease.outBack(enterT);
    const marks = events
      .filter((e): e is Extract<BEEvent, { type: "mark" }> => e.type === "mark" && e.who === id && e.frame >= cur.frame)
      .map((e) => ({ type: e.mark, start: e.frame }));
    beans.push({
      id, cast: castOf(data, id), x, hopY,
      pose: cur.pose, prevPose: prev.pose,
      poseT: poses.length === 1 ? 1 : clamp01((frame - cur.frame) / TIMING.poseSnap),
      swapFrame: poses.length === 1 ? -100 : cur.frame, poseAt: cur.frame,
      face: cur.face, look: cur.look ?? "front", enter, aimAt: cur.at, marks, scale, seed: n * 7 + shot * 13 + 3,
    });
  });

  const props: PropState[] = [];
  const acts = events.filter((e): e is Extract<BEEvent, { type: "act" }> => e.type === "act");
  for (const e of events) {
    if (e.type !== "prop") continue;
    const key = propInstanceId(e);
    const mine = acts.filter((a) => a.target === key);
    const last = mine[mine.length - 1];
    props.push({
      key, prop: e.prop, x: e.x * W, y: e.y * H, scale: e.scale ?? 1, since: e.frame, enter: e.enter ?? "pop",
      text: e.text ?? "", act: last?.act ?? "", actAt: last?.frame ?? -1,
    });
  }
  const labels: LabelState[] = events
    .filter((e): e is Extract<BEEvent, { type: "label" }> => e.type === "label")
    .map((e, i) => ({ key: `l${i}`, text: e.text, x: e.x * W, y: e.y * H, red: e.tone === "red", since: e.frame }));
  const strikes = events.filter((e): e is Extract<BEEvent, { type: "strike" }> => e.type === "strike").map((e) => ({ target: e.target, since: e.frame }));
  const arrows = events.filter((e): e is Extract<BEEvent, { type: "arrow" }> => e.type === "arrow").map((e) => ({ from: e.from, to: e.to, since: e.frame }));
  const impacts = events.filter((e): e is Extract<BEEvent, { type: "impact" }> => e.type === "impact").map((e) => ({ frame: e.frame, strength: e.strength ?? 2 }));

  return { shot, section, shotWindow: win, carousel, beans, props, labels, strikes, arrows, impacts };
}

/** Camera kick from the impacts: a decaying shake and a small zoom pulse (about 6 frames). */
export function kickAt(impacts: { frame: number; strength: number }[], frame: number, fps: number) {
  let x = 0, y = 0, z = 0;
  for (const im of impacts) {
    const d = (frame - im.frame) / fps;
    if (d < 0 || d > 0.19) continue;
    const env = (1 - d / 0.19) ** 2;
    const mag = 6 + 6 * im.strength;
    x += Math.sin(d * 104) * mag * env;
    y += Math.cos(d * 92) * mag * 0.55 * env;
    z += (0.03 + 0.007 * im.strength) * env;
  }
  return { x, y, z };
}

/** The point an arrow or a pointing hand aims at: a prop's centre or a bean's head. */
export function anchorOf(state: StageState, key: string): [number, number] | null {
  const p = state.props.find((q) => q.key === key);
  if (p) return [p.x, p.y];
  const b = state.beans.find((q) => q.id === key);
  if (b) return [b.x, GEOMETRY.floorY - GEOMETRY.beanHeight * b.scale * 0.72];
  return null;
}

export const BADGE_SLOT = BADGE;
export const STRIP = { y: 900, gap: 420, big: 160 } as const;
export type { BESection };
