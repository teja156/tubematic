/**
 * VideoModal's style pick from Auto, and the switch to its runner-up (TMDEV-203).
 *
 *  1. A style Auto picked shows its reason and runner-up beside the style.
 *  2. At Script Ready, with a runner-up, a Switch button posts to
 *     /switch-style after a confirm and refetches the video. Nowhere else:
 *     after Script Ready the voice is paid for, and before it there is no
 *     script to throw away.
 *  3. A refusal shows the server's reason.
 */
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { VideoModal } from "@/components/VideoModal";
import type { Video, VideoStatus } from "@/lib/types";

vi.mock("@/components/TimeZoneProvider", () => ({
  useTimeZone: () => ({ timeZone: "UTC", label: "UTC", degraded: false }),
}));

function makeVideo(status: VideoStatus, extra: Partial<Video> = {}): Video {
  return {
    id: "vid-1", project_id: null, title: null, topic: "Test topic", strategy: "curriculum",
    producibility_score: 5, status, script: null, voice_file_path: null, timeline_path: null,
    scene_config_path: null, video_path: null, archived_at: null, video_version: 1,
    gemini_feedback: null, youtube_url: null, voice_id: "", created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-01T00:00:00Z", comments: [],
    visual_style: "system_flow", style_pick: "system_flow", style_runner_up: "stick",
    style_reason: "A packet's path through a network.",
    ...extra,
  };
}

function renderModal(video: Video, sw = { ok: true, body: {} as object }) {
  const fetchMock = vi.fn(async (url: unknown, init?: RequestInit) => {
    const u = String(url);
    if (u.endsWith("/switch-style") && init?.method === "POST") {
      return { ok: sw.ok, json: async () => sw.body } as Response;
    }
    if (u.endsWith(`/videos/${video.id}`)) return { ok: true, json: async () => video } as Response;
    return { ok: true, json: async () => [] } as Response;
  });
  vi.stubGlobal("fetch", fetchMock);
  render(<VideoModal video={video} onClose={vi.fn()} onAction={vi.fn()} />);
  return fetchMock;
}

async function settle() {
  await screen.findByTestId("video-modal");
  await act(async () => {});
}

describe("VideoModal — Auto's style pick", () => {
  afterEach(() => { vi.unstubAllGlobals(); vi.restoreAllMocks(); });

  it("shows the reason and the runner-up", async () => {
    renderModal(makeVideo("SCRIPT_READY"));
    const reason = await screen.findByTestId("style-pick-reason");
    expect(reason).toHaveTextContent("A packet's path through a network.");
    expect(reason).toHaveTextContent("Runner-up:");
  });

  it("offers the switch at Script Ready and posts it after a confirm", async () => {
    vi.spyOn(window, "confirm").mockReturnValue(true);
    const fetchMock = renderModal(makeVideo("SCRIPT_READY"));
    const box = await screen.findByTestId("switch-style");
    fireEvent.click(box.querySelector("button")!);
    await waitFor(() => expect(fetchMock.mock.calls.some(
      ([u, i]) => String(u).endsWith("/videos/vid-1/switch-style") && (i as RequestInit)?.method === "POST",
    )).toBe(true));
  });

  it("does nothing when the confirm is declined", async () => {
    vi.spyOn(window, "confirm").mockReturnValue(false);
    const fetchMock = renderModal(makeVideo("SCRIPT_READY"));
    fireEvent.click((await screen.findByTestId("switch-style")).querySelector("button")!);
    await act(async () => {});
    expect(fetchMock.mock.calls.some(([u]) => String(u).endsWith("/switch-style"))).toBe(false);
  });

  it("shows the server's refusal", async () => {
    vi.spyOn(window, "confirm").mockReturnValue(true);
    renderModal(makeVideo("SCRIPT_READY"), { ok: false, body: { error: "Stick Explainer is not available" } });
    fireEvent.click((await screen.findByTestId("switch-style")).querySelector("button")!);
    expect(await screen.findByTestId("switch-style-error")).toHaveTextContent("not available");
  });

  it.each<VideoStatus>(["TOPIC_APPROVED", "VOICING", "VOICE_READY", "VIDEO_READY"])(
    "is not offered at %s", async (status) => {
      renderModal(makeVideo(status));
      await settle();
      expect(screen.queryByTestId("switch-style")).not.toBeInTheDocument();
    });

  it("is not offered without a runner-up, or for a style a person chose", async () => {
    renderModal(makeVideo("SCRIPT_READY", { style_runner_up: "" }));
    await settle();
    expect(screen.queryByTestId("switch-style")).not.toBeInTheDocument();
  });

  it("shows no pick for a style a person chose", async () => {
    renderModal(makeVideo("SCRIPT_READY", { style_pick: "", style_runner_up: "", style_reason: "" }));
    await settle();
    expect(screen.queryByTestId("style-pick-reason")).not.toBeInTheDocument();
    expect(screen.queryByTestId("switch-style")).not.toBeInTheDocument();
  });
});
