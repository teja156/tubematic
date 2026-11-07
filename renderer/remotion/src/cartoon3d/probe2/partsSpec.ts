// PROBE 2 parts pool — the PURE half. No textures, no `document`: the headless
// checker imports this, so it must run in Node. The DOM half is parts.ts.
//
// Every part is drawn at the origin, standing on y = 0, facing +z, local +x to
// its right. PART_DIMS is its footprint box (w along x, d along z, h up), the
// box the layout and the checker use for collision and line-of-sight. Long
// things (tracks, fences, wagons, benches) run along x. Kinds written in the
// part grammar (partSpecs/) take both from their spec, never by hand.
import type { BuildingPiece, Hsl } from "./worldKit";
import { deriveDims, deriveInfo, type PartSpec } from "./partGrammar";
import { PART_SPECS } from "./partSpecs";
import PROMOTED_JSON from "./partSpecs/promoted.json";
import { CODE_PARTS } from "./partSpecs/code/index";
import CODE_PROMOTED_JSON from "./partSpecs/code/promoted.json";
import { measureCodePart } from "./partSpecs/code/measure";

export type PartKind =
  // the original twelve (same names, same footprints)
  | "crate" | "barrel" | "cart" | "trough" | "lamp" | "sacks"
  | "hitchRail" | "woodpile" | "stump" | "bench" | "haybale" | "firepit"
  // railway
  | "railTrack" | "bufferStop" | "handcar" | "railSignal" | "waterTower" | "stationClock" | "luggage" | "coalBin"
  // post and telegraph
  | "mailbox" | "mailSacks" | "telegraphBox" | "noticeBoard" | "signpost" | "bellPost" | "flagpole"
  // town and yard
  | "cratePile" | "barrelStack" | "rainBarrel" | "bucket" | "ladder" | "lanternPost" | "hitchPost"
  | "wheelbarrow" | "wagonWheel" | "coveredWagon" | "anvil" | "grindstone" | "waterPump" | "well" | "outhouse"
  | "saddleRail" | "milkCans"
  // furniture
  | "table" | "chair" | "rockingChair" | "stool" | "picnicTable" | "logBench" | "flowerBox"
  // camp, lumber, mine
  | "tent" | "campfire" | "logStack" | "lumberStack" | "sawhorse" | "choppingBlock" | "toolRack"
  | "mineCart" | "mineEntrance" | "rockPile"
  // farm
  | "plow" | "scarecrow" | "chickenCoop" | "haystack" | "beehive" | "windmill" | "laundryLine"
  // fences and walls
  | "picketFence" | "splitRailFence" | "stoneWall"
  // riverside
  | "rowboat" | "canoe" | "dock" | "footbridge" | "pond" | "reeds"
  // nature
  | "shrub" | "pineTree" | "deadTree" | "saguaro" | "barrelCactus"
  // story: trains, people, water
  | "locomotive" | "passengerCar" | "bystander" | "crowd" | "riverWater" | "horse";

const D = (w: number, h: number, d: number) => ({ w, h, d });

