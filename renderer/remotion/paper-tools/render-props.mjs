#!/usr/bin/env node
//
// Paper Diorama custom-prop preview (TMDEV-228).
//
// Paints the props an agent wrote for one video (its scene-config's
// customProps: paper pieces as data, never code) on the "PaperPropSheet"
// composition (src/scenes/installed/paperDiorama/PaperPropSheet.tsx) and writes
// it as a PNG. Called by mcp/bean_preview.py::render_preview
// (script=PAPER_SCRIPT) for the render_paper_props tool.
//
//   node paper-tools/render-props.mjs <spec_json> <out_png>
//
// <spec_json> is {"props": {"<name>": {"w", "h", "pieces": [...]}}}, already
// checked by mcp/paper_diorama.py::prop_errors.
//
// Exit 0 with <out_png> written is success. Anything else exits non-zero with a
// message on stderr and leaves no <out_png>. stdout carries nothing: Remotion
// forwards browser console lines to it.
//
// Its own entry point, written per call into a private folder under
// paper-tools/.tmp/, importing only the sheet: never src/index.ts, which
// bundles every agent-written scene and would fail on any one of them.
// Software GL only (swangle). Deliberately .mjs and outside src/, like
// storybook-tools/render-props.mjs: validate_job's `tsc` never sees it.

import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const PREVIEW_TIMEOUT_MS = 200_000; // under mcp/bean_preview.py TIMEOUT_SECS
const REMOTION_ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");

const die = (message, code = 1) => {
  process.stderr.write(`render-props: ${message}\n`);
  process.exit(code);
};

const [specFile, outPng] = process.argv.slice(2);
if (!specFile || !outPng || process.argv.length !== 4) die("usage: node paper-tools/render-props.mjs <spec_json> <out_png>", 2);
let spec;
try {
  spec = JSON.parse(fs.readFileSync(specFile, "utf8"));
} catch (err) {
  die(`cannot read the spec ${specFile}: ${err.message}`, 2);
}
const props = spec?.props && typeof spec.props === "object" ? spec.props : null;
if (!props || !Object.keys(props).length) die("the spec names no props", 2);
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

const tmpRoot = path.join(REMOTION_ROOT, "paper-tools", ".tmp");
fs.mkdirSync(tmpRoot, { recursive: true });
// A preview killed on its timeout never reaches its `finally`; previews run one
// at a time (the MCP server's heavy-check lock), so any folder found now is such a leftover.
for (const stale of fs.readdirSync(tmpRoot)) {
  if (stale.startsWith("preview-")) fs.rmSync(path.join(tmpRoot, stale), { recursive: true, force: true });
}
const work = fs.mkdtempSync(path.join(tmpRoot, "preview-"));
let failure = null;
try {
  const rel = (p) => path.relative(work, p).split(path.sep).join("/");
  const entry = [
    'import React from "react";',
    'import { Composition, registerRoot } from "remotion";',
    `import { PaperPropSheet } from "${rel(path.join(REMOTION_ROOT, "src/scenes/installed/paperDiorama/PaperPropSheet"))}";`,
    "const Root = () => <Composition id=\"PaperPropSheet\" component={PaperPropSheet} durationInFrames={1} fps={30} width={1080} height={1920} />;",
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
  const inputProps = { props };
  const composition = await selectComposition({ ...browser, serveUrl, id: "PaperPropSheet", inputProps, logLevel: "error" });
  const tmpPng = path.join(work, "preview.png");
  await renderStill({
    ...browser, serveUrl, composition, inputProps, output: tmpPng, imageFormat: "png",
    timeoutInMilliseconds: PREVIEW_TIMEOUT_MS, onBrowserLog, logLevel: "error",
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
