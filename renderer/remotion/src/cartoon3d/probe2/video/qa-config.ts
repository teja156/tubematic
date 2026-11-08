// Headless runner for the deterministic check on a scene-config.json — the
// file the authoring agent actually writes — rather than a TypeScript world.
// Finds the Cartoon3D scene and checks its world, beats and opts.
//   node qa-config.mjs <scene-config.json>
// Exit 0 when nothing blocks, 2 when something does.
import { installDomShim } from "../domShim";
import { ensureCodeBuilder } from "../parts";
installDomShim();
ensureCodeBuilder();
import * as fs from "node:fs";
import { checkWorld } from "../qa";
import { cartoonScene } from "./sceneConfig";

const file = process.argv[2];
if (!file) {
  console.error("usage: qa-config <scene-config.json>");
  process.exit(1);
}
const config = JSON.parse(fs.readFileSync(file, "utf8")) as { totalFrames?: number };
const { world, beats, opts } = cartoonScene(config);
const t0 = Date.now();
const { findings, counts } = checkWorld(world, beats, opts, config.totalFrames);
const blocking = findings.filter((f) => f.gate === "block").length;
console.log(`=== ${world.name} === ${findings.length} findings (${blocking} blocking) in ${Date.now() - t0}ms, all ${beats[beats.length - 1].end + 1} frames`);
console.log("  placed: " + Object.entries(counts).map(([k, v]) => `${k}=${v}`).join(" "));
for (const f of findings) console.log(`  [${f.gate.toUpperCase()}] beat ${f.beat} f${f.frame} ${f.who}: ${f.kind} - ${f.detail}`);
if (!findings.length) console.log("  clean");
process.exit(blocking ? 2 : 0);
