import { describe, expect, it } from "vitest";
// @ts-expect-error a plain .mjs module beside the stills server, which node runs untranspiled
import { outPathError } from "./out-path.mjs";

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
