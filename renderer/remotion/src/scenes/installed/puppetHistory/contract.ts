/*
 * The Puppet History data contract: the shape of `props.puppetHistory`, its
 * limits, its catalogues (costumes, poses, faces, sets, hand props, countries)
 * and the geometry the MCP server checks before render.
 *
 * Puppet History tells "you are now a..." history with round-headed cut-out
 * puppets in era costumes, framed from the waist up on flat illustrated sets.
 * The video is a run of beats with hard cuts between them: a set with puppets
 * acting on the narrator's words, a document card with stamps and struck-out
 * numbers, or a flat map with regions filling in and arrows growing. A real,
 * historical person is the house puppet in a generic era costume with a name
 * plate: the rig has no likeness and no signature feature to draw.
 *
 * Keep in sync: mcp/puppet_history.py holds the Python side of every constant
 * here, and the style pack's `extra` lists the catalogues for the agent. Both
 * are written from this file by character-tools/sync-contract.mjs (never edit
 * them by hand); mcp/tests/test_puppet_history.py fails when they disagree.
 */
import world from "world-atlas/countries-110m.json";

export const W = 1080;
export const H = 1920;

export const LIMITS = {
  maxCast: 4,
  maxBeats: 14,
  maxEvents: 100,
  nameChars: 18,
  signChars: 14,
  stampChars: 10,
  dateChars: 12,
  titleChars: 22,
  cardLines: 5,
  lineChars: 26,
  strikeChars: 12,
  labelChars: 18,
  maxFocus: 8,
  maxArrows: 6,
  maxStillSeconds: 3,
  minBeatSeconds: 1.5,
  // A card line may not repeat this many narration words in a row: the captions carry the words.
  echoWords: 5,
} as const;

export const TIMING = {
  // A slide-in from the frame's edge (ease-out, then a dead stop), and a pop-in.
  slide: 16,
  pop: 8,
  // A move to another slot.
  move: 16,
  // Two changes to one puppet closer than this read as a twitch.
  minActorGap: 6,
  // A stamp lands with a kick that decays over this long.
  stamp: 7,
  // A strike-out draws, then the new value is scrawled, each over this long.
  strike: 14,
  // A map region fills in, and an arrow grows, over these.
  fill: 12,
  arrow: 18,
  // An event this close to its beat's end is cut before it is seen.
  endMargin: 6,
} as const;

export const GEOMETRY = {
  // Puppets are framed from the waist up: the waist sits on this line, hidden by the set's foreground band.
  waistY: 1640,
  frontY: 1600,
  // Three slots across the frame.
  slots: [210, 540, 870],
  puppetScale: 1,
  // A puppet's box from its waist at scale 1, hat included, and its arms' reach to each side.
  puppetW: 330,
  puppetH: 470,
  // The name plate on the foreground band under a puppet, and a held-up sign's centre in front of its chest
  // (the rig's arms cannot reach above the head; the sign's top stays below the chin).
  plateY: 1735,
  signY: 1440,
  signH: 128,
  // A stamp's centre on a set or a map, on a card (under its lines), and the hand-lettered date tag's top-left corner.
  stampY: 860,
  cardStampY: 1180,
  dateX: 70,
  dateY: 400,
  // The map's area on a map beat; the card's box on a card beat.
  map: [40, 330, 1000, 740],
  card: [150, 430, 780, 940],
} as const;

/**
 * The poses: each arm's raise from hanging down (degrees, outward; past 180 it
 * crosses in over the head, as a salute reaches the brow), and the head's tilt.
 */
export const POSES = {
  stand: { l: -14, r: -14, head: 0 },
  point: { l: -14, r: 98, head: 4 },
  salute: { l: -14, r: 196, head: 0 },
  wave: { l: -14, r: 150, head: -4 },
  shrug: { l: 52, r: 52, head: 6 },
  hold: { l: -14, r: 62, head: 0 },
  cheer: { l: 145, r: 145, head: 0 },
  panic: { l: 138, r: 138, head: -6 },
  think: { l: -14, r: 170, head: 8 },
  // both hands out at the sides of a sign held in front of the chest
  sign: { l: 88, r: 88, head: 0 },
} as const;
export const FACES = ["stern", "happy", "proud", "worried", "shock", "sad", "smug", "angry"] as const;

/*
 * Era costumes: a torso, sleeves and a hat drawn over the one house rig
 * (./costumes.tsx). Each is generic: no uniform, insignia, crest, flag or
 * feature that belongs to one person, army or country.
 */
export const COSTUMES = [
  "plain", "dress", "peasant", "farmer", "worker", "clerk", "noble", "royal", "knight", "legionary",
  "soldier_1910s", "soldier_1940s", "sailor", "pilot", "explorer", "scientist", "monk",
] as const;

/*
 * Sets: flat illustrated places (./sets.tsx). Each is drawn as flat colour
 * bands and a few cached pieces of decor, with a foreground band the puppets
 * stand behind.
 */
export const SETS = [
  "farm", "street", "office", "palace", "castle", "deck", "market", "factory", "camp", "lab", "classroom", "field",
] as const;

