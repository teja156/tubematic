#!/usr/bin/env node
//
// Night Signal: rewrite the two files the Python side reads from the
// renderer's own code, so they cannot drift by hand:
//
//   tubematic_core/style_packs/night_signal.json   its `extra` block (the
//       people, animals and objects of the library and the other catalogues)
//   mcp/tests/fixtures/night_signal_contract.json  the constants and the cases
//       contract.ts and stage.ts work out (event frames, still stretches,
//       tears, items, the timecode, font fits)
//
//   node nightsignal-tools/sync-contract.mjs          (from renderer/remotion)
//
// Run it after changing a part, a limit, contract.ts or stage.ts; the tests on
// both sides (nightSignal.test.ts, test_night_signal.py) fail until it has run.
// It bundles a small entry with esbuild (a dependency of the Remotion bundler)
// and runs it in this process; nothing is typechecked here.

import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { createRequire } from "node:module";

const REMOTION = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const REPO = path.resolve(REMOTION, "../..");
const NS = "./src/scenes/installed/nightSignal";
const require = createRequire(import.meta.url);
const esbuild = require("esbuild");

const entry = `
import {
  ANIMAL_NAMES, BUBBLES, CAMERA, CUTS, GEOMETRY, LIMITS, MARKS, OBJECT_NAMES, PEOPLE, SCENE_KINDS, SCREENS, SETTINGS,
  SHAPES, SLOTS, TIMING, TONES, eventFrames, fitFontSize, timecode,
} from "${NS}/contract";
import { itemAt, quietSpans, tearAt } from "${NS}/stage";

const extra = {
  people: [...PEOPLE], animals: [...ANIMAL_NAMES], objects: [...OBJECT_NAMES], sceneKinds: [...SCENE_KINDS],
  settings: [...SETTINGS], slots: [...SLOTS], screens: [...SCREENS], marks: [...MARKS], cuts: [...CUTS],
  bubbles: [...BUBBLES], shapes: [...SHAPES], tones: [...TONES],
};
const data = {
  file: { number: 7, title: "Case" },
  scenes: [
    { kind: "tableau", start: 0, setting: "night", items: [{ what: "person", slot: "left" }, { what: "person_phone", slot: "right", threat: true, redAt: 40, at: 20, to: { slot: "center", at: 60 } }], connector: { from: "left", to: "right", at: 70 }, bubble: { over: "left", icon: "qr", at: 90 } },
    { kind: "rule", start: 200, number: 1, lines: ["DON'T"], icon: "qr" },
    { kind: "rule", start: 300, cut: "hard", number: 2, lines: ["NEVER"], icon: "door", slashAt: 330 },
    { kind: "steps", start: 420, title: "STEPS", steps: [{ text: "One", at: 440 }, { text: "Two", at: 480 }] },
    { kind: "phone", start: 600, screen: "link", title: "PREVIEW", lines: ["a"], mark: { kind: "check", at: 640 } },
    { kind: "case", start: 760, label: "WITNESS", name: "DOUG", icon: "dog", bars: 3, stamp: { text: "CLOSED", at: 800 } },
    { kind: "camera", start: 900, label: "CAM 1", items: [{ what: "door", slot: "center" }], button: { text: "OPEN", crossAt: 950 } },
  ],
};
const total = 1100;
const item = data.scenes[0].items[1];
const fixture = {
  _about: "Shared by renderer/remotion/src/scenes/installed/nightSignal/nightSignal.test.ts and mcp/tests/test_night_signal.py: the constants both sides use, and cases worked out by the renderer's own contract.ts and stage.ts. Written by renderer/remotion/nightsignal-tools/sync-contract.mjs; never edit it by hand.",
  constants: { LIMITS, TIMING, CAMERA, GEOMETRY },
  data, total,
  event_frames: data.scenes.map((s) => eventFrames(s)),
  quiet_spans: quietSpans(data, total),
  tear_at: [197, 198, 199, 200, 201, 202, 300, 418, 419].map((f) => { const t = tearAt(data, f); return { frame: f, tear: t ? [t.into, t.progress] : null }; }),
  item_at: [0, 19, 20, 25, 30, 40, 43, 46, 60, 69, 78, 90].map((f) => { const s = itemAt(item, f); return { frame: f, visible: s.visible, x: s.x, red: s.red }; }),
  timecode: [[undefined, 0], ["03:12", 61], ["23:59", 1830], ["bad", 5]].map(([c, f]) => ({ clock: c ?? null, frame: f, text: timecode(c, f, 30) })),
  fit_font_size: [["RULE", 128], ["A LONGER LINE OF TEXT HERE", 96], ["X", 40]].map(([t, s]) => ({ text: t, size: s, fit: fitFontSize(t, s) })),
};
globalThis.__out = { extra, fixture };
`;

const built = await esbuild.build({
  stdin: { contents: entry, resolveDir: REMOTION, loader: "ts" },
  bundle: true, platform: "node", format: "cjs", jsx: "automatic", write: false, logLevel: "error",
});
new Function("require", "module", "exports", built.outputFiles[0].text)(require, { exports: {} }, {});
const { extra, fixture } = globalThis.__out;

const packPath = path.join(REPO, "tubematic_core/style_packs/night_signal.json");
const pack = JSON.parse(fs.readFileSync(packPath, "utf8"));
pack.extra = JSON.parse(JSON.stringify(extra));
fs.writeFileSync(packPath, JSON.stringify(pack, null, 2) + "\n");
const fixturePath = path.join(REPO, "mcp/tests/fixtures/night_signal_contract.json");
fs.writeFileSync(fixturePath, JSON.stringify(fixture, null, 2) + "\n");
process.stdout.write(`wrote ${path.relative(REPO, packPath)} (${extra.people.length + extra.animals.length + extra.objects.length} parts) and ${path.relative(REPO, fixturePath)}\n`);
