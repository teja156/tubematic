/**
 * canDelete decides whether the Delete button is shown (TMDEV-84). The API's
 * DELETABLE_STATUSES is the real gate; this pins that the two agree, including
 * the non-obvious half — VOICE_READY and REVISION_REQUESTED are blocked because
 * an agent can hold a scene-work claim there, not because they are processing.
 * SCHEDULED is blocked because postforme is holding a post that will go out.
 */
import { afterEach, describe, expect, it, vi } from "vitest";
import { DELETABLE_STATUSES, canDelete, deleteVideo, patchVideo } from "@/lib/videoStatus";
import type { VideoStatus } from "@/lib/types";

const ALL: VideoStatus[] = [
  "TOPIC_PROPOSED", "TOPIC_APPROVED", "TOPIC_REJECTED", "SCRIPT_READY",
  "VOICING", "VOICE_READY", "RENDER_QUEUED", "RENDERING", "VIDEO_READY",
  "VIDEO_APPROVED", "REVISION_REQUESTED", "SCHEDULED", "PUBLISHING", "PUBLISHED", "FAILED",
];
const BLOCKED: VideoStatus[] = [
  "VOICING", "RENDER_QUEUED", "RENDERING", "SCHEDULED", "PUBLISHING", "VOICE_READY",
  "REVISION_REQUESTED",
];

describe("canDelete", () => {
  it.each(ALL.filter((s) => !BLOCKED.includes(s)))("allows %s", (status) => {
    expect(canDelete({ status, archived_at: null })).toBe(true);
  });

  it.each(BLOCKED)("refuses %s", (status) => {
    expect(canDelete({ status, archived_at: null })).toBe(false);
  });

  it("refuses an already-archived video at any status", () => {
    for (const status of ALL) {
      expect(canDelete({ status, archived_at: "2026-09-01T00:00:00Z" })).toBe(false);
    }
  });

  it("matches the API's set exactly", () => {
    expect([...DELETABLE_STATUSES].sort()).toEqual(ALL.filter((s) => !BLOCKED.includes(s)).sort());
  });
});

describe("deleteVideo", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("sends DELETE through the proxy", async () => {
    const fetchMock = vi.fn(async () => ({ ok: true, json: async () => ({ ok: true }) }) as Response);
    vi.stubGlobal("fetch", fetchMock);
    await deleteVideo("vid-1");
    expect(fetchMock).toHaveBeenCalledWith("/api/proxy/videos/vid-1", { method: "DELETE" });
  });

  it("throws the API's reason on a conflict", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => ({
      ok: false, json: async () => ({ error: "A video cannot be deleted while it is RENDERING." }),
    }) as Response));
    await expect(deleteVideo("vid-1")).rejects.toThrow("while it is RENDERING");
  });
});

describe("patchVideo", () => {
  afterEach(() => vi.unstubAllGlobals());

  const respond = (status: number, body: unknown) =>
    vi.stubGlobal("fetch", vi.fn(async () => ({
      ok: status < 400, status, json: async () => body,
    }) as Response));

  it("sends the body as a JSON PATCH through the proxy", async () => {
    const fetchMock = vi.fn(async () => ({ ok: true, status: 200, json: async () => ({}) }) as Response);
    vi.stubGlobal("fetch", fetchMock);
    await patchVideo("vid-1", { status: "VIDEO_APPROVED" });
    expect(fetchMock).toHaveBeenCalledWith("/api/proxy/videos/vid-1", {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ status: "VIDEO_APPROVED" }),
    });
  });

  it("names a lost status race as a conflict", async () => {
    respond(409, { error: "Status precondition failed", current: "VOICING", expected: "SCRIPT_READY" });
    await expect(patchVideo("vid-1", {})).rejects.toThrow("Status conflict — action already taken");
  });

  it("passes any other refusal through in the API's own words", async () => {
    respond(400, { error: "agent_id 'codex' is uninstalled, so no work can be handed to it." });
    await expect(patchVideo("vid-1", {})).rejects.toThrow("agent_id 'codex' is uninstalled");
  });

  it("falls back to a generic message when the body says nothing", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => ({
      ok: false, status: 502, json: async () => { throw new Error("not json"); },
    }) as unknown as Response));
    await expect(patchVideo("vid-1", {})).rejects.toThrow("Failed to update video");
  });
});
