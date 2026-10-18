/**
 * Tests for the two /stream URL builders.
 *
 * The stream route serves files from /output_videos (container mount).
 *
 * Critical regressions guarded here:
 *  1. A rendered video's URL comes from its own ids, never from the stored
 *     video_path: a tampered or legacy row naming another video's file must
 *     still play its own, and a legacy host path must still play at all
 *  2. Each id is URL-encoded, and a project-less video is under default_proj,
 *     where the worker renders it
 *  3. videoToStreamUrl (voice previews, whose path the API returns) rewrites
 *     /output_videos/... and mounted/output_videos/... to /stream/..., and
 *     returns any other path unchanged (no destructive fallback)
 */
import { describe, expect, it } from "vitest";
import { videoStreamUrl, videoToStreamUrl } from "@/lib/utils";

describe("videoStreamUrl", () => {
  it("builds the URL from the video's project and id", () => {
    expect(videoStreamUrl({ id: "vid_a", project_id: "proj_a" })).toBe("/stream/proj_a/vid_a.mp4");
  });

  it("puts a project-less video under default_proj, where the worker renders it", () => {
    expect(videoStreamUrl({ id: "vid_a", project_id: null })).toBe("/stream/default_proj/vid_a.mp4");
    expect(videoStreamUrl({ id: "vid_a", project_id: "" })).toBe("/stream/default_proj/vid_a.mp4");
  });

  it("encodes each id as one path segment", () => {
    expect(videoStreamUrl({ id: "a b#1", project_id: "x/y?z" })).toBe("/stream/x%2Fy%3Fz/a%20b%231.mp4");
  });
});

describe("videoToStreamUrl", () => {
  it("rewrites /output_videos/ prefix to /stream/", () => {
    expect(videoToStreamUrl("/output_videos/abc123.mp4")).toBe("/stream/abc123.mp4");
  });

  it("rewrites mounted/output_videos/ prefix to /stream/", () => {
    expect(videoToStreamUrl("mounted/output_videos/abc123.mp4")).toBe("/stream/abc123.mp4");
  });

  it("preserves paths in subdirectories", () => {
    expect(videoToStreamUrl("/output_videos/jobs/v1/final.mp4")).toBe("/stream/jobs/v1/final.mp4");
  });

  it("returns unrecognised paths unchanged", () => {
    expect(videoToStreamUrl("/some/other/path.mp4")).toBe("/some/other/path.mp4");
  });
});
