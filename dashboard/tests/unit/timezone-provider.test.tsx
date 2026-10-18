import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { TimeZoneProvider, useTimeZone } from "@/components/TimeZoneProvider";

function Probe() {
  const { timeZone, label, degraded } = useTimeZone();
  return (
    <div>
      <span data-testid="tz">{timeZone}</span>
      <span data-testid="label">{label}</span>
      <span data-testid="degraded">{String(degraded)}</span>
    </div>
  );
}

function mockFetchOnce(response: unknown, ok = true) {
  vi.stubGlobal(
    "fetch",
    vi.fn().mockResolvedValue({ ok, json: () => Promise.resolve(response) } as Response),
  );
}

describe("TimeZoneProvider degradation matrix", () => {
  afterEach(() => vi.restoreAllMocks());

  it("accepts a valid IANA timezone + label from the API", async () => {
    mockFetchOnce({ timezone: "America/New_York", timezone_label: "EDT (UTC-04:00)" });
    render(<TimeZoneProvider><Probe /></TimeZoneProvider>);
    await waitFor(() => expect(screen.getByTestId("tz").textContent).toBe("America/New_York"));
    expect(screen.getByTestId("label").textContent).toBe("EDT (UTC-04:00)");
    expect(screen.getByTestId("degraded").textContent).toBe("false");
  });

  it("degrades to UTC when the API response has no timezone fields (older API)", async () => {
    mockFetchOnce({});
    render(<TimeZoneProvider><Probe /></TimeZoneProvider>);
    await waitFor(() => expect(screen.getByTestId("degraded").textContent).toBe("true"));
    expect(screen.getByTestId("tz").textContent).toBe("UTC");
  });

  it("degrades to UTC when timezone is null", async () => {
    mockFetchOnce({ timezone: null, timezone_label: "local" });
    render(<TimeZoneProvider><Probe /></TimeZoneProvider>);
    await waitFor(() => expect(screen.getByTestId("degraded").textContent).toBe("true"));
    expect(screen.getByTestId("tz").textContent).toBe("UTC");
  });

  it("does not let a human label leak into the timezone slot — no RangeError, degrades to UTC", async () => {
    mockFetchOnce({ timezone: "EDT (UTC-04:00)", timezone_label: "EDT (UTC-04:00)" });
    expect(() => render(<TimeZoneProvider><Probe /></TimeZoneProvider>)).not.toThrow();
    await waitFor(() => expect(screen.getByTestId("degraded").textContent).toBe("true"));
    expect(screen.getByTestId("tz").textContent).toBe("UTC");
  });

  it("degrades to UTC on a non-ok HTTP response", async () => {
    mockFetchOnce({}, false);
    render(<TimeZoneProvider><Probe /></TimeZoneProvider>);
    await waitFor(() => expect(screen.getByTestId("degraded").textContent).toBe("true"));
  });

  it("degrades to UTC when fetch rejects (network error / proxy down)", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error("connection refused")));
    render(<TimeZoneProvider><Probe /></TimeZoneProvider>);
    await waitFor(() => expect(screen.getByTestId("degraded").textContent).toBe("true"));
    expect(screen.getByTestId("tz").textContent).toBe("UTC");
  });

  it("useTimeZone outside a provider returns the safe UTC default (never throws)", () => {
    expect(() => render(<Probe />)).not.toThrow();
    expect(screen.getByTestId("tz").textContent).toBe("UTC");
  });
});
