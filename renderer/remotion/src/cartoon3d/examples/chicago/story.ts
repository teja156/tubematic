// The Chicago short's story: shots timed to the recorded voice (timeline.json, 30 fps), the story state (street
// fill, building lift, jackscrew turns), its places and its camera keys. The camera grammar itself is the kit's
// (../../camera.ts); this file is the worked example the tubematic-cartoon3d skill points at.
import { FPS, type ShotDef, type V3 } from "../../video";
import { add, clamp01, dofAtOf, dolly, easeOut, glide, keyEnd as keyEndOf, layersAt as layersAtOf, lin, makeCamAt, pushK, rolled, shotAt as shotAtOf, smooth, zoom, type Cam, type Dof, type Key, type Shot } from "../../camera";
export { FPS, clamp01, smooth, easeOut, lin, glide, add, rolled, zoom, dolly, pushK };
export type { V3, Cam, Shot, Key, Dof };
export const TOTAL = 3614;


// ---------------- places (all sets live in one world, far apart; one set is shown per shot) ----------------
/** Lake Street: x runs east, the lake beyond x = 260; old grade y = 0, the new grade RAISE above it */
export const RAISE = 2.6;
export const NZ = -12, SZ = 12; // north / south facade lines
export const WALK = 3.0; // plank sidewalk depth in front of the facades
export const WALK_Y = 0.4; // old plank sidewalk height
/** the hero building of the hook and seg 3-4 (north row) */
export const HERO = { x0: -5, x1: 5, floors: 4 };
/** the Lake Street row of seg 5 (north row): five shops rising together */
export const ROW = { x0: 9, x1: 49, n: 5 };
/** the Tremont House (south row, corner of the cross street at x = 62) */
export const TREMONT = { x0: 22, x1: 62, floors: 6 };
export const WAGON: V3 = [-9, 0, 2.2];
/** the plank the gentleman walks across the mud on (seg 1) */
export const PLANK = { x: -1.6, z0: -9, z1: -2.6 };
export const SIGN_AT: V3 = [-7.3, 0, 4.4];
/** the crawlspace under a building (seg 4, seg 7): its own set */
export const CRAWL: V3 = [0, 0, 1000];
export const CRAWL_H = 2.3; // joists overhead
/** the Tremont dining room (seg 6) */
export const DINING: V3 = [1000, 0, 0];
/** the buried-street section (seg 7) */
export const SECTION: V3 = [1000, 0, 1000];
/** the river at dusk (seg 8) */
export const RIVER: V3 = [-1000, 0, 0];

