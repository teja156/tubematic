#!/usr/bin/env node
//
// Mascot sheet renderer.
//
// Draws one model sheet (turn, feels or act) of a mascot's drawing code on the
// "MascotSheet" composition (src/mascot/MascotSheet.tsx) and writes it as a PNG.
// Called by mcp/mascot_sheets.py::render_sheet, which decides nothing about the
// picture either: a person reviews it.
//
//   node mascot-tools/render-sheet.mjs <code_file> <sheet> <out_png>
//
// Exit 0 with <out_png> written is success. Anything else exits non-zero with a
// message on stderr, and leaves no <out_png>. stdout carries nothing: Remotion
// forwards browser console lines to it.
//
// Software GL only (swangle), like the text audit: sheets are rendered by the
// MCP container, which never gets the GPU, and the GPU stays free for videos.
// The browser is PUPPETEER_EXECUTABLE_PATH when set. A named browser gets
// chromeMode "chrome-for-testing" (new headless): a current Chrome binary no
// longer has the old headless mode, which "headless-shell" asks for.
//
// The code file can be anywhere. It is staged in a public/ directory of this
// call's own, beside a link to the engine (public/mascot/), so nothing is
// written into the shared remotion/public/ and concurrent calls never meet.
// Its own entry point (src/mascot/sheet-index.ts), never src/index.ts: that one
// bundles every agent-written scene, and one broken scene would fail the bundle.
//
// Deliberately .mjs and outside src/, like audit/run-text-layout-audit.mjs:
// nothing here is typechecked, and validate_job's `tsc` never sees it.

import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";

const SHEETS = ["turn", "feels", "act"];   // keep in sync with tubematic_core/mascots.py's SHEETS
const SHEET_TIMEOUT_MS = 1_080_000;         // keep in sync with src/mascot/MascotSheet.tsx's SHEET_TIMEOUT_MS
const STAGED_CODE = "sheet/mascot.js";      // under the staged public/, as the composition's `code` prop
const REMOTION_ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const ENTRY_POINT = path.join(REMOTION_ROOT, "src", "mascot", "sheet-index.ts");

const die = (message, code = 1) => {
  process.stderr.write(`render-sheet: ${message}\n`);
  process.exit(code);
};

// Arguments are checked before Remotion is loaded, so a bad call answers at once.
const [codeFile, sheet, outPng] = process.argv.slice(2);
if (!codeFile || !sheet || !outPng || process.argv.length !== 5) {
  die("usage: node mascot-tools/render-sheet.mjs <code_file> <sheet> <out_png>", 2);
}
if (!SHEETS.includes(sheet)) die(`unknown sheet ${JSON.stringify(sheet)}; expected one of ${SHEETS.join(", ")}`, 2);
let code;
try {
  code = fs.readFileSync(codeFile, "utf8");
} catch (err) {
  die(`cannot read the mascot code ${codeFile}: ${err.message}`, 2);
}
if (!code.trim()) die(`the mascot code ${codeFile} is empty`, 2);
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

const work = fs.mkdtempSync(path.join(os.tmpdir(), "tubematic-mascot-sheet-"));
let failure = null;
try {
  const publicDir = path.join(work, "public");
  fs.mkdirSync(path.join(publicDir, path.dirname(STAGED_CODE)), { recursive: true });
  fs.symlinkSync(path.join(REMOTION_ROOT, "public", "mascot"), path.join(publicDir, "mascot"));
  fs.writeFileSync(path.join(publicDir, STAGED_CODE), code);

  const serveUrl = await bundle({
    entryPoint: ENTRY_POINT,
    outDir: path.join(work, "bundle"),
    publicDir,
    symlinkPublicDir: true,
    onProgress: () => {},
  });
  const inputProps = { code: STAGED_CODE, sheet };
  const composition = await selectComposition({ ...browser, serveUrl, id: "MascotSheet", inputProps, logLevel: "error" });
  // Written beside the bundle first, so a failed render never leaves a picture at outPng.
  const tmpPng = path.join(work, "sheet.png");
  await renderStill({
    ...browser,
    serveUrl,
    composition,
    inputProps,
    output: tmpPng,
    imageFormat: "png",
    timeoutInMilliseconds: SHEET_TIMEOUT_MS,
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
  die(`the ${sheet} sheet failed: ${String(failure?.message ?? failure).split("\n")[0]}${seen ? `\n${seen}` : ""}`);
}
