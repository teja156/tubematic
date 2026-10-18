/**
 * VideoModal's "Retry publishing" action (TMDEV-97).
 *
 *  1. Offered only for a video that failed while publishing — FAILED with
 *     publication rows. A render failure has none, so it gets Delete only.
 *  2. Never offered on an archived video, nor with publishing turned off.
 *  3. The server decides what a retry means: "reconciling" (a live post was
 *     found and adopted) refreshes in place; "republish" (nothing is live)
 *     opens the normal Publish dialog, since the account and privacy choices
 *     are not stored anywhere.
 */
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { VideoModal } from "@/components/VideoModal";
import { canRetryPublish } from "@/lib/videoStatus";
import type { Video, VideoPublication, VideoStatus } from "@/lib/types";

vi.mock("@/components/TimeZoneProvider", () => ({
  useTimeZone: () => ({ timeZone: "UTC", label: "UTC", degraded: false }),
}));

function makeVideo(status: VideoStatus, archived_at: string | null = null): Video {
  return {
    id: "vid-1", project_id: null, title: null, topic: "Test topic", strategy: "curriculum",
    producibility_score: 5, status, script: null, voice_file_path: null, timeline_path: null,
    scene_config_path: null, video_path: null, archived_at, video_version: 1,
    gemini_feedback: null, youtube_url: null, voice_id: "", created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-01T00:00:00Z", comments: [],
  };
}

const FAILED_PUB: VideoPublication = {
  id: "pub-1", video_id: "vid-1", platform: "youtube", social_account_id: "spc_yt",
  status: "FAILED", post_url: "", error: "rejected", published_at: "",
  created_at: "2026-01-01T00:00:00Z", updated_at: "2026-01-01T00:00:00Z",
};

function renderModal(
  video: Video,
  { pubs = [FAILED_PUB], retry = { ok: true, body: { outcome: "reconciling" } as object },
    publishingEnabled = true } = {},
) {
  const fetchMock = vi.fn(async (url: unknown, init?: RequestInit) => {
    const u = String(url);
    if (u.endsWith("/publish/retry") && init?.method === "POST") {
      return { ok: retry.ok, json: async () => retry.body } as Response;
    }
    if (u.endsWith("/publications")) return { ok: true, json: async () => pubs } as Response;
    if (u.endsWith(`/videos/${video.id}`)) return { ok: true, json: async () => video } as Response;
    return { ok: true, json: async () => [] } as Response;
  });
  vi.stubGlobal("fetch", fetchMock);
  render(
    <VideoModal video={video} onClose={vi.fn()} onAction={vi.fn()}
                publishingEnabled={publishingEnabled} />,
  );
  return fetchMock;
}

async function settle() {
  await screen.findByTestId("video-modal");
  await act(async () => {});
}

describe("canRetryPublish", () => {
  it("needs FAILED, publication rows and no archive", () => {
    expect(canRetryPublish({ status: "FAILED", archived_at: null }, 1)).toBe(true);
    expect(canRetryPublish({ status: "FAILED", archived_at: null }, 0)).toBe(false);
    expect(canRetryPublish({ status: "FAILED", archived_at: "2026-09-01" }, 1)).toBe(false);
    expect(canRetryPublish({ status: "PUBLISHED", archived_at: null }, 1)).toBe(false);
  });
});

describe("VideoModal — Retry publishing", () => {
  afterEach(() => { vi.unstubAllGlobals(); vi.restoreAllMocks(); });

  it("is offered for a video that failed while publishing", async () => {
    renderModal(makeVideo("FAILED"));
    expect(await screen.findByText("Retry publishing")).toBeInTheDocument();
    expect(screen.getByText("Delete Video")).toBeInTheDocument();
  });

  it("is not offered for a FAILED video with no publication rows", async () => {
    renderModal(makeVideo("FAILED"), { pubs: [] });
    await settle();
    expect(screen.queryByText("Retry publishing")).not.toBeInTheDocument();
    expect(screen.getByText("Delete Video")).toBeInTheDocument();
  });

  it("is not offered for an archived video", async () => {
    renderModal(makeVideo("FAILED", "2026-09-01T12:00:00Z"));
    await settle();
    expect(screen.queryByText("Retry publishing")).not.toBeInTheDocument();
  });

  it("is not offered while publishing is turned off", async () => {
    renderModal(makeVideo("FAILED"), { publishingEnabled: false });
    await settle();
    expect(screen.queryByText("Retry publishing")).not.toBeInTheDocument();
  });

  it("refreshes in place when the server adopted a live post", async () => {
    const fetchMock = renderModal(makeVideo("FAILED"));
    fireEvent.click(await screen.findByText("Retry publishing"));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith(
      "/api/proxy/videos/vid-1/publish/retry", expect.objectContaining({ method: "POST" })));
    await act(async () => {});
    expect(screen.queryByTestId("publish-dialog")).not.toBeInTheDocument();
    const refetches = fetchMock.mock.calls.filter(([u]) => String(u).endsWith("/publications"));
    expect(refetches.length).toBeGreaterThanOrEqual(2);
  });

  it("opens the Publish dialog when nothing was live", async () => {
    renderModal(makeVideo("FAILED"), { retry: { ok: true, body: { outcome: "republish" } } });
    fireEvent.click(await screen.findByText("Retry publishing"));
    expect(await screen.findByTestId("publish-dialog")).toBeInTheDocument();
  });

  it("shows the server's reason when the retry is refused", async () => {
    renderModal(makeVideo("FAILED"),
                { retry: { ok: false, body: { error: "Video is no longer FAILED." } } });
    fireEvent.click(await screen.findByText("Retry publishing"));
    expect(await screen.findByTestId("retry-publish-error"))
      .toHaveTextContent("Video is no longer FAILED.");
    expect(screen.queryByTestId("publish-dialog")).not.toBeInTheDocument();
  });
});
