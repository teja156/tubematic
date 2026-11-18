// Scene API v1 (TMDEV-252): what an external style package may import from the
// image as `@tubematic/scene-api`. Packages target this list, so removing or
// renaming a name breaks installed styles: that needs SCENE_API 2, never an edit here.
import { expect, it, vi } from "vitest";
import * as api from "./v1";

// The engine touches `document` when imported; its names are what is pinned here,
// and tsc checks that the re-exports resolve.
vi.mock("../cartoon3d/CartoonShort", () => ({ CartoonShort: () => null, INK_DEFAULTS: {} }));

it("exports the scene API v1 names", () => {
  expect(Object.keys(api).sort()).toEqual([
    "CartoonShort", "FPS", "FRAME_WIDTH", "INK_DEFAULTS", "KEEP_OUT_GAP", "KEEP_OUT_X",
    "WATERMARK_BOTTOM", "WATERMARK_HEIGHT", "WATERMARK_LEFT", "WATERMARK_RIGHT", "WATERMARK_TOP",
    "WATERMARK_WIDTH", "add", "clamp01", "dolly", "easeOut", "estimateWidth", "fitFontSize",
    "fontFaceCss", "glide", "keyEnd", "kicked", "kicksAt", "layersAt", "lin", "makeCamAt", "pushK",
    "rolled", "runKeys", "shotAt", "smooth", "useStyleFonts", "wrapCount", "zoom",
  ].sort());
});
