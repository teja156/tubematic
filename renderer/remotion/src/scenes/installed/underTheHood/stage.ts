/*
 * What the Under the Hood scene shows at a frame: which plate (and, during a
 * transition, which outgoing one), the camera on each, which events are up,
 * and the presenter's pose, mouth and blink. Pure functions, so vitest can
 * pin them without a browser.
 */
import {
  CAMERA, TIMING, plateScale, projectAt,
  type Pose, type UTHEvent, type UTHPlate, type UnderTheHoodData,
} from "./contract";

export interface Word { word: string; startFrame: number; endFrame: number }

export const clamp01 = (v: number) => Math.max(0, Math.min(1, v));
export const easeOut = (t: number) => 1 - (1 - clamp01(t)) ** 3;

/** The index of the plate on screen at `frame` (the last one started). */
export function plateIndexAt(data: UnderTheHoodData, frame: number): number {
  let idx = 0;
  data.plates.forEach((p, i) => {
    if (frame >= p.start) idx = i;
  });
  return idx;
}

/** The end frame of plate `i`. */
export function plateEnd(data: UnderTheHoodData, i: number, total: number): number {
  return i + 1 < data.plates.length ? data.plates[i + 1].start : total;
}

/**
 * A plate's camera at a frame: its scale, the point the scale is about, and
 * its opacity. `extraScale` and `about` carry a transition (a zoom-through on
 * the outgoing plate, the settle on the incoming one); the slow push is in
 * `scale`.
 */
export interface Cam { scale: number; extra: number; about: [number, number]; opacity: number }

export function camAt(data: UnderTheHoodData, i: number, frame: number, fps: number): Cam {
  const p = data.plates[i];
  const scale = plateScale(p, frame - p.start, fps);
  const centre: [number, number] = projectAt(p, scale, ...(p.focus ?? [0.5, 0.5]));
  const next = data.plates[i + 1];
  // the outgoing side of a zoom-through: rush into the next plate's `through` point
  if (next && next.enter === "zoom" && next.through && frame >= next.start - TIMING.zoomOut && frame < next.start) {
    const k = easeOut((frame - (next.start - TIMING.zoomOut)) / TIMING.zoomOut);
    const about = projectAt(p, scale, next.through[0], next.through[1]);
    const fadeFrom = next.start - 2;
    return { scale, extra: 1 + (CAMERA.through - 1) * k, about, opacity: frame >= fadeFrom ? 0.5 : 1 };
  }
  // the incoming side: settle from enterFrom to 1
  if (p.enter === "zoom" && frame < p.start + TIMING.zoomIn) {
    const k = easeOut((frame - p.start) / TIMING.zoomIn);
    return { scale, extra: CAMERA.enterFrom + (1 - CAMERA.enterFrom) * k, about: centre, opacity: 1 };
  }
  // a cut cross-fades in
  if ((p.enter ?? "cut") === "cut" && i > 0 && frame < p.start + TIMING.fade) {
    return { scale, extra: 1, about: centre, opacity: clamp01((frame - p.start + 1) / (TIMING.fade + 1)) };
  }
  return { scale, extra: 1, about: centre, opacity: 1 };
}

/**
 * The plate drawn under plate `i` at `frame`, or -1: the previous one, only
 * while plate `i` cross-fades in after a cut. A zoom-through's own dip (the
 * outgoing plate at half opacity) goes to black, never to an older photograph.
 */
export function underPlateAt(data: UnderTheHoodData, i: number, frame: number): number {
  const p = data.plates[i];
  return i > 0 && (p.enter ?? "cut") === "cut" && frame < p.start + TIMING.fade ? i - 1 : -1;
}

/** A point of the photograph in the frame, through the plate's camera (push and transition). */
export function pointAt(p: UTHPlate, cam: Cam, u: number, v: number): [number, number] {
  const [x, y] = projectAt(p, cam.scale, u, v);
  return [cam.about[0] + (x - cam.about[0]) * cam.extra, cam.about[1] + (y - cam.about[1]) * cam.extra];
}

/** The events of plate `i` already started at `frame`. */
export function eventsUp(p: UTHPlate, frame: number): UTHEvent[] {
  return (p.events ?? []).filter((e) => e.frame <= frame);
}

/** Every pose event in the video, in frame order. */
export function poseTrack(data: UnderTheHoodData): { frame: number; pose: Pose }[] {
  return data.plates
    .flatMap((p) => (p.events ?? []).filter((e): e is Extract<UTHEvent, { type: "pose" }> => e.type === "pose"))
    .map((e) => ({ frame: e.frame, pose: e.pose }))
    .sort((a, b) => a.frame - b.frame);
}

/**
 * The presenter at a frame: the pose, and the previous one on the single
 * dissolve frame where a swap lands (both drawn at half opacity).
 */
export function poseAt(track: { frame: number; pose: Pose }[], frame: number): { pose: Pose; dissolveFrom: Pose | null } {
  let pose: Pose = "idle", prev: Pose = "idle", at = -1;
  for (const t of track) {
    if (t.frame > frame) break;
    prev = pose;
    pose = t.pose;
    at = t.frame;
  }
  return { pose, dissolveFrom: at === frame && prev !== pose ? prev : null };
}

/** The mouth: shut unless a word is being spoken, then cycling open shapes every 3 frames. */
export function mouthAt(words: Word[], frame: number): 0 | 1 | 2 {
  const speaking = words.some((w) => frame >= w.startFrame && frame < w.endFrame);
  if (!speaking) return 0;
  const phase = Math.floor(frame / 3) % 4;
  return phase === 1 ? 1 : phase === 2 ? 2 : phase === 3 ? 1 : 0;
}

/** A blink of two frames, at a deterministic rhythm (about every 2 to 3.5 seconds). */
export function blinkAt(frame: number): boolean {
  const cycle = 97; // frames between blinks at 30 fps, never a multiple of the mouth cycle
  const t = frame % cycle;
  return t === 60 || t === 61;
}

/** The value a counter shows `t` frames after it starts: stepped every tickStep frames, settled after tickFrames. */
export function counterValue(from: number, to: number, t: number): number {
  if (t <= 0) return from;
  const stepped = Math.floor(t / TIMING.tickStep) * TIMING.tickStep;
  const k = easeOut(stepped / TIMING.tickFrames);
  return Math.round(from + (to - from) * k);
}

/** A stat's value `t` frames after it starts, counting up over statCount frames. */
export function statValue(from: number, to: number, t: number): number {
  // exactly `to` once counted, so the last digit is the one the agent wrote
  if (t >= TIMING.statCount) return to;
  return from + (to - from) * easeOut(t / TIMING.statCount);
}
