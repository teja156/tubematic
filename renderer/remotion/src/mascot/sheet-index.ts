// The sheet renderer's own entry point (mascot-tools/render-sheet.mjs), never src/index.ts: that one bundles every
// agent-written scene, and one broken scene would fail the bundle and read as a broken mascot. Same reason as
// src/gpu-probe/index.ts.
import { registerRoot } from "remotion";
import { MascotSheetComposition } from "./MascotSheet";

registerRoot(MascotSheetComposition);
