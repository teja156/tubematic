import * as fs from "node:fs";
import * as os from "node:os";
import * as path from "node:path";
import { describe, expect, it } from "vitest";
import { filesOf, importedPackages, keyMaterial } from "./sourceKey";

const tree = (files: Record<string, string>) => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), "srckey-"));
  for (const [name, text] of Object.entries(files)) {
    fs.mkdirSync(path.dirname(path.join(root, name)), { recursive: true });
    fs.writeFileSync(path.join(root, name), text);
  }
  return root;
};

describe("the beat gate's key", () => {
  it("keeps a built-in video's key exactly as before, so recorded verdicts stay valid", () => {
    const src = tree({ "Short.tsx": 'import { x } from "../../../cartoon3d/kit";' });
    const extra = { beats: [1], sentences: ["a"] };
    expect(keyMaterial(src, "/nowhere", extra)).toBe(JSON.stringify({ source: filesOf(src), ...extra }));
  });

  it("finds the external packages a world video imports", () => {
    expect(importedPackages([["a.tsx", 'import R from "../../external/ext_low_poly/runner/Run";\n'
      + 'import { k } from "../../../external/ext_other/runner/kit/k";\nimport "../external/not_ext/x";']]))
      .toEqual(["ext_low_poly", "ext_other"]);
  });

  it("changes when the package the video imports changes, and not for another package", () => {
    const ext = tree({ "ext_lp/runner/Run.tsx": "v1", "ext_unused/runner/Run.tsx": "u1" });
    const src = tree({ "Short.tsx": 'import R from "../../external/ext_lp/runner/Run";' });
    const before = keyMaterial(src, ext, {});
    fs.writeFileSync(path.join(ext, "ext_unused/runner/Run.tsx"), "u2");
    expect(keyMaterial(src, ext, {})).toBe(before);
    fs.writeFileSync(path.join(ext, "ext_lp/runner/Run.tsx"), "v2");
    expect(keyMaterial(src, ext, {})).not.toBe(before);
  });
});

describe("the beat gate's key over binary package files", () => {
  it("changes when a binary asset of the package changes", () => {
    const ext = tree({ "ext_lp/runner/Run.tsx": "v1" });
    fs.writeFileSync(path.join(ext, "ext_lp/runner/model.glb"), Buffer.from([0xff]));
    const src = tree({ "Short.tsx": 'import R from "../../external/ext_lp/runner/Run";' });
    const before = keyMaterial(src, ext, {});
    fs.writeFileSync(path.join(ext, "ext_lp/runner/model.glb"), Buffer.from([0xfe]));
    expect(keyMaterial(src, ext, {})).not.toBe(before);
  });
});
