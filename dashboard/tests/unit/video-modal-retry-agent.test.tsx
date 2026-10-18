/**
 * VideoModal's "Retry agent" action and the Kanban card's STUCK badge (TMDEV-129).
 *
 *  1. Offered only for a video the scheduled agent gave up on (agent_stuck_at
 *     set), and never on an archived one. The stuck statuses are all agent
 *     statuses, where the modal otherwise shows no Actions block at all.
 *  2. Retrying posts to /agent-retry and refetches the video; the status is
 *     left alone, which is the point — the human is not asked to pick one.
 *  3. A refusal shows the server's reason.
 */
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { VideoModal } from "@/components/VideoModal";
import { KanbanCard } from "@/components/KanbanCard";
import { isAgentStuck } from "@/lib/videoStatus";
import type { Video, VideoStatus } from "@/lib/types";

vi.mock("@/components/TimeZoneProvider", () => ({
  useTimeZone: () => ({ timeZone: "UTC", label: "UTC", degraded: false }),
}));

function makeVideo(status: VideoStatus, agent_stuck_at: string | null,
                   archived_at: string | null = null): Video {
  return {
    id: "vid-1", project_id: null, title: null, topic: "Test topic", strategy: "curriculum",
    producibility_score: 5, status, script: null, voice_file_path: null, timeline_path: null,
    scene_config_path: null, video_path: null, archived_at, video_version: 1,
    gemini_feedback: null, youtube_url: null, voice_id: "", created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-01T00:00:00Z", comments: [],
    agent_no_progress_count: agent_stuck_at ? 3 : 0, agent_stuck_at,
  };
}

function renderModal(video: Video, retry = { ok: true, body: {} as object }) {
  const fetchMock = vi.fn(async (url: unknown, init?: RequestInit) => {
    const u = String(url);
    if (u.endsWith("/agent-retry") && init?.method === "POST") {
      return { ok: retry.ok, json: async () => retry.body } as Response;
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

describe("isAgentStuck", () => {
  it("needs the flag and no archive", () => {
    expect(isAgentStuck({ agent_stuck_at: "2026-09-26T00:00:00Z", archived_at: null })).toBe(true);
    expect(isAgentStuck({ agent_stuck_at: null, archived_at: null })).toBe(false);
    expect(isAgentStuck({ agent_stuck_at: undefined, archived_at: null })).toBe(false);
    expect(isAgentStuck({ agent_stuck_at: "2026-09-26T00:00:00Z",
                          archived_at: "2026-09-27T00:00:00Z" })).toBe(false);
  });
});

describe("VideoModal — Retry agent", () => {
  afterEach(() => { vi.unstubAllGlobals(); vi.restoreAllMocks(); });

  it("is offered, with the reason, for a stuck video at an agent status", async () => {
    renderModal(makeVideo("VOICE_READY", "2026-09-26T00:00:00Z"));
    expect(await screen.findByText("Retry agent")).toBeInTheDocument();
    expect(screen.getByTestId("agent-stuck-banner")).toHaveTextContent("3 sessions in a row");
  });

  it("is not offered for a video that is not stuck", async () => {
    renderModal(makeVideo("VOICE_READY", null));
    await settle();
    expect(screen.queryByText("Retry agent")).not.toBeInTheDocument();
    expect(screen.queryByTestId("agent-stuck-banner")).not.toBeInTheDocument();
  });

  it("is not offered for an archived video", async () => {
    renderModal(makeVideo("VOICE_READY", "2026-09-26T00:00:00Z", "2026-09-27T00:00:00Z"));
    await settle();
    expect(screen.queryByText("Retry agent")).not.toBeInTheDocument();
  });

  it("posts to agent-retry and refetches the video", async () => {
    const fetchMock = renderModal(makeVideo("TOPIC_APPROVED", "2026-09-26T00:00:00Z"));
    fireEvent.click(await screen.findByText("Retry agent"));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith(
      "/api/proxy/videos/vid-1/agent-retry", expect.objectContaining({ method: "POST" })));
    await act(async () => {});
    const refetches = fetchMock.mock.calls.filter(([u]) => String(u).endsWith("/videos/vid-1"));
    expect(refetches.length).toBeGreaterThanOrEqual(2);
  });

  it("shows the server's reason when the retry is refused", async () => {
    renderModal(makeVideo("VOICE_READY", "2026-09-26T00:00:00Z"),
                { ok: false, body: { error: "Video is archived and can no longer be changed" } });
    fireEvent.click(await screen.findByText("Retry agent"));
    expect(await screen.findByTestId("retry-agent-error"))
      .toHaveTextContent("Video is archived and can no longer be changed");
  });
});

describe("KanbanCard — STUCK badge", () => {
  it("marks a stuck video and only a stuck one", () => {
    const { rerender } = render(
      <KanbanCard video={makeVideo("VOICE_READY", "2026-09-26T00:00:00Z")} accent="#fff"
                  onAction={vi.fn()} onOpenModal={vi.fn()} />);
    expect(screen.getByTestId("kanban-card-stuck-vid-1")).toHaveTextContent("STUCK");
    rerender(<KanbanCard video={makeVideo("VOICE_READY", null)} accent="#fff"
                         onAction={vi.fn()} onOpenModal={vi.fn()} />);
    expect(screen.queryByTestId("kanban-card-stuck-vid-1")).not.toBeInTheDocument();
  });
});
