/**
 * Logs page (TMDEV-86).
 *
 * The page's whole job is to turn GET /logs into something filterable, so the
 * behaviour worth pinning is what it puts on the query string — and that the
 * service and level lists come from the API's own response rather than a second
 * copy of the allowlist living here, which is the thing that would silently
 * drift once a service is added or renamed.
 */
import { render, screen, act, fireEvent, waitFor } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import LogsPage from "@/app/logs/page";
import type { LogRecord } from "@/lib/types";

vi.mock("@/components/SectionLabel", () => ({
  SectionLabel: ({ label, count }: { label: string; count?: string }) => (
    <div data-testid="section-label">{label} {count}</div>
  ),
}));

vi.mock("@/components/TimeZoneProvider", () => ({
  useTimeZone: () => ({ timeZone: "UTC", label: "UTC", degraded: false }),
}));

const RECORDS: LogRecord[] = [
  { ts: "2026-09-06T12:00:00Z", service: "renderer", level: "error", message: "render failed" },
  { ts: "2026-09-06T11:00:00Z", service: "api", level: "info", message: "GET /videos -> 200" },
];

function stubFetch(body: unknown = { records: RECORDS, count: 2, limit: 200,
                                     services: ["api", "mcp", "renderer", "poll"],
                                     levels: ["debug", "info", "warning", "error"] },
                   ok = true) {
  const fn = vi.fn().mockResolvedValue({ ok, json: async () => body });
  vi.stubGlobal("fetch", fn);
  return fn;
}

function lastUrl(fn: ReturnType<typeof vi.fn>): string {
  return String(fn.mock.calls[fn.mock.calls.length - 1][0]);
}

beforeEach(() => vi.clearAllMocks());
afterEach(() => { vi.restoreAllMocks(); vi.unstubAllGlobals(); });

describe("LogsPage", () => {
  it("renders records newest-first as the API returned them", async () => {
    stubFetch();
    await act(async () => { render(<LogsPage />); });
    const rows = await screen.findAllByTestId("log-row");
    expect(rows).toHaveLength(2);
    expect(rows[0]).toHaveTextContent("render failed");
    expect(rows[0]).toHaveAttribute("data-level", "error");
    expect(rows[0]).toHaveAttribute("data-service", "renderer");
  });

  it("takes its service and level options from the API response, not a local list", async () => {
    // A hardcoded copy here is exactly what would go stale when a service is
    // added or renamed server-side.
    stubFetch({ records: [], count: 0, limit: 200,
                services: ["api", "invented-service"], levels: ["info"] });
    await act(async () => { render(<LogsPage />); });
    await waitFor(() => {
      expect(screen.getByTestId("filter-service")).toHaveTextContent("invented-service");
    });
  });

  it("sends no service parameter until one is picked", async () => {
    const fn = stubFetch();
    await act(async () => { render(<LogsPage />); });
    expect(lastUrl(fn)).not.toContain("service=");

    await act(async () => {
      fireEvent.change(screen.getByTestId("filter-service"), { target: { value: "mcp" } });
    });
    await waitFor(() => expect(lastUrl(fn)).toContain("service=mcp"));
  });

  it("puts level, search and limit on the query string", async () => {
    const fn = stubFetch();
    await act(async () => { render(<LogsPage />); });

    await act(async () => {
      fireEvent.change(screen.getByTestId("filter-level"), { target: { value: "warning" } });
    });
    await waitFor(() => expect(lastUrl(fn)).toContain("level=warning"));

    await act(async () => {
      fireEvent.change(screen.getByTestId("filter-search"), { target: { value: "timed out" } });
    });
    await waitFor(() => expect(lastUrl(fn)).toContain("q=timed+out"));

    await act(async () => {
      fireEvent.change(screen.getByTestId("filter-limit"), { target: { value: "500" } });
    });
    await waitFor(() => expect(lastUrl(fn)).toContain("limit=500"));
  });

  it("refreshes on demand — there is no polling or live tail", async () => {
    const fn = stubFetch();
    await act(async () => { render(<LogsPage />); });
    const before = fn.mock.calls.length;
    await act(async () => { fireEvent.click(screen.getByTestId("logs-refresh")); });
    await waitFor(() => expect(fn.mock.calls.length).toBe(before + 1));
  });

  it("surfaces an API error rather than showing an empty list", async () => {
    stubFetch({ error: "Unknown service: 'nope'" }, false);
    await act(async () => { render(<LogsPage />); });
    expect(await screen.findByTestId("logs-error")).toHaveTextContent("Unknown service");
    expect(screen.queryByTestId("log-list")).toBeNull();
  });

  it("says so when the API is unreachable", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error("boom")));
    await act(async () => { render(<LogsPage />); });
    expect(await screen.findByTestId("logs-error")).toHaveTextContent("Could not reach");
  });

  it("explains an empty result rather than showing a bare blank", async () => {
    stubFetch({ records: [], count: 0, limit: 200, services: [], levels: [] });
    await act(async () => { render(<LogsPage />); });
    expect(await screen.findByTestId("log-list-empty")).toHaveTextContent("stdout");
  });
});
