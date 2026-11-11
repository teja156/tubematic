/*
 * What is on a Terminal Doc stage at a frame: pure functions of the data and
 * the frame, so the scene, the preview and the tests agree.
 */
import {
  LIMITS, SIZES, SLOTS, TIMING, moveFrames,
  type Size, type SlotName, type TDBeat, type TDCustomMove, type TDEvent, type TerminalDocData, type Tone,
} from "./contract";

export type Creating = Extract<TDEvent, { id: string }>;
export type GlowEvent = Extract<TDEvent, { type: "glow" }>;
export type BracketEvent = Extract<TDEvent, { type: "bracket" }>;

export interface ElState {
  id: string;
  ev: Creating;
  /** The element this one was made from (rearrange, encode), as it was. */
  from?: ElState;
  /** Frame the element starts fading out (a clear), or Infinity. */
  outAt: number;
  /** Frame a later rearrange or encode took its letters, or Infinity. */
  consumedAt: number;
  bracket?: BracketEvent;
}

export interface StageState {
  beatIndex: number;
  beat: TDBeat | null;
  beatStart: number;
  beatEnd: number;
  elements: ElState[];
  glows: GlowEvent[];
  push: { at: number; frames: number; scale: number } | null;
}

export const DEFAULT_TONE: Record<string, Tone> = {
  word: "white", rearrange: "white", encode: "white", number: "white", grid: "grey", stream: "white", type: "white", custom: "white",
};

export const sizeOf = (e: Creating): Size => {
  if ("size" in e && e.size) return e.size;
  if (e.type === "grid") return "s";
  if (e.slot === "context" || e.slot === "note") return "s";
  if (e.type === "number") return "xl";
  if (e.type === "type") return "m";
  return "l";
};

export const slotOf = (el: ElState): SlotName => {
  const e = el.ev;
  if (e.type === "grid") return "stage";
  if (e.type === "rearrange") return e.slot ?? (el.from ? slotOf(el.from) : "b");
  return e.slot;
};

/** The text an element ends up showing (for a rearrange's source, a bracket's width). */
export const finalText = (e: Creating): string => {
  switch (e.type) {
    case "number": return e.value;
    case "stream": return e.target;
    case "grid": return e.rows.reduce((a, r) => (r.length > a.length ? r : a), "");
    case "custom": return e.text ?? "";
    default: return e.text;
  }
};

export function beatBounds(data: TerminalDocData, i: number, total: number): [number, number] {
  const b = data.beats;
  return [b[i].start, i + 1 < b.length ? b[i + 1].start : total];
}

/** The beat on screen at a frame: the last one started. */
export function beatIndexAt(data: TerminalDocData, frame: number): number {
  let idx = -1;
  data.beats.forEach((b, i) => {
    if (frame >= b.start) idx = i;
  });
  return idx;
}

/** The stage of beat `bi` at `frame` (frame inside the beat, or frozen past its end). */
export function beatState(data: TerminalDocData, bi: number, frame: number, total: number): StageState {
  if (bi < 0) return { beatIndex: -1, beat: null, beatStart: 0, beatEnd: 0, elements: [], glows: [], push: null };
  const beat = data.beats[bi];
  const [start, end] = beatBounds(data, bi, total);
  const els = new Map<string, ElState>();
  const glows: GlowEvent[] = [];
  let push: StageState["push"] = null;
  const events = [...beat.events].sort((x, y) => x.at - y.at);
  for (const e of events) {
    if (e.at > frame) break;
    switch (e.type) {
      case "glow":
        glows.push(e);
        break;
      case "bracket": {
        const t = els.get(e.target);
        if (t) t.bracket = e;
        break;
      }
      case "clear":
        for (const id of e.targets) {
          const t = els.get(id);
          if (t) t.outAt = Math.min(t.outAt, e.at);
        }
        break;
      case "push":
        push = { at: e.at, frames: e.frames, scale: e.scale };
        break;
      case "wall":
        break;
      default: {
        let from: ElState | undefined;
        if (e.type === "rearrange" || e.type === "encode") {
          from = els.get(e.from);
          if (from) {
            from.consumedAt = e.at;
            els.delete(e.from);
          }
        }
        els.set(e.id, { id: e.id, ev: e, from: from ? { ...from } : undefined, outAt: Infinity, consumedAt: Infinity });
      }
    }
  }
  const elements = [...els.values()].filter((el) => frame < el.outAt + TIMING.clearOut);
  return { beatIndex: bi, beat, beatStart: start, beatEnd: end, elements, glows, push };
}

/** The wall's level at a frame, and the level it had before its last change. */
export function wallAt(data: TerminalDocData, frame: number): { level: number; prev: number; since: number } {
  let level = 0, prev = 0, since = -Infinity;
  for (const b of data.beats) {
    for (const e of b.events) {
      if (e.type === "wall" && e.at <= frame && e.at >= since) {
        prev = level;
        level = e.level;
        since = e.at;
      }
    }
  }
  return { level, prev, since };
}

/** The camera's push-in scale at a frame. */
export function pushScale(push: StageState["push"], frame: number, easeFn: (t: number) => number): number {
  if (!push) return 1;
  const p = easeFn(Math.max(0, Math.min(1, (frame - push.at) / push.frames)));
  return 1 + (push.scale - 1) * p;
}

/** Which glow is on an element at a frame: its strength 0..1 and the event. A
 *  later glow fades the earlier one out over the same frames it fades in. */
export function glowOn(glows: GlowEvent[], id: string, frame: number): { k: number; ev: GlowEvent | null } {
  let k = 0, ev: GlowEvent | null = null;
  glows.forEach((g, i) => {
    if (g.target !== id) return;
    const next = glows[i + 1];
    const inK = Math.min(1, (frame - g.at) / TIMING.glowIn);
    const outK = next ? Math.max(0, 1 - (frame - next.at) / TIMING.glowIn) : 1;
    const kk = Math.max(0, Math.min(inK, outK));
    if (kk > 0) {
      k = kk;
      ev = g;
    }
  });
  return { k, ev };
}

/** How long a creating event takes, given the stage it plays on. */
export function elementFrames(el: ElState, custom: Record<string, TDCustomMove>): number {
  return moveFrames(el.ev, custom, el.from ? finalText(el.from.ev) : "");
}

export const bandOf = (slot: SlotName) => SLOTS[slot];
export const sizePx = (s: Size) => SIZES[s];
export { LIMITS };
