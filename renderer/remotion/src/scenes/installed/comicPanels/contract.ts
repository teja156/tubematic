/*
 * The Comic Panels data contract: the shape of `props.comicPanels`, its limits,
 * its catalogues (layouts, tones, cast, poses, faces, props, sound effects) and
 * the geometry the MCP server checks before render.
 *
 * A Comic Panels video is told as comic pages built on screen: each page is a
 * layout of 3 or 4 panels on cream newsprint; a panel inks in on its word, and
 * the camera reads panel by panel, then pulls back to the whole page. Inside a
 * panel, characters (a house hero, invented people with knobs, a villain
 * silhouette) and props appear on words, with balloons, caption boxes, drawn
 * sound effects and speed lines.
 *
 * Keep in sync: mcp/comic_panels.py holds the Python side of every constant
 * here, and the style pack's `extra` lists the catalogues for the agent. Both
 * are written from this file by character-tools/sync-contract.mjs (never edit
 * them by hand); mcp/tests/test_comic_panels.py fails when they disagree.
 */

export const W = 1080;
export const H = 1920;

export const LIMITS = {
  maxPages: 3,
  maxCast: 4,
  maxItemsPerPanel: 8,
  titleChars: 28,
  balloonChars: 40,
  captionChars: 40,
  sfxChars: 10,
  maxStillSeconds: 3,
  minPanelSeconds: 1.5,
  // A balloon or caption may not repeat this many narration words in a row: the captions carry the words.
  echoWords: 5,
} as const;

export const TIMING = {
  // A panel's border draws, its art wipes in and its tone lands over this long, from its start.
  inkIn: 18,
  // The camera moves from one panel to the next over this long.
  read: 18,
  // An item pops in over this long; another item may not start in the same panel closer than `minItemGap`.
  pop: 10,
  minItemGap: 4,
  // A hit: the camera punches in and shakes for this long.
  hit: 8,
  // The pull back to the whole page.
  pullBack: 20,
  // An item this close to its panel's end is cut before it is seen.
  endMargin: 6,
} as const;

// The page, in page units: a 1000 x 1700 portrait page framed on the frame.
export const PAGE = {
  w: 1000,
  h: 1700,
  // The title bar at the top of every page.
  titleH: 120,
  gutter: 20,
  margin: 24,
  // The page on screen when the camera shows all of it: its top-left corner and scale.
  x: 40,
  y: 120,
  scale: 1,
} as const;

/*
 * Page layouts: each panel's rectangle in page units (x, y, w, h), under the
 * title bar. The panels are read in this order.
 */
export const LAYOUTS = {
  stack3: [[24, 140, 952, 500], [24, 660, 952, 500], [24, 1180, 952, 496]],
  stack4: [[24, 140, 952, 370], [24, 530, 952, 370], [24, 920, 952, 370], [24, 1310, 952, 366]],
  "2+1": [[24, 140, 466, 760], [510, 140, 466, 760], [24, 920, 952, 756]],
  "1+2": [[24, 140, 952, 760], [24, 920, 466, 756], [510, 920, 466, 756]],
  "2+2": [[24, 140, 466, 760], [510, 140, 466, 760], [24, 920, 466, 756], [510, 920, 466, 756]],
} as const;

export const TONES = {
  cream: "#fffaf0",
  pink: "#f7c9c6",
  blue: "#c4e0f2",
  yellow: "#fbe9a0",
  green: "#cfe6c4",
  dark: "#2a2d3a",
} as const;

export const CAST_KINDS = ["hero", "person", "villain"] as const;
export const HAIRS = ["spiky", "bob", "bun", "short", "bald", "curly"] as const;
export const OUTFITS = ["blue", "red", "green", "yellow", "purple", "grey"] as const;
export const SKINS = ["light", "tan", "brown", "dark"] as const;
export const POSES = ["stand", "point", "panic", "cheer", "think", "type", "shrug", "facepalm"] as const;
export const FACES = ["neutral", "happy", "shocked", "worried", "angry", "smug", "sad", "grin"] as const;
export const BALLOONS = ["speech", "thought", "shout"] as const;
export const LINES = ["speed", "focus"] as const;
export const ITEM_TYPES = ["actor", "prop", "balloon", "caption", "sfx", "lines", "hit"] as const;

/*
 * The prop library. Each prop is drawn once, in heavy black ink with flat
 * colour (./props/), centred on (0, 0). `w` and `h` are its box at scale 1, in
 * page units. `text` is the most characters its text slot takes (0 when none).
 */
