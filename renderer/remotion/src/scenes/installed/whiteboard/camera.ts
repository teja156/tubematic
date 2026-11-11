/**
 * The camera over the board: it rests on one region at a time, glides to the
 * next when the narration moves on (and only then does the marker draw there),
 * creeps in a little while it rests, and at the recap pulls back to show every
 * region at once. It never cuts.
 *
 * The camera is the ink canvas's transform, an SVG transform attribute on the
 * recap numbers, and screen positions for the text, never a CSS transform: a
 * CSS-transformed layer is re-composited every frame in software GL and cost
 * about 1.3x in System Flow's measurements.
 */
import { Easing } from "remotion";
import { BOARD, TIMING, type WhiteboardData } from "./contract";
import { regionCenter, regionOrigin } from "./layout";

export const W = 1080;
export const H = 1920;

/** Board point (x, y) sits at screen (sx, sy) at zoom z. */
export type Cam = { x: number; y: number; z: number; sy: number };

const glideEase = Easing.bezier(0.37, 0, 0.63, 1); // easeInOutSine
const pullEase = Easing.bezier(0.65, 0, 0.35, 1);
const clamp01 = (v: number) => Math.max(0, Math.min(1, v));
const lerp = (a: number, b: number, t: number) => a + (b - a) * t;

/** How far the camera creeps in over a region's rest. At most 2%: a 2% push
 *  on a full-width line puts its ends at the 60 px side safe zone. */
const CREEP = 0.02;
/** The recap keeps pulling out slowly after it lands, so the ending is never a
 *  still frame: this fraction of the zoom per frame. */
const RECAP_DRIFT = 0.0003;
/** Where the recap map sits: inside the safe zone (150 px at the top, 60 px at
 *  the sides) and above the captions, which start near y 1340. */
const MAP_CENTER_Y = 755;
const MAP_W = 920;
const MAP_H = 1150;
/** Board margin kept around the regions in the recap, for the numbers. */
const MAP_MARGIN = 140;

function mix(a: Cam, b: Cam, t: number): Cam {
  // Zoom in log space, so a pull-back reads as even.
  return { x: lerp(a.x, b.x, t), y: lerp(a.y, b.y, t), z: Math.exp(lerp(Math.log(a.z), Math.log(b.z), t)), sy: lerp(a.sy, b.sy, t) };
}

/** The whole-board view of the recap. */
export function mapView(regionCount: number): Cam {
  const xs: number[] = [];
  const ys: number[] = [];
  for (let i = 0; i < regionCount; i++) {
    const [x, y] = regionOrigin(i);
    xs.push(x, x + BOARD.regionW);
    ys.push(y, y + BOARD.regionH);
  }
  const x0 = Math.min(...xs) - MAP_MARGIN;
  const x1 = Math.max(...xs) + MAP_MARGIN;
  const y0 = Math.min(...ys) - MAP_MARGIN;
  const y1 = Math.max(...ys) + MAP_MARGIN;
  const z = Math.min(MAP_W / (x1 - x0), MAP_H / (y1 - y0));
  return { x: (x0 + x1) / 2, y: (y0 + y1) / 2, z, sy: MAP_CENTER_Y };
}

export function cameraAt(data: WhiteboardData, frame: number): Cam {
  const regions = data.regions;
  const restOn = (i: number, f: number): Cam => {
    const [x, y] = regionCenter(i);
    const settle = i === 0 ? 0 : regions[i].startFrame + TIMING.glide;
    const leave = i + 1 < regions.length ? regions[i + 1].startFrame : data.recapFrame;
    const t = clamp01((f - settle) / Math.max(1, leave - settle));
    return { x, y, z: 1 + CREEP * t, sy: BOARD.bandCenterY };
  };
  if (frame >= data.recapFrame) {
    const from = restOn(regions.length - 1, data.recapFrame);
    const t = pullEase(clamp01((frame - data.recapFrame) / TIMING.recapPull));
    const cam = mix(from, mapView(regions.length), t);
    const drift = Math.max(0, frame - data.recapFrame - TIMING.recapPull) * RECAP_DRIFT;
    return { ...cam, z: cam.z * (1 - drift) };
  }
  let i = 0;
  for (let k = 0; k < regions.length; k++) if (regions[k].startFrame <= frame) i = k;
  if (i > 0 && frame < regions[i].startFrame + TIMING.glide) {
    const from = restOn(i - 1, regions[i].startFrame);
    const to = restOn(i, regions[i].startFrame + TIMING.glide);
    return mix(from, to, glideEase(clamp01((frame - regions[i].startFrame) / TIMING.glide)));
  }
  return restOn(i, frame);
}

/** The board group's SVG transform for a camera. */
export const svgTransform = (c: Cam) =>
  `translate(${(W / 2).toFixed(2)} ${c.sy.toFixed(2)}) scale(${c.z.toFixed(5)}) translate(${(-c.x).toFixed(2)} ${(-c.y).toFixed(2)})`;

export const toScreen = (c: Cam, x: number, y: number): [number, number] => [(x - c.x) * c.z + W / 2, (y - c.y) * c.z + c.sy];

/** Whether any part of a board rectangle is in the frame. Text that is not is
 *  left out of the page: the text-layout audit measures every text element on
 *  the page, and writing from a region the camera has left would otherwise be
 *  reported as off-screen text on every sampled frame. */
export function onScreen(c: Cam, x: number, y: number, w: number, h: number): boolean {
  const [x0, y0] = toScreen(c, x, y);
  return x0 < W && y0 < H && x0 + w * c.z > 0 && y0 + h * c.z > 0;
}