// ---------------- shots ----------------
export type Light = "day" | "golden" | "lamp" | "hall";
export type Place = "street" | "crawl" | "dining" | "section" | "river";
export type ChicagoShot = ShotDef & { set: Place; era: number };
// era: 0 = 1858 mud, 1 = sewers laid + fill rising, 2 = buildings lifting, 3 = finished raised street
export const SHOTS: ChicagoShot[] = [
  { id: 1, a: 0, b: 127, light: "day", set: "street", era: 0, note: "a gentleman planks across the mud and steps in" },
  { id: 2, a: 127, b: 209, light: "day", set: "street", era: 0, note: "the whole street sinking in mud, wagon stuck" },
  { id: 3, a: 209, b: 275, light: "day", set: "street", era: 0, note: "the fix: jackscrews set under the hero building" },
  { id: 4, a: 275, b: 388, light: "day", set: "street", era: 0, note: "the hero building jacked up into the air" },
  { id: 5, a: 388, b: 456, light: "day", set: "street", era: 0, note: "people still inside: shopkeeper in the risen doorway" },
  { id: 6, a: 456, b: 611, light: "day", set: "street", era: 0, note: "aerial: low flat city at the edge of Lake Michigan", aerial: true, sunAz: 140, sunEl: 40 },
  { id: 7, a: 611, b: 670, light: "day", set: "street", era: 0, note: "water standing in the street, nowhere to drain" },
  { id: 8, a: 670, b: 727, light: "day", set: "street", era: 0, note: "deep mud: horse and wagon stuck, NO BOTTOM sign" },
  { id: 9, a: 727, b: 778, light: "day", set: "street", era: 0, note: "sewage pooled in the gutter" },
  { id: 10, a: 778, b: 845, light: "day", set: "street", era: 0, note: "cholera notice, people with cloths to faces" },
  { id: 11, a: 845, b: 919, light: "day", set: "street", era: 0, note: "officials over the strange plan" },
  { id: 12, a: 919, b: 1022, light: "day", set: "street", era: 1, note: "sewer pipes laid on top of the old street" },
  { id: 13, a: 1022, b: 1067, light: "day", set: "street", era: 1, note: "shovels bury the pipes" },
  { id: 14, a: 1067, b: 1146, light: "day", set: "street", era: 1, note: "the street level rises several feet" },
  { id: 15, a: 1146, b: 1235, light: "day", set: "street", era: 1, note: "new road built on top of the old one" },
  { id: 16, a: 1235, b: 1337, light: "day", set: "street", era: 1, note: "every building now below the road" },
  { id: 17, a: 1337, b: 1411, light: "day", set: "street", era: 1, note: "front door at the bottom of a pit" },
  { id: 18, a: 1411, b: 1493, light: "day", set: "street", era: 2, note: "contractor: lift the buildings too" },
  { id: 19, a: 1493, b: 1556, light: "lamp", set: "crawl", era: 2, note: "crews dig under the foundations" },
  { id: 20, a: 1556, b: 1656, light: "lamp", set: "crawl", era: 2, note: "rows of iron jackscrews under the walls" },
  { id: 21, a: 1656, b: 1747, light: "lamp", set: "crawl", era: 2, note: "a man at every screw; the foreman's signal" },
  { id: 22, a: 1747, b: 1856, light: "lamp", set: "crawl", era: 2, note: "whistle: every man turns his screw" },
  { id: 23, a: 1856, b: 1894, light: "lamp", set: "crawl", era: 2, note: "all together" },
  { id: 24, a: 1894, b: 1976, light: "lamp", set: "crawl", era: 2, note: "the beam rises a fraction of an inch" },
  { id: 25, a: 1976, b: 2066, light: "lamp", set: "crawl", era: 2, note: "masons lay the new foundation" },
  { id: 26, a: 2066, b: 2224, light: "day", set: "street", era: 2, note: "1860: half a block of Lake Street shops rising" },
  { id: 27, a: 2224, b: 2330, light: "day", set: "street", era: 2, note: "six hundred men, six thousand screws under the row" },
  { id: 28, a: 2330, b: 2420, light: "day", set: "street", era: 2, note: "the gauge: almost five feet in five days" },
  { id: 29, a: 2420, b: 2482, light: "day", set: "street", era: 2, note: "the shops never closed" },
  { id: 30, a: 2482, b: 2566, light: "day", set: "street", era: 2, note: "customers climb temporary stairs" },
  { id: 31, a: 2566, b: 2683, light: "day", set: "street", era: 2, note: "young George Pullman directs the crews" },
  { id: 32, a: 2683, b: 2789, light: "day", set: "street", era: 2, note: "the Tremont House rising" },
  { id: 33, a: 2789, b: 2844, light: "hall", set: "dining", era: 2, note: "guests keep eating" },
  { id: 34, a: 2844, b: 2909, light: "day", set: "street", era: 2, note: "a guest checks out down the temporary steps" },
  { id: 35, a: 2909, b: 2976, light: "hall", set: "dining", era: 2, note: "teacup trembles; the reader shrugs" },
  { id: 36, a: 2976, b: 3034, light: "day", set: "street", era: 3, note: "the finished raised street" },
  { id: 37, a: 3034, b: 3110, light: "day", set: "street", era: 3, note: "the raised city, dry ground", sunAz: 140, sunEl: 40, aerial: true },
  { id: 38, a: 3110, b: 3240, light: "lamp", set: "crawl", era: 2, note: "one quarter turn at a time" },
  { id: 39, a: 3240, b: 3382, light: "day", set: "section", era: 3, note: "sink through the pavement to the buried street" },
  { id: 40, a: 3382, b: 3497, light: "golden", set: "river", era: 3, note: "dusk: the river, gas lamps coming on" },
  { id: 41, a: 3497, b: TOTAL, light: "golden", set: "river", era: 3, note: "a small boat drifts on the river" },
];
/** crossfades (frames) at place/time changes; a white 4-frame flash after the hook */
export const XFADE: Record<number, number> = { 6: 8, 12: 8, 19: 8, 26: 8, 33: 6, 34: 6, 35: 6, 36: 8, 38: 8, 39: 8, 40: 10 };
export const FLASH_AT = 456;

