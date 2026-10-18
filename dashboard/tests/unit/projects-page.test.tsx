import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

vi.mock("@/components/VideoModal", () => ({ VideoModal: () => null }));
vi.mock("@/components/SectionLabel", () => ({
  SectionLabel: ({ label }: { label: string; count?: string }) => (
    <div data-testid="section-label">{label}</div>
  ),
}));
// Fixed to America/New_York so the rendered-date test below has a deterministic,
// non-UTC expected value (see the "renders video dates in the host timezone" test).
vi.mock("@/components/TimeZoneProvider", () => ({
  useTimeZone: () => ({ timeZone: "America/New_York", label: "EDT (UTC-04:00)", degraded: false }),
}));

import ProjectsPage from "@/app/projects/page";

const MOCK_PROJECT = {
  id: "proj-1",
  name: "Python Tutorials",
  description: "Python content",
  is_curriculum_seed: 1,
  status: "active",
  created_at: "2026-01-01T00:00:00Z",
  expired: false,
};

const MOCK_VIDEO = {
  id: "vid-1",
  project_id: "proj-1",
  topic: "Python basics",
  strategy: "curriculum",
  status: "TOPIC_PROPOSED",
  producibility_score: 7,
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-01T00:00:00Z",
};

function mockFetch(projects = [MOCK_PROJECT], videos = [MOCK_VIDEO]) {
  return vi.spyOn(global, "fetch").mockImplementation((url: string | URL | Request) => {
    const urlStr = url.toString();
    if (urlStr.includes("/videos")) {
      return Promise.resolve({ ok: true, json: () => Promise.resolve(videos) } as Response);
    }
    return Promise.resolve({ ok: true, json: () => Promise.resolve(projects) } as Response);
  });
}

describe("ProjectsPage", () => {
  afterEach(() => vi.restoreAllMocks());

  // Pause exists only on curriculum seeds, so a status badge on any other
  // domain would describe a state nothing can change.
  it("shows the active/paused badge on a curriculum seed only", async () => {
    mockFetch([MOCK_PROJECT, { ...MOCK_PROJECT, id: "proj-2", name: "Plain", is_curriculum_seed: 0 }]);
    render(<ProjectsPage />);
    await waitFor(() => screen.getByTestId("project-row-proj-2"));
    expect(screen.getByTestId("project-status-proj-1").textContent).toBe("active");
    expect(screen.queryByTestId("project-status-proj-2")).toBeNull();
  });

  // TMDEV-153: any domain at its topic cap is expired, seed or not.
  it("shows the expired badge on any domain at its topic cap", async () => {
    mockFetch([MOCK_PROJECT,
               { ...MOCK_PROJECT, id: "proj-2", name: "Plain", is_curriculum_seed: 0, expired: true }]);
    render(<ProjectsPage />);
    await waitFor(() => screen.getByTestId("project-row-proj-2"));
    expect(screen.getByTestId("project-expired-proj-2").textContent).toBe("expired");
    expect(screen.queryByTestId("project-expired-proj-1")).toBeNull();
  });

  it("renders project rows after loading", async () => {
    mockFetch();
    render(<ProjectsPage />);
    await waitFor(() => {
      expect(screen.getByTestId("project-row-proj-1")).toBeTruthy();
    });
  });

  it("renders video dates in the host timezone, not UTC", async () => {
    mockFetch();
    render(<ProjectsPage />);
    await waitFor(() => screen.getByTestId("project-row-proj-1"));

    await act(async () => {
      fireEvent.click(screen.getByTestId("project-row-proj-1"));
    });

    // created_at is 2026-01-01T00:00:00Z — a day earlier in America/New_York.
    await waitFor(() => {
      expect(screen.getByTestId("project-video-vid-1").textContent).toContain("Dec 31, 2025");
    });
  });

  it("clicking a project row shows its videos", async () => {
    mockFetch();
    render(<ProjectsPage />);
    await waitFor(() => screen.getByTestId("project-row-proj-1"));

    await act(async () => {
      fireEvent.click(screen.getByTestId("project-row-proj-1"));
    });

    await waitFor(() => {
      expect(screen.getByTestId("project-video-vid-1")).toBeTruthy();
    });
  });

  it("shows empty state when no project is selected", async () => {
    mockFetch();
    render(<ProjectsPage />);
    await waitFor(() => screen.getByTestId("project-row-proj-1"));
    // No project selected → should show "select a project" message
    // Confirm vid-1 is not in the DOM yet
    expect(screen.queryByTestId("project-video-vid-1")).toBeNull();
  });

  it("filters videos to only the selected project", async () => {
    const proj2 = { ...MOCK_PROJECT, id: "proj-2", name: "Go Tutorials" };
    const vid2 = { ...MOCK_VIDEO, id: "vid-2", project_id: "proj-2", topic: "Go basics" };
    mockFetch([MOCK_PROJECT, proj2], [MOCK_VIDEO, vid2]);

    render(<ProjectsPage />);
    await waitFor(() => screen.getByTestId("project-row-proj-1"));

    // Click project 1 - should show vid-1, not vid-2
    await act(async () => {
      fireEvent.click(screen.getByTestId("project-row-proj-1"));
    });

    await waitFor(() => {
      expect(screen.getByTestId("project-video-vid-1")).toBeTruthy();
      expect(screen.queryByTestId("project-video-vid-2")).toBeNull();
    });
  });

  it("polls for updates every 5 seconds", async () => {
    vi.useFakeTimers({ toFake: ["setInterval", "clearInterval"] });
    const fetchSpy = mockFetch();
    render(<ProjectsPage />);
    await act(async () => { await Promise.resolve(); });

    const callsAfterMount = fetchSpy.mock.calls.length;
    expect(callsAfterMount).toBeGreaterThanOrEqual(1);

    await act(async () => {
      vi.advanceTimersByTime(5_000);
      await Promise.resolve();
    });

    expect(fetchSpy.mock.calls.length).toBeGreaterThan(callsAfterMount);
    vi.useRealTimers();
  });
});
