/*
 * The Isometric Infographic data contract: the shape of `props.isometric`, its
 * limits and timings, and the geometry the MCP server checks before render.
 *
 * Keep in sync: mcp/isometric_infographic.py holds the Python side of every
 * constant here, and tubematic_core/style_packs/isometric_infographic.json lists
 * the catalogues for the agent. Both are written from this file by
 * renderer/remotion/isometric-tools/sync-contract.mjs, with the shared cases in
 * mcp/tests/fixtures/isometric_infographic_contract.json.
 *
 * The frame has fixed zones: the title and the readout at the top, the board
 * in the middle, the caption card under it (the shared Subtitles layer, `card`)
 * and the legend at the foot. The board is BOARD x BOARD tiles; props stand on
 * tile coordinates, never on pixels.
 */
import { AREA_COLORS, PALETTE, PROPS, type Solid } from "./kit";

export const W = 1080;
export const H = 1920;
export const BOARD = 10;

export const AREA_KINDS = Object.keys(AREA_COLORS);
export const COLOR_NAMES = Object.keys(PALETTE);
export const PROP_NAMES = Object.keys(PROPS);
export const ROOMS = PROP_NAMES.filter((n) => PROPS[n].room);
export const STACKS = PROP_NAMES.filter((n) => PROPS[n].layers);
export const MOVERS = ["cube", "parcel", "truck", "van", "car", "bus", "ship", "plane", "train", "person", "coin"];
export const SOLIDS = ["box", "cyl", "cone", "pyr", "gable"] as const;

export const LIMITS = {
  minBoards: 1,
  maxBoards: 3,
  maxAreas: 8,
  maxProps: 14,
  maxRoutes: 3,
  maxRoutePoints: 8,
  maxMovers: 4,
  maxPins: 4,
  maxCamera: 8,
  maxLifts: 3,
  maxCustomProps: 6,
  maxSolids: 16,
  titleChars: 22,
  labelChars: 12,
  valueChars: 8,
  unitChars: 4,
  legendItems: 5,
  legendChars: 12,
  maxReadoutSteps: 8,
  maxCubes: 12,
  maxValue: 999999,
  minBoardSeconds: 2,
  // The longest stretch, in seconds, in which nothing new happens apart from
  // the drift and the moving things. The AI review is told the same number.
  maxStillSeconds: 4,
} as const;

export const TIMING = {
  snap: 2,
  // A prop that arrives drops in with a squash over this many frames.
  drop: 12,
  // A route draws ahead over this many frames; a mover takes `move` to travel it.
  draw: 20,
  move: 40,
  // A pin builds (dot, leader, rule, text) over this many frames.
  pin: 18,
  // The camera eases to a new view over this many frames.
  glide: 24,
  // A lift and a cutaway take this long.
  lift: 14,
  cut: 16,
  // The readout rolls to a new value over this many frames.
  roll: 18,
  // The legend rises in over this many frames.
  legend: 12,
  readFrames: 20,
} as const;

export const GEOMETRY = {
  // The board's projection at zoom 1: tile size in pixels and the screen point of tile (0, 0).
  k: 60,
  cx: 540,
  cy: 650,
  slab: 1.05,
  zoomMax: 2,
  // The band the board is drawn in: under the readout, above the caption card.
  bandTop: 590,
  bandBottom: 1335,
  titleTop: 236,
  readoutTop: 330,
  legendTop: 1640,
  safeLeft: 70,
  safeRight: 1010,
} as const;

export interface Area {
  kind: string;
  /** Tile rectangle [x0, y0, x1, y1], whole or half tiles. */
  rect: [number, number, number, number];
}

export interface PropItem {
  id: string;
  what: string;
  /** Its footprint's centre, in tiles. */
  at: [number, number];
  color?: string;
  /** Drawn larger or smaller than its tile (0.6 to 1.6). */
  scale?: number;
  /** The frame it drops in on; absent, it is there when the board starts. */
  enter?: number;
}

export interface Route {
  id: string;
  points: [number, number][];
  color: string;
  /** The frame it starts to draw ahead. */
  at: number;
}

export interface Mover {
  route: string;
  what: string;
  color?: string;
  at: number;
  /** Travels the route backwards (an answer coming home). */
  back?: boolean;
}

export interface Pin {
  on: string;
  label: string;
  value?: string;
  unit?: string;
  at: number;
  /** Which way its rule runs from the leader. */
  side?: "left" | "right";
}

export interface CameraMove {
  at: number;
  /** A prop id to centre on; absent, the whole board. */
  focus?: string;
  zoom?: number;
}

export interface Lift {
  prop: string;
  at: number;
}

export interface Cutaway {
  prop: string;
  at: number;
  /** Up to 3 small props shown inside once its front walls are gone. */
  inside: string[];
}

export interface Explode {
  prop: string;
  at: number;
}

export interface Board {
  start: number;
  areas: Area[];
  props: PropItem[];
  routes?: Route[];
  movers?: Mover[];
  pins?: Pin[];
  camera?: CameraMove[];
  lifts?: Lift[];
  cutaways?: Cutaway[];
  explodes?: Explode[];
}

export interface Readout {
  label: string;
  unit: string;
  steps: { value: number; at: number; red?: boolean }[];
  /** One Isotype cube per `per` units of the value, in this colour. */
  cubes?: { per: number; color: string };
}

export interface CustomProp {
  id: string;
  solids: Solid[];
  main: string;
  height: number;
}

export interface IsometricData {
  title: string;
  readout?: Readout;
  boards: Board[];
  legend?: { at: number; items: { color: string; label: string }[] };
  customProps?: CustomProp[];
}

/** The frames at which something new happens on a board, sorted. */
export function eventFrames(b: Board): number[] {
  const out = [b.start];
  for (const p of b.props) if (p.enter !== undefined) out.push(p.enter);
  for (const r of b.routes ?? []) out.push(r.at);
  for (const m of b.movers ?? []) out.push(m.at);
  for (const p of b.pins ?? []) out.push(p.at);
  for (const c of b.camera ?? []) out.push(c.at);
  for (const l of b.lifts ?? []) out.push(l.at);
  for (const c of b.cutaways ?? []) out.push(c.at);
  for (const e of b.explodes ?? []) out.push(e.at);
  return [...new Set(out)].sort((a, c) => a - c);
}

/** Number text as the readout shows it: grouped by commas. */
export function grouped(n: number): string {
  const s = String(Math.round(Math.abs(n)));
  let out = "";
  for (let i = 0; i < s.length; i++) {
    if (i > 0 && (s.length - i) % 3 === 0) out += ",";
    out += s[i];
  }
  return n < 0 ? `-${out}` : out;
}
