// Entry point for the GPU probe (TMDEV-178), separate from src/index.ts on
// purpose: the main entry bundles every agent-written scene under
// scenes/generated/, and one broken file there fails the whole bundle. Through
// that entry a broken scene would read as "GPU not usable". The probe must
// answer one question — which GL device does this Chromium get — and nothing
// else.
import { registerRoot } from "remotion";
import { GpuProbeRoot } from "./GpuProbe";

registerRoot(GpuProbeRoot);
