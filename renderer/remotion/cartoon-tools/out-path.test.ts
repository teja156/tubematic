import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { afterAll, describe, expect, it } from "vitest";
// @ts-expect-error a plain .mjs module beside the stills server, which node runs untranspiled
import { outPathError, planRequest } from "./out-path.mjs";

const PUBLIC = "/jobs";

describe("outPathError", () => {
  it("allows the paths the Cartoon 3D tools write", () => {
    expect(outPathError(PUBLIC, "/jobs/vid_56f81a994069/cartoon/stills/f0060.png")).toBeNull();
    expect(outPathError(PUBLIC, "/jobs/vid_56f81a994069/cartoon/beatgate/beat00-f0045.png")).toBeNull();
    expect(outPathError(PUBLIC, "/jobs/vid_a/cartoon/stills", { dir: true })).toBeNull();
    expect(outPathError("/jobs/", "/jobs/vid_a/cartoon/x.png")).toBeNull();
  });

  it("refuses anything outside <public>/<video>/cartoon/", () => {
    for (const p of [
      "/jobs/vid_a/scene-config.json",
      "/jobs/vid_a/audio.png",
      "/jobs/vid_a/cartoon.png",
      "/jobs/cartoon/x.png",
      "/jobs/x.png",
      "/etc/passwd.png",
      "/tmp/out.png",
      "/jobs/vid_a/cartoon/../timeline.png",
      "/jobs/../jobs2/vid_a/cartoon/x.png",
      "relative/vid_a/cartoon/x.png",
    ]) expect(outPathError(PUBLIC, p), p).toMatch(/is not under/);
  });

  it("refuses a file that is not a PNG, and a missing path", () => {
    expect(outPathError(PUBLIC, "/jobs/vid_a/cartoon/beatgate/beat-verdict.json")).toMatch(/not a \.png/);
    expect(outPathError(PUBLIC, undefined)).toMatch(/no output path/);
    expect(outPathError(PUBLIC, "", { dir: true })).toMatch(/no output path/);
  });

  it("refuses an output directory outside a video's cartoon folder", () => {
    expect(outPathError(PUBLIC, "/jobs/vid_a", { dir: true })).toMatch(/is not under/);
    expect(outPathError(PUBLIC, "/jobs", { dir: true })).toMatch(/is not under/);
  });
});

describe("outPathError with symlinks", () => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), "out-path-"));
  const pub = path.join(root, "jobs");
  const outside = path.join(root, "elsewhere");
  fs.mkdirSync(path.join(pub, "vid_a", "cartoon", "beatgate"), { recursive: true });
  fs.mkdirSync(outside);
  fs.symlinkSync(outside, path.join(pub, "vid_a", "cartoon", "stills"));
  fs.symlinkSync(outside, path.join(pub, "vid_b"));
  // a dangling link: its target does not exist yet, so a realpath check would read it as "not created"
  fs.symlinkSync(path.join(outside, "new.png"), path.join(pub, "vid_a", "cartoon", "beatgate", "beat00-f0001.png"));
  fs.symlinkSync(path.join(pub, "vid_a", "cartoon", "beatgate"), path.join(pub, "vid_a", "cartoon", "inside"));
  afterAll(() => fs.rmSync(root, { recursive: true, force: true }));

  it("refuses any path through a symlink, dangling or not, even one pointing back inside", () => {
    expect(outPathError(pub, path.join(pub, "vid_a", "cartoon", "stills", "f0001.png"))).toMatch(/goes through the symlink/);
    expect(outPathError(pub, path.join(pub, "vid_b", "cartoon", "f0001.png"))).toMatch(/goes through the symlink/);
    expect(outPathError(pub, path.join(pub, "vid_a", "cartoon", "beatgate", "beat00-f0001.png"))).toMatch(/goes through the symlink/);
    expect(outPathError(pub, path.join(pub, "vid_a", "cartoon", "inside", "x.png"))).toMatch(/goes through the symlink/);
    expect(fs.existsSync(path.join(outside, "new.png"))).toBe(false);
  });

  it("allows a real folder, including parts not yet created", () => {
    expect(outPathError(pub, path.join(pub, "vid_a", "cartoon", "beatgate", "beat01-f0002.png"))).toBeNull();
    expect(outPathError(pub, path.join(pub, "vid_new", "cartoon", "stills", "f0001.png"))).toBeNull();
  });
});

describe("planRequest", () => {
  it("plans one /still and the frames of a /stills, writing exactly what it checked", () => {
    expect(planRequest(PUBLIC, "/still", { out: "/jobs/v/cartoon/stills/f0005.png", frame: 5 }))
      .toEqual({ targets: [{ frame: 5, out: "/jobs/v/cartoon/stills/f0005.png" }] });
    expect(planRequest(PUBLIC, "/stills", { outDir: "/jobs/v/cartoon/beatgate", frames: [3, 40], prefix: "b" }))
      .toEqual({ targets: [{ frame: 3, out: "/jobs/v/cartoon/beatgate/b0003.png" }, { frame: 40, out: "/jobs/v/cartoon/beatgate/b0040.png" }] });
  });

  it("refuses frames that are not a list of non-negative integers", () => {
    // a string iterates character by character: its prefix escape would otherwise go unchecked
    const escape = { outDir: "/jobs/v/cartoon", prefix: "../../../app/remotion/public/watermark" };
    for (const frames of ["1", [], [1.5], [-1], ["1"], undefined, { 0: 1 }]) {
      expect(planRequest(PUBLIC, "/stills", { ...escape, frames }).error, JSON.stringify(frames)).toMatch(/frames must be/);
    }
    expect(planRequest(PUBLIC, "/still", { out: "/jobs/v/cartoon/x.png", frame: "1" }).error).toMatch(/frame must be/);
  });

  it("refuses a prefix that leaves the cartoon folder, and a prefix that is not a string", () => {
    expect(planRequest(PUBLIC, "/stills", { outDir: "/jobs/v/cartoon", frames: [1], prefix: "../../../app/x" }).error).toMatch(/is not under/);
    expect(planRequest(PUBLIC, "/stills", { outDir: "/jobs/v/cartoon", frames: [1], prefix: 7 }).error).toMatch(/prefix must be/);
    expect(planRequest(PUBLIC, "/still", { out: "/jobs/v/timeline.png" }).error).toMatch(/is not under/);
  });
});
