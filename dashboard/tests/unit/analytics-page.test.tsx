/**
 * Analytics page (TMDEV-83).
 *
 * The recurring hazard here is treating a missing metric as a zero. Nulls are
 * "postforme did not report this", which is a different claim from "nobody
 * watched it" — a chart or a tile that renders one as the other is lying about
 * the data, and several tests below exist only to keep that distinction —
 * including in the sort, where an unreported metric goes below a real 0.
 *
 * TMDEV-130 split the page into Videos and Spend tabs, added the sort, and
 * named accounts in the filter from a live lookup that must fail quietly.
 */
import { render, screen, act, fireEvent, waitFor } from "@testing-library/react";
import { describe, it, expect, vi, afterEach } from "vitest";
import AnalyticsPage from "@/app/analytics/page";

vi.mock("@/components/SectionLabel", () => ({
  SectionLabel: ({ label, count }: { label: string; count?: string }) => (
    <div data-testid="section-label">{label} {count}</div>
  ),
}));

vi.mock("@/components/TimeZoneProvider", () => ({
  useTimeZone: () => ({ timeZone: "UTC", label: "UTC" }),
}));

vi.mock("@/components/SpendCard", () => ({
  SpendCard: () => <div data-testid="spend-card-stub" />,
}));

function row(over: Record<string, unknown> = {}) {
  return {
    id: "pub1", video_id: "vid_a", platform: "youtube", social_account_id: "spc_yt",
    status: "PUBLISHED", post_url: "https://yt/1", error: "", published_at: "2026-01-01T00:00:00Z",
    created_at: "2026-01-01T00:00:00Z", updated_at: "2026-01-01T00:00:00Z",
    title: "A Video", views: 120, likes: 9, comments: 2, shares: 1,
    fetched_at: "2026-01-02T00:00:00Z",
    ...over,
  };
}

const DATA = {
  totals: { views: 120, likes: 9, comments: 2, shares: 1, videos: 1, publications: 1 },
  by_platform: { youtube: { views: 120, likes: 9, comments: 2, shares: 1 } },
  publications: [row()],
};

function stubFetch(data: unknown = DATA, ok = true) {
  const fn = vi.fn().mockImplementation(() =>
    Promise.resolve({ ok, json: async () => data }));
  vi.stubGlobal("fetch", fn);
  return fn;
}

/** /analytics answers `data`; /publishing/accounts answers `accounts`. */
function stubRoutes(data: unknown, accounts: { ok: boolean; body: unknown }) {
  const fn = vi.fn().mockImplementation((url: string) =>
    String(url).includes("/publishing/accounts")
      ? Promise.resolve({ ok: accounts.ok, json: async () => accounts.body })
      : Promise.resolve({ ok: true, json: async () => data }));
  vi.stubGlobal("fetch", fn);
  return fn;
}

function optionTexts(testId: string) {
  return Array.from((screen.getByTestId(testId) as HTMLSelectElement).options)
    .map((o) => [o.value, o.textContent]);
}

function rowOrder() {
  return screen.getAllByTestId(/^analytics-row-/).map((el) => el.getAttribute("data-testid"));
}

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

