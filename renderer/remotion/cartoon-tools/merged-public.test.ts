import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { afterAll, describe, expect, it } from "vitest";
// @ts-expect-error a plain .mjs module beside the stills server, which node runs untranspiled
import { syncMergedPublic } from "./merged-public.mjs";

describe("syncMergedPublic", () => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), "merged-public-"));
  const jobs = path.join(root, "jobs");
  const project = path.join(root, "public");
  const merged = path.join(root, "merged");
  fs.mkdirSync(path.join(jobs, "vid_a"), { recursive: true });
  fs.mkdirSync(path.join(project, "fonts"), { recursive: true });
  fs.writeFileSync(path.join(project, "watermark.png"), "png");
  fs.writeFileSync(path.join(project, "fonts", "x.woff2"), "font");
  fs.writeFileSync(path.join(jobs, "vid_a", "scene-config.json"), "{}");
  afterAll(() => fs.rmSync(root, { recursive: true, force: true }));

  it("serves a video's files and the project's fonts and watermark from one directory", () => {
    syncMergedPublic(merged, jobs, project);
    expect(fs.readFileSync(path.join(merged, "vid_a", "scene-config.json"), "utf8")).toBe("{}");
    expect(fs.readFileSync(path.join(merged, "fonts", "x.woff2"), "utf8")).toBe("font");
    expect(fs.readFileSync(path.join(merged, "watermark.png"), "utf8")).toBe("png");
    // a plain file is a copy, a folder a link
    expect(fs.lstatSync(path.join(merged, "watermark.png")).isSymbolicLink()).toBe(false);
    expect(fs.lstatSync(path.join(merged, "fonts")).isSymbolicLink()).toBe(true);
  });

  it("picks up a video filed later and drops one that is gone", () => {
    fs.mkdirSync(path.join(jobs, "vid_b"));
    fs.rmSync(path.join(jobs, "vid_a"), { recursive: true });
    syncMergedPublic(merged, jobs, project);
    expect(fs.existsSync(path.join(merged, "vid_b"))).toBe(true);
    expect(fs.lstatSync(path.join(merged, "vid_a"), { throwIfNoEntry: false })).toBeUndefined();
  });

  it("lets the jobs volume win a name clash, and writes nothing into either source", () => {
    fs.mkdirSync(path.join(jobs, "fonts"));
    syncMergedPublic(merged, jobs, project);
    expect(fs.readlinkSync(path.join(merged, "fonts"))).toBe(path.join(jobs, "fonts"));
    expect(fs.readdirSync(project).sort()).toEqual(["fonts", "watermark.png"]);
  });
});