export const PART_DIMS: Record<PartKind, { w: number; h: number; d: number }> = {
  crate: deriveDims(PART_SPECS.crate),
  barrel: D(0.62, 0.9, 0.62),
  cart: D(2.2, 1.2, 1.4),
  trough: D(1.8, 0.5, 0.6),
  lamp: D(0.3, 3.0, 0.3),
  sacks: D(1.0, 0.5, 0.9),
  hitchRail: D(2.5, 1.1, 0.2),
  woodpile: D(1.6, 0.8, 1.0),
  stump: D(0.76, 0.47, 0.76),
  bench: D(1.6, 0.95, 0.45),
  haybale: D(1.1, 0.55, 0.6),
  firepit: D(1.4, 0.5, 1.4),

  railTrack: D(4.0, 0.3, 2.8),
  bufferStop: D(2.0, 1.3, 1.3),
  handcar: D(1.8, 1.5, 1.4),
  railSignal: D(1.0, 5.2, 0.5),
  waterTower: deriveDims(PART_SPECS.waterTower),
  stationClock: D(0.7, 3.3, 0.3),
  luggage: D(1.3, 0.9, 0.8),
  coalBin: D(1.4, 0.9, 1.0),

  mailbox: D(0.4, 1.3, 0.6),
  mailSacks: D(1.3, 0.75, 1.0),
  telegraphBox: D(0.55, 1.6, 0.45),
  noticeBoard: D(1.8, 2.4, 0.45),
  signpost: D(1.9, 2.6, 0.9),
  bellPost: D(1.4, 2.9, 0.8),
  flagpole: D(0.8, 6.4, 0.8),

  cratePile: D(1.8, 1.5, 1.0),
  barrelStack: D(1.9, 1.45, 0.92),
  rainBarrel: D(0.75, 1.05, 0.75),
  bucket: D(0.36, 0.42, 0.36),
  ladder: D(0.7, 1.8, 1.0),
  lanternPost: D(0.9, 2.4, 0.3),
  hitchPost: D(0.3, 1.2, 0.3),
  wheelbarrow: D(1.6, 0.75, 0.7),
  wagonWheel: D(1.2, 1.25, 0.6),
  coveredWagon: D(4.2, 2.8, 1.9),
  anvil: D(0.9, 0.95, 0.6),
  grindstone: D(1.0, 1.1, 0.7),
  waterPump: D(0.8, 1.4, 0.8),
  well: D(2.0, 2.7, 1.9),
  outhouse: D(1.2, 2.4, 1.2),
  saddleRail: D(1.6, 1.25, 0.7),
  milkCans: D(1.0, 0.75, 0.65),

  table: D(1.4, 0.78, 0.8),
  chair: D(0.46, 1.0, 0.46),
  rockingChair: D(0.56, 1.1, 0.85),
  stool: D(0.4, 0.66, 0.4),
  picnicTable: D(1.8, 0.8, 1.6),
  logBench: D(1.6, 0.5, 0.45),
  flowerBox: D(0.9, 0.5, 0.32),

  tent: deriveDims(PART_SPECS.tent),
  campfire: D(1.4, 1.5, 1.4),
  logStack: D(4.2, 1.5, 1.9),
  lumberStack: D(3.0, 0.95, 1.2),
  sawhorse: D(1.4, 1.1, 0.7),
  choppingBlock: D(1.0, 0.9, 0.9),
  toolRack: D(1.4, 1.7, 0.5),
  mineCart: D(1.4, 1.05, 1.0),
  mineEntrance: D(5.0, 3.2, 4.5),
  rockPile: D(1.7, 0.8, 1.5),

  plow: D(2.0, 1.0, 0.7),
  scarecrow: D(1.4, 2.1, 0.4),
  chickenCoop: D(1.7, 1.5, 1.3),
  haystack: D(2.2, 2.7, 2.2),
  beehive: D(0.6, 1.1, 0.6),
  windmill: D(2.4, 7.4, 2.6),
  laundryLine: D(3.4, 2.0, 0.4),

  picketFence: D(3.0, 1.0, 0.12),
  splitRailFence: D(3.4, 1.2, 0.9),
  stoneWall: D(3.0, 0.85, 0.6),

  rowboat: D(3.3, 0.6, 1.25),
  canoe: D(4.0, 0.5, 0.8),
  dock: D(2.0, 0.75, 5.0),
  footbridge: D(4.6, 1.6, 1.6),
  pond: D(4.0, 0.3, 3.0),
  reeds: D(0.8, 1.4, 0.8),

  shrub: D(1.2, 0.9, 1.2),
  pineTree: deriveDims(PART_SPECS.pineTree),
  deadTree: D(2.4, 4.2, 2.4),
  saguaro: D(1.1, 3.2, 0.5),
  barrelCactus: D(0.5, 0.55, 0.5),

  locomotive: deriveDims(PART_SPECS.locomotive),
  passengerCar: D(8.0, 3.7, 2.6),
  bystander: deriveDims(PART_SPECS.bystander),
  crowd: D(5.0, 1.9, 2.2),
  riverWater: D(6.0, 0.05, 4.0),
  horse: D(2.3, 1.9, 0.8),
};

export interface PartInfo {
  /** blocks walking and camera rays (the layout's SOLID) */
  solid: boolean;
  /** a character may stand on it (rails, docks, bridges): its top is the floor */
  walkable?: boolean;
  /** carries a glow and a PointLight the scene drives up at night */
  lightAtNight?: boolean;
  /** sets group.userData.smoke (local emitter points) */
  smoke?: boolean;
  blurb: string;
}

