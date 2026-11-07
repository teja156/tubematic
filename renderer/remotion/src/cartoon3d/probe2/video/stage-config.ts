// Writes <dir>/scene-config.json for the real Composition from JSON the
// authoring agent wrote — the shape a production agent hands write_scene_config:
//   node stage-config.mjs <dir> [--verdicts <verdict.json>]
// <dir> holds timeline.json (from the voice-over), world.json (a WorldSpec),
// beats.json (BeatSpec[]), and optionally opts.json (SceneOpts) and
// subtitles.json (the captions block; default: the plate-free outline style).
// A world with its own parts (world.parts) is refused unless every part has a
// PASS verdict for its current spec in the gate's verdict.json: the judge
// cannot be skipped.
import { installDomShim } from "../domShim";
import { ensureCodeBuilder } from "../parts";
installDomShim();
ensureCodeBuilder();
import * as fs from "node:fs";
import * as path from "node:path";
import { gateSpecs } from "../gate/codeSpecs";
import { readVerdicts, unpassed } from "../gate/verdicts";
import { CARTOON_SCENE_SRC } from "./sceneConfig";

const argv = process.argv.slice(2);
const dir = argv.find((a) => !a.startsWith("--"));
const vAt = argv.indexOf("--verdicts");
const verdictFile = vAt >= 0 ? argv[vAt + 1] : undefined;
if (!dir) {
  console.error("usage: stage-config <dir with timeline.json, world.json, beats.json> [--verdicts <verdict.json>]");
  process.exit(1);
}
const read = (name: string, required = true) => {
  const f = path.join(dir, name);
  if (!fs.existsSync(f)) {
    if (required) throw new Error(`missing ${f}`);
    return undefined;
  }
  return JSON.parse(fs.readFileSync(f, "utf8"));
};
const timeline = read("timeline.json");
const total: number = timeline.totalFrames;
const beats = read("beats.json") as { start: number; end: number }[];
const last = beats[beats.length - 1];
if (!last || last.end + 1 !== total) {
  console.error(`beats end at frame ${last?.end} but the timeline has ${total} frames: the last beat must end at ${total - 1}`);
  process.exit(2);
}
const world = read("world.json");
const ROOT = path.resolve(process.env.REMOTION_ROOT ?? process.cwd());
const parts = gateSpecs(world, ROOT) as Record<string, unknown>;
if (Object.keys(parts).length) {
  const missing = unpassed(parts, verdictFile ? readVerdicts(verdictFile) : { parts: {} });
  if (missing.length) {
    console.error(`parts without a PASS verdict for their current spec: ${missing.join(", ")} — run the gate (and its judge) first${verdictFile ? "" : " and pass --verdicts <verdict.json>"}`);
    process.exit(2);
  }
}
const config = {
  totalFrames: total,
  fps: timeline.fps ?? 30,
  canvas: "dark",
  subtitles: read("subtitles.json", false) ?? { background: "outline", fontFamily: "Montserrat", fontSize: 70, maxWords: 4 },
  scenes: [
    {
      type: "generated",
      source: "installed",
      src: CARTOON_SCENE_SRC,
      startFrame: 0,
      durationInFrames: total,
      props: { world, beats, opts: read("opts.json", false) ?? {} },
      transitionToNext: { durationInFrames: 0 },
    },
  ],
  sfx: [],
};
fs.writeFileSync(path.join(dir, "scene-config.json"), JSON.stringify(config, null, 2));
console.log(`scene-config.json: 1 scene, ${total} frames, ${JSON.stringify(config).length} bytes`);
