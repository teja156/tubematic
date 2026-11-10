/**
 * The Whiteboard contract: the shape of `props.whiteboard`, and every limit,
 * size and timing the renderer and the validator share.
 *
 * Keep in sync: mcp/whiteboard.py mirrors BOARD, SIZES, LIMITS, TIMING, SPEED,
 * FLOOR, LAYOUTS, INKS, MARKS and the functions textWidth, wrapText,
 * itemNatural and itemFloor. mcp/tests/test_whiteboard.py reads the constants
 * from this file and runs the shared cases in
 * mcp/tests/fixtures/whiteboard_contract.json on both sides, so a drift fails a
 * test instead of a render.
 *
 * All sizes are board ("world") pixels. At the camera's resting zoom of 1, one
 * world pixel is one video pixel, so a size here is its size on a phone.
 */
import { GLYPH_EM } from "./glyphs";

/** One region is one screen of board: as wide as the frame, as tall as the
 *  writing band. Regions sit in a grid of two columns, in snake order. */
export const BOARD = {
  regionW: 1080,
  regionH: 1040,
  gapX: 160,
  gapY: 240,
  /** Screen y of a resting region's centre: the middle of the writing band,
   *  14% to 68% of the frame height, above the captions. */
  bandCenterY: 787,
  /** Inner padding of a slot around its content. */
  pad: 10,
};

export const SIZES = {
  text: 68,
  big: 92,
  formula: 80,
  label: 58,
  lineHeight: 1.15,
};

export const LIMITS = {
  minRegions: 2,
  maxRegions: 6,
  textLines: 2,
  labelLines: 2,
  maxHighlightsPerRegion: 1,
  maxStillSeconds: 3.5,
  recapMinSeconds: 2,
  recapMaxSeconds: 8,
};

export const TIMING = {
  /** The marker starts an item this many frames after its word. */
  lag: 12,
  /** The camera's glide to a region, from the region's startFrame. */
  glide: 42,
  /** A region, an item or the recap must start within this many frames of a word. */
  snap: 2,
  /** Frames an item stays on screen, finished, before the camera may leave. */
  read: 15,
  /** Frames the marker needs between two items. */
  gap: 2,
  /** The recap's pull-back to the whole board. */
  recapPull: 30,
  /** Frames between the numbers that pop onto the regions in the recap. */
  recapNumberStep: 6,
};

/** Natural drawing time, frames per character (spaces excluded) or per item.
 *  Body text is about 16 characters a second, a big title about 7.5. */
export const SPEED = {
  text: 1.875,
  big: 4,
  formula: 2.5,
  label: 1.875,
  doodle: 30,
  arrow: 14,
  mark: 12,
};

/** The fastest the marker may go, so writing still reads as writing. */
export const FLOOR = {
  text: 0.9,
  formula: 1.0,
  minText: 8,
  doodle: 18,
  arrow: 8,
  mark: 8,
};

export type Layout = "stack" | "pair" | "compare" | "focus";
export type Rect = [x: number, y: number, w: number, h: number];

/** Slot rectangles, relative to a region's top-left corner. */
export const LAYOUTS: Record<Layout, Record<string, Rect>> = {
  stack: {
    "1": [60, 60, 960, 230],
    "2": [60, 290, 960, 230],
    "3": [60, 520, 960, 230],
    "4": [60, 750, 960, 230],
  },
  pair: {
    top: [60, 60, 960, 200],
    left: [60, 280, 450, 480],
    right: [570, 280, 450, 480],
    bottom: [60, 780, 960, 200],
  },
  compare: {
    left_title: [60, 60, 450, 150],
    right_title: [570, 60, 450, 150],
    left_1: [60, 230, 450, 230],
    left_2: [60, 470, 450, 230],
    left_3: [60, 710, 450, 230],
    right_1: [570, 230, 450, 230],
    right_2: [570, 470, 450, 230],
    right_3: [570, 710, 450, 230],
  },
  focus: {
    top: [60, 60, 960, 220],
    center: [60, 300, 960, 440],
    bottom: [60, 760, 960, 220],
  },
};

