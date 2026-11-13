/*
 * The Process Cast data contract: the shape of `props.processCast`, its limits,
 * its catalogues (bodies, tints, faces, marks, stations, props) and the
 * geometry the MCP server checks before render.
 *
 * Process Cast tells an invisible process with a cast of drawn parts that have
 * faces (a packet, a cell, a byte made of unit blocks), standing at stations
 * along one long ground line, and a camera that travels from station to
 * station. The cast never talks: faces show feelings only.
 *
 * Keep in sync: mcp/process_cast.py holds the Python side of every constant
 * here, and the style pack's `extra` lists the catalogues for the agent. Both
 * are written from this file by character-tools/sync-contract.mjs (never edit
 * them by hand); mcp/tests/test_process_cast.py fails when they disagree.
 */

export const W = 1080;
export const H = 1920;

export const LIMITS = {
  maxCast: 6,
  maxStations: 6,
  maxEvents: 120,
  nameChars: 14,
  signChars: 14,
  cardChars: 18,
  maxUnits: 16,
  maxClones: 3,
  maxStillSeconds: 3,
  minStationSeconds: 1.5,
} as const;

export const TIMING = {
  // An actor's entrance pops in over this many frames; nothing else of it starts before it ends.
  enter: 8,
  // A hop within a station, and a trip to another station (two hops while the camera glides).
  hop: 10,
  trip: 20,
  // The camera's glide from one station to the next.
  glide: 20,
  // A card handed from one actor to another flies for this long.
  hand: 12,
  // Clones show as flat silhouettes for this long before their outline and face pop on.
  silhouette: 2,
  // A merge or a join: the others hop in and vanish over this long.
  merge: 12,
  // Two changes to one actor closer than this read as a twitch.
  minActorGap: 6,
  // A mark beside an actor's head shows for this long.
  mark: 45,
} as const;

export const GEOMETRY = {
  // The ground line every station stands on, and where stations sit along it.
  groundY: 1190,
  stationGap: 1080,
  // Actor slots, as x offsets from a station's centre: three before its furniture,
  // five across an open stage.
  slots: [-390, -160, 70],
  stageSlots: [-420, -210, 0, 210, 420],
  // The furniture stands to the right of the slots, its centre this far from the station's.
  furnitureX: 330,
  // The station's hanging sign.
  signY: 330,
  // An actor's body at scale 1 (a units body is sized by its count instead).
  actorW: 190,
  actorH: 250,
  unitPx: 80,
  // Actors on an open stage are drawn smaller so five fit.
  stageScale: 0.9,
  // Two bodies, or a body and furniture, may touch by this much and no more.
  overlapTolerance: 12,
  // A name tag or card over an actor in an odd slot sits this much higher, so neighbours' tags clear each other.
  tagStagger: 64,
  // Props are drawn this much larger than their library box, so their labels read on a phone.
  propScale: 1.5,
  // A focused actor grows by this much; the others at its station shrink by `focusOthers`.
  focusScale: 1.3,
  focusOthers: 0.85,
} as const;

export const BODIES = ["bean", "blob", "block", "gem", "units"] as const;
export const TINTS = {
  teal: "#2F8D89",
  olive: "#A6B23B",
  coral: "#CC5040",
  sky: "#6E9CC8",
  mustard: "#D9A93A",
  plum: "#8A5A8C",
  cream: "#F4ECD9",
} as const;
export const ACCESSORIES = ["none", "glasses", "tuft", "sprout", "cap"] as const;
export const FACES = ["neutral", "happy", "curious", "proud", "surprised", "worried", "sad"] as const;
export const MARKS = ["question", "exclaim", "sweat", "check", "cross", "idea"] as const;
export const ENTRANCES = ["pop", "drop", "slide"] as const;
export const CAMERA_MOVES = ["glide", "cut"] as const;
export const EVENT_TYPES = ["enter", "move", "exit", "clone", "merge", "react", "look", "carry", "hand", "prop", "join", "focus", "camera"] as const;

/*
 * Station furniture. Each kind is drawn once, by hand, in the style's pencil
 * hatching (./stations.tsx), standing on the ground at the station's
 * furniture spot. `top` is the height its top surface stands above the
 * ground, where a prop sits (0 for a stage, which has no furniture).
 */
export const STATIONS = {
  desk: { w: 300, h: 170, top: 150 },
  board: { w: 300, h: 330, top: 0 },
  door: { w: 230, h: 380, top: 0 },
  shelf: { w: 280, h: 300, top: 300 },
  machine: { w: 290, h: 280, top: 280 },
  server: { w: 220, h: 360, top: 360 },
  cell: { w: 340, h: 300, top: 0 },
  stage: { w: 0, h: 0, top: 0 },
} as const;

/*
 * The prop library: things a station holds on its furniture (or, at a station
 * without a top, in front of it). `w` and `h` are its box at scale 1: every
 * pixel its drawing can reach. `text` is the most characters its label takes
 * (0 when it has none).
 */
