// The worked example of Low-Poly Skit (TMDEV-250): "What if you dug straight down?", 16 s, 14 shots, four sets. It is a
// small original story in Tubematic's own tone: second person, one new place or action per sentence, the scale
// climbing from a garden to the planet. Read it as the spelling of the kit: shots tile the video, the camera is built
// from camera.ts keys, a footstep jolt and an impact jolt come from `joltAt`, one whip lands on the globe.
import { dolly, joltAt, jolted, pushK, runKeys, whip, type Cam, type Key } from "../../../camera";
import { footfalls } from "../../cycles";
import type { LPShot } from "../../def";

export const TOTAL = 480;

/** the narration, for the author: one line per shot, the words each shot illustrates */
export const NARRATION = [
  "You start digging a hole in your garden.",            // 1 walks in, 2 digs
  "The soil is easy. Then comes the clay.",              // 3, 4
  "Then you hit solid rock.",                            // 5
  "So you fetch a bigger shovel.",                       // 6 a hit
  "Past the rock the ground gets hot.",                  // 7
  "Far hotter than any oven.",                           // 8
  "Word gets out, and the whole street comes to watch.", // 9
  "They cheer. You keep going.",                         // 10
  "At the centre, gravity pulls from every side at once.", // 11
  "So you float.",                                       // 12
  "And on the other side of the planet,",                // 13 a whip
  "you pop out. Welcome to the other side.",             // 14
];

export const SHOTS: LPShot[] = [
  { id: 1, a: 0, b: 30, set: "garden", note: "you walk to the lawn with a shovel" },
  { id: 2, a: 30, b: 60, set: "garden", note: "you dig the first hole" },
  { id: 3, a: 60, b: 95, set: "cutaway", note: "down in the soft soil" },
  { id: 4, a: 95, b: 125, set: "cutaway", note: "the orange clay" },
  { id: 5, a: 125, b: 155, set: "cutaway", note: "solid rock" },
  { id: 6, a: 155, b: 190, set: "cutaway", note: "a bigger shovel hits the rock" },
  { id: 7, a: 190, b: 225, set: "cutaway", note: "the ground turns hot" },
  { id: 8, a: 225, b: 260, set: "cutaway", note: "far hotter than an oven" },
  { id: 9, a: 260, b: 295, set: "crowd", note: "the street comes to watch" },
  { id: 10, a: 295, b: 335, set: "crowd", note: "they cheer" },
  { id: 11, a: 335, b: 375, set: "planet", note: "the centre of the planet" },
  { id: 12, a: 375, b: 410, set: "planet", note: "you float" },
  { id: 13, a: 410, b: 445, set: "planet", note: "a whip to the other side of the planet" },
  { id: 14, a: 445, b: 480, set: "planet", note: "you pop out on the other side" },
];

export const ORIGINS: Record<string, [number, number, number]> = { garden: [0, 0, 0], cutaway: [100, 0, 0], crowd: [200, 0, 0], planet: [300, 0, 0] };
const at = (set: string, p: [number, number, number]): [number, number, number] => [ORIGINS[set][0] + p[0], p[1], p[2]];
const cam = (set: string, pos: [number, number, number], look: [number, number, number], fov = 38, roll = 0): Cam => ({ pos: at(set, pos), look: at(set, look), fov, roll });

/** the depth of the hero in the cutaway at frame f (metres below the grass) */
export const depthAt = (f: number) => (f < 60 ? 0 : f < 95 ? 0.8 + (f - 60) * 0.02 : f < 125 ? 1.9 + (f - 95) * 0.03 : f < 155 ? 3.1 : f < 190 ? 3.2 : f < 225 ? 5.2 + (f - 190) * 0.02 : 6.3);

/** a framing of the hero in the shaft: the look point sits a little under his chest so he rides the upper half of the frame, above the captions */
const deep = (f: number, f0: number, dist = 3.2, rate = 0.0035, fov = 38, roll = 0) =>
  dolly(at("cutaway", [0.25, -depthAt(f) + 0.7, dist]), at("cutaway", [0, -depthAt(f) + 0.12, 0]), push(f, f0, rate), { fov, roll });
const push = (f: number, f0: number, rate = 0.0035) => pushK(f, f0, rate);
const KEYS: Record<number, Key[]> = {
  1: [{ f: 0, s: (f) => dolly(at("garden", [1.6, 1.3, 5.2]), at("garden", [0, 0.9, 0]), push(f, 0)) }],
  2: [{ f: 30, s: (f) => dolly(at("garden", [-1.2, 1.1, 3.0]), at("garden", [0, 0.9, 0]), push(f, 30, 0.005)) }],
  3: [{ f: 60, s: (f) => deep(f, 60) }],
  4: [{ f: 95, s: (f) => deep(f, 95) }],
  5: [{ f: 125, s: (f) => deep(f, 125, 3.0, 0.004) }],
  6: [{ f: 155, s: (f) => deep(f, 155, 2.8, 0.002) }],
  7: [{ f: 190, s: (f) => deep(f, 190) }],
  8: [{ f: 225, s: (f) => deep(f, 225, 2.4, 0.005, 36, 0.04) }],
  9: [{ f: 260, s: (f) => dolly(at("crowd", [0, 1.8, 7.5]), at("crowd", [0, 0.9, -1.5]), push(f, 260)) }],
  10: [{ f: 295, s: (f) => dolly(at("crowd", [0.8, 1.2, 4.6]), at("crowd", [0, 1.0, 0.4]), push(f, 295, 0.005)) }],
  11: [{ f: 335, s: (f) => dolly(at("planet", [-3, 0, 5.0]), at("planet", [-3, 0, 0]), push(f, 335)) }],
  12: [{ f: 375, s: (f) => dolly(at("planet", [-3.2, 0.2, 2.2]), at("planet", [-3, 0, 0]), push(f, 375, 0.004), { roll: 0.05 }) }],
  13: [{ f: 410, s: () => cam("planet", [-3, 0, 5.0], [-3, 0, 0]) }],
  14: [{ f: 445, s: (f) => dolly(at("planet", [3, 2.1, 3.2]), at("planet", [3, 1.5, 0]), push(f, 445, 0.004)) }],
};
const WHIP_FROM = 417, WHIP_FRAMES = 12;
const FEET = footfalls(0, 30, 0);
const HITS = [175];     // the shovel meets the rock
export const camAt = (id: number, f: number): Cam => {
  if (id === 13) {
    const a = cam("planet", [-3, 0, 5.0], [-3, 0, 0]), b = cam("planet", [3, 1.7, 4.0], [3, 1.4, 0]);
    return whip(a, b, f, WHIP_FROM, WHIP_FRAMES).cam;
  }
  return jolted(runKeys(KEYS[id], f), joltAt(id === 1 ? FEET : HITS, f) * (id === 6 ? 2.2 : 0.8));
};
export const blurAt = (id: number, f: number) => (id === 13 ? whip(cam("planet", [0, 0, 0], [0, 0, 1]), cam("planet", [1, 0, 0], [0, 0, 1]), f, WHIP_FROM, WHIP_FRAMES).blur : 0);
export const FOOTFALLS = FEET;
export const BURST_AT = 175;
