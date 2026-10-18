import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { TopBar } from "@/components/TopBar";

// TopBar reads the timezone from context and the pathname from next/navigation;
// neither is what these tests are about, so both are stubbed to something inert.
vi.mock("next/navigation", () => ({ usePathname: () => "/" }));
vi.mock("@/components/TimeZoneProvider", () => ({
  useTimeZone: () => ({ timeZone: "UTC", label: "UTC", degraded: true }),
}));

function mockFetch(response: unknown, ok = true) {
  vi.stubGlobal(
    "fetch",
    vi.fn().mockResolvedValue({ ok, json: () => Promise.resolve(response) } as Response),
  );
}

/** The badge must show the real version or nothing at all. A wrong version in a
 * bug report is worse than none, so every failure mode below renders nothing
 * rather than "unknown" or a fallback number. */
describe("TopBar version badge", () => {
  afterEach(() => vi.restoreAllMocks());

  it("shows the version the API reports, prefixed with v", async () => {
    mockFetch({ version: "1.0.1" });
    render(<TopBar />);
    await waitFor(() => expect(screen.getByTestId("version-badge").textContent).toBe("v1.0.1"));
  });

  it("renders nothing when the API sends no version field (an API older than this feature)", async () => {
    mockFetch({ timezone: "UTC", timezone_label: "UTC" });
    render(<TopBar />);
    // The health indicator is in the same cluster and does not depend on the
    // version, so waiting on it proves the bar rendered before asserting absence.
    await waitFor(() => expect(screen.getByTestId("health-status")).toBeTruthy());
    expect(screen.queryByTestId("version-badge")).toBeNull();
  });

  it("renders nothing on a non-ok HTTP response", async () => {
    mockFetch({ version: "1.0.1" }, false);
    render(<TopBar />);
    await waitFor(() => expect(screen.getByTestId("health-status")).toBeTruthy());
    expect(screen.queryByTestId("version-badge")).toBeNull();
  });

  it("renders nothing when the fetch rejects — the API is unreachable", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error("connection refused")));
    render(<TopBar />);
    await waitFor(() => expect(screen.getByTestId("health-status")).toBeTruthy());
    expect(screen.queryByTestId("version-badge")).toBeNull();
  });

  it("renders nothing for an empty version string rather than a bare v", async () => {
    mockFetch({ version: "" });
    render(<TopBar />);
    await waitFor(() => expect(screen.getByTestId("health-status")).toBeTruthy());
    expect(screen.queryByTestId("version-badge")).toBeNull();
  });
});

/** The badge is polled rather than fetched once, because the one thing it is
 * documented for — confirming an upgrade landed — happens *while the page is
 * open*. An upgrade restarts the API underneath it, and a once-on-mount fetch
 * would keep showing the version from before the upgrade. */
describe("TopBar version badge across an API restart", () => {
  afterEach(() => {
    vi.restoreAllMocks();
    vi.useRealTimers();
  });

  it("picks up a new version after an upgrade, instead of showing the old one", async () => {
    vi.useFakeTimers();
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce({ ok: true, json: async () => ({ version: "1.0.1" }) })
      .mockResolvedValue({ ok: true, json: async () => ({ version: "1.0.2" }) });
    vi.stubGlobal("fetch", fetchMock);

    render(<TopBar />);
    await vi.waitFor(() =>
      expect(screen.getByTestId("version-badge").textContent).toBe("v1.0.1"),
    );

    await vi.advanceTimersByTimeAsync(30_000);
    await vi.waitFor(() =>
      expect(screen.getByTestId("version-badge").textContent).toBe("v1.0.2"),
    );
  });

  it("drops the version while the API is down rather than showing a stale one", async () => {
    vi.useFakeTimers();
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce({ ok: true, json: async () => ({ version: "1.0.1" }) })
      .mockRejectedValue(new Error("connection refused"));
    vi.stubGlobal("fetch", fetchMock);

    render(<TopBar />);
    await vi.waitFor(() =>
      expect(screen.getByTestId("version-badge").textContent).toBe("v1.0.1"),
    );

    await vi.advanceTimersByTimeAsync(30_000);
    await vi.waitFor(() => expect(screen.queryByTestId("version-badge")).toBeNull());
  });

  it("stops polling once unmounted", async () => {
    vi.useFakeTimers();
    const fetchMock = vi
      .fn()
      .mockResolvedValue({ ok: true, json: async () => ({ version: "1.0.1" }) });
    vi.stubGlobal("fetch", fetchMock);

    const { unmount } = render(<TopBar />);
    await vi.waitFor(() => expect(screen.getByTestId("version-badge")).toBeTruthy());

    unmount();
    const callsAtUnmount = fetchMock.mock.calls.length;
    await vi.advanceTimersByTimeAsync(120_000);
    expect(fetchMock.mock.calls.length).toBe(callsAtUnmount);
  });
});
