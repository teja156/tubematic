/*
 * What is on stage at a frame: pure functions of the data, shared by the scene,
 * the model sheet and the tests. mcp/storybook_atlas.py mirrors the walk rule
 * (actorAt), the chapter spans and the prop states to check a config; the
 * shared cases in mcp/tests/fixtures/storybook_atlas_contract.json pin them.
 */
import { PLATE_EVENTS, STAGE, TIMING, W, type Chapter, type Facing, type PlateEvent, type PropSpec, type SAEvent, type StorybookAtlasData } from "./contract";
import type { Act } from "./props/types";

export const clamp01 = (t: number) => Math.max(0, Math.min(1, t));
export const ease = {
  out: (t: number) => 1 - (1 - t) ** 3,
  in: (t: number) => t ** 3,
  inOut: (t: number) => (t < 0.5 ? 4 * t ** 3 : 1 - (-2 * t + 2) ** 3 / 2),
};

/** Where an actor walks in from or off to: just past the nearer frame edge. */
export const OFFSTAGE = { left: -160, right: W + 160 } as const;
export function nearerEdge(x: number): number {
  return x < W / 2 ? OFFSTAGE.left : OFFSTAGE.right;
}

/** Frames a walk from a to b takes. */
export function walkFrames(a: number, b: number): number {
  return Math.ceil(Math.abs(b - a) / TIMING.walkSpeed);
}

export type Move = { at: number; x?: number; pose?: string; facing?: Facing; exit?: boolean };

export type ActorState = {
  x: number;
  visible: boolean;
  walking: boolean;
  /** Which walk drawing, counted from the walk's start (held TIMING.walkHold frames each). */
  step: number;
  pose: string;
  facing: Facing;
  /** The frame the current pose took effect (the end of the walk that led to it). */
  posedAt: number;
};

type Walk = { from: number; to: number; at: number; exit: boolean };

function walkX(w: Walk, frame: number): number {
  const done = frame - w.at;
  return done >= walkFrames(w.from, w.to) ? w.to : w.from + Math.sign(w.to - w.from) * done * TIMING.walkSpeed;
}

/**
 * An actor's state at `frame`, given its moves in one chapter, sorted by `at`.
 * `start` is where it stands when the chapter opens, or null for an actor who
 * is offstage until its first move walks it in from the nearer edge.
 * A move with an `x` walks there (at TIMING.walkSpeed) and then takes its pose;
 * `exit` walks off at the nearer edge. A move that comes while a walk is still
 * going starts from wherever the actor is at that frame.
 */
export function actorAt(moves: Move[], frame: number, start: number | null): ActorState {
  let x = start ?? 0;
  let visible = start !== null;
  let pose = "stand";
  let facing: Facing = x < W / 2 ? "right" : "left";
  let rest: Facing = facing;
  let walk: Walk | null = null;
  let posedAt = -Infinity;
  for (const m of moves) {
    if (m.at > frame) break;
    if (walk) {
      x = walkX(walk, m.at);
      if (x === walk.to && walk.exit) visible = false;
      walk = null;
    }
    if (m.exit) {
      if (visible) walk = { from: x, to: nearerEdge(x), at: m.at, exit: true };
    } else if (!visible) {
      const target = m.x ?? W / 2;
      x = nearerEdge(target);
      visible = true;
      walk = { from: x, to: target, at: m.at, exit: false };
    } else if (m.x !== undefined && m.x !== x) {
      walk = { from: x, to: m.x, at: m.at, exit: false };
    }
    pose = m.pose ?? "stand";
    const heading: Facing | null = walk ? (walk.to > walk.from ? "right" : "left") : null;
    rest = m.facing ?? heading ?? facing;
    facing = heading ?? rest;
    posedAt = walk ? walk.at + walkFrames(walk.from, walk.to) : m.at;
  }
  if (walk) {
    const done = frame - walk.at;
    if (done < walkFrames(walk.from, walk.to)) {
      return { x: walkX(walk, frame), visible: true, walking: true, step: Math.floor(done / TIMING.walkHold), pose, facing, posedAt };
    }
    x = walk.to;
    if (walk.exit) visible = false;
    facing = rest;
  }
  return { x, visible, walking: false, step: 0, pose, facing, posedAt };
}