const S = (blurb: string, more: Partial<PartInfo> = {}): PartInfo => ({ solid: true, blurb, ...more });
const F = (blurb: string, more: Partial<PartInfo> = {}): PartInfo => ({ solid: false, blurb, ...more });

export const PART_INFO: Record<PartKind, PartInfo> = {
  crate: deriveInfo(PART_SPECS.crate),
  barrel: S("upright bulged stave barrel with iron hoops"),
  cart: S("two-axle hand cart with spoked wheels and a pull shaft (long side along x)"),
  trough: S("plank horse trough full of water"),
  lamp: S("iron street lamp, glass lantern lit at night", { lightAtNight: true }),
  sacks: S("three tied burlap grain sacks"),
  hitchRail: S("two posts and a rail for tying horses, 2.5 m along x"),
  woodpile: S("split firewood stacked between two stakes"),
  stump: S("cut tree stump with roots and end-grain rings"),
  bench: S("plank bench with a back and arm rests, seats face +z"),
  haybale: S("rectangular straw bale bound with twine"),
  firepit: S("ring of stones with burning logs; glows, flickers and smokes at night", { lightAtNight: true, smoke: true }),

  railTrack: F("4 m straight of standard-gauge track on ties and ballast, runs along x; chain several end to end", { walkable: true }),
  bufferStop: S("timber buffer stop that ends a line; its buffers face +z, so turn it 90 deg to cap an x-running track"),
  handcar: S("railway pump handcar with a see-saw handle"),
  railSignal: S("tall semaphore signal post with a red lamp lit at night", { lightAtNight: true }),
  waterTower: deriveInfo(PART_SPECS.waterTower),
  stationClock: S("double-faced platform clock on an iron post"),
  luggage: S("steamer trunk, two suitcases and a hat box"),
  coalBin: S("open plank bin heaped with coal, a shovel stuck in it"),

  mailbox: S("rural mailbox on a post with its flag up"),
  mailSacks: S("heap of canvas mail sacks with stencilled stripes"),
  telegraphBox: S("weatherproof telegraph instrument box on a post, wire leading up"),
  noticeBoard: S("roofed notice board covered in posters"),
  signpost: S("crossroads signpost with three arrow boards"),
  bellPost: S("small roofed frame with a hanging bell"),
  flagpole: S("tall flagpole on a stone base flying a striped flag (flag overhangs +x by 1.5 m)"),

  cratePile: S("three stacked crates of mixed sizes"),
  barrelStack: S("barrels lying on their sides, three below and two above"),
  rainBarrel: S("open barrel full of rainwater on two blocks"),
  bucket: S("small wooden bucket with an iron bail"),
  ladder: S("wooden stepladder standing open"),
  lanternPost: S("shepherd's-hook post with a hanging lantern lit at night", { lightAtNight: true }),
  hitchPost: S("single hitching post with an iron ring"),
  wheelbarrow: S("wooden wheelbarrow, wheel at +x"),
  wagonWheel: S("spare wagon wheel leaning on a stake"),
  coveredWagon: S("prairie schooner: wagon with a canvas bonnet, tongue toward +x (4.2 m)"),
  anvil: S("blacksmith's anvil on a stump"),
  grindstone: S("treadle grindstone on a timber frame"),
  waterPump: S("cast-iron hand pump on a stone base with a bucket"),
  well: S("stone well with a small roof, crank and bucket"),
  outhouse: S("plank privy with a crescent moon on the door, door faces +z"),
  saddleRail: S("rail with a saddle and a folded blanket"),
  milkCans: S("three steel milk churns"),

  table: S("plank table with four legs"),
  chair: S("ladder-back chair, seat faces +z"),
  rockingChair: S("rocking chair, seat faces +z"),
  stool: S("three-legged stool"),
  picnicTable: S("trestle table with attached benches on both sides"),
  logBench: S("half-log bench on two stump legs"),
  flowerBox: S("planter box of mixed flowers, to sit under a window or on a porch"),

  tent: deriveInfo(PART_SPECS.tent),
  campfire: S("cook fire under an iron tripod with a kettle; glows and smokes at night", { lightAtNight: true, smoke: true }),
  logStack: S("lumber-camp pile of six felled logs, 4 m along x"),
  lumberStack: S("stack of sawn boards on stickers"),
  sawhorse: S("sawhorse with a log on it and a bow saw"),
  choppingBlock: S("chopping stump with an axe in it and split pieces around"),
  toolRack: S("rack of picks and shovels"),
  mineCart: S("iron ore cart on a short stub of narrow track"),
  mineEntrance: S("timbered mine adit in a rock mound, dark opening faces +z, rails coming out"),
  rockPile: S("loose heap of rocks"),

  plow: S("horse-drawn walking plow, handles toward -x"),
  scarecrow: S("scarecrow on a cross post in a hat and patched shirt"),
  chickenCoop: S("little hen house on legs with a ramp facing +z"),
  haystack: S("round domed haystack built around a pole"),
  beehive: S("straw bee skep on a stand"),
  windmill: S("farm windpump: lattice tower, multi-blade fan facing +z and a tail vane"),
  laundryLine: S("washing line between two T-posts with clothes hung out"),

  picketFence: S("3 m of painted picket fence along x; chain segments end to end"),
  splitRailFence: S("3.4 m of zig-zag split-rail fence along x"),
  stoneWall: S("3 m of dry-stone wall along x"),

  rowboat: S("small wooden rowboat with oars, bow toward +x"),
  canoe: S("birch-bark style canoe with a paddle, along x"),
  dock: S("plank jetty 5 m long reaching out toward +z on piles", { walkable: true }),
  footbridge: S("arched plank footbridge with hand rails, crossing along x", { walkable: true }),
  pond: F("small pond: a flat water decal with lily pads, rim stones and reeds"),
  reeds: F("clump of reeds and cattails, for water edges"),

  shrub: S("low rounded bush"),
  pineTree: deriveInfo(PART_SPECS.pineTree),
  deadTree: S("bare dead tree with crooked branches"),
  saguaro: S("tall saguaro cactus with two arms"),
  barrelCactus: S("squat ribbed barrel cactus with flowers"),

  locomotive: deriveInfo(PART_SPECS.locomotive),
  passengerCar: S("wooden 1860s passenger coach on two 4-wheel trucks, clerestory roof and end platforms, 8 m along x; place it on railTrack"),
  bystander: deriveInfo(PART_SPECS.bystander),
  crowd: S("loose two-rank arc of 7-9 flat cartoon bystanders facing +z, taller figures at the back"),
  riverWater: F("6 x 4 m flat slab of rippled water with no bank or rim, flush with the ground; chain several along x for a creek or river", { walkable: false }),
  horse: S("saddled standing cartoon horse with a red saddle blanket and reins, head toward +x; coat (bay, chestnut, grey, black, palomino) and white blaze by seed"),
};