/*
 * Hand props: drawn once (./props.tsx), held in a puppet's raised hand. `w`
 * and `h` are its box at scale 1; `text` is the most characters its label
 * takes (0 when none).
 */
export const PROPS = {
  scroll: { w: 150, h: 170, text: 10 },
  letter: { w: 150, h: 120, text: 10 },
  coin_bag: { w: 130, h: 140, text: 0 },
  quill: { w: 90, h: 170, text: 0 },
  book: { w: 150, h: 120, text: 0 },
  lantern: { w: 100, h: 160, text: 0 },
  hammer: { w: 110, h: 170, text: 0 },
  shovel: { w: 80, h: 200, text: 0 },
  flag: { w: 160, h: 200, text: 6 },
  telescope: { w: 180, h: 80, text: 0 },
  cup: { w: 100, h: 110, text: 0 },
  bread: { w: 150, h: 90, text: 0 },
  sword: { w: 60, h: 200, text: 0 },
  basket: { w: 150, h: 130, text: 0 },
} as const;

export const STAMP_COLORS = ["red", "green", "blue"] as const;
export const FILLS = { red: "#E53935", blue: "#4A7BB7", green: "#6E9A4F", yellow: "#E8B93C", purple: "#8A63A8", grey: "#8C8A82" } as const;
export const ENTRANCES = ["slide", "pop", "cut"] as const;
export const BEAT_TYPES = ["set", "card", "map"] as const;
export const EVENT_TYPES = ["enter", "move", "exit", "act", "swap", "sign", "hold", "stamp", "date", "strike", "fill", "arrow", "label"] as const;
// Which events each kind of beat takes.
export const BEAT_EVENTS = {
  set: ["enter", "move", "exit", "act", "swap", "sign", "hold", "stamp", "date"],
  map: ["enter", "move", "exit", "act", "swap", "sign", "hold", "fill", "arrow", "label", "date"],
  card: ["stamp", "strike", "date"],
} as const;

/** Every country the map knows, by the name world-atlas gives it (today's borders, 1:110m Natural Earth). */
type Atlas = { objects: { countries: { geometries: { id?: string; properties: { name: string } }[] } } };
export const COUNTRIES: readonly string[] = (world as unknown as Atlas).objects.countries.geometries.map((g) => g.properties.name);

/*
 * A prop the agent draws for one video when the library lacks it: a TSX file
 * beside the video's other generated files (generated/<video_id>/prop-<name>.tsx),
 * modelled on a library prop and using the same helpers (./ink).
 */
export const CUSTOM = { maxProps: 6, minSide: 50, maxSide: 300, maxText: 10, maxActs: 0 } as const;

export type Pose = keyof typeof POSES;
export type Face = (typeof FACES)[number];
export type Costume = (typeof COSTUMES)[number];
export type SetId = (typeof SETS)[number];
export type PropId = keyof typeof PROPS;
export type FillColor = keyof typeof FILLS;

export type PHActor = { id: string; costume: Costume; name?: string };
type At = { frame: number };
export type PHEvent =
  | (At & { type: "enter"; who: string; slot: number; from?: (typeof ENTRANCES)[number]; pose?: Pose; face?: Face })
  | (At & { type: "move"; who: string; slot: number })
  | (At & { type: "exit"; who: string })
  | (At & { type: "act"; who: string; pose?: Pose; face?: Face })
  | (At & { type: "swap"; who: string; costume: Costume })
  | (At & { type: "sign"; who: string; text: string })
  | (At & { type: "hold"; who: string; prop: string; text?: string })
  | (At & { type: "stamp"; text: string; color?: (typeof STAMP_COLORS)[number] })
  | (At & { type: "date"; text: string })
  | (At & { type: "strike"; line: number; text: string })
  | (At & { type: "fill"; region: string; color: FillColor })
  | (At & { type: "arrow"; from: string; to: string })
  | (At & { type: "label"; region: string; text: string });
export type PHBeat =
  | { type: "set"; start: number; set: SetId; events: PHEvent[] }
  | { type: "map"; start: number; focus: string[]; events: PHEvent[] }
  | { type: "card"; start: number; title: string; lines: string[]; events: PHEvent[] };
export type PHCustomProp = { id: string; src: string; w: number; h: number; text?: number };
export type PuppetHistoryData = { cast: PHActor[]; beats: PHBeat[]; customProps?: PHCustomProp[] };

/** A puppet's box on screen at a slot (x0, y0, x1, y1), hat and raised hands included. */
export function puppetBox(slot: number): [number, number, number, number] {
  const s = GEOMETRY.puppetScale, x = GEOMETRY.slots[slot];
  return [x - (GEOMETRY.puppetW / 2) * s, GEOMETRY.waistY - GEOMETRY.puppetH * s, x + (GEOMETRY.puppetW / 2) * s, GEOMETRY.waistY];
}

/** A held-up sign's width for its text: about 34 px a character plus its frame. */
export const signWidth = (text: string) => Math.max(160, text.length * 34 + 60);