/**
 * Events in time; on one frame, what puts something on stage comes before
 * what refers to it (an act or a tag on a prop placed that frame), whatever
 * order they were listed in. mcp/storybook_atlas.py::event_order is the same.
 */
export function eventOrder(a: SAEvent, b: SAEvent): number {
  const rank = (e: SAEvent) => (e.type === "act" || e.type === "tag" ? 1 : 0);
  return a.at - b.at || rank(a) - rank(b);
}

/** Each chapter's [start, end) in frames. */
export function chapterSpans(chapters: Chapter[], total: number): [number, number][] {
  return chapters.map((c, i) => [c.start, i + 1 < chapters.length ? chapters[i + 1].start : total]);
}

export function chapterIndexAt(chapters: Chapter[], frame: number): number {
  let k = 0;
  for (let i = 0; i < chapters.length; i++) if (frame >= chapters[i].start) k = i;
  return k;
}

/** The guide's moves and each person's moves in a chapter, sorted. */
export function movesOf(events: SAEvent[]): { guide: Move[]; people: Map<string, Move[]> } {
  const guide: Move[] = [];
  const people = new Map<string, Move[]>();
  for (const e of [...events].sort(eventOrder)) {
    if (e.type === "guide") guide.push({ at: e.at, x: e.x, pose: e.pose, facing: e.facing });
    if (e.type === "person") {
      const list = people.get(e.who) ?? [];
      list.push({ at: e.at, x: e.x, pose: e.pose, facing: e.facing, exit: e.exit });
      people.set(e.who, list);
    }
  }
  return { guide, people };
}

// ── props ────────────────────────────────────────────────────────────────────
export type PropState = {
  id: string;
  prop: string;
  x: number;
  /** The prop's base line, in frame px. */
  y: number;
  scale: number;
  enter: string;
  since: number;
  /** The drawing to show, and the one it is cross-fading from (with the fade's progress), if any. */
  state: number;
  /** The drawing it rests on: 0, or 1 once switched. */
  base: number;
  from: number | null;
  fade: number;
  /** A transform act running now, with its progress (0..1). */
  motion: { act: Act; t: number } | null;
  /** Halo strength 0..1 once a glow act has fired. */
  glow: number;
};

/** The base line a prop sits on: the floor, or its own `y` on the wall. */
export function propBase(spec: PropSpec, y: number | undefined): number {
  return spec.place === "floor" ? STAGE.floor : y ?? 900;
}

/** The props on stage in a chapter at `frame`, with their state and act. */
export function propsAt(events: SAEvent[], frame: number, specs: Record<string, PropSpec>): PropState[] {
  const out = new Map<string, PropState>();
  const sorted = [...events].sort(eventOrder);
  for (const e of sorted) {
    if (e.at > frame) break;
    if (e.type === "prop") {
      const spec = specs[e.prop];
      if (!spec) continue;
      out.set(e.id, {
        id: e.id, prop: e.prop, x: e.x, y: propBase(spec, e.y), scale: e.scale ?? 1, enter: e.enter ?? "pop",
        since: e.at, state: 0, base: 0, from: null, fade: 1, motion: null, glow: 0,
      });
    }
    if (e.type === "act") {
      const p = out.get(e.id);
      if (!p) continue;
      const spec = specs[p.prop];
      const t = frame - e.at;
      if (e.act === "switch") {
        const next = Math.min(1, spec.states - 1);
        if (next !== p.base) {
          p.from = p.state;
          p.state = next;
          p.base = next;
          p.fade = clamp01(t / TIMING.switchFade);
        }
      } else if (e.act === "cycle") {
        if (t < TIMING.act && spec.states > 1) {
          const n = Math.max(1, spec.states - 1);
          p.from = null;
          p.fade = 1;
          p.state = 1 + (Math.floor(t / TIMING.cycleHold) % n);
          p.motion = null;
        } else {
          p.state = p.base;
        }
      } else if (e.act === "glow") {
        p.glow = clamp01(t / 8);
      } else if (t < TIMING.act) {
        p.motion = { act: e.act, t: t / TIMING.act };
      } else if (p.motion?.act === e.act) {
        p.motion = null;
      }
    }
  }
  for (const p of out.values()) if (p.from !== null && p.fade >= 1) p.from = null;
  return [...out.values()];
}

