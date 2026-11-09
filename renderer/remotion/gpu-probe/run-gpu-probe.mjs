#!/usr/bin/env node
//
// GPU probe driver (TMDEV-178).
//
// Renders one still of the "GpuProbe" composition (src/gpu-probe/) and writes
// what Chromium's WebGL reported — its unmasked renderer and vendor strings —
// as one JSON document to the file named by the config's outputPath. Called by
// renderer/api/render_agent.py::_run_gpu_probe, which decides whether that string is
// the GPU it expected; this driver decides nothing. Keep it thin.
//
// Why a Node driver and not `npx remotion still`: the CLI never prints a page's
// console output for a still (it renders with onBrowserLog unset), so the
// probe's answer could not get out. onBrowserLog here receives it directly.
//
// The browser and GL options come from the worker verbatim, built by the same
// render_agent.py::_gl_options a render's command-line flags are built from. The
// Node API does NOT read remotion.config.ts, so nothing may be left to it: the
// worker always sends gl, chromeMode and browserExecutable explicitly.
//
// Deliberately .mjs and outside src/, like audit/run-text-layout-audit.mjs:
// nothing here is typechecked or linted, and validate_job's `tsc` never sees it.
//
// Usage:
//   node gpu-probe/run-gpu-probe.mjs '<json-config>'
// where <json-config> is:
//   {
//     "outputPath": "/tmp/xxx.json",
//     "gl": "angle-egl" | "swangle",
//     "chromeMode": "chrome-for-testing" | "headless-shell",
//     "enableMultiprocessOnLinux": true,
//     "browserExecutable": "/usr/bin/chromium" | null
//   }

import { bundle } from "@remotion/bundler";
import { renderStill, selectComposition } from "@remotion/renderer";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";

const PROBE_TAG = "TUBEMATIC_GPU_PROBE"; // keep in sync with src/gpu-probe/GpuProbe.tsx
const REMOTION_ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
// Its own entry point, never src/index.ts: that one bundles every agent-written
// scene, and one broken scene would fail the bundle and read as a broken GPU.
const ENTRY_POINT = path.join(REMOTION_ROOT, "src", "gpu-probe", "index.ts");

const cfg = JSON.parse(process.argv[2] ?? "{}");
const emit = (payload) => fs.writeFileSync(cfg.outputPath, JSON.stringify(payload));

let found = null;
const onBrowserLog = (log) => {
  const idx = log.text.indexOf(`${PROBE_TAG} `);
  if (idx < 0) return;
  try {
    found = JSON.parse(log.text.slice(idx + PROBE_TAG.length + 1));
  } catch {
    // a malformed line is the same as no line
  }
};

const outDir = fs.mkdtempSync(path.join(os.tmpdir(), "tubematic-gpu-probe-"));
try {
  const serveUrl = await bundle({ entryPoint: ENTRY_POINT, outDir: path.join(outDir, "bundle") });
  const options = {
    serveUrl,
    browserExecutable: cfg.browserExecutable ?? null,
    chromeMode: cfg.chromeMode,
    chromiumOptions: { gl: cfg.gl, enableMultiprocessOnLinux: cfg.enableMultiprocessOnLinux ?? true },
    onBrowserLog,
    logLevel: "error",
  };
  const composition = await selectComposition({ ...options, id: "GpuProbe" });
  await renderStill({ ...options, composition, output: path.join(outDir, "probe.png") });
  emit(found ?? { webgl: false, error: "the probe page printed no result" });
} catch (e) {
  emit({ webgl: false, error: `the probe could not render: ${String(e?.message ?? e).slice(0, 500)}` });
} finally {
  fs.rmSync(outDir, { recursive: true, force: true });
}
