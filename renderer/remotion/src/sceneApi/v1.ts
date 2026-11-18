// Scene API v1 (TMDEV-252): what an external style package may import from the
// image, as `@tubematic/scene-api` (alias in webpack-override.mjs and tsconfig.json).
// tubematic_core/external_styles.py::SCENE_API is this version. A name here is a
// promise to every installed package: never remove or change one; a breaking
// change is a new file (v2.ts) and SCENE_API 2.
//
// Scene components get `durationInFrames` and `words: TimelineWord[]` from the
// composition, which also draws the captions, the watermark and the transitions.
export type { TimelineWord, SubtitleConfig } from "../scenes/installed/Subtitles";
export {
  FRAME_WIDTH, KEEP_OUT_GAP, KEEP_OUT_X, WATERMARK_BOTTOM, WATERMARK_HEIGHT, WATERMARK_LEFT,
  WATERMARK_RIGHT, WATERMARK_TOP, WATERMARK_WIDTH,
} from "../watermarkBox";
export { estimateWidth, fitFontSize, wrapCount } from "../scenes/installed/fitText";
export { fontFaceCss, useStyleFonts, type FontFile } from "../scenes/installed/characterKit/fonts";

// World styles (renderer "cartoon_3d"): the Cartoon 3D engine, its video
// definition and its camera helpers.
export { CartoonShort, INK_DEFAULTS } from "../cartoon3d/CartoonShort";
export { FPS, type Camera, type CamInfo, type Dof, type Light, type SetPiece, type ShotDef, type Stage,
  type V3, type VideoDef } from "../cartoon3d/video";
export {
  add, clamp01, dolly, easeOut, glide, keyEnd, kicked, kicksAt, layersAt, lin, makeCamAt, pushK, rolled,
  runKeys, shotAt, smooth, zoom, type Cam, type Key, type Shot,
} from "../cartoon3d/camera";
