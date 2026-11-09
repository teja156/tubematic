import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { DiskUsage, DISK_USAGE_POLL_MS } from "@/components/DiskUsage";
import type { StorageUsage } from "@/lib/types";

const GB = 1024 ** 3;
const MB = 1024 ** 2;

function usage(host: StorageUsage["host"] = null): StorageUsage {
  const items = [
    { key: "videos", bytes: 3 * GB }, { key: "voice_previews", bytes: 2 * MB },
    { key: "jobs", bytes: 1 * GB }, { key: "scenes", bytes: 5 * MB },
    { key: "database", bytes: 40 * MB }, { key: "mascots", bytes: 0 },
    { key: "backups", bytes: 200 * MB }, { key: "logs", bytes: 60 * MB },
  ];
  const data = items.reduce((a, i) => a + i.bytes, 0);
  const hostTotal = host
    ? (host.images?.current_bytes ?? 0) + (host.images?.old_bytes ?? 0)
      + (host.containers_bytes ?? 0) + (host.install_bytes ?? 0)
    : 0;
  return { data: { measured_at: "2026-11-09T10:00:00Z", items, total_bytes: data },
           host, total_bytes: data + hostTotal };
}

const HOST = {
  measured_at: new Date(Date.now() - 20 * 60_000).toISOString(),
  images: { current_bytes: 5 * GB, old_bytes: 4.5 * GB, old_count: 2 },
  containers_bytes: 30 * MB, build_cache_bytes: 2 * GB, install_bytes: 900 * MB,
};

function mockFetch(body: unknown, ok = true) {
  const fn = vi.fn().mockResolvedValue({ ok, status: ok ? 200 : 404,
    json: () => Promise.resolve(body) } as Response);
  vi.stubGlobal("fetch", fn);
  return fn;
}

async function openPopup() {
  fireEvent.click(await screen.findByTestId("disk-usage"));
  return screen.findByTestId("disk-usage-popup");
}

describe("DiskUsage", () => {
  afterEach(() => { vi.restoreAllMocks(); vi.useRealTimers(); });

  it("shows the API's total in the bar, from the storage route", async () => {
    const fn = mockFetch(usage(HOST));
    render(<DiskUsage />);
    const badge = await screen.findByTestId("disk-usage");
    expect(badge.textContent).toContain("14.7 GB");  // "≥": two old images
    expect(String(fn.mock.calls[0][0])).toBe("/api/proxy/storage");
  });

  it("breaks the total down into data and Docker lines", async () => {
    mockFetch(usage(HOST));
    render(<DiskUsage />);
    const popup = await openPopup();
    expect(popup.textContent).toContain("Finished videos");
    expect(screen.getByTestId("disk-row-videos").textContent).toContain("3.0 GB");
    expect(screen.getByTestId("disk-row-images_current").textContent).toContain("5.0 GB");
    expect(screen.getByTestId("disk-row-images_old").textContent).toContain("4.5 GB");
    expect(screen.getByTestId("disk-row-images_old").textContent).toContain("next upgrade removes them");
    expect(screen.getByTestId("disk-row-install").textContent).toContain("900.0 MB");
    expect(popup.textContent).toContain("measured 20 min ago");
  });

  it("shows several old images' size as a floor, one image's as exact", async () => {
    mockFetch(usage(HOST));
    render(<DiskUsage />);
    await openPopup();
    expect(screen.getByTestId("disk-row-images_old").textContent).toContain("≥ 4.5 GB");
  });

  it("marks the bar's and the popup's total as a floor when the old-image figure is one", async () => {
    mockFetch(usage(HOST));
    render(<DiskUsage />);
    expect((await screen.findByTestId("disk-usage")).textContent).toContain("≥ 14.7 GB");
    await openPopup();
    expect(screen.getByTestId("disk-usage-total").textContent).toBe("≥ 14.7 GB");
  });

  it("shows a single old image's size, and the total, without the floor mark", async () => {
    mockFetch(usage({ ...HOST, images: { current_bytes: 5 * GB, old_bytes: GB, old_count: 1 } }));
    render(<DiskUsage />);
    await openPopup();
    const row = screen.getByTestId("disk-row-images_old").textContent ?? "";
    expect(row).toContain("1.0 GB");
    expect(row).not.toContain("≥");
    expect(screen.getByTestId("disk-usage").textContent).not.toContain("≥");
    expect(screen.getByTestId("disk-usage-total").textContent).not.toContain("≥");
  });

  it("marks the build cache as outside the total", async () => {
    mockFetch(usage(HOST));
    render(<DiskUsage />);
    await openPopup();
    expect(screen.getByTestId("disk-row-build_cache").textContent).toContain("not in the total");
  });

  it("says the host half is not measured yet instead of showing zeros", async () => {
    mockFetch(usage(null));
    render(<DiskUsage />);
    await openPopup();
    expect(screen.getByTestId("disk-usage-unmeasured")).toBeTruthy();
    expect(screen.queryByTestId("disk-row-images_current")).toBeNull();
  });

  it("shows unknown, not 0 B, for a figure Docker could not give", async () => {
    mockFetch(usage({ ...HOST, images: null, containers_bytes: null }));
    render(<DiskUsage />);
    await openPopup();
    expect(screen.getByTestId("disk-row-images_old").textContent).toContain("unknown");
    expect(screen.getByTestId("disk-row-containers").textContent).toContain("unknown");
  });

  it("fetches afresh when opened", async () => {
    const fn = mockFetch(usage(HOST));
    render(<DiskUsage />);
    await screen.findByTestId("disk-usage");
    const before = fn.mock.calls.length;
    await openPopup();
    await waitFor(() => expect(fn.mock.calls.length).toBe(before + 1));
  });

  it.each([
    ["a 404 from an older API", () => mockFetch({ error: "not found" }, false)],
    ["a body of another shape", () => mockFetch({ version: "2.1.0" })],
    ["a network error", () => vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error("down")))],
  ])("renders nothing on %s", async (_name, setup) => {
    setup();
    const { container } = render(<DiskUsage />);
    await new Promise((r) => setTimeout(r, 20));
    expect(container.textContent).toBe("");
  });

  it("refreshes on its poll interval", async () => {
    vi.useFakeTimers();
    const fn = mockFetch(usage(null));
    render(<DiskUsage />);
    await vi.waitFor(() => expect(fn).toHaveBeenCalledTimes(1));
    await vi.advanceTimersByTimeAsync(DISK_USAGE_POLL_MS);
    expect(fn).toHaveBeenCalledTimes(2);
  });
});
