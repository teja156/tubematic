// The creation skill's template package (agent_files/skills/tubematic-create-style/template)
// must compile under this project's tsconfig, the check validate_job runs on every video.
// A template error is copied into every package the skill builds and fails each one's
// renders after install (found live: an unused `import React` and TS6133).
import * as path from "node:path";
import * as fs from "node:fs";
import ts from "typescript";
import { expect, it } from "vitest";

const ROOT = path.resolve(__dirname, "../..");
const TEMPLATE = path.resolve(ROOT, "../../agent_files/skills/tubematic-create-style/template/ext_template");

function sources(dir: string): string[] {
  return fs.readdirSync(dir, { withFileTypes: true }).flatMap((e) => {
    const p = path.join(dir, e.name);
    if (e.isDirectory()) return sources(p);
    return /\.tsx?$/.test(e.name) ? [p] : [];
  });
}

it("type-checks the skill's template package with the renderer's tsconfig", () => {
  const cfg = ts.readConfigFile(path.join(ROOT, "tsconfig.json"), ts.sys.readFile);
  const { options } = ts.parseJsonConfigFileContent(cfg.config, ts.sys, ROOT);
  const host = ts.createCompilerHost(options);
  // The template lives outside this project; bare imports resolve as they do once it
  // is installed under src/scenes/external.
  const anchor = path.join(ROOT, "src/scenes/external/x.tsx");
  host.resolveModuleNames = (names, containing) =>
    names.map((n) => ts.resolveModuleName(n, n.startsWith(".") ? containing : anchor, options, host).resolvedModule);
  const files = sources(path.join(TEMPLATE, "components"));
  expect(files.length).toBeGreaterThan(0);
  const program = ts.createProgram(files, options, host);
  const errors = ts
    .getPreEmitDiagnostics(program)
    .filter((d) => d.file && d.file.fileName.startsWith(TEMPLATE))
    .map((d) => `${path.relative(TEMPLATE, d.file!.fileName)}: TS${d.code} ${ts.flattenDiagnosticMessageText(d.messageText, " ")}`);
  expect(errors).toEqual([]);
}, 60_000);
