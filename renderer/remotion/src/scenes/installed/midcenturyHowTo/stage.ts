/*
 * What is on stage at a frame: a pure function of the data, so the scene, the
 * sheet and the tests read the same answer.
 *
 * The video is an optional intro (the title card, before the first step), the
 * steps, and an optional summary card at the end. A shot is a cut: inside a
 * shot nothing leaves (the build is additive), and the next shot starts empty.
 * Everything that moves steps on twos.
 */
import { clamp01, hashSeed, onTwos, type Pt } from "../characterKit/geometry";
import {
  GEOMETRY, H, TIMING, W, inReach, objectInstanceId, presenterFeetX,
  type Face, type MCEvent, type MCShot, type MidcenturyData, type Pose, type Side,
} from "./contract";

export type Window = { start: number; end: number };
export type Segment = { kind: "intro" } | { kind: "step"; index: number } | { kind: "summary" };

export type ObjectState = {
  key: string; object: string; x: number; y: number; scale: number; since: number; enter: string; text: string;
  act: string; actAt: number;
};
export type PressState = { target: string; at: number; tip: Pt; hose: boolean; from: Pt };
export type BadgeState = { target: string; since: number; kind: "check" | "cross" };
export type InsetState = { target: string; text: string; x: number; y: number; since: number };
export type LabelState = { key: string; text: string; x: number; y: number; since: number };
export type PresenterState = {
  side: Exclude<Side, "none">;
  pose: Pose; prevPose: Pose; poseT: number; poseAt: number; face: Face;
  at: string | undefined; prevAt: string | undefined;
  blink: boolean;
};

export type StageState = {
  segment: Segment;
  shot: number;
  shotWindow: Window;
  presenter: PresenterState | null;
  objects: ObjectState[];
  presses: PressState[];
  badges: BadgeState[];
  insets: InsetState[];
  labels: LabelState[];
};

const indexAt = (starts: number[], frame: number) => {
  let i = -1;
  for (let k = 0; k < starts.length; k++) if (starts[k] <= frame) i = k;
  return i;
};

export function shotWindows(data: MidcenturyData, total: number): Window[] {
  return data.shots.map((s, i) => ({ start: s.start, end: i + 1 < data.shots.length ? data.shots[i + 1].start : total }));
}

export function segmentAt(data: MidcenturyData, frame: number): Segment {
  if (data.summary !== undefined && frame >= data.summary) return { kind: "summary" };
  const step = indexAt(data.steps.map((s) => s.start), frame);
  return step < 0 ? { kind: "intro" } : { kind: "step", index: step };
}

/** Where a press lands on an object: a screen's row when a row act starts with it, a keypad's keys, else the centre. */
export function pressPoint(o: ObjectState, act: string | undefined): Pt {
  const k = o.scale;
  let dx = 0, dy = 0;
  const row = act ? /^row([1-3])$/.exec(act) : null;
  if (row) {
    const i = Number(row[1]) - 1;
    if (o.object === "phone") dy = -80 + 108 * i;
    else if (o.object === "laptop") dy = -57 + 70.5 * i;
    else if (o.object === "window") dy = -9 + 85.7 * i;
  } else if (o.object === "keypad") {
    dy = 40;
  }
  return [o.x + dx * k, o.y + dy * k];
}

/** Whether the presenter blinks at a frame: two frames every few seconds, seeded so it never lands on a beat. */
export function blinkAt(frame: number, seed: number): boolean {
  const period = 98 + (seed % 23);
  return (onTwos(frame) + (seed % period)) % period < 2;
}

