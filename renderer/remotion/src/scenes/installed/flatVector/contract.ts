/*
 * The Flat Vector Science data contract: the shape of `props.flatVector`, its
 * limits and timings, and the geometry the MCP server checks before render.
 *
 * Keep in sync: mcp/flat_vector_science.py holds the Python side of every
 * constant here, and tubematic_core/style_packs/flat_vector_science.json lists
 * the catalogues for the agent. Both are written from this file by
 * renderer/remotion/flatvector-tools/sync-contract.mjs, with the shared cases
 * in mcp/tests/fixtures/flat_vector_science_contract.json; the tests on both
 * sides fail until it has run.
 *
 * The frame has fixed zones: the readout row near the top (a counter or a
 * stage title), the subject band in the middle where the props drift, the
 * scale strip under it (a rule, a scale bar, a gauge) and the captions at 78%
 * (the shared Subtitles layer). Props stand in named slots, never at
 * coordinates, and are sized by name, never by pixels.
 */
import { PROPS, type PropGroup } from "./props";

export const W = 1080;
export const H = 1920;

export const SHOT_KINDS = ["subject", "ladder", "zoom", "descent", "stages"] as const;
export const BACKDROPS = ["abyss", "ocean", "night", "sky", "strata", "inside"] as const;
export const SLOTS = ["center", "left", "right", "top", "bottom"] as const;
export const SIZES = ["s", "m", "l"] as const;
export const CUTS = ["cut", "lens", "flash", "push"] as const;
export const GROUPS: PropGroup[] = ["sea", "body", "space", "earth", "scale"];

export type ShotKind = (typeof SHOT_KINDS)[number];
export type Backdrop = (typeof BACKDROPS)[number];
export type Slot = (typeof SLOTS)[number];
export type Size = (typeof SIZES)[number];
export type Cut = (typeof CUTS)[number];

export const PROP_NAMES = Object.keys(PROPS);
/** The library by group, for the pack. */
export const CATALOGUE: Record<string, string[]> = Object.fromEntries(
  GROUPS.map((g) => [g, PROP_NAMES.filter((n) => PROPS[n].group === g)]),
);

export const LIMITS = {
  minShots: 3,
  maxShots: 12,
  maxItems: 3,
  maxPills: 2,
  maxPillParts: 2,
  pillChars: 18,
  labelChars: 14,
  valueChars: 12,
  unitChars: 4,
  minRungs: 2,
  maxRungs: 5,
  minLevels: 2,
  maxLevels: 6,
  minLayers: 2,
  maxLayers: 6,
  minSteps: 2,
  maxSteps: 5,
  maxCustomProps: 8,
  maxValue: 999999999,
  minShotSeconds: 1.5,
  // The longest stretch, in seconds, in which nothing new arrives apart from
  // the drift. The AI review is told the same number.
  maxStillSeconds: 4,
} as const;

export const TIMING = {
  // A shot start or an event lands within this many frames of a word's start.
  snap: 2,
  // A prop that arrives pops in with an overshoot over this many frames.
  pop: 15,
  // A pill grows to its width, then its text reveals.
  pillGrow: 9,
  pillReveal: 9,
  // A pill's part lights over this many frames from its word.
  light: 5,
  // A counter rolls to its new value over this many frames.
  roll: 24,
  ruleDraw: 12,
  // A ladder rung, a zoom level, a descent layer and a stage take this long to arrive.
  rung: 21,
  // Shot transitions into the shot, in frames before its start (lens, push) or around it (flash).
  lens: 18,
  push: 12,
  flash: 6,
  // Text needs this long on screen before its shot ends to be read.
  readFrames: 20,
} as const;

export const GEOMETRY = {
  // Where each slot's centre sits, in frame pixels.
  slot: {
    center: [540, 930],
    left: [300, 960],
    right: [780, 900],
    top: [540, 700],
    bottom: [540, 1150],
  } as Record<Slot, [number, number]>,
  // The longest side a prop is drawn at, by size.
  size: { s: 260, m: 460, l: 780 } as Record<Size, number>,
  // The readout row (a counter, a stage or rung title) and the scale strip.
  readoutTop: 222,
  stripY: 1260,
  safeLeft: 70,
  safeRight: 1010,
  // A pill's height, its text size, the advance of one capital in ems a fit assumes.
  pillHeight: 76,
  pillText: 40,
  capCharWidth: 0.72,
  pillMaxWidth: 940,
} as const;