export const PART_KINDS = Object.keys(PART_DIMS) as PartKind[];

// ------------------------------------------------------------ agent parts
// Parts an agent wrote in the grammar: promoted ones (passed the gate on an
// earlier video, saved in partSpecs/promoted.json by gate/gateCli.ts) and the
// ones a WorldSpec carries itself (`parts`). A prop names any of the three.

/** parts promoted by the gate, by name */
export const PROMOTED = PROMOTED_JSON as unknown as Record<string, PartSpec>;
/** a kit kind, or the name of a promoted or world-carried part */
export type PropName = PartKind | (string & {});
/** the names a new part may not take (a JSON part may not shadow a code part either) */
export const RESERVED_PART_NAMES: readonly string[] = [...PART_KINDS, ...Object.keys(PROMOTED), ...Object.keys(CODE_PARTS)];
/** code parts that passed the gate on an earlier video (partSpecs/code/promoted.json): name -> hash of the source
 *  file as judged. A promoted part whose file changed is gated again (the gate compares hashes). */
export const CODE_PROMOTED: Record<string, string> = CODE_PROMOTED_JSON as Record<string, string>;
export const CODE_PROMOTED_NAMES: readonly string[] = Object.keys(CODE_PROMOTED);
export const isCodePart = (what: string) => what in CODE_PARTS;

export const partSpecOf = (what: string, custom?: Record<string, PartSpec>): PartSpec | undefined => custom?.[what] ?? PROMOTED[what];

const codeInfoCache = new Map<string, PartInfo>();
const codeInfo = (what: string): PartInfo => {
  let v = codeInfoCache.get(what);
  if (!v) {
    const c = CODE_PARTS[what];
    v = { solid: c.solid ?? true, walkable: c.walkable, lightAtNight: c.lightAtNight, smoke: !!c.smoke?.length, blurb: c.blurb };
    codeInfoCache.set(what, v);
  }
  return v;
};

