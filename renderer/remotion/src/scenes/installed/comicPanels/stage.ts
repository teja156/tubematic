/*
 * What is on screen at a frame: a pure function of the data, so the scene, the
 * sheet and the tests read the same answer.
 *
 * A page shows from its start until the next page's. Its panels ink in on their
 * starts and stay: the page fills up as it is read, and a panel not reached
 * yet is blank paper (pencil sketches there cost about 0.07 CPU-seconds per
 * frame). The camera frames the panel being read (moving there over
 * TIMING.read frames, then holding still: a slow push-in on every frame cost
 * about 0.15 CPU-seconds per frame), punches in and shakes on a hit, and pulls
 * back to the whole page at the splash.
 */
import { clamp01, ease } from "../characterKit/geometry";
import { H, LAYOUTS, PAGE, TIMING, W, type CPItem, type CPPage, type ComicPanelsData } from "./contract";

export type Rect = readonly [number, number, number, number];
export type Camera = { cx: number; cy: number; scale: number };

// Where the camera puts what it frames on screen: centred across, its centre at this height,
// fitted inside this box (the captions sit under it).
export const VIEW = { cy: 820, maxW: 1020, maxH: 1080 } as const;

/** The camera that frames a rectangle of the page (page units). */
export function frameRect(r: Rect): Camera {
  const scale = Math.min(VIEW.maxW / r[2], VIEW.maxH / r[3]);
  return { cx: r[0] + r[2] / 2, cy: r[1] + r[3] / 2, scale };
}

/** The whole page, title bar included. */
export const WHOLE_PAGE: Rect = [0, 0, PAGE.w, PAGE.h];

/**
 * What the camera frames to read a panel. A panel in the top row is framed with
 * the title bar above it, across the page's width: framing a half-width panel on
 * its own cut the page title off at the frame's edges.
 */
export function readRect(r: Rect): Rect {
  return r[1] <= PAGE.titleH + PAGE.gutter ? [0, 0, PAGE.w, r[1] + r[3]] : r;
}

const indexAt = (starts: number[], frame: number) => {
  let i = -1;
  for (let k = 0; k < starts.length; k++) if (starts[k] <= frame) i = k;
  return i;
};

export function pageAt(data: ComicPanelsData, frame: number): number {
  return indexAt(data.pages.map((p) => p.start), frame);
}

/** The panel being read on a page at a frame, or -1 before the first panel. */
export function panelAt(page: CPPage, frame: number): number {
  return indexAt(page.panels.map((p) => p.start), frame);
}

const lerpCam = (a: Camera, b: Camera, t: number): Camera => ({
  cx: a.cx + (b.cx - a.cx) * t, cy: a.cy + (b.cy - a.cy) * t, scale: a.scale + (b.scale - a.scale) * t,
});

/** The frames at which the camera's target changes on a page, with each target. */
function targets(data: ComicPanelsData, pi: number): { at: number; cam: Camera; read: boolean }[] {
  const page = data.pages[pi];
  const end = pi + 1 < data.pages.length ? data.pages[pi + 1].start : Infinity;
  const out = page.panels.map((p, i) => ({ at: p.start, cam: frameRect(readRect(LAYOUTS[page.layout][i])), read: true }));
  if (out.length && out[0].at > page.start) out.unshift({ at: page.start, cam: frameRect(WHOLE_PAGE), read: false });
  if (data.splash !== undefined && data.splash >= page.start && data.splash < end) out.push({ at: data.splash, cam: frameRect(WHOLE_PAGE), read: false });
  return out.sort((a, b) => a.at - b.at);
}

/** Every hit item on a page, with its frame. */
function hitsOf(page: CPPage): number[] {
  return page.panels.flatMap((p) => p.items.filter((it) => it.type === "hit").map((it) => it.frame));
}

/** The camera at a frame, with a punch-in and a decaying shake on a hit. */
export function cameraAt(data: ComicPanelsData, frame: number): Camera & { shakeX: number; shakeY: number } {
  const pi = pageAt(data, frame);
  if (pi < 0) return { ...frameRect(WHOLE_PAGE), shakeX: 0, shakeY: 0 };
  const ts = targets(data, pi);
  let cur = ts[0]?.cam ?? frameRect(WHOLE_PAGE);
  for (let i = 0; i < ts.length; i++) {
    const t = ts[i];
    if (frame < t.at) break;
    const prev = i > 0 ? ts[i - 1].cam : t.cam;
    const move = i === 0 ? 1 : ease.inOut(clamp01((frame - t.at) / (t.read ? TIMING.read : TIMING.pullBack)));
    cur = lerpCam(prev, t.cam, move);
  }
  let shakeX = 0, shakeY = 0, punch = 1;
  for (const h of hitsOf(data.pages[pi])) {
    const d = frame - h;
    if (d < 0 || d >= TIMING.hit) continue;
    const env = 1 - d / TIMING.hit;
    shakeX += Math.sin(d * 2.7) * 8 * env;
    shakeY += Math.cos(d * 2.1) * 5 * env;
    punch = Math.max(punch, 1 + 0.08 * env);
  }
  return { ...cur, scale: cur.scale * punch, shakeX, shakeY };
}

/** A page point on screen for a camera. */
export function toScreen(cam: Camera & { shakeX: number; shakeY: number }, x: number, y: number): [number, number] {
  return [W / 2 + (x - cam.cx) * cam.scale + cam.shakeX, VIEW.cy + (y - cam.cy) * cam.scale + cam.shakeY];
}

/** How far a panel has inked in at a frame: 0 not started, 1 done. The opening panel is already inked at
 * frame 0, so the video never opens on an empty page. */
export const inkAt = (start: number, frame: number) => (start <= 0 ? 1 : clamp01((frame - start) / TIMING.inkIn));

/** The items of a panel that have appeared by a frame. */
export const itemsAt = (items: readonly CPItem[], frame: number) => items.filter((it) => it.frame <= frame);

/** An item's pop at a frame: 0 to 1 with a small overshoot, exactly 1 once settled. */
export function popAt(since: number, frame: number): number {
  if (since <= 0) return 1; // what the video opens on is already there at frame 0
  const t = (frame - since) / TIMING.pop;
  return t >= 1 ? 1 : t <= 0 ? 0 : Math.max(0.01, ease.outBack(t));
}

export { H };
