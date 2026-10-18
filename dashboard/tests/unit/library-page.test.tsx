/**
 * Tests for the Library page data-fetching behavior.
 *
 * Critical regressions guarded here:
 *  1. Fetch includes cache: "no-store"
 *  2. Non-array API response does not crash the page
 *  3. Polling fires again after 5 seconds
 *  4. Polling interval is cleaned up on unmount
 *  5. Search matches the short title AND the full topic — after the split,
 *     searching one field alone makes a video unfindable by words in the other
 */
import { act, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

// Records its props so a test can drive onAction the way the real modal would.
type ModalProps = {
  agents?: unknown;
  publishingEnabled?: boolean;
  onAction: (id: string, action: string, video?: unknown, extra?: Record<string, unknown>)
    => Promise<void> | void;
};
const modalProps: ModalProps[] = [];
vi.mock("@/components/VideoModal", () => ({
  VideoModal: (props: ModalProps) => {
    modalProps.push(props);
    return null;
  },
}));
vi.mock("@/components/SectionLabel", () => ({ SectionLabel: () => null }));

import LibraryPage from "@/app/library/page";

// ── helpers ──────────────────────────────────────────────────────────────────

function mockFetchEmpty() {
  return vi.spyOn(global, "fetch").mockResolvedValue({
    status: 200,
    json: () => Promise.resolve([]),
  } as unknown as Response);
}

// ── tests ─────────────────────────────────────────────────────────────────────

describe("LibraryPage", () => {
  afterEach(() => vi.restoreAllMocks());

  it('fetches /videos with cache: "no-store" on mount', async () => {
    const fetchSpy = mockFetchEmpty();

    render(<LibraryPage />);
    await act(async () => {});

    expect(fetchSpy).toHaveBeenCalledWith(
      expect.stringContaining("/videos"),
      expect.objectContaining({ cache: "no-store" }),
    );
  });

  it("a delete from the modal sends DELETE and reloads the list (TMDEV-84)", async () => {
    const fetchSpy = vi.spyOn(global, "fetch").mockResolvedValue({
      ok: true,
      status: 200,
      json: () => Promise.resolve([]),
    } as unknown as Response);

    render(<LibraryPage />);
    await act(async () => {});
    await act(async () => { await modalProps.at(-1)!.onAction("vid-1", "delete"); });

    expect(fetchSpy).toHaveBeenCalledWith("/api/proxy/videos/vid-1", { method: "DELETE" });
    const after = fetchSpy.mock.calls.findIndex(([, init]) => init?.method === "DELETE");
    expect(fetchSpy.mock.calls.slice(after + 1).some(([u]) => String(u).endsWith("/videos"))).toBe(true);
  });

  it("does not crash when the API returns an error object instead of an array", async () => {
    vi.spyOn(global, "fetch").mockResolvedValue({
      status: 502,
      json: () => Promise.resolve({ error: "Service unavailable" }),
    } as unknown as Response);

    expect(() => render(<LibraryPage />)).not.toThrow();
    await act(async () => {});
  });

  it("polls again after 5 seconds", async () => {
    vi.useFakeTimers({ toFake: ["setInterval", "clearInterval"] });
    const fetchSpy = mockFetchEmpty();

    render(<LibraryPage />);
    await act(async () => { await Promise.resolve(); });

    const countAfterMount = fetchSpy.mock.calls.length;
    expect(countAfterMount).toBeGreaterThanOrEqual(1);

    await act(async () => {
      vi.advanceTimersByTime(5_000);
      await Promise.resolve();
    });

    expect(fetchSpy.mock.calls.length).toBeGreaterThan(countAfterMount);
    vi.useRealTimers();
  });

  it("clears the polling interval on unmount (no memory leak)", async () => {
    vi.useFakeTimers({ toFake: ["setInterval", "clearInterval"] });
    const clearSpy = vi.spyOn(global, "clearInterval");
    mockFetchEmpty();

    const { unmount } = render(<LibraryPage />);
    await act(async () => {});

    unmount();
    expect(clearSpy).toHaveBeenCalled();
    vi.useRealTimers();
  });
});

// ── search across both text fields ───────────────────────────────────────────

const VIDEO_WITH_TITLE = {
  id: "vid-1",
  project_id: "proj-1",
  title: "Converting video in the browser",
  topic: "Why a web app can transcode a 2 GB file without ever uploading it, using a "
       + "WebAssembly codec and SharedArrayBuffer across Web Workers.",
  strategy: "trending",
  producibility_score: 8,
  status: "VIDEO_READY",
  video_version: 1,
  voice_id: "",
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-01T00:00:00Z",
};

// A legacy row: title is '' (not null), which is what every pre-split row holds.
const LEGACY_VIDEO = {
  ...VIDEO_WITH_TITLE,
  id: "vid-2",
  title: "",
  topic: "How DNS resolves a domain name to an IP address",
};

function mockFetchVideos(videos: unknown[]) {
  return vi.spyOn(global, "fetch").mockResolvedValue({
    status: 200,
    json: () => Promise.resolve(videos),
  } as unknown as Response);
}

async function renderWithSearch(videos: unknown[], term: string) {
  mockFetchVideos(videos);
  render(<LibraryPage />);
  await act(async () => {});
  const input = screen.getByPlaceholderText(/search titles/i);
  await act(async () => {
    fireEvent.change(input, { target: { value: term } });
  });
}

describe("LibraryPage search", () => {
  afterEach(() => vi.restoreAllMocks());

  it("matches a word in the short title", async () => {
    await renderWithSearch([VIDEO_WITH_TITLE, LEGACY_VIDEO], "browser");
    expect(screen.getByText("Converting video in the browser")).toBeTruthy();
    expect(screen.queryByText(LEGACY_VIDEO.topic)).toBeNull();
  });

  it("matches a word that only appears in the full topic", async () => {
    // "SharedArrayBuffer" is nowhere in the title. Searching titles alone would
    // make this video unfindable by the very term that describes it.
    await renderWithSearch([VIDEO_WITH_TITLE, LEGACY_VIDEO], "SharedArrayBuffer");
    expect(screen.getByText("Converting video in the browser")).toBeTruthy();
    expect(screen.queryByText(LEGACY_VIDEO.topic)).toBeNull();
  });

  it("still matches a legacy row whose title is empty", async () => {
    await renderWithSearch([VIDEO_WITH_TITLE, LEGACY_VIDEO], "DNS");
    expect(screen.getByText(LEGACY_VIDEO.topic)).toBeTruthy();
    expect(screen.queryByText("Converting video in the browser")).toBeNull();
  });

  it("returns nothing for a term in neither field", async () => {
    await renderWithSearch([VIDEO_WITH_TITLE, LEGACY_VIDEO], "kubernetes");
    expect(screen.queryByText("Converting video in the browser")).toBeNull();
    expect(screen.queryByText(LEGACY_VIDEO.topic)).toBeNull();
  });
});

// ── Request Revision and the agent picker (TMDEV-110) ────────────────────────

describe("LibraryPage — revising a ready video", () => {
  afterEach(() => vi.restoreAllMocks());

  const AGENTS = [{ id: "claude", name: "Claude Code", models: ["sonnet"], archived_at: null }];

  function mockApi() {
    return vi.spyOn(global, "fetch").mockImplementation((url) =>
      Promise.resolve({
        ok: true, status: 200,
        json: () => Promise.resolve(String(url).endsWith("/agents") ? AGENTS : []),
      } as unknown as Response));
  }

  function patchBody(fetchSpy: ReturnType<typeof mockApi>) {
    const patch = fetchSpy.mock.calls.find(([, init]) => (init as RequestInit | undefined)?.method === "PATCH");
    return patch ? JSON.parse((patch[1] as RequestInit).body as string) : undefined;
  }

  it("fetches /agents and hands them to the modal", async () => {
    const fetchSpy = mockApi();
    render(<LibraryPage />);
    await act(async () => { await Promise.resolve(); await Promise.resolve(); });
    expect(fetchSpy.mock.calls.some(([u]) => String(u).endsWith("/api/proxy/agents"))).toBe(true);
    expect(modalProps[modalProps.length - 1].agents).toEqual(AGENTS);
  });

  it("Request Revision actually moves the video — it used to post the comment and stop", async () => {
    const fetchSpy = mockApi();
    render(<LibraryPage />);
    await act(async () => {});
    await act(async () => {
      await modalProps[modalProps.length - 1].onAction("vid-1", "revise-video", { id: "vid-1" });
    });
    expect(patchBody(fetchSpy)).toEqual(
      { status: "REVISION_REQUESTED", onlyIfCurrentStatus: "VIDEO_READY" });
  });

  it("the revision carries the picked agent in the same PATCH", async () => {
    const fetchSpy = mockApi();
    render(<LibraryPage />);
    await act(async () => {});
    await act(async () => {
      await modalProps[modalProps.length - 1].onAction("vid-1", "revise-video", { id: "vid-1" },
        { agent_id: "codex", agent_model: "gpt-5" });
    });
    expect(patchBody(fetchSpy)).toEqual({
      status: "REVISION_REQUESTED", onlyIfCurrentStatus: "VIDEO_READY",
      agent_id: "codex", agent_model: "gpt-5",
    });
  });
});

describe("LibraryPage — a refused action is reported, not swallowed", () => {
  afterEach(() => vi.restoreAllMocks());

  it.each([
    ["revise-video", { agent_id: "codex" }],
    ["approve-video", undefined],
  ] as const)("%s: tells the human why the API said no", async (action, extra) => {
    vi.spyOn(global, "fetch").mockImplementation((url, init) =>
      Promise.resolve((init as RequestInit | undefined)?.method === "PATCH"
        ? { ok: false, status: 400, json: () => Promise.resolve({ error: "agent_id 'codex' is uninstalled" }) }
        : { ok: true, status: 200, json: () => Promise.resolve([]) }) as unknown as Promise<Response>);
    const alertSpy = vi.spyOn(window, "alert").mockImplementation(() => {});
    render(<LibraryPage />);
    await act(async () => {});
    await act(async () => {
      await modalProps[modalProps.length - 1].onAction("vid-1", action, { id: "vid-1" }, extra);
    });
    expect(alertSpy).toHaveBeenCalledWith("agent_id 'codex' is uninstalled");
  });
});

// The modal offers Publish… (and Retry publishing, Cancel schedule) only when
// told publishing is on. The Library lists exactly the videos those apply to,
// yet never passed the flag, so a video opened here could not be published.
describe("LibraryPage publishing flag", () => {
  afterEach(() => vi.restoreAllMocks());

  function stubSettings(settings: Record<string, unknown> | "fail") {
    vi.spyOn(global, "fetch").mockImplementation((url: string | URL | Request) => {
      const u = url.toString();
      if (u.endsWith("/settings")) {
        return settings === "fail"
          ? Promise.reject(new Error("down"))
          : Promise.resolve({ ok: true, json: () => Promise.resolve(settings) } as Response);
      }
      return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve([]) } as Response);
    });
  }

  it("tells the modal publishing is on when /settings says so", async () => {
    stubSettings({ publishing_enabled: true });
    render(<LibraryPage />);
    await act(async () => {});
    expect(modalProps.at(-1)!.publishingEnabled).toBe(true);
  });

  it("keeps it off when publishing is disabled", async () => {
    stubSettings({ publishing_enabled: false });
    render(<LibraryPage />);
    await act(async () => {});
    expect(modalProps.at(-1)!.publishingEnabled).toBe(false);
  });

  it("keeps it off when /settings cannot be read", async () => {
    stubSettings("fail");
    render(<LibraryPage />);
    await act(async () => {});
    expect(modalProps.at(-1)!.publishingEnabled).toBe(false);
  });
});
