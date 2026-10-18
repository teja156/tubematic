/**
 * VideoModal's Delete action and archived state (TMDEV-84).
 *
 *  1. Delete is offered exactly for the deletable statuses — never while a
 *     video is processing, nor at the two scene-claim statuses.
 *  2. It goes through a confirm dialog; only confirming fires onAction("delete").
 *  3. An archived video shows an Archived badge and none of the status actions
 *     (the API would 409 them all), and cannot be deleted again.
 */
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { VideoModal } from "@/components/VideoModal";
import type { Video, VideoStatus } from "@/lib/types";

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

function renderModal(video: Video, onAction = vi.fn(), onClose = vi.fn()) {
  vi.stubGlobal("fetch", vi.fn(async (url: unknown) => ({
    ok: true,
    json: async () => (String(url).endsWith(`/videos/${video.id}`) ? video : []),
  }) as Response));
  render(<VideoModal video={video} onClose={onClose} onAction={onAction} publishingEnabled />);
  return { onAction, onClose };
}

const DELETABLE: VideoStatus[] = [
  "TOPIC_PROPOSED", "TOPIC_APPROVED", "TOPIC_REJECTED", "SCRIPT_READY",
  "VIDEO_READY", "VIDEO_APPROVED", "PUBLISHED", "FAILED",
];
const BLOCKED: VideoStatus[] = [
  "VOICING", "RENDER_QUEUED", "RENDERING", "PUBLISHING", "VOICE_READY", "REVISION_REQUESTED",
];

describe("VideoModal — Delete", () => {
  afterEach(() => { vi.unstubAllGlobals(); vi.restoreAllMocks(); });

  it.each(DELETABLE)("offers Delete Video at %s", async (status) => {
    renderModal(makeVideo(status));
    expect(await screen.findByText("Delete Video")).toBeInTheDocument();
  });

  it.each(BLOCKED)("does not offer Delete Video at %s", async (status) => {
    renderModal(makeVideo(status));
    await screen.findByTestId("video-modal");
    // Let the mount-time refresh settle before asserting an absence.
    await act(async () => {});
    expect(screen.queryByText("Delete Video")).not.toBeInTheDocument();
  });

  it("asks for confirmation and fires delete only once confirmed", async () => {
    const { onAction, onClose } = renderModal(makeVideo("VIDEO_READY"));
    fireEvent.click(await screen.findByText("Delete Video"));
    expect(await screen.findByTestId("delete-dialog")).toBeInTheDocument();
    expect(onAction).not.toHaveBeenCalled();

    fireEvent.click(screen.getByText("Delete"));
    expect(onAction).toHaveBeenCalledWith("vid-1", "delete", expect.objectContaining({ id: "vid-1" }));
    expect(onClose).toHaveBeenCalled();
  });

  it("cancelling the confirmation deletes nothing", async () => {
    const { onAction } = renderModal(makeVideo("VIDEO_READY"));
    fireEvent.click(await screen.findByText("Delete Video"));
    fireEvent.click(await screen.findByText("Cancel"));
    await waitFor(() => expect(screen.queryByTestId("delete-dialog")).not.toBeInTheDocument());
    expect(onAction).not.toHaveBeenCalled();
  });
});

describe("VideoModal — archived", () => {
  afterEach(() => { vi.unstubAllGlobals(); vi.restoreAllMocks(); });

  it("shows the Archived badge", async () => {
    renderModal(makeVideo("PUBLISHED", "2026-09-01T12:00:00Z"));
    expect(await screen.findByTestId("archived-badge")).toHaveTextContent(/Archived/);
  });

  it.each(["TOPIC_PROPOSED", "SCRIPT_READY", "VIDEO_READY", "VIDEO_APPROVED"] as VideoStatus[])(
    "offers no status actions or delete for an archived %s video", async (status) => {
      renderModal(makeVideo(status, "2026-09-01T12:00:00Z"));
      await screen.findByTestId("archived-badge");
      for (const label of ["Approve Topic", "Approve Script", "Approve Video", "Publish…",
                           "Request Revision", "Delete Video"]) {
        expect(screen.queryByText(label)).not.toBeInTheDocument();
      }
    });
});
