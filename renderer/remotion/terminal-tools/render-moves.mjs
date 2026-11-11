#!/usr/bin/env node
//
// Terminal Doc custom-move preview.
//
// Draws the moves an agent wrote for one video (generated/<video_id>/move-*.tsx)
// on the "TerminalMovePreview" composition (src/scenes/installed/terminalDoc/
// TerminalMovePreview.tsx) and writes it as a PNG. Called by
// mcp/terminal_preview.py::render_preview for the preview_terminal_moves tool.
// The same runner as bean-tools/render-props.mjs, for another composition.
//
//   node terminal-tools/render-moves.mjs <spec_json> <out_png>
//
// <spec_json> is {"skin": "house"|"crt", "moves": [{"id", "src", "frames",
// "slot", "text"}]}, each src "<video_id>/move-<name>".
//
// Exit 0 with <out_png> written is success. Anything else exits non-zero with a
// message on stderr and leaves no <out_png>. stdout carries nothing: Remotion
// forwards browser console lines to it.
//
// Its own entry point, written per call into a private folder under
// terminal-tools/.tmp/ (inside the Remotion project so imports resolve against its
// node_modules), statically importing only this video's move files: never
// src/index.ts, which bundles every agent-written scene and would fail on any
// one of them. Software GL only (swangle), like the mascot sheets: the MCP
// container never gets the GPU.
//
// Deliberately .mjs and outside src/, like mascot-tools/render-sheet.mjs:
// nothing here is typechecked, and validate_job's `tsc` never sees it.

import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const PREVIEW_TIMEOUT_MS = 200_000; // under mcp/terminal_preview.py TIMEOUT_SECS
const REMOTION_ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const GENERATED = path.join(REMOTION_ROOT, "src", "scenes", "generated");
const SRC = /^[a-z0-9_-]{1,64}\/move-[a-z0-9-]{1,40}$/; // video ids are UUIDs (hyphens) or vid_ names
const ID = /^[a-z0-9_]{1,24}$/;

const die = (message, code = 1) => {
  process.stderr.write(`render-moves: ${message}\n`);
  process.exit(code);
};

const [specFile, outPng] = process.argv.slice(2);
if (!specFile || !outPng || process.argv.length !== 4) die("usage: node terminal-tools/render-moves.mjs <spec_json> <out_png>", 2);
let spec;
try {
  spec = JSON.parse(fs.readFileSync(specFile, "utf8"));
} catch (err) {
  die(`cannot read the spec ${specFile}: ${err.message}`, 2);
}
const SLOTS = ["context", "a", "b", "c", "note", "stage"];
const props = Array.isArray(spec?.moves) ? spec.moves : [];
if (!props.length) die("the spec names no moves", 2);
for (const p of props) {
  if (!ID.test(p.id ?? "") || !SRC.test(p.src ?? "") || !Number.isInteger(p.frames) || !SLOTS.includes(p.slot)) die(`bad move entry ${JSON.stringify(p)}`, 2);
  if (!fs.existsSync(path.join(GENERATED, `${p.src}.tsx`))) die(`the move file ${p.src}.tsx does not exist; write it first`, 2);
}
if (!fs.existsSync(path.dirname(path.resolve(outPng)))) die(`the output directory of ${outPng} does not exist`, 2);

const { bundle } = await import("@remotion/bundler");
const { renderStill, selectComposition } = await import("@remotion/renderer");

const browserExecutable = process.env.PUPPETEER_EXECUTABLE_PATH || null;
const browser = {
  browserExecutable,
  chromeMode: browserExecutable ? "chrome-for-testing" : "headless-shell",
  chromiumOptions: { gl: "swangle", enableMultiprocessOnLinux: true },
};
const errors = [];
const onBrowserLog = (log) => {
  if (log.type === "error") errors.push(log.text);
};

const tmpRoot = path.join(REMOTION_ROOT, "terminal-tools", ".tmp");
fs.mkdirSync(tmpRoot, { recursive: true });
// A preview killed on its timeout never reaches its `finally`, so its folder
// (an entry and a whole bundle) is left here. Previews run one at a time (the
// MCP server's heavy-check lock), so any folder found now is such a leftover.
for (const stale of fs.readdirSync(tmpRoot)) {
  if (stale.startsWith("preview-")) fs.rmSync(path.join(tmpRoot, stale), { recursive: true, force: true });
}
const work = fs.mkdtempSync(path.join(tmpRoot, "preview-"));
let failure = null;
try {
  const rel = (p) => path.relative(work, p).split(path.sep).join("/");
  const specs = props.map(({ id, frames, slot, text }) => ({ id, frames, slot, text: typeof text === "string" ? text : "" }));
  const entry = [
    'import React from "react";',
    'import { Composition, registerRoot } from "remotion";',
    `import { TerminalMovePreview, previewHeight } from "${rel(path.join(REMOTION_ROOT, "src/scenes/installed/terminalDoc/TerminalMovePreview"))}";`,
    ...props.map((p, i) => `import P${i} from "${rel(path.join(GENERATED, p.src))}";`),
    `const SPECS = ${JSON.stringify(specs)};`,
    `const DRAWS = { ${props.map((p, i) => `${JSON.stringify(p.id)}: P${i}`).join(", ")} };`,
    `const SKIN = ${JSON.stringify(spec.skin === "crt" ? "crt" : "house")};`,
    "const Preview = () => <TerminalMovePreview moves={SPECS} draws={DRAWS} skin={SKIN} />;",
    "const Root = () => <Composition id=\"TerminalMovePreview\" component={Preview} durationInFrames={1} fps={30} width={1080} height={Math.ceil(previewHeight(SPECS) / 2) * 2} />;",
    "registerRoot(Root);",
    "",
  ].join("\n");
  const entryPoint = path.join(work, "entry.tsx");
  fs.writeFileSync(entryPoint, entry);

  const serveUrl = await bundle({
    entryPoint,
    outDir: path.join(work, "bundle"),
    publicDir: path.join(REMOTION_ROOT, "public"),
    symlinkPublicDir: true,
    onProgress: () => {},
  });
  const composition = await selectComposition({ ...browser, serveUrl, id: "TerminalMovePreview", inputProps: {}, logLevel: "error" });
  const tmpPng = path.join(work, "preview.png");
  await renderStill({
    ...browser,
    serveUrl,
    composition,
    inputProps: {},
    output: tmpPng,
    imageFormat: "png",
    timeoutInMilliseconds: PREVIEW_TIMEOUT_MS,
    onBrowserLog,
    logLevel: "error",
  });
  fs.copyFileSync(tmpPng, outPng);
} catch (err) {
  failure = err;
} finally {
  fs.rmSync(work, { recursive: true, force: true });
}

if (failure) {
  fs.rmSync(outPng, { force: true });
  const seen = errors.slice(-5).map((e) => `  browser: ${e}`).join("\n");
  die(`the preview failed: ${String(failure?.message ?? failure).split("\n")[0]}${seen ? `\n${seen}` : ""}`);
}
