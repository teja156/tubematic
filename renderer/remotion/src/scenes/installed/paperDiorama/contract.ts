/*
 * The Paper Diorama data contract: the shape of `props.paperDiorama`, its
 * limits and timings, and the stage geometry the MCP server checks before
 * render.
 *
 * Keep in sync: mcp/paper_diorama.py holds the Python side of every constant
 * here, and tubematic_core/style_packs/paper_diorama.json lists the rooms,
 * props, colours, expressions, accessories, events and cuts for the agent.
 * mcp/tests/test_paper_diorama.py reads this file and fails when they
 * disagree, and both sides run the shared cases in
 * mcp/tests/fixtures/paper_diorama_contract.json.
 *
 * The frame has fixed zones, so nothing the agent places can land on another
 * zone: the taped banner near the top, the paper room with its floor line, the
 * stage of slots the props and the critter stand in, and the captions low on
 * the floor (the shared Subtitles component, "tags" look). The agent never
 * writes a coordinate: a prop stands in a named slot at a named level.
 *
 * Rooms are the papercut-explainer kit's code-drawn sets, rendered once to
 * JPEGs (public/paperDiorama/rooms/, MIT). Props, the critter and stamps are
 * pieces of paper painted once onto a canvas each (paint.ts) and moved, never
 * repainted, so a frame costs about what its transforms cost.
 */

export const W = 1080;
export const H = 1920;

// The room's paper colours. A piece's fill names one of these, never a hex
// value, so every prop in every video shares the kit's palette.
export const COLORS = {
  cream: "#DACEC0", creamHi: "#E8DFD3", creamLo: "#BFB2A2", paper: "#F3E6D3", tape: "#C3B284",
  ink: "#1C1B17", inkSoft: "#3A3832", white: "#F7F3EC",
  wood: "#7F5231", woodLo: "#5E3B22", woodHi: "#95653F",
  brass: "#C89B4A", brassLo: "#9C7433", metal: "#B1B9BC", metalLo: "#8C9598",
  board: "#2E3235", boardLo: "#202326", boardHi: "#3E4347",
  sage: "#8A9A86", sageLo: "#667563",
  screen: "#1B1726", screenHi: "#2A2438", screenText: "#E9E2F2",
  hero: "#D67354", heroLo: "#A9553B", cap: "#3968AD", capLo: "#284C80",
  tag: "#C9573C", purple: "#4E3881",
  go: "#2DA34D", goDim: "#165329", nogo: "#D63A2B", nogoDim: "#4D140D",
  amber: "#F3A53B", amberDim: "#6B4716", yellow: "#F5C542", pink: "#F4A7B9", sky: "#8FB8D8", skyLo: "#5D7896",
} as const;
export type ColorName = keyof typeof COLORS;
export const COLOR_NAMES = Object.keys(COLORS) as ColorName[];

// The rooms: the kit's eight code-drawn sets. floorY is where a prop standing
// on the floor puts its bottom edge, measured per set by the kit's author.
export const ROOMS = {
  "bank-vault": { floorY: 1450, mood: "cool" },
  courtroom: { floorY: 1450, mood: "warm" },
  warehouse: { floorY: 1450, mood: "warm" },
  "mission-control": { floorY: 1440, mood: "night" },
  "airport-gate": { floorY: 1440, mood: "day" },
  "subway-platform": { floorY: 1440, mood: "cool" },
  diner: { floorY: 1440, mood: "warm" },
  "bedroom-day": { floorY: 1450, mood: "day" },
} as const;
export type RoomName = keyof typeof ROOMS;
export const ROOM_NAMES = Object.keys(ROOMS) as RoomName[];

// Where a prop can stand: five slots across the stage, three levels up it.
// A slot is the centre x of what stands there; a level is how far above the
// floor its bottom edge sits.
export const SLOTS = { l: 190, cl: 365, c: 540, cr: 715, r: 890 } as const;
export type SlotName = keyof typeof SLOTS;
export const SLOT_NAMES = Object.keys(SLOTS) as SlotName[];
export const LEVELS = { floor: 0, shelf: 420, air: 760 } as const;
export type LevelName = keyof typeof LEVELS;
export const LEVEL_NAMES = Object.keys(LEVELS) as LevelName[];
export const SCALES = { s: 0.7, m: 1, l: 1.35 } as const;
export type ScaleName = keyof typeof SCALES;
export const SCALE_NAMES = Object.keys(SCALES) as ScaleName[];

