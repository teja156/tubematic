/**
 * VideoModal's "Mark as published" action (TMDEV-191).
 *
 *  1. Offered only at PARTIALLY_PUBLISHED (live on some accounts, failed on
 *     others), never on an archived video, and not gated on publishing being
 *     enabled — it is the only way out of that state.
 *  2. Opens a confirm dialog that says how many accounts it reached, tells the
 *     human to download first (retention counts from the first successful post,
 *     not from this click) and carries the download link.
 *  3. Confirming sends a guarded PATCH; a refusal stays visible in the dialog.
 */
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { VideoModal } from "@/components/VideoModal";
import { canMarkPublished } from "@/lib/videoStatus";
import type { Video, VideoPublication, VideoStatus } from "@/lib/types";

vi.mock("@/components/TimeZoneProvider", () => ({
  useTimeZone: () => ({ timeZone: "UTC", label: "UTC", degraded: false }),
}));

function makeVideo(status: VideoStatus, archived_at: string | null = null): Video {
  return {
    id: "vid-1", project_id: "proj-1", title: null, topic: "Test topic", strategy: "curriculum",
    producibility_score: 5, status, script: null, voice_file_path: null, timeline_path: null,
    scene_config_path: null, video_path: null, archived_at, video_version: 1,
    gemini_feedback: null, youtube_url: null, voice_id: "", created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-01T00:00:00Z", comments: [],
  };
}

function pub(id: string, status: VideoPublication["status"]): VideoPublication {
  return {
    id, video_id: "vid-1", platform: "youtube", social_account_id: `spc_${id}`, status,
    post_url: status === "PUBLISHED" ? "https://youtu.be/x" : "", error: status === "FAILED" ? "nope" : "",
    published_at: "", created_at: "2026-01-01T00:00:00Z", updated_at: "2026-01-01T00:00:00Z",
  };
}

const PUBS = [pub("a", "PUBLISHED"), pub("b", "FAILED")];

function renderModal(video: Video, { patch = { ok: true, status: 200, body: {} as object },
                                     publishingEnabled = true,
                                     pubs = "ok" as "ok" | "pending" | "error" } = {}) {
  const fetchMock = vi.fn(async (url: unknown, init?: RequestInit) => {
    const u = String(url);
    if (u.endsWith(`/videos/${video.id}`) && init?.method === "PATCH") {
      return { ok: patch.ok, status: patch.status, json: async () => patch.body } as Response;
    }
    if (u.endsWith("/publications")) {
      if (pubs === "pending") return new Promise<Response>(() => {});
      if (pubs === "error") return { ok: false, status: 502, json: async () => ({ error: "down" }) } as Response;
      return { ok: true, json: async () => PUBS } as Response;
    }
    if (u.endsWith(`/videos/${video.id}`)) return { ok: true, json: async () => video } as Response;
    return { ok: true, json: async () => [] } as Response;
  });
  vi.stubGlobal("fetch", fetchMock);
  render(<VideoModal video={video} onClose={vi.fn()} onAction={vi.fn()}
                     publishingEnabled={publishingEnabled} />);
  return fetchMock;
}

async function settle() {
  await screen.findByTestId("video-modal");
  await act(async () => {});
}

describe("canMarkPublished", () => {
  it("needs PARTIALLY_PUBLISHED and no archive", () => {
    expect(canMarkPublished({ status: "PARTIALLY_PUBLISHED", archived_at: null })).toBe(true);
    expect(canMarkPublished({ status: "PARTIALLY_PUBLISHED", archived_at: "2026-09-01" })).toBe(false);
    expect(canMarkPublished({ status: "PUBLISHED", archived_at: null })).toBe(false);
    expect(canMarkPublished({ status: "FAILED", archived_at: null })).toBe(false);
  });
});

