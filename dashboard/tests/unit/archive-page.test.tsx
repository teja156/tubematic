/**
 * The Archive page (TMDEV-84): lists only archived videos, and keeps their
 * publication links and analytics — archiving deletes files, not the record.
 */
import { act, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

vi.mock("@/components/SectionLabel", () => ({
  SectionLabel: ({ label, count }: { label: string; count?: string }) => (
    <div data-testid="section-label">{label}{count && ` — ${count}`}</div>
  ),
}));
vi.mock("@/components/TimeZoneProvider", () => ({
  useTimeZone: () => ({ timeZone: "UTC", label: "UTC", degraded: false }),
}));
const modalProps: Array<{ video: unknown }> = [];
vi.mock("@/components/VideoModal", () => ({
  VideoModal: (props: { video: unknown }) => { modalProps.push(props); return null; },
}));

import ArchivePage from "@/app/archive/page";

const ARCHIVED = [
  { id: "vid-a", title: "", topic: "Old published video", project_id: "proj-1",
    status: "PUBLISHED", archived_at: "2026-09-01T00:00:00Z" },
  { id: "vid-b", title: "Deleted draft", topic: "long brief", project_id: null,
    status: "VIDEO_READY", archived_at: "2026-09-05T00:00:00Z" },
];
const ANALYTICS = {
  totals: {}, by_platform: {},
  publications: [
    { id: "p1", video_id: "vid-a", platform: "youtube", post_url: "https://yt/1", views: 100 },
    { id: "p2", video_id: "vid-a", platform: "instagram", post_url: "https://ig/1", views: 23 },
    { id: "p3", video_id: "other", platform: "youtube", post_url: "https://yt/2", views: 9 },
  ],
};

function mockFetch(videos: unknown = ARCHIVED) {
  const fn = vi.fn(async (url: unknown) => {
    const u = String(url);
    const body = u.includes("/videos") ? videos
      : u.includes("/analytics") ? ANALYTICS
      : u.includes("/projects") ? [{ id: "proj-1", name: "Networking" }]
      : {};
    return { ok: true, json: async () => body } as Response;
  });
  vi.stubGlobal("fetch", fn);
  return fn;
}

async function renderPage() {
  render(<ArchivePage />);
  await act(async () => {});
}

describe("ArchivePage", () => {
  afterEach(() => { vi.unstubAllGlobals(); modalProps.length = 0; });

  it("asks only for archived videos", async () => {
    const fetchMock = mockFetch();
    await renderPage();
    const urls = fetchMock.mock.calls.map(([u]) => String(u));
    expect(urls).toContain("/api/proxy/videos?archived=only");
  });

  it("lists every archived video, most recently archived first", async () => {
    mockFetch();
    await renderPage();
    const rows = screen.getAllByTestId(/^archive-row-/);
    expect(rows.map((r) => r.getAttribute("data-testid"))).toEqual(["archive-row-vid-b", "archive-row-vid-a"]);
    expect(screen.getByText("Deleted draft")).toBeInTheDocument();
    expect(screen.getByText("Old published video")).toBeInTheDocument();
    expect(screen.getByText("Networking")).toBeInTheDocument();
  });

  it("keeps publication links and sums views across that video's platforms", async () => {
    mockFetch();
    await renderPage();
    const row = screen.getByTestId("archive-row-vid-a");
    expect(row).toHaveTextContent("123");
    expect(row.querySelectorAll("a")).toHaveLength(2);
    expect(row).toHaveTextContent("YouTube →");
    expect(row).toHaveTextContent("Instagram →");
  });

  it("shows — rather than 0 for a video with no reported views", async () => {
    mockFetch();
    await renderPage();
    expect(screen.getByTestId("archive-row-vid-b")).toHaveTextContent("—");
  });

  it("opens the video in the modal on click", async () => {
    mockFetch();
    await renderPage();
    fireEvent.click(screen.getByTestId("archive-row-vid-b"));
    expect(modalProps.at(-1)?.video).toMatchObject({ id: "vid-b" });
  });

  it("says so when nothing is archived", async () => {
    mockFetch([]);
    await renderPage();
    expect(screen.getByTestId("archive-empty")).toBeInTheDocument();
  });
});
