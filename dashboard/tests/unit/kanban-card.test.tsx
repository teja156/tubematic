import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

vi.mock("@/components/TimeZoneProvider", () => ({
  useTimeZone: () => ({ timeZone: "America/New_York", label: "EDT (UTC-04:00)", degraded: false }),
}));

import { KanbanCard } from "@/components/KanbanCard";
import type { Video } from "@/lib/types";
import { scoreLabel } from "@/lib/utils";

const LONG_TOPIC =
  "Why a web app can convert a 2 GB video without ever uploading it, and the two HTTP " +
  "headers it must send to be allowed to. Walk the mechanism in order: picking a file " +
  "hands the page the actual bytes locally, so no network request has happened yet.";

function makeVideo(overrides: Partial<Video> = {}): Video {
  return {
    id: "vid-1",
    project_id: "proj-1",
    title: "",
    topic: LONG_TOPIC,
    strategy: "trending",
    producibility_score: 7,
    status: "TOPIC_PROPOSED",
    script: null,
    voice_file_path: null,
    timeline_path: null,
    scene_config_path: null,
    video_path: null,
    video_version: 1,
    gemini_feedback: null,
    youtube_url: null,
    voice_id: "",
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-01T00:00:00Z",
    ...overrides,
  } as Video;
}

function renderCard(video: Video) {
  return render(
    <KanbanCard video={video} accent="#f5a623" onAction={() => {}} onOpenModal={() => {}} />,
  );
}

describe("KanbanCard display name", () => {
  it("renders the short title when the video has one", () => {
    renderCard(makeVideo({ title: "Converting video without uploading it" }));
    expect(screen.getByText("Converting video without uploading it")).toBeTruthy();
    expect(screen.queryByText(LONG_TOPIC)).toBeNull();
  });

  it("falls back to the topic when title is the empty string", () => {
    // Every row written before the split holds '' here, not null — a `??`
    // fallback would leave those cards blank.
    renderCard(makeVideo({ title: "" }));
    expect(screen.getByText(LONG_TOPIC)).toBeTruthy();
  });

  it("falls back to the topic when title is null", () => {
    renderCard(makeVideo({ title: null }));
    expect(screen.getByText(LONG_TOPIC)).toBeTruthy();
  });

  // The two-line clamp is what stops a legacy row's 400-2400 character topic
  // from turning the card into a wall of text, and it cannot be asserted through
  // the DOM: jsdom's cssstyle drops every -webkit- property, so the rendered
  // style attribute comes back as just "overflow: hidden". Guard the source
  // instead, so the clamp cannot be deleted silently.
  it("declares a two-line clamp on the display name", () => {
    const src = readFileSync(
      resolve(__dirname, "../../components/KanbanCard.tsx"),
      "utf8",
    );
    expect(src).toContain('display: "-webkit-box"');
    expect(src).toContain("WebkitLineClamp: 2");
    expect(src).toContain('WebkitBoxOrient: "vertical"');
  });

  it("keeps the full topic reachable on hover even when a short title is shown", () => {
    const { container } = renderCard(makeVideo({ title: "A short name" }));
    const name = Array.from(container.querySelectorAll<HTMLElement>("div")).find(
      (d) => d.textContent === "A short name",
    );
    expect(name!.getAttribute("title")).toBe(LONG_TOPIC);
  });
});

describe("KanbanCard score", () => {
  it("shows a real score out of 10", () => {
    const { container } = renderCard(makeVideo({ producibility_score: 7 }));
    expect(container.textContent).toContain("7/10");
  });

  it("shows an unscored video (score 0, from the New Video page) as a dash", () => {
    const { container } = renderCard(makeVideo({ producibility_score: 0 }));
    expect(container.textContent).toContain("—");
    expect(container.textContent).not.toContain("0/10");
  });
});

describe("scoreLabel", () => {
  it("reads 0 as unscored and anything else out of 10", () => {
    expect(scoreLabel(0)).toBe("—");
    expect(scoreLabel(5)).toBe("5/10");
  });
});

describe("KanbanCard scheduled time (TMDEV-133)", () => {
  it("shows when a scheduled post goes out, in the zone it was picked in", () => {
    renderCard(makeVideo({
      status: "SCHEDULED", scheduled_at: "2026-10-01T03:30:00Z", scheduled_timezone: "Asia/Kolkata",
    }));
    const line = screen.getByTestId("scheduled-at-vid-1");
    expect(line.textContent).toContain("Oct 1, 2026");
    expect(line.textContent).toContain("9:00 AM");
    expect(line.textContent).toContain("Asia/Kolkata");
  });

  it("shows nothing of the kind on any other status", () => {
    renderCard(makeVideo({ status: "VIDEO_APPROVED", scheduled_at: "2026-10-01T03:30:00Z" }));
    expect(screen.queryByTestId("scheduled-at-vid-1")).toBeNull();
  });
});