/** A transform act at progress t (0..1): translation in px, rotation in degrees, scale; and its pivot. */
export function actMotion(act: Act, t: number): { dx: number; dy: number; rot: number; s: number; pivot: "base" | "centre" | "top" } {
  const damp = (1 - t) ** 2;
  switch (act) {
    case "wobble":
      return { dx: 0, dy: 0, rot: 6 * Math.sin(t * Math.PI * 4) * damp, s: 1, pivot: "base" };
    case "bounce": {
      const k = t < 0.5 ? Math.sin(t * 2 * Math.PI) : 0;
      return { dx: 0, dy: -36 * Math.max(0, k), rot: 0, s: 1, pivot: "base" };
    }
    case "shake":
      return { dx: 7 * Math.sin(t * Math.PI * 14) * damp, dy: 0, rot: 0, s: 1, pivot: "base" };
    case "spin":
      return { dx: 0, dy: 0, rot: 360 * ease.inOut(t), s: 1, pivot: "centre" };
    case "swing":
      return { dx: 0, dy: 0, rot: 10 * Math.sin(t * Math.PI * 3) * damp, s: 1, pivot: "top" };
    case "pulse":
      return { dx: 0, dy: 0, rot: 0, s: 1 + 0.08 * Math.abs(Math.sin(t * Math.PI * 2)), pivot: "base" };
    default:
      return { dx: 0, dy: 0, rot: 0, s: 1, pivot: "base" };
  }
}

/** The plate open at `frame` in a chapter, with how far open it is (0..1), or null. */
export function plateAt(events: SAEvent[], frame: number): { e: PlateEvent; open: number } | null {
  for (const e of events) {
    if (!(PLATE_EVENTS as readonly string[]).includes(e.type)) continue;
    const p = e as PlateEvent;
    if (frame < p.at || frame >= p.until + TIMING.plateOpen) continue;
    const opening = clamp01((frame - p.at) / TIMING.plateOpen);
    const closing = clamp01((p.until + TIMING.plateOpen - frame) / TIMING.plateOpen);
    return { e: p, open: ease.inOut(Math.min(opening, closing)) };
  }
  return null;
}

/** The chapter transition at `frame`, if one is running. */
export type Transition =
  | { kind: "push"; from: number; t: number }
  | { kind: "white"; to: number; t: number }
  | { kind: "wipe"; from: number; to: number; t: number };

export function transitionAt(data: StorybookAtlasData, frame: number): Transition | null {
  const cs = data.chapters;
  for (let i = 1; i < cs.length; i++) {
    const s = cs[i].start;
    if (cs[i].enter === "push") {
      if (frame >= s - TIMING.pushFrames && frame < s) return { kind: "push", from: i - 1, t: (frame - (s - TIMING.pushFrames)) / TIMING.pushFrames };
      const white = TIMING.whiteHold + TIMING.dissolve;
      if (frame >= s && frame < s + white) return { kind: "white", to: i, t: clamp01((frame - s - TIMING.whiteHold) / TIMING.dissolve) };
    } else if (frame >= s && frame < s + TIMING.wipeFrames) {
      return { kind: "wipe", from: i - 1, to: i, t: (frame - s) / TIMING.wipeFrames };
    }
  }
  return null;
}

/**
 * The portal prop a push goes through: the last one in the chapter that has
 * landed by `cut` (the push's first frame), or null. The validator requires
 * one to have landed by then.
 */
export function portalOf(chapter: Chapter, specs: Record<string, PropSpec>, cut: number): Extract<SAEvent, { type: "prop" }> | null {
  let found: Extract<SAEvent, { type: "prop" }> | null = null;
  for (const e of [...chapter.events].sort(eventOrder)) {
    if (e.type === "prop" && specs[e.prop]?.portal && e.at + TIMING.propIn <= cut) found = e;
  }
  return found;
}