const dimsCache = new WeakMap<PartSpec, { w: number; h: number; d: number }>();
const infoCache = new WeakMap<PartSpec, PartInfo>();
const derived = <X>(spec: PartSpec, cache: WeakMap<PartSpec, X>, make: (s: PartSpec) => X) => {
  let v = cache.get(spec);
  if (!v) cache.set(spec, (v = make(spec)));
  return v;
};
const unknown = (what: string): never => {
  throw new Error(`unknown part "${what}": not a kit kind, not promoted, not a code part, and not in this world's parts`);
};
/** footprint of any prop name (kit, promoted, or in `custom`) */
export const partDims = (what: PropName, custom?: Record<string, PartSpec>) => {
  const kit = PART_DIMS[what as PartKind];
  if (kit) return kit;
  const spec = partSpecOf(what, custom);
  if (spec) return derived(spec, dimsCache, deriveDims);
  if (isCodePart(what)) {
    const m = measureCodePart(what);
    return { w: m.w, h: m.h, d: m.d };
  }
  return unknown(what);
};
export const partInfo = (what: PropName, custom?: Record<string, PartSpec>): PartInfo => {
  const kit = PART_INFO[what as PartKind];
  if (kit) return kit;
  const spec = partSpecOf(what, custom);
  if (spec) return derived(spec, infoCache, deriveInfo);
  if (isCodePart(what)) return codeInfo(what);
  return unknown(what);
};

// ------------------------------------------------------------------ buildings

export type WallKind = "planks" | "clapboard" | "logs" | "stone" | "brick" | "adobe";
export type RoofKind = "gable" | "hip" | "shed" | "flat" | "falseFront";

/** Every field is optional. Absent fields take the defaults in resolveStyle(),
 *  which reproduce the round-2 building (plank or clapboard walls, gable roof,
 *  or a false front when the piece has `falseFront`) plus a closed door and a
 *  low stone footing. Small details (which side the chimney is on, which slot
 *  the door takes when the count is even) come from the piece's seed. */
export interface BuildingStyle {
  /** wall material; the piece's `wall` Hsl tints it */
  wall?: WallKind;
  /** roof shape; "falseFront" uses the piece's `falseFront` height (or 1.4 m) */
  roof?: RoofKind;
  /** roof covering; default shingles (tin on shed roofs) */
  roofMat?: "shingles" | "tin" | "planks";
  /** what the floor sits on; "posts" raises it 0.6 m, "stone" 0.3 m */
  foundation?: "stone" | "posts" | "none";
  /** covered porch across the front: deck + posts + roof */
  porch?: { depth?: number; rail?: boolean; roof?: boolean };
  /** sloped awning over the ground-floor openings; canvas is striped */
  awning?: { depth?: number; kind?: "canvas" | "wood"; stripe?: Hsl };
  /** front door; set false for no door. `at` in -1..1 picks a facade slot */
  door?: false | { at?: number; open?: boolean; lit?: boolean; color?: Hsl };
  /** chimney with a smoke emitter; logs cabins get an outside stone stack */
  chimney?: boolean | { side?: -1 | 1; kind?: "stone" | "brick"; outside?: boolean };
  /** steps up to the door (or to the porch); default on when the floor is raised */
  steps?: boolean;
  /** window shutters; true = muted green */
  shutters?: boolean | Hsl;
  /** trim colour (window frames, door frame, corner boards) */
  trim?: Hsl;
  /** a second row of windows (one above each ground-floor slot) and a belt course.
   *  The piece's h is still the whole wall height; give it ~5.5 m or more. */
  storeys?: 1 | 2;
  /** upper-floor balcony across the front on posts (needs storeys: 2) */
  balcony?: boolean;
}

export interface ResolvedStyle {
  wall: WallKind;
  roof: RoofKind;
  roofMat: "shingles" | "tin" | "planks";
  foundation: "stone" | "posts" | "none";
  floor: number;
  porch: { depth: number; rail: boolean; roof: boolean } | null;
  awning: { depth: number; kind: "canvas" | "wood"; stripe: Hsl } | null;
  door: { at: number; open: boolean; lit: boolean; color: Hsl } | null;
  chimney: { side: -1 | 1; kind: "stone" | "brick"; outside: boolean } | null;
  steps: boolean;
  shutters: Hsl | null;
  trim: Hsl;
  storeys: 1 | 2;
  balcony: boolean;
  falseFront: number;
}

