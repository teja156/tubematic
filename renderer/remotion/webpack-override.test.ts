// The bundler override every whole-project bundle uses (TMDEV-252): Tailwind, the
// scene-API alias, and the rule that a bundle compiles at most one external style.
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { describe, expect, it } from "vitest";
import { webpack } from "@remotion/bundler";
// @ts-expect-error a plain .mjs module shared with the Node scripts
import { SCENE_API_ALIAS, externalContextRegExp, overrideFor } from "./webpack-override.mjs";

describe("externalContextRegExp", () => {
  it("matches only the named style's files", () => {
    const re = externalContextRegExp("ext_night");
    expect(re.test("./ext_night/components/Main.tsx")).toBe(true);
    expect(re.test("./ext_night/runner/kit/a.tsx")).toBe(true);
    expect(re.test("./ext_other/components/Main.tsx")).toBe(false);
    expect(re.test("./ext_nightly/components/Main.tsx")).toBe(false);
  });
  it("matches nothing when no style is named", () => {
    const re = externalContextRegExp("");
    expect(re.test("./ext_night/components/Main.tsx")).toBe(false);
  });
  it("refuses an id outside the external namespace", () => {
    expect(() => externalContextRegExp("../x")).toThrow();
    expect(() => externalContextRegExp("ext_a.*")).toThrow();
  });
});

describe("overrideFor", () => {
  it("adds the scene-API alias and the context rule", () => {
    const cfg = overrideFor("ext_a")({ resolve: { alias: {} }, plugins: [], module: { rules: [] } });
    expect(cfg.resolve.alias[SCENE_API_ALIAS]).toMatch(/src[\\/]sceneApi[\\/]v1\.ts$/);
    expect(cfg.plugins.some((p: object) => p instanceof webpack.ContextReplacementPlugin)).toBe(true);
  });
});

// A real webpack compile of the composition's import shape: one package is broken,
// and a bundle for the other style, or for no external style, still builds.
const compile = (root: string, style: string) =>
  new Promise<webpack.Stats>((resolve, reject) => {
    const base = { mode: "development" as const, context: root, entry: "./entry.js",
      output: { path: path.join(root, "out", style || "none") }, resolve: { alias: {} }, plugins: [], module: { rules: [] } };
    webpack(overrideFor(style)(base), (err: Error | null, stats?: webpack.Stats) => (err || !stats ? reject(err) : resolve(stats)));
  });

describe("one broken package", () => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), "ext-isolation-"));
  fs.writeFileSync(path.join(root, "entry.js"), "export const load = (src) => import(`./scenes/external/${src}.tsx`);\n");
  for (const [id, body] of [["ext_good", "export default 1;\n"], ["ext_broken", "export default (;\n"]]) {
    fs.mkdirSync(path.join(root, "scenes", "external", id, "components"), { recursive: true });
    fs.writeFileSync(path.join(root, "scenes", "external", id, "components", "Main.tsx"), body);
  }
  it("breaks its own bundle", async () => {
    expect((await compile(root, "ext_broken")).hasErrors()).toBe(true);
  });
  it("leaves another style's bundle and a built-in video's bundle building", async () => {
    expect((await compile(root, "ext_good")).hasErrors()).toBe(false);
    expect((await compile(root, "")).hasErrors()).toBe(false);
  });
});
