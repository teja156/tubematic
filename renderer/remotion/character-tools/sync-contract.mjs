#!/usr/bin/env node
//
// The code-drawn character styles (Mid-century How-To, Process Cast, Comic
// Panels, Puppet History): rewrite the two files the Python side reads from
// the renderer's own code, so they cannot drift by hand:
//
//   tubematic_core/style_packs/<style>.json        its `extra` block (the
//       catalogues the agent picks from)
//   mcp/tests/fixtures/<style>_contract.json       the constants and cases the
//       renderer's contract.ts and stage.ts work out
//
//   node character-tools/sync-contract.mjs [style...]     (from renderer/remotion)
//
// With no style it rewrites all of them. Run it after changing a catalogue, a
// limit, a box or stage.ts; the tests on both sides fail until it has run. It
// bundles a small entry per style with esbuild (a dependency of the Remotion
// bundler) and runs it in this process; nothing is typechecked here.

import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { createRequire } from "node:module";

const REMOTION = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const REPO = path.resolve(REMOTION, "../..");
const require = createRequire(import.meta.url);
const esbuild = require("esbuild");

const ABOUT = (style, dir) =>
  `Shared by renderer/remotion/src/scenes/installed/${dir}/${dir}.test.ts and mcp/tests/test_${style}.py: the constants both sides use, and cases worked out by the renderer's own contract.ts and stage.ts. Written by renderer/remotion/character-tools/sync-contract.mjs; never edit it by hand.`;

// Each style: its folder, and an entry that sets globalThis.__out = { extra, fixture }.
const STYLES = {
  midcentury_howto: {
    dir: "midcenturyHowTo",
    entry: (D, about) => `
import { AIM_POSES, SUMMARY_POSES, CUSTOM, ENTRANCES, EVENT_TYPES, FACES, GEOMETRY, GROUNDS, HAIRS, LIMITS, OBJECTS, OBJECT_SCALE, OUTFITS, POSES, SIDES, TIMING,
  inReach, insetBox, labelBox, objectBox, presenterBox, screenLines } from "${D}/contract";
import { pressPoint, blinkAt } from "${D}/stage";
const extra = {
  grounds: Object.keys(GROUNDS), poses: [...POSES], summary_poses: [...SUMMARY_POSES], faces: [...FACES], outfits: [...OUTFITS], hairs: [...HAIRS],
  sides: [...SIDES], entrances: [...ENTRANCES],
  objects: Object.fromEntries(Object.entries(OBJECTS).map(([k, v]) => [k, { text: v.text, acts: [...v.acts] }])),
};
const obj = (object, x, y, scale) => ({ key: object, object, x: x * 1080, y: y * 1920, scale, since: 0, enter: "pop", text: "", act: "", actAt: -1 });
globalThis.__out = { extra, fixture: {
  _about: ${JSON.stringify(about)},
  constants: { LIMITS, TIMING, GEOMETRY, GROUNDS, EVENT_TYPES, POSES, SUMMARY_POSES, AIM_POSES, FACES, OUTFITS, HAIRS, SIDES, ENTRANCES, OBJECTS, OBJECT_SCALE, CUSTOM },
  object_box: [["phone", 0.66, 0.52, 1], ["keypad", 0.5, 0.55, 1.2], ["table", 0.72, 0.66, 0.8]].map(([o, x, y, s]) => ({ object: o, x, y, scale: s, box: objectBox(o, x, y, s) })),
  label_box: [["Settings", 0.5, 0.4], ["Six digits, 30 seconds", 0.3, 0.7]].map(([t, x, y]) => ({ text: t, x, y, box: labelBox(t, x, y) })),
  inset_box: [[0.8, 0.4]].map(([x, y]) => ({ x, y, box: insetBox(x, y) })),
  presenter_box: ["left", "right"].map((s) => ({ side: s, box: presenterBox(s) })),
  in_reach: [["left", 500, 900], ["left", 900, 700], ["right", 600, 900], ["right", 100, 1000], ["none", 540, 900]].map(([s, x, y]) => ({ side: s, x, y, reach: inReach(s, x, y) })),
  press_point: [["phone", "row2"], ["laptop", "row1"], ["window", "row3"], ["keypad", ""], ["lock", ""]].map(([o, a]) => ({ object: o, act: a, point: pressPoint(obj(o, 0.5, 0.5, 1.2), a) })),
  screen_lines: ["Settings|Profile|Security|Privacy", "A | B ||C|D|E", ""].map((t) => ({ text: t, lines: screenLines(t) })),
  blink: [0, 1, 50, 99, 100, 101, 300].map((f) => ({ frame: f, seed: 17, blink: blinkAt(f, 17) })),
} };
`,
  },
};

async function sync(style) {
  const spec = STYLES[style];
  if (!spec) throw new Error(`unknown style ${style}; one of ${Object.keys(STYLES).join(", ")}`);
  const dir = `./src/scenes/installed/${spec.dir}`;
  const built = await esbuild.build({
    stdin: { contents: spec.entry(dir, ABOUT(style, spec.dir)), resolveDir: REMOTION, loader: "tsx" },
    bundle: true, platform: "node", format: "cjs", jsx: "automatic", write: false, logLevel: "error",
  });
  new Function("require", "module", "exports", built.outputFiles[0].text)(require, { exports: {} }, {});
  const { extra, fixture } = globalThis.__out;
  const packPath = path.join(REPO, `tubematic_core/style_packs/${style}.json`);
  const pack = JSON.parse(fs.readFileSync(packPath, "utf8"));
  pack.extra = JSON.parse(JSON.stringify(extra));
  fs.writeFileSync(packPath, JSON.stringify(pack, null, 2) + "\n");
  const fixturePath = path.join(REPO, `mcp/tests/fixtures/${style}_contract.json`);
  fs.writeFileSync(fixturePath, JSON.stringify(fixture, null, 2) + "\n");
  process.stdout.write(`wrote ${path.relative(REPO, packPath)} and ${path.relative(REPO, fixturePath)}\n`);
}

const wanted = process.argv.slice(2);
for (const style of wanted.length ? wanted : Object.keys(STYLES)) await sync(style);