describe("VideoModal — Mark as published", () => {
  afterEach(() => { vi.unstubAllGlobals(); vi.restoreAllMocks(); });

  it("is offered for a partial publish, even with publishing switched off", async () => {
    renderModal(makeVideo("PARTIALLY_PUBLISHED"), { publishingEnabled: false });
    expect(await screen.findByText("Mark as published…")).toBeInTheDocument();
  });

  it.each(["PUBLISHED", "FAILED", "VIDEO_APPROVED"] as VideoStatus[])("is not offered at %s", async (s) => {
    renderModal(makeVideo(s));
    await settle();
    expect(screen.queryByText("Mark as published…")).not.toBeInTheDocument();
  });

  it("is not offered on an archived video", async () => {
    renderModal(makeVideo("PARTIALLY_PUBLISHED", "2026-09-01T00:00:00Z"));
    await settle();
    expect(screen.queryByText("Mark as published…")).not.toBeInTheDocument();
  });

  it("confirms with the account count, the download warning and a download link", async () => {
    const fetchMock = renderModal(makeVideo("PARTIALLY_PUBLISHED"));
    await waitFor(() => expect(fetchMock.mock.calls.some(([u]) => String(u).endsWith("/publications"))).toBe(true));
    fireEvent.click(await screen.findByText("Mark as published…"));
    const dialog = await screen.findByTestId("mark-published-dialog");
    expect(dialog.textContent).toContain("1 of 2");
    expect(screen.getByTestId("mark-published-warning").textContent).toMatch(/Download the video first/);
    const link = screen.getByTestId("mark-published-download");
    expect(link.getAttribute("href")).toBe("/stream/proj-1/vid-1.mp4");
    expect(link.hasAttribute("download")).toBe(true);
    // Nothing is sent until the human confirms.
    expect(fetchMock.mock.calls.some(([, init]) => (init as RequestInit)?.method === "PATCH")).toBe(false);
  });

  it("sends a guarded PATCH when confirmed", async () => {
    const fetchMock = renderModal(makeVideo("PARTIALLY_PUBLISHED"));
    fireEvent.click(await screen.findByText("Mark as published…"));
    fireEvent.click(await screen.findByRole("button", { name: "Mark as published" }));
    await waitFor(() => {
      const call = fetchMock.mock.calls.find(([, init]) => (init as RequestInit)?.method === "PATCH");
      expect(call).toBeDefined();
      expect(JSON.parse(String((call![1] as RequestInit).body))).toEqual({
        status: "PUBLISHED", onlyIfCurrentStatus: "PARTIALLY_PUBLISHED",
      });
    });
    await waitFor(() => expect(screen.queryByTestId("mark-published-dialog")).not.toBeInTheDocument());
  });

  it("keeps the dialog open with the reason when the API refuses", async () => {
    renderModal(makeVideo("PARTIALLY_PUBLISHED"),
                { patch: { ok: false, status: 409, body: { error: "Status precondition failed" } } });
    fireEvent.click(await screen.findByText("Mark as published…"));
    fireEvent.click(await screen.findByRole("button", { name: "Mark as published" }));
    expect((await screen.findByTestId("mark-published-error")).textContent).toMatch(/already taken/);
    expect(screen.getByTestId("mark-published-dialog")).toBeInTheDocument();
  });

  it("cannot be confirmed while the publishing results are still loading", async () => {
    // Confirming hands the video to retention; doing it before the human can
    // see which accounts failed (and with a "0 of 0" count) must not be possible.
    renderModal(makeVideo("PARTIALLY_PUBLISHED"), { pubs: "pending" });
    fireEvent.click(await screen.findByText("Mark as published…"));
    const dialog = await screen.findByTestId("mark-published-dialog");
    expect(screen.getByRole("button", { name: "Mark as published" })).toBeDisabled();
    expect(dialog.textContent).not.toContain("0 of 0");
  });

  it("says so, and cannot be confirmed, when the publishing results fail to load", async () => {
    renderModal(makeVideo("PARTIALLY_PUBLISHED"), { pubs: "error" });
    fireEvent.click(await screen.findByText("Mark as published…"));
    expect((await screen.findByTestId("mark-published-pubs-error")).textContent).toMatch(/could not load/i);
    expect(screen.getByRole("button", { name: "Mark as published" })).toBeDisabled();
  });

  it("ignores a late publication response for the video it showed before", async () => {
    // Video A's request resolving after the modal moved to B must not mark B's
    // list as loaded — that would unlock B's confirm behind A's rows.
    let releaseA: (r: Response) => void = () => {};
    const A = { ...makeVideo("PUBLISHED"), id: "vid-A" };
    const B = { ...makeVideo("PARTIALLY_PUBLISHED"), id: "vid-B" };
    vi.stubGlobal("fetch", vi.fn(async (url: unknown) => {
      const u = String(url);
      if (u.endsWith("/videos/vid-A/publications")) return new Promise<Response>((r) => { releaseA = r; });
      if (u.endsWith("/videos/vid-B/publications")) return new Promise<Response>(() => {});
      if (u.endsWith("/videos/vid-A")) return { ok: true, json: async () => A } as Response;
      if (u.endsWith("/videos/vid-B")) return { ok: true, json: async () => B } as Response;
      return { ok: true, json: async () => [] } as Response;
    }));
    const { rerender } = render(<VideoModal video={A} onClose={vi.fn()} onAction={vi.fn()} publishingEnabled />);
    await settle();
    rerender(<VideoModal video={B} onClose={vi.fn()} onAction={vi.fn()} publishingEnabled />);
    await act(async () => {});
    await act(async () => { releaseA({ ok: true, json: async () => PUBS } as Response); });
    fireEvent.click(await screen.findByText("Mark as published…"));
    await screen.findByTestId("mark-published-dialog");
    expect(screen.getByRole("button", { name: "Mark as published" })).toBeDisabled();
  });
});

