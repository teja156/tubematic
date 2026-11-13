/*
 * Where everything on a Paper Diorama stage is at a frame. Pure functions of
 * the data and the frame, so the component draws nothing it has to remember
 * and the MCP server's checks (mcp/paper_diorama.py) can mirror the geometry.
 */
import {
  LEVELS, ROOMS, SCALES, SLOTS, TIMING,
  type Item, type LevelName, type PaperSet, type PropDef, type ScaleName, type SlotName, type StageEvent,
} from "./contract";

export const clamp01 = (v: number) => Math.max(0, Math.min(1, v));
export const easeInOut = (t: number) => (t < 0.5 ? 2 * t * t : 1 - (-2 * t + 2) ** 2 / 2);
/** An ease-out that runs a little past 1 and settles: the kit's slide-in curve. */
export const overshoot = (t: number) => {
  const k = clamp01(t);
  const c = 1.7;
  return 1 + (c + 1) * (k - 1) ** 3 + c * (k - 1) ** 2;
};

/** The pop of a prop or a stamp: 0.6 up to 1.08 and back to 1, settled after `frames`. */
export function popScale(age: number, frames: number = TIMING.pop): number {
  if (age >= frames) return 1;
  const k = Math.max(0, age / frames);
  return k < 0.6 ? 0.6 + 0.48 * (k / 0.6) : 1.08 - 0.08 * ((k - 0.6) / 0.4);
}

export function setIndexAt(sets: PaperSet[], frame: number): number {
  let index = 0;
  sets.forEach((s, i) => {
    if (frame >= s.start) index = i;
  });
  return index;
}

export function setEnd(sets: PaperSet[], i: number, total: number): number {
  return i + 1 < sets.length ? sets[i + 1].start : total;
}

export function floorY(set: PaperSet): number {
  return ROOMS[set.room]?.floorY ?? 1440;
}

/** Where a prop of size (w, h) at a slot and level puts its box: [left, top, right, bottom]. */
export function slotBox(set: PaperSet, slot: SlotName, level: LevelName, w: number, h: number): [number, number, number, number] {
  const cx = SLOTS[slot];
  const bottom = floorY(set) - LEVELS[level];
  return [cx - w / 2, bottom - h, cx + w / 2, bottom];
}

export function scaled(def: PropDef, scale: ScaleName | undefined): [number, number] {
  const s = SCALES[scale ?? "m"];
  return [def.w * s, def.h * s];
}

const eventsFor = (set: PaperSet, id: string, frame: number) =>
  (set.events ?? []).filter((e) => e.target === id && e.at <= frame).sort((a, b) => a.at - b.at);

export interface ItemPose {
  visible: boolean;
  prop: string;
  x: number;          // centre
  bottom: number;
  scale: number;      // the enter pop, the exit shrink
  dy: number;         // a drop or a hop
  label: string;      // a label pill over it, "" for none
  labelAge: number;
}

/** An item at a frame: where it stands, what it is, and how it is entering or leaving. */
export function itemPose(set: PaperSet, item: Item, frame: number): ItemPose {
  let slot: SlotName = item.slot;
  let level: LevelName = item.level ?? "floor";
  let prop = item.prop;
  let label = "";
  let labelAt = 0;
  let x = SLOTS[slot];
  let bottom = floorY(set) - LEVELS[level];
  let scale = 1, dy = 0;
  const age = frame - item.at;
  if (age < 0) return { visible: false, prop, x, bottom, scale: 0, dy: 0, label, labelAge: 0 };
  const enter = item.enter ?? "pop";
  if (enter === "pop") scale = popScale(age);
  if (enter === "slide") {
    const from = x < 540 ? -260 : 1340;
    x = from + (x - from) * overshoot(age / TIMING.slide);
  }
  if (enter === "drop") dy = -320 * (1 - overshoot(age / TIMING.drop));
  for (const e of eventsFor(set, item.id, frame)) {
    const t = frame - e.at;
    if (e.do === "exit") {
      if (t >= TIMING.exit) return { visible: false, prop, x, bottom, scale: 0, dy, label, labelAge: 0 };
      scale *= 1 - t / TIMING.exit;
    } else if (e.do === "move" && e.to) {
      const toLevel = e.level ?? level;
      const k = easeInOut(clamp01(t / TIMING.move));
      const fromX = SLOTS[slot], fromBottom = floorY(set) - LEVELS[level];
      x = fromX + (SLOTS[e.to] - fromX) * k;
      bottom = fromBottom + (floorY(set) - LEVELS[toLevel] - fromBottom) * k;
      if (k >= 1) {
        slot = e.to;
        level = toLevel;
      }
    } else if (e.do === "swap" && e.prop) {
      if (t >= 0) prop = e.prop;
    } else if (e.do === "hop") {
      if (t < TIMING.hop) dy -= Math.sin((t / TIMING.hop) * Math.PI) * 34;
    } else if (e.do === "label") {
      label = e.text ?? "";
      labelAt = e.at;
    }
  }
  return { visible: true, prop, x, bottom, scale, dy, label, labelAge: frame - labelAt };
}