/** near/far per shot: as much depth precision as the shot can use (the aerials see nothing closer than ~60 m; every
 *  other shot's world ends at the 1100 m sky sphere). Post passes take these per frame (Chicago.tsx). */
export const clipAt = (id: number) => (id === 6 || id === 37 ? { near: 5, far: 2600 } : { near: 0.2, far: 1200 });

// ---------------- story state ----------------
/** the foreman's whistle and the unison quarter turns (frames). Every turn lifts the building a little. */
export const WHISTLES = [1740, 1850, 3172];
export const TURN_LEN = 14; // frames a quarter turn takes
export const TURNS = [1752, 1860, 1912, 1950, 3186];
/** quarter-turns done by frame f (fractional during a turn), counted from the crawl's first turn */
export const turnsAt = (f: number) => TURNS.reduce((a, t0) => a + smooth((f - t0) / TURN_LEN), 0);
/** street fill above old grade (m) per shot: era 1 rises during 12-15 */
export const fillAt = (id: number, f: number) => {
  if (id <= 11) return 0;
  if (id === 12) return 0;
  if (id === 13) return lin([[1030, 0], [1067, 0.7]], f);
  if (id === 14) return lin([[1067, 0.7], [1146, 1.9]], f);
  if (id === 15) return RAISE;
  if (id >= 26 && id <= 30) return 0; // Lake Street row: lifted before its street was filled
  return RAISE;
};
/** shot 15: the new road's front edge (x) advancing east over the old mud road */
export const fillFrontAt = (id: number, f: number) => (id === 15 ? lin([[1146, -16], [1235, -6]], f) : 140);
/** the sewer pipes: how many of the pipe sections lie on the street by frame f (laying animation in shot 12) */
export const pipesAt = (id: number, f: number) => (id < 12 ? 0 : id === 12 ? lin([[919, 3], [1010, 9]], f) : 12);
/** lift (m) of a building: "hero" (hook flash-forward, then seg 3-4), "row" (Lake Street, seg 5), "tremont" (seg 6) */
export const liftAt = (who: "hero" | "row" | "tremont" | "other", id: number, f: number) => {
  const s = SHOTS[id - 1];
  if (who === "hero") {
    if (id <= 2) return 0.55;
    if (id === 3) return 0.55;
    if (id === 4) return lin([[275, 0.55], [300, 0.6], [372, 2.3]], f);
    if (id === 5) return lin([[388, 2.3], [456, 2.45]], f);
    if (id <= 11) return 0;
    if (id <= 17) return 0;
    if (id === 18) return lin([[1411, 0.5], [1493, 1.2]], f);
    return RAISE;
  }
  if (who === "row") {
    if (id < 26) return id >= 18 ? 0 : 0;
    if (id === 26) return lin([[2066, 0.9], [2224, 1.15]], f);
    if (id === 27) return lin([[2224, 1.15], [2330, 1.3]], f);
    if (id === 28) return lin([[2330, 0.15], [2410, 1.42]], f); // the gauge beat replays the five days fast: 0 -> 4 ft 8 in
    if (id === 29 || id === 30) return 1.42;
    return RAISE;
  }
  if (who === "tremont") {
    if (id < 31) return 0;
    if (id === 31) return lin([[2566, 0.6], [2683, 0.8]], f);
    if (id === 32) return lin([[2683, 0.8], [2789, 1.05]], f);
    if (id === 34) return lin([[2844, 1.1], [2909, 1.2]], f);
    return s.era >= 3 ? RAISE : 1.2;
  }
  return s.era >= 3 ? RAISE : 0;
};

// ---------------- camera ----------------
// Grammar (motion.md): every move is a symmetric smootherstep glide of 18-40 f (peak speed = 1.875 x distance / dur,
// so dur >= 0.075 x the move in 720p px keeps the peak near the reference 14-25 px/f); a reframe bigger than about
// half a frame width or 40 % zoom is a hard cut on its key frame. Glides are centred on the old key frame (the
// whoosh in the sound mix peaks there), so a glide key starts dur/2 earlier. Holds push in (dolly toward the look
// point or a fov zoom near walls): 0.15-0.35 %/f, ~0.6 %/f for ~35 f on the punch words. Rolls of 4-8 deg
// over >= 18 f on emphasis beats, held tilt <= 0.07 rad.
const C = (p: V3) => add(CRAWL, p), Dn = (p: V3) => add(DINING, p), Sc = (p: V3) => add(SECTION, p), Rv = (p: V3) => add(RIVER, p);

