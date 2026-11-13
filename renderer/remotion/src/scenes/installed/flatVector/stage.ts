/*
 * What the Flat Vector Science scene shows at a frame: which shot, how its
 * transition is going, where each prop is and how far it has popped in, what
 * the counter reads, and how far a ladder, a zoom, a descent or a list of
 * stages has come. Pure functions, so vitest can pin them without a browser,
 * and mcp/flat_vector_science.py mirrors the ones the checks need.
 */
import {
  GEOMETRY, TIMING, eventFrames, type Counter, type DescentShot, type FlatVectorData, type Item, type LadderShot, type Shot,
  type StagesShot, type ZoomShot,
} from "./contract";

export const clamp01 = (v: number) => Math.max(0, Math.min(1, v));
export const easeInOut = (t: number) => {
  const x = clamp01(t);
  return x < 0.5 ? 4 * x * x * x : 1 - (-2 * x + 2) ** 3 / 2;
};
export const easeOut = (t: number) => 1 - (1 - clamp01(t)) ** 3;
/** Ease out with a small overshoot past 1 before settling (a pop). */
export const easeOutBack = (t: number) => {
  const x = clamp01(t);
  const c1 = 1.70158, c3 = c1 + 1;
  return 1 + c3 * (x - 1) ** 3 + c1 * (x - 1) ** 2;
};
export const ramp = (frame: number, at: number, frames: number) => (frames <= 0 ? (frame >= at ? 1 : 0) : clamp01((frame - at) / frames));

export function shotIndexAt(data: FlatVectorData, frame: number): number {
  let idx = 0;
  data.shots.forEach((s, i) => {
    if (frame >= s.start) idx = i;
  });
  return idx;
}

export function shotEnd(data: FlatVectorData, i: number, total: number): number {
  return i + 1 < data.shots.length ? data.shots[i + 1].start : total;
}

/**
 * The transition running at `frame`, if any: the shot coming in and how far
 * it has gone (0..1). A lens and a push run over the frames before the shot's
 * start; a flash runs over the frames after it; a cut has none.
 */
export function transitionAt(data: FlatVectorData, frame: number): { into: number; kind: "lens" | "push" | "flash"; progress: number } | null {
  for (let k = 1; k < data.shots.length; k++) {
    const s = data.shots[k];
    const kind = s.cut ?? "cut";
    if (kind === "lens" || kind === "push") {
      const n = TIMING[kind];
      if (frame >= s.start - n && frame < s.start) return { into: k, kind, progress: (frame - (s.start - n) + 1) / (n + 1) };
    } else if (kind === "flash") {
      if (frame >= s.start && frame < s.start + TIMING.flash) return { into: k, kind, progress: (frame - s.start + 1) / (TIMING.flash + 1) };
    }
  }
  return null;
}

/** A prop's idle drift at a frame: a slow bob and sway, seeded by its slot so neighbours differ. */
export function drift(frame: number, seed: number): { dx: number; dy: number; rot: number } {
  return {
    dx: Math.sin(frame * 0.021 + seed * 1.7) * 14,
    dy: Math.sin(frame * 0.047 + seed) * 9,
    rot: Math.sin(frame * 0.033 + seed * 2.3) * 1.6,
  };
}

/** How far an item has popped in: 0 before its frame, overshooting past 1, then 1. */
export function itemScale(item: Item, frame: number): number {
  return item.at === undefined ? 1 : Math.max(0, easeOutBack(ramp(frame, item.at, TIMING.pop)));
}

/**
 * A counter's value at a frame: `from` (or the value it starts from) until its
 * `at`, then rolling to `value` over TIMING.roll frames.
 */
export function counterValue(c: Counter, frame: number, start = 0): number {
  const from = c.from ?? start;
  return from + (c.value - from) * easeInOut(ramp(frame, c.at, TIMING.roll));
}

/**
 * Which item of a ladder, a zoom, a descent or a list of stages is the current
 * one at a frame, and how far its arrival has gone (0..1). Before the first
 * one's frame the index is -1.
 */
export function stepAt(ats: number[], frame: number): { index: number; progress: number } {
  let index = -1;
  ats.forEach((a, i) => {
    if (frame >= a) index = i;
  });
  return { index, progress: index < 0 ? 0 : easeInOut(ramp(frame, ats[index], TIMING.rung)) };
}

export function shotAts(shot: LadderShot | ZoomShot | DescentShot | StagesShot): number[] {
  switch (shot.kind) {
    case "ladder":
      return shot.rungs.map((r) => r.at);
    case "zoom":
      return shot.levels.map((l) => l.at);
    case "descent":
      return shot.layers.map((l) => l.at);
    case "stages":
      return shot.steps.map((s) => s.at);
  }
}

/**
 * The frames the pictures of a ladder, a zoom, a descent or stages arrive on:
 * the first one is on screen from the shot's start (a shot never opens empty),
 * the rest on their own words. Their titles still light on their own words.
 */
export function pictureAts(shot: LadderShot | ZoomShot | DescentShot | StagesShot): number[] {
  const ats = shotAts(shot);
  return ats.length ? [Math.min(shot.start, ats[0]), ...ats.slice(1)] : ats;
}

/** A descent's depth at a frame: rolling from the last layer's value to the current one's. */
export function depthAt(shot: DescentShot, frame: number): number {
  const { index, progress } = stepAt(shot.layers.map((l) => l.at), frame);
  if (index < 0) return 0;
  const from = index === 0 ? 0 : shot.layers[index - 1].value;
  return from + (shot.layers[index].value - from) * progress;
}

/** The slot centre of an item, in frame pixels. */
export const slotCentre = (slot: Item["slot"]) => GEOMETRY.slot[slot];

/**
 * The stretches in which nothing new arrives apart from the drift, as
 * [from, to] frames: from each event of a shot (contract.ts eventFrames) to
 * the next, and from the last to the shot's end. The validator refuses one
 * longer than LIMITS.maxStillSeconds.
 */
export function quietSpans(data: FlatVectorData, total: number): [number, number][] {
  const spans: [number, number][] = [];
  data.shots.forEach((s: Shot, i) => {
    const end = shotEnd(data, i, total);
    const frames = [...eventFrames(s).filter((f) => f < end), end];
    for (let k = 1; k < frames.length; k++) spans.push([frames[k - 1], frames[k]]);
  });
  return spans;
}