// The fixed zones, in frame pixels.
export const ZONES = {
  bannerTop: 270, bannerBottom: 400, bannerMaxWidth: 860,
  stageTop: 430,
  // Nothing the agent places reaches below this: the captions sit lower.
  stageBottom: 1480,
} as const;

export const CRITTER = {
  size: 240,
  expressions: ["idle", "happy", "shock", "worried", "squint", "sleep"],
  accessories: ["none", "cap", "hardhat", "headset", "glasses", "bowtie", "beret", "visor"],
  bobAmp: 3, bobPeriod: 36, blinkEvery: 83, blinkFrames: 3,
} as const;
export type Expression = (typeof CRITTER.expressions)[number];
export type Accessory = (typeof CRITTER.accessories)[number];

export const EVENTS = ["exit", "move", "swap", "expr", "hop", "stamp", "ring", "route", "label", "zoom"] as const;
export type EventKind = (typeof EVENTS)[number];
export const ENTERS = ["pop", "slide", "drop"] as const;
export type Enter = (typeof ENTERS)[number];
export const CUTS = ["cut", "tear"] as const;
export type Cut = (typeof CUTS)[number];
export const SHAPES = ["rect", "ellipse", "poly", "text"] as const;
export const FONTS = ["banner", "label", "mono"] as const;

export const LIMITS = {
  maxSets: 24,
  minSetSeconds: 1.2,
  maxItemsPerSet: 6,
  maxEvents: 160,
  bannerChars: 28,
  labelChars: 16,
  stampChars: 12,
  textChars: 14,
  maxCustomProps: 8,
  maxPieces: 60,
  // A custom prop's own box, in pixels at scale m.
  maxPropW: 520,
  maxPropH: 620,
  maxZooms: 3,
  // The longest stretch, in seconds, with nothing new on stage (a cut or an
  // event); the critter's idle bob does not count. The AI review is told it.
  maxStillSeconds: 3,
} as const;

export const TIMING = {
  // A set start or an event lands within this many frames of a word's start.
  snap: 2,
  pop: 8,
  slide: 10,
  drop: 9,
  exit: 6,
  move: 12,
  swap: 2,
  hop: 12,
  stamp: 6,
  ring: 9,
  route: 18,
  label: 6,
  zoomIn: 4,
  zoomHold: 14,
  zoomOut: 12,
  tear: 12,
  zoomScale: 1.18,
  // An event this close to its set's end is never read.
  readFrames: 8,
} as const;

/** One piece of paper in a prop, in the prop's own pixels at scale m. */
export interface Piece {
  shape: (typeof SHAPES)[number];
  fill: ColorName;
  x?: number; y?: number; w?: number; h?: number; r?: number;   // rect, ellipse (x, y top-left)
  points?: [number, number][];                                  // poly
  shade?: ColorName; shadeH?: number;                           // a darker strip along the bottom
  hi?: ColorName; hiH?: number;                                  // a lighter strip along the top
  rot?: number;                                                  // degrees about the piece's centre
  text?: string; font?: (typeof FONTS)[number]; size?: number;   // text: x, y is the centre
}

export interface PropDef {
  w: number;
  h: number;
  pieces: Piece[];
}

export interface Item {
  id: string;
  prop: string;          // a library prop or one of customProps
  slot: SlotName;
  level?: LevelName;
  scale?: ScaleName;
  at: number;            // the frame it enters, on a word
  enter?: Enter;
}

export interface StageEvent {
  at: number;
  do: EventKind;
  target?: string;       // an item id, or "critter"
  to?: SlotName;         // move
  level?: LevelName;     // move, stamp
  prop?: string;         // swap
  value?: Expression;    // expr
  text?: string;         // stamp, label
  from?: string;         // route: an item id
  color?: ColorName;     // route, ring, stamp
}

export interface PaperSet {
  start: number;
  room: RoomName;
  banner: string;
  cut?: Cut;
  critter?: { slot: SlotName; face?: 1 | -1; expr?: Expression } | null;
  items?: Item[];
  events?: StageEvent[];
}

export interface PaperDioramaData {
  critter?: { color?: "hero" | "cap" | "sage" | "amber" | "purple" | "pink"; acc?: Accessory };
  customProps?: Record<string, PropDef>;
  sets: PaperSet[];
}