export const INKS = {
  black: "#23262c",
  blue: "#2a5cb3",
  orange: "#d97757",
} as const;
export type Ink = keyof typeof INKS;
export const HIGHLIGHTER = "#FFE45C";
export const BOARD_COLOR = "#FBFBFB";

export const MARKS = ["highlight", "underline", "circle", "box", "cross"] as const;
export type MarkKind = (typeof MARKS)[number];
export const ITEM_KINDS = ["text", "formula", "doodle", "arrow", ...MARKS] as const;
export type ItemKind = (typeof ITEM_KINDS)[number];

type Base = { id: string; at: number; ink?: Ink };
export type TextItem = Base & { kind: "text"; slot: string; text: string; big?: boolean };
export type FormulaItem = Base & { kind: "formula"; slot: string; text: string };
export type DoodleItem = Base & { kind: "doodle"; slot: string; doodle: string; label?: string };
export type ArrowItem = Base & { kind: "arrow"; from: string; to: string };
export type MarkItem = Base & { kind: MarkKind; target: string };
export type WBItem = TextItem | FormulaItem | DoodleItem | ArrowItem | MarkItem;
export type PlacedItem = TextItem | FormulaItem | DoodleItem;

export type WBRegion = { startFrame: number; layout: Layout; items: WBItem[] };
export type WhiteboardData = { regions: WBRegion[]; recapFrame: number };

export const isPlaced = (it: WBItem): it is PlacedItem =>
  it.kind === "text" || it.kind === "formula" || it.kind === "doodle";

/** Characters the bundled font can draw; anything else would fall back to
 *  another typeface mid-word. */
export const hasGlyph = (ch: string) => ch in GLYPH_EM;

/** Width of a string at a font size, from the font's own advance widths. */
export function textWidth(s: string, size: number): number {
  let em = 0;
  for (const ch of s) em += GLYPH_EM[ch] ?? 0.75;
  return em * size;
}

/** Greedy word wrap into lines no wider than `width`. A word wider than the
 *  line on its own is returned on its own line; callers treat that as too long. */
export function wrapText(text: string, size: number, width: number): string[] {
  const words = text.trim().split(/\s+/).filter(Boolean);
  const lines: string[] = [];
  let cur = "";
  for (const w of words) {
    const next = cur ? `${cur} ${w}` : w;
    if (cur && textWidth(next, size) > width) {
      lines.push(cur);
      cur = w;
    } else {
      cur = next;
    }
  }
  if (cur) lines.push(cur);
  return lines;
}

const inked = (s: string) => s.replace(/\s+/g, "").length;

/** Frames the item takes at its natural pace. */
export function itemNatural(it: WBItem): number {
  switch (it.kind) {
    case "text":
      return Math.round(inked(it.text) * (it.big ? SPEED.big : SPEED.text));
    case "formula":
      return Math.round(inked(it.text) * SPEED.formula);
    case "doodle":
      return SPEED.doodle + Math.round(inked(it.label ?? "") * SPEED.label);
    case "arrow":
      return SPEED.arrow;
    default:
      return SPEED.mark;
  }
}

/** The part of a labelled doodle's `dur` frames spent drawing the doodle; the
 *  rest writes the label. Squeezed below its natural time, each part keeps its
 *  own floor, so the label is never written faster than text may be. */
export function doodleShare(it: DoodleItem, dur: number): number {
  if (!it.label) return 1;
  const nat = itemNatural(it);
  const flo = itemFloor(it);
  if (dur >= nat) return SPEED.doodle / nat;
  const t = nat > flo ? Math.max(0, (dur - flo) / (nat - flo)) : 0;
  return (FLOOR.doodle + t * (SPEED.doodle - FLOOR.doodle)) / dur;
}

/** The fewest frames the item may be squeezed into. */
export function itemFloor(it: WBItem): number {
  switch (it.kind) {
    case "text":
      return Math.max(FLOOR.minText, Math.round(inked(it.text) * FLOOR.text));
    case "formula":
      return Math.max(FLOOR.minText, Math.round(inked(it.text) * FLOOR.formula));
    case "doodle":
      return FLOOR.doodle + (it.label ? Math.max(FLOOR.minText, Math.round(inked(it.label) * FLOOR.text)) : 0);
    case "arrow":
      return FLOOR.arrow;
    default:
      return FLOOR.mark;
  }
}