describe("AnalyticsPage", () => {
  it("shows the cross-platform totals", async () => {
    stubFetch();
    render(<AnalyticsPage />);
    await waitFor(() => expect(screen.getByTestId("total-views")).toHaveTextContent("120"));
    expect(screen.getByTestId("total-likes")).toHaveTextContent("9");
  });

  it("counts published videos, not publications", async () => {
    stubFetch({
      ...DATA,
      totals: { ...DATA.totals, videos: 3, publications: 7 },
    });
    render(<AnalyticsPage />);
    await waitFor(() =>
      expect(screen.getByTestId("section-label")).toHaveTextContent("3 Published"));
  });

  it("renders a row per publication, linked to the live post", async () => {
    stubFetch();
    render(<AnalyticsPage />);
    const link = await screen.findByText("A Video");
    expect(link).toHaveAttribute("href", "https://yt/1");
  });

  it("shows an unreported metric as a dash, never as zero", async () => {
    stubFetch({
      totals: { views: 0, likes: 0, comments: 0, shares: 0, videos: 1, publications: 1 },
      by_platform: {},
      publications: [row({ views: null, likes: null, comments: null, shares: null,
                           fetched_at: null })],
    });
    render(<AnalyticsPage />);
    const cells = await screen.findByTestId("analytics-row-pub1");
    expect(cells).toHaveTextContent("—");
    expect(cells).toHaveTextContent("not polled yet");
  });

  it("filters by platform through the API, not in the browser", async () => {
    const fetchMock = stubFetch();
    render(<AnalyticsPage />);
    await screen.findByTestId("filter-platform");
    await act(async () => {
      fireEvent.change(screen.getByTestId("filter-platform"), { target: { value: "youtube" } });
    });
    await waitFor(() =>
      expect(fetchMock.mock.calls.some(([url]) =>
        String(url).includes("platform=youtube"))).toBe(true));
  });

  it("filters by account", async () => {
    const fetchMock = stubFetch();
    render(<AnalyticsPage />);
    await screen.findByTestId("filter-account");
    await act(async () => {
      fireEvent.change(screen.getByTestId("filter-account"), { target: { value: "spc_yt" } });
    });
    await waitFor(() =>
      expect(fetchMock.mock.calls.some(([url]) =>
        String(url).includes("social_account_id=spc_yt"))).toBe(true));
  });

  it("says so when nothing has been published", async () => {
    stubFetch({ totals: { views: 0, likes: 0, comments: 0, shares: 0, videos: 0, publications: 0 },
                by_platform: {}, publications: [] });
    render(<AnalyticsPage />);
    await screen.findByTestId("analytics-empty");
  });

  it("takes a snapshot on demand, then re-reads", async () => {
    const fetchMock = stubFetch();
    render(<AnalyticsPage />);
    await screen.findByTestId("refresh-analytics");
    fetchMock.mockClear();
    await act(async () => {
      fireEvent.click(screen.getByTestId("refresh-analytics"));
    });
    const posted = fetchMock.mock.calls.find(([url, init]) =>
      String(url).includes("/analytics/refresh") &&
      (init as RequestInit | undefined)?.method === "POST");
    expect(posted).toBeTruthy();
    // ...and re-reads afterwards rather than leaving the page on stale numbers.
    expect(fetchMock.mock.calls.some(([url, init]) =>
      String(url).includes("/analytics") &&
      (init as RequestInit | undefined)?.method !== "POST")).toBe(true);
  });

  it("says so when a refresh could not read every account", async () => {
    // The endpoint answers 200 with an error count; ignoring it makes a
    // refresh that captured nothing indistinguishable from one that worked.
    const fn = vi.fn().mockImplementation((url: string, init?: RequestInit) =>
      String(url).includes("/refresh") && init?.method === "POST"
        ? Promise.resolve({ ok: true, json: async () => ({ accounts: 2, snapshots: 0, errors: 2 }) })
        : Promise.resolve({ ok: true, json: async () => DATA }));
    vi.stubGlobal("fetch", fn);
    render(<AnalyticsPage />);
    await screen.findByTestId("refresh-analytics");
    await act(async () => {
      fireEvent.click(screen.getByTestId("refresh-analytics"));
    });
    expect(await screen.findByTestId("analytics-refresh-note"))
      .toHaveTextContent("2 account(s) unreachable");
  });

  it("stays quiet when every account was read", async () => {
    const fn = vi.fn().mockImplementation((url: string, init?: RequestInit) =>
      String(url).includes("/refresh") && init?.method === "POST"
        ? Promise.resolve({ ok: true, json: async () => ({ accounts: 1, snapshots: 1, errors: 0 }) })
        : Promise.resolve({ ok: true, json: async () => DATA }));
    vi.stubGlobal("fetch", fn);
    render(<AnalyticsPage />);
    await screen.findByTestId("refresh-analytics");
    await act(async () => {
      fireEvent.click(screen.getByTestId("refresh-analytics"));
    });
    expect(screen.queryByTestId("analytics-refresh-note")).toBeNull();
  });

  it("reports a refresh failure instead of looking like it worked", async () => {
    stubFetch({ error: "Publishing is disabled" }, false);
    render(<AnalyticsPage />);
    await screen.findByTestId("refresh-analytics");
    await act(async () => {
      fireEvent.click(screen.getByTestId("refresh-analytics"));
    });
    expect(await screen.findByTestId("analytics-error")).toHaveTextContent("Publishing is disabled");
  });

  it("surfaces an API error instead of rendering an empty page", async () => {
    stubFetch({ error: "Could not reach postforme." }, false);
    render(<AnalyticsPage />);
    expect(await screen.findByTestId("analytics-error")).toHaveTextContent("Could not reach");
  });

  it("opens on the Videos tab and mounts spend only on the Spend tab", async () => {
    stubFetch();
    render(<AnalyticsPage />);
    await screen.findByTestId("total-views");
    // Not mounted until asked for, so a visit does not fetch spend at all.
    expect(screen.queryByTestId("spend-card-stub")).toBeNull();
    await act(async () => {
      fireEvent.click(screen.getByTestId("tab-spend"));
    });
    expect(await screen.findByTestId("spend-card-stub")).toBeInTheDocument();
    expect(screen.queryByTestId("total-views")).toBeNull();
  });

  it("sorts highest first, with an unreported metric below a real zero", async () => {
    stubFetch({
      ...DATA,
      publications: [
        row({ id: "old", views: 10 }),
        row({ id: "none", views: null }),
        row({ id: "zero", views: 0 }),
        row({ id: "top", views: 500 }),
      ],
    });
    render(<AnalyticsPage />);
    await screen.findByTestId("analytics-row-old");
    // Newest first is the API's order, untouched.
    expect(rowOrder()).toEqual(["analytics-row-old", "analytics-row-none",
                                "analytics-row-zero", "analytics-row-top"]);
    fireEvent.change(screen.getByTestId("sort-by"), { target: { value: "views" } });
    expect(rowOrder()).toEqual(["analytics-row-top", "analytics-row-old",
                                "analytics-row-zero", "analytics-row-none"]);
  });

  it("sorts by likes, comments and shares too", async () => {
    stubFetch({
      ...DATA,
      publications: [row({ id: "a", likes: 1, comments: 9, shares: 2 }),
                     row({ id: "b", likes: 5, comments: 1, shares: 7 })],
    });
    render(<AnalyticsPage />);
    await screen.findByTestId("analytics-row-a");
    fireEvent.change(screen.getByTestId("sort-by"), { target: { value: "likes" } });
    expect(rowOrder()[0]).toBe("analytics-row-b");
    fireEvent.change(screen.getByTestId("sort-by"), { target: { value: "comments" } });
    expect(rowOrder()[0]).toBe("analytics-row-a");
    fireEvent.change(screen.getByTestId("sort-by"), { target: { value: "shares" } });
    expect(rowOrder()[0]).toBe("analytics-row-b");
  });

  it("names accounts as username and platform, asking without the feed probe", async () => {
    const fetchMock = stubRoutes(
      { ...DATA, publications: [row({ social_account_id: "spc_ig", platform: "instagram" })] },
      { ok: true, body: [{ id: "spc_ig", platform: "instagram", username: "demo_channel" }] });
    render(<AnalyticsPage />);
    await waitFor(() =>
      expect(optionTexts("filter-account")).toContainEqual(["spc_ig", "demo_channel (Instagram)"]));
    expect(fetchMock.mock.calls.some(([url]) =>
      String(url).endsWith("/publishing/accounts?feeds=0"))).toBe(true);
  });

  it("falls back to the id when the accounts lookup fails, and still filters by id", async () => {
    const fetchMock = stubRoutes(
      { ...DATA, publications: [row({ social_account_id: "spc_ig", platform: "instagram" })] },
      { ok: false, body: { error: "Publishing is disabled — turn it on in Settings first." } });
    render(<AnalyticsPage />);
    await screen.findByTestId("analytics-row-pub1");
    expect(optionTexts("filter-account")).toContainEqual(["spc_ig", "spc_ig (Instagram)"]);
    // A failed lookup is not an analytics error.
    expect(screen.queryByTestId("analytics-error")).toBeNull();
    await act(async () => {
      fireEvent.change(screen.getByTestId("filter-account"), { target: { value: "spc_ig" } });
    });
    await waitFor(() =>
      expect(fetchMock.mock.calls.some(([url]) =>
        String(url).includes("social_account_id=spc_ig"))).toBe(true));
  });

  // ── TMDEV-113: graphs, and a table that loads as it scrolls ───────────────

  it("filters by platform when its bar is clicked, through the API", async () => {
    const fetchMock = stubFetch();
    render(<AnalyticsPage />);
    const bar = await screen.findByTestId("bar-platform-youtube");
    await act(async () => {
      fireEvent.click(bar);
    });
    await waitFor(() =>
      expect(fetchMock.mock.calls.some(([url]) =>
        String(url).includes("platform=youtube"))).toBe(true));
    expect((screen.getByTestId("filter-platform") as HTMLSelectElement).value).toBe("youtube");
  });

  it("filters by account when its bar is clicked", async () => {
    const fetchMock = stubFetch();
    render(<AnalyticsPage />);
    const bar = await screen.findByTestId("bar-account-spc_yt");
    await act(async () => {
      fireEvent.click(bar);
    });
    await waitFor(() =>
      expect(fetchMock.mock.calls.some(([url]) =>
        String(url).includes("social_account_id=spc_yt"))).toBe(true));
  });

  it("draws the month graph from by_month, and copes without it", async () => {
    stubFetch({ ...DATA, by_month: [{ month: "2026-09", views: 42 }], timezone: "Asia/Tokyo" });
    render(<AnalyticsPage />);
    expect(await screen.findByTestId("month-2026-09"))
      .toHaveAttribute("title", "September 2026: 42 views gained");
    expect(screen.getByTestId("chart-month")).toHaveTextContent("Asia/Tokyo");
  });

  describe("lazy rows", () => {
    class FakeIO {
      static all: FakeIO[] = [];
      targets: Element[] = [];
      closed = false;
      constructor(public cb: IntersectionObserverCallback,
                  public opts?: IntersectionObserverInit) { FakeIO.all.push(this); }
      observe(el: Element) { this.targets.push(el); }
      disconnect() { this.closed = true; }
      unobserve() {}
      takeRecords() { return []; }
    }

    /** Scroll the sentinel into view: fire the one live observer. */
    async function reachBottom() {
      const io = FakeIO.all.filter((o) => !o.closed).at(-1)!;
      await act(async () => {
        io.cb(io.targets.map((target) => ({ isIntersecting: true, target })) as never,
              io as never);
      });
    }

    const MANY = { ...DATA, publications: Array.from({ length: 120 }, (_, i) =>
      row({ id: `p${i}`, views: i })) };

    afterEach(() => { FakeIO.all = []; });

    it("renders 50 rows, then 50 more each time the end of its own scroll box shows", async () => {
      vi.stubGlobal("IntersectionObserver", FakeIO);
      stubFetch(MANY);
      render(<AnalyticsPage />);
      await screen.findByTestId("analytics-row-p0");
      expect(rowOrder()).toHaveLength(50);
      expect(screen.getByTestId("analytics-more")).toHaveTextContent("50 of 120");
      // Observed against the table's box, not the page.
      expect(FakeIO.all.at(-1)!.opts?.root).toBe(screen.getByTestId("analytics-scroll"));
      await reachBottom();
      expect(rowOrder()).toHaveLength(100);
      await reachBottom();
      expect(rowOrder()).toHaveLength(120);
      expect(screen.queryByTestId("analytics-more")).toBeNull();
    });

    it("starts again from 50 when the sort changes", async () => {
      vi.stubGlobal("IntersectionObserver", FakeIO);
      stubFetch(MANY);
      render(<AnalyticsPage />);
      await screen.findByTestId("analytics-row-p0");
      await reachBottom();
      expect(rowOrder()).toHaveLength(100);
      await act(async () => {
        fireEvent.change(screen.getByTestId("sort-by"), { target: { value: "views" } });
      });
      expect(rowOrder()).toHaveLength(50);
      expect(rowOrder()[0]).toBe("analytics-row-p119");
    });

    it("renders every row where the browser cannot observe scrolling", async () => {
      vi.stubGlobal("IntersectionObserver", undefined);
      stubFetch(MANY);
      render(<AnalyticsPage />);
      await screen.findByTestId("analytics-row-p0");
      expect(rowOrder()).toHaveLength(120);
    });
  });

  it("falls back to the id for an account that is gone upstream", async () => {
    stubRoutes(
      { ...DATA, publications: [row({ social_account_id: "spc_gone", platform: "youtube" })] },
      { ok: true, body: [{ id: "spc_gone", platform: "", username: "", available: false }] });
    render(<AnalyticsPage />);
    await screen.findByTestId("analytics-row-pub1");
    await waitFor(() =>
      expect(optionTexts("filter-account")).toContainEqual(["spc_gone", "spc_gone (YouTube)"]));
  });
});
