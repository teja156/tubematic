/*
 * The camera: one transform on the whole diagram. It fits what is visible into
 * the diagram band as the board grows, pushes in on a focused node, and pulls
 * back to the whole board before the next cut. Keyframes come from the
 * board's events, so the camera is a pure function of the frame.
 */
import { Easing } from "remotion";
import { TIMING, type SFBoard } from "./contract";
import { slotBox, type Box, type BoardLayout } from "./layout";

export const W = 1080;
export const H = 1920;
// The diagram band: 0.27 to 0.69 of the height, inside the side margins.
// Above it sit the pill and the headline; below it, the captions.
export const BAND = { x0: 70, x1: 1010, y0: 0.27 * H, y1: 0.69 * H };
const FIT_MAX = 1.2; // a lone node is not blown up past this
const FOCUS_PUSH = 1.12;
const SCALE_MAX = 1.33;
const PAD = 30;

export type Cam = { cx: number; cy: number; s: number };
type Key = { at: number; cam: Cam };

const ease = Easing.bezier(0.65, 0, 0.35, 1);

function union(boxes: Box[]): Box | null {
  if (boxes.length === 0) return null;
  return {
    x0: Math.min(...boxes.map((b) => b.x0)),
    y0: Math.min(...boxes.map((b) => b.y0)),
    x1: Math.max(...boxes.map((b) => b.x1)),
    y1: Math.max(...boxes.map((b) => b.y1)),
  };
}

/** The largest scale at which `box` fits the band. */
function room(box: Box): number {
  const w = box.x1 - box.x0 + 2 * PAD;
  const h = box.y1 - box.y0 + 2 * PAD;
  return Math.min((BAND.x1 - BAND.x0) / w, (BAND.y1 - BAND.y0) / h);
}

export function fit(box: Box): Cam {
  return { cx: (box.x0 + box.x1) / 2, cy: (box.y0 + box.y1) / 2, s: Math.min(room(box), FIT_MAX) };
}

/** The camera keyframes of one board, from its events. `end` is the board's
 *  last frame + 1. */
export function boardKeys(board: SFBoard, layout: BoardLayout, end: number): Key[] {
  const enterAt: Record<string, number> = {};
  for (const ev of board.events) if (ev.type === "node") enterAt[ev.node] = ev.at;
  const visibleBox = (t: number): Box | null =>
    union(Object.values(layout.nodes).filter((n) => (enterAt[n.id] ?? Infinity) <= t).map(slotBox));
  const visibleFit = (t: number): Cam | null => {
    const box = visibleBox(t);
    return box ? fit(box) : null;
  };
  const events = [...board.events].sort((a, b) => a.at - b.at);
  const keys: Key[] = [];
  for (const ev of events) {
    if (ev.type === "node") {
      const cam = visibleFit(ev.at);
      if (cam) keys.push({ at: ev.at, cam });
    } else if (ev.type === "focus" || ev.type === "fault") {
      const box = visibleBox(ev.at);
      if (layout.nodes[ev.node] && box) {
        // Push in only as far as everything visible still fits the band:
        // past that, the top row would slide under the headline.
        const base = fit(box);
        keys.push({ at: ev.at, cam: { ...base, s: Math.min(base.s * FOCUS_PUSH, room(box), SCALE_MAX) } });
      }
    }
  }
  // Pull back to the whole board before the cut, when there is time to hold it.
  const last = events.length ? events[events.length - 1].at : board.startFrame;
  const pullAt = Math.max(last + TIMING.cameraMove, end - 50);
  if (end - pullAt >= TIMING.cameraMove && Object.keys(layout.nodes).length > 0) {
    keys.push({ at: pullAt, cam: fit(layout.bounds) });
  }
  return keys;
}

/** The camera at a frame: each keyframe's move starts TIMING.cameraLead frames
 *  before its event and eases over TIMING.cameraMove frames from wherever the
 *  camera was. */
export function cameraAt(keys: Key[], frame: number): Cam {
  if (keys.length === 0) return { cx: 0, cy: 0, s: 1 };
  let c: Cam = { ...keys[0].cam };
  for (const k of keys.slice(1)) {
    const t0 = k.at - TIMING.cameraLead;
    const p = ease(Math.max(0, Math.min(1, (frame - t0) / TIMING.cameraMove)));
    if (p <= 0) break;
    c = { cx: c.cx + (k.cam.cx - c.cx) * p, cy: c.cy + (k.cam.cy - c.cy) * p, s: c.s + (k.cam.s - c.s) * p };
  }
  return c;
}

// Where the band's centre sits on screen; the camera's centre lands there.
const BX = (BAND.x0 + BAND.x1) / 2;
const BY = (BAND.y0 + BAND.y1) / 2;

/** The SVG transform attribute placing world coordinates on screen. An SVG
 *  attribute rather than a CSS transform: a CSS-transformed layer is
 *  composited on the CPU every frame in software GL, which tripled the render
 *  cost of this scene. */
export function svgTransform(c: Cam): string {
  return `translate(${BX} ${BY}) scale(${c.s}) translate(${-c.cx} ${-c.cy})`;
}

/** A world point on screen. HTML (labels, chips) is placed with this, at
 *  font sizes scaled by the camera, for the same reason. */
export function toScreen(c: Cam, x: number, y: number): { x: number; y: number } {
  return { x: BX + (x - c.cx) * c.s, y: BY + (y - c.cy) * c.s };
}
