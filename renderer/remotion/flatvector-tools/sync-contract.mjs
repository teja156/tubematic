#!/usr/bin/env node
//
// Flat Vector Science: rewrite the two files the Python side reads from the
// renderer's own code, so they cannot drift by hand:
//
//   tubematic_core/style_packs/flat_vector_science.json   its `extra` block (the
//       prop library by group with each prop's box, the backdrops and the
//       other catalogues)
//   mcp/tests/fixtures/flat_vector_science_contract.json  the constants and the
//       cases contract.ts and stage.ts work out (events, still stretches,
//       counters, steps, pill widths)
//
//   node flatvector-tools/sync-contract.mjs          (from renderer/remotion)
//
// Run it after changing a prop, a limit, contract.ts or stage.ts; the tests on
// both sides (flatVector.test.ts, test_flat_vector_science.py) fail until it
// has run. It bundles a small entry with esbuild and runs it in this process.

import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { createRequire } from "node:module";

const REMOTION = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const REPO = path.resolve(REMOTION, "../..");
const FV = "./src/scenes/installed/flatVector";
const require = createRequire(import.meta.url);
const esbuild = require("esbuild");

const entry = `
import {
  BACKDROPS, CATALOGUE, CUTS, GEOMETRY, LIMITS, SHOT_KINDS, SIZES, SLOTS, TIMING, eventFrames, grouped, pillWidth, propScale,
} from "${FV}/contract";
import { PROPS } from "${FV}/props";
import { counterValue, quietSpans, stepAt } from "${FV}/stage";

const extra = {
  props: CATALOGUE,
  boxes: Object.fromEntries(Object.entries(PROPS).map(([k, p]) => [k, p.box])),
  lights: Object.keys(PROPS).filter((k) => PROPS[k].light),
  shotKinds: [...SHOT_KINDS], backdrops: [...BACKDROPS], slots: [...SLOTS], sizes: [...SIZES], cuts: [...CUTS],
};
const data = {
  shots: [
    { kind: "subject", start: 0, backdrop: "abyss", items: [{ what: "whale", slot: "center", size: "l" }, { what: "diver", slot: "bottom", size: "s", at: 40 }],
      pills: [{ on: "center", parts: [{ text: "SPERM WHALE", at: 20 }, { text: "16 M", at: 60, red: true }] }], rule: { beside: "center", label: "16 M", at: 80 },
      counter: { label: "DEPTH", value: 2000, unit: "m", at: 10 } },
    { kind: "ladder", start: 200, backdrop: "night", rungs: [{ what: "earth", label: "EARTH", value: "12,742 KM", at: 210 }, { what: "sun", label: "SUN", value: "1.4M KM", at: 260 }] },
    { kind: "zoom", start: 360, backdrop: "night", cut: "lens", levels: [{ what: "earth", label: "10,000 KM", at: 362 }, { what: "sun", label: "1M KM", at: 420 }] },
    { kind: "descent", start: 520, backdrop: "ocean", cut: "flash", label: "DEPTH", unit: "m", layers: [{ name: "DIVER", value: 40, at: 530 }, { name: "BOTTOM", value: 10900, at: 600, red: true }] },
    { kind: "stages", start: 700, backdrop: "inside", cut: "push", steps: [{ what: "virus", label: "ENTERS", at: 710 }, { what: "cell", label: "COPIES", at: 760 }] },
  ],
};
const total = 860;
const fixture = {
  _about: "Shared by renderer/remotion/src/scenes/installed/flatVector/flatVector.test.ts and mcp/tests/test_flat_vector_science.py: the constants both sides use, and cases worked out by the renderer's own contract.ts and stage.ts. Written by renderer/remotion/flatvector-tools/sync-contract.mjs; never edit it by hand.",
  constants: { LIMITS, TIMING, GEOMETRY },
  data, total,
  event_frames: data.shots.map((s) => eventFrames(s)),
  quiet_spans: quietSpans(data, total),
  counter_value: [0, 10, 22, 34, 60].map((f) => ({ frame: f, value: counterValue(data.shots[0].counter, f, 500) })),
  step_at: [205, 210, 220, 231, 259, 260, 300].map((f) => ({ frame: f, ...stepAt([210, 260], f) })),
  pill_width: [[{ text: "SPERM WHALE" }, { text: "16 M" }], [{ text: "OCEAN" }]].map((parts) => ({ parts, width: pillWidth(parts) })),
  grouped: [0, 40, 1000, 10900, 1234567].map((n) => ({ n, text: grouped(n) })),
  prop_scale: [["whale", "l"], ["bus", "s"], ["dna", "m"]].map(([w, s]) => ({ what: w, size: s, scale: propScale(PROPS[w].box, s) })),
};
globalThis.__out = { extra, fixture };
`;

const built = await esbuild.build({
  stdin: { contents: entry, resolveDir: REMOTION, loader: "tsx" },
  bundle: true, platform: "node", format: "cjs", jsx: "automatic", write: false, logLevel: "error",
});
new Function("require", "module", "exports", built.outputFiles[0].text)(require, { exports: {} }, {});
const { extra, fixture } = globalThis.__out;

const packPath = path.join(REPO, "tubematic_core/style_packs/flat_vector_science.json");
const pack = JSON.parse(fs.readFileSync(packPath, "utf8"));
pack.extra = JSON.parse(JSON.stringify(extra));
fs.writeFileSync(packPath, JSON.stringify(pack, null, 2) + "\n");
const fixturePath = path.join(REPO, "mcp/tests/fixtures/flat_vector_science_contract.json");
fs.writeFileSync(fixturePath, JSON.stringify(fixture, null, 2) + "\n");
process.stdout.write(`wrote ${path.relative(REPO, packPath)} (${Object.keys(extra.boxes).length} props) and ${path.relative(REPO, fixturePath)}\n`);
