/**
 * KanbanBoard column placement (TMDEV-191).
 *
 * PARTIALLY_PUBLISHED has no column of its own: it is live somewhere, so it
 * sits in Published, tagged PARTIAL by its card. A status with no column would
 * simply vanish from the board, which is the regression this guards.
 */
import { render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

vi.mock("@/components/TimeZoneProvider", () => ({
  useTimeZone: () => ({ timeZone: "UTC", label: "UTC", degraded: false }),
}));

import { KanbanBoard } from "@/components/KanbanBoard";
import type { Video, VideoStatus } from "@/lib/types";

function video(id: string, status: VideoStatus): Video {
  return {
    id, project_id: "proj-1", title: id, topic: id, strategy: "manual", producibility_score: 0,
    status, script: null, voice_file_path: null, timeline_path: null, scene_config_path: null,
    video_path: null, video_version: 1, gemini_feedback: null, youtube_url: null, voice_id: "",
    created_at: "2026-01-01T00:00:00Z", updated_at: "2026-01-01T00:00:00Z",
  } as Video;
}

describe("KanbanBoard", () => {
  it("shows a partially published video in the Published column", () => {
    render(<KanbanBoard videos={[video("full", "PUBLISHED"), video("part", "PARTIALLY_PUBLISHED")]}
                        onAction={() => {}} onOpenModal={() => {}} />);
    const column = screen.getByTestId("kanban-col-PUBLISHED");
    expect(within(column).getByTestId("kanban-card-full")).toBeTruthy();
    expect(within(column).getByTestId("kanban-card-part")).toBeTruthy();
    expect(screen.queryByTestId("kanban-col-PARTIALLY_PUBLISHED")).toBeNull();
  });
});
