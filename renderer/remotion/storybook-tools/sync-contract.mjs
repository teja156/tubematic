#!/usr/bin/env node
//
// Storybook Atlas: rewrite the two files the Python side reads from the
// renderer's own code, so they cannot drift by hand:
//
//   tubematic_core/style_packs/storybook_atlas.json   its `extra` block (coats,
//       backdrops, poses, the people's knobs and the prop catalogue)
//   mcp/tests/fixtures/storybook_atlas_contract.json   the constants and the
//       cases stage.ts works out (title wrapping, walk timing, actorAt)
//
//   node storybook-tools/sync-contract.mjs          (from renderer/remotion)
//
// Run it after changing a prop, a backdrop, a knob, a limit or stage.ts; the
// tests on both sides (storybookAtlas.test.ts, test_storybook_atlas.py) fail
// until it has run. It bundles a small entry with esbuild (a dependency of the
// Remotion bundler) and runs it in this process; nothing is typechecked here.

import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { createRequire } from "node:module";

const REMOTION = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const REPO = path.resolve(REMOTION, "../..");
const SA = "./src/scenes/installed/storybookAtlas";
const require = createRequire(import.meta.url);
const esbuild = require("esbuild");

const entry = `
import { ACTS } from "${SA}/props/types";
import { BACKDROPS } from "${SA}/backdrops";
import { ENTERS, FACINGS, GLYPHS, LIMITS, PLATE_EVENTS, PROPS, PROP_ENTRANCES, STAGE, TIMING, wrapTitle } from "${SA}/contract";
import { BUILDS, FACES, GARMENTS, HAIRS, HAIR_COLORS, HATS, PERSON_POSES } from "${SA}/figure";
import { GUIDE_POSES } from "${SA}/guide";
import { COAT_COLORS, GARMENT_COLORS, SKIN } from "${SA}/palette";
import { actorAt, walkFrames } from "${SA}/stage";

const extra = {
  coats: Object.keys(COAT_COLORS),
  backdrops: [...BACKDROPS],
  guidePoses: [...GUIDE_POSES],
  personPoses: [...PERSON_POSES],
  knobs: {
    build: [...BUILDS], skin: Object.keys(SKIN), hair: [...HAIRS], hairColor: [...HAIR_COLORS], face: [...FACES],
    hat: [...HATS], garment: [...GARMENTS], color: Object.keys(GARMENT_COLORS),
  },
  props: PROPS,
};
const walks = [
  { start: 210, moves: [{ at: 30, x: 600, pose: "point" }], frames: [0, 30, 40, 73, 74, 100] },
  { start: null, moves: [{ at: 10, x: 300 }, { at: 100, exit: true }], frames: [9, 10, 20, 40, 60, 100, 110, 160, 200] },
  { start: 500, moves: [{ at: 0, x: 900 }, { at: 20, x: 100 }], frames: [10, 20, 30, 80, 120] },
  { start: null, moves: [{ at: 0, x: 800, pose: "hold" }, { at: 50, pose: "think" }], frames: [0, 15, 29, 30, 50, 60] },
];
const fixture = {
  _about: "Shared by renderer/remotion/src/scenes/installed/storybookAtlas/storybookAtlas.test.ts and mcp/tests/test_storybook_atlas.py: the constants both sides use, and cases worked out by the renderer's own stage.ts. Written by renderer/remotion/storybook-tools/sync-contract.mjs; never edit it by hand.",
  constants: { LIMITS, TIMING, STAGE, ACTS, ENTERS, FACINGS, GLYPHS, PLATE_EVENTS, PROP_ENTRANCES },
  wrap_title: ["The Machine", "A Moth in Relay Seventy", "The Logbook of Harvard Mark II", "Supercalifragilistic word"].map((t) => ({ title: t, lines: wrapTitle(t) })),
  walk_frames: [[210, 600], [-160, 300], [900, 100]].map(([a, b]) => ({ a, b, frames: walkFrames(a, b) })),
  actor_at: walks.map((w) => ({ ...w, states: w.frames.map((f) => { const s = actorAt(w.moves, f, w.start); return { x: s.x, visible: s.visible, walking: s.walking }; }) })),
};
globalThis.__out = { extra, fixture };
`;

const built = await esbuild.build({
  stdin: { contents: entry, resolveDir: REMOTION, loader: "ts" },
  bundle: true, platform: "node", format: "cjs", jsx: "automatic", write: false, logLevel: "error",
});
new Function("require", "module", "exports", built.outputFiles[0].text)(require, { exports: {} }, {});
const { extra, fixture } = globalThis.__out;

const packPath = path.join(REPO, "tubematic_core/style_packs/storybook_atlas.json");
const pack = JSON.parse(fs.readFileSync(packPath, "utf8"));
pack.extra = JSON.parse(JSON.stringify(extra));
fs.writeFileSync(packPath, JSON.stringify(pack, null, 2) + "\n");
const fixturePath = path.join(REPO, "mcp/tests/fixtures/storybook_atlas_contract.json");
fs.writeFileSync(fixturePath, JSON.stringify(fixture, null, 2) + "\n");
process.stdout.write(`wrote ${path.relative(REPO, packPath)} (${Object.keys(extra.props).length} props) and ${path.relative(REPO, fixturePath)}\n`);