// ---- framings (f -> camera); each pushes in from the frame its key starts ----
const heroY = (id: number, f: number) => liftAt("hero", id, f);
// seg 1: the gentleman on the plank (his walk: story constants in cast.ts), the wagon behind, the hero building beyond
const S1a = (f: number) => dolly([1.4, 1.35, 1.6], [-1.6, 0.95, -5.6], pushK(f, 0, 0.0025), { fov: 42 });
const S1b = (f: number) => dolly([0.4, 0.75, 0.6], [-1.6, 0.55, -3.0], pushK(f, 84, 0.003, 0.006, 30), { fov: 40, roll: 0.03 });
const S2a = (f: number) => dolly([4.0, 3.8, 10.5], [-5.0, 0.7, -0.8], pushK(f, 127, 0.0022, 0.005, 35), { fov: 46 });
const S3a = (f: number) => dolly([1.9, 0.85, -8.4], [-0.2, 0.42, -11.6], pushK(f, 209, 0.0028), { fov: 40 });
const S4a = (f: number) => ({ ...dolly([7.5, 1.7, 10.5], [0, 3.6 + 0.6 * heroY(4, f), -12], pushK(f, 275, 0.0018), { fov: 46 }) });
const S4b = (f: number) => dolly([5.8, 1.6, 7.0], [0, 5.0 + heroY(4, f), -12], pushK(f, 330, 0.0015, 0.005, 30), { fov: 48, roll: -0.04 });
const S5a = (f: number) => dolly([1.6, 2.9, -6.3], [0, heroY(5, f) + 1.5, -12], pushK(f, 388, 0.003), { fov: 40, roll: 0.03 });
// seg 2: the aerial, then street-level detail
const S6a = (f: number) => dolly([-150, 105, 95], [110, 2, -30], pushK(f, 456, 0.0016), { fov: 42 });
const S6b = (f: number) => dolly([-40, 60, 60], [220, -10, -20], pushK(f, 545, 0.0015, 0.004, 30), { fov: 40 }); // "Lake Michigan": the shore line
const S7a = (f: number) => dolly([-12.2, 1.05, 4.2], [-15, 0.2, -1.5], pushK(f, 611, 0.0025), { fov: 42, roll: -0.03 });
const S8a = (f: number) => dolly([-1.0, 1.35, 7.4], [-5.0, 0.55, 2.0], pushK(f, 670, 0.003), { fov: 44 });
const S9a = (f: number) => dolly([-20, 1.0, -4.0], [-23.5, 0.15, -8.8], pushK(f, 727, 0.003), { fov: 40 });
const S10a = (f: number) => dolly([-30.4, 1.9, -5.4], [-32.4, 1.7, -11.9], pushK(f, 778, 0.0025, 0.005, 25), { fov: 42 });
const S11a = (f: number) => dolly([16.4, 2.3, 6.4], [17.7, 1.25, 10.6], pushK(f, 845, 0.0028), { fov: 42, roll: 0.03 });
// sewers laid and buried, the fill rising
const S12a = (f: number) => dolly([-24, 4.2, 6.5], [6, 0.4, -0.5], pushK(f, 919, 0.0018), { fov: 40 });
const S13a = (f: number) => dolly([-4.2, 5.0, 8.4], [1.2, 0.4, -0.4], pushK(f, 1022, 0.003), { fov: 44, roll: -0.03 });
const S14a = (f: number) => dolly([-14, 1.7 + fillAt(14, f) * 0.6, 4.6], [-14, 0.9 + fillAt(14, f) * 0.5, -10.5], pushK(f, 1067, 0.002), { fov: 42 });
const S15a = (f: number) => dolly([7.5, 4.6, 7.0], [-9.0, 0.9, -1.0], pushK(f, 1146, 0.0018), { fov: 46 });
const S16a = (f: number) => dolly([-22, RAISE + 3.6, -3.0], [2, 0.6, -11.0], pushK(f, 1235, 0.0018), { fov: 40 });
const S17a = (f: number) => dolly([3.0, RAISE + 1.9, -5.0], [0.3, 1.1, -11.2], pushK(f, 1337, 0.0025), { fov: 46, roll: 0.03 });
const S18a = (f: number) => dolly([3.6, RAISE + 4.6, -2.6], [0, 0.5 + 0.5 * heroY(18, f), -11.2], pushK(f, 1411, 0.0022), { fov: 46 });
// crawlspace
const S19a = (f: number) => dolly(C([2.2, 1.45, 5.0]), C([-1.2, 0.7, -0.6]), pushK(f, 1493, 0.0028), { fov: 42 });
const S20a = (f: number) => dolly(C([14.5, 1.0, 2.8]), C([-4, 0.6, -1.4]), pushK(f, 1556, 0.0018, 0.004, 30), { fov: 40 });
const S21a = (f: number) => dolly(C([4.6, 1.45, 4.4]), C([-1.8, 0.8, -1.6]), pushK(f, 1656, 0.002), { fov: 44 });
const S21b = (f: number) => dolly(C([9.4, 1.55, 1.4]), C([7.4, 1.5, -1.1]), pushK(f, 1712, 0.003), { fov: 38, roll: 0.03 }); // the foreman: "on a signal"
const S22a = (f: number) => dolly(C([0.35, 1.2, 2.5]), C([0.25, 0.88, 0.0]), pushK(f, 1747, 0.0028, 0.006, 25), { fov: 40 }); // CU: one screw, one man
const S22b = (f: number) => dolly(C([8.8, 1.1, 3.6]), C([-2, 0.55, 0.0]), pushK(f, 1800, 0.002), { fov: 42 });
const S23a = (f: number) => dolly(C([-9.5, 1.6, 3.9]), C([4, 0.6, 0.0]), pushK(f, 1856, 0.002, 0.006, 30), { fov: 44, roll: -0.04 });
const S24a = (f: number) => dolly(C([1.0, 1.75, 1.25]), C([0.5, 1.78, 0.24]), pushK(f, 1894, 0.002), { fov: 30 });
const S25a = (f: number) => dolly(C([-4.4, 1.35, -1.6]), C([-5.2, 0.7, -6.2]), pushK(f, 1976, 0.0025), { fov: 44 });
const S38a = (f: number) => dolly(C([0.3, 1.15, 2.6]), C([0.25, 0.88, 0.0]), pushK(f, 3110, 0.002, 0.005, 30), { fov: 38 });
// Lake Street row (north row, x 9..49)
const rowY = (id: number, f: number) => liftAt("row", id, f);
const S26a = (f: number) => dolly([58, 1.8, 9], [29, 2.4 + 0.3 * rowY(26, f), -12], pushK(f, 2066, 0.0016), { fov: 46 });
const S26b = (f: number) => dolly([42, 1.8, 7.5], [24, 2.6 + 0.4 * rowY(26, f), -12], pushK(f, 2160, 0.0018, 0.004, 30), { fov: 44 });
const S27a = (f: number) => dolly([38.5, 1.05, -5.4], [25, 0.7 + 0.4 * rowY(27, f), -11.6], pushK(f, 2224, 0.002), { fov: 42, roll: 0.03 });
const S28a = (f: number) => dolly([14.5, 1.8, -6.0], [16.9, 1.2 + 0.5 * rowY(28, f), -12], pushK(f, 2330, 0.002), { fov: 40 });
const S29a = (f: number) => dolly([30.5, 2.8, -4.8], [29, 1.42 + 1.3, -12.6], pushK(f, 2420, 0.003), { fov: 40 });
const S30a = (f: number) => dolly([31.6, 1.7, -5.2], [29.0, 1.05, -10.8], pushK(f, 2482, 0.0025), { fov: 42, roll: -0.03 });
// Tremont House (south row, x 22..62)
const trY = (id: number, f: number) => liftAt("tremont", id, f);
const S31a = (f: number) => dolly([46.4, RAISE + 1.7, 1.4], [43.2, RAISE + 1.15, 8.6], pushK(f, 2566, 0.0025), { fov: 40 });
const S31b = (f: number) => dolly([47.4, RAISE + 1.7, 1.0], [43.2, RAISE + 1.2, 8.6], pushK(f, 2634, 0.002, 0.005, 30), { fov: 40, roll: 0.03 });
const S32a = (f: number) => dolly([70, RAISE + 2.2, -3], [42, 4.6 + trY(32, f), 12], pushK(f, 2683, 0.0016), { fov: 46 });
const S34a = (f: number) => dolly([45.5, RAISE + 1.9, 4.2], [42.0, 2.0 + 0.4 * trY(34, f), 10.2], pushK(f, 2844, 0.0025), { fov: 44 });
// dining room
const S33a = (f: number) => dolly(Dn([4.4, 2.1, 5.6]), Dn([-0.2, 1.05, -0.4]), pushK(f, 2789, 0.002), { fov: 44 });
const S35a = (f: number) => dolly(Dn([1.15, 1.35, 2.15]), Dn([0.05, 0.98, -0.3]), pushK(f, 2909, 0.0028, 0.006, 25), { fov: 42 });
// finished street, then the raised city from above
const S36a = (f: number) => dolly([-18, RAISE + 1.7, 7.5], [4, RAISE + 1.4, -4], pushK(f, 2976, 0.002), { fov: 42 });
const S37a = (f: number) => dolly([-130, 80, 70], [130, 2, -25], pushK(f, 3034, 0.0016, 0.004, 30), { fov: 42 });
// buried street section: a crane down the cut face from the strollers to the old doorway
const S39a = (f: number): Shot => {
  const u = glide((f - 3262) / 92);
  return { pos: Sc([0.8, 4.6 - 3.4 * u, 9.0]), look: Sc([0, 3.9 - 3.05 * u, -1]), fov: 44, roll: 0 };
};
// river at dusk
const S40a = (f: number) => dolly(Rv([-78, 7, -8]), Rv([10, 1.5, 4]), pushK(f, 3382, 0.0016), { fov: 42 });
const S41a = (f: number) => dolly(Rv([-6, 2.2, 10.5]), Rv([4, 0.2, 1.5]), pushK(f, 3497, 0.0018), { fov: 42 });

