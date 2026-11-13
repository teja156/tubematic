#!/usr/bin/env node
//
// Isometric Infographic: rewrite the two files the Python side reads from the
// renderer's own code, so they cannot drift by hand:
//
//   tubematic_core/style_packs/isometric_infographic.json   its `extra` block
//       (the prop library, the colours, the area kinds, which props open or
//       separate, the solids)
//   mcp/tests/fixtures/isometric_infographic_contract.json  the constants and
//       the cases contract.ts and stage.ts work out
//
//   node isometric-tools/sync-contract.mjs          (from renderer/remotion)

import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { createRequire } from "node:module";

const REMOTION = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const REPO = path.resolve(REMOTION, "../..");
const ISO = "./src/scenes/installed/isometric";
const require = createRequire(import.meta.url);
const esbuild = require("esbuild");

const entry = `
import { AREA_KINDS, COLOR_NAMES, GEOMETRY, LIMITS, MOVERS, PROP_NAMES, ROOMS, SOLIDS, STACKS, TIMING, eventFrames, grouped } from "${ISO}/contract";
import { quietSpans, readoutAt, viewAt } from "${ISO}/stage";

const extra = {
  props: [...PROP_NAMES], colors: [...COLOR_NAMES], areas: [...AREA_KINDS], rooms: [...ROOMS], stacks: [...STACKS],
  movers: [...MOVERS], solids: [...SOLIDS],
};
const data = {
  title: "TRIP",
  readout: { label: "HOURS", unit: "h", steps: [{ value: 0, at: 10 }, { value: 24, at: 100 }, { value: 36, at: 400, red: true }] },
  legend: { at: 420, items: [{ color: "red", label: "PARCEL" }] },
  boards: [
    { start: 0, areas: [], props: [{ id: "a", what: "house", at: [2, 2] }, { id: "b", what: "factory", at: [7, 7], enter: 50 }],
      routes: [{ id: "r", points: [[2, 2], [7, 7]], color: "red", at: 60 }], movers: [{ route: "r", what: "truck", at: 70 }],
      pins: [{ on: "b", label: "DEPOT", at: 80 }], camera: [{ at: 120, focus: "b", zoom: 1.6 }, { at: 200 }],
      lifts: [{ prop: "b", at: 220 }] },
    { start: 300, areas: [], props: [{ id: "h", what: "house", at: [5, 5] }], camera: [{ at: 360, focus: "h", zoom: 2 }] },
  ],
};
const total = 500;
const fixture = {
  _about: "Shared by renderer/remotion/src/scenes/installed/isometric/isometric.test.ts and mcp/tests/test_isometric_infographic.py: the constants both sides use, and cases worked out by the renderer's own contract.ts and stage.ts. Written by renderer/remotion/isometric-tools/sync-contract.mjs; never edit it by hand.",
  constants: { LIMITS, TIMING, GEOMETRY },
  data, total,
  event_frames: data.boards.map((b) => eventFrames(b)),
  quiet_spans: quietSpans(data, total),
  readout_at: [0, 10, 100, 109, 118, 400, 418].map((f) => ({ frame: f, ...readoutAt(data, f) })),
  view_at: [0, 120, 132, 144, 200, 230].map((f) => ({ frame: f, ...viewAt(data.boards[0], f) })),
  grouped: [0, 36, 1234, 999999].map((n) => ({ n, text: grouped(n) })),
};
globalThis.__out = { extra, fixture };
`;

const built = await esbuild.build({
  stdin: { contents: entry, resolveDir: REMOTION, loader: "ts" },
  bundle: true, platform: "node", format: "cjs", jsx: "automatic", write: false, logLevel: "error",
});
new Function("require", "module", "exports", built.outputFiles[0].text)(require, { exports: {} }, {});
const { extra, fixture } = globalThis.__out;

const packPath = path.join(REPO, "tubematic_core/style_packs/isometric_infographic.json");
const pack = JSON.parse(fs.readFileSync(packPath, "utf8"));
pack.extra = JSON.parse(JSON.stringify(extra));
fs.writeFileSync(packPath, JSON.stringify(pack, null, 2) + "\n");
const fixturePath = path.join(REPO, "mcp/tests/fixtures/isometric_infographic_contract.json");
fs.writeFileSync(fixturePath, JSON.stringify(fixture, null, 2) + "\n");
process.stdout.write(`wrote ${path.relative(REPO, packPath)} (${extra.props.length} props) and ${path.relative(REPO, fixturePath)}\n`);
