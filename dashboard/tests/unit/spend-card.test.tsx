/**
 * The Analytics page's spend card (TMDEV-107, TMDEV-130) — where spend that
 * belongs to no video is visible at all. Guards that unpriced calls are called
 * out beside the total rather than folded in as $0, that the ElevenLabs pool
 * is shown when the key can read it and credits otherwise, and the disclaimer.
 * The range guards: a preset is sent by *name* for the API to resolve in the
 * host zone — the browser's own idea of "today" is unreliable until the host
 * zone loads, and stays wrong if it never does — a change re-fetches, the
 * label shows the days the API actually summed, and a broken custom range
 * never reaches the API.
 */
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { describe, it, expect, vi, afterEach } from "vitest";
import { SpendCard } from "@/components/SpendCard";

vi.mock("@/components/SectionLabel", () => ({
  SectionLabel: ({ label, count }: { label: string; count?: string }) => (
    <div data-testid="section-label">{label} {count}</div>
  ),
}));

const SPEND = {
  since: "2026-09-01T04:00:00Z", until: "2026-09-11T04:00:00Z", from: "2026-09-01",
  to: "2026-09-10", timezone: "America/New_York", total_usd: 18.4, videos: 14.1, research: 3.9, agent_other: 0.3,
  other: 0.1, video_count: 34, unpriced_calls: 3, voice_credits: 60000, preview_credits: 900,
  estimated: false, elevenlabs_pool: { tier: "creator", used: 70011, limit: 300000,
                                       resets_at_unix: 1791518545 },
};

function stub(body: unknown, ok = true) {
  const fn = vi.fn().mockImplementation(() =>
    Promise.resolve({ ok, status: ok ? 200 : 500, json: async () => body }));
  vi.stubGlobal("fetch", fn);
  return fn;
}

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

describe("SpendCard", () => {
  it("splits this month's spend and shows the ElevenLabs pool", async () => {
    stub(SPEND);
    render(<SpendCard />);
    expect(await screen.findByTestId("spend-total")).toHaveTextContent("$18.40");
    expect(screen.getByTestId("spend-videos")).toHaveTextContent("Videos (34)");
    expect(screen.getByTestId("spend-research")).toHaveTextContent("$3.90");
    expect(screen.getByTestId("spend-agent-other")).toHaveTextContent("$0.40");
    expect(screen.getByTestId("spend-credits")).toHaveTextContent("70,011 / 300,000");
  });

  it("asks for this month by name and labels it with the days the API summed", async () => {
    const fetchFn = stub(SPEND);
    render(<SpendCard />);
    await screen.findByTestId("spend-total");
    // No dates of the browser's own: the API decides which days "this month" is.
    expect(fetchFn).toHaveBeenCalledWith(
      "/api/proxy/usage/summary?preset=month", expect.anything());
    expect(screen.getByTestId("section-label")).toHaveTextContent("2026-09-01 → 2026-09-10");
    expect(screen.getByTestId("spend-notes")).toHaveTextContent("Days are in America/New_York");
  });

  it("re-fetches by name when a preset is chosen", async () => {
    const fetchFn = stub(SPEND);
    render(<SpendCard />);
    await screen.findByTestId("spend-total");
    fireEvent.change(screen.getByTestId("spend-range"), { target: { value: "week" } });
    await waitFor(() => expect(fetchFn).toHaveBeenLastCalledWith(
      "/api/proxy/usage/summary?preset=week", expect.anything()));
    fireEvent.change(screen.getByTestId("spend-range"), { target: { value: "today" } });
    await waitFor(() => expect(fetchFn).toHaveBeenLastCalledWith(
      "/api/proxy/usage/summary?preset=today", expect.anything()));
  });

  it("starts a custom range from the days that were showing, and fetches its edits", async () => {
    const fetchFn = stub(SPEND);
    render(<SpendCard />);
    await screen.findByTestId("spend-total");
    fireEvent.change(screen.getByTestId("spend-range"), { target: { value: "custom" } });
    expect(screen.getByTestId("spend-from")).toHaveValue("2026-09-01");
    expect(screen.getByTestId("spend-to")).toHaveValue("2026-09-10");
    fireEvent.change(screen.getByTestId("spend-from"), { target: { value: "2026-08-15" } });
    await waitFor(() => expect(fetchFn).toHaveBeenLastCalledWith(
      "/api/proxy/usage/summary?from=2026-08-15&to=2026-09-10", expect.anything()));
  });

  it("never sends a backwards or half-empty custom range", async () => {
    const fetchFn = stub(SPEND);
    render(<SpendCard />);
    await screen.findByTestId("spend-total");
    fireEvent.change(screen.getByTestId("spend-range"), { target: { value: "custom" } });
    const calls = fetchFn.mock.calls.length;
    fireEvent.change(screen.getByTestId("spend-from"), { target: { value: "2026-09-20" } });
    expect(await screen.findByTestId("spend-range-problem")).toHaveTextContent("after the end");
    fireEvent.change(screen.getByTestId("spend-from"), { target: { value: "" } });
    expect(screen.getByTestId("spend-range-problem")).toHaveTextContent("Pick both");
    expect(fetchFn.mock.calls.length).toBe(calls);
    // Figures for a range that is no longer the one shown must not linger.
    expect(screen.queryByTestId("spend-total")).toBeNull();
  });

  it("says the ElevenLabs pool is the billing period, not the range", async () => {
    stub(SPEND);
    render(<SpendCard />);
    expect(await screen.findByTestId("spend-credits")).toHaveTextContent("billing period");
    expect(screen.getByTestId("spend-notes")).toHaveTextContent("does not follow the range");
  });

  it("calls out unpriced calls beside the total", async () => {
    stub(SPEND);
    render(<SpendCard />);
    expect(await screen.findByTestId("spend-unpriced")).toHaveTextContent("+ 3 unpriced calls");
  });

  it("falls back to recorded credits when the pool cannot be read", async () => {
    stub({ ...SPEND, elevenlabs_pool: null });
    render(<SpendCard />);
    expect(await screen.findByTestId("spend-credits")).toHaveTextContent("60,900 credits");
  });

  it("carries the API list price disclaimer", async () => {
    stub(SPEND);
    render(<SpendCard />);
    expect(await screen.findByTestId("spend-notes")).toHaveTextContent("API list prices");
  });

  it("shows an error instead of a blank card", async () => {
    stub({ error: "boom" }, false);
    render(<SpendCard />);
    expect(await screen.findByTestId("spend-error")).toHaveTextContent("boom");
  });
});