export const PROPS = {
  card: { w: 200, h: 120, text: 18 },
  envelope: { w: 190, h: 130, text: 14 },
  packet: { w: 170, h: 130, text: 10 },
  box: { w: 170, h: 150, text: 10 },
  file: { w: 140, h: 180, text: 12 },
  folder: { w: 190, h: 150, text: 12 },
  key: { w: 170, h: 90, text: 0 },
  lock: { w: 120, h: 160, text: 0 },
  coin: { w: 120, h: 120, text: 0 },
  cookie: { w: 130, h: 130, text: 0 },
  gear: { w: 140, h: 140, text: 0 },
  bug: { w: 150, h: 140, text: 0 },
  shield: { w: 130, h: 160, text: 0 },
  stamp: { w: 130, h: 160, text: 0 },
  clock: { w: 140, h: 150, text: 0 },
  phone: { w: 110, h: 190, text: 12 },
  laptop: { w: 230, h: 160, text: 14 },
  bulb: { w: 110, h: 160, text: 0 },
  magnifier: { w: 160, h: 160, text: 0 },
  molecule: { w: 170, h: 150, text: 0 },
  virus: { w: 150, h: 150, text: 0 },
  battery: { w: 180, h: 100, text: 0 },
} as const;

/*
 * A prop the agent draws for one video when the library lacks it: a TSX file
 * beside the video's other generated files (generated/<video_id>/prop-<name>.tsx),
 * modelled on a library prop and using the same helpers (./ink).
 */
export const CUSTOM = { maxProps: 8, minSide: 60, maxSide: 400, maxText: 18, maxActs: 0 } as const;

export type Body = (typeof BODIES)[number];
export type Tint = keyof typeof TINTS;
export type Accessory = (typeof ACCESSORIES)[number];
export type Face = (typeof FACES)[number];
export type Mark = (typeof MARKS)[number];
export type StationKind = keyof typeof STATIONS;
export type PropId = keyof typeof PROPS;

export type PCActor = { id: string; name?: string; body: Body; tint: Tint; units?: number; accessory?: Accessory };
export type PCStation = { id: string; kind: StationKind; sign: string };
export type PCEvent =
  | { type: "enter"; frame: number; who: string; station: string; slot: number; from?: (typeof ENTRANCES)[number] }
  | { type: "move"; frame: number; who: string; station: string; slot: number }
  | { type: "exit"; frame: number; who: string }
  | { type: "clone"; frame: number; who: string; count: number }
  | { type: "merge"; frame: number; who: string }
  | { type: "react"; frame: number; who: string; face: Face; mark?: Mark }
  | { type: "look"; frame: number; who: string; at: string }
  | { type: "carry"; frame: number; who: string; text: string }
  | { type: "hand"; frame: number; from: string; to: string }
  | { type: "prop"; frame: number; station: string; prop: string; text?: string }
  | { type: "join"; frame: number; who: string; with: string }
  | { type: "focus"; frame: number; who: string }
  | { type: "camera"; frame: number; station: string; move?: (typeof CAMERA_MOVES)[number] };
export type PCCustomProp = { id: string; src: string; w: number; h: number; text?: number };
export type ProcessCastData = {
  cast: PCActor[];
  stations: PCStation[];
  customProps?: PCCustomProp[];
  events: PCEvent[];
};

/** The ids a clone of `who` gets: who2, who3... */
export const cloneId = (who: string, n: number) => `${who}${n + 1}`;

/** A station's centre along the world, from its index. */
export const stationX = (index: number) => index * GEOMETRY.stationGap;

/** The x of a slot at a station, along the world. */
export function slotX(index: number, kind: StationKind, slot: number): number {
  const slots = kind === "stage" ? GEOMETRY.stageSlots : GEOMETRY.slots;
  return stationX(index) + slots[slot];
}

export const slotCount = (kind: StationKind) => (kind === "stage" ? GEOMETRY.stageSlots.length : GEOMETRY.slots.length);

/** The width and height of an actor's body at scale 1: a units body is sized by its count. */
export function bodySize(body: Body, units = 1): { w: number; h: number } {
  if (body !== "units") return { w: GEOMETRY.actorW, h: GEOMETRY.actorH };
  const n = Math.max(1, Math.min(units, LIMITS.maxUnits));
  const cols = Math.ceil(Math.sqrt(n));
  const rows = Math.ceil(n / cols);
  return { w: cols * GEOMETRY.unitPx, h: rows * GEOMETRY.unitPx };
}

/**
 * Where a prop's centre is at a station: resting on its furniture's top, pinned
 * to the face of furniture without one (a board, a door, a cell), or held up
 * over the middle of an open stage.
 */
export function propCentre(index: number, kind: StationKind, prop: { w: number; h: number }): { x: number; y: number } {
  const st = STATIONS[kind];
  if (kind === "stage") return { x: stationX(index), y: GEOMETRY.groundY - 460 };
  const x = stationX(index) + GEOMETRY.furnitureX;
  if (st.top > 0) return { x, y: GEOMETRY.groundY - st.top - (prop.h * GEOMETRY.propScale) / 2 };
  return { x, y: GEOMETRY.groundY - st.h * 0.55 };
}
