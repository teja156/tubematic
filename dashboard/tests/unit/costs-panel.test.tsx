/**
 * Settings → Costs (TMDEV-107). Guards that each model shows where its rate
 * came from, that the last successful sync time and a failed sync are both
 * visible, that Sync now posts to the sync route, that an unpriced model can be
 * given a price — typed per million tokens and sent per token — and that only
 * a manual rate offers Reset.
 */
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { describe, it, expect, vi, afterEach } from "vitest";
import { CostsPanel } from "@/components/CostsPanel";

vi.mock("@/components/SectionLabel", () => ({
  SectionLabel: ({ label }: { label: string }) => <div>{label}</div>,
}));
vi.mock("@/components/TimeZoneProvider", () => ({
  useTimeZone: () => ({ timeZone: "UTC", label: "UTC" }),
}));

const TABLE = {
  models: [
    { service: "gemini", model: "gemini-2.5-flash", source: "openrouter",
      rates: { input: 3e-7, output: 2.5e-6 }, tiered: false,
      effective_from: "2026-09-20T00:00:00Z" },
    { service: "openai", model: "gpt-5.6-sol", source: "manual", rates: { input: 2e-6 },
      tiered: false, effective_from: "2026-09-21T00:00:00Z" },
    { service: "gemini", model: "gemini-9-flash", source: null, rates: {}, tiered: false,
      effective_from: null },
  ],
  unpriced: [{ service: "gemini", model: "gemini-9-flash", calls: 4 }],
  unit_kinds: ["input", "input_audio", "input_image", "output", "reasoning", "output_image",
               "cache_read", "cache_write", "cache_write_1h"],
  last_sync_attempt_at: "2026-09-24T09:00:00Z",
  last_sync_ok_at: "2026-09-20T09:00:00Z",
  last_sync_error: "network unreachable",
};

function stub() {
  const fn = vi.fn().mockImplementation((url: string, init?: RequestInit) => {
    if (url.endsWith("/prices/sync"))
      return Promise.resolve({ ok: true, json: async () => ({ ok: true, updated: ["x"],
                                                              rejected: [] }) });
    if (url.endsWith("/prices/override") && init?.method === "POST")
      return Promise.resolve({ ok: true, json: async () => ({ ok: true, repriced: 4 }) });
    return Promise.resolve({ ok: true, json: async () => TABLE });
  });
  vi.stubGlobal("fetch", fn);
  return fn;
}

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

describe("CostsPanel", () => {
  it("names each model's source, and says when there is none", async () => {
    stub();
    render(<CostsPanel inputStyle={{}} />);
    expect(await screen.findByTestId("price-source-gemini-2.5-flash")).toHaveTextContent("OpenRouter");
    expect(screen.getByTestId("price-source-gpt-5.6-sol")).toHaveTextContent("manual");
    expect(screen.getByTestId("price-source-gemini-9-flash")).toHaveTextContent("no price");
  });

  it("shows rates per million tokens", async () => {
    stub();
    render(<CostsPanel inputStyle={{}} />);
    expect(await screen.findByTestId("price-row-gemini-2.5-flash")).toHaveTextContent("input $0.3");
  });

  it("shows the last successful sync and a failed one", async () => {
    stub();
    render(<CostsPanel inputStyle={{}} />);
    expect(await screen.findByTestId("costs-last-sync")).toHaveTextContent("Sep 20, 2026");
    expect(screen.getByTestId("costs-sync-error")).toHaveTextContent("network unreachable");
  });

  it("syncs on demand", async () => {
    const fn = stub();
    render(<CostsPanel inputStyle={{}} />);
    fireEvent.click(await screen.findByTestId("costs-sync-now"));
    await waitFor(() => expect(screen.getByTestId("costs-sync-note")).toHaveTextContent("1 updated"));
    expect(fn).toHaveBeenCalledWith("/api/proxy/prices/sync", expect.objectContaining({ method: "POST" }));
  });

  it("adds a price for an unpriced model, sent per token", async () => {
    const fn = stub();
    render(<CostsPanel inputStyle={{}} />);
    fireEvent.click(await screen.findByTestId("costs-add-gemini-9-flash"));
    fireEvent.change(screen.getByTestId("price-input-input"), { target: { value: "0.5" } });
    fireEvent.click(screen.getByTestId("price-save"));
    await waitFor(() => expect(fn).toHaveBeenCalledWith("/api/proxy/prices/override",
                                                        expect.objectContaining({ method: "POST" })));
    const call = fn.mock.calls.find(([u, i]) => String(u).endsWith("/prices/override") &&
                                                 (i as RequestInit)?.method === "POST");
    const body = JSON.parse(String((call![1] as RequestInit).body));
    expect(body).toEqual({ service: "gemini", model: "gemini-9-flash", rates: { input: 5e-7 } });
  });

  it("offers Reset only on a manual rate", async () => {
    stub();
    render(<CostsPanel inputStyle={{}} />);
    await screen.findByTestId("price-row-gpt-5.6-sol");
    expect(screen.getByTestId("price-reset-gpt-5.6-sol")).toBeInTheDocument();
    expect(screen.queryByTestId("price-reset-gemini-2.5-flash")).toBeNull();
  });
});
