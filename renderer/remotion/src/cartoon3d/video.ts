// The contract a Cartoon 3D video implements (TMDEV-185). The authoring agent writes one module per video exporting a
// VideoDef: its shots (one per sentence or part of one, timed to the narration's word frames), the camera for every
// frame (built with camera.ts's grammar), the sets (three.js code against kit/*), who stands where in every shot
// (kit/cast.ts staging), and the lens. CartoonShort.tsx renders it inside Tubematic's Composition; kit/world.ts
// drives it. Everything here is a pure function of the frame number, so stills, the beat gate and the render agree.
import type * as THREE from "three";
import type { CamInfo, Stage } from "./kit/cast";
import type { SetPiece } from "./kit/set";
import type { InkOptions } from "./post/ink";
import type { LightName } from "./kit/lights";
import type { Cam, Dof } from "./camera";

export const FPS = 30;
export type V3 = [number, number, number];
export type Light = LightName;

/** one shot: frames [a, b), its light preset, which set it is on, and the sentence or part of one it illustrates */
export type ShotDef = {
  id: number;             // 1-based, in order, contiguous frames: shot n ends where shot n+1 starts
  a: number; b: number;   // frames; b exclusive; the last shot's b is the video's total
  light: Light;
  set: string;            // a key of sets()
  note: string;           // what the frame shows (the beat gate's judges read the SENTENCE; this is for the author)
  aerial?: boolean;       // a view from far above: the shadow map, fog and clip planes cover the whole set
  sunAz?: number; sunEl?: number;   // camera-relative sun in degrees (default: outdoor day az 128 / el 56, else the preset)
};

export interface VideoDef {
  total: number;                          // frames, = timeline.totalFrames
  shots: ShotDef[];
  /** crossfade frames keyed by the id of the shot being faded IN (place or time changes only); a cut otherwise */
  xfade: Record<number, number>;
  /** a 4-frame white flash starting here (the reference's hook flash), if any */
  flashAt?: number;
  camAt(id: number, f: number): Cam;
  /** near/far per shot: as much depth precision as the shot can use (the post passes take them every frame) */
  clipAt(id: number): { near: number; far: number };
  dofAt(f: number): { cInf: number; focus?: (f: number) => V3 };
  /** the sets, built once per World; every set is placed far from the others and one is shown per shot */
  sets(): Record<string, SetPiece>;
  /** whether a set is under the sky (clouds, sky dome, sun disc) */
  outdoor(set: string): boolean;
  /** an interior whose windows show the sky dome (default: only outdoor sets show it) */
  skyVisible?(set: string): boolean;
  /** who stands where, doing what, at frame f of shot id */
  stage(id: number, f: number, cam: CamInfo): Stage;
  /** per-shot ink overrides on top of the kit defaults (exterior, interior, aerial) */
  inkFor?(shot: ShotDef): Partial<InkOptions> | undefined;
}

export type { Cam, Dof, CamInfo, Stage, SetPiece };
export type Camera = THREE.PerspectiveCamera;
