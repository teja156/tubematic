// The contract a Low-Poly Skit video implements (TMDEV-250). Like Cartoon 3D's VideoDef, everything is a pure function of
// the frame number, so stills, the beat gate and the render agree. Unlike it there is no cast of cards, ink or lens:
// each set builds its own figures (figure.ts) and poses them in `pose`, and the shot is a hard cut on a plain light rig.
import type { Cam } from "../camera";
import type { SetPiece } from "../kit/set";

export type LPShot = { id: number; a: number; b: number; set: string; note: string };

export type LowPolyLight = {
  ambient: number;
  key: number;
  /** direction the key light comes FROM, relative to the set's origin */
  keyFrom: [number, number, number];
  keyColor: string;
  fill: number;
  fillColor: string;
};
export const DEFAULT_LIGHT: LowPolyLight = { ambient: 1.05, key: 1.5, keyFrom: [3, 5, 4], keyColor: "#fff1dc", fill: 0.35, fillColor: "#bcd0ff" };

export interface LowPolyDef {
  total: number;
  shots: LPShot[];
  camAt(id: number, f: number): Cam;
  /** the sets, built once; every set sits far from the others and one is shown per shot */
  sets(): Record<string, SetPiece>;
  /** the colour behind a set (the void it stands on): a grey for a diorama, black for space */
  background(set: string): string;
  light?(shot: LPShot): Partial<LowPolyLight>;
  /** 0 to 1: smear this frame (a whip, an impact). Costs extra renders on these frames only. */
  blurAt?(id: number, f: number): number;
}

export const shotOf = (shots: LPShot[], f: number) => shots.find((s) => f >= s.a && f < s.b) ?? shots[shots.length - 1];
export type { Cam, SetPiece };
