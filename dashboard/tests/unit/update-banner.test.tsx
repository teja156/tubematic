/**
 * The update banner (TMDEV-114): shown under the top bar when the dashboard
 * server reports a newer stable release, dismissible per version.
 */
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const nav = vi.hoisted(() => ({ pathname: "/" }));
vi.mock("next/navigation", () => ({ usePathname: () => nav.pathname }));

import { UpdateBanner } from "@/components/UpdateBanner";

const UPDATE = {
  available: true,
  current: "2.0.0",
  latest: "2.0.1",
  release_url: "https://github.com/teja156/tubematic/releases/tag/v2.0.1",
  upgrade_url: "https://docs.tubematic.ai/user-guide/upgrading",
};

function mockFetch(body: unknown, status = 200) {
  const m = vi.fn().mockResolvedValue({ ok: status < 400, status, json: async () => body } as Response);
  vi.stubGlobal("fetch", m);
  return m;
}

describe("UpdateBanner", () => {
  beforeEach(() => {
    nav.pathname = "/";
    window.localStorage.clear();
  });
  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
    vi.useRealTimers();
  });

  it("names both versions and links the release and the upgrade guide in a new tab", async () => {
    const fetchMock = mockFetch(UPDATE);
    render(<UpdateBanner />);
    const banner = await screen.findByTestId("update-banner");
    expect(fetchMock).toHaveBeenCalledWith("/api/update-check", expect.objectContaining({ cache: "no-store" }));
    expect(banner.textContent).toContain("v2.0.1");
    expect(banner.textContent).toContain("v2.0.0");

    const release = screen.getByTestId("update-release-link");
    expect(release.getAttribute("href")).toBe(UPDATE.release_url);
    const guide = screen.getByTestId("update-guide-link");
    expect(guide.getAttribute("href")).toBe(UPDATE.upgrade_url);
    for (const a of [release, guide]) {
      expect(a.getAttribute("target")).toBe("_blank");
      expect(a.getAttribute("rel")).toContain("noopener");
    }
  });

  it("renders nothing when no update is available", async () => {
    const fetchMock = mockFetch({ available: false });
    render(<UpdateBanner />);
    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    expect(screen.queryByTestId("update-banner")).toBeNull();
  });

  it("renders nothing on a 401 or a failed request", async () => {
    const m401 = mockFetch({ error: "unauthorized" }, 401);
    const { unmount } = render(<UpdateBanner />);
    await waitFor(() => expect(m401).toHaveBeenCalled());
    expect(screen.queryByTestId("update-banner")).toBeNull();
    unmount();

    const rejected = vi.fn().mockRejectedValue(new Error("down"));
    vi.stubGlobal("fetch", rejected);
    render(<UpdateBanner />);
    await waitFor(() => expect(rejected).toHaveBeenCalled());
    expect(screen.queryByTestId("update-banner")).toBeNull();
  });

  it("does not check at all on the login page", async () => {
    nav.pathname = "/login";
    const fetchMock = mockFetch(UPDATE);
    render(<UpdateBanner />);
    await act(async () => {});
    expect(fetchMock).not.toHaveBeenCalled();
    expect(screen.queryByTestId("update-banner")).toBeNull();
  });

  it("refuses a link that is not https", async () => {
    mockFetch({ ...UPDATE, release_url: "javascript:alert(1)" });
    render(<UpdateBanner />);
    await act(async () => {});
    expect(screen.queryByTestId("update-banner")).toBeNull();
  });

  it("stays hidden for a dismissed version, in this and later page loads", async () => {
    mockFetch(UPDATE);
    const { unmount } = render(<UpdateBanner />);
    fireEvent.click(await screen.findByTestId("update-dismiss"));
    expect(screen.queryByTestId("update-banner")).toBeNull();
    unmount();

    const again = mockFetch(UPDATE);
    render(<UpdateBanner />);
    await waitFor(() => expect(again).toHaveBeenCalled());
    await act(async () => {});
    expect(screen.queryByTestId("update-banner")).toBeNull();
  });

  it("comes back for a newer release than the one dismissed", async () => {
    window.localStorage.setItem("tubematic.update-dismissed", "2.0.1");
    mockFetch({ ...UPDATE, latest: "2.0.2", release_url: UPDATE.release_url.replace("2.0.1", "2.0.2") });
    render(<UpdateBanner />);
    expect((await screen.findByTestId("update-banner")).textContent).toContain("v2.0.2");
  });

  it("still shows, and still dismisses for the page, when storage is blocked", async () => {
    vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => { throw new Error("blocked"); });
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => { throw new Error("blocked"); });
    mockFetch(UPDATE);
    render(<UpdateBanner />);
    fireEvent.click(await screen.findByTestId("update-dismiss"));
    expect(screen.queryByTestId("update-banner")).toBeNull();
  });

  it("checks again every 10 minutes", async () => {
    vi.useFakeTimers();
    const fetchMock = mockFetch({ available: false });
    render(<UpdateBanner />);
    await act(async () => {});
    expect(fetchMock).toHaveBeenCalledTimes(1);
    await act(async () => { vi.advanceTimersByTime(10 * 60_000); });
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });
});
