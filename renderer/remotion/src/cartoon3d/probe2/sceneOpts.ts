// PURE — per-video options that are not part of the world, shared by the
// renderer (WorldScene) and the headless checker (qa.ts).
import type { CameraMotion } from "./cameraMotion";

/** Camera grammar (kicks, emphasis, rolls) and anything else timed to the voice. */
export interface SceneOpts {
  motion?: CameraMotion;
  /** render path: "v1" = the hand-rolled InkPipeline (default), "v2" = the ported post stack
   *  (kit/post: MSAA ink pass, lens blur, bloom, neutral tone map, grade, two-tone world shading) */
  post?: "v1" | "v2";
  /** v2 only: world shading, two-tone (default) or plain Lambert; and a shadow switch, for A/B stills */
  shade?: "twoTone" | "lambert";
  shadows?: boolean;
  /** v2 debug: paint the two-tone lit side green and the shade side red */
  debugTone?: boolean;
  /** v2 debug: 1 = show the ink mask, 2 = show the world normal buffer */
  debugInk?: 0 | 1 | 2;
  /** A/B knobs for calibrating the golden look by stills (not for authoring) */
  tune?: { goldenAz?: number; goldShade?: readonly [number, number, number]; goldLift?: readonly [number, number, number]; keyGain?: number };
  /** v2 debug: switch post stages off for A/B stills */
  debugPost?: { ink?: boolean; lens?: boolean; bloom?: boolean; tone?: boolean; grade?: boolean };
}

/** The reference's MEDIAN hold creep (0.14 %/frame). The camera module's 0.25
 *  default compounds to a 44 % push over a 7 s hold on top of a shot's push. */
export const DEFAULT_MOTION: CameraMotion = { creep: 0.0014 };
export const motionOf = (o: SceneOpts): CameraMotion => ({ ...DEFAULT_MOTION, ...(o.motion ?? {}) });
