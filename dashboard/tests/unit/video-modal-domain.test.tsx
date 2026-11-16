/**
 * VideoModal's Details list names a curriculum video's domain.
 *
 *  1. A curriculum video in a domain shows the domain's name, looked up in the
 *     projects list (the video record carries only the id).
 *  2. A lookup that fails or misses shows the id, never a blank row.
 *  3. A mining or manual video, or a curriculum video with no domain, shows no
 *     Domain row at all.
 */
import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { VideoModal } from "@/components/VideoModal";
import type { Video } from "@/lib/types";

vi.mock("@/components/TimeZoneProvider", () => ({
  useTimeZone: () => ({ timeZone: "UTC", label: "UTC", degraded: false }),
}));

function makeVideo(extra: Partial<Video> = {}): Video {
  return {
    id: "vid-1", project_id: "proj_a", title: "T", topic: "Topic",
    strategy: "curriculum", producibility_score: 6, status: "TOPIC_PROPOSED", script: null,
    voice_file_path: null, timeline_path: null, scene_config_path: null, video_path: null,
    archived_at: null, video_version: 1, gemini_feedback: null, youtube_url: null, voice_id: "",
    created_at: "2026-01-01T00:00:00Z", updated_at: "2026-01-01T00:00:00Z", comments: [],
    visual_style: "auto",
    ...extra,
  };
}

function renderModal(video: Video, projects: Response | Error) {
  vi.stubGlobal("fetch", vi.fn(async (url: unknown) => {
    const u = String(url);
    if (u.endsWith("/projects")) {
      if (projects instanceof Error) throw projects;
      return projects;
    }
    if (u.includes("/videos/")) return { ok: true, json: async () => ({ ...video, id: u.split("/videos/")[1].split("/")[0] }) } as Response;
    return { ok: true, json: async () => [] } as Response;
  }));
  return render(<VideoModal video={video} onClose={vi.fn()} onAction={vi.fn()} />);
}

const LIST = { ok: true, json: async () => [{ id: "proj_a", name: "Operating Systems" }] } as Response;

afterEach(() => vi.unstubAllGlobals());

describe("VideoModal domain row", () => {
  it("shows the domain name for a curriculum video", async () => {
    renderModal(makeVideo(), LIST);
    expect(await screen.findByText("Operating Systems")).toBeTruthy();
    expect(screen.getByText("Domain")).toBeTruthy();
  });

  it("falls back to the id when the domain is not in the list or the lookup fails", async () => {
    renderModal(makeVideo({ project_id: "proj_gone" }), LIST);
    expect(await screen.findByText("proj_gone")).toBeTruthy();
  });

  it("falls back to the id when the request throws", async () => {
    renderModal(makeVideo(), new Error("down"));
    expect(await screen.findByText("proj_a")).toBeTruthy();
  });

  it("shows no Domain row for mining, or for a curriculum video with no domain", async () => {
    renderModal(makeVideo({ strategy: "mining" }), LIST);
    await screen.findByText("Strategy");
    expect(screen.queryByText("Domain")).toBeNull();
  });

  it("shows no Domain row without a project_id", async () => {
    renderModal(makeVideo({ project_id: null }), LIST);
    await screen.findByText("Strategy");
    await waitFor(() => expect(screen.queryByText("Domain")).toBeNull());
  });

  it("keeps the name when the window moves to another video in the same domain", async () => {
    const { rerender } = renderModal(makeVideo(), LIST);
    await screen.findByText("Operating Systems");
    rerender(<VideoModal video={makeVideo({ id: "vid-2" })} onClose={vi.fn()} onAction={vi.fn()} />);
    expect(await screen.findByText("Operating Systems")).toBeTruthy();
    expect(screen.queryByText("proj_a")).toBeNull();
  });
});