export const PROPS = {
  phone: { w: 150, h: 260, text: 24 },
  laptop: { w: 300, h: 220, text: 24 },
  inbox: { w: 420, h: 220, text: 30 },
  login: { w: 340, h: 260, text: 20 },
  browser: { w: 420, h: 120, text: 24 },
  monitor: { w: 320, h: 260, text: 24 },
  server: { w: 160, h: 260, text: 0 },
  lock: { w: 120, h: 160, text: 0 },
  key: { w: 170, h: 90, text: 0 },
  shield: { w: 150, h: 180, text: 0 },
  bug: { w: 160, h: 150, text: 0 },
  virus: { w: 160, h: 160, text: 0 },
  cell: { w: 180, h: 180, text: 0 },
  bomb: { w: 160, h: 170, text: 0 },
  money: { w: 200, h: 120, text: 8 },
  document: { w: 160, h: 210, text: 20 },
  envelope: { w: 200, h: 140, text: 16 },
  rocket: { w: 140, h: 260, text: 0 },
  planet: { w: 220, h: 220, text: 0 },
  clock: { w: 150, h: 160, text: 0 },
  sign: { w: 260, h: 160, text: 16 },
  door: { w: 180, h: 300, text: 0 },
} as const;

export const SCALE = { min: 0.5, max: 1.6 } as const;

/*
 * A prop the agent draws for one video when the library lacks it: a TSX file
 * beside the video's other generated files (generated/<video_id>/prop-<name>.tsx),
 * modelled on a library prop and using the same helpers (./ink).
 */
export const CUSTOM = { maxProps: 8, minSide: 60, maxSide: 500, maxText: 24, maxActs: 0 } as const;

// A character in a panel, in page units at scale 1: its box from the waist up (panels frame characters as busts).
export const ACTOR = { w: 260, h: 300 } as const;

export type Layout = keyof typeof LAYOUTS;
export type Tone = keyof typeof TONES;
export type CastKind = (typeof CAST_KINDS)[number];
export type Pose = (typeof POSES)[number];
export type Face = (typeof FACES)[number];
export type PropId = keyof typeof PROPS;

export type CPActor = { id: string; kind: CastKind; hair?: (typeof HAIRS)[number]; outfit?: (typeof OUTFITS)[number]; skin?: (typeof SKINS)[number] };
export type CPItem =
  | { type: "actor"; frame: number; who: string; pose: Pose; face: Face; x: number; y: number; scale?: number; flip?: boolean; id?: string }
  | { type: "prop"; frame: number; prop: string; x: number; y: number; scale?: number; text?: string; id?: string }
  | { type: "balloon"; frame: number; kind: (typeof BALLOONS)[number]; text: string; x: number; y: number; to: string }
  | { type: "caption"; frame: number; text: string }
  | { type: "sfx"; frame: number; text: string; x: number; y: number }
  | { type: "lines"; frame: number; kind: (typeof LINES)[number] }
  | { type: "hit"; frame: number };
export type CPPanel = { start: number; tone: Tone; items: CPItem[] };
export type CPPage = { start: number; layout: Layout; title?: string; panels: CPPanel[] };
export type CPCustomProp = { id: string; src: string; w: number; h: number; text?: number };
export type ComicPanelsData = {
  cast: CPActor[];
  pages: CPPage[];
  // The frame the camera pulls back to the last page for its ending, or absent.
  splash?: number;
  customProps?: CPCustomProp[];
};

/** A panel's rectangle in page units. */
export const panelRect = (layout: Layout, i: number) => LAYOUTS[layout][i] as readonly [number, number, number, number];

/** An item's box in page units, placed at (x, y), fractions of its panel. */
export function itemBox(rect: readonly number[], x: number, y: number, w: number, h: number, scale = 1): [number, number, number, number] {
  const cx = rect[0] + x * rect[2], cy = rect[1] + y * rect[3];
  return [cx - (w * scale) / 2, cy - (h * scale) / 2, cx + (w * scale) / 2, cy + (h * scale) / 2];
}

/** A balloon's box, sized from its text: up to three lines of about 16 characters. */
export function balloonSize(text: string): { w: number; h: number } {
  const lines = Math.min(3, Math.max(1, Math.ceil(text.length / 16)));
  const chars = Math.min(16, text.length);
  return { w: Math.max(140, chars * 20 + 70), h: lines * 46 + 60 };
}

/** A sound effect's box: slammed capitals about 70 units tall. */
export const sfxSize = (text: string) => ({ w: Math.max(1, text.length) * 52 + 40, h: 110 });