/** A prop the agent drew for this video: `generated/<video_id>/prop-<name>.tsx`. */
export interface CustomProp {
  id: string;
  src: string;
  box: [number, number];
  /** The colour of its halo, if it gives light. */
  light?: string;
}

export interface Item {
  what: string;
  slot: Slot;
  size: Size;
  /** The frame it pops in on; absent, it is there when the shot starts. */
  at?: number;
  /** Faces the other way. */
  flip?: boolean;
}

export interface PillPart {
  text: string;
  /** The frame this part lights up (white, or red). */
  at: number;
  red?: boolean;
}

export interface Pill {
  /** The slot of the item it names; its leader line points there. */
  on: Slot;
  parts: PillPart[];
}

export interface Counter {
  label: string;
  value: number;
  unit: string;
  at: number;
  /** Where it rolls from; absent, from 0 (or the last shot's counter). */
  from?: number;
  red?: boolean;
}

export interface Rule {
  /** The slot of the item it measures. */
  beside: Slot;
  label: string;
  at: number;
}

interface ShotBase {
  start: number;
  backdrop: Backdrop;
  /** How the shot arrives: a cut (the default), a lens reveal, a white flash or a push through a colour. */
  cut?: Cut;
  counter?: Counter;
}

export interface SubjectShot extends ShotBase {
  kind: "subject";
  items: Item[];
  pills?: Pill[];
  rule?: Rule;
}

export interface Rung {
  what: string;
  label: string;
  value: string;
  at: number;
  red?: boolean;
}

export interface LadderShot extends ShotBase {
  kind: "ladder";
  rungs: Rung[];
}

export interface Level {
  what: string;
  /** The scale bar's label at this level ("1 M", "10 KM"). */
  label: string;
  at: number;
  red?: boolean;
}

export interface ZoomShot extends ShotBase {
  kind: "zoom";
  levels: Level[];
}

export interface Layer {
  name: string;
  value: number;
  at: number;
  what?: string;
  red?: boolean;
}

export interface DescentShot extends ShotBase {
  kind: "descent";
  label: string;
  unit: string;
  layers: Layer[];
}

export interface Step {
  what: string;
  label: string;
  at: number;
  red?: boolean;
}

export interface StagesShot extends ShotBase {
  kind: "stages";
  steps: Step[];
}

export type Shot = SubjectShot | LadderShot | ZoomShot | DescentShot | StagesShot;

export interface FlatVectorData {
  shots: Shot[];
  customProps?: CustomProp[];
}

// ── helpers both sides share ───────────────────────────────────────────────
/** The scale a prop of `box` is drawn at for a size: its longest side becomes GEOMETRY.size. */
export function propScale(box: [number, number], size: Size): number {
  return GEOMETRY.size[size] / Math.max(box[0], box[1]);
}

/** A number as a readout shows it: digits grouped by commas. */
export function grouped(n: number): string {
  const s = String(Math.floor(Math.abs(n)));
  let out = "";
  for (let i = 0; i < s.length; i++) {
    if (i > 0 && (s.length - i) % 3 === 0) out += ",";
    out += s[i];
  }
  return n < 0 ? `-${out}` : out;
}

/** The width a pill takes for its parts (text, a dot between parts, padding). */
export function pillWidth(parts: { text: string }[]): number {
  const G = GEOMETRY;
  const chars = parts.reduce((n, p) => n + p.text.length, 0);
  return Math.round(chars * G.pillText * G.capCharWidth + (parts.length - 1) * 27 + 60);
}

/** The frames at which something new arrives in a shot, sorted. */
export function eventFrames(shot: Shot): number[] {
  const out = [shot.start];
  if (shot.counter) out.push(shot.counter.at);
  switch (shot.kind) {
    case "subject":
      for (const it of shot.items) if (it.at !== undefined) out.push(it.at);
      for (const p of shot.pills ?? []) for (const part of p.parts) out.push(part.at);
      if (shot.rule) out.push(shot.rule.at);
      break;
    case "ladder":
      for (const r of shot.rungs) out.push(r.at);
      break;
    case "zoom":
      for (const l of shot.levels) out.push(l.at);
      break;
    case "descent":
      for (const l of shot.layers) out.push(l.at);
      break;
    case "stages":
      for (const s of shot.steps) out.push(s.at);
      break;
  }
  return [...new Set(out)].sort((a, b) => a - b);
}