describe("VideoModal — an action that finishes after the modal moved on", () => {
  afterEach(() => { vi.unstubAllGlobals(); vi.restoreAllMocks(); });

  it("does not load the old video's rows into the new one", async () => {
    // Retry publishing started on A finishes after B opened; its callback
    // refreshes A's publications, which is now the newest request of all.
    let finishRetry: (r: Response) => void = () => {};
    const A = { ...makeVideo("FAILED"), id: "vid-A" };
    const B = { ...makeVideo("PARTIALLY_PUBLISHED"), id: "vid-B" };
    vi.stubGlobal("fetch", vi.fn(async (url: unknown, init?: RequestInit) => {
      const u = String(url);
      if (u.endsWith("/videos/vid-A/publish/retry") && init?.method === "POST") {
        return new Promise<Response>((r) => { finishRetry = r; });
      }
      if (u.endsWith("/videos/vid-A/publications")) {
        return { ok: true, json: async () => [{ ...pub("b", "FAILED"), video_id: "vid-A" }] } as Response;
      }
      if (u.endsWith("/videos/vid-B/publications")) return new Promise<Response>(() => {});
      if (u.endsWith("/videos/vid-A")) return { ok: true, json: async () => A } as Response;
      if (u.endsWith("/videos/vid-B")) return { ok: true, json: async () => B } as Response;
      return { ok: true, json: async () => [] } as Response;
    }));
    const { rerender } = render(<VideoModal video={A} onClose={vi.fn()} onAction={vi.fn()} publishingEnabled />);
    fireEvent.click(await screen.findByText("Retry publishing"));
    rerender(<VideoModal video={B} onClose={vi.fn()} onAction={vi.fn()} publishingEnabled />);
    await act(async () => {});
    await act(async () => { finishRetry({ ok: true, json: async () => ({ outcome: "reconciling" }) } as Response); });
    await act(async () => {});
    fireEvent.click(await screen.findByText("Mark as published…"));
    await screen.findByTestId("mark-published-dialog");
    expect(screen.getByRole("button", { name: "Mark as published" })).toBeDisabled();
  });
});

describe("VideoModal — two refreshes of the same video", () => {
  afterEach(() => { vi.unstubAllGlobals(); vi.restoreAllMocks(); });

  it("keeps the newer video snapshot when the older one answers last", async () => {
    // The modal's first fetch is still out when Retry publishing's refresh
    // returns PUBLISHING; the first fetch's stale FAILED must not win.
    let releaseFirst: (r: Response) => void = () => {};
    let videoCalls = 0;
    const failed = makeVideo("FAILED");
    vi.stubGlobal("fetch", vi.fn(async (url: unknown, init?: RequestInit) => {
      const u = String(url);
      if (u.endsWith("/publish/retry") && init?.method === "POST") {
        return { ok: true, json: async () => ({ outcome: "reconciling" }) } as Response;
      }
      if (u.endsWith("/publications")) {
        return { ok: true, json: async () => [pub("b", "FAILED")] } as Response;
      }
      if (u.endsWith("/videos/vid-1")) {
        videoCalls += 1;
        if (videoCalls === 1) return new Promise<Response>((r) => { releaseFirst = r; });
        return { ok: true, json: async () => makeVideo("PUBLISHING") } as Response;
      }
      return { ok: true, json: async () => [] } as Response;
    }));
    render(<VideoModal video={failed} onClose={vi.fn()} onAction={vi.fn()} publishingEnabled />);
    fireEvent.click(await screen.findByText("Retry publishing"));
    await waitFor(() => expect(videoCalls).toBe(2));
    await act(async () => {});
    await act(async () => { releaseFirst({ ok: true, json: async () => failed } as Response); });
    await act(async () => {});
    expect(screen.queryByText("Retry publishing")).not.toBeInTheDocument();
  });
});

describe("VideoModal — a failed publication refresh", () => {
  afterEach(() => { vi.unstubAllGlobals(); vi.restoreAllMocks(); });

  it("clears the rows rather than keeping the ones from before the action", async () => {
    const failedPub = { ...pub("b", "FAILED") };
    let pubCalls = 0;
    const video = makeVideo("FAILED");
    vi.stubGlobal("fetch", vi.fn(async (url: unknown, init?: RequestInit) => {
      const u = String(url);
      if (u.endsWith("/publish/retry") && init?.method === "POST") {
        return { ok: true, json: async () => ({ outcome: "reconciling" }) } as Response;
      }
      if (u.endsWith("/publications")) {
        pubCalls += 1;
        if (pubCalls === 1) return { ok: true, json: async () => [failedPub] } as Response;
        return { ok: false, status: 502, json: async () => ({ error: "down" }) } as Response;
      }
      if (u.endsWith(`/videos/${video.id}`)) return { ok: true, json: async () => video } as Response;
      return { ok: true, json: async () => [] } as Response;
    }));
    render(<VideoModal video={video} onClose={vi.fn()} onAction={vi.fn()} publishingEnabled />);
    fireEvent.click(await screen.findByText("Retry publishing"));
    await waitFor(() => expect(pubCalls).toBe(2));
    // The pre-retry FAILED row is gone, so nothing offers to retry it again.
    await waitFor(() => expect(screen.queryByText("Retry publishing")).not.toBeInTheDocument());
  });
});