export const CAMS: Record<number, Key[]> = {
  1: [{ f: 0, s: S1a }, { f: 84, dur: 30, s: S1b }], // glide down onto the plank as he steps (centred on 99 "step")
  2: [{ f: 127, s: S2a }],
  3: [{ f: 209, s: S3a }],
  4: [{ f: 275, s: S4a }, { f: 330, dur: 34, s: S4b }], // tilt with the rise, roll on "air"
  5: [{ f: 388, s: S5a }],
  6: [{ f: 456, s: S6a }, { f: 545, cut: true, s: S6b }],
  7: [{ f: 611, s: S7a }],
  8: [{ f: 670, s: S8a }],
  9: [{ f: 727, s: S9a }],
  10: [{ f: 778, s: S10a }],
  11: [{ f: 845, s: S11a }],
  12: [{ f: 919, s: S12a }],
  13: [{ f: 1022, s: S13a }],
  14: [{ f: 1067, s: S14a }],
  15: [{ f: 1146, s: S15a }],
  16: [{ f: 1235, s: S16a }],
  17: [{ f: 1337, s: S17a }],
  18: [{ f: 1411, s: S18a }],
  19: [{ f: 1493, s: S19a }],
  20: [{ f: 1556, s: S20a }],
  21: [{ f: 1656, s: S21a }, { f: 1712, cut: true, s: S21b }],
  22: [{ f: 1747, s: S22a }, { f: 1800, cut: true, s: S22b }],
  23: [{ f: 1856, s: S23a }],
  24: [{ f: 1894, s: S24a }],
  25: [{ f: 1976, s: S25a }],
  26: [{ f: 2066, s: S26a }, { f: 2160, dur: 36, s: S26b }],
  27: [{ f: 2224, s: S27a }],
  28: [{ f: 2330, s: S28a }],
  29: [{ f: 2420, s: S29a }],
  30: [{ f: 2482, s: S30a }],
  31: [{ f: 2566, s: S31a }, { f: 2634, dur: 30, s: S31b }],
  32: [{ f: 2683, s: S32a }],
  33: [{ f: 2789, s: S33a }],
  34: [{ f: 2844, s: S34a }],
  35: [{ f: 2909, s: S35a }],
  36: [{ f: 2976, s: S36a }],
  37: [{ f: 3034, s: S37a }],
  38: [{ f: 3110, s: S38a }],
  39: [{ f: 3240, s: S39a }],
  40: [{ f: 3382, s: S40a }],
  41: [{ f: 3497, s: S41a }],
};