export interface CritterPose {
  visible: boolean;
  x: number;
  bottom: number;
  face: 1 | -1;
  expr: string;
  dy: number;
}

export function critterPose(set: PaperSet, frame: number, start: number): CritterPose {
  const c = set.critter;
  if (!c) return { visible: false, x: 0, bottom: 0, face: 1, expr: "idle", dy: 0 };
  let slot = c.slot;
  let x = SLOTS[slot];
  let expr: string = c.expr ?? "idle";
  let dy = 0;
  for (const e of eventsFor(set, "critter", frame)) {
    const t = frame - e.at;
    if (e.do === "expr" && e.value) expr = e.value;
    else if (e.do === "hop" && t < TIMING.hop) dy -= Math.sin((t / TIMING.hop) * Math.PI) * 40;
    else if (e.do === "move" && e.to) {
      const k = easeInOut(clamp01(t / TIMING.move));
      x = SLOTS[slot] + (SLOTS[e.to] - SLOTS[slot]) * k;
      if (k >= 1) slot = e.to;
    }
  }
  void start;
  return { visible: true, x, bottom: floorY(set), face: c.face ?? 1, expr, dy };
}

/** The stage's scale at a frame: 1, or more during a snap zoom. There is no
 *  slow push: scaling the stage makes the CPU renderer redraw every prop on
 *  every frame (measured: a pushed set cost two and a half times a still one). */
export function stageScale(set: PaperSet, frame: number): number {
  let s = 1;
  for (const e of set.events ?? []) {
    if (e.do !== "zoom") continue;
    const t = frame - e.at;
    if (t < 0) continue;
    const up = TIMING.zoomScale - 1;
    if (t < TIMING.zoomIn) s += up * (t / TIMING.zoomIn);
    else if (t < TIMING.zoomIn + TIMING.zoomHold) s += up;
    else s += up * (1 - easeInOut(clamp01((t - TIMING.zoomIn - TIMING.zoomHold) / TIMING.zoomOut)));
  }
  return s;
}

/** The point a snap zoom pushes toward: the centre of its target, or the stage's. */
export function zoomOrigin(set: PaperSet, frame: number, size: (item: Item) => [number, number]): [number, number] {
  const last = (set.events ?? []).filter((e) => e.do === "zoom" && e.at <= frame).sort((a, b) => b.at - a.at)[0];
  const item = last && (set.items ?? []).find((i) => i.id === last.target);
  if (item) {
    const [w, h] = size(item);
    const [l, t, r, b] = slotBox(set, item.slot, item.level ?? "floor", w, h);
    return [(l + r) / 2, (t + b) / 2];
  }
  return [540, floorY(set) - 360];
}

/** How far an event's drawing has got: a ring's stroke, a route's unroll. */
export function drawProgress(e: StageEvent, frame: number): number {
  const frames = e.do === "ring" ? TIMING.ring : e.do === "route" ? TIMING.route : TIMING.stamp;
  return clamp01((frame - e.at) / frames);
}

/** The torn cut's edge, as the share of the frame the new set has uncovered. */
export function tearReveal(frame: number, start: number): number {
  return easeInOut(clamp01((frame - start) / TIMING.tear));
}

/** Points on a hand-drawn ellipse around a box, as far as `progress` has drawn it.
 *  It starts at the top right and ends a little past where it began, unclosed. */
export function ringPoints(box: [number, number, number, number], progress: number, seed: number): [number, number][] {
  const [l, t, r, b] = box;
  const cx = (l + r) / 2, cy = (t + b) / 2, rx = (r - l) / 2 + 26, ry = (b - t) / 2 + 22;
  const turns = 1.12;
  const n = Math.max(2, Math.round(48 * progress));
  const out: [number, number][] = [];
  for (let i = 0; i <= n; i++) {
    const a = -0.6 + (i / 48) * Math.PI * 2 * turns;
    const wobble = 1 + 0.04 * Math.sin(a * 3 + seed);
    out.push([cx + Math.cos(a) * rx * wobble, cy + Math.sin(a) * ry * wobble]);
  }
  return out;
}
