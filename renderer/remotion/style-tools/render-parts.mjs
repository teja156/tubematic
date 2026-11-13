#!/usr/bin/env node
//
// The part sheet for the styles whose videos may draw parts of their own:
// Night Signal (customParts, JSON shapes), Flat Vector Science (customProps,
// prop-<name>.tsx files) and Isometric Infographic (customProps, JSON blocks).
// Called by mcp/bean_preview.py::render_preview (script=STYLE_PARTS_SCRIPT)
// for the render_style_parts tool. A copy of storybook-tools/render-props.mjs
// with one sheet composition per style.
//
//   node style-tools/render-parts.mjs <spec_json> <out_png>
//
// <spec_json> is {"style": "<id>", "parts": [...]} for the JSON styles, or
// {"style": "flat_vector_science", "props": [{"id", "src", "box", "light"?}]},
// each src "<video_id>/prop-<name>".
//
// Exit 0 with <out_png> written is success. Anything else exits non-zero with a
// message on stderr and leaves no <out_png>. stdout carries nothing: Remotion
// forwards browser console lines to it.
//
// Its own entry point, written per call into a private folder under
// style-tools/.tmp/, statically importing only the style's sheet and this
// video's prop files: never src/index.ts, which bundles every agent-written
// scene and would fail on any one of them. Software GL only (swangle).

import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const PREVIEW_TIMEOUT_MS = 200_000; // under mcp/bean_preview.py TIMEOUT_SECS
const REMOTION_ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const GENERATED = path.join(REMOTION_ROOT, "src", "scenes", "generated");
const SRC = /^[a-z0-9_-]{1,64}\/prop-[a-z0-9-]{1,40}$/; // video ids are UUIDs (hyphens) or vid_ names
const ID = /^[a-z0-9_]{1,24}$/;
const SHEETS = {
  night_signal: ["src/scenes/installed/nightSignal/NightSignalPartsSheet", "NightSignalPartsSheet"],
  flat_vector_science: ["src/scenes/installed/flatVector/FlatVectorPartsSheet", "FlatVectorPartsSheet"],
  isometric_infographic: ["src/scenes/installed/isometric/IsometricPartsSheet", "IsometricPartsSheet"],
};

const die = (message, code = 1) => {
  process.stderr.write(`render-props: ${message}\n`);
  process.exit(code);
};

const [specFile, outPng] = process.argv.slice(2);
if (!specFile || !outPng || process.argv.length !== 4) die("usage: node style-tools/render-parts.mjs <spec_json> <out_png>", 2);
let spec;
try {
  spec = JSON.parse(fs.readFileSync(specFile, "utf8"));
} catch (err) {
  die(`cannot read the spec ${specFile}: ${err.message}`, 2);
}
const sheet = SHEETS[spec?.style];
if (!sheet) die(`no part sheet for style ${JSON.stringify(spec?.style)}`, 2);
const props = Array.isArray(spec?.props) ? spec.props : [];
const parts = Array.isArray(spec?.parts) ? spec.parts : [];
if (!props.length && !parts.length) die("the spec names no parts", 2);
for (const p of props) {
  if (!ID.test(p.id ?? "") || !SRC.test(p.src ?? "")) die(`bad prop entry ${JSON.stringify(p)}`, 2);
  if (!fs.existsSync(path.join(GENERATED, `${p.src}.tsx`))) die(`the prop file ${p.src}.tsx does not exist; write it first`, 2);
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

const tmpRoot = path.join(REMOTION_ROOT, "style-tools", ".tmp");
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
  const specs = props.map(({ id, src, box, light }) => ({ id, src, box, light }));
  const [sheetPath, sheetName] = sheet;
  const entry = [
    'import React from "react";',
    'import { Composition, registerRoot } from "remotion";',
    `import { ${sheetName} } from "${rel(path.join(REMOTION_ROOT, sheetPath))}";`,
    ...props.map((p, i) => `import P${i} from "${rel(path.join(GENERATED, p.src))}";`),
    `const SPECS = ${JSON.stringify(specs)};`,
    `const PARTS = ${JSON.stringify(parts)};`,
    `const DRAWINGS = { ${props.map((p, i) => `${JSON.stringify(p.id)}: P${i}`).join(", ")} };`,
    `const Preview = () => <${sheetName} specs={SPECS} drawings={DRAWINGS} parts={PARTS} />;`,
    "const Root = () => <Composition id=\"StyleParts\" component={Preview} durationInFrames={1} fps={30} width={1080} height={1920} />;",
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
  const composition = await selectComposition({ ...browser, serveUrl, id: "StyleParts", inputProps: {}, logLevel: "error" });
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