// impact kicks (reference v14): the image offset flips sign every frame (~3 px at 720p per unit), decays to 0 in
// 7 f, roll +-0.23 deg per unit; they start on the first frame at/after the event. No hand-held float.
// (seconds) the gentleman's boot in the mud, the building jacked up, the whistles
const KICKS: [number, number][] = [[100 / FPS, 0.7], [300 / FPS, 0.5], [1740 / FPS, 0.4], [1850 / FPS, 0.4]];

// ---------------- lens: depth of field ----------------
/** Lens blur per shot (thin lens). cInf = blur-disc radius in px at 1080x1920 for things at infinity; 0 = all sharp.
 *  Reference: DOF on in ~1/3 of shots: CU/hook 15-16, close-ups 12-14, MS 10-12; establishing/wide stay sharp.
 *  focus = world point (else the camera look point). */
export const DOF: Dof[] = [
  { f: 0, cInf: 12 }, // hook: the gentleman on the plank
  { f: 127, cInf: 0 }, // street wide
  { f: 209, cInf: 8 }, // the screws under the hero building
  { f: 275, cInf: 0 }, // the rise
  { f: 388, cInf: 12 }, // the shopkeeper in the doorway
  { f: 456, cInf: 0 }, // aerial
  { f: 611, cInf: 8 }, // the standing water
  { f: 670, cInf: 10 }, // horse and wagon
  { f: 727, cInf: 12 }, // gutter
  { f: 778, cInf: 10 }, // notice
  { f: 845, cInf: 12 }, // officials over the plan
  { f: 919, cInf: 0 }, // pipes laid (wide)
  { f: 1022, cInf: 10 }, // shovels
  { f: 1067, cInf: 0 }, // fill rising, wide
  { f: 1337, cInf: 8 }, // the pit
  { f: 1411, cInf: 0 },
  { f: 1493, cInf: 0 }, // diggers
  { f: 1556, cInf: 0 }, // rows of screws
  { f: 1712, cInf: 12 }, // foreman
  { f: 1747, cInf: 14 }, // CU screw
  { f: 1800, cInf: 0 }, // row
  { f: 1894, cInf: 4 }, // beam gauge
  { f: 1976, cInf: 0 }, // masons
  { f: 2066, cInf: 0 }, // Lake Street row
  { f: 2330, cInf: 10 }, // gauge
  { f: 2420, cInf: 10 }, // shop open
  { f: 2482, cInf: 8 }, // stairs
  { f: 2566, cInf: 12 }, // Pullman
  { f: 2683, cInf: 0 }, // Tremont
  { f: 2789, cInf: 10, focus: () => add(DINING, [0, 1.1, 0]) }, // dining wide: the middle table sharp
  { f: 2844, cInf: 8 }, // checking out
  { f: 2909, cInf: 12, focus: () => add(DINING, [-0.25, 1.15, -0.7]) }, // teacup CU: the reader's eyes
  { f: 2976, cInf: 0 }, // finished street, aerial
  { f: 3110, cInf: 14 }, // quarter turn CU
  { f: 3240, cInf: 0 }, // section
  { f: 3382, cInf: 0 }, // river
  { f: 3497, cInf: 10, focus: (f) => add(RIVER, [lin([[3382, 9], [3614, -1]], f), 0.2, 10 * Math.sin(lin([[3382, 9], [3614, -1]], f) / 45) + 3]) }, // the rower
];

export const camAt = makeCamAt(CAMS, KICKS);
export const keyEnd = (id: number, f: number) => keyEndOf(CAMS[id], f);
export const dofAt = (f: number) => dofAtOf(DOF, f);
export const shotAt = (f: number) => shotAtOf(SHOTS, f);
export const layersAt = (f: number) => layersAtOf(SHOTS, XFADE, f);
export const focusAt = (id: number, f: number): V3 => {
  const d = dofAt(f);
  return d.focus ? d.focus(f) : camAt(id, f).look;
};