export function stageAt(data: MidcenturyData, total: number, frame: number): StageState | null {
  const windows = shotWindows(data, total);
  const shot = indexAt(windows.map((w) => w.start), frame);
  if (shot < 0) return null;
  const segment = segmentAt(data, frame);
  const sh = data.shots[shot] as MCShot;
  const all = sh.events as MCEvent[];
  const events = all.filter((e) => e.frame <= frame);
  const t = onTwos(frame);

  const objects: ObjectState[] = [];
  const acts = events.filter((e): e is Extract<MCEvent, { type: "act" }> => e.type === "act");
  for (const e of events) {
    if (e.type !== "object") continue;
    const key = objectInstanceId(e);
    const mine = acts.filter((a) => a.target === key);
    const last = mine[mine.length - 1];
    objects.push({
      key, object: e.object, x: e.x * W, y: e.y * H, scale: e.scale ?? 1, since: e.frame, enter: e.enter ?? "pop",
      text: e.text ?? "", act: last?.act ?? "", actAt: last?.frame ?? -1,
    });
  }

  const side: Side = segment.kind === "summary" ? "right" : sh.presenter ?? "left";
  let presenter: PresenterState | null = null;
  const poses = events.filter((e): e is Extract<MCEvent, { type: "pose" }> => e.type === "pose");
  if (side !== "none") {
    const cur = poses[poses.length - 1];
    const prev = poses.length > 1 ? poses[poses.length - 2] : cur;
    const fallback: Pose = segment.kind === "summary" ? "thumbsup" : "stand";
    presenter = {
      side,
      pose: cur?.pose ?? fallback, prevPose: prev?.pose ?? fallback,
      poseT: !cur || poses.length === 1 ? 1 : clamp01((t - cur.frame) / TIMING.poseBlend),
      poseAt: cur?.frame ?? sh.start,
      face: cur?.face ?? (segment.kind === "summary" ? "smile" : "neutral"),
      at: cur?.at, prevAt: prev?.at,
      blink: blinkAt(frame, hashSeed(`${shot}`)),
    };
  }

  // Presses still showing: from their lead-in to the end of their return.
  const presses: PressState[] = [];
  for (const e of all) {
    if (e.type !== "press") continue;
    const from = e.frame - TIMING.pressLead;
    const to = e.frame + TIMING.pressHold + TIMING.pressReturn;
    if (frame < from || frame >= to) continue;
    const o = objects.find((q) => q.key === e.target);
    if (!o) continue;
    const sameAct = all.find((a) => a.type === "act" && a.target === e.target && Math.abs(a.frame - e.frame) <= 2) as
      | Extract<MCEvent, { type: "act" }> | undefined;
    const tip = pressPoint(o, sameAct?.act);
    const hose = !inReach(side, tip[0], tip[1]);
    const edgeX = side === "left" ? W + 60 : side === "right" ? -60 : tip[0] > W / 2 ? W + 60 : -60;
    // The hose reaches in from the side, a little below the point, above the floor and the captions.
    presses.push({ target: e.target, at: e.frame, tip, hose, from: [edgeX, Math.min(GEOMETRY.floorY - 40, tip[1] + 260)] });
  }

  const badges: BadgeState[] = events
    .filter((e): e is Extract<MCEvent, { type: "check" | "cross" }> => e.type === "check" || e.type === "cross")
    .map((e) => ({ target: e.target, since: e.frame, kind: e.type }));
  const insets: InsetState[] = events
    .filter((e): e is Extract<MCEvent, { type: "inset" }> => e.type === "inset")
    .map((e) => ({ target: e.target, text: e.text, x: e.x * W, y: e.y * H, since: e.frame }));
  const labels: LabelState[] = events
    .filter((e): e is Extract<MCEvent, { type: "label" }> => e.type === "label")
    .map((e, i) => ({ key: `l${i}`, text: e.text, x: e.x * W, y: e.y * H, since: e.frame }));
  return { segment, shot, shotWindow: windows[shot], presenter, objects, presses, badges, insets, labels };
}

/** How far a press has moved the hand toward its point at a frame: 0 at rest, 1 pressed. Steps on twos. */
export function pressReach(p: PressState, frame: number): number {
  const t = onTwos(frame) - p.at;
  if (t < -TIMING.pressLead) return 0;
  if (t < -2) return -0.12 * clamp01((t + TIMING.pressLead) / (TIMING.pressLead - 2)); // anticipation: pulls back
  if (t < 0) return 0.7;
  if (t <= TIMING.pressHold) return 1;
  return 1 - clamp01((t - TIMING.pressHold) / TIMING.pressReturn);
}

/** The point the presenter aims at for `at`: an object's centre on stage. */
export function aimPoint(state: StageState, at: string | undefined): Pt | null {
  if (!at) return null;
  const o = state.objects.find((q) => q.key === at);
  return o ? [o.x, o.y] : null;
}

/** A frame point in the presenter's own coordinates (feet at 0, facing right). */
export function toPresenter(side: Exclude<Side, "none">, p: Pt): Pt {
  const fx = presenterFeetX(side);
  return [side === "right" ? fx - p[0] : p[0] - fx, p[1] - GEOMETRY.floorY];
}
