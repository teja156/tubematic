/*
 * What the Night Signal scene shows at a frame: which scene, whether a glitch
 * tear is running, the slow push, and how far each item, connector, bubble,
 * mark and card part has come. Pure functions, so vitest can pin them without
 * a browser, and mcp/night_signal.py mirrors the ones the checks need.
 */
import { CAMERA, GEOMETRY, TIMING, eventFrames, type Item, type NightSignalData, type Scene, type Slot } from "./contract";

export const clamp01 = (v: number) => Math.max(0, Math.min(1, v));
export const easeInOut = (t: number) => {
  const x = clamp01(t);
  return x < 0.5 ? 4 * x * x * x : 1 - (-2 * x + 2) ** 3 / 2;
};
/** Ease out with a small overshoot past 1 before settling (a pop). */
export const easeOutBack = (t: number) => {
  const x = clamp01(t);
  const c1 = 1.70158, c3 = c1 + 1;
  return 1 + c3 * (x - 1) ** 3 + c1 * (x - 1) ** 2;
};

/** Progress from 0 to 1 over `frames` frames starting at `at` (1 once past, 0 before). */
export const ramp = (frame: number, at: number, frames: number) => (frames <= 0 ? (frame >= at ? 1 : 0) : clamp01((frame - at) / frames));

/** The index of the scene on screen at `frame` (the last one started). */
export function sceneIndexAt(data: NightSignalData, frame: number): number {
  let idx = 0;
  data.scenes.forEach((s, i) => {
    if (frame >= s.start) idx = i;
  });
  return idx;
}

/** The end frame of scene `i`. */
export function sceneEnd(data: NightSignalData, i: number, total: number): number {
  return i + 1 < data.scenes.length ? data.scenes[i + 1].start : total;
}

/**
 * The glitch tear running at `frame`, if any: the index of the scene coming in
 * and how far the tear has gone (0..1). A tear runs from TIMING.tearBefore
 * frames before a scene's start to TIMING.tearAfter after it; a hard cut has none.
 */
export function tearAt(data: NightSignalData, frame: number): { into: number; progress: number } | null {
  const { tearBefore, tearAfter } = TIMING;
  for (let k = 1; k < data.scenes.length; k++) {
    const s = data.scenes[k];
    if ((s.cut ?? "glitch") !== "glitch") continue;
    if (frame >= s.start - tearBefore && frame <= s.start + tearAfter) {
      return { into: k, progress: (frame - (s.start - tearBefore) + 0.5) / (tearBefore + tearAfter + 1) };
    }
  }
  return null;
}

/** The band's scale for the slow push over a scene, 1 at its start, CAMERA.push at its end. */
export function pushAt(start: number, end: number, frame: number): number {
  return 1 + (CAMERA.push - 1) * easeInOut((frame - start) / Math.max(1, end - start));
}

export interface ItemState {
  visible: boolean;
  /** 0..~1.08 while popping in, 1 after. */
  scale: number;
  x: number;
  /** 0..1: how red the item is (always 0 for an item that is not the threat). */
  red: number;
  /** -1 faces left, 1 faces right. */
  facing: number;
}

/** An item at a frame: where it is, how far it has popped in, how red it is. */
export function itemAt(item: Item, frame: number, slotX: (s: Slot) => number = (s) => GEOMETRY.slotX[s]): ItemState {
  const T = TIMING;
  const visible = item.at === undefined || frame >= item.at;
  const scale = item.at === undefined ? 1 : Math.max(0, easeOutBack(ramp(frame, item.at, T.pop)));
  let x = slotX(item.slot);
  if (item.to) x += (slotX(item.to.slot) - x) * easeInOut(ramp(frame, item.to.at, T.step));
  const red = item.threat ? (item.redAt === undefined ? 1 : ramp(frame, item.redAt, T.redden)) : 0;
  return { visible, scale, x, red, facing: item.face === "left" ? -1 : 1 };
}

/** The HUD's progress squares at a frame: how many there are, and which is current. */
export function squaresAt(data: NightSignalData, frame: number): { count: number; current: number } {
  return { count: data.scenes.length, current: sceneIndexAt(data, frame) };
}

/**
 * The stretches in which nothing new happens apart from the running loops and
 * the slow push, as [from, to] frames: from each event of a scene (contract.ts
 * eventFrames) to the next, and from the last to the scene's end. The
 * validator refuses one longer than LIMITS.maxStillSeconds.
 */
export function quietSpans(data: NightSignalData, total: number): [number, number][] {
  const spans: [number, number][] = [];
  data.scenes.forEach((s: Scene, i) => {
    const frames = [...eventFrames(s).filter((f) => f < sceneEnd(data, i, total)), sceneEnd(data, i, total)];
    for (let k = 1; k < frames.length; k++) spans.push([frames[k - 1], frames[k]]);
  });
  return spans;
}