type BuildingIn = Pick<BuildingPiece, "w" | "h" | "d" | "falseFront" | "windows" | "seed" | "wall"> & { style?: BuildingStyle };

// tiny pure hash so the spec needs no RNG state
const pick = (seed: number, salt: number) => {
  let x = (seed * 2654435761 + salt * 40503) >>> 0;
  x ^= x >>> 13;
  x = Math.imul(x, 0x5bd1e995) >>> 0;
  x ^= x >>> 15;
  return (x >>> 0) / 4294967296;
};

export const resolveStyle = (b: BuildingIn): ResolvedStyle => {
  const s = b.style ?? {};
  const wall: WallKind = s.wall ?? (b.wall.clapboard ? "clapboard" : "planks");
  const roof: RoofKind = s.roof ?? (b.falseFront ? "falseFront" : "gable");
  const foundation = s.foundation ?? (wall === "adobe" ? "none" : "stone");
  const floor = foundation === "posts" ? 0.6 : foundation === "stone" ? 0.3 : 0;
  const porch = s.porch ? { depth: s.porch.depth ?? 2.0, rail: s.porch.rail ?? true, roof: s.porch.roof ?? true } : null;
  const awning = s.awning
    ? { depth: s.awning.depth ?? 1.4, kind: s.awning.kind ?? "canvas", stripe: s.awning.stripe ?? { hue: 8, sat: 0.32, light: 0.5 } }
    : null;
  const door =
    s.door === false
      ? null
      : { at: s.door?.at ?? 0, open: s.door?.open ?? false, lit: s.door?.lit ?? false, color: s.door?.color ?? { hue: 22, sat: 0.3, light: 0.3 } };
  const chimney = s.chimney
    ? {
        side: (typeof s.chimney === "object" && s.chimney.side) || (pick(b.seed, 7) < 0.5 ? -1 : 1),
        kind: (typeof s.chimney === "object" && s.chimney.kind) || (wall === "brick" ? "brick" : "stone"),
        outside: typeof s.chimney === "object" && s.chimney.outside !== undefined ? s.chimney.outside : wall === "logs",
      } as ResolvedStyle["chimney"]
    : null;
  const steps = s.steps ?? (floor >= 0.45 || (porch !== null && floor > 0.2));
  const shutters = s.shutters ? (s.shutters === true ? { hue: 150, sat: 0.2, light: 0.34 } : s.shutters) : null;
  const trim = s.trim ?? { hue: 40, sat: 0.3, light: 0.82 };
  const storeys = s.storeys ?? 1;
  const balcony = !!s.balcony && storeys === 2;
  const roofMat = s.roofMat ?? (roof === "shed" ? "tin" : "shingles");
  return {
    wall, roof, roofMat, foundation, floor, porch, awning, door, chimney, steps, shutters, trim, storeys, balcony,
    falseFront: b.falseFront ?? 1.4,
  };
};

/** gable/hip rise above the eave, by roof kind */
export const roofRise = (b: { w: number; h: number; d: number }, r: ResolvedStyle) =>
  r.roof === "gable" ? b.h * 0.5
  : r.roof === "hip" ? Math.min(b.w, b.d) * 0.36
  : r.roof === "shed" ? Math.min(1.4, b.d * 0.22)
  : r.roof === "flat" ? 0.35 // parapet
  : Math.min(r.falseFront * 0.8, b.w * 0.25); // the low gable hidden behind a false front

export interface Facade {
  /** x of each ground-floor slot; the door takes one, windows the rest */
  slots: number[];
  doorX: number | null;
  /** ground-floor window x positions, left to right (lit[] indexes these first) */
  windows: number[];
  /** upper-floor window x positions (lit[] continues with these) */
  upper: number[];
  /** sill-to-head of the openings, in metres above the ground */
  winY: number;
  upperY: number;
  doorTop: number;
}

