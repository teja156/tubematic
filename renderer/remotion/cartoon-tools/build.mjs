#!/usr/bin/env node
// Builds the Cartoon 3D command lines (TypeScript under src/cartoon3d/probe2) into cartoon-tools/dist/*.mjs
// for Node, so the MCP server and the authoring scripts can run them without a TypeScript loader. The Remotion
// packages stay external (they load from node_modules beside this directory); everything else is bundled.
//
//   node cartoon-tools/build.mjs            # builds every CLI, ~1 s; safe to run before every use
//
// Deliberately .mjs and outside src/ like audit/run-text-layout-audit.mjs: nothing here is typechecked by the
// `tsc --noEmit` validate_job runs over the project.
import { execFileSync } from "node:child_process";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const SRC = path.join(ROOT, "src/cartoon3d/probe2");
const DIST = path.join(ROOT, "cartoon-tools/dist");
export const CLIS = {
  gate: "gate/gateCli.ts",
  beatgate: "gate/beatGateCli.ts",
  "stage-config": "video/stage-config.ts",
  "qa-config": "video/qa-config.ts",
  catalog: "video/catalog.ts",
  still: "video/stillCli.ts",
};

fs.mkdirSync(DIST, { recursive: true });
const esbuild = path.join(ROOT, "node_modules/.bin/esbuild");
for (const [name, file] of Object.entries(CLIS)) {
  execFileSync(esbuild, [
    path.join(SRC, file), "--bundle", "--platform=node", "--format=esm", `--outfile=${path.join(DIST, `${name}.mjs`)}`,
    "--log-level=error", "--external:@remotion/*",
    "--banner:js=import { createRequire } from \"node:module\"; const require = createRequire(import.meta.url);",
  ], { stdio: "inherit" });
}
console.log(`cartoon-tools/dist: ${Object.keys(CLIS).join(", ")}`);
