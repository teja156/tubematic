// A CODE PART: a prop the authoring agent writes as a three.js builder instead of a JSON spec, for anything the
// grammar cannot express (a sidewheel steamboat at full size, a telegraph key that taps, a door that comes off).
// It is judged by the same vision gate as a JSON part; its footprint is MEASURED from what it builds, never declared.
import type * as THREE from "three";
import type { PartCtx, PartMaterials } from "../../parts";

/** what a beat may ask a part to do this frame (see worldKit.ts BeatSpec.props[].act); any keys the part documents */
export type Act = Record<string, number>;

export interface AnimState {
  /** frame and seconds since the video started */
  f: number;
  t: number;
  /** 0..1 through the current beat */
  beatT: number;
  /** the beat's `act` for this prop (empty when none) */
  act: Act;
}

export interface CodePart {
  /** one line, what it is, for the gate's judge and the catalog */
  blurb: string;
  /** stands on y = 0 at the origin, faces +z, long axis along x; the same kit materials and ctx every part gets */
  build: (m: PartMaterials, ctx: PartCtx, seed: number) => THREE.Group;
  /** optional: pose the built group for this frame (wheel turns, key taps, door lifts). Must be a pure function of
   *  the state: the renderer and the stills call it per frame in any order. */
  animate?: (g: THREE.Group, s: AnimState) => void;
  /** which `act` keys animate() understands, with a one-line meaning each, for the author of beats */
  acts?: Record<string, string>;
  solid?: boolean;
  walkable?: boolean;
  lightAtNight?: boolean;
  /** smoke attach points in part space, like a JSON part's `smoke` */
  smoke?: { at: [number, number, number]; kind: "chimney" | "fire" | "stack" }[];
}