/** Where the openings go. Pure, so a checker can reason about the facade. */
export const facadeLayout = (b: BuildingIn): Facade => {
  const r = resolveStyle(b);
  const n = b.windows ?? 0;
  const k = n + (r.door ? 1 : 0);
  const slots = Array.from({ length: k }, (_, i) => (i - (k - 1) / 2) * (b.w / (k + 0.6)));
  let doorSlot = -1;
  if (r.door) {
    const t = (r.door.at + 1) / 2; // 0..1
    doorSlot = Math.round(t * (k - 1));
    if (k % 2 === 0 && r.door.at === 0) doorSlot = pick(b.seed, 3) < 0.5 ? k / 2 - 1 : k / 2;
  }
  const storeyH = r.storeys === 2 ? b.h / 2 : b.h;
  const winY = r.storeys === 2 ? r.floor + (storeyH - r.floor) * 0.48 : b.h * 0.55;
  const doorTop = Math.min(r.floor + 2.15, storeyH - 0.35);
  return {
    slots,
    doorX: doorSlot >= 0 ? slots[doorSlot] : null,
    windows: slots.filter((_, i) => i !== doorSlot),
    upper: r.storeys === 2 ? slots : [],
    winY,
    upperY: storeyH + storeyH * 0.5,
    doorTop,
  };
};

/** How far the building's dressing reaches past its plain box. `front` is how
 *  far it projects in FRONT of the facade line (porch, steps, awning, balcony,
 *  footing); `top` is its highest point; `chimney` is in local coordinates
 *  (x right, z = 0 at the facade, negative into the building). */
export const buildingExtent = (b: { w: number; h: number; d: number; falseFront?: number; style?: BuildingStyle; seed?: number; windows?: number; wall?: Hsl & { clapboard?: boolean } }) => {
  const bi: BuildingIn = { w: b.w, h: b.h, d: b.d, falseFront: b.falseFront, style: b.style, seed: b.seed ?? 1, windows: b.windows, wall: b.wall ?? { hue: 30, sat: 0.4, light: 0.5 } };
  const r = resolveStyle(bi);
  const rise = roofRise(b, r);
  let front = r.foundation === "stone" ? 0.06 : 0;
  const stepsD = r.steps ? Math.max(1, Math.ceil(r.floor / 0.2)) * 0.3 : 0;
  if (r.porch) front = Math.max(front, r.porch.depth + 0.15 + stepsD);
  else front = Math.max(front, stepsD);
  if (r.awning) front = Math.max(front, r.awning.depth);
  if (r.balcony) front = Math.max(front, 1.3);
  let top =
    r.roof === "falseFront" ? b.h + Math.max(r.falseFront, rise)
    : r.roof === "shed" ? b.h + rise + 0.08
    : r.roof === "flat" ? b.h + rise
    : b.h + rise + 0.12;
  let chimney: { x: number; z: number; top: number } | undefined;
  if (r.chimney) {
    const c = chimneyPlace(b, r, rise);
    chimney = { x: c.x, z: c.z, top: c.top };
    top = Math.max(top, c.top);
  }
  return { front, top, chimney };
};

/** Shared by builder and buildingExtent so the smoke point is where the stack is. */
export const chimneyPlace = (b: { w: number; h: number; d: number }, r: ResolvedStyle, rise: number) => {
  const ch = r.chimney!;
  if (ch.outside) {
    const x = ch.side * (b.w / 2 + 0.4);
    const z = -b.d / 2;
    const ridge = r.roof === "gable" || r.roof === "hip" ? b.h + rise : b.h + 0.5;
    return { x, z, bottom: 0, top: ridge + 0.5, size: 0.8, outside: true };
  }
  const x = ch.side * Math.min(b.w / 2 - 0.6, b.w * 0.3);
  const z = -b.d * 0.62;
  // roof surface height at the stack (ridge runs along z for gable/falseFront)
  let at: number;
  if (r.roof === "gable" || r.roof === "falseFront") at = b.h + rise * (1 - Math.abs(x) / (b.w / 2));
  else if (r.roof === "hip") at = b.h + rise * Math.min(1, (b.w / 2 - Math.abs(x)) / (b.w / 2));
  else if (r.roof === "shed") at = b.h + rise * (1 + z / b.d); // high at the front
  else at = b.h;
  const ridge = r.roof === "gable" || r.roof === "falseFront" || r.roof === "hip" ? b.h + rise : at;
  return { x, z, bottom: b.h - 0.4, top: Math.max(at + 0.9, ridge + 0.45), size: 0.6, outside: false };
};
